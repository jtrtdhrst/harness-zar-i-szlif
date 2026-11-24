"""No-network privacy/source integrity regression for PR39-stacked Hermes overlay."""
import ast
import importlib.util
from pathlib import Path
import tempfile
import typing
import unittest

SOURCE=Path(__file__).resolve().parents[1]/"apply_opik_telemetry_privacy.py"
spec=importlib.util.spec_from_file_location("privacy",SOURCE)
privacy=importlib.util.module_from_spec(spec)
spec.loader.exec_module(privacy)

class PrivacyOverlayTest(unittest.TestCase):
    def helpers(self):
        ns={"Path":Path,"Any":typing.Any,
            "__file__":"/test/profiles/cho/plugins/opik/hooks.py",
            "_verified_role_from_plugin_path":lambda path: "cho" if "/profiles/cho/" in path else "",
            "_configured_hindsight_mode":lambda path,role:"cloud" if role=="cho" else ""}
        exec(compile(ast.parse(privacy.HELPERS),"<privacy-only>","exec"),ns)
        return ns

    def test_fixed_tool_category_no_dynamic_secrets(self):
        f=self.helpers()["_safe_tool_label"]
        self.assertEqual(f("hindsight_recall"),"hindsight_recall")
        self.assertEqual(f("hindsight_retain"),"hindsight_retain")
        self.assertEqual(f("mcp__private__LONG_FAKE_TOKEN_123"),"mcp_tool")
        self.assertEqual(f("LONG_FAKE_TOKEN_123"),"other_tool")
        self.assertEqual(f(None),"unknown_tool")

    def test_only_typed_outcome_not_untrusted_error_text(self):
        f=self.helpers()["_reported_tool_outcome"]
        self.assertEqual(f({"isError":True,"output":"FAKE_PRIVATE_MEMORY"}),"reported_error")
        self.assertEqual(f({"isError":False,"result":"FAKE_PRIVATE_MEMORY"}),"reported_no_error")
        self.assertEqual(f({"success":False,"error":"FAKE_PRIVATE_MEMORY"}),"reported_error")
        self.assertEqual(f("Error: FAKE_PRIVATE_MEMORY"),"unverified")
        self.assertEqual(f({"status":"success","result":"FAKE_PRIVATE_MEMORY"}),"unverified")

    def test_profile_binding_is_configuration_only(self):
        f=self.helpers()["_configured_bank_for_tool"]
        r=f("hindsight_retain")
        self.assertEqual(r["configured_memory_bank"],"hermes-cho")
        self.assertIn("not_call_proof",r["memory_bank_provenance"])
        self.assertEqual(f("unrelated_tool"),{})

    def test_source_pin_drifts_fail_before_writes(self):
        with tempfile.TemporaryDirectory() as d:
            lc=Path(d)/"lifecycle.py";hk=Path(d)/"hooks.py"
            lc.write_text("bad source")
            hk.write_text("bad source")
            with self.assertRaisesRegex(ValueError,"SHA mismatch"):
                privacy.prepare(lc,hk)
            self.assertEqual(lc.read_text(),"bad source")
            self.assertEqual(hk.read_text(),"bad source")

    def test_transform_anchors_do_not_silently_reapply(self):
        with self.assertRaisesRegex(ValueError,"anchor drift"):
            privacy.transform_hooks("import datetime\n")
        with self.assertRaisesRegex(ValueError,"anchor drift"):
            privacy.transform_segmented_lifecycle("def harmless(): pass")

    def test_helpers_never_serialize_private_data(self):
        ns=self.helpers()
        sample={"isError":True,"api_key":"SYNTHETIC_CREDENTIAL_MARKER",
                "result":{"text":"SYNTHETIC_MEMORY_MARKER"}}
        output={"label":ns["_safe_tool_label"]("hindsight_recall"),
                "outcome":ns["_reported_tool_outcome"](sample),
                **ns["_configured_bank_for_tool"]("hindsight_recall")}
        self.assertNotIn("SYNTHETIC",str(output))
        self.assertEqual(output["outcome"],"reported_error")

if __name__=="__main__":unittest.main()
