"""
excel_handler.py
Read and write Vantagepoint Project.xlsx using Python standard library only.
No openpyxl or pandas required — uses zipfile + xml.etree.ElementTree.
"""
import zipfile
import xml.etree.ElementTree as ET
from io import BytesIO

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NSP = {"ns": NS}

COLUMNS = [
    "Employee Name", "Role", "Labor Rate", "Skills", "Project Designation",
    "Date Hired", "Tenureship", "Project Total Budget", "Project Timeline",
    "Allocation %", "Est. Hours/Week", "Burden Rate %", "Fully Burdened Rate",
    "Est. Total Labor Cost", "Billing Rate", "Target Margin %",
    "Revenue Forecast", "Current Utilization %", "Risk Level", "Project Phase",
]

NUMERIC_COLS = {
    "Project Total Budget", "Allocation %", "Est. Hours/Week", "Burden Rate %",
    "Est. Total Labor Cost", "Target Margin %", "Revenue Forecast",
    "Current Utilization %", "Date Hired",
}


def col_letter(n: int) -> str:
    """Convert 0-indexed column number to Excel column letter (A, B, ... Z, AA, ...)."""
    result = ""
    n += 1
    while n > 0:
        n -= 1
        result = chr(65 + n % 26) + result
        n //= 26
    return result


def parse_rate(rate_str: str) -> float:
    """Parse '$45/hr' or '$58.5/hr' → 45.0"""
    return float(str(rate_str).replace("$", "").replace("/hr", "").strip())


def parse_timeline(timeline_str: str) -> float:
    """Parse '2 years' or '1 year' → 2.0"""
    return float(str(timeline_str).replace("years", "").replace("year", "").strip())


def recalculate(row: dict) -> dict:
    """
    Recalculate all derived fields from base values.
    Call this after any AI-applied change to keep data consistent.
    """
    try:
        labor_rate    = parse_rate(row["Labor Rate"])
        burden_pct    = float(row["Burden Rate %"]) / 100
        allocation_pct = float(row["Allocation %"]) / 100
        hrs_per_week  = float(row["Est. Hours/Week"])
        timeline_yrs  = parse_timeline(row["Project Timeline"])
        billing_rate  = parse_rate(row["Billing Rate"])
        utilization   = float(row["Current Utilization %"])

        burdened   = round(labor_rate * (1 + burden_pct), 2)
        total_hrs  = hrs_per_week * 52 * timeline_yrs * allocation_pct
        labor_cost = round(burdened * total_hrs, 2)
        margin     = round((billing_rate - burdened) / billing_rate * 100, 1)
        revenue    = round(billing_rate * total_hrs, 2)
        risk       = "High" if utilization > 88 else ("Medium" if utilization > 80 else "Low")

        row["Fully Burdened Rate"]    = f"${burdened}/hr"
        row["Est. Total Labor Cost"]  = labor_cost
        row["Target Margin %"]        = margin
        row["Revenue Forecast"]       = revenue
        row["Risk Level"]             = risk
    except Exception as e:
        print(f"[excel_handler] Warning: recalculate failed for {row.get('Employee Name')}: {e}")

    return row


def read_xlsx(path: str) -> list[dict]:
    """
    Read all employee rows from the Excel file.
    Returns a list of dicts keyed by column name.
    """
    with zipfile.ZipFile(path) as z:
        ss_root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        strings = [t.text or "" for t in ss_root.findall(".//ns:t", NSP)]

        s_root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))

    raw_rows = []
    for row in s_root.findall(".//ns:row", NSP):
        cells = []
        for c in row.findall("ns:c", NSP):
            t = c.get("t")
            v = c.find("ns:v", NSP)
            if v is not None and v.text is not None:
                cells.append(strings[int(v.text)] if t == "s" else v.text)
            else:
                cells.append("")
        raw_rows.append(cells)

    if not raw_rows:
        return []

    headers = raw_rows[0]
    rows = []
    for raw in raw_rows[1:]:
        row = {}
        for i, h in enumerate(headers):
            val = raw[i] if i < len(raw) else ""
            if h in NUMERIC_COLS:
                try:
                    row[h] = float(val) if "." in str(val) else int(val)
                except (ValueError, TypeError):
                    row[h] = val
            else:
                row[h] = val
        rows.append(row)

    return rows


def write_xlsx(path: str, rows: list[dict]) -> None:
    """Write employee rows back to the Excel file, preserving column order."""
    data = [COLUMNS] + [[row.get(col, "") for col in COLUMNS] for row in rows]
    with open(path, "wb") as f:
        f.write(_build_xlsx(data))


def _build_xlsx(data: list[list]) -> bytes:
    """Build a valid .xlsx file from a 2D list of values."""
    strings, str_map = [], {}

    def si(s: str) -> int:
        if s not in str_map:
            str_map[s] = len(strings)
            strings.append(s)
        return str_map[s]

    def is_numeric(val) -> bool:
        if isinstance(val, (int, float)):
            return True
        try:
            float(str(val))
            return True
        except (ValueError, TypeError):
            return False

    sheet_rows = []
    for ri, row in enumerate(data):
        cells = []
        for ci, val in enumerate(row):
            if val is None or val == "":
                continue
            ref = f"{col_letter(ci)}{ri + 1}"
            if is_numeric(val) and not str(val).startswith("$"):
                cells.append(f'<c r="{ref}"><v>{val}</v></c>')
            else:
                idx = si(str(val))
                cells.append(f'<c r="{ref}" t="s"><v>{idx}</v></c>')
        sheet_rows.append(f'<row r="{ri + 1}">{"".join(cells)}</row>')

    ss_items = "".join(
        f'<si><t xml:space="preserve">{s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")}</t></si>'
        for s in strings
    )

    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets><sheet name=\"Sheet1\" sheetId=\"1\" r:id=\"rId1\"/></sheets>"
            "</workbook>"
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
            "</Relationships>"
        ),
        "xl/worksheets/sheet1.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(sheet_rows)}</sheetData>'
            "</worksheet>"
        ),
        "xl/sharedStrings.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<sst xmlns="{NS}" count="{len(strings)}" uniqueCount="{len(strings)}">'
            f"{ss_items}</sst>"
        ),
    }

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)
    return buf.getvalue()
