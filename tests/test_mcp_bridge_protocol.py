"""Protocol-version negotiation for both stdio MCP bridges.

REUSE-R2 (#426): the advertised revision comes from the ``mcp_types`` registry,
not a hand-maintained literal, so SDK protocol drift is visible instead of silent.
"""

import inspect
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mcp_types.version import (
    HANDSHAKE_PROTOCOL_VERSIONS,
    LATEST_HANDSHAKE_VERSION,
    LATEST_PROTOCOL_VERSION,
    MODERN_PROTOCOL_VERSIONS,
)

from personal_agent import isolated_engine_mcp_bridge, mcp_bridge
from personal_agent.quickstart_store import QuickStore


BRIDGES = (mcp_bridge, isolated_engine_mcp_bridge)


class ProtocolVersionRegistryTests(unittest.TestCase):
    def test_registry_handshake_set_is_the_reviewed_one(self):
        """Pin the registry the bridges were reviewed against.

        LATEST_HANDSHAKE_VERSION is HANDSHAKE_PROTOCOL_VERSIONS[-1], and the
        registry is additive, so a minor SDK release that appends a
        handshake-era revision silently changes what both bridges advertise
        at the isolation boundary - to a revision nobody implemented or
        reviewed.

        Every other assertion in this file is written in terms of
        LATEST_HANDSHAKE_VERSION or HANDSHAKE_PROTOCOL_VERSIONS, so they move
        with the SDK and cannot detect that. Simulating a 2.3.0 that appends
        one revision leaves this whole suite green while both bridges
        advertise it.

        Retiring the hardcoded literal made backward drift visible. Without
        this pin it made forward drift *less* visible than before, because
        previously a human had to edit a literal to change the answer. There
        is no lockfile, so a rebuild of Dockerfile.engine is enough.

        A failure here is not a bug: it means the SDK added a revision and a
        human must decide whether these bridges implement it.
        """
        from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS

        self.assertEqual(
            HANDSHAKE_PROTOCOL_VERSIONS,
            ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"),
        )

    def test_no_bridge_hardcodes_a_protocol_revision(self):
        """The literal both bridges used to carry must not come back."""
        for module in BRIDGES:
            source = inspect.getsource(module)
            for revision in HANDSHAKE_PROTOCOL_VERSIONS + MODERN_PROTOCOL_VERSIONS:
                with self.subTest(module=module.__name__, revision=revision):
                    self.assertNotIn(revision, source)

    def test_known_offer_is_echoed_back(self):
        for module in BRIDGES:
            for offered in HANDSHAKE_PROTOCOL_VERSIONS:
                with self.subTest(module=module.__name__, offered=offered):
                    self.assertEqual(module.negotiated_protocol_version(offered), offered)

    def test_absent_or_unknown_offer_counter_offers_latest_handshake(self):
        for module in BRIDGES:
            for offered in (None, "", "zzz", "9999-01-01", 20241105, 2.0, True, {"a": 1}, ["2024-11-05"]):
                with self.subTest(module=module.__name__, offered=offered):
                    self.assertEqual(
                        module.negotiated_protocol_version(offered), LATEST_HANDSHAKE_VERSION
                    )

    def test_stateless_modern_revision_is_not_echoed(self):
        """These bridges implement the initialize handshake, not the 2026 per-request envelope."""
        self.assertNotIn(LATEST_PROTOCOL_VERSION, HANDSHAKE_PROTOCOL_VERSIONS)
        for module in BRIDGES:
            for revision in MODERN_PROTOCOL_VERSIONS:
                with self.subTest(module=module.__name__, revision=revision):
                    negotiated = module.negotiated_protocol_version(revision)
                    self.assertEqual(negotiated, LATEST_HANDSHAKE_VERSION)
                    self.assertNotEqual(negotiated, revision)

    def test_negotiated_result_is_always_a_registry_member(self):
        """An engine-supplied string is never reflected verbatim to the peer."""
        for module in BRIDGES:
            for offered in ("../../etc/passwd", "2024-11-05\n\rinjected", "x" * 500, None):
                with self.subTest(module=module.__name__, offered=offered):
                    self.assertIn(
                        module.negotiated_protocol_version(offered), HANDSHAKE_PROTOCOL_VERSIONS
                    )


class SubscriptionBridgeWireTests(unittest.TestCase):
    """End-to-end stdio check that the negotiated version reaches the wire."""

    def _initialize(self, params):
        with tempfile.TemporaryDirectory() as folder:
            store = QuickStore(Path(folder) / "data")
            request = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
            if params is not None:
                request["params"] = params
            process = subprocess.Popen(
                [sys.executable, "-m", "personal_agent.mcp_bridge", "--data", str(store.root), "--job", "proto-job"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                env=os.environ.copy(),
            )
            try:
                process.stdin.write(json.dumps(request) + "\n")
                process.stdin.flush()
                reply = json.loads(process.stdout.readline())
            finally:
                process.terminate()
                process.wait(timeout=10)
                process.stdin.close()
                process.stdout.close()
        return reply

    def test_wire_initialize_echoes_a_supported_offer(self):
        reply = self._initialize({"protocolVersion": "2024-11-05"})
        self.assertEqual(reply["result"]["protocolVersion"], "2024-11-05")

    def test_wire_initialize_counter_offers_when_offer_is_unknown(self):
        reply = self._initialize({"protocolVersion": "1999-01-01"})
        self.assertEqual(reply["result"]["protocolVersion"], LATEST_HANDSHAKE_VERSION)

    def test_wire_initialize_without_params_still_advertises_a_version(self):
        reply = self._initialize(None)
        self.assertEqual(reply["result"]["protocolVersion"], LATEST_HANDSHAKE_VERSION)


if __name__ == "__main__":
    unittest.main()
