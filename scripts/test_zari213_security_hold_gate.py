"""Fail-closed tests for persisted HOLD, independently of issue status."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
GATE=ROOT/"ops/harness/release/multica_native_release_gate.py"
spec=importlib.util.spec_from_file_location("native_hold_gate",GATE)
gate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
OWNER=gate.SECURITY_HOLD_OWNER
CTO=gate.SECURITY_HOLD_CTO
COO=gate.SECURITY_HOLD_COO
EVIDENCE_ID="11111111-1111-4111-8111-111111111111"
CTO_ID="22222222-2222-4222-8222-222222222222"
COO_ID="33333333-3333-4333-8333-333333333333"
CTO_TASK="44444444-4444-4444-8444-444444444444"
COO_TASK="55555555-5555-4555-8555-555555555555"
SHA="a"*40

class PersistedHoldTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"hold.json"
        self.record={
            "schema_version":1,"owner":OWNER,"reason":"Fail closed",
            "activated_at":"2026-11-23T16:00:00Z",
            "clearing_authority":"workspace_owner_and_independent_CTO_COO",
            "active":True,"clearance":None,
        }

    def save(self):
        self.path.write_text(json.dumps(self.record))
        self.path.chmod(0o600)

    def denied(self,reason):
        with self.assertRaisesRegex(gate.Denied,reason):
            gate.enforce_persistent_security_hold("fake-db",self.path)

    def cleared(self):
        self.record["active"]=False
        self.record["clearance"]={
            "cleared_by":OWNER,"cleared_at":"2026-11-23T16:10:00Z",
            "ctocoo_review_sha":SHA,
            "isolation_e2e_comment_id":EVIDENCE_ID,
            "cto_review_comment_id":CTO_ID,
            "coo_authorization_comment_id":COO_ID,
        }
        self.save()

    def test_active_hold_denies_with_any_task_status(self):
        self.save()
        with patch.object(gate,"read_rows") as q:
            for status in ("blocked","in_review","done"):
                with self.subTest(status=status):
                    self.denied("security_hold_active")
            q.assert_not_called()

    def test_missing_corrupted_symlink_or_untrusted_file(self):
        self.denied("security_hold_record_missing")
        self.path.write_text("not json")
        self.denied("security_hold_record_unreadable")
        self.record["schema_version"]=999
        self.save()
        self.denied("security_hold_record_invalid")
        self.record["schema_version"]=1
        self.save()
        self.path.chmod(0o666)
        self.denied("security_hold_record_unsafe_permissions")
        self.path.unlink()
        real=Path(self.tmp.name)/"actual.json"
        real.write_text(json.dumps(self.record))
        os.symlink(real,self.path)
        self.denied("security_hold_record_missing")

    def test_no_clearance_and_wrong_clearing_actor_fail(self):
        self.record["active"]=False
        self.save()
        self.denied("security_hold_clearance_missing")
        self.cleared()
        self.record["clearance"]["cleared_by"]="foreign-user"
        self.save()
        self.denied("security_hold_clearance_not_authorized")

    def test_source_cleared_live_hold_or_missing_comment_denied(self):
        self.cleared()
        with patch.object(gate,"read_rows",return_value=[{"metadata":{"security_hold":True}}]):
            self.denied("security_hold_live_not_cleared")
        with patch.object(gate,"read_rows",side_effect=[[{"metadata":{"security_hold":False}}],[]]):
            self.denied("security_hold_evidence_comment_missing")

    def test_three_role_authenticated_live_comments_and_completed_runs_required(self):
        self.cleared()
        replies={
            EVIDENCE_ID:{"author_type":"member","author_id":OWNER,
                "content":"ISOLATION_E2E_PASS HARNESS_OWN_REPO_PASS PRODUCT_OWN_REPO_PASS CROSS_REPO_DENIED ROLLBACK_PASS",
                "source_task_id":None},
            CTO_ID:{"author_type":"agent","author_id":CTO,"content":"CODE_ONLY_APPROVED "+SHA,
                "source_task_id":CTO_TASK},
            COO_ID:{"author_type":"agent","author_id":COO,"content":"RELEASE_APPROVED "+SHA,
                "source_task_id":COO_TASK},
        }
        tasks={
            CTO_TASK:{"agent_id":CTO,"issue_id":gate.SECURITY_HOLD_ISSUE,"status":"completed"},
            COO_TASK:{"agent_id":COO,"issue_id":gate.SECURITY_HOLD_ISSUE,"status":"completed"},
        }
        def read(sql, db):
            if "FROM issue " in sql: return [{"metadata":{"security_hold":False}}]
            for cid,body in replies.items():
                if "FROM comment " in sql and "id='"+cid+"'" in sql: return [body]
            for tid,body in tasks.items():
                if "FROM agent_task_queue " in sql and "id='"+tid+"'" in sql: return [body]
            return []
        with patch.object(gate,"read_rows",side_effect=read):
            self.assertTrue(gate.enforce_persistent_security_hold("fake-db",self.path))
            replies[CTO_ID]["content"]="CODE_ONLY_APPROVED "+"b"*40
            self.denied("security_hold_evidence_comment_untrusted")
            replies[CTO_ID]["content"]="CODE_ONLY_APPROVED "+SHA
            tasks[COO_TASK]["status"]="running"
            self.denied("security_hold_evidence_run_not_completed")
            tasks[COO_TASK]["status"]="completed"
            replies[EVIDENCE_ID]["author_id"]="attacker"
            self.denied("security_hold_evidence_comment_untrusted")

if __name__=="__main__":
    unittest.main()
