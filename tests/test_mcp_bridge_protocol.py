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


# -- AGENCY-BASE-01 (#603, AX-11): no-model baseline reproducers ---------------
#
# Evidence class: controlled local integration without a model.  A scripted
# stand-in replaces only the CLI and the public network; the MCP bridge
# process, JSON-RPC loop, AgentOSMcpTools facade and Capabilities run for real.
# ``test_finding_*`` tests are ``expectedFailure`` baselines of known defects
# owned by later AGENCY children; they are not repaired here, and an unexpected
# pass fails the suite so the owning change must remove the marker.

def _doctor():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "agentos_doctor", Path(__file__).parents[1] / "scripts" / "agentos_doctor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExposedToolWireBoundary(unittest.TestCase):
    """The tool list a CLI actually receives, from the command AgentOS writes for it.

    Unit tests of ``AgentOSMcpTools.definitions`` pass, and ``mcp_types.Tool``
    accepts a Python-style ``input_schema`` because it populates by field name.
    Only the wire -- the exact bridge command from the per-turn MCP config,
    answering ``tools/list`` over stdio -- shows what an MCP client reading
    ``inputSchema`` sees.
    """

    def setUp(self):
        from personal_agent.bounded_execution import BoundedExecutionAdapter
        from personal_agent.providers import ModelAdapter
        from personal_agent.quickstart_service import AgentService
        from personal_agent.subscription_engines import SubscriptionEngines

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / "state")
        captured = {}

        class Done:
            returncode = 0
            stdout = json.dumps({"item": {"type": "agent_message", "text": "engine answer"}})

        adapter = None

        def runner(argv, **kwargs):
            config = json.loads((Path(kwargs["cwd"]) / "agentos-mcp.json").read_text())
            captured["server"] = config["mcpServers"]["agentos"]
            captured["env"] = adapter.environment("codex", "/runtime/codex", Path(kwargs["cwd"]))
            return Done()

        profile = Path(tmp.name) / "codex-home"
        profile.mkdir()
        adapter = BoundedExecutionAdapter(finder=lambda name: "/runtime/" + name, runner=runner,
                                          runtime_root=Path(tmp.name) / "turns", codex_home=profile)
        service = AgentService(self.store, adapter=ModelAdapter(lambda *a: {"choices": [{"message": {"content": "x"}}]}),
                               subscription_engines=SubscriptionEngines(finder=lambda _: "/runtime/codex", clock=lambda: 1),
                               execution_adapter=adapter)
        service.connect_subscription_engine({"engine": "codex", "officially_authenticated": True})
        self.store.enqueue("hello there", "k1")
        self.assertTrue(service.run_one())
        self.server, self.env = captured["server"], captured["env"]

    def _wire(self, *requests):
        """Run the exact configured bridge command; it exits at end of input."""
        env = {**self.env, **self.server.get("env", {})}
        env["HOME"] = self.env["HOME"] if Path(self.env["HOME"]).exists() else tempfile.gettempdir()
        completed = subprocess.run(
            [self.server["command"], *self.server["args"]],
            input="".join(json.dumps(request) + "\n" for request in requests),
            capture_output=True, text=True, timeout=30, env=env)
        return {reply.get("id"): reply for reply in map(json.loads, completed.stdout.splitlines()) if reply}

    def _listed(self):
        return self._wire({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                          {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})[2]["result"]["tools"]

    def test_listed_local_tools_are_invocable_through_the_real_bridge(self):
        """Positive control: exposure and host invocation agree for local tools."""
        names = [tool["name"] for tool in self._listed()]
        self.assertEqual(names, ["list_notes", "save_note", "web_search"])
        replies = self._wire(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "save_note", "arguments": {"content": "wire note"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_notes", "arguments": {}}})
        self.assertIn("result", replies[2])
        listed = json.loads(replies[3]["result"]["content"][0]["text"])
        self.assertIn("wire note", [note["content"] for note in listed["notes"]])

    def test_an_unlisted_native_tool_is_refused_by_the_real_bridge(self):
        """Denied control: invocation never exceeds exposure."""
        replies = self._wire({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                             {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                              "params": {"name": "read_file", "arguments": {"root_id": "r", "path": "a.md"}}})
        self.assertIn("error", replies[2])

    @unittest.expectedFailure
    def test_finding_listed_tools_are_not_valid_mcp_wire_tools(self):
        """Owner #604 (AX-02).  Defect layer: ``bounded_execution.MCP_TOOLS``.

        ``list_notes`` has no ``inputSchema`` and the others send
        ``input_schema``; MCP requires ``inputSchema`` (an object schema).
        How Codex/Claude Code react to this list is not observed here.
        """
        self.assertEqual(_doctor().mcp_wire_problems(self._listed()), [])


class BridgeErrorMapping(unittest.TestCase):
    """What the CLI receives when a bridged AgentOS call does not succeed."""

    def _serve(self, requests, provenance=(), network=None):
        import contextlib
        import io
        from unittest import mock
        from personal_agent.local_tools import LocalTools

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / "state")
        calls = []

        def execute(_self, plan):
            calls.append(plan)
            if network:
                return network(plan)
            return {"query": plan.get("query"), "results": [{"title": "t", "url": "https://example.org/", "snippet": "s"}],
                    "sources": ["https://example.org/"]}

        out = io.StringIO()
        with mock.patch.object(LocalTools, "execute", execute), \
             mock.patch.object(sys, "stdin", io.StringIO("".join(json.dumps(r) + "\n" for r in requests))), \
             contextlib.redirect_stdout(out):
            try:
                mcp_bridge.serve(str(store.root), "err-job", provenance)
            except Exception as exc:  # recorded, asserted by the finding below
                calls.append({"bridge_crashed": type(exc).__name__})
        replies = {reply["id"]: reply for reply in map(json.loads, out.getvalue().splitlines())}
        return replies, calls

    @staticmethod
    def _call(ident, name, arguments):
        return {"jsonrpc": "2.0", "id": ident, "method": "tools/call", "params": {"name": name, "arguments": arguments}}

    def test_a_clean_public_search_returns_its_result(self):
        """Allowed control for the error cases below."""
        replies, calls = self._serve([self._call(1, "web_search", {"query": "today news"})])
        self.assertIn("result", replies[1])
        self.assertEqual([plan["tool"] for plan in calls], ["web_search"])

    def test_a_tainted_search_is_refused_before_the_network(self):
        """Denied control: the refusal itself is correct; only its mapping is the finding."""
        replies, calls = self._serve([self._call(1, "web_search", {"query": "today news"})],
                                     provenance=["personal-space"])
        self.assertIn("error", replies[1])
        self.assertEqual(calls, [])

    def _failure_signatures(self):
        replies, _ = self._serve([
            self._call(1, "web_search", {"query": "today news"}),       # policy denied (taint below)
            self._call(2, "web_search", {"q": "today news"}),           # invalid arguments
            self._call(3, "weather", {"city": "Daejeon"}),              # tool not exposed
            {"jsonrpc": "2.0", "id": 4, "method": "resources/list"},     # unsupported method
        ], provenance=["conversation-history"])
        return {ident: json.dumps(reply.get("error") or reply.get("result"), sort_keys=True) for ident, reply in replies.items()}

    @unittest.expectedFailure
    def test_finding_distinct_failures_collapse_into_one_protocol_error(self):
        """Owner #607 (AX-06).  Defect layer: ``mcp_bridge.serve`` except-branch.

        Policy denial, invalid arguments, an unexposed tool and an unsupported
        method all become ``-32602 'AgentOS MCP request rejected.'``, so the
        CLI cannot tell a recoverable argument error from a denial.
        """
        signatures = self._failure_signatures()
        self.assertEqual(sorted(signatures), [1, 2, 3, 4])
        self.assertEqual(len(set(signatures.values())), 4, signatures)

    @unittest.expectedFailure
    def test_finding_a_transient_network_failure_ends_the_bridge(self):
        """Owner #607 (AX-06).  Defect layer: ``mcp_bridge.serve`` catches only
        ValueError/ExecutionError/TypeError, so a ProviderError from the public
        read escapes the loop: the call gets no reply and later requests none.
        """
        from personal_agent.providers import ProviderError

        def offline(_plan):
            raise ProviderError("offline")

        replies, calls = self._serve([self._call(1, "web_search", {"query": "today news"}),
                                      {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}], network=offline)
        self.assertEqual(calls[0]["tool"], "web_search", "the read was attempted")
        self.assertIn(1, replies, "the failed call is answered")
        self.assertIn(2, replies, "the bridge keeps serving")


if __name__ == "__main__":
    unittest.main()
