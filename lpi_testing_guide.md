# LPI Platform — Backend Testing & Verification Guide
> Scope: Authentication → Goal CRUD → Activity Signals  
> Stack: FastAPI · Pydantic v2 · Supabase · pytest  
> Base URL (local): `http://localhost:8000`

---

## Part 1 — Implementation Review Against plan.md

### What Should Be Done By Now (Phase 2 Module 1)

Based on the plan gate criteria:

| Gate Criterion | Expected Status | Verify With |
|---|---|---|
| 10+ seeded goals in DB | ✅ 15 seeded | `GET /goals` count |
| Priority scoring working | ✅ per PR #12 | `GET /goals?sort=priority` |
| SMILE transitions logged | ✅ `log_transition` in store.py | POST to signal endpoint |
| `test_goal_crud.py` 100% green | ⚠️ 4 failing | `pytest -v tests/test_goal_crud.py` |
| All PRs merged | ⚠️ PRs #14, #15 under review | Check GitHub |
| JWT auth working | ⚠️ Aditi implementing | `POST /auth/login` |

### Known Deviations / Risk Areas

1. **JWT auth (Aditi's PR)** — Not yet merged. All protected endpoints will return 401 until this lands. Test auth endpoints separately once merged.
2. **Signals endpoint (`signals.py`)** — Previously returned HTTP 501 (stub). Confirm it's been promoted to real implementation before testing ingestion.
3. **Pydantic v2 migration** — `model_config` fix applied in `config.py`. Watch for any remaining v1-style validators (`@validator`) in models not yet migrated.
4. **Supabase `.delete()` filter requirement** — `clear_all()` uses `.neq()` sentinel. Confirm this pattern holds in any new store methods added via PRs #14/#15.
5. **SMILE phase label** — Confirmed 6-phase lifecycle: `sense → model → intervene → learn → evolve` (plus the corrected 6th phase from PR #17). Verify conftest fixture uses `"reality-emulation"` not `"sense"` as the test phase.

---

## Part 2 — Testing Commands

> **Prerequisites**
> ```bash
> # From the lpi-platform directory
> cd C:\Users\Aadil_islam\Desktop\Projects\Internship\Winniio\lpi-platform
> 
> # Start the server (one terminal)
> uvicorn app.main:app --reload --port 8000
> 
> # Confirm it's alive (second terminal)
> curl http://localhost:8000/health
> # Expected: {"status": "ok"} or {"status": "healthy"}
> ```

---

### 2A — Authentication

#### 1. Register / Create User (if endpoint exists)
```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@lpi.dev", "password": "Test1234!", "name": "Test User"}'
```
**Tests:** User creation flow  
**Expected:** `201 Created` with user object or `{"message": "User created"}`  
**Failure signs:** `422 Unprocessable Entity` (schema mismatch), `500` (Supabase connection issue)

#### 2. Login — Get JWT Token
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@lpi.dev", "password": "Test1234!"}' \
  -v
```
**Tests:** JWT generation  
**Expected:** `200 OK` with `{"access_token": "<jwt>", "token_type": "bearer"}`  
**Failure signs:** `401 Unauthorized`, `404 Not Found` (route missing), `500` (Supabase auth not configured)

#### 3. Capture Token for Subsequent Calls
```bash
# Windows CMD
for /f "tokens=*" %i in ('curl -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d "{\"email\": \"test@lpi.dev\", \"password\": \"Test1234!\"}" ^| python -c "import sys,json; print(json.load(sys.stdin)[\"access_token\"])"') do set TOKEN=%i
echo %TOKEN%

# PowerShell
$resp = Invoke-RestMethod -Uri "http://localhost:8000/auth/login" -Method POST -ContentType "application/json" -Body '{"email":"test@lpi.dev","password":"Test1234!"}'
$TOKEN = $resp.access_token
echo $TOKEN

# Git Bash / WSL
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@lpi.dev","password":"Test1234!"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo $TOKEN
```

#### 4. Access Protected Route with Token
```bash
curl http://localhost:8000/goals \
  -H "Authorization: Bearer $TOKEN"
```
**Tests:** JWT middleware is enforcing auth  
**Expected:** `200 OK` with goals list  
**Failure signs:** `401` with `{"detail": "Not authenticated"}` (token not passed), `403` (token invalid/expired)

#### 5. Token with Invalid Credentials
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@lpi.dev", "password": "WrongPassword"}'
```
**Tests:** Negative auth case  
**Expected:** `401 Unauthorized` with error message  
**Failure signs:** `200 OK` (auth bypass bug), `500` (unhandled exception on bad credentials)

#### 6. Token Refresh (if implemented)
```bash
curl -X POST http://localhost:8000/auth/refresh \
  -H "Authorization: Bearer $TOKEN"
```
**Tests:** Refresh token flow  
**Expected:** New `access_token` in response  
**Failure signs:** `404` (not implemented yet — acceptable if Aditi's PR not merged)

---

### 2B — Goal CRUD Endpoints

Replace `$TOKEN` with your captured token in all commands below.

#### 7. Create a Goal (POST)
```bash
curl -X POST http://localhost:8000/goals \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Complete LPI Module 1",
    "description": "Finish Goal Registry implementation",
    "priority": 1,
    "smile_phase": "sense",
    "due_date": "2026-06-27T00:00:00Z"
  }'
```
**Tests:** Goal creation, Pydantic v2 validation, Supabase insert  
**Expected:** `201 Created` with goal object including `id`, `created_at`  
**Failure signs:**  
- `422` → schema mismatch (check field names vs your GoalCreate model)  
- `500` → Supabase connection or RLS policy blocking insert

#### 8. List All Goals (GET)
```bash
curl http://localhost:8000/goals \
  -H "Authorization: Bearer $TOKEN"
```
**Tests:** Goal retrieval, confirms 15 seeded goals exist  
**Expected:** `200 OK` with array of ≥15 goals  
**Failure signs:** Empty array `[]` (seeding didn't run), `401` (auth middleware issue)

#### 9. Get Goals Count (verify seeding)
```bash
curl http://localhost:8000/goals \
  -H "Authorization: Bearer $TOKEN" \
  | python -c "import sys,json; goals=json.load(sys.stdin); print(f'Total goals: {len(goals)}')"
```
**Expected:** `Total goals: 15` (or more)

#### 10. Get Single Goal by ID (GET)
```bash
# First grab an ID from the list
GOAL_ID="<paste-an-id-from-step-8>"

curl http://localhost:8000/goals/$GOAL_ID \
  -H "Authorization: Bearer $TOKEN"
```
**Tests:** Single-resource fetch, UUID routing  
**Expected:** `200 OK` with single goal object  
**Failure signs:** `404 Not Found` (ID doesn't exist or routing broken)

#### 11. Update a Goal (PUT / PATCH)
```bash
curl -X PATCH http://localhost:8000/goals/$GOAL_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Complete LPI Module 1 — UPDATED",
    "smile_phase": "model"
  }'
```
**Tests:** Partial update, SMILE phase transition  
**Expected:** `200 OK` with updated goal; `smile_phase` changed to `"model"`  
**Failure signs:** `422` (PATCH not accepting partial body — try PUT with full body instead), `404` (wrong ID)

#### 12. Get Goals Sorted by Priority
```bash
curl "http://localhost:8000/goals?sort=priority&order=asc" \
  -H "Authorization: Bearer $TOKEN"
```
**Tests:** Priority scoring feature (Phase 2 gate criterion)  
**Expected:** Goals ordered by priority field ascending  
**Failure signs:** `422` (query param not supported), unordered response

#### 13. Filter Goals by SMILE Phase
```bash
curl "http://localhost:8000/goals?smile_phase=sense" \
  -H "Authorization: Bearer $TOKEN"
```
**Tests:** Filtering by phase  
**Expected:** Only goals in `sense` phase  
**Failure signs:** All goals returned (filter ignored), `422`

#### 14. Delete a Goal (DELETE)
```bash
# Create a throwaway goal first
THROWAWAY=$(curl -s -X POST http://localhost:8000/goals \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "DELETE ME", "priority": 99, "smile_phase": "sense"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Now delete it
curl -X DELETE http://localhost:8000/goals/$THROWAWAY \
  -H "Authorization: Bearer $TOKEN" \
  -v
```
**Tests:** Goal deletion  
**Expected:** `200 OK` or `204 No Content`  
**Failure signs:** `405 Method Not Allowed` (DELETE not implemented), `500`

#### 15. Delete Non-Existent Goal (Negative Case)
```bash
curl -X DELETE http://localhost:8000/goals/00000000-0000-0000-0000-000000000000 \
  -H "Authorization: Bearer $TOKEN"
```
**Expected:** `404 Not Found`  
**Failure signs:** `500` (unhandled exception), `200` (false success)

---

### 2C — Activity Signals Endpoint

#### 16. Check Signals Endpoint is Live
```bash
curl http://localhost:8000/signals \
  -H "Authorization: Bearer $TOKEN"
```
**Tests:** Route exists and responds  
**Expected:** `200 OK` (list of signals) or `405` (GET not allowed — signals may be POST-only)  
**Failure signs:** `501 Not Implemented` → signals.py still stubbed; `404` → route not registered in main.py

#### 17. Ingest a Single Activity Signal (POST)
```bash
curl -X POST http://localhost:8000/signals \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "goal_id": "'$GOAL_ID'",
    "actor": "test@lpi.dev",
    "event_type": "goal_updated",
    "payload": {
      "field_changed": "smile_phase",
      "old_value": "sense",
      "new_value": "model"
    },
    "timestamp": "2026-06-15T10:30:00Z"
  }'
```
**Tests:** Signal ingestion, Timestamp/Actor/Event schema  
**Expected:** `201 Created` with signal ID  
**Failure signs:** `422` (schema mismatch — check your SignalCreate model field names), `404` (goal_id not found if FK enforced)

#### 18. Ingest Signal Without Auth (Negative Case)
```bash
curl -X POST http://localhost:8000/signals \
  -H "Content-Type: application/json" \
  -d '{"actor": "hacker", "event_type": "test"}'
```
**Expected:** `401 Unauthorized`  
**Failure signs:** `201` (auth not enforced on signals endpoint)

#### 19. Retrieve Signals for a Goal
```bash
curl "http://localhost:8000/signals?goal_id=$GOAL_ID" \
  -H "Authorization: Bearer $TOKEN"
```
**Tests:** Signal retrieval and filtering by goal  
**Expected:** Array containing the signal from step 17  
**Failure signs:** Empty array (signal not persisted), `422` (query param not supported)

#### 20. Ingest Signal with Missing Required Fields (Negative Case)
```bash
curl -X POST http://localhost:8000/signals \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"actor": "test@lpi.dev"}'
```
**Expected:** `422 Unprocessable Entity` with validation error details  
**Failure signs:** `500` (Pydantic not catching the missing field — model may have Optional where it should be Required)

#### 21. Verify SMILE Transition Logging
```bash
# Transition a goal through a phase change
curl -X PATCH http://localhost:8000/goals/$GOAL_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"smile_phase": "intervene"}'

# Now check signals were auto-created by log_transition
curl "http://localhost:8000/signals?goal_id=$GOAL_ID" \
  -H "Authorization: Bearer $TOKEN" \
  | python -c "import sys,json; sigs=json.load(sys.stdin); print(f'Signals logged: {len(sigs)}')"
```
**Tests:** `log_transition()` in store.py auto-creates signal on SMILE phase change  
**Expected:** At least 1 signal with `event_type` like `"smile_transition"` or `"phase_changed"`

---

## Part 3 — Addressing the 4 Failing pytest Tests

### Step 1: Identify Which 4 Tests Are Failing

```bash
cd C:\Users\Aadil_islam\Desktop\Projects\Internship\Winniio\lpi-platform

# Run full suite and capture output
pytest tests/ -v --tb=short 2>&1 | tee test_output.txt

# Show only failures
pytest tests/ -v --tb=short 2>&1 | grep -E "FAILED|ERROR"
```

### Step 2: Run Failing Tests in Isolation

Once you know which 4 are failing, run each individually:

```bash
# Pattern: pytest tests/test_file.py::TestClass::test_function -v --tb=long

# Example — if test_goal_crud.py has failures:
pytest tests/test_goal_crud.py -v --tb=long -s

# Run a specific test by name keyword:
pytest tests/ -v -k "test_create_goal" --tb=long -s

# Run with full traceback and print statements:
pytest tests/ -v --tb=long -s --no-header -rN
```

### Step 3: Common Root Causes and Diagnostics

#### Cause A: conftest.py fixture using wrong SMILE phase label

```bash
# Check the fixture
grep -n "sense\|reality-emulation\|smile_phase" tests/conftest.py
```
**Fix:** Ensure `"reality-emulation"` is used as the test phase name (from PR #17 correction). If `"sense"` is hardcoded in a fixture that then gets validated against the enum, it may fail if the enum was updated.

#### Cause B: Pydantic v2 `model_config` not applied everywhere

```bash
# Find any remaining v1-style validators
grep -rn "@validator\|class Config:" app/
```
**Fix:** Replace `class Config: orm_mode = True` with `model_config = ConfigDict(from_attributes=True)`. Replace `@validator` with `@field_validator`.

#### Cause C: Supabase `.delete()` requires at least one filter

```bash
grep -n "\.delete()" app/
```
**Fix:** Any `.delete()` without a `.eq()/.neq()/.in_()` filter will raise an error in supabase-py v2. Use the `.neq("id", "00000000-0000-0000-0000-000000000000")` sentinel for clear_all-style operations.

#### Cause D: Test database isolation (tests polluting each other)

```bash
# Run tests in isolation and compare pass/fail
pytest tests/test_goal_crud.py::test_create_goal -v --tb=long
pytest tests/test_goal_crud.py::test_list_goals -v --tb=long
pytest tests/test_goal_crud.py -v --tb=long  # run together

# If isolated pass but combined fail → fixture teardown issue
```
**Fix:** Ensure each test fixture runs its own `clear_all()` in teardown, and that `clear_all()` itself works (see Cause C).

#### Cause E: HTTP 501 still returned by signals.py

```bash
curl -X POST http://localhost:8000/signals \
  -H "Content-Type: application/json" \
  -d '{"actor":"test","event_type":"test","timestamp":"2026-06-15T00:00:00Z"}' \
  | python -c "import sys,json; r=json.load(sys.stdin); print(r)"
```
If any test POSTs to `/signals` and expects 201 but gets 501, the stub is still active.

### Step 4: Address pytest Warnings

```bash
# See all warnings in detail
pytest tests/ -v --tb=short -W always 2>&1 | grep -A3 "Warning\|DeprecationWarning\|PytestWarning"
```

**Likely Warning Categories:**

| Warning | Category | Fix |
|---|---|---|
| `DeprecationWarning: @validator` | Pydantic v1→v2 | Replace with `@field_validator` |
| `PytestUnraisableExceptionWarning` | Async teardown not awaited | Add `asyncio_mode = "auto"` to pytest.ini or use `pytest-asyncio` properly |
| `ResourceWarning: unclosed socket` | Supabase client not closed | Add `client.close()` or use context manager in fixtures |
| `UserWarning: datetime naive` | Missing timezone on timestamps | Use `datetime.now(timezone.utc)` instead of `datetime.utcnow()` |
| `pytest.PytestConfigWarning` | Missing pytest.ini setting | Add `[pytest] asyncio_mode = auto` to `pytest.ini` or `pyproject.toml` |

**Fix for asyncio warnings (add to `pytest.ini` or `pyproject.toml`):**
```ini
# pytest.ini
[pytest]
asyncio_mode = auto
filterwarnings =
    ignore::DeprecationWarning:pydantic
```

---

## Part 4 — Dataset Evaluation for Activity Signal Testing

### 4A — Loghub (LogPAI)

**Repo:** https://github.com/logpai/loghub  
**Format:** System logs (Apache, Hadoop, Linux) — Timestamp + Component + Message

**Schema Mapping:**
| Loghub Field | Your Signal Field | Notes |
|---|---|---|
| `Timestamp` | `timestamp` | Direct map after ISO 8601 conversion |
| `Component` | `actor` | Maps well — represents the source system/service |
| `EventTemplate` | `event_type` | Use parsed template ID (e.g., `E42`) |
| `Content` | `payload.raw_log` | Store full message in payload |
| N/A | `goal_id` | Must inject synthetically — map by log source |

**Suitability:** ⭐⭐⭐ (3/5) — Structurally perfect for testing ingestion pipelines but semantically irrelevant to intern goals. Best for **volume and format testing**, not semantic validation.

**Download and Transform:**
```bash
# 1. Clone the repo
git clone https://github.com/logpai/loghub.git
cd loghub

# 2. Use the small Apache dataset (~1MB, good for testing)
# File: loghub/Apache/Apache_2k.log

# 3. Parse and transform to signal format
python - << 'EOF'
import json, re
from datetime import datetime

LOG_FILE = "Apache/Apache_2k.log"
GOAL_ID = "YOUR-SEEDED-GOAL-UUID-HERE"  # replace with a real goal ID
OUTPUT_FILE = "signals_apache.json"

signals = []
# Apache log pattern: [Day Mon DD HH:MM:SS YYYY] [level] message
pattern = re.compile(r'\[(.+?)\] \[(\w+)\] (.+)')

with open(LOG_FILE, "r") as f:
    for line in f:
        m = pattern.match(line.strip())
        if m:
            raw_ts, level, message = m.groups()
            try:
                ts = datetime.strptime(raw_ts, "%a %b %d %H:%M:%S %Y").isoformat() + "Z"
            except:
                ts = datetime.utcnow().isoformat() + "Z"
            signals.append({
                "goal_id": GOAL_ID,
                "actor": "apache-server",
                "event_type": f"log_{level.lower()}",
                "timestamp": ts,
                "payload": {"raw_log": message[:500]}
            })

with open(OUTPUT_FILE, "w") as f:
    json.dump(signals[:50], f, indent=2)  # first 50 for testing

print(f"Wrote {min(50, len(signals))} signals to {OUTPUT_FILE}")
EOF

# 4. Send signals to your endpoint
python - << 'EOF'
import json, requests

TOKEN = "YOUR-JWT-TOKEN-HERE"
BASE_URL = "http://localhost:8000"

with open("signals_apache.json") as f:
    signals = json.load(f)

headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
success, fail = 0, 0

for sig in signals:
    r = requests.post(f"{BASE_URL}/signals", json=sig, headers=headers)
    if r.status_code in (200, 201):
        success += 1
    else:
        fail += 1
        print(f"FAILED: {r.status_code} — {r.text[:100]}")

print(f"\nResults: {success} success, {fail} failed out of {len(signals)} signals")
EOF
```

---

### 4B — BPI Challenge 2013 (Volvo IT Incident Management)

**Source:** https://www.tf-pm.org/competitions-awards/bpi-challenge  
**Format:** XES event log — CaseID + Timestamp + Activity + Resource

**Schema Mapping:**
| BPI 2013 Field | Your Signal Field | Notes |
|---|---|---|
| `time:timestamp` | `timestamp` | Direct map — already ISO 8601 |
| `org:resource` | `actor` | Maps directly — person handling the incident |
| `concept:name` (activity) | `event_type` | e.g., `"Accepted"`, `"Wait"`, `"Resolved"` |
| `case:concept:name` (case ID) | `goal_id` | Map 1 case → 1 goal (create goals from unique case IDs) |
| `impact`, `sub_status` | `payload.*` | Rich metadata for payload |

**Suitability:** ⭐⭐⭐⭐⭐ (5/5) — This is the **ideal dataset**. IT incidents moving through statuses directly mirrors how an intern goal moves through SMILE phases. The lifecycle (Open → Accepted → In Progress → Resolved) maps conceptually to (sense → model → intervene → learn → evolve).

**Download and Transform:**
```bash
# 1. Download from tf-pm.org (manual step — requires accepting terms)
# Navigate to: https://www.tf-pm.org/competitions-awards/bpi-challenge
# Find BPI Challenge 2013 and download the XES file
# File will be something like: VINST.xes or BPI_Challenge_2013_incidents.xes

# 2. Install XES parser
pip install pm4py

# 3. Parse XES and transform to signal format
python - << 'EOF'
import json
import pm4py
from datetime import datetime, timezone

XES_FILE = "BPI_Challenge_2013_incidents.xes"   # adjust filename
OUTPUT_FILE = "signals_bpi2013.json"
BASE_URL = "http://localhost:8000"
TOKEN = "YOUR-JWT-TOKEN-HERE"

# Load the XES file
log = pm4py.read_xes(XES_FILE)

signals = []
case_to_goal = {}  # we'll create one goal per unique case

import requests
headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# Create goals for unique cases (first 10 cases only for testing)
cases = list(log.groupby("case:concept:name"))[:10]

for case_id, trace in cases:
    # Create a goal for this incident case
    goal_resp = requests.post(f"{BASE_URL}/goals", json={
        "title": f"Incident Case {case_id}",
        "description": f"Volvo IT incident tracked from BPI 2013",
        "priority": 3,
        "smile_phase": "sense"
    }, headers=headers)
    
    if goal_resp.status_code in (200, 201):
        goal_id = goal_resp.json()["id"]
        case_to_goal[case_id] = goal_id
        print(f"Created goal {goal_id} for case {case_id}")
    else:
        print(f"Failed to create goal for case {case_id}: {goal_resp.text}")

# Build signals from events
for case_id, trace in cases:
    goal_id = case_to_goal.get(case_id)
    if not goal_id:
        continue
    for _, event in trace.iterrows():
        ts = event.get("time:timestamp")
        if hasattr(ts, "isoformat"):
            ts_str = ts.isoformat()
        else:
            ts_str = datetime.now(timezone.utc).isoformat()
        
        signals.append({
            "goal_id": goal_id,
            "actor": str(event.get("org:resource", "unknown")),
            "event_type": str(event.get("concept:name", "unknown_event")).lower().replace(" ", "_"),
            "timestamp": ts_str,
            "payload": {
                "impact": str(event.get("impact", "")),
                "sub_status": str(event.get("sub_status", "")),
                "case_id": str(case_id)
            }
        })

with open(OUTPUT_FILE, "w") as f:
    json.dump(signals, f, indent=2)

print(f"\nTransformed {len(signals)} events from {len(cases)} cases")
print(f"Written to {OUTPUT_FILE}")
EOF

# 4. Send all signals in batch
python - << 'EOF'
import json, requests

TOKEN = "YOUR-JWT-TOKEN-HERE"
BASE_URL = "http://localhost:8000"

with open("signals_bpi2013.json") as f:
    signals = json.load(f)

headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
success, fail = 0, 0

for i, sig in enumerate(signals):
    r = requests.post(f"{BASE_URL}/signals", json=sig, headers=headers)
    if r.status_code in (200, 201):
        success += 1
    else:
        fail += 1
        if fail <= 5:  # only print first 5 failures
            print(f"[{i}] FAILED {r.status_code}: {r.text[:150]}")

print(f"\nFinal: {success}/{len(signals)} signals ingested successfully")
EOF
```

---

### 4C — BPI Challenge 2020 (Travel Administration)

**Source:** https://www.tf-pm.org/resources/logs  
**Format:** XES event log — travel requests moving through approval/rejection states

**Schema Mapping:**
| BPI 2020 Field | Your Signal Field | Notes |
|---|---|---|
| `time:timestamp` | `timestamp` | Direct map |
| `org:resource` | `actor` | Approver/submitter name |
| `concept:name` | `event_type` | e.g., `"Declaration SUBMITTED"`, `"Declaration APPROVED"` |
| `case:concept:name` | `goal_id` | One travel request = one goal |
| `case:Amount` | `payload.amount` | Budget metadata |
| `case:org:role` | `payload.role` | Submitter role |

**Suitability:** ⭐⭐⭐⭐ (4/5) — Very relevant since travel request approval mirrors intern goal approval/progression. Useful for testing multi-step workflows and rejection/re-submission loops.

**Download and Transform:**
```bash
# 1. Download from tf-pm.org (manual — select BPI Challenge 2020)
# Multiple sublogs available: Prepaid Travel Costs, Declaration with pre-approval, etc.
# Recommended: "RequestForPayment" sublog (smaller, cleaner)

pip install pm4py

python - << 'EOF'
import json, pm4py, requests
from datetime import datetime, timezone

XES_FILE = "RequestForPayment.xes"   # adjust to your downloaded filename
OUTPUT_FILE = "signals_bpi2020.json"
TOKEN = "YOUR-JWT-TOKEN-HERE"
BASE_URL = "http://localhost:8000"

log = pm4py.read_xes(XES_FILE)
headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

signals = []
case_to_goal = {}
cases = list(log.groupby("case:concept:name"))[:10]

for case_id, trace in cases:
    amount = trace.get("case:Amount", [None]).iloc[0] if "case:Amount" in trace.columns else None
    goal_resp = requests.post(f"{BASE_URL}/goals", json={
        "title": f"Travel Request {case_id}",
        "description": f"BPI 2020 travel administration case",
        "priority": 2,
        "smile_phase": "sense",
        "metadata": {"amount": str(amount) if amount else "unknown"}
    }, headers=headers)
    
    if goal_resp.status_code in (200, 201):
        goal_id = goal_resp.json()["id"]
        case_to_goal[case_id] = goal_id

for case_id, trace in cases:
    goal_id = case_to_goal.get(case_id)
    if not goal_id:
        continue
    for _, event in trace.iterrows():
        ts = event.get("time:timestamp")
        ts_str = ts.isoformat() if hasattr(ts, "isoformat") else datetime.now(timezone.utc).isoformat()
        event_name = str(event.get("concept:name", "unknown")).lower().replace(" ", "_")
        
        signals.append({
            "goal_id": goal_id,
            "actor": str(event.get("org:resource", "system")),
            "event_type": event_name,
            "timestamp": ts_str,
            "payload": {
                "case_id": str(case_id),
                "role": str(event.get("org:role", ""))
            }
        })

with open(OUTPUT_FILE, "w") as f:
    json.dump(signals, f, indent=2)

print(f"Generated {len(signals)} signals for {len(cases)} travel cases")
EOF
```

---

## Part 5 — Complete Testing Checklist (Sequential)

Run these in order. Each section depends on the previous.

### Phase 0: Environment Check
- [ ] Server running: `curl http://localhost:8000/health` → 200
- [ ] Supabase local running: `npx supabase status` → shows running services
- [ ] 15 goals seeded: `curl http://localhost:8000/goals | python -c "import sys,json; print(len(json.load(sys.stdin)))"`

### Phase 1: Authentication
- [ ] **Step 2** — POST `/auth/login` → 200 with JWT
- [ ] **Step 3** — Token captured in `$TOKEN`
- [ ] **Step 4** — GET `/goals` with token → 200
- [ ] **Step 5** — POST `/auth/login` with wrong password → 401

### Phase 2: Goal CRUD
- [ ] **Step 7** — POST `/goals` → 201, goal created
- [ ] **Step 8** — GET `/goals` → 200, ≥15 goals
- [ ] **Step 9** — Count = 15+
- [ ] **Step 10** — GET `/goals/:id` → 200, correct goal
- [ ] **Step 11** — PATCH `/goals/:id` → 200, updated
- [ ] **Step 12** — GET `/goals?sort=priority` → 200, ordered
- [ ] **Step 13** — GET `/goals?smile_phase=sense` → filtered
- [ ] **Step 14** — DELETE throwaway goal → 204/200
- [ ] **Step 15** — DELETE non-existent → 404

### Phase 3: Activity Signals
- [ ] **Step 16** — GET `/signals` → 200 or 405 (not 501 or 404)
- [ ] **Step 17** — POST `/signals` with valid body → 201
- [ ] **Step 18** — POST `/signals` without auth → 401
- [ ] **Step 19** — GET `/signals?goal_id=X` → contains step 17's signal
- [ ] **Step 20** — POST `/signals` missing fields → 422
- [ ] **Step 21** — PATCH goal phase → signals auto-created by `log_transition`

### Phase 4: pytest
- [ ] `pytest tests/ -v` → identify the 4 failing tests
- [ ] Run each failing test in isolation with `--tb=long -s`
- [ ] Fix conftest.py fixture phase label if needed
- [ ] Fix Pydantic v2 validators if needed
- [ ] Verify `.delete()` uses `.neq()` filter
- [ ] `pytest tests/ -v` → all green ✅

### Phase 5: Dataset Testing (optional, for Demo Day evidence)
- [ ] Download Apache 2K log from Loghub
- [ ] Run Loghub transform script → `signals_apache.json` (50 signals)
- [ ] Send to `/signals` endpoint → ≥45/50 success rate
- [ ] Download BPI 2013 XES
- [ ] Install `pm4py`: `pip install pm4py`
- [ ] Run BPI 2013 script → goals created + signals ingested
- [ ] Verify via GET `/signals?goal_id=X` for each created goal
- [ ] Validate signal count matches expected event count from XES

---

## Quick Reference: Signal Schema

```json
{
  "goal_id": "uuid-string",
  "actor": "user@email.com or system-name",
  "event_type": "snake_case_event_name",
  "timestamp": "2026-06-15T10:30:00Z",
  "payload": {
    "any": "additional",
    "context": "here"
  }
}
```

## Quick Reference: SMILE Phases (6-phase lifecycle)
```
sense → model → intervene → learn → evolve → reality-emulation
```
(Use `reality-emulation` in test fixtures per PR #17 correction)
