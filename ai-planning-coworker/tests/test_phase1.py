"""
tests/test_phase1.py
Phase 1 validation — data layer smoke tests.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.deltek_client import extract_planning_data, get_projects, get_employees_by_project
from modules.excel_handler import recalculate, COLUMNS

def test_extract():
    rows = extract_planning_data()
    assert len(rows) == 10, f"Expected 10 employees, got {len(rows)}"
    print(f"  PASS: extracted {len(rows)} employees")

def test_columns():
    rows = extract_planning_data()
    for col in COLUMNS:
        assert col in rows[0], f"Missing column: {col}"
    print(f"  PASS: all {len(COLUMNS)} columns present")

def test_projects():
    projects = get_projects()
    assert set(projects) == {"Project Atlas", "Project Helios", "Project Titan"}
    print(f"  PASS: projects found — {projects}")

def test_employees_by_project():
    titan = get_employees_by_project("Project Titan")
    assert len(titan) == 5, f"Expected 5 in Titan, got {len(titan)}"
    atlas = get_employees_by_project("Project Atlas")
    assert len(atlas) == 3, f"Expected 3 in Atlas, got {len(atlas)}"
    helios = get_employees_by_project("Project Helios")
    assert len(helios) == 2, f"Expected 2 in Helios, got {len(helios)}"
    print(f"  PASS: project employee counts — Atlas:{len(atlas)}, Helios:{len(helios)}, Titan:{len(titan)}")

def test_risk_flags():
    rows = extract_planning_data()
    high_risk = [r for r in rows if r["Risk Level"] == "High"]
    assert any(r["Employee Name"] == "Priya Sharma" for r in high_risk), \
        "Priya Sharma (92%) should be High risk"
    print(f"  PASS: High-risk employees — {[r['Employee Name'] for r in high_risk]}")

def test_recalculate():
    rows = extract_planning_data()
    emp = next(r for r in rows if r["Employee Name"] == "Edison Macabuhay")
    emp["Labor Rate"] = "$50/hr"  # bump rate
    emp = recalculate(emp)
    assert emp["Fully Burdened Rate"] == "$65.0/hr", f"Expected $65.0/hr, got {emp['Fully Burdened Rate']}"
    assert emp["Target Margin %"] > 0, "Margin should remain positive"
    print(f"  PASS: recalculate — burdened={emp['Fully Burdened Rate']}, margin={emp['Target Margin %']}%")

if __name__ == "__main__":
    print("\n=== Phase 1 Tests ===\n")
    tests = [test_extract, test_columns, test_projects, test_employees_by_project, test_risk_flags, test_recalculate]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  FAIL [{t.__name__}]: {e}")
    print(f"\n{passed}/{len(tests)} tests passed.")
