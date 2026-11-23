#!/usr/bin/env bash
# Stage and verify GitHub main first; never switch or reset live source worktrees.
# Deployed as /opt/repowise-knowledge/sync-from-github.sh with the helpers from
# this directory. See ops/repowise/README.md for the install map.
set -Eeuo pipefail
exec 9>/run/lock/repowise-github-sync.lock
flock -n 9 || { echo "SYNC_SKIPPED lock-held"; exit 0; }
export REPOWISE_SYNC_LOCK_FD=9
export GIT_TERMINAL_PROMPT=0

BASE=/opt/repowise-knowledge
INDEX_TOOL=$BASE/sync-index-replicas.py
MCP_SMOKE=$BASE/mcp-stage-smoke.py
SEED_GATE=$BASE/repowise_sync_gate.py
STATUS=$BASE/github-main.json
LIVE=/var/lib/docker/volumes/oea9obpkhzbgkmipxwqmz2hj-repowise-workspace/_data
VOLUME=oea9obpkhzbgkmipxwqmz2hj-repowise-workspace
MIRRORS=/home/opencode/projects/repowise-mirrors
OPENCODE=opencode-26aqp0flyvdinjn6dklxnb1c
MCP=repowise-mcp-lecwi3emh9hjxir7gphmalie
STAGE_ONLY=${REPOWISE_SYNC_STAGE_ONLY:-0}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
STAGE=$BASE/staging-sync-$STAMP-$$
BACKUP=$BASE/rollback/sync-$STAMP-$
DECISIONS_REL=.repowise/decisions.yaml
DECISIONS_SAVE=$BACKUP/preserved-harness-decisions.yaml
TEST_MCP=repowise-stage-smoke-$STAMP-$$
INDEX_IMAGE=$(docker inspect --format '{{.Config.Image}}' "$MCP")

PRODUCT_SHA=
HARNESS_SHA=
BASELINE_PRODUCT_SHA=
BASELINE_HARNESS_SHA=
CONSUMERS=()
SERVICES_STOPPED=0
PROMOTED=0
VERIFIED=0
RECOVERY_FAILED=0
TEST_CREATED=0

fail() { echo "SYNC_ERROR $*" >&2; exit 1; }

write_status() {
  local tmp
  tmp=$(mktemp "$BASE/.github-main.XXXXXX")
  python3 - "$tmp" "$PRODUCT_SHA" "$HARNESS_SHA" <<'PY'
import datetime, json, sys
path, product, harness = sys.argv[1:]
with open(path, 'w') as fh:
    json.dump({'fetched_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'product': product, 'harness': harness}, fh)
    fh.write('\n')
PY
  chmod 0644 "$tmp"
  mv -f "$tmp" "$STATUS"
}

fetch_main() {
  local repo mirror attempt done
  for repo in product harness; do
    mirror=$MIRRORS/$repo.git
    done=0
    for attempt in 1 2 3; do
      if docker exec "$OPENCODE" sh -lc "set -eu; M=$mirror; GIT_TERMINAL_PROMPT=0 timeout 100 git -c credential.helper=/root/.config/opencode/bin/git-credential-github-app --git-dir=\"\$M\" fetch --quiet --depth=50 origin +refs/heads/main:refs/heads/main"; then
        done=1
        break
      fi
      echo "SYNC_FETCH_RETRY repo=$repo attempt=$attempt" >&2
      sleep 3
    done
    [[ $done == 1 ]] || fail "github-fetch repo=$repo"
  done
  PRODUCT_SHA=$(git --git-dir="$MIRRORS/product.git" rev-parse refs/heads/main)
  HARNESS_SHA=$(git --git-dir="$MIRRORS/harness.git" rev-parse refs/heads/main)
  [[ $PRODUCT_SHA =~ ^[0-9a-f]{40}$ && $HARNESS_SHA =~ ^[0-9a-f]{40}$ ]] || fail "invalid-main-sha"
  echo "SYNC_GITHUB_MAIN product=$PRODUCT_SHA harness=$HARNESS_SHA"
  write_status
}

check_live_worktrees() {
  local repo expected current
  for repo in product harness; do
    expected=$BASELINE_PRODUCT_SHA
    [[ $repo == harness ]] && expected=$BASELINE_HARNESS_SHA
    current=$(git -c "safe.directory=$LIVE/$repo" -C "$LIVE/$repo" rev-parse HEAD)
    [[ $current == "$expected" ]] || fail "live-worktree-changed-during-stage repo=$repo live=$current baseline=$expected; preserving live worktree"
  done
}

# Prepare source updates without altering a running checkout. Only fast-forward
# Git commits already verified against private GitHub main in the staged index.
# Refuse any overlapping local tracked/untracked path; leave unrelated dirty
# submodules and files intact.
prepare_live_sources() {
  local repo old expected path
  local -a changed
  for repo in product harness; do
    old=$BASELINE_PRODUCT_SHA
    expected=$PRODUCT_SHA
    [[ $repo == harness ]] && { old=$BASELINE_HARNESS_SHA; expected=$HARNESS_SHA; }
    [[ $(git -c "safe.directory=$LIVE/$repo" -C "$LIVE/$repo" rev-parse HEAD) == "$old" ]] || fail "source-head-moved repo=$repo"
    git -c "safe.directory=$STAGE/$repo" -C "$STAGE/$repo" merge-base --is-ancestor "$old" "$expected" || fail "source-non-fast-forward repo=$repo"
    mapfile -d '' -t changed < <(git -c "safe.directory=$STAGE/$repo" -C "$STAGE/$repo" diff --name-only -z "$old" "$expected")
    for path in "${changed[@]}"; do
      if [[ $repo == harness && $path == "$DECISIONS_REL" ]] &&
         [[ -n $(git -c "safe.directory=$LIVE/$repo" -C "$LIVE/$repo" status --porcelain -- "$path") ]]; then
        # A generated, accepted decision store is tracked by OLD Git, but
        # current main intentionally deletes that tracked path. Preserve it
        # only when the independently indexed stage has identical bytes.
        [[ -z $(git -c "safe.directory=$STAGE/$repo" -C "$STAGE/$repo" ls-tree -r --name-only "$expected" -- "$path") ]] || fail "decisions-still-tracked-in-target"
        [[ -f "$LIVE/$repo/$path" && -f "$STAGE/$repo/$path" ]] || fail "decisions-preserve-missing"
        cmp -s "$LIVE/$repo/$path" "$STAGE/$repo/$path" || fail "decisions-changed-since-stage"
        echo "SOURCE_GENERATED_DECISIONS_ADMITTED bytes=$(wc -c < "$LIVE/$repo/$path")"
        continue
      fi
      [[ -z $(git -c "safe.directory=$LIVE/$repo" -C "$LIVE/$repo" status --porcelain -- "$path") ]] || fail "source-dirty-overlap repo=$repo path=$path"
    done
    git -c "safe.directory=$LIVE/$repo" -C "$LIVE/$repo" fetch --quiet --no-tags "$STAGE/$repo" "$expected" || fail "source-fetch-failed repo=$repo"
    echo "SOURCE_PREPARED repo=$repo old=$old new=$expected paths=${#changed[@]}"
  done
}

advance_live_sources() {
  local repo old expected now preserve_decisions
  for repo in product harness; do
    old=$BASELINE_PRODUCT_SHA
    expected=$PRODUCT_SHA
    [[ $repo == harness ]] && { old=$BASELINE_HARNESS_SHA; expected=$HARNESS_SHA; }
    now=$(git -c "safe.directory=$LIVE/$repo" -C "$LIVE/$repo" rev-parse HEAD)
    [[ $now == "$old" ]] || fail "source-head-drift-during-promotion repo=$repo"
    preserve_decisions=0
    if [[ $repo == harness && $old != "$expected" ]] &&
       [[ -f "$LIVE/$repo/$DECISIONS_REL" && -f "$STAGE/$repo/$DECISIONS_REL" ]] &&
       [[ -z $(git -c "safe.directory=$STAGE/$repo" -C "$STAGE/$repo" ls-tree -r --name-only "$expected" -- "$DECISIONS_REL") ]]; then
      cmp -s "$LIVE/$repo/$DECISIONS_REL" "$STAGE/$repo/$DECISIONS_REL" || fail "decisions-promotion-source-changed"
      [[ -d "$BACKUP" && ! -e "$DECISIONS_SAVE" ]] || fail "decisions-backup-not-ready"
      cp -p "$LIVE/$repo/$DECISIONS_REL" "$DECISIONS_SAVE" || fail "decisions-preserve-copy-failed"
      cmp -s "$DECISIONS_SAVE" "$STAGE/$repo/$DECISIONS_REL" || fail "decisions-preserve-readback-failed"
      git -c "safe.directory=$LIVE/$repo" -C "$LIVE/$repo" restore --source=HEAD --worktree -- "$DECISIONS_REL" || fail "decisions-source-restore-failed"
      preserve_decisions=1
    fi
    if [[ $old != "$expected" ]]; then
      git -c "safe.directory=$LIVE/$repo" -C "$LIVE/$repo" merge --ff-only "$expected" || fail "source-fast-forward-failed repo=$repo"
    fi
    if [[ $preserve_decisions == 1 ]]; then
      cp -p "$DECISIONS_SAVE" "$LIVE/$repo/$DECISIONS_REL" || fail "decisions-post-merge-restore-failed"
      cmp -s "$DECISIONS_SAVE" "$LIVE/$repo/$DECISIONS_REL" || fail "decisions-post-merge-readback-failed"
      echo "SOURCE_GENERATED_DECISIONS_PRESERVED"
    fi
    [[ $(git -c "safe.directory=$LIVE/$repo" -C "$LIVE/$repo" rev-parse HEAD) == "$expected" ]] || fail "source-advance-readback-failed repo=$repo"
    echo "SOURCE_ADVANCED repo=$repo commit=$expected"
  done
}

restore_live_sources() {
  local repo baseline now
  for repo in product harness; do
    baseline=$BASELINE_PRODUCT_SHA
    [[ $repo == harness ]] && baseline=$BASELINE_HARNESS_SHA
    now=$(git -c "safe.directory=$LIVE/$repo" -C "$LIVE/$repo" rev-parse HEAD) || return 1
    if [[ $repo == harness && -f "$DECISIONS_SAVE" && $now != "$baseline" ]] &&
       [[ -f "$LIVE/$repo/$DECISIONS_REL" ]]; then
      cmp -s "$DECISIONS_SAVE" "$LIVE/$repo/$DECISIONS_REL" || return 1
      mv "$LIVE/$repo/$DECISIONS_REL" "$BACKUP/preserved-harness-decisions-after-failure.yaml" || return 1
    fi
    if [[ $now != "$baseline" ]]; then
      # Native merge-aware reset preserves unrelated dirty paths, unlike --hard.
      git -c "safe.directory=$LIVE/$repo" -C "$LIVE/$repo" reset --merge "$baseline" || return 1
    fi
    if [[ $repo == harness && -f "$DECISIONS_SAVE" ]]; then
      cp -p "$DECISIONS_SAVE" "$LIVE/$repo/$DECISIONS_REL" || return 1
      cmp -s "$DECISIONS_SAVE" "$LIVE/$repo/$DECISIONS_REL" || return 1
    fi
    [[ $(git -c "safe.directory=$LIVE/$repo" -C "$LIVE/$repo" rev-parse HEAD) == "$baseline" ]] || return 1
    echo "SOURCE_ROLLBACK_OK repo=$repo commit=$baseline"
  done
}

run_indexer() {
  docker run --rm --network none --memory=4g --memory-swap=4g --cpus=1 \
    --mount "type=bind,source=$STAGE,target=/workspace" \
    --workdir /workspace --entrypoint /usr/bin/env "$INDEX_IMAGE" \
    -i HOME=/tmp PATH="$IMAGE_PATH" REPOWISE_TELEMETRY_DISABLED=1 \
    DO_NOT_TRACK=1 REPOWISE_NO_COST_TRACKING=1 "$@"
}

start_consumers() {
  local name
  for name in "${CONSUMERS[@]}"; do
    [[ $name == repowise-mcp-* ]] && continue
    if [[ $(docker inspect --format '{{.State.Running}}' "$name" 2>/dev/null || true) != true ]]; then
      docker start "$name" >/dev/null
    fi
  done
  for name in "${CONSUMERS[@]}"; do
    [[ $name == repowise-mcp-* ]] || continue
    if [[ $(docker inspect --format '{{.State.Running}}' "$name" 2>/dev/null || true) != true ]]; then
      docker start "$name" >/dev/null
    fi
  done
  SERVICES_STOPPED=0
}

stop_consumers() {
  local name
  SERVICES_STOPPED=1
  for name in "${CONSUMERS[@]}"; do
    [[ $name == repowise-mcp-* ]] || continue
    if [[ $(docker inspect --format '{{.State.Running}}' "$name" 2>/dev/null || true) == true ]]; then
      docker stop --time 30 "$name" >/dev/null
    fi
  done
  for name in "${CONSUMERS[@]}"; do
    [[ $name == repowise-mcp-* ]] && continue
    if [[ $(docker inspect --format '{{.State.Running}}' "$name" 2>/dev/null || true) == true ]]; then
      docker stop --time 30 "$name" >/dev/null
    fi
  done
  SERVICES_STOPPED=1
}

cleanup() {
  local rc=$?
  trap - EXIT
  set +e
  if [[ $TEST_CREATED == 1 ]]; then docker rm -f "$TEST_MCP" >/dev/null 2>&1; fi
  if [[ $PROMOTED == 1 && $VERIFIED != 1 ]]; then
    echo "SYNC_RECOVERY post-promotion verification failed; restoring backup=$BACKUP" >&2
    stop_consumers
    local args=(python3 "$INDEX_TOOL" rollback --backup-root "$BACKUP")
    local name
    for name in "${CONSUMERS[@]}"; do args+=(--require-stopped "$name"); done
    if "${args[@]}" && restore_live_sources; then
      PROMOTED=0
      start_consumers
    else
      echo "SYNC_CRITICAL database-or-git-rollback-failed backup=$BACKUP; consumers remain stopped" >&2
      RECOVERY_FAILED=1
      rc=1
    fi
  fi
  if [[ $SERVICES_STOPPED == 1 && $RECOVERY_FAILED == 0 ]]; then
    if ! start_consumers; then
      echo "SYNC_CRITICAL service-restart-failed consumers=${CONSUMERS[*]}" >&2
      rc=1
    fi
  fi
  unset REPOWISE_API_KEY REPOWISE_EMBEDDER
  exit "$rc"
}
trap cleanup EXIT

[[ -x $INDEX_TOOL && -x $MCP_SMOKE && -x $SEED_GATE ]] || fail "missing sync helper"
fetch_main
# Capture exact internally consistent live baseline. GitHub main may legitimately
# advance, but concurrent live worktree changes during staged validation must fail.
BASELINE_PRODUCT_SHA=$(git -c "safe.directory=$LIVE/product" -C "$LIVE/product" rev-parse HEAD)
BASELINE_HARNESS_SHA=$(git -c "safe.directory=$LIVE/harness" -C "$LIVE/harness" rev-parse HEAD)
[[ $BASELINE_PRODUCT_SHA =~ ^[0-9a-f]{40}$ && $BASELINE_HARNESS_SHA =~ ^[0-9a-f]{40}$ ]] || fail "invalid-live-baseline-sha"
python3 "$INDEX_TOOL" check-live --product-sha "$BASELINE_PRODUCT_SHA" --harness-sha "$BASELINE_HARNESS_SHA" || fail "inconsistent-live-baseline"
INITIAL_PRODUCT_SHA=$PRODUCT_SHA
INITIAL_HARNESS_SHA=$HARNESS_SHA
check_live_worktrees
if python3 "$INDEX_TOOL" check-live --product-sha "$PRODUCT_SHA" --harness-sha "$HARNESS_SHA"; then
  echo "SYNC_CURRENT product=$PRODUCT_SHA harness=$HARNESS_SHA"
  VERIFIED=1
  exit 0
fi

echo "SYNC_STAGE_BEGIN path=$STAGE"
mkdir -m 0700 "$STAGE"
python3 "$INDEX_TOOL" seed --stage-root "$STAGE"
for repo in product harness; do
  state=$STAGE/.seed-state-$repo
  mv "$STAGE/$repo/.repowise" "$state"
  rmdir "$STAGE/$repo"
  git clone --quiet --no-hardlinks --no-checkout "$MIRRORS/$repo.git" "$STAGE/$repo"
  expected=$PRODUCT_SHA
  [[ $repo == harness ]] && expected=$HARNESS_SHA
  git -c "safe.directory=$STAGE/$repo" -C "$STAGE/$repo" checkout --quiet --detach "$expected"
  [[ $(git -c "safe.directory=$STAGE/$repo" -C "$STAGE/$repo" rev-parse HEAD) == "$expected" ]] || fail "stage-checkout-mismatch repo=$repo"
  mkdir -p "$STAGE/$repo/.repowise"
  cp -an "$state/." "$STAGE/$repo/.repowise/"
  case "$state" in "$STAGE"/.seed-state-*) rm -rf -- "$state" ;; *) fail "unsafe-stage-state-path" ;; esac
done
chown -R 999:999 "$STAGE"
IMAGE_PATH=$(docker image inspect --format '{{json .Config.Env}}' "$INDEX_IMAGE" | python3 -c 'import json,sys; env=json.load(sys.stdin); print(next((x.split("=",1)[1] for x in env if x.startswith("PATH=")), "/usr/local/bin:/usr/bin:/bin"))')
# Incremental native update is safe only when both staged seeds have already
# passed the full baseline upgrade. A missing/partial seed fails closed.
for repo in product harness; do
  python3 "$SEED_GATE" "$STAGE/$repo/.repowise/state.json" >/dev/null || fail "stage-seed-not-full repo=$repo"
done
run_indexer repowise update --workspace --no-cost-tracking --no-agents --index-only --progress json
# Second pass refreshes structural pages the first pass only decayed (product scripts/*.mjs).
run_indexer repowise update --workspace --no-cost-tracking --no-agents --index-only --progress json
python3 "$INDEX_TOOL" shard --stage-root "$STAGE"
python3 "$INDEX_TOOL" validate --root "$STAGE"
fetch_main
[[ $PRODUCT_SHA == $INITIAL_PRODUCT_SHA && $HARNESS_SHA == $INITIAL_HARNESS_SHA ]] || fail "main-moved-during-stage"
check_live_worktrees

export REPOWISE_API_KEY="$(docker inspect "$MCP" --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^REPOWISE_API_KEY=//p')"
export REPOWISE_EMBEDDER="$(docker inspect "$MCP" --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^REPOWISE_EMBEDDER=//p')"
[[ -n $REPOWISE_API_KEY ]] || fail "live-mcp-api-key-missing"
if docker inspect "$TEST_MCP" >/dev/null 2>&1; then fail "test-container-name-collision"; fi
docker run -d --name "$TEST_MCP" --restart=no --network none --memory=1g --cpus=1 \
  --mount "type=bind,source=$STAGE,target=/workspace,readonly" \
  --mount "type=bind,source=$MCP_SMOKE,target=/tmp/mcp-stage-smoke.py,readonly" \
  --env REPOWISE_API_KEY --env REPOWISE_EMBEDDER --env REPOWISE_TELEMETRY_DISABLED=1 --env DO_NOT_TRACK=1 \
  --entrypoint repowise "$INDEX_IMAGE" mcp /workspace --transport streamable-http \
  --host 0.0.0.0 --port 7338 --tools get_answer,get_context,get_symbol,search_codebase,get_risk,get_change_risk,get_why,get_overview,get_health,get_dead_code,list_repos,get_dependency_path,get_execution_flows,get_blast_radius,get_architecture,get_conformance >/dev/null
TEST_CREATED=1
ready=0
for _ in $(seq 1 30); do
  if docker exec "$TEST_MCP" python3 -c 'import socket; s=socket.create_connection(("127.0.0.1",7338),timeout=1); s.close()' >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
[[ $ready == 1 ]] || fail "stage-mcp-did-not-listen"
docker exec "$TEST_MCP" python3 /tmp/mcp-stage-smoke.py

docker rm -f "$TEST_MCP" >/dev/null
TEST_CREATED=0
if [[ $STAGE_ONLY == 1 ]]; then
  echo "SYNC_STAGE_OK path=$STAGE product=$PRODUCT_SHA harness=$HARNESS_SHA"
  VERIFIED=1
  exit 0
fi

mapfile -t CONSUMERS < <(docker ps --filter "volume=$VOLUME" --format '{{.Names}}' | sort)
((${#CONSUMERS[@]} >= 2)) || fail "live-workspace-consumers-not-found"
has_api=0
has_mcp=0
for name in "${CONSUMERS[@]}"; do
  [[ $name == oea9obpkhzbgkmipxwqmz2hj-* ]] && has_api=1
  [[ $name == repowise-mcp-* ]] && has_mcp=1
done
[[ $has_api == 1 && $has_mcp == 1 ]] || fail "required-repowise-consumers-not-found"
# An additional authenticated deployment-publisher sidecar binds the Product
# directory directly, not the named workspace volume. The live-file guard
# intentionally rejects promotion while it is running. Admit its exact scoped
# container to the SAME stop / validate / rollback / restart transaction,
# never by bypassing the live-file guard or ignoring the sidecar's mount.
PUBLISHER=repowise-deployment-publisher-product
if [[ $(docker inspect --format '{{.State.Running}}' "$PUBLISHER" 2>/dev/null || true) == true ]]; then
  docker inspect "$PUBLISHER" | python3 -c '
import json, pathlib, sys
containers=json.load(sys.stdin)
if len(containers)!=1: raise SystemExit("publisher_container_count_mismatch")
c=containers[0]
h=c["HostConfig"]
if c["Config"]["User"]!="999:999" or not h["ReadonlyRootfs"] or h["NetworkMode"]!="host":
    raise SystemExit("publisher_isolation_changed")
live=pathlib.Path("/var/lib/docker/volumes/oea9obpkhzbgkmipxwqmz2hj-repowise-workspace/_data/product").resolve()
episodes=live/".repowise"/"episodes"
mounts=c["Mounts"]
if not any(pathlib.Path(m["Source"]).resolve()==live and not m["RW"] for m in mounts):
    raise SystemExit("publisher_scoped_readonly_product_mount_missing")
if not any(pathlib.Path(m["Source"]).resolve()==episodes and m["RW"] for m in mounts):
    raise SystemExit("publisher_scoped_episodes_mount_missing")
if any(m["RW"] and pathlib.Path(m["Source"]).resolve()!=episodes for m in mounts):
    raise SystemExit("publisher_unexpected_writable_mount")
' || fail "publisher_mount_or_identity_changed"
  CONSUMERS+=("$PUBLISHER")
  echo "SYNC_SCOPED_PUBLISHER_INCLUDED name=$PUBLISHER"
fi
# Coolify staging publisher also bind-mounts the Product subtree directly.
# Discover it by stable, verified Coolify labels (not ephemeral container name).
# Guard remains authoritative: unknown mounts still abort before any file swap.
# Scan running containers, not a mutable single-label filter: a changed Coolify
# label must never silently exclude a publisher that still mounts Product.
# Capture errors explicitly; a process substitution would hide docker failures.
RUNNING_IDS=$(docker ps --quiet) || fail "coolify-docker-list-failed"
[[ -n $RUNNING_IDS ]] || fail "coolify-no-running-containers"
# Project only the identity/isolation/mount fields required for admission.
# Never copy unrelated containers' Config.Env into the sync process.
INSPECT_FORMAT='{"Name":{{json .Name}},"Config":{"User":{{json .Config.User}},"Labels":{"coolify.managed":{{json (index .Config.Labels "coolify.managed")}},"coolify.projectName":{{json (index .Config.Labels "coolify.projectName")}},"coolify.resourceName":{{json (index .Config.Labels "coolify.resourceName")}},"coolify.applicationUuid":{{json (index .Config.Labels "coolify.applicationUuid")}},"com.docker.compose.project":{{json (index .Config.Labels "com.docker.compose.project")}}}},"HostConfig":{"ReadonlyRootfs":{{json .HostConfig.ReadonlyRootfs}},"NetworkMode":{{json .HostConfig.NetworkMode}}},"Mounts":[{{range $i,$m:=.Mounts}}{{if $i}},{{end}}{"Source":{{json $m.Source}},"Destination":{{json $m.Destination}},"RW":{{json $m.RW}}}{{end}}]}'
ALL_RUNNING_INSPECT=$(docker inspect --format "$INSPECT_FORMAT" $RUNNING_IDS) || fail "coolify-docker-inspect-failed"
COOLIFY_PUBLISHER=$(python3 -c '
import json,pathlib,sys
try: containers=[json.loads(line) for line in sys.stdin if line.strip()]
except (ValueError,TypeError): raise SystemExit("publisher_discovery_invalid_json")
if not isinstance(containers,list): raise SystemExit("publisher_discovery_invalid_shape")
live=pathlib.Path("/var/lib/docker/volumes/oea9obpkhzbgkmipxwqmz2hj-repowise-workspace/_data/product").resolve()
episodes=live/".repowise"/"episodes"
app_uuid="gl8bvfjtw2af8hkox4mguzzr"
matches=[]
for c in containers:
    name=str(c.get("Name") or "").lstrip("/")
    labels=(c.get("Config") or {}).get("Labels") or {}
    if not isinstance(labels,dict): raise SystemExit("publisher_discovery_invalid_labels")
    sources=set()
    for m in c.get("Mounts") or []:
        source=m.get("Source")
        if source: sources.add(pathlib.Path(source).resolve())
    plausible=(labels.get("coolify.applicationUuid")==app_uuid
              or labels.get("com.docker.compose.project")==app_uuid
              or labels.get("coolify.resourceName")=="repowise-deployment-publisher-staging"
              or (live in sources or episodes in sources)
                 and name!="repowise-deployment-publisher-product")
    if plausible: matches.append(name)
if len(matches)!=1: raise SystemExit("publisher_discovery_expected_exactly_one_got_"+str(len(matches)))
if not matches[0]: raise SystemExit("publisher_discovery_empty_name")
print(matches[0])
' <<< "$ALL_RUNNING_INSPECT") || fail "coolify-publisher-discovery-failed"
unset ALL_RUNNING_INSPECT
COOLIFY_PUBLISHERS=("$COOLIFY_PUBLISHER")
for coolify_publisher in "${COOLIFY_PUBLISHERS[@]}"; do
  docker inspect --format "$INSPECT_FORMAT" "$coolify_publisher" | python3 -c '
import json,pathlib,sys
cs=[json.loads(line) for line in sys.stdin if line.strip()]
if len(cs)!=1: raise SystemExit("publisher_container_count_mismatch")
c=cs[0]; cfg=c["Config"]; host=c["HostConfig"]; labels=cfg.get("Labels") or {}
want={"coolify.managed":"true","coolify.projectName":"repowise-knowledge",
      "coolify.resourceName":"repowise-deployment-publisher-staging",
      "coolify.applicationUuid":"gl8bvfjtw2af8hkox4mguzzr"}
if any(labels.get(k)!=v for k,v in want.items()):
    raise SystemExit("publisher_identity_changed")
if cfg.get("User")!="999:999" or not host.get("ReadonlyRootfs") or host.get("NetworkMode")!="host":
    raise SystemExit("publisher_isolation_changed")
live=pathlib.Path("/var/lib/docker/volumes/oea9obpkhzbgkmipxwqmz2hj-repowise-workspace/_data/product").resolve()
episodes=live/".repowise"/"episodes"
expected={
  "/workspace/product":(live,False),
  "/workspace/product/.repowise/episodes":(episodes,True),
  "/run/lock/repowise-github-sync.lock":(pathlib.Path("/run/lock/repowise-github-sync.lock").resolve(),False),
  "/run/secrets/repowise-token":(pathlib.Path("/etc/repowise-publisher/product.token").resolve(),False),
}
mounts=c["Mounts"]
if len(mounts)!=len(expected): raise SystemExit("publisher_unexpected_mount_count")
seen=set()
for m in mounts:
    dest=m["Destination"]
    if dest not in expected or dest in seen: raise SystemExit("publisher_unexpected_mount")
    seen.add(dest)
    source,rw=expected[dest]
    if pathlib.Path(m["Source"]).resolve()!=source or bool(m["RW"])!=rw:
        raise SystemExit("publisher_mount_or_rw_mismatch")
if seen!=set(expected): raise SystemExit("publisher_mount_missing")
' || fail "coolify-publisher-mount-or-identity-changed"
  CONSUMERS+=("$coolify_publisher")
  echo "SYNC_COOLIFY_PUBLISHER_INCLUDED name=$coolify_publisher"
done
prepare_live_sources
check_live_worktrees
stop_consumers
promote_args=(python3 "$INDEX_TOOL" promote --stage-root "$STAGE" --backup-root "$BACKUP")
for name in "${CONSUMERS[@]}"; do promote_args+=(--require-stopped "$name"); done
"${promote_args[@]}"
PROMOTED=1
advance_live_sources
start_consumers

healthy=0
for _ in $(seq 1 60); do
  state=$(docker inspect --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$MCP" 2>/dev/null || true)
  if [[ $state == running\|healthy ]]; then healthy=1; break; fi
  sleep 2
done
[[ $healthy == 1 ]] || fail "production-mcp-not-healthy"
python3 "$INDEX_TOOL" check-live --product-sha "$PRODUCT_SHA" --harness-sha "$HARNESS_SHA"
docker exec "$MCP" repowise status --workspace --format json 2>/dev/null | PRODUCT_SHA="$PRODUCT_SHA" HARNESS_SHA="$HARNESS_SHA" python3 -c 'import json,os,sys; d=json.load(sys.stdin); r={x["alias"]:x for x in d["repos"]}; expected={"product":os.environ["PRODUCT_SHA"],"harness":os.environ["HARNESS_SHA"]}; assert set(r)==set(expected); assert all(x.get("indexed") and not x.get("stale") and x.get("commits_behind")==0 and x.get("head")==expected[a] for a,x in r.items()); print("LIVE_STATUS_OK")'
docker exec "$MCP" python3 - < "$MCP_SMOKE"

# Rebuild vectors with the real embedder: the staged indexer runs without
# network and would otherwise leave mock vectors in the promoted index.
for repo in harness product; do
  timeout 300 docker exec "$MCP" sh -lc "cd /workspace/$repo && repowise reindex --embedder openai" >/dev/null 2>&1 \
    || echo "SYNC_EMBED_FAILED repo=$repo" >&2
done

VERIFIED=1
PROMOTED=0
unset REPOWISE_API_KEY REPOWISE_EMBEDDER
echo "SYNC_SUCCESS product=$PRODUCT_SHA harness=$HARNESS_SHA stage=$STAGE backup=$BACKUP"
