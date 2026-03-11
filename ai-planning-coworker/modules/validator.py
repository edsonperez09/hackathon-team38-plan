"""
validator.py
Validation gate — enforces all business rules before any push to Deltek.

Violations are separated into two tiers:
  blocking  — must be resolved (or explicitly overridden) before push is allowed
  warnings  — noted in the response but do not block push
"""

# Configurable thresholds
UTILIZATION_CAP      = 82    # % — warn above this
HIGH_RISK_THRESHOLD  = 88    # % — block above this (Risk Level = High)
MIN_MARGIN_PCT       = 0     # % — block if margin goes negative
WARN_MARGIN_PCT      = 10    # % — warn if margin drops below this


def validate(rows: list[dict], override: bool = False) -> dict:
    """
    Validate all employee rows against business rules.

    Args:
        rows     : current planning data (list of dicts)
        override : if True, blocking violations are downgraded to warnings
                   and the push is allowed to proceed

    Returns dict with:
        valid    : bool — True if push is allowed
        blocking : list of critical violations
        warnings : list of non-critical concerns
        override : echo of the override flag
        summary  : human-readable validation result
    """
    blocking: list[dict] = []
    warnings: list[dict] = []

    for r in rows:
        name   = r.get("Employee Name", "Unknown")
        util   = _num(r.get("Current Utilization %", 0))
        margin = _num(r.get("Target Margin %", 0))
        cost   = _num(r.get("Est. Total Labor Cost", 0))
        budget = _num(r.get("Project Total Budget", 0))
        risk   = r.get("Risk Level", "Low")

        # ── Utilization ──────────────────────────────────────────────────
        if risk == "High" or util > HIGH_RISK_THRESHOLD:
            blocking.append(_issue(
                name, "High risk — utilization exceeds threshold",
                f"Utilization = {util}% (block threshold: {HIGH_RISK_THRESHOLD}%)",
                "blocking",
            ))
        elif util > UTILIZATION_CAP:
            warnings.append(_issue(
                name, "Utilization above cap",
                f"Utilization = {util}% (cap: {UTILIZATION_CAP}%)",
                "warning",
            ))

        # ── Margin ───────────────────────────────────────────────────────
        if margin < MIN_MARGIN_PCT:
            blocking.append(_issue(
                name, "Negative target margin",
                f"Target Margin = {margin}% (must be ≥ {MIN_MARGIN_PCT}%)",
                "blocking",
            ))
        elif margin < WARN_MARGIN_PCT:
            warnings.append(_issue(
                name, "Low target margin",
                f"Target Margin = {margin}% (recommended min: {WARN_MARGIN_PCT}%)",
                "warning",
            ))

        # ── Budget ───────────────────────────────────────────────────────
        if budget > 0 and cost > budget:
            warnings.append(_issue(
                name, "Labor cost exceeds project budget",
                f"Est. Labor Cost ${cost:,.0f} > Budget ${budget:,.0f}",
                "warning",
            ))

        # ── Burden rate consistency ───────────────────────────────────────
        try:
            from modules.excel_handler import parse_rate
            labor      = parse_rate(str(r.get("Labor Rate", "0")))
            burden_pct = _num(r.get("Burden Rate %", 0)) / 100
            expected   = round(labor * (1 + burden_pct), 2)
            actual     = parse_rate(str(r.get("Fully Burdened Rate", "0")))
            if abs(actual - expected) > 0.01:
                warnings.append(_issue(
                    name, "Fully Burdened Rate is out of sync",
                    f"Expected ${expected}/hr but found ${actual}/hr — recalculate before push",
                    "warning",
                ))
        except Exception:
            pass

    is_valid = (len(blocking) == 0) or override

    if len(blocking) == 0:
        summary = f"Validation passed — {len(warnings)} warning(s)."
    elif override:
        summary = (f"Push allowed via override — {len(blocking)} blocking issue(s) bypassed, "
                   f"{len(warnings)} warning(s).")
    else:
        summary = (f"Validation FAILED — {len(blocking)} blocking issue(s) must be resolved "
                   f"before push. Use override=true to force.")

    return {
        "valid":    is_valid,
        "blocking": blocking,
        "warnings": warnings,
        "override": override,
        "summary":  summary,
    }


def _issue(employee: str, rule: str, detail: str, severity: str) -> dict:
    return {"employee": employee, "rule": rule, "detail": detail, "severity": severity}


def _num(val) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0
