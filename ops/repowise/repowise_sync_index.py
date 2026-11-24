#!/usr/bin/env python3
"""Stage, shard, validate and transactionally promote Repowise SQLite replicas.

Production Git worktrees are read-only inputs; all indexing happens under /opt/repowise-knowledge.
"""
import argparse
import errno
import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import yaml
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

LIVE_DEFAULT = Path('/var/lib/docker/volumes/oea9obpkhzbgkmipxwqmz2hj-repowise-workspace/_data')
BASE = Path('/opt/repowise-knowledge')
LOCK = Path('/run/lock/repowise-github-sync.lock')
REPOS = ('product', 'harness')
UID, GID = 999, 999
FTS_COLUMNS = ('page_id', 'title', 'content', 'summary', 'target_path', 'vocabulary', 'digest')
FTS_DDL = 'CREATE VIRTUAL TABLE page_fts USING fts5(page_id UNINDEXED,title,content,summary,target_path,vocabulary,digest)'
FTS_INSERT = """INSERT INTO page_fts(page_id,title,content,summary,target_path,vocabulary,digest)
SELECT id,COALESCE(title,''),COALESCE(content,''),COALESCE(summary,''),COALESCE(target_path,''),
CASE WHEN json_valid(metadata_json) THEN COALESCE(json_extract(metadata_json,'$.file_vocabulary'),'') ELSE '' END,
COALESCE(digest,'') FROM wiki_pages WHERE repository_id=? AND COALESCE(freshness_status,'fresh')!='tombstone'"""
FTS_SHADOWS = {'page_fts_config', 'page_fts_content', 'page_fts_data', 'page_fts_docsize', 'page_fts_idx'}
INDIRECT = {
    'component_snapshots': 'SELECT c.* FROM component_snapshots c JOIN snapshot_runs p ON c.run_id=p.id WHERE p.repository_id=?',
    'chat_messages': 'SELECT c.* FROM chat_messages c JOIN conversations p ON c.conversation_id=p.id WHERE p.repository_id=?',
    'decision_evidence': 'SELECT c.* FROM decision_evidence c JOIN decision_records p ON c.decision_id=p.id WHERE p.repository_id=?',
    'page_version_archive': 'SELECT c.* FROM page_version_archive c JOIN page_archive p ON c.archive_id=p.id WHERE p.repository_id=?',
}
WS_ARTIFACTS = (
    '.repowise-workspace/analysis_config.json',
    '.repowise-workspace/breaking_changes.json',
    '.repowise-workspace/conformance.json',
    '.repowise-workspace/contracts.json',
    '.repowise-workspace/cross_repo_edges.json',
    '.repowise-workspace/member_refresh.json',
    '.repowise-workspace/system_graph.json',
)


def fail(message):
    raise RuntimeError(message)


def move_to_archive(src, dest):
    # Under ProtectSystem/ReadWritePaths, live and rollback paths are separate bind mounts.
    try:
        os.replace(src, dest)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        shutil.move(str(src), str(dest))


def q(name):
    return '"' + name.replace('"', '""') + '"'



@contextmanager
def sync_lock():
    inherited = os.environ.get('REPOWISE_SYNC_LOCK_FD')
    if inherited:
        try:
            fd = int(inherited)
            target = Path(os.readlink(f'/proc/self/fd/{fd}')).resolve()
            if target != LOCK.resolve():
                fail('inherited sync lock fd does not point to the sync lock')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception as exc:
            fail(f'inherited sync lock is not held: {exc}')
        yield
        return
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(LOCK, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def stage_path(value):
    p = Path(value).resolve(strict=True)
    base = BASE.resolve(strict=True)
    if p == base or base not in p.parents or p == LIVE_DEFAULT.resolve():
        fail(f'refusing non-staging root: {p}')
    return p


def connect(path, readonly=False):
    path = Path(path)
    if readonly:
        db = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=30)
        db.execute('PRAGMA query_only=ON')
    else:
        db = sqlite3.connect(str(path), timeout=60)
        db.execute('PRAGMA busy_timeout=60000')
        db.execute('PRAGMA foreign_keys=ON')
    return db


def sqlite_backup(src, dst):
    src, dst = Path(src), Path(dst)
    if not src.is_file():
        fail(f'missing SQLite source: {src}')
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        fail(f'refusing to overwrite SQLite backup target: {dst}')
    source = connect(src, readonly=True)
    target = sqlite3.connect(str(dst), timeout=60)
    try:
        source.backup(target, pages=500, sleep=0.05)
        target.commit()
    finally:
        target.close()
        source.close()


def owner_rows(db, table, cols, target_id):
    order = ','.join(q(c) for c in cols)
    if table == 'repositories':
        sql, args = f'SELECT * FROM repositories WHERE id=? ORDER BY {order}', (target_id,)
    elif table == 'webhook_events':
        fks = db.execute('PRAGMA foreign_key_list(webhook_events)').fetchall()
        refs = [r for r in fks if r[2] == 'generation_jobs']
        if refs:
            job_col, parent_col = q(refs[0][3]), q(refs[0][4] or 'id')
            unassigned = db.execute(
                f'SELECT COUNT(*) FROM webhook_events e LEFT JOIN generation_jobs g ON e.{job_col}=g.{parent_col} '
                'WHERE e.repository_id IS NULL AND g.repository_id IS NULL'
            ).fetchone()[0]
            cross = db.execute(
                f'SELECT COUNT(*) FROM webhook_events e JOIN generation_jobs g ON e.{job_col}=g.{parent_col} '
                'WHERE e.repository_id=? AND g.repository_id<>?', (target_id, target_id)
            ).fetchone()[0]
            if unassigned or cross:
                fail(f'webhook_events cannot be assigned safely: unassigned={unassigned}, cross_repo={cross}')
            sql = (f'SELECT e.* FROM webhook_events e LEFT JOIN generation_jobs g ON e.{job_col}=g.{parent_col} '
                   'WHERE e.repository_id=? OR (e.repository_id IS NULL AND g.repository_id=?) ORDER BY ' +
                   ','.join('e.' + q(c) for c in cols))
            args = (target_id, target_id)
        else:
            unassigned = db.execute('SELECT COUNT(*) FROM webhook_events WHERE repository_id IS NULL').fetchone()[0]
            if unassigned:
                fail(f'unassignable webhook_events: {unassigned}')
            sql, args = f'SELECT * FROM webhook_events WHERE repository_id=? ORDER BY {order}', (target_id,)
    elif table in INDIRECT:
        sql, args = INDIRECT[table] + ' ORDER BY ' + order, (target_id,)
    elif 'repository_id' in cols:
        sql, args = f'SELECT * FROM {q(table)} WHERE repository_id=? ORDER BY {order}', (target_id,)
    else:
        sql, args = f'SELECT * FROM {q(table)} ORDER BY {order}', ()
    return db.execute(sql, args).fetchall()


def row_digest(rows):
    serialized = []
    for row in rows:
        serialized.append(json.dumps(
            [{'bytes': v.hex()} if isinstance(v, bytes) else v for v in row],
            sort_keys=True, separators=(',', ':'), default=str,
        ))
    h = hashlib.sha256()
    for row in sorted(serialized):
        h.update(row.encode())
        h.update(b'\n')
    return h.hexdigest(), len(rows)


def integrity(db):
    result = db.execute('PRAGMA integrity_check').fetchone()[0]
    if result != 'ok':
        fail(f'SQLite integrity_check failed: {result}')
    fk = db.execute('PRAGMA foreign_key_check').fetchall()
    if fk:
        fail(f'SQLite foreign_key_check failed: {fk[:3]}')


def remove_sqlite_sidecars(path):
    for suffix in ('-wal', '-shm'):
        side = Path(str(path) + suffix)
        if side.exists() or side.is_symlink():
            side.unlink()


def checkpoint_sqlite(path):
    db = connect(path)
    try:
        row = db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
        if row and row[0]:
            fail(f'SQLite WAL checkpoint busy: {path}')
    finally:
        db.close()
    remove_sqlite_sidecars(path)


def expected_sha(root, repo):
    return subprocess.check_output(['git', '-c', f'safe.directory={root/repo}', '-C', str(root/repo), 'rev-parse', 'HEAD'], text=True).strip()


def check_wiki(path, repo, sha, full=True):
    db = connect(path, readonly=True)
    try:
        integrity(db) if full else None
        rows = db.execute('SELECT id,name,local_path,head_commit FROM repositories').fetchall()
        if len(rows) != 1 or rows[0][1] != repo:
            fail(f'{path}: expected exactly one {repo} repository row, got {[r[1] for r in rows]}')
        if rows[0][2] != f'/workspace/{repo}' or rows[0][3] != sha:
            fail(f'{path}: wrong repo path/SHA: {rows[0][2]} {rows[0][3]}')
        target_id = rows[0][0]
        pages = {r[0] for r in db.execute("SELECT id FROM wiki_pages WHERE repository_id=? AND COALESCE(freshness_status,'fresh')!='tombstone'", (target_id,))}
        fts = [r[0] for r in db.execute('SELECT page_id FROM page_fts')]
        if not pages or len(fts) != len(pages) or set(fts) != pages:
            fail(f'{path}: page/FTS mismatch pages={len(pages)} FTS={len(fts)}')
        for table, in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            cols = {r[1] for r in db.execute(f'PRAGMA table_info({q(table)})')}
            if 'repository_id' in cols:
                n = db.execute(f'SELECT COUNT(*) FROM {q(table)} WHERE repository_id IS NOT NULL AND repository_id<>?', (target_id,)).fetchone()[0]
                if n:
                    fail(f'{path}: foreign-owned rows remain in {table}: {n}')
        return {'repo': repo, 'head': sha, 'pages': len(pages), 'symbols': db.execute('SELECT COUNT(*) FROM wiki_symbols WHERE repository_id=?', (target_id,)).fetchone()[0]}
    finally:
        db.close()


def partition_wiki(path, repo, sha):
    path = Path(path)
    db = connect(path)
    try:
        integrity(db)
        records = db.execute('SELECT id,name,local_path,head_commit FROM repositories ORDER BY name').fetchall()
        names = {r[1] for r in records}
        if names not in ({repo}, set(REPOS)):
            fail(f'{path}: unexpected repo rows {sorted(names)}')
        target = next((r for r in records if r[1] == repo), None)
        if target is None or target[2] != f'/workspace/{repo}' or target[3] != sha:
            fail(f'{path}: target {repo} does not match expected path/SHA {sha}')
        target_id = target[0]
        if db.execute('SELECT COUNT(*) FROM wiki_pages WHERE repository_id=?', (target_id,)).fetchone()[0] == 0:
            fail(f'{path}: target repository has no indexed pages')
        if 'wiki_page_versions' in {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
            bad = db.execute('SELECT COUNT(*) FROM wiki_page_versions v JOIN wiki_pages p ON p.id=v.page_id WHERE v.repository_id=? AND p.repository_id<>?', (target_id, target_id)).fetchone()[0]
            unowned = db.execute('SELECT COUNT(*) FROM wiki_page_versions WHERE repository_id IS NULL OR repository_id NOT IN (SELECT id FROM repositories)').fetchone()[0]
            if bad or unowned:
                fail(f'{path}: page-version ownership invalid cross={bad} unowned={unowned}')
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        logical = {}
        for table in tables:
            if table == 'page_fts' or table in FTS_SHADOWS or table == 'sqlite_stat1':
                continue
            cols = [r[1] for r in db.execute(f'PRAGMA table_info({q(table)})')]
            if not cols or table == 'page_fts_config':
                continue
            count = db.execute(f'SELECT COUNT(*) FROM {q(table)}').fetchone()[0]
            if table not in INDIRECT and table != 'repositories' and 'repository_id' not in cols and count:
                fail(f'{path}: populated ownerless table needs an explicit rule: {table} ({count})')
            logical[table] = row_digest(owner_rows(db, table, cols, target_id))
        db.execute('BEGIN IMMEDIATE')
        try:
            if len(records) > 1:
                db.execute('DELETE FROM wiki_page_versions WHERE repository_id<>?', (target_id,))
                if 'webhook_events' in tables:
                    refs = [r for r in db.execute('PRAGMA foreign_key_list(webhook_events)').fetchall() if r[2] == 'generation_jobs']
                    db.execute('DELETE FROM webhook_events WHERE repository_id IS NOT NULL AND repository_id<>?', (target_id,))
                    if refs:
                        job_col, parent_col = q(refs[0][3]), q(refs[0][4] or 'id')
                        db.execute(f'DELETE FROM webhook_events WHERE repository_id IS NULL AND {job_col} IN (SELECT {parent_col} FROM generation_jobs WHERE repository_id<>?)', (target_id,))
                    else:
                        db.execute('DELETE FROM webhook_events WHERE repository_id IS NULL')
                db.execute('DELETE FROM repositories WHERE id<>?', (target_id,))
            remaining = db.execute('SELECT id,name FROM repositories').fetchall()
            if remaining != [(target_id, repo)]:
                fail(f'{path}: RepoRegistry shard is not singular: {remaining}')
            for table in tables:
                cols = {r[1] for r in db.execute(f'PRAGMA table_info({q(table)})')}
                if 'repository_id' in cols:
                    n = db.execute(f'SELECT COUNT(*) FROM {q(table)} WHERE repository_id IS NOT NULL AND repository_id<>?', (target_id,)).fetchone()[0]
                    if n:
                        fail(f'{path}: foreign-owned rows remain in {table}: {n}')
            fts_sql = db.execute("SELECT sql FROM sqlite_master WHERE name='page_fts'").fetchone()
            if not fts_sql or 'fts5' not in fts_sql[0].lower():
                fail(f'{path}: page_fts is not the expected FTS5 table')
            db.execute('DROP TABLE page_fts')
            db.execute(FTS_DDL)
            db.execute(FTS_INSERT, (target_id,))
            db.execute('ANALYZE')
            for table, expected in logical.items():
                cols = [r[1] for r in db.execute(f'PRAGMA table_info({q(table)})')]
                actual = row_digest(owner_rows(db, table, cols, target_id))
                if actual != expected:
                    fail(f'{path}: target data changed unexpectedly in {table}')
            page_ids = {r[0] for r in db.execute("SELECT id FROM wiki_pages WHERE repository_id=? AND COALESCE(freshness_status,'fresh')!='tombstone'", (target_id,))}
            fts_ids = [r[0] for r in db.execute('SELECT page_id FROM page_fts')]
            if len(fts_ids) != len(page_ids) or set(fts_ids) != page_ids:
                fail(f'{path}: rebuilt FTS mismatch pages={len(page_ids)} FTS={len(fts_ids)}')
            token = None
            for (title,) in db.execute("SELECT title FROM wiki_pages WHERE repository_id=? AND COALESCE(freshness_status,'fresh')!='tombstone'", (target_id,)):
                words = re.findall(r'[A-Za-z0-9_]{4,}', title or '')
                if words:
                    token = words[0]
                    break
            if token:
                hit = db.execute('SELECT page_id FROM page_fts WHERE page_fts MATCH ? LIMIT 1', (token,)).fetchone()
                if not hit or hit[0] not in page_ids:
                    fail(f'{path}: FTS MATCH self-test failed')
            db.commit()
        except Exception:
            db.rollback()
            raise
        integrity(db)
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchall()
        return {'repo': repo, 'head': sha, 'pages': len(page_ids), 'fts_rows': len(fts_ids), 'logical_rows_preserved': sum(n for _, n in logical.values())}
    finally:
        db.close()



def workspace_check(root, full=True):
    root = Path(root)
    config_path = root / '.repowise-workspace.yaml'
    if not config_path.is_file():
        fail(f'missing .repowise-workspace.yaml under {root}')
    try:
        cfg = yaml.safe_load(config_path.read_text())
        entries = cfg['repos'] if isinstance(cfg, dict) else None
        aliases = {str(item['alias']): item for item in entries}
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
        fail(f'invalid workspace YAML: {exc}')
    if set(aliases) != set(REPOS):
        fail(f'workspace YAML aliases differ: {sorted(aliases)}')
    for repo in REPOS:
        expected = expected_sha(root, repo)
        if aliases[repo].get('last_commit_at_index') != expected:
            fail(f'workspace YAML indexed SHA mismatch repo={repo}')
    dbpath = root / '.repowise-workspace/workspace.db'
    if not dbpath.is_file():
        fail(f'missing workspace.db under {root}')
    db = connect(dbpath, readonly=True)
    try:
        integrity(db) if full else None
        cols = {r[1] for r in db.execute('PRAGMA table_info(repos)')}
        if 'alias' in cols:
            aliases = {r[0] for r in db.execute('SELECT alias FROM repos')}
            if aliases != set(REPOS):
                fail(f'workspace.db aliases differ: {sorted(aliases)}')
    finally:
        db.close()
    for rel in WS_ARTIFACTS:
        artifact = root / rel
        if not artifact.is_file():
            fail(f'missing workspace artifact: {rel}')
        try:
            json.loads(artifact.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            fail(f'invalid JSON workspace artifact {rel}: {exc}')


def validate_root(root, full=True):
    root = Path(root).resolve()
    out = []
    shas = {}
    for repo in REPOS:
        sha = expected_sha(root, repo)
        shas[repo] = sha
        out.append(check_wiki(root / repo / '.repowise/wiki.db', repo, sha, full=full))
        state = root / repo / '.repowise/state.json'
        if not state.is_file():
            fail(f'missing {repo} state.json')
        try:
            json.loads(state.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            fail(f'invalid {repo} state.json: {exc}')
    workspace_check(root, full=full)
    return shas, out


def seed(live_root, stage_root):
    live = Path(live_root).resolve(strict=True)
    stage = stage_path(stage_root)
    if live == stage or live in stage.parents or stage in live.parents:
        fail('live and stage roots must be disjoint')
    cfg = live / '.repowise-workspace.yaml'
    ws_src = live / '.repowise-workspace'
    if not cfg.is_file() or not (ws_src / 'workspace.db').is_file():
        fail('live workspace configuration or workspace.db is missing')
    shutil.copy2(cfg, stage / cfg.name)
    ws_dst = stage / '.repowise-workspace'
    ws_dst.mkdir(parents=True, exist_ok=True)
    for item in ws_src.iterdir():
        if item.name in {'workspace.db', 'workspace.db-wal', 'workspace.db-shm'}:
            continue
        dest = ws_dst / item.name
        if item.is_file():
            shutil.copy2(item, dest)
        elif item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
    sqlite_backup(ws_src / 'workspace.db', ws_dst / 'workspace.db')
    for repo in REPOS:
        src = live / repo / '.repowise'
        dst = stage / repo / '.repowise'
        if not (src / 'wiki.db').is_file() or not (src / 'state.json').is_file():
            fail(f'{repo}: live wiki.db/state.json missing')
        dst.mkdir(parents=True, exist_ok=True)
        for name in ('state.json', 'config.yaml', 'decisions.yaml'):
            source = src / name
            if source.is_file():
                shutil.copy2(source, dst / name)
        sqlite_backup(src / 'wiki.db', dst / 'wiki.db')
    for base, dirs, files in os.walk(stage):
        os.chown(base, UID, GID)
        for name in files:
            p = Path(base) / name
            if not p.is_symlink():
                os.chown(p, UID, GID)
    print(f'SEED_OK stage={stage}')


def check_live(live_root, expected):
    try:
        for repo in REPOS:
            result = check_wiki(Path(live_root) / repo / '.repowise/wiki.db', repo, expected[repo], full=False)
            print(f'LIVE_REPO_OK {repo} {result["head"]}')
        workspace_check(live_root, full=False)
        print('LIVE_CURRENT')
        return True
    except Exception as exc:
        print(f'LIVE_NEEDS_SYNC {exc}')
        return False


def container_stopped(name):
    r = subprocess.run(['docker', 'inspect', '--format', '{{.State.Running}}', name], capture_output=True, text=True)
    if r.returncode != 0:
        fail(f'cannot inspect required stopped container {name}: {r.stderr.strip()}')
    if r.stdout.strip().lower() == 'true':
        fail(f'refusing file promotion while container is running: {name}')


def assert_no_live_consumers(live):
    live = Path(live).resolve(strict=True)
    ps = subprocess.run(['docker', 'ps', '-q'], capture_output=True, text=True)
    if ps.returncode:
        fail(f'cannot inspect running containers: {ps.stderr.strip()}')
    ids = ps.stdout.split()
    if not ids:
        return
    inspected = subprocess.run(['docker', 'inspect', *ids], capture_output=True, text=True)
    if inspected.returncode:
        fail(f'cannot inspect running container mounts: {inspected.stderr.strip()}')
    consumers = []
    for container in json.loads(inspected.stdout):
        name = container.get('Name', '').lstrip('/')
        for mount in container.get('Mounts', []):
            source = mount.get('Source')
            if not source:
                continue
            source = Path(source).resolve()
            if source == live or source in live.parents or live in source.parents:
                destination = mount.get('Destination', '?')
                consumers.append(f'{name} ({source} -> {destination})')
                break
    if consumers:
        fail('refusing live-file operation while containers mount the workspace: ' + ', '.join(consumers))


def artifact_specs():
    specs = []
    for repo in REPOS:
        specs.extend([(f'{repo}/.repowise/wiki.db', 'sqlite'), (f'{repo}/.repowise/state.json', 'file')])
    # Workspace config carries repo indexed_at/last_commit_at_index as well as
    # conformance rules. Promoting SQLite without YAML leaves status stale.
    specs.append(('.repowise-workspace.yaml', 'yaml'))
    specs.append(('.repowise-workspace/workspace.db', 'sqlite'))
    specs.extend((rel, 'file') for rel in WS_ARTIFACTS)
    return specs


def write_manifest(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def copy_metadata(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    os.chown(dst, UID, GID)


def backup_sidecar(dest, backup_root, suffix):
    side = Path(str(dest) + suffix)
    if not side.exists():
        return None
    rel = side.name + suffix if False else None
    return side



def promote(stage_root, live_root, backup_root, stopped):
    stage = stage_path(stage_root)
    live = Path(live_root).resolve(strict=True)
    if stage == live or stage in live.parents or live in stage.parents:
        fail('live and stage roots must be disjoint')
    for name in stopped:
        container_stopped(name)
    assert_no_live_consumers(live)
    expected, _ = validate_root(stage, full=True)
    backup = Path(backup_root).resolve()
    base = BASE.resolve(strict=True)
    if base not in backup.parents:
        fail(f'rollback directory must be under {base}')
    if backup.exists():
        fail(f'rollback directory already exists: {backup}')
    if backup == stage or backup in stage.parents or stage in backup.parents or backup == live or backup in live.parents or live in backup.parents:
        fail('rollback directory must be disjoint from live and stage roots')
    backup.parent.mkdir(parents=True, exist_ok=True)
    building = backup.with_name(f'.{backup.name}.building-{os.getpid()}')
    if building.exists():
        fail(f'rollback build directory already exists: {building}')
    building.mkdir(mode=0o700)
    (building / 'sidecars').mkdir(mode=0o700)
    (building / 'failed-current').mkdir(mode=0o700)
    entries = []
    try:
        for rel, kind in artifact_specs():
            src, dest = stage / rel, live / rel
            if not src.is_file():
                fail(f'stage artifact missing: {rel}')
            original = dest.is_file()
            item = {'path': rel, 'kind': kind, 'original_exists': original, 'sidecars': []}
            if original:
                saved = building / rel
                saved.parent.mkdir(parents=True, exist_ok=True)
                if kind == 'sqlite':
                    sqlite_backup(dest, saved)
                    db = connect(saved, readonly=True)
                    try:
                        integrity(db)
                    finally:
                        db.close()
                else:
                    shutil.copy2(dest, saved)
            if kind == 'sqlite':
                for suffix in ('-wal', '-shm'):
                    side = Path(str(dest) + suffix)
                    if side.is_file():
                        side_saved = building / 'sidecars' / (rel.replace('/', '__') + suffix)
                        shutil.copy2(side, side_saved)
                        item['sidecars'].append({'suffix': suffix, 'saved': str(side_saved.relative_to(building))})
            entries.append(item)
        manifest_path = building / 'manifest.json'
        manifest = {'version': 1, 'created_at': datetime.now(timezone.utc).isoformat(), 'live_root': str(live), 'stage_root': str(stage), 'expected_shas': expected, 'artifacts': entries}
        write_manifest(manifest_path, manifest)
        os.replace(building, backup)
    except Exception:
        if building.exists():
            shutil.rmtree(building)
        raise

    prepared = []
    write_started = False
    try:
        for rel, kind in artifact_specs():
            src, dest = stage / rel, live / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(f'.{dest.name}.syncing-{os.getpid()}')
            if tmp.exists():
                fail(f'temporary promotion file already exists: {tmp}')
            prepared.append((rel, kind, tmp, dest))
            if kind == 'sqlite':
                sqlite_backup(src, tmp)
                db = connect(tmp, readonly=True)
                try:
                    integrity(db)
                finally:
                    db.close()
                checkpoint_sqlite(tmp)
                os.chown(tmp, UID, GID)
                os.chmod(tmp, 0o600)
            else:
                shutil.copy2(src, tmp)
                os.chown(tmp, UID, GID)
        assert_no_live_consumers(live)
        for rel, kind, tmp, dest in prepared:
            write_started = True
            if kind == 'sqlite':
                for suffix in ('-wal', '-shm'):
                    side = Path(str(dest) + suffix)
                    if side.exists() or side.is_symlink():
                        displaced = backup / 'failed-current' / 'sidecars' / (rel.replace('/', '__') + suffix)
                        displaced.parent.mkdir(parents=True, exist_ok=True)
                        if displaced.exists():
                            displaced = displaced.with_name(f'{displaced.name}.{int(time.time())}')
                        move_to_archive(side, displaced)
            os.replace(tmp, dest)
        manifest['promoted'] = True
        write_manifest(backup / 'manifest.json', manifest)
    except Exception as exc:
        for _, _, tmp, _ in prepared:
            if tmp.exists() or tmp.is_symlink():
                tmp.unlink()
            remove_sqlite_sidecars(tmp)
        if write_started:
            try:
                restore_backup(live, backup)
            except Exception as rollback_exc:
                raise RuntimeError(f'promotion failed ({exc}); automatic rollback also failed ({rollback_exc}); backup={backup}') from rollback_exc
        raise
    print(f'PROMOTE_OK backup={backup} product={expected["product"]} harness={expected["harness"]}')


def restore_backup(live_root, backup_root):
    live, backup = Path(live_root).resolve(strict=True), Path(backup_root).resolve(strict=True)
    base = BASE.resolve(strict=True)
    if base not in backup.parents or backup == live or backup in live.parents or live in backup.parents:
        fail('rollback directory must be under the sync base and disjoint from live')
    manifest_path = backup / 'manifest.json'
    if not manifest_path.is_file():
        fail(f'rollback manifest missing: {manifest_path}')
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        fail(f'rollback manifest invalid: {exc}')
    if manifest.get('version') != 1 or Path(manifest.get('live_root', '')).resolve() != live:
        fail('rollback manifest version or live_root mismatch')
    assert_no_live_consumers(live)
    specs = dict(artifact_specs())
    items = manifest.get('artifacts')
    if not isinstance(items, list):
        fail('rollback manifest artifacts must be a list')
    paths = []
    for item in items:
        rel = item.get('path') if isinstance(item, dict) else None
        if not isinstance(rel, str) or Path(rel).is_absolute() or '..' in Path(rel).parts:
            fail(f'unsafe rollback artifact path: {rel!r}')
        if rel not in specs or item.get('kind') != specs[rel]:
            fail(f'unexpected rollback artifact: {rel}')
        paths.append(rel)
        if item.get('original_exists'):
            saved = backup / rel
            if not saved.is_file():
                fail(f'rollback backup missing: {saved}')
            if item['kind'] == 'sqlite':
                db = connect(saved, readonly=True)
                try:
                    integrity(db)
                finally:
                    db.close()
            else:
                try:
                    if item['kind'] == 'yaml':
                        cfg = yaml.safe_load(saved.read_text())
                        if not isinstance(cfg, dict) or {x.get('alias') for x in cfg.get('repos', [])} != set(REPOS):
                            fail(f'rollback workspace YAML aliases invalid: {rel}')
                    else:
                        json.loads(saved.read_text())
                except (OSError, ValueError, yaml.YAMLError) as exc:
                    fail(f'rollback metadata backup invalid for {rel}: {exc}')
    if len(paths) != len(set(paths)) or set(paths) != set(specs):
        fail('rollback manifest artifact set is incomplete or duplicated')

    prepared = {}
    try:
        for item in items:
            if not item.get('original_exists'):
                continue
            rel, kind = item['path'], item['kind']
            dest, saved = live / rel, backup / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(f'.{dest.name}.rollback-{os.getpid()}')
            if tmp.exists() or tmp.is_symlink():
                fail(f'temporary rollback file already exists: {tmp}')
            if kind == 'sqlite':
                sqlite_backup(saved, tmp)
                db = connect(tmp, readonly=True)
                try:
                    integrity(db)
                finally:
                    db.close()
                checkpoint_sqlite(tmp)
                os.chown(tmp, UID, GID)
                os.chmod(tmp, 0o600)
            else:
                shutil.copy2(saved, tmp)
                os.chown(tmp, UID, GID)
            prepared[rel] = tmp
    except Exception:
        for tmp in prepared.values():
            if tmp.exists() or tmp.is_symlink():
                tmp.unlink()
            remove_sqlite_sidecars(tmp)
        raise

    failed = backup / 'failed-current'
    failed.mkdir(parents=True, exist_ok=True)
    try:
        for item in reversed(items):
            rel, kind = item['path'], item['kind']
            dest = live / rel
            if kind == 'sqlite':
                for suffix in ('-wal', '-shm'):
                    side = Path(str(dest) + suffix)
                    if side.exists() or side.is_symlink():
                        failed_side = failed / 'sidecars' / (rel.replace('/', '__') + suffix)
                        failed_side.parent.mkdir(parents=True, exist_ok=True)
                        if failed_side.exists():
                            failed_side = failed_side.with_name(f'{failed_side.name}.{int(time.time())}')
                        move_to_archive(side, failed_side)
            if dest.exists() or dest.is_symlink():
                failed_dest = failed / rel
                failed_dest.parent.mkdir(parents=True, exist_ok=True)
                if failed_dest.exists() or failed_dest.is_symlink():
                    failed_dest = failed_dest.with_name(f'{failed_dest.name}.{int(time.time())}')
                move_to_archive(dest, failed_dest)
            if item.get('original_exists'):
                os.replace(prepared.pop(rel), dest)
        manifest['rolled_back_at'] = datetime.now(timezone.utc).isoformat()
        write_manifest(manifest_path, manifest)
    except Exception:
        for tmp in prepared.values():
            if tmp.exists() or tmp.is_symlink():
                tmp.unlink()
            remove_sqlite_sidecars(tmp)
        raise
    print(f'ROLLBACK_OK backup={backup} failed_current={failed}')


def parse_expected(args):
    return {'product': args.product_sha, 'harness': args.harness_sha}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    p = sub.add_parser('seed'); p.add_argument('--live-root', default=str(LIVE_DEFAULT), type=Path); p.add_argument('--stage-root', required=True, type=Path)
    p = sub.add_parser('shard'); p.add_argument('--stage-root', required=True, type=Path)
    p = sub.add_parser('validate'); p.add_argument('--root', required=True, type=Path)
    p = sub.add_parser('check-live'); p.add_argument('--live-root', default=str(LIVE_DEFAULT), type=Path); p.add_argument('--product-sha', required=True); p.add_argument('--harness-sha', required=True)
    p = sub.add_parser('promote'); p.add_argument('--stage-root', required=True, type=Path); p.add_argument('--live-root', default=str(LIVE_DEFAULT), type=Path); p.add_argument('--backup-root', required=True, type=Path); p.add_argument('--require-stopped', action='append', default=[])
    p = sub.add_parser('rollback'); p.add_argument('--live-root', default=str(LIVE_DEFAULT), type=Path); p.add_argument('--backup-root', required=True, type=Path); p.add_argument('--require-stopped', action='append', default=[])
    args = parser.parse_args()
    with sync_lock():
        if args.mode == 'seed':
            seed(args.live_root, args.stage_root)
        elif args.mode == 'shard':
            root = stage_path(args.stage_root)
            for repo in REPOS:
                print(json.dumps(partition_wiki(root / repo / '.repowise/wiki.db', repo, expected_sha(root, repo))))
        elif args.mode == 'validate':
            root = Path(args.root).resolve(strict=True)
            shas, repos = validate_root(root, full=True)
            print(json.dumps({'stage': str(root), 'repos': repos, 'workspace': 'ok'}))
        elif args.mode == 'check-live':
            current = check_live(args.live_root, parse_expected(args))
            return 0 if current else 1
        elif args.mode == 'promote':
            promote(args.stage_root, args.live_root, args.backup_root, args.require_stopped)
        elif args.mode == 'rollback':
            for name in args.require_stopped:
                container_stopped(name)
            restore_backup(args.live_root, args.backup_root)
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)

