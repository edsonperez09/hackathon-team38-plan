"""
tests/test_phase2.py
Phase 2 validation — AI engine unit tests.

Tests that don't require an API key run against the internal logic.
The live Claude test is skipped if ANTHROPIC_API_KEY is not set.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.excel_handler import recalculate, COLUMNS
from modules.deltek_client import extract_planning_data
from modules.ai_engine import _apply_changes, _rows_to_context


def test_apply_single_change():
    rows = extract_planning_data()
    changes = [{"employee": "Edison Macabuhay", "field": "Labor Rate", "new_value": "$55/hr"}]
    updated, skipped = _apply_changes(rows, changes)

    emp = next(r for r in updated if r["Employee Name"] == "Edison Macabuhay")
    assert emp["Labor Rate"] == "$55/hr"
    assert emp["Fully Burdened Rate"] == "$71.5/hr"   # 55 * 1.30
    assert skipped == []
    print(f"  PASS: single change applied — Labor Rate=$55/hr → Burdened={emp['Fully Burdened Rate']}")


def test_apply_multiple_changes():
    rows = extract_planning_data()
    changes = [
        {"employee": "Li Wei",        "field": "Current Utilization %", "new_value": 78},
        {"employee": "Carlos Ramirez","field": "Current Utilization %", "new_value": 79},
    ]
    updated, skipped = _apply_changes(rows, changes)

    li     = next(r for r in updated if r["Employee Name"] == "Li Wei")
    carlos = next(r for r in updated if r["Employee Name"] == "Carlos Ramirez")

    assert li["Current Utilization %"] == 78 and li["Risk Level"] == "Low"
    assert carlos["Current Utilization %"] == 79 and carlos["Risk Level"] == "Low"
    assert skipped == []
    print(f"  PASS: multiple changes — Li Wei={li['Risk Level']}, Carlos={carlos['Risk Level']}")


def test_unknown_employee_skipped():
    rows = extract_planning_data()
    changes = [{"employee": "Ghost Employee", "field": "Labor Rate", "new_value": "$99/hr"}]
    _, skipped = _apply_changes(rows, changes)
    assert len(skipped) == 1 and "Ghost Employee" in skipped[0]
    print(f"  PASS: unknown employee skipped — {skipped[0]}")


def test_unknown_field_skipped():
    rows = extract_planning_data()
    changes = [{"employee": "Maria Santos", "field": "NonExistentField", "new_value": "X"}]
    _, skipped = _apply_changes(rows, changes)
    assert len(skipped) == 1 and "NonExistentField" in skipped[0]
    print(f"  PASS: unknown field skipped — {skipped[0]}")


def test_recalculate_chain():
    rows = extract_planning_data()
    emp = next(r for r in rows if r["Employee Name"] == "Ahmed Khan")

    # Increase billing rate — should raise margin
    emp["Billing Rate"] = "$65/hr"
    emp = recalculate(emp)
    assert emp["Target Margin %"] > 20, f"Expected margin > 20%, got {emp['Target Margin %']}"
    assert emp["Revenue Forecast"] > 0
    print(f"  PASS: recalculate chain — margin={emp['Target Margin %']}%, revenue={emp['Revenue Forecast']}")


def test_context_serialization():
    rows = extract_planning_data()
    context = _rows_to_context(rows)
    assert "Edison Macabuhay" in context
    assert "Project Atlas" in context
    assert "Labor Rate" in context
    print(f"  PASS: context serialized ({len(context)} chars)")


def test_live_claude(prompt="Who is over-utilized? List them with their utilization %."):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("  SKIP: ANTHROPIC_API_KEY not set — skipping live Claude test")
        return

    from modules.ai_engine import ask
    rows = extract_planning_data()
    result = ask(prompt, rows)

    assert "summary" in result
    assert "rows" in result
    assert len(result["rows"]) == 10
    print(f"  PASS: live Claude response — {result['summary'][:80]}...")
    if result.get("warnings"):
        print(f"  Warnings: {result['warnings']}")


if __name__ == "__main__":
    print("\n=== Phase 2 Tests ===\n")
    tests = [
        test_apply_single_change,
        test_apply_multiple_changes,
        test_unknown_employee_skipped,
        test_unknown_field_skipped,
        test_recalculate_chain,
        test_context_serialization,
        test_live_claude,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  FAIL [{t.__name__}]: {e}")
    print(f"\n{passed}/{len(tests)} tests passed.")
