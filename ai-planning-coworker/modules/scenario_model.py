"""
scenario_model.py
Scenario modeling — what-if analysis, snapshots, and before/after comparison.

Responsibilities:
  - Save/restore named snapshots of planning data
  - Apply changes to a copy (non-destructive what-if)
  - Generate structured before/after comparison reports
  - Aggregate project-level metrics (cost, revenue, margin, utilization)
  - Flag business rule violations
"""
import copy

from modules.excel_handler import recalculate, COLUMNS

# In-memory snapshot store: { name → rows }
_snapshots: dict[str, list[dict]] = {}


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------

def take_snapshot(rows: list[dict], name: str = "baseline") -> list[dict]:
    """Save a deep copy of rows under a given name. Returns the copy."""
    _snapshots[name] = copy.deepcopy(rows)
    print(f"[Scenario] Snapshot saved: '{name}' ({len(rows)} employees)")
    return _snapshots[name]


def get_snapshot(name: str = "baseline") -> list[dict] | None:
    """Retrieve a previously saved snapshot by name."""
    snap = _snapshots.get(name)
    return copy.deepcopy(snap) if snap else None


def list_snapshots() -> list[str]:
    """Return the names of all saved snapshots."""
    return list(_snapshots.keys())


# ---------------------------------------------------------------------------
# What-if
# ---------------------------------------------------------------------------

def what_if(rows: list[dict], changes: list[dict]) -> dict:
    """
    Apply a list of changes to a COPY of the data (non-destructive).
    Returns a full comparison report (before vs after).

    changes: [{"employee": "...", "field": "...", "new_value": ...}, ...]
    """
    before = copy.deepcopy(rows)
    after  = copy.deepcopy(rows)

    row_map = {r["Employee Name"]: r for r in after}
    for chg in changes:
        emp   = chg.get("employee", "")
        field = chg.get("field", "")
        val   = chg.get("new_value")
        if emp in row_map and field in COLUMNS:
            row_map[emp][field] = val
            row_map[emp] = recalculate(row_map[emp])

    return compare(before, list(row_map.values()))


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def compare(before: list[dict], after: list[dict]) -> dict:
    """
    Generate a structured before/after comparison report.

    Returns:
      employee_diffs  — per-employee field-level changes
      project_summary — aggregate metrics per project (before vs after)
      overall         — total metrics across all employees (before vs after)
      violations      — business rule violations in the after state
    """
    before_map = {r["Employee Name"]: r for r in before}
    after_map  = {r["Employee Name"]: r for r in after}

    # Employee-level diffs
    employee_diffs = []
    for name, row_after in after_map.items():
        row_before = before_map.get(name, {})
        diffs = {}
        for field in COLUMNS:
            vb = row_before.get(field)
            va = row_after.get(field)
            if str(vb) != str(va):
                entry = {"before": vb, "after": va}
                try:
                    entry["delta"] = round(float(va) - float(vb), 2)
                except (TypeError, ValueError):
                    pass
                diffs[field] = entry
        if diffs:
            employee_diffs.append({
                "employee": name,
                "project":  row_after.get("Project Designation"),
                "changes":  diffs,
            })

    # Project-level aggregates
    proj_summary: dict[str, dict] = {}
    for rows, label in [(before, "before"), (after, "after")]:
        by_proj: dict[str, list] = {}
        for r in rows:
            by_proj.setdefault(r.get("Project Designation", "Unknown"), []).append(r)
        for proj, emps in by_proj.items():
            proj_summary.setdefault(proj, {})[label] = _aggregate(emps)

    return {
        "employee_diffs":  employee_diffs,
        "project_summary": proj_summary,
        "overall": {
            "before": _aggregate(before),
            "after":  _aggregate(after),
        },
        "violations": flag_violations(after),
    }


# ---------------------------------------------------------------------------
# Aggregation & violation checks
# ---------------------------------------------------------------------------

def project_summary(rows: list[dict]) -> dict:
    """Return aggregate metrics grouped by project."""
    by_proj: dict[str, list] = {}
    for r in rows:
        by_proj.setdefault(r.get("Project Designation", "Unknown"), []).append(r)
    return {proj: _aggregate(emps) for proj, emps in sorted(by_proj.items())}


def flag_violations(rows: list[dict]) -> list[dict]:
    """
    Check all rows against business rules.
    Returns a list of violation dicts with employee, rule, detail, severity.
    """
    violations = []
    for r in rows:
        name   = r.get("Employee Name", "Unknown")
        util   = _num(r.get("Current Utilization %", 0))
        cost   = _num(r.get("Est. Total Labor Cost", 0))
        budget = _num(r.get("Project Total Budget", 0))
        margin = _num(r.get("Target Margin %", 0))

        if util > 82:
            violations.append({
                "employee": name,
                "rule":     "Utilization cap exceeded",
                "detail":   f"Utilization = {util}% (cap: 82%)",
                "severity": "High" if util > 88 else "Medium",
            })

        if budget > 0 and cost > budget:
            violations.append({
                "employee": name,
                "rule":     "Labor cost exceeds project budget",
                "detail":   f"Est. Labor Cost ${cost:,.0f} > Budget ${budget:,.0f}",
                "severity": "High",
            })

        if margin < 10:
            violations.append({
                "employee": name,
                "rule":     "Low target margin",
                "detail":   f"Target Margin = {margin}% (min: 10%)",
                "severity": "High" if margin < 0 else "Medium",
            })

    return violations


def _aggregate(rows: list[dict]) -> dict:
    """Compute aggregate planning metrics for a group of employees."""
    total_cost    = sum(_num(r.get("Est. Total Labor Cost", 0)) for r in rows)
    total_revenue = sum(_num(r.get("Revenue Forecast", 0))      for r in rows)
    margins       = [_num(r.get("Target Margin %", 0))          for r in rows]
    utils         = [_num(r.get("Current Utilization %", 0))    for r in rows]

    return {
        "headcount":           len(rows),
        "total_labor_cost":    round(total_cost, 2),
        "total_revenue":       round(total_revenue, 2),
        "net_profit":          round(total_revenue - total_cost, 2),
        "avg_margin_pct":      round(sum(margins) / len(margins), 1) if margins else 0,
        "avg_utilization_pct": round(sum(utils)   / len(utils),   1) if utils   else 0,
    }


def _num(val) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0
