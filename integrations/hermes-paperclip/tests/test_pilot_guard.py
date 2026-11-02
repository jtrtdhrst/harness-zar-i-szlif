import importlib.util
import pathlib
import unittest

module_path = pathlib.Path(__file__).resolve().parents[1] / "pilot_guard.py"
spec = importlib.util.spec_from_file_location("pilot_guard", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PilotIsolationTests(unittest.TestCase):
    def inventory(self):
        pilot = {
            "id": module.PILOT_ID,
            "name": module.PILOT_NAME,
            "adapterType": "hermes_gateway",
            "status": "idle",
            "adapterConfig": {
                "apiBaseUrl": module.PILOT_URL,
                "apiKey": {"type": "secret_ref", "secretId": "pilot-only-encrypted-reference"}
            },
            "runtimeConfig": {"heartbeat": {"enabled": False, "maxConcurrentRuns": 1}},
        }
        control = {"id": "control-agent", "name": "CHO", "adapterType": "opencode_local"}
        return {"agents": [pilot, control]}

    def test_pilot_configuration_passes(self):
        self.assertEqual(module.validate_inventory(self.inventory()), [])

    def test_pilot_can_be_non_operational_without_spoofing_delivery(self):
        snapshot = self.inventory()
        snapshot["agents"][0]["status"] = "error"
        self.assertEqual(module.validate_inventory(snapshot), [])
        self.assertIn("not operational", " ".join(module.validate_inventory(snapshot, require_operational=True)))

    def test_rejects_second_gateway_agent(self):
        snapshot = self.inventory()
        snapshot["agents"][1]["adapterType"] = "hermes_gateway"
        self.assertTrue(module.validate_inventory(snapshot))

    def test_rejects_wrong_named_profile(self):
        snapshot = self.inventory()
        snapshot["agents"][0]["adapterConfig"]["apiBaseUrl"] = "https://hermes-poc.zariszlif.pl"
        self.assertIn("named", " ".join(module.validate_inventory(snapshot)))

    def test_rejects_raw_or_missing_secret(self):
        snapshot = self.inventory()
        snapshot["agents"][0]["adapterConfig"]["apiKey"] = "plaintext-do-not-save"
        self.assertIn("secret_ref", " ".join(module.validate_inventory(snapshot)))

    def test_rejects_enabled_heartbeat(self):
        snapshot = self.inventory()
        snapshot["agents"][0]["runtimeConfig"]["heartbeat"]["enabled"] = True
        self.assertIn("disabled", " ".join(module.validate_inventory(snapshot)))

    def test_rejects_concurrent_pilot_runs(self):
        snapshot = self.inventory()
        snapshot["agents"][0]["runtimeConfig"]["heartbeat"]["maxConcurrentRuns"] = 20
        self.assertIn("maxConcurrentRuns", " ".join(module.validate_inventory(snapshot)))

    def test_rejects_missing_pilot(self):
        snapshot = self.inventory()
        snapshot["agents"].pop(0)
        self.assertIn("exactly one", " ".join(module.validate_inventory(snapshot)))

    def test_rejects_missing_inventory(self):
        self.assertTrue(module.validate_inventory({"agents": []}))

    def test_rejects_duplicate_id(self):
        snapshot = self.inventory()
        snapshot["agents"].append(dict(snapshot["agents"][0]))
        self.assertIn("duplicate", " ".join(module.validate_inventory(snapshot)))


if __name__ == "__main__":
    unittest.main()
