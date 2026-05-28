# LPI Platform — Life Programmable Interface

Goal registry, activity signals, recommendation engine — powered by SMILE methodology.

## Quick Start
```bash
pip install -e ".[dev]"
make test  # smoke + SMILE tests pass immediately
make run   # FastAPI on port 8000
```

## Local dev (Windows + Supabase local)

See `DEVELOPMENT.md` for a PowerShell-first setup:

```powershell
.\scripts\dev.ps1 -Setup
.\scripts\dev.ps1 -RunApi
.\scripts\dev.ps1 -Test
```

## Architecture
```
Module 1: Goals  ->  Priority scoring + SMILE phase tracking
Module 2: Signals ->  Events from all streams (Boardy, DataPro+, VSAB, etc.)
Module 3: Recommendations ->  Goals + Signals -> Top 3 actions with SMILE reasoning
```

## Team
| Name | Role | Tests to pass |
|------|------|---------------|
| **Jaivardhan** | Lead, recommendations | `test_recommendations.py` |
| Aditi | Data ingestion | Signal ingestion, proxy data |
| Adil | API endpoints | `test_goal_crud.py`, `test_activity_signals.py` |
| Jahanvi | Frontend | UI components |
| Yashika | Testing + SMILE | `test_smile.py`, coverage |
| Ankit | LLM integration | Explanation generation |
