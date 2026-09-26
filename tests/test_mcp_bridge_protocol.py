"""Protocol-version negotiation for both stdio MCP bridges.

REUSE-R2 (#426): the advertised revision comes from the ``mcp_types`` registry,
not a hand-maintained literal, so SDK protocol drift is visible instead of silent.
"""

import contextlib
import inspect
import io
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

from lookup_judgment import ordinary_lookup_judgment
from personal_agent import isolated_engine_mcp_bridge, mcp_bridge
from personal_agent.quickstart_store import QuickStore


BRIDGES = (mcp_bridge, isolated_engine_mcp_bridge)



def _refused(reply):
    """#607 AX-06: a refusal is a protocol error or a typed MCP tool-result error."""
    return "error" in reply or bool((reply.get("result") or {}).get("isError"))


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
# pass fails the suite so the owning change must remove the marker.  #604 fixed
# and un-marked the wire-conformance finding; the #607 error-mapping findings
# below remain expected failures.

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
    answering over stdio *while its Work is running* -- shows what an MCP
    client reading ``inputSchema`` sees and what the host actually executes.
    """

    def setUp(self):
        from personal_agent.bounded_execution import BoundedExecutionAdapter
        from personal_agent.providers import ModelAdapter
        from personal_agent.quickstart_service import AgentService
        from personal_agent.subscription_engines import SubscriptionEngines

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / "state")
        self.pending, self.replies, self.turns = None, None, 0

        class Done:
            returncode = 0
            stdout = json.dumps({"item": {"type": "agent_message", "text": "engine answer"}})

        adapter = None

        def runner(argv, **kwargs):
            # The scripted CLI: it speaks to the exact configured bridge while
            # AgentOS holds this Work in `running`, as a real CLI would.
            config = json.loads((Path(kwargs["cwd"]) / "agentos-mcp.json").read_text())
            self.server = config["mcpServers"]["agentos"]
            self.env = adapter.environment("codex", "/runtime/codex", Path(kwargs["cwd"]))
            if self.pending is not None:
                self.replies = self._run_bridge(self.server["args"], self.pending)
            return Done()

        profile = Path(tmp.name) / "codex-home"
        profile.mkdir()
        adapter = BoundedExecutionAdapter(finder=lambda name: "/runtime/" + name, runner=runner,
                                          runtime_root=Path(tmp.name) / "turns", codex_home=profile)
        self.service = AgentService(self.store, adapter=ModelAdapter(lambda *a: {"choices": [{"message": {"content": "x"}}]}),
                                    subscription_engines=SubscriptionEngines(finder=lambda _: "/runtime/codex", clock=lambda: 1),
                                    execution_adapter=adapter)
        self.service.connect_subscription_engine({"engine": "codex", "officially_authenticated": True})

    def _run_bridge(self, args, requests):
        env = {**self.env, **self.server.get("env", {})}
        env["HOME"] = self.env["HOME"] if Path(self.env["HOME"]).exists() else tempfile.gettempdir()
        completed = subprocess.run(
            [self.server["command"], *args],
            input="".join(json.dumps(request) + "\n" for request in requests),
            capture_output=True, text=True, timeout=30, env=env)
        return {reply.get("id"): reply for reply in map(json.loads, completed.stdout.splitlines()) if reply}

    def _wire(self, *requests):
        """One owner turn whose scripted CLI sends ``requests`` to the real bridge."""
        self.pending = (INIT, *requests)
        self.turns += 1
        self.store.enqueue("hello there", f"wire-{self.turns}")
        self.assertTrue(self.service.run_one())
        self.pending = None
        return self.replies

    def _listed(self):
        return self._wire({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})[2]["result"]["tools"]

    def test_listed_local_tools_are_invocable_through_the_real_bridge(self):
        """Positive control: exposure and host invocation agree for local tools."""
        names = [tool["name"] for tool in self._listed()]
        self.assertEqual(names, ["bounded_public_research", "list_notes", "save_note", "weather", "web_search"])
        replies = self._wire(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "save_note", "arguments": {"content": "wire note"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_notes", "arguments": {}}})
        self.assertIn("result", replies[2])
        listed = json.loads(replies[3]["result"]["content"][0]["text"])
        self.assertIn("wire note", [note["content"] for note in listed["notes"]])

    def test_an_unlisted_native_tool_is_refused_by_the_real_bridge(self):
        """Denied control: invocation never exceeds exposure."""
        replies = self._wire({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                              "params": {"name": "read_file", "arguments": {"root_id": "r", "path": "a.md"}}})
        self.assertTrue(_refused(replies[2]))

    def test_the_bridge_refuses_calls_once_its_work_is_no_longer_running(self):
        """#604: discovery grants nothing; a finished or foreign Work cannot act.

        The same configured command, run after the Work ended, still lists its
        tools but refuses the call; a foreign Work id is refused too.  The
        allowed control is the in-Work call above.
        """
        self._listed()
        args = self.server["args"]
        list_notes = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_notes", "arguments": {}}}
        after = self._run_bridge(args, (INIT, {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, list_notes))
        self.assertIn("tools", after[3]["result"], "listing is still answered")
        self.assertTrue(_refused(after[2]), "a finished Work is refused")
        foreign = list(args)
        foreign[foreign.index("--job") + 1] = "not-a-work-of-this-store"
        self.assertTrue(_refused(self._run_bridge(foreign, (INIT, list_notes))[2]))
        with self.store.db() as db:
            failed = [json.loads(row[0]) for row in db.execute(
                "SELECT detail FROM tool_events WHERE tool='list_notes' AND status='failed'")]
        # #607: the refusal is typed (code/retry/effect) and still carries no arguments.
        self.assertTrue(failed and all(set(detail) <= {"scope", "error", "host_action", "code", "retry", "effect"}
                                       and detail["code"] == "stopped" for detail in failed),
                        "the refusal is recorded with a reason and no arguments")

    def test_finding_listed_tools_are_not_valid_mcp_wire_tools(self):
        """Fixed by #604 (was an ``expectedFailure`` baseline from #603).

        The list is now derived from ``Capabilities.definitions()``, so every
        tool carries an MCP ``inputSchema`` object and no Python-style field.
        """
        self.assertEqual(_doctor().mcp_wire_problems(self._listed()), [])

    def test_listed_tools_and_results_match_the_adopted_mcp_types_models_strictly(self):
        """The one no-model compatibility check for the changed list/call framing.

        Adopted type: ``mcp_types`` (REUSE-R2 #426) ``Tool``, ``ListToolsResult``
        and ``CallToolResult``.  Its models ignore unknown fields (``extra`` is
        unset) and also populate by Python name, so validation alone would pass
        a misnamed field.  Strict unknown-field rejection is therefore a
        wire-alias-only validation plus exact round-trip equality: anything the
        model would drop or rename fails here.  The bridge's hand-written
        envelope handling (#426 mismatch) is unchanged by #604.
        """
        from mcp_types import CallToolResult, ListToolsResult, Tool

        def strict(model, wire):
            parsed = model.model_validate(wire, by_alias=True, by_name=False)
            self.assertEqual(parsed.model_dump(by_alias=True, exclude_unset=True, mode="json"), wire)

        # The recorded mismatch this check compensates for stays visible.
        dropped = Tool.model_validate({"name": "t", "inputSchema": {"type": "object"}, "unknownField": 1})
        self.assertNotIn("unknownField", dropped.model_dump(by_alias=True, exclude_unset=True))

        listed = self._listed()
        strict(ListToolsResult, {"tools": listed})
        for tool in listed:
            with self.subTest(tool=tool["name"]):
                strict(Tool, tool)
                self.assertEqual(tool["inputSchema"]["type"], "object")
                self.assertIs(tool["inputSchema"]["additionalProperties"], False)
        reply = self._wire({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                            "params": {"name": "list_notes", "arguments": {}}})[2]
        self.assertEqual(set(reply), {"jsonrpc", "id", "result"})
        strict(CallToolResult, reply["result"])


INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}


def _running_work(store, text="bridge turn"):
    """A Work of ``store`` in the state a bridge serves: ``running``."""
    job = store.enqueue(text, "bridge-" + str(len(store.jobs())))
    with store.db() as db:
        db.execute("UPDATE jobs SET status='running' WHERE id=?", (job,))
    return job


@ordinary_lookup_judgment
class BoundedProfileHostInvocation(unittest.TestCase):
    """#604: weather, search, search-result page follow-up and a private read
    through the real bridge JSON-RPC loop and actual host invocation.

    Stubs replace only the public network: the search host, the weather host
    and page transport/DNS (the real ``PublicPageReader`` still enforces its
    SSRF, redirect and approved-scope rules).  No model is involved.
    """

    RESULTS = [
        {"url": "https://example.com/a", "title": "A", "snippet": "a"},
        {"url": "https://example.com/b", "title": "B", "snippet": "b"},
        {"url": "http://169.254.169.254/latest/meta-data/", "title": "M", "snippet": "m"},
    ]

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / "state")
        with self.store.db() as db:
            db.execute("INSERT INTO notes VALUES (?,?,?)", ("n1", "granted private note", 1))
        self.job = _running_work(self.store)
        self.searches, self.weather, self.opened = [], [], []

    def _network(self):
        from personal_agent.local_tools import LocalTools, PublicPageReader
        test = self

        class Response:
            def __init__(self, status=200, headers=None, body=b""):
                self.status, self.headers, self._body = status, headers or {}, io.BytesIO(body)

            def read(self, size=-1):
                return self._body.read(size)

        class Opener:
            def open(self, request, timeout=None):
                test.opened.append(request.full_url)
                if request.full_url.endswith("/b"):
                    return Response(302, {"Location": "https://elsewhere.example/landing"})
                return Response(200, {"Content-Type": "text/plain"}, b"Model A costs 100 USD. In stock: 3 units.")

        def public_dns(host, port, type=None, timeout=None):
            return [(None, None, None, None, ("93.184.216.34", port))]

        tools = LocalTools(page_reader=PublicPageReader(opener=Opener(), resolver=public_dns))

        def search(query):
            test.searches.append(query)
            return {"tool": "web_search", "query": query, "retrieved_at": 1, "results": test.RESULTS,
                    "sources": [row["url"] for row in test.RESULTS]}

        def weather(city, country=""):
            test.weather.append({"city": city, "country": country})
            return {"tool": "weather", "location": {"name": city}, "retrieved_at": 1, "forecast": {},
                    "sources": ["https://open-meteo.com/"]}

        tools.search, tools.weather = search, weather
        return tools

    def _serve(self, requests, job=None, provenance=()):
        from unittest import mock

        out = io.StringIO()
        with mock.patch.object(mcp_bridge, "LocalTools", self._network), \
             mock.patch.object(sys, "stdin", io.StringIO("".join(json.dumps(r) + "\n" for r in (INIT, *requests)))), \
             contextlib.redirect_stdout(out):
            mcp_bridge.serve(str(self.store.root), job or self.job, provenance)
        return {reply["id"]: reply for reply in map(json.loads, out.getvalue().splitlines())}

    @staticmethod
    def _call(ident, name, arguments):
        return {"jsonrpc": "2.0", "id": ident, "method": "tools/call", "params": {"name": name, "arguments": arguments}}

    @staticmethod
    def _value(reply):
        return json.loads(reply["result"]["content"][0]["text"])

    def test_allowed_public_and_private_reads_reach_the_host_with_exact_fields(self):
        replies = self._serve([
            self._call(2, "weather", {"city": "Daejeon", "country": "KR"}),
            self._call(3, "web_search", {"query": "today news"}),
            self._call(4, "bounded_public_research", {"mode": "product_comparison", "query": "model a price"}),
            self._call(5, "list_notes", {}),
        ])
        self.assertEqual(self.weather, [{"city": "Daejeon", "country": "KR"}])
        self.assertEqual(self.searches, ["today news", "model a price"])
        self.assertEqual(self._value(replies[2])["location"]["name"], "Daejeon")
        research = self._value(replies[4])
        # Only the research's own search results were contacted.  The metadata
        # address fails public-URL normalisation and is never a candidate; the
        # redirect off a result leaves its single-URL scope and is refused by
        # the shared reader, never followed.
        self.assertEqual(research["attempted_urls"], ["https://example.com/a", "https://example.com/b"])
        self.assertEqual(self.opened, ["https://example.com/a", "https://example.com/b"])
        self.assertEqual(research["sources"][:1], ["https://example.com/a"])
        self.assertEqual([row["url"] for row in research["read_failures"]], ["https://example.com/b"])
        self.assertIn("granted private note", [note["content"] for note in self._value(replies[5])["notes"]])
        with self.store.db() as db:
            events = [tuple(row) for row in db.execute(
                "SELECT tool,status FROM tool_events WHERE job_id=? AND status!='running' ORDER BY id", (self.job,))]
        self.assertEqual(events, [("weather", "succeeded"), ("web_search", "succeeded"),
                                  ("bounded_public_research", "succeeded"), ("list_notes", "succeeded")])
        # Review P1: the success trace carries the direct route's redacted
        # Evidence -- every contacted URL, failed reads and sources, no payload.
        traces = self._traces("succeeded")
        self.assertEqual(traces["bounded_public_research"]["evidence"]["attempted_urls"],
                         ["https://example.com/a", "https://example.com/b"])
        self.assertEqual(traces["bounded_public_research"]["evidence"]["read_failures"], ["https://example.com/b"])
        self.assertEqual(traces["weather"]["evidence"]["sources"], ["https://open-meteo.com/"])
        self.assertEqual(traces["list_notes"]["evidence"], {"note_count": 1})
        self.assertNotIn("granted private note", json.dumps(traces, ensure_ascii=False))

    def _traces(self, status):
        with self.store.db() as db:
            return {row[0]: json.loads(row[1]) for row in db.execute(
                "SELECT tool,detail FROM tool_events WHERE job_id=? AND status=?", (self.job, status))}

    def test_a_recorded_private_read_under_a_package_alias_taints_too(self):
        """Re-review P3: rehydration is keyed on the host action, not the built-in name."""
        with self.store.db() as db:
            db.execute("INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)",
                       (self.job, "my_notes", "succeeded",
                        json.dumps({"scope": "x", "host_action": "list_notes"}), 1))
        replies = self._serve([self._call(2, "web_search", {"query": "granted private note"})])
        self.assertTrue(_refused(replies[2]))
        self.assertEqual(self.searches, [])

    def test_private_taint_survives_a_second_bridge_process_for_the_same_work(self):
        """Review P2: a restarted bridge rehydrates taint from this Work's own events."""
        first = self._serve([self._call(2, "list_notes", {})])
        self.assertIn("result", first[2])
        second = self._serve([
            self._call(2, "weather", {"city": "granted private note"}),
            self._call(3, "web_search", {"query": "granted private note"}),
            self._call(4, "bounded_public_research", {"mode": "travel_plan", "query": "granted private note"}),
        ])
        for ident in (2, 3, 4):
            self.assertTrue(_refused(second[ident]))
        self.assertEqual((self.searches, self.weather, self.opened), ([], [], []))
        # Allowed control: another running Work of the same store is not tainted.
        other = _running_work(self.store, "another turn")
        self.assertIn("result", self._serve([self._call(2, "web_search", {"query": "today news"})], job=other)[2])

    def test_an_unlisted_tool_name_is_not_stored_verbatim(self):
        """Review P3: a CLI-chosen unknown name becomes 'unlisted' in the event store."""
        replies = self._serve([self._call(2, "run_shell; rm -rf ~ " + "x" * 200, {})])
        self.assertTrue(_refused(replies[2]))
        with self.store.db() as db:
            tools = [row[0] for row in db.execute("SELECT tool FROM tool_events WHERE job_id=?", (self.job,))]
        self.assertEqual(tools, ["unlisted"])

    def test_out_of_scope_self_approving_and_stale_calls_are_refused_before_the_network(self):
        cases = [
            self._call(2, "public_page_read", {"url": "https://example.com/a"}),        # not in the CLI profile
            self._call(3, "bounded_public_research", {"mode": "travel_plan", "query": "q",
                                                      "url": "https://evil.example/"}),  # no URL/approval channel
            self._call(4, "weather", {"city": "Daejeon", "approved_urls": ["x"]}),     # unknown field
            self._call(5, "read_file", {"root_id": "r", "path": "a.md"}),               # private, not bound
            self._call(6, "weather", {"city": 7}),                                      # non-string
        ]
        replies = self._serve(cases)
        for ident in range(2, 7):
            with self.subTest(case=ident):
                self.assertTrue(_refused(replies[ident]))
        self.assertEqual((self.searches, self.weather, self.opened), ([], [], []))
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='succeeded' WHERE id=?", (self.job,))
        stale = self._serve([self._call(2, "weather", {"city": "Daejeon"})])
        self.assertTrue(_refused(stale[2]), "a Work that ended cannot keep calling")
        self.assertEqual(self.weather, [])

    def test_private_provenance_still_closes_every_public_destination(self):
        replies = self._serve([
            self._call(2, "weather", {"city": "Daejeon"}),
            self._call(3, "web_search", {"query": "q"}),
            self._call(4, "bounded_public_research", {"mode": "travel_plan", "query": "q"}),
            self._call(5, "list_notes", {}),
        ], provenance=["personal-space"])
        for ident in (2, 3, 4):
            self.assertTrue(_refused(replies[ident]))
        self.assertIn("result", replies[5], "the granted private read still works")
        self.assertEqual((self.searches, self.weather, self.opened), ([], [], []))

    def test_a_private_read_in_the_same_bridge_session_closes_the_new_public_reads(self):
        """Same-Work provenance: after list_notes, weather and research are refused."""
        replies = self._serve([
            self._call(2, "list_notes", {}),
            self._call(3, "weather", {"city": "Daejeon"}),
            self._call(4, "bounded_public_research", {"mode": "travel_plan", "query": "q"}),
        ])
        self.assertIn("result", replies[2])
        self.assertTrue(_refused(replies[3]))
        self.assertTrue(_refused(replies[4]))
        self.assertEqual((self.searches, self.weather, self.opened), ([], [], []))


@ordinary_lookup_judgment
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
        job = _running_work(store)
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
                mcp_bridge.serve(str(store.root), job, provenance)
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
        self.assertTrue(_refused(replies[1]))
        self.assertEqual(calls, [])

    def _failure_signatures(self):
        replies, _ = self._serve([
            self._call(1, "web_search", {"query": "today news"}),       # policy denied (taint below)
            self._call(2, "web_search", {"q": "today news"}),           # invalid arguments
            self._call(3, "read_file", {"root_id": "r", "path": "a"}),  # tool not exposed (weather is, since #604)
            {"jsonrpc": "2.0", "id": 4, "method": "resources/list"},     # unsupported method
        ], provenance=["conversation-history"])
        return {ident: json.dumps(reply.get("error") or reply.get("result"), sort_keys=True) for ident, reply in replies.items()}

    def test_finding_distinct_failures_collapse_into_one_protocol_error(self):
        """Fixed by #607 (AX-06); was an ``expectedFailure`` finding.

        Policy denial is a typed tool-result error; invalid arguments, an
        unexposed tool and an unsupported method are distinct protocol errors.
        """
        signatures = self._failure_signatures()
        self.assertEqual(sorted(signatures), [1, 2, 3, 4])
        self.assertEqual(len(set(signatures.values())), 4, signatures)

    def test_finding_a_transient_network_failure_ends_the_bridge(self):
        """Fixed by #607 (AX-06); was an ``expectedFailure`` finding: a
        ProviderError from the public read escaped the loop, so the call got no
        reply and later requests none.  It is now a typed tool-result error.
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
