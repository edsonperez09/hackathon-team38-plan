"""
ai_engine.py
AI Engine — Claude integration for natural language planning manipulation.

Flow:
  NL prompt + current rows → Claude API → JSON change actions → apply + recalculate → updated rows
"""
import json
import os
import re

from anthropic import Anthropic
from dotenv import load_dotenv

from modules.excel_handler import recalculate, COLUMNS

load_dotenv()

SYSTEM_PROMPT = f"""You are an AI planning assistant for Deltek Vantagepoint.
You help planners manipulate workforce and project planning data using natural language.

The planning data has these exact columns:
{", ".join(COLUMNS)}

Business rules to enforce:
- Current Utilization % cap is 82%. Warn if any change causes it to exceed this.
- Risk Level = "High" if Utilization > 88%, "Medium" if > 80%, "Low" otherwise.
- Fully Burdened Rate     = Labor Rate × (1 + Burden Rate % / 100)
- Est. Total Labor Cost   = Fully Burdened Rate × (Est. Hours/Week × 52 × Timeline Years × Allocation % / 100)
- Target Margin %         = (Billing Rate − Fully Burdened Rate) / Billing Rate × 100
- Revenue Forecast        = Billing Rate × Total Hours
- Target Margin % must remain positive. Warn if it drops below 10%.
- Est. Total Labor Cost must not exceed Project Total Budget. Warn if it does.

You MUST respond with a valid JSON object only — no markdown, no extra text:
{{
  "understanding": "brief restatement of what the user wants",
  "changes": [
    {{
      "employee": "exact employee name from the data",
      "field": "exact column name from the list above",
      "new_value": "new value in same format as existing data"
    }}
  ],
  "summary": "human-readable summary of all changes made",
  "warnings": ["any business rule violations or concerns"]
}}

Format rules:
- Rates use format: "$50/hr"
- Numeric fields (Allocation %, Utilization %, etc.) use plain numbers: 85
- If no changes are needed, return an empty changes array with a helpful summary.
"""


def _rows_to_context(rows: list[dict]) -> str:
    """Serialize employee rows into a readable block for Claude's context."""
    lines = ["Current Vantagepoint planning data:\n"]
    for r in rows:
        lines.append(f"Employee: {r['Employee Name']}")
        for col in COLUMNS[1:]:
            lines.append(f"  {col}: {r.get(col, 'N/A')}")
        lines.append("")
    return "\n".join(lines)


def _apply_changes(rows: list[dict], changes: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Apply a list of JSON change actions to the data rows.
    Recalculates derived fields for every modified employee.
    Returns (updated_rows, list_of_skipped_warnings).
    """
    row_map = {r["Employee Name"]: r for r in rows}
    skipped = []

    for change in changes:
        emp   = change.get("employee", "")
        field = change.get("field", "")
        val   = change.get("new_value")

        if emp not in row_map:
            skipped.append(f"Employee not found: '{emp}'")
            continue
        if field not in COLUMNS:
            skipped.append(f"Unknown column '{field}' for {emp}")
            continue

        old = row_map[emp].get(field)
        row_map[emp][field] = val
        print(f"  [AI] {emp} | {field}: {old!r} → {val!r}")

        row_map[emp] = recalculate(row_map[emp])

    return list(row_map.values()), skipped


def ask(prompt: str, rows: list[dict]) -> dict:
    """
    Send a natural language prompt and current planning data to Claude.

    Returns a dict with:
      - rows        : updated employee list with recalculated fields
      - changes     : list of change actions Claude produced
      - understanding: Claude's restatement of the request
      - summary     : human-readable summary of what changed
      - warnings    : list of business rule concerns
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set. Add it to your .env file:\n"
            "  ANTHROPIC_API_KEY=sk-ant-..."
        )

    client = Anthropic(api_key=api_key)
    context = _rows_to_context(rows)
    user_message = f"{context}\nInstruction: {prompt}"

    print(f'\n[AI] Prompt → "{prompt}"')

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    print(f"[AI] Response received ({len(raw)} chars)")

    # Parse JSON — fallback regex extraction if Claude wraps it in text
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            result = json.loads(match.group())
        else:
            raise ValueError(f"Claude returned non-JSON response:\n{raw[:300]}")

    changes = result.get("changes", [])
    updated_rows, skipped = _apply_changes(rows, changes)

    if skipped:
        result.setdefault("warnings", []).extend(skipped)

    result["rows"]    = updated_rows
    result["changes"] = changes
    return result
