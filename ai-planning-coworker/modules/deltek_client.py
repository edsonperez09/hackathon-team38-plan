"""
deltek_client.py
Mock Deltek Vantagepoint client.

Simulates extract and push operations using the local Excel file.
In production, replace read_xlsx / write_xlsx calls with real
Deltek Vantagepoint REST API calls using httpx.
"""
import os
from modules.excel_handler import read_xlsx, write_xlsx

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "Vantagepoint Project.xlsx")


def extract_planning_data() -> list[dict]:
    """
    Extract planning data from Deltek Vantagepoint.
    Returns a list of employee dicts with all 20 columns.

    Production: replace with GET request to Vantagepoint REST API.
    """
    print("[Deltek] Extracting planning data from Vantagepoint...")
    rows = read_xlsx(DATA_PATH)
    print(f"[Deltek] Extracted {len(rows)} employee records across "
          f"{len(set(r['Project Designation'] for r in rows))} projects.")
    return rows


def push_planning_data(rows: list[dict], override: bool = False) -> dict:
    """
    Validate then push planning data back to Deltek Vantagepoint.
    Blocks push if validation fails unless override=True.

    Returns a result dict with keys: success, validation.
    Production: replace write_xlsx with PUT/POST to Vantagepoint REST API.
    """
    from modules.validator import validate

    result = validate(rows, override=override)

    if not result["valid"]:
        print(f"[Deltek] Push BLOCKED — {result['summary']}")
        return {"success": False, "validation": result}

    if result["warnings"]:
        print(f"[Deltek] Push proceeding with {len(result['warnings'])} warning(s).")

    print(f"[Deltek] Pushing {len(rows)} records to Vantagepoint...")
    write_xlsx(DATA_PATH, rows)
    print("[Deltek] Push complete.")

    return {"success": True, "validation": result}


def get_projects() -> list[str]:
    """Return a distinct list of project names from the planning data."""
    rows = extract_planning_data()
    return sorted(set(r["Project Designation"] for r in rows))


def get_employees_by_project(project: str) -> list[dict]:
    """Return all employees assigned to a given project."""
    rows = extract_planning_data()
    return [r for r in rows if r["Project Designation"] == project]
