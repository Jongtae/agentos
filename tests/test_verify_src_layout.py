import importlib.util
from pathlib import Path
import textwrap

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_src_layout", ROOT / "scripts" / "verify_src_layout.py")
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)

BOOTSTRAP = 'import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))\n'


@pytest.fixture
def layout(tmp_path):
    package = tmp_path / "src" / "personal_agent"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("raise RuntimeError('package code must not run')\n")
    (package / "store.py").write_text("raise RuntimeError('module code must not run')\nclass Store:\n    pass\n")
    (tmp_path / "scripts").mkdir()
    return tmp_path


def _script(layout, body):
    path = layout / "scripts" / "tool.py"
    path.write_text(textwrap.dedent(body))
    return path


def test_repository_package_scripts_pass():
    assert verifier.main() == 0


def test_resolvable_import_passes_without_executing_package_code(layout):
    script = _script(layout, BOOTSTRAP + "from personal_agent.store import Store\n")
    assert verifier.check_package_script(script, layout / "src") == []


def test_bootstrap_to_missing_module_fails(layout):
    script = _script(layout, BOOTSTRAP + "from personal_agent.gone import Store\n")
    assert verifier.check_package_script(script, layout / "src") == [
        "tool.py imports missing module personal_agent.gone"]


def test_removing_the_imported_module_turns_the_gate_red(layout):
    script = _script(layout, BOOTSTRAP + "from personal_agent.store import Store\n")
    (layout / "src" / "personal_agent" / "store.py").unlink()
    assert verifier.check_package_script(script, layout / "src") == [
        "tool.py imports missing module personal_agent.store"]


def test_missing_imported_name_fails(layout):
    script = _script(layout, BOOTSTRAP + "from personal_agent.store import Missing\n")
    assert verifier.check_package_script(script, layout / "src") == [
        "tool.py imports missing name personal_agent.store.Missing"]


def test_src_only_in_comment_or_docstring_is_not_a_bootstrap(layout):
    script = _script(layout, '"""Uses /src."""\n# sys.path.insert(0, "/src")\nfrom personal_agent.store import Store\n')
    assert verifier.check_package_script(script, layout / "src") == [
        "tool.py does not bootstrap the src package root"]


def test_bootstrap_through_module_level_name_passes(layout):
    script = _script(layout, """\
        import sys
        from pathlib import Path
        SOURCE = Path(__file__).resolve().parents[1] / "src"
        sys.path.insert(0, str(SOURCE))

        def run():
            from personal_agent.store import Store
        """)
    assert verifier.check_package_script(script, layout / "src") == []


def test_listed_script_without_package_import_fails(layout):
    script = _script(layout, BOOTSTRAP)
    assert verifier.check_package_script(script, layout / "src") == [
        "tool.py does not import personal_agent from the src root"]
