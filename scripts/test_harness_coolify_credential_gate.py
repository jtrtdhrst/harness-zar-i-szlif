import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

path = Path(__file__).with_name("harness_coolify_credential_gate.py")
spec = importlib.util.spec_from_file_location("gate", path)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
OK = {k:{"legacy_ref":False,"dedicated_ref":True} for k in g.CONTROLLERS}
CANDIDATES = {k:200 for k in g.CONTROLLERS}

class RotationGateTests(unittest.TestCase):
  def test_revoked_requires_every_condition(self):
    self.assertEqual(g.decide("revoked",OK,401,CANDIDATES,False,True), [])
  def test_legacy_still_live(self):
    self.assertIn("old_token_not_revoked",g.decide("revoked",OK,200,CANDIDATES,False,True))
  def test_no_self_approval_before_switch(self):
    x = {k:dict(v) for k,v in OK.items()}; x["harness"]["legacy_ref"]=True
    self.assertIn("controllers_still_reference_old_token",g.decide("revoked",x,401,CANDIDATES,False,True))
  def test_all_controllers_must_switch(self):
    x = {k:dict(v) for k,v in OK.items()}; x["product_image"]["dedicated_ref"]=False
    self.assertIn("controllers_not_switched",g.decide("revoked",x,401,CANDIDATES,False,True))
  def test_missing_token_denied(self):
    x=dict(CANDIDATES);del x["product_mcp_host"]
    self.assertIn("product_mcp_host_missing_candidate",g.decide("revoked",OK,401,x,False,True))
  def test_wrong_scope_denied(self):
    x=dict(CANDIDATES);x["harness"]=403
    self.assertIn("harness_candidate_not_authorized",g.decide("revoked",OK,401,x,False,True))
  def test_duplicate_token_denied(self):
    self.assertIn("credential_reuse_detected",g.decide("revoked",OK,401,CANDIDATES,True,True))
  def test_image_changed_denied(self):
    self.assertIn("image_changed",g.decide("revoked",OK,401,CANDIDATES,False,False))
  def test_baseline_never_success(self):
    self.assertIn("rotation_incomplete",g.decide("inspect",OK,401,{},False,True))
  def test_staged_is_not_revoked(self):
    self.assertEqual(g.decide("staged",OK,200,CANDIDATES,False,True),[])
  def test_symlink_denied(self):
    with tempfile.TemporaryDirectory() as tmp:
      base=Path(tmp)/"secret";base.write_text("test-value");os.chmod(base,0o600)
      link=Path(tmp)/"link";link.symlink_to(base)
      with self.assertRaises(g.Denied):g.read_secret(link)
  def test_mode_must_be_0600(self):
    with tempfile.TemporaryDirectory() as tmp:
      p=Path(tmp)/"secret";p.write_text("test-value");os.chmod(p,0o644)
      with self.assertRaises(g.Denied):g.read_secret(p)
  def test_comments_cannot_spoof_controller_token_switch(self):
    with tempfile.TemporaryDirectory() as tmp:
      p = Path(tmp) / "controller.py"
      candidate = Path("/root/coolify-secrets/harness_delivery_api_token")
      p.write_text('# COOLIFY_TOKEN = Path("'+str(candidate)+'")\n'
                   'COOLIFY_TOKEN = Path("'+str(g.OLD)+'")\n')
      self.assertEqual(g.source_flags(p, candidate),
                       {"legacy_ref": True, "dedicated_ref": False})
      p.write_text('from pathlib import Path\nCOOLIFY_TOKEN = Path("'+str(candidate)+'")\n')
      self.assertEqual(g.source_flags(p, candidate),
                       {"legacy_ref": False, "dedicated_ref": True})
  def test_invalid_uuid_denied_before_http(self):
    with self.assertRaises(g.Denied):g.get_status("secret","../etc/passwd")

if __name__=="__main__":
  unittest.main(verbosity=2)
