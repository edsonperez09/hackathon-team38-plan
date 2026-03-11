"""
tests/test_phase4.py
Phase 4 validation — validator and push-to-Deltek tests.
"""
import sys, os, copy
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.deltek_client import extract_planning_data, push_planning_data
from modules.excel_handler import recalculate
from modules.validator import validate


# ---------------------------------------------------------------------------
# Validator unit tests
# ---------------------------------------------------------------------------

def test_blocking_high_risk_utilization():
    rows = copy.deepcopy(extract_planning_data())
    # Inject a high-risk utilization violation
    for r in rows:
        if r["Employee Name"] == "Priya Sharma":
            r["Current Utilization %"] = 92
            r["Risk Level"] = "High"
    result = validate(rows)
    blocking_names = [v["employee"] for v in result["blocking"]]
    assert "Priya Sharma" in blocking_names, "Priya (92%) must be a blocking violation"
    assert not result["valid"]
    print(f"  PASS: Priya Sharma blocked — {[v['rule'] for v in result['blocking'] if v['employee'] == 'Priya Sharma']}")


def test_no_blocking_after_fix():
    rows = copy.deepcopy(extract_planning_data())
    for r in rows:
        if r["Current Utilization %"] > 88:
            r["Current Utilization %"] = 80
            recalculate(r)
    result = validate(rows)
    assert len(result["blocking"]) == 0
    assert result["valid"]
    print(f"  PASS: no blocking violations after fixing utilization — {result['summary']}")


def test_blocking_negative_margin():
    rows = copy.deepcopy(extract_planning_data())
    rows[0]["Target Margin %"] = -5
    result = validate(rows)
    blocking = [v for v in result["blocking"] if v["employee"] == rows[0]["Employee Name"]]
    assert any("Negative" in v["rule"] for v in blocking)
    assert not result["valid"]
    print(f"  PASS: negative margin blocks push — {blocking[0]['detail']}")


def test_warning_utilization_between_cap_and_threshold():
    rows = copy.deepcopy(extract_planning_data())
    # Set utilization to 83% — above cap (82%) but below high-risk (88%)
    for r in rows:
        if r["Employee Name"] == "Edison Macabuhay":
            r["Current Utilization %"] = 83
            recalculate(r)
    result = validate(rows)
    warn_names = [v["employee"] for v in result["warnings"] if "Utilization" in v["rule"]]
    assert "Edison Macabuhay" in warn_names
    print(f"  PASS: 83% utilization is a warning, not blocking — {warn_names}")


def test_warning_low_margin():
    rows = copy.deepcopy(extract_planning_data())
    rows[0]["Target Margin %"] = 5   # below 10% threshold but positive
    result = validate(rows)
    warn_names = [v["employee"] for v in result["warnings"] if "margin" in v["rule"].lower()]
    assert rows[0]["Employee Name"] in warn_names
    print(f"  PASS: margin=5% triggers warning, not blocking — {warn_names}")


def test_override_allows_push_despite_blocking():
    rows = copy.deepcopy(extract_planning_data())
    # Inject a blocking violation
    for r in rows:
        if r["Employee Name"] == "Priya Sharma":
            r["Current Utilization %"] = 92
            r["Risk Level"] = "High"
    result = validate(rows, override=True)
    assert result["valid"]
    assert result["override"]
    assert len(result["blocking"]) > 0   # blocking issues still listed
    print(f"  PASS: override=True allows push — {len(result['blocking'])} blocking issue(s) bypassed")


def test_burden_rate_sync_warning():
    rows = copy.deepcopy(extract_planning_data())
    # Manually break the burdened rate (out of sync with labor rate)
    rows[0]["Labor Rate"]         = "$60/hr"
    rows[0]["Fully Burdened Rate"] = "$50/hr"   # should be $78/hr — out of sync
    result = validate(rows)
    sync_warns = [v for v in result["warnings"] if "sync" in v["rule"].lower()]
    assert len(sync_warns) > 0
    print(f"  PASS: out-of-sync burdened rate flagged as warning — {sync_warns[0]['detail']}")


# ---------------------------------------------------------------------------
# Push integration tests
# ---------------------------------------------------------------------------

def test_push_blocked_with_violations():
    rows = copy.deepcopy(extract_planning_data())
    # Inject a blocking violation without writing to file
    for r in rows:
        if r["Employee Name"] == "Priya Sharma":
            r["Current Utilization %"] = 92
            r["Risk Level"] = "High"
    result = push_planning_data(rows, override=False)
    assert not result["success"]
    assert len(result["validation"]["blocking"]) > 0
    print(f"  PASS: push blocked — {result['validation']['summary']}")


def test_push_succeeds_with_override():
    rows = extract_planning_data()
    result = push_planning_data(rows, override=True)
    assert result["success"]
    assert result["validation"]["override"]
    print(f"  PASS: push succeeded with override — {result['validation']['summary']}")


def test_push_succeeds_after_fix():
    rows = copy.deepcopy(extract_planning_data())
    for r in rows:
        if r["Current Utilization %"] > 88:
            r["Current Utilization %"] = 80
            recalculate(r)
    result = push_planning_data(rows, override=False)
    assert result["success"]
    assert len(result["validation"]["blocking"]) == 0
    print(f"  PASS: push succeeded after fixing violations — {result['validation']['summary']}")


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

def test_validate_endpoint():
    import main
    from fastapi.testclient import TestClient
    client = TestClient(main.app)

    r = client.get("/validate")
    assert r.status_code == 200
    data = r.json()
    assert "valid" in data and "blocking" in data and "warnings" in data
    print(f"  PASS: GET /validate — valid={data['valid']}, "
          f"blocking={len(data['blocking'])}, warnings={len(data['warnings'])}")


def test_push_endpoint_blocked():
    import main
    from fastapi.testclient import TestClient
    client = TestClient(main.app)

    # Pass an explicit row with a high-risk violation (utilization > 88%)
    bad_rows = [{col: "" for col in [
        "Employee Name", "Role", "Labor Rate", "Skills", "Project Designation",
        "Date Hired", "Tenureship", "Project Total Budget", "Project Timeline",
        "Allocation %", "Est. Hours/Week", "Burden Rate %", "Fully Burdened Rate",
        "Est. Total Labor Cost", "Billing Rate", "Target Margin %",
        "Revenue Forecast", "Current Utilization %", "Risk Level", "Project Phase",
    ]}]
    bad_rows[0].update({
        "Employee Name": "Test Employee", "Current Utilization %": 95,
        "Risk Level": "High", "Target Margin %": 15, "Labor Rate": "$50/hr",
        "Burden Rate %": 30, "Fully Burdened Rate": "$65.0/hr",
        "Billing Rate": "$80/hr", "Project Total Budget": 100000,
    })

    r = client.post("/push", json={"rows": bad_rows, "override": False})
    assert r.status_code == 422
    print(f"  PASS: POST /push blocked with 422 — {r.json()['detail']['validation']['summary']}")


def test_push_endpoint_override():
    import main
    from fastapi.testclient import TestClient
    client = TestClient(main.app)

    r = client.post("/push", json={"rows": [], "override": True})
    assert r.status_code == 200
    assert r.json()["success"]
    print(f"  PASS: POST /push with override=true succeeded")


if __name__ == "__main__":
    print("\n=== Phase 4 Tests ===\n")
    tests = [
        test_blocking_high_risk_utilization,
        test_no_blocking_after_fix,
        test_blocking_negative_margin,
        test_warning_utilization_between_cap_and_threshold,
        test_warning_low_margin,
        test_override_allows_push_despite_blocking,
        test_burden_rate_sync_warning,
        test_push_blocked_with_violations,
        test_push_succeeds_with_override,
        test_push_succeeds_after_fix,
        test_validate_endpoint,
        test_push_endpoint_blocked,
        test_push_endpoint_override,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  FAIL [{t.__name__}]: {e}")
    print(f"\n{passed}/{len(tests)} tests passed.")
