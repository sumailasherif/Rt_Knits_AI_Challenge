# ─── RT Knits CMMS — Developer Commands ──────────────────────────────────────
.PHONY: up down build migrate seed seed-reset seed-knowledge lint test

# ── Docker ───────────────────────────────────────────────────────────────────
up:
	docker-compose up -d

down:
	docker-compose down

build:
	docker-compose build --no-cache

# ── Database migrations ───────────────────────────────────────────────────────
migrate:
	cd cmms_backend && alembic upgrade head

migrate-sql:
	cd cmms_backend && alembic upgrade head --sql

# ── Seed data ─────────────────────────────────────────────────────────────────
seed:
	python -m app.db.seed.seed_runner

seed-reset:
	python -m app.db.seed.seed_runner --reset

seed-dry-run:
	python -m app.db.seed.seed_runner --dry-run

seed-knowledge:
	python -m app.db.seed.seed_knowledge

seed-all: seed seed-knowledge

# ── Dev server ────────────────────────────────────────────────────────────────
dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# ── Code quality ──────────────────────────────────────────────────────────────
lint:
	ruff check app/ && black --check app/

format:
	black app/ && ruff check --fix app/

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	pytest tests/ -v --asyncio-mode=auto
