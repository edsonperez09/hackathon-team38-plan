# Challenge 4: AI-Powered Planning Coworker
**Led by:** Dinakar Hituvalli (CPTO)

---

## Overview

Build an AI-powered planning assistant that connects Deltek Vantagepoint planning data to an Excel layer, allows planners to manipulate data via natural language using Claude (Anthropic) or OpenAI, runs scenario modeling, and pushes validated changes back to Deltek — preserving all integrations, validations, and business rules.

---

## The Flow

```
Deltek Planning → Excel Layer → AI Engine → Excel Output → Back to Deltek
```

| Step | Component | Description |
|------|-----------|-------------|
| 1 | **Deltek Planning** | Extract revenue, cost, resource & capacity |
| 2 | **Excel Layer** | Smart transform with formulas & validation |
| 3 | **AI Engine** | Claude / OpenAI — natural language prompts + scenario modeling |
| 4 | **Excel Output** | Modified plan with constraint checking |
| 5 | **Back to Deltek** | Push validated changes, preserve integrations |

---

## Application Architecture

### Tech Stack
- **Backend:** Python (FastAPI)
- **AI Engine:** Anthropic Claude API (`claude-sonnet-4-6`)
- **Excel Processing:** Python `zipfile` + `xml.etree.ElementTree` (no external dependencies)
- **Deltek Integration:** Deltek Vantagepoint REST API
- **Frontend:** Simple web UI (HTML/JS) or CLI for demo

### Folder Structure
```
ai-planning-coworker/
├── main.py                  # FastAPI app entry point
├── .env                     # API keys (ANTHROPIC_API_KEY, DELTEK credentials)
├── requirements.txt
├── modules/
│   ├── deltek_client.py     # Deltek API: extract & push data
│   ├── excel_handler.py     # Read/write/transform Excel files
│   ├── ai_engine.py         # Claude API: natural language → actions
│   ├── scenario_model.py    # Scenario modeling logic & constraint checks
│   └── validator.py         # Business rules & validation before push
├── data/
│   └── Vantagepoint Project.xlsx  # Source planning data (20 columns)
└── tests/
    └── test_scenarios.py
```

---

## Module Breakdown

### 1. `deltek_client.py` — Deltek Integration
- **Extract:** Pull revenue, cost, resource, capacity data from Deltek Vantagepoint API
- **Push:** Send validated modified plan back to Deltek
- **Preserve:** Maintain all existing integrations (Costpoint, etc.)

### 2. `excel_handler.py` — Excel Layer
- Read/write `.xlsx` files using Python `zipfile` + `xml.etree.ElementTree` (no pip dependencies)
- Load and parse all 20 columns from `Vantagepoint Project.xlsx`
- Recalculate derived fields after any AI-applied change:
  - `Fully Burdened Rate` = Labor Rate × (1 + Burden Rate %)
  - `Est. Total Labor Cost` = Fully Burdened Rate × (Est. Hours/Week × 52 × Timeline × Allocation %)
  - `Target Margin %` = (Billing Rate − Fully Burdened Rate) / Billing Rate × 100
  - `Revenue Forecast` = Billing Rate × Total Hours
  - `Risk Level` = High if Utilization > 88%, Medium if > 80%, else Low
- Export modified Excel after AI changes

### 3. `ai_engine.py` — AI Engine (Claude)
- Accept natural language prompt from planner
- Send prompt + serialized Excel data (all 20 columns) as context to Claude API
- Parse Claude's response into structured JSON change actions (e.g., update field, recalculate column)
- Example system prompt:
  ```
  You are a planning assistant for Deltek Vantagepoint.
  You have access to employee planning data with the following columns:
  Employee Name, Role, Labor Rate, Skills, Project Designation, Date Hired,
  Tenureship, Project Total Budget, Project Timeline, Allocation %,
  Est. Hours/Week, Burden Rate %, Fully Burdened Rate, Est. Total Labor Cost,
  Billing Rate, Target Margin %, Revenue Forecast, Current Utilization %,
  Risk Level, Project Phase.

  Interpret the user's instruction and return a JSON list of changes to apply.
  Always recalculate dependent fields after any change.
  Enforce: Utilization cap = 82%, Risk = High if >88%, Medium if >80%.
  ```

### 4. `scenario_model.py` — Scenario Modeling
- Apply AI-generated changes to the in-memory data rows
- Recalculate all dependent fields after each change:
  - Burden rate chain: Labor Rate → Fully Burdened Rate → Est. Total Labor Cost
  - Profitability chain: Billing Rate → Target Margin % → Revenue Forecast
  - Risk chain: Current Utilization % → Risk Level
- Support "what-if" branching (save scenario snapshots before applying changes)
- Flag employees whose `Est. Total Labor Cost` exceeds `Project Total Budget`

### 5. `validator.py` — Constraint Checking
- Enforce business rules before pushing back to Deltek:
  - `Current Utilization %` must not exceed **82%** cap
  - `Est. Total Labor Cost` must not exceed `Project Total Budget`
  - `Target Margin %` must remain positive after changes
  - `Risk Level` = High blocks push unless explicitly overridden
  - Skill constraints respected when reassigning employees across projects
  - `Burden Rate %` must be recalculated any time Labor Rate changes

---

## Data Schema (Vantagepoint Project.xlsx)

| # | Column | Type | Description |
|---|--------|------|-------------|
| 1 | Employee Name | String | Full name |
| 2 | Role | String | Job title |
| 3 | Labor Rate | String | e.g. `$45/hr` |
| 4 | Skills | String | Comma-separated skill list |
| 5 | Project Designation | String | Project Atlas / Helios / Titan |
| 6 | Date Hired | Number | Excel date serial |
| 7 | Tenureship | String | e.g. `6 years` |
| 8 | Project Total Budget | Number | Total budget allocated |
| 9 | Project Timeline | String | e.g. `2 years` |
| 10 | Allocation % | Number | % of time on this project (default 80%) |
| 11 | Est. Hours/Week | Number | Hours worked per week (default 40) |
| 12 | Burden Rate % | Number | Overhead % on top of labor (default 30%) |
| 13 | Fully Burdened Rate | String | Labor Rate × 1.30, e.g. `$58.5/hr` |
| 14 | Est. Total Labor Cost | Number | Burdened Rate × Total Hours |
| 15 | Billing Rate | String | Client charge rate, e.g. `$70/hr` |
| 16 | Target Margin % | Number | (Billing − Burdened) / Billing × 100 |
| 17 | Revenue Forecast | Number | Billing Rate × Total Hours |
| 18 | Current Utilization % | Number | Overall workload across all projects |
| 19 | Risk Level | String | Low / Medium / High |
| 20 | Project Phase | String | Planning / In Progress |

### Current Risk Flags (from data)
| Employee | Project | Utilization | Risk |
|---|---|---|---|
| Priya Sharma | Project Helios | 92% | High |
| Li Wei | Project Titan | 84% | Medium |
| Carlos Ramirez | Project Titan | 83% | Medium |
| Edison Macabuhay | Project Atlas | 85% | Medium |

---

## Detailed Use Cases

### Use Case 1: Revenue Forecasting
> "Show revenue impact if we increase billing rate for Project Atlas by 15%"
- AI updates `Billing Rate` for Edison, Maria, John
- Recalculates `Target Margin %` and `Revenue Forecast` for each
- Flags if margin drops below threshold
- Pushes results to Vantagepoint

### Use Case 2: Resource Optimization
> "Rebalance Project Titan to keep utilization under 82%"
- AI identifies Li Wei (84%), Carlos Ramirez (83%) as over-threshold
- Reduces `Allocation %` or redistributes hours
- Recalculates `Est. Total Labor Cost` and `Risk Level`
- Returns optimized resource plan

### Use Case 3: Cost Scenario Modeling
> "Increase burden rate to 35% for all Project Helios employees"
- AI updates `Burden Rate %` for Priya Sharma and Ahmed Khan
- Recalculates `Fully Burdened Rate`, `Est. Total Labor Cost`, `Target Margin %`
- Validates cost doesn't exceed `Project Total Budget`
- Sends updated cost plan to Costpoint

### Other Example Prompts Planners Can Use
- "Who is over-utilized across all projects?"
- "What happens to Project Titan's margin if we replace Emily Wong with a $55/hr developer?"
- "Optimize staffing for Project Helios, keep utilization under 82%"
- "Show total revenue forecast across all projects"
- "What if we extend Project Atlas timeline by 1 year?"

---

## Implementation Phases

### Phase 1 — Data Layer (Day 1)
- [x] Define 20-column data schema (Employee, Role, Labor Rate, Skills, Project, Budget, Timeline, Allocation, Hours, Burden Rate, Fully Burdened Rate, Labor Cost, Billing Rate, Margin, Revenue Forecast, Utilization, Risk, Phase)
- [x] Populate `Vantagepoint Project.xlsx` with 10 employees across 3 projects
- [x] Implement Excel read/write using Python `zipfile` + `xml.etree.ElementTree`
- [ ] Connect to Deltek Vantagepoint API (or keep mock data for demo)

### Phase 2 — AI Engine (Day 1–2)
- [ ] Set up Anthropic Claude API integration
- [ ] Design system prompt with business rules as context
- [ ] Parse Claude responses into structured change actions (JSON)
- [ ] Apply changes to Excel data

### Phase 3 — Scenario Modeling (Day 2)
- [ ] Implement recalculation engine (utilization, margin, P&L)
- [ ] Add constraint checker (utilization cap, budget limits)
- [ ] Support scenario snapshots / comparison

### Phase 4 — Push Back to Deltek (Day 2)
- [ ] Validate all changes against business rules
- [ ] Push validated data back to Deltek via API
- [ ] Preserve existing integrations (Costpoint, etc.)

### Phase 5 — Demo UI (Day 2–3)
- [ ] Simple web interface: upload Excel or connect live
- [ ] Text input for natural language prompts
- [ ] Display before/after scenario comparison
- [ ] Show validation results before push

---

## Key Constraints & Business Rules
- Utilization cap: **82%** (configurable) — Risk = Medium above 80%, High above 88%
- `Fully Burdened Rate` must recalculate whenever `Labor Rate` or `Burden Rate %` changes
- `Est. Total Labor Cost` must not exceed `Project Total Budget`
- `Target Margin %` must remain positive after any billing or labor change
- Skill constraints must be respected when reassigning employees across projects
- `Risk Level = High` blocks Deltek push unless explicitly overridden by planner
- All dependent fields must be recalculated before any push to Deltek

---

## Environment Variables (.env)
```
ANTHROPIC_API_KEY=sk-ant-...
DELTEK_BASE_URL=https://your-vantagepoint-instance.com/api
DELTEK_USERNAME=...
DELTEK_PASSWORD=...
```

---

## Demo Script (Hackathon Presentation)
1. Show `Vantagepoint Project.xlsx` loaded — 10 employees, 20 columns, 3 projects
2. Highlight current risk flags: Priya Sharma (92%), Li Wei (84%), Carlos Ramirez (83%)
3. Type: *"Rebalance Project Titan to keep utilization under 82%"*
4. Show Claude interpreting the prompt → JSON change actions generated
5. Show `scenario_model.py` applying changes + recalculating Fully Burdened Rate, Margin, Risk Level
6. Show `validator.py` confirming all utilization values now ≤ 82%
7. Show updated Excel with before/after comparison
8. Push validated changes back to Deltek — show confirmation
