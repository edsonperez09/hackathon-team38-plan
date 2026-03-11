"""
tests/test_phase5.py
Phase 5 validation — UI and full end-to-end API smoke tests.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main
from fastapi.testclient import TestClient

client = TestClient(main.app)


def test_root_serves_html():
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "AI Planning Coworker" in r.text
    assert "Claude" in r.text
    print("  PASS: GET / returns HTML with correct title")


def test_ui_contains_key_elements():
    r = client.get("/")
    html = r.text
    assert "Ask Claude" in html
    assert "Preview Changes" in html
    assert "Push to Deltek" in html
    assert "Project Overview" in html
    assert "Planning Data" in html
    print("  PASS: UI contains all key UI sections")


def test_scenario_summary_has_all_projects():
    r = client.get("/scenario/summary")
    assert r.status_code == 200
    data = r.json()
    assert "Project Atlas" in data["projects"]
    assert "Project Helios" in data["projects"]
    assert "Project Titan" in data["projects"]
    for name, metrics in data["projects"].items():
        assert metrics["total_revenue"] > 0
        assert metrics["avg_margin_pct"] > 0
        assert metrics["headcount"] > 0
    print(f"  PASS: /scenario/summary — all 3 projects with valid metrics")


def test_data_endpoint_returns_full_schema():
    r = client.get("/data")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 10
    required = ["Employee Name", "Risk Level", "Target Margin %",
                "Revenue Forecast", "Current Utilization %", "Billing Rate"]
    for col in required:
        assert col in rows[0], f"Missing column: {col}"
    print(f"  PASS: GET /data — 10 employees, all required columns present")


def test_validate_endpoint_returns_full_structure():
    r = client.get("/validate")
    assert r.status_code == 200
    data = r.json()
    assert "valid" in data
    assert "blocking" in data
    assert "warnings" in data
    assert "summary" in data
    print(f"  PASS: GET /validate — valid={data['valid']}, "
          f"blocking={len(data['blocking'])}, warnings={len(data['warnings'])}")


def test_what_if_endpoint_returns_comparison():
    r = client.post("/scenario/what-if", json={"changes": [
        {"employee": "Li Wei", "field": "Current Utilization %", "new_value": 75},
    ]})
    assert r.status_code == 200
    data = r.json()
    assert "employee_diffs" in data
    assert "overall" in data
    assert "violations" in data
    li_diff = next((d for d in data["employee_diffs"] if d["employee"] == "Li Wei"), None)
    assert li_diff is not None
    print(f"  PASS: POST /scenario/what-if — Li Wei diff present with "
          f"{len(li_diff['changes'])} field change(s)")


def test_ask_without_api_key_returns_500():
    original = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        r = client.post("/ask", json={"prompt": "test", "push_to_deltek": False})
        assert r.status_code == 500
        assert "ANTHROPIC_API_KEY" in r.json()["detail"]
        print("  PASS: POST /ask without API key returns 500 with helpful message")
    finally:
        if original:
            os.environ["ANTHROPIC_API_KEY"] = original


def test_push_endpoint_with_override():
    r = client.post("/push", json={"rows": [], "override": True})
    assert r.status_code == 200
    assert r.json()["success"]
    print("  PASS: POST /push with override=true — 200 OK")


def test_full_api_coverage():
    endpoints = [
        ("GET",  "/"),
        ("GET",  "/data"),
        ("GET",  "/projects"),
        ("GET",  "/validate"),
        ("GET",  "/scenario/summary"),
        ("GET",  "/scenario/violations"),
        ("GET",  "/scenario/snapshots"),
    ]
    for method, path in endpoints:
        r = client.get(path) if method == "GET" else client.post(path)
        assert r.status_code == 200, f"{method} {path} returned {r.status_code}"
    print(f"  PASS: all {len(endpoints)} GET endpoints return 200")


if __name__ == "__main__":
    print("\n=== Phase 5 Tests ===\n")
    tests = [
        test_root_serves_html,
        test_ui_contains_key_elements,
        test_scenario_summary_has_all_projects,
        test_data_endpoint_returns_full_schema,
        test_validate_endpoint_returns_full_structure,
        test_what_if_endpoint_returns_comparison,
        test_ask_without_api_key_returns_500,
        test_push_endpoint_with_override,
        test_full_api_coverage,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  FAIL [{t.__name__}]: {e}")
    print(f"\n{passed}/{len(tests)} tests passed.")
