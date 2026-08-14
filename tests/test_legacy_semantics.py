import ast
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src" / "ails_intel"


def test_snapshot_barrier_has_one_executable_owner():
    owners = []
    for path in SRC.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "validate_structured_snapshot_barrier"
            for node in ast.walk(tree)
        ):
            owners.append(path.name)
    assert owners == ["snapshot_policy.py"]


def test_retired_coverage_veto_tokens_are_absent_from_executable_source():
    text = "\n".join(path.read_text(encoding="utf-8") for path in SRC.glob("*.py"))
    assert "structured_snapshot_unready_collector" not in text
    assert "freeze_not_allowed_from_low_coverage" not in text
    assert "final_coverage_still_low" not in text
