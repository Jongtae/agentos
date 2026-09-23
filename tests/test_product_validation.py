"""Product-validation gate, relocated to scripts/ by REUSE-R8 / #435.

The module is a development-only repository-introspection tool: it imports no
product code and reads the package as text, so it does not belong in the
installed runtime. It is loaded by path here, the same way the repository
already tests other scripts/ modules.
"""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_NAME = "scripts_product_validation"
_spec = importlib.util.spec_from_file_location(
    _NAME, Path(__file__).resolve().parents[1] / "scripts" / "product_validation.py"
)
_module = importlib.util.module_from_spec(_spec)
# Registered before exec_module because the module defines a @dataclass under
# `from __future__ import annotations`; dataclasses resolves the owning module
# through sys.modules and fails with AttributeError if it is absent.
sys.modules[_NAME] = _module
_spec.loader.exec_module(_module)
ProductValidator, markdown = _module.ProductValidator, _module.markdown


class ProductValidationTests(unittest.TestCase):
    def fixture(self):
        folder = tempfile.TemporaryDirectory(); root = Path(folder.name)
        (root / "docs").mkdir(); (root / "src/personal_agent").mkdir(parents=True)
        (root / "TASKS.md").write_text("# tasks\n")
        (root / "QUICKSTART.md").write_text("PDF and Office documents are supported.\n")
        (root / "docs/roadmap.md").write_text("## M3 — continuity and installation\nCompleted: yes\n## M4 — extensibility\nCompleted: yes\n## M5 — v1 release\nCompleted: yes\n")
        (root / "src/personal_agent/quickstart_service.py").write_text("model_ready document_boundary connect_telegram")
        (root / "src/personal_agent/agent_runtime.py").write_text("delegate_agent")
        (root / "src/personal_agent/plugins.py").write_text("class PluginRegistry: pass")
        (root / "src/personal_agent/quickstart.py").write_text("# no plugin interface")
        return folder, root

    def test_stale_documents_fail(self):
        folder, root = self.fixture()
        try:
            (root / "TASKS.md").write_text("| M3 | Persistent runtime and official server install | Planned |\n")
            validator = ProductValidator(root); validator.documentation()
            self.assertEqual(validator.findings[0].status, "failed")
        finally: folder.cleanup()

    def test_delivered_roadmap_wording_is_current(self):
        folder, root = self.fixture()
        try:
            (root / "docs/roadmap.md").write_text("## M3 — continuity and installation\nCompleted: yes\n## M4 — extensibility\nP4-01 delivered\n## M5 — v1 release\nCompleted: yes\n")
            validator = ProductValidator(root); validator.documentation()
            self.assertEqual(validator.findings[0].status, "passed")
        finally: folder.cleanup()

    def test_plugin_registry_without_surface_fails(self):
        folder, root = self.fixture()
        try:
            validator = ProductValidator(root); validator.source_contracts()
            self.assertEqual(next(f for f in validator.findings if f.id == "EXT-001").status, "failed")
        finally: folder.cleanup()

    def test_command_failure_is_reported_without_output_leak(self):
        folder, root = self.fixture()
        try:
            def runner(*args, **kwargs): return subprocess.CompletedProcess(args[0], 1, "", "failed")
            validator = ProductValidator(root, runner=runner)
            self.assertFalse(validator.command(["bad"], "Contract check"))
            self.assertEqual(validator.findings[-1].status, "failed")
        finally: folder.cleanup()

    def test_markdown_contains_all_findings(self):
        folder, root = self.fixture()
        try:
            validator = ProductValidator(root); validator.documentation(); validator.vision_gaps()
            report = validator.report()
            self.assertIn("VISION-001", markdown(report))
        finally: folder.cleanup()
