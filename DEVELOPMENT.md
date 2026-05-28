## Local dev (FastAPI + Supabase local + pytest)

### Prerequisites
- **Python**: 3.11+
- **Docker Desktop**: running
- **Supabase CLI**: installed (provides `supabase` command)

### Setup (Windows / PowerShell)

```powershell
.\scripts\dev.ps1 -Setup
```

### Start Supabase local

```powershell
.\scripts\supabase.ps1 -Start
```

This will:
- run `supabase start`
- write/update `.env` with local `SUPABASE_URL` + `SUPABASE_KEY` (anon key)

### Run the API

```powershell
.\scripts\dev.ps1 -RunApi
```

API should be on `http://127.0.0.1:8000` and health check at `/health`.

### Run tests

```powershell
.\scripts\dev.ps1 -Test
```

### Notes
- `.env.example` shows the required environment variables.
- If you prefer `make`, `make install`, `make run`, `make test` are available (works best with a Unix-like shell or a Make install on Windows).

