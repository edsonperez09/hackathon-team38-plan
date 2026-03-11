"""
main.py
AI-Powered Planning Coworker — FastAPI entry point.
"""
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os, shutil, tempfile

from modules.excel_handler import read_xlsx

from modules.deltek_client import extract_planning_data, push_planning_data, get_projects
from modules.ai_engine import ask
from modules.scenario_model import (
    take_snapshot, get_snapshot, list_snapshots,
    what_if, compare, project_summary, flag_violations,
)
from modules.validator import validate

app = FastAPI(
    title="AI-Powered Planning Coworker",
    description="Deltek Vantagepoint planning assistant powered by Claude AI",
    version="1.0.0",
)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
DATA_PATH  = os.path.join(os.path.dirname(__file__), "data", "Vantagepoint Project.xlsx")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class PromptRequest(BaseModel):
    prompt: str
    push_to_deltek: bool = False


class WhatIfRequest(BaseModel):
    changes: list[dict]


class PushRequest(BaseModel):
    rows: list[dict]
    override: bool = False


@app.get("/")
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/data")
def get_data():
    """Return all planning data from Vantagepoint."""
    return extract_planning_data()


@app.get("/projects")
def list_projects():
    """Return all distinct project names."""
    return get_projects()


@app.post("/ask")
def ask_ai(request: PromptRequest):
    """
    Send a natural language instruction to Claude.
    Claude interprets it, applies changes, recalculates derived fields,
    runs scenario comparison, and optionally pushes back to Deltek.
    """
    try:
        rows = extract_planning_data()
        take_snapshot(rows, name="before_ask")

        result = ask(request.prompt, rows)
        updated_rows = result["rows"]

        # Attach scenario comparison (before vs after)
        result["scenario"] = compare(rows, updated_rows)

        if request.push_to_deltek:
            push_result = push_planning_data(updated_rows, override=True)
            result["pushed_to_deltek"] = push_result["success"]
        else:
            result["pushed_to_deltek"] = False

        result.pop("rows", None)
        return result

    except EnvironmentError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI engine error: {str(e)}")


# ---------------------------------------------------------------------------
# Scenario endpoints
# ---------------------------------------------------------------------------

@app.get("/scenario/summary")
def get_scenario_summary():
    """Return aggregate metrics per project (current data)."""
    rows = extract_planning_data()
    return {
        "projects": project_summary(rows),
        "overall":  project_summary(rows),
    }


@app.get("/scenario/violations")
def get_violations():
    """Return all current business rule violations."""
    rows = extract_planning_data()
    violations = flag_violations(rows)
    return {
        "total": len(violations),
        "violations": violations,
    }


@app.post("/scenario/what-if")
def run_what_if(request: WhatIfRequest):
    """
    Run a what-if scenario with manual change actions (no AI).
    Returns before/after comparison without modifying the source data.
    """
    rows = extract_planning_data()
    return what_if(rows, request.changes)


@app.get("/scenario/snapshots")
def get_snapshots():
    """List all saved scenario snapshots."""
    return {"snapshots": list_snapshots()}


# ---------------------------------------------------------------------------
# Upload endpoint
# ---------------------------------------------------------------------------

@app.post("/upload")
async def upload_excel(file: UploadFile = File(...)):
    """
    Upload a new .xlsx planning file to replace the current data source.
    Validates the file is readable before replacing.
    """
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported.")

    content = await file.read()

    # Write to a temp file and validate before overwriting live data
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        rows = read_xlsx(tmp_path)
        if not rows:
            raise ValueError("File contains no data rows.")
    except Exception as e:
        os.unlink(tmp_path)
        raise HTTPException(status_code=400, detail=f"Invalid Excel file: {e}")

    shutil.copy(tmp_path, DATA_PATH)
    os.unlink(tmp_path)

    projects = list(set(r.get("Project Designation", "") for r in rows))
    return {
        "success":  True,
        "rows":     len(rows),
        "projects": sorted(projects),
        "message":  f"Loaded {len(rows)} employee records from {file.filename}.",
    }


# ---------------------------------------------------------------------------
# Validation & push endpoints
# ---------------------------------------------------------------------------

@app.get("/validate")
def validate_current():
    """Validate current planning data against all business rules."""
    rows = extract_planning_data()
    return validate(rows)


@app.post("/push")
def push_to_deltek(request: PushRequest):
    """
    Validate and push a set of rows back to Deltek Vantagepoint.
    Set override=true to force push despite blocking violations.
    If no rows are provided, pushes current data from source file.
    """
    rows = request.rows if request.rows else extract_planning_data()
    result = push_planning_data(rows, override=request.override)
    if not result["success"]:
        raise HTTPException(status_code=422, detail=result)
    return result
