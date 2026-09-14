"""Offline v0.1 schema/fixture conformance, never live runtime authorization."""

import importlib.util
from copy import deepcopy
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
        self.assertGreaterEqual(counts["negative"], 35)

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

    def test_standalone_runtime_provenance_is_representable_without_inventing_a_package(self):
        validators = verifier.load_validators()
        _, documents = verifier.load_fixture_bundle()
        artifact = deepcopy(documents["positive/artifact-native.json"])
        runtime_ref = documents["positive/runtime.json"]
        runtime_ref = {
            "kind": "Runtime", "id": runtime_ref["id"], "schemaVersion": "0.1",
            "revision": runtime_ref["revision"], "releaseVersion": runtime_ref["releaseVersion"],
            "digest": runtime_ref["releaseDigest"],
        }
        artifact["runtimeRef"] = runtime_ref
        artifact["provenance"] = {
            "producer": "runtime", "evidenceClass": "deterministicFixture", "sourceRefs": [],
            "workRef": artifact["workRef"], "packageRef": None, "runtimeRef": runtime_ref,
        }
        self.assertEqual(verifier.schema_errors(artifact, validators["artifact.schema.json"]), [])

    def test_valid_memory_candidate_acceptance_is_sealed_bound_and_reciprocal(self):
        validators = verifier.load_validators()
        catalog, documents = verifier.load_fixture_bundle()
        changed = deepcopy(documents)
        candidate = changed["positive/memory-candidate.json"]
        memory = changed["positive/memory.json"]
        decision = changed["positive/evidence-memory.json"]
        candidate_ref = {"kind": "MemoryCandidate", "id": candidate["id"], "schemaVersion": "0.1", "revision": candidate["revision"]}
        memory_ref = {"kind": "Memory", "id": memory["id"], "schemaVersion": "0.1", "revision": memory["revision"]}
        decision_ref = {"kind": "Evidence", "id": decision["id"], "schemaVersion": "0.1", "revision": decision["revision"]}
        candidate.update(state="accepted", decisionRef=decision_ref, resultingMemoryRef=memory_ref)
        memory["acceptedCandidateRef"] = candidate_ref
        decision["relatedRefs"] = [candidate_ref, memory_ref]
        self.assertEqual(verifier.schema_errors(candidate, validators["memory-candidate.schema.json"]), [])
        self.assertEqual(verifier.schema_errors(memory, validators["memory.schema.json"]), [])
        self.assertEqual(verifier.semantic_errors(list(changed.values()), catalog), [])

    def test_latest_context_revision_revokes_a_historical_snapshot(self):
        catalog, documents = verifier.load_fixture_bundle()
        for state, expires_at in (("deleted", "2026-09-14T02:00:00Z"), ("available", "2026-09-14T00:04:00Z")):
            with self.subTest(state=state, expires_at=expires_at):
                revoked = deepcopy(documents["positive/context.json"])
                revoked.update(revision=2, createdAt="2026-09-14T00:01:00Z", state=state, expiresAt=expires_at)
                errors = verifier.semantic_errors([*documents.values(), revoked], catalog)
                self.assertTrue(any(error.startswith("CONTEXT-002 ") for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
