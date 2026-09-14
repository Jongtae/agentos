"""Offline v0.1 schema/fixture conformance, never live runtime authorization."""

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_agentpackage_v01", ROOT / "scripts" / "verify_agentpackage_v01.py")
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


class AgentPackageV01Tests(unittest.TestCase):
    def test_all_schemas_and_fixtures(self):
        failures, counts = verifier.verify()
        self.assertEqual(failures, [])
        self.assertEqual(counts["schemas"], 14)
        self.assertGreaterEqual(counts["positive"], 13)

    def test_json_parser_rejects_duplicate_keys_and_non_json_numbers(self):
        for value in ('{"issuer":"package","issuer":"agentos"}', '{"value":NaN}', '{"value":Infinity}', '{"value":-Infinity}'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                verifier.loads_strict(value)

    def test_issuer_const_is_structural_not_authenticated_authority(self):
        # A malicious author can spell issuer='agentos'. Validation accepts this
        # declaration; a future kernel must separately authenticate its issuer.
        validators = verifier.load_validators()
        _, documents = verifier.load_fixture_bundle()
        grant = documents["positive/grant.json"]
        self.assertEqual(grant["issuer"], "agentos")
        self.assertEqual(verifier.schema_errors(grant, validators["grant.schema.json"]), [])

    def test_registry_rejects_remote_retrieval(self):
        from referencing.exceptions import NoSuchResource
        with self.assertRaises(NoSuchResource):
            verifier._deny_remote("https://invalid.example/remote.schema.json")


if __name__ == "__main__":
    unittest.main()
