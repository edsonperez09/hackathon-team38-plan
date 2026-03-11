"""
tests/test_phase3.py
Phase 3 validation — scenario modeling tests.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.deltek_client import extract_planning_data
from modules.scenario_model import (
    take_snapshot, get_snapshot, list_snapshots,
    what_if, compare, project_summary, flag_violations,
)


def test_snapshot_save_restore():
    rows = extract_planning_data()
    take_snapshot(rows, "test_snap")
    restored = get_snapshot("test_snap")
    assert restored is not None
    assert len(restored) == len(rows)
    assert restored[0]["Employee Name"] == rows[0]["Employee Name"]
    print(f"  PASS: snapshot saved and restored ({len(restored)} employees)")


def test_snapshot_is_deep_copy():
    rows = extract_planning_data()
    take_snapshot(rows, "isolation_test")
    rows[0]["Labor Rate"] = "$999/hr"        # mutate original
    restored = get_snapshot("isolation_test")
    assert restored[0]["Labor Rate"] != "$999/hr"  # snapshot unaffected
    print("  PASS: snapshot is isolated from original data mutations")


def test_what_if_is_nondestructive():
    rows = extract_planning_data()
    original_util = next(r for r in rows if r["Employee Name"] == "Li Wei")["Current Utilization %"]

    what_if(rows, [{"employee": "Li Wei", "field": "Current Utilization %", "new_value": 50}])

    current_util = next(r for r in rows if r["Employee Name"] == "Li Wei")["Current Utilization %"]
    assert current_util == original_util
    print(f"  PASS: what_if is non-destructive — Li Wei utilization unchanged at {current_util}%")


def test_what_if_compare_report():
    rows = extract_planning_data()
    changes = [{"employee": "Li Wei", "field": "Current Utilization %", "new_value": 75}]
    report = what_if(rows, changes)

    assert "employee_diffs" in report
    assert "project_summary" in report
    assert "overall" in report
    assert "violations" in report

    li_diff = next((d for d in report["employee_diffs"] if d["employee"] == "Li Wei"), None)
    assert li_diff is not None
    assert "Current Utilization %" in li_diff["changes"]
    assert li_diff["changes"]["Current Utilization %"]["before"] == 84
    assert li_diff["changes"]["Current Utilization %"]["after"]  == 75
    assert li_diff["changes"]["Current Utilization %"]["delta"]  == -9
    print(f"  PASS: what-if diff — Li Wei utilization 84% → 75% (delta=-9)")


def test_project_summary_aggregates():
    rows = extract_planning_data()
    summary = project_summary(rows)

    assert set(summary.keys()) == {"Project Atlas", "Project Helios", "Project Titan"}

    atlas = summary["Project Atlas"]
    assert atlas["headcount"] == 3
    assert atlas["total_labor_cost"] > 0
    assert atlas["total_revenue"] > atlas["total_labor_cost"]   # revenue > cost
    assert 0 < atlas["avg_margin_pct"] < 100
    print(f"  PASS: project summary — Atlas: headcount={atlas['headcount']}, "
          f"revenue=${atlas['total_revenue']:,.0f}, margin={atlas['avg_margin_pct']}%")


def test_flag_violations_existing():
    rows = extract_planning_data()
    violations = flag_violations(rows)

    names_with_violations = [v["employee"] for v in violations]
    # Priya Sharma at 92% and all employees whose labor cost > budget should appear
    assert "Priya Sharma" in names_with_violations
    print(f"  PASS: violations detected — {len(violations)} total, "
          f"employees: {list(set(names_with_violations))}")


def test_flag_violations_after_fix():
    rows = extract_planning_data()
    # Fix Priya's utilization
    for r in rows:
        if r["Employee Name"] == "Priya Sharma":
            r["Current Utilization %"] = 78
            from modules.excel_handler import recalculate
            r = recalculate(r)

    violations = flag_violations(rows)
    util_violations = [v for v in violations if v["employee"] == "Priya Sharma"
                       and "Utilization" in v["rule"]]
    assert len(util_violations) == 0
    print("  PASS: no utilization violation for Priya Sharma after fix to 78%")


def test_overall_metrics():
    rows = extract_planning_data()
    changes = [
        {"employee": "Li Wei",         "field": "Current Utilization %", "new_value": 78},
        {"employee": "Carlos Ramirez", "field": "Current Utilization %", "new_value": 79},
        {"employee": "Priya Sharma",   "field": "Current Utilization %", "new_value": 80},
    ]
    report = what_if(rows, changes)

    before = report["overall"]["before"]
    after  = report["overall"]["after"]

    # Revenue and cost should not change (utilization doesn't affect them in current model)
    assert before["total_revenue"] == after["total_revenue"]

    # Violations should be fewer after fixing over-utilized employees
    before_violations = len(flag_violations(rows))
    after_violations  = len(report["violations"])
    assert after_violations < before_violations
    print(f"  PASS: overall metrics — violations reduced from {before_violations} → {after_violations}")


if __name__ == "__main__":
    print("\n=== Phase 3 Tests ===\n")
    tests = [
        test_snapshot_save_restore,
        test_snapshot_is_deep_copy,
        test_what_if_is_nondestructive,
        test_what_if_compare_report,
        test_project_summary_aggregates,
        test_flag_violations_existing,
        test_flag_violations_after_fix,
        test_overall_metrics,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  FAIL [{t.__name__}]: {e}")
    print(f"\n{passed}/{len(tests)} tests passed.")
