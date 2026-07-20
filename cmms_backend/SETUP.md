# RT Knits Agentic CMMS — Complete Setup & Activation Guide

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | https://python.org |
| Docker Desktop | latest | https://docker.com |
| Git | any | https://git-scm.com |
| ngrok | any | https://ngrok.com (for local WhatsApp testing) |

---

## Step 1 — Clone & Enter the Project

```bash
cd "C:\Users\User\Desktop\Rt_Knits_AI Challenge\cmms_backend"
```

---

## Step 2 — Create & Activate a Python Virtual Environment

```bash
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
```

---

## Step 3 — Install All Dependencies

```bash
pip install -e ".[dev]"
```

This installs all runtime + dev packages from pyproject.toml including:
- fastapi, uvicorn, sqlalchemy, asyncpg, alembic
- langgraph, langchain, openai
- chromadb, apscheduler, structlog
- pandas, openpyxl (for Excel seed data)
- pytest, aiosqlite, httpx (for tests)

---

## Step 4 — Configure Environment Variables

Edit `.env` in the `cmms_backend/` directory. Fill in ALL of these:

```env
# Required — get from platform.openai.com
OPENAI_API_KEY=sk-YOUR-REAL-KEY-HERE

# Required — get from developers.facebook.com > Your App > WhatsApp > API Setup
WHATSAPP_VERIFY_TOKEN=choose-any-secret-string     # you decide this
WHATSAPP_ACCESS_TOKEN=EAAxxxxxxxxxxxxxxx            # Meta temporary/permanent token
WHATSAPP_PHONE_NUMBER_ID=12345678901234             # from Meta dashboard
WHATSAPP_APP_SECRET=abc123def456                    # Meta App Dashboard > Settings > Basic

# PostgreSQL — leave as-is if using Docker Compose
DATABASE_URL=postgresql+asyncpg://cmms_user:supersecret@localhost:5432/rtknits_cmms
DATABASE_URL_SYNC=postgresql://cmms_user:supersecret@localhost:5432/rtknits_cmms
```

---

## Step 5 — Start Infrastructure Services (Docker)

```bash
# Start PostgreSQL + ChromaDB (from cmms_backend/ folder)
docker-compose up -d db chromadb

# Verify both are running
docker-compose ps
```

Expected output:
```
rtknits_postgres   running   0.0.0.0:5432->5432/tcp
rtknits_chroma     running   0.0.0.0:8001->8000/tcp
```

---

## Step 6 — Run Database Migrations

```bash
# From cmms_backend/ directory with venv active
alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, Initial schema
```

---

## Step 7 — Seed the Database

Place your Excel files in `cmms_backend/data/`:
- `Assets.xlsx`
- `Technicians.xlsx`
- `Tasks.xlsx`

Then run:
```bash
python -m app.db.seed.seed_runner
```

To reset and re-seed:
```bash
python -m app.db.seed.seed_runner --reset
```

To embed knowledge documents into ChromaDB:
```bash
python -m app.db.seed.seed_knowledge
```

---

## Step 8 — Run the Tests (Verify Everything Works)

```bash
pytest -v
```

All tests use SQLite in-memory — no external services needed.

Expected output:
```
tests/test_health.py::test_root PASSED
tests/test_health.py::test_health_endpoint_ok PASSED
tests/test_webhook_verification.py::test_webhook_verify_success PASSED
... (40+ tests) ...
40 passed in X.XXs
```

---

## Step 9 — Start the FastAPI Server

```bash
# Development mode (auto-reload on file changes)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Visit:
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health
- ReDoc: http://localhost:8000/redoc

---

## Step 10 — Expose to WhatsApp via ngrok

Open a second terminal:

```bash
ngrok http 8000
```

Copy the HTTPS forwarding URL, e.g.:
```
https://abc123.ngrok-free.app
```

---

## Step 11 — Configure Meta WhatsApp Webhook

1. Go to https://developers.facebook.com
2. Your App → WhatsApp → Configuration → Webhooks
3. Set **Callback URL**: `https://abc123.ngrok-free.app/webhook`
4. Set **Verify Token**: same value as `WHATSAPP_VERIFY_TOKEN` in your `.env`
5. Click **Verify and Save**
6. Subscribe to: `messages`

If verification succeeds you'll see a ✅ in the Meta dashboard.

---

## Step 12 — Full Docker Deployment (Production)

To run everything in Docker including the API:

```bash
docker-compose up -d
```

This starts:
- PostgreSQL (port 5432)
- ChromaDB (port 8001)
- FastAPI API (port 8000) — automatically runs migrations on startup
- ngrok tunnel (port 4040 for the web UI)

Set `NGROK_AUTHTOKEN` in `.env` for a persistent ngrok URL.

---

## Quick Command Reference

```bash
# Start services
docker-compose up -d

# Run migrations
alembic upgrade head

# Seed database
python -m app.db.seed.seed_runner

# Seed knowledge base
python -m app.db.seed.seed_knowledge

# Start API (development)
uvicorn app.main:app --reload --port 8000

# Run all tests
pytest -v

# Run specific test
pytest tests/test_webhook_verification.py -v

# Check API health
curl http://localhost:8000/health

# Manually trigger nightly planning
curl -X POST "http://localhost:8000/api/v1/planning/trigger?force=true"

# View logs (Docker)
docker-compose logs -f api
```

---

## Common Errors & Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `connection refused 5432` | PostgreSQL not running | `docker-compose up -d db` |
| `connection refused 8001` | ChromaDB not running | `docker-compose up -d chromadb` |
| `OPENAI_API_KEY not set` | Missing env var | Fill `.env` with real key |
| `webhook verification failed` | Token mismatch | Ensure `WHATSAPP_VERIFY_TOKEN` matches Meta dashboard exactly |
| `alembic: can't locate revision` | Wrong cwd | Run from `cmms_backend/` directory |
| `ModuleNotFoundError: app` | venv not activated or not installed | Run `pip install -e .` from `cmms_backend/` |
| `422 Unprocessable Entity` on POST | Missing required field | Check `/docs` for required fields |

---

## Architecture Summary

```
WhatsApp User
     │
     ▼
Meta Cloud API
     │  POST /webhook
     ▼
FastAPI (uvicorn)
     │
     ▼
LangGraph Orchestrator
     │
     ├── Rating Gate (blocks if unrated WOs)
     ├── Intake Agent (GPT-4o + Whisper + Vision)
     ├── Knowledge Agent (ChromaDB vector search)
     ├── Triage Agent (P0/P1/P2 classification)
     └── Dispatch Agent (assign technician)
          │
          ├── PostgreSQL (work orders, assignments, feedback)
          ├── ChromaDB (SOPs, manuals, history)
          └── APScheduler (nightly planning + P0 escalation)
```
