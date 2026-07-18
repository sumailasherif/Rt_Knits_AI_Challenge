"""
Main seed entry point.

Usage (from cmms_backend/ root):
    python -m app.db.seed.seed_runner
    python -m app.db.seed.seed_runner --reset    # drops all rows first
    python -m app.db.seed.seed_runner --dry-run  # validate only, no DB writes

The script reads three Excel files from settings.seed_data_dir:
    Assets.xlsx        → department + asset rows
    Technicians.xlsx   → technician rows
    Tasks.xlsx         → requester + task_request + work_order rows

All IDs are deterministic UUIDs derived from source identifiers so the
script is safely re-runnable (INSERT ... ON CONFLICT DO NOTHING).
"""
import argparse
import asyncio
import sys
from pathlib import Path

import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.seed.loaders import (
    load_assets_xlsx,
    load_technicians_xlsx,
    load_tasks_xlsx,
)
from app.db.seed.writers import (
    upsert_departments,
    upsert_assets,
    upsert_technicians,
    upsert_requesters,
    upsert_task_requests,
    upsert_work_orders,
    reset_seed_tables,
)
from app.db.session import db_context

configure_logging()
log = structlog.get_logger(__name__)
settings = get_settings()


async def run_seed(reset: bool = False, dry_run: bool = False) -> None:
    data_dir = Path(settings.seed_data_dir)

    assets_path = data_dir / "Assets.xlsx"
    techs_path = data_dir / "Technicians.xlsx"
    tasks_path = data_dir / "Tasks.xlsx"

    missing = [p for p in (assets_path, techs_path, tasks_path) if not p.exists()]
    if missing:
        log.error("seed_files_missing", files=[str(p) for p in missing])
        sys.exit(1)

    log.info("seed_loading_files", data_dir=str(data_dir))

    # ── Parse Excel files into plain dicts ────────────────────────────────────
    departments, assets = load_assets_xlsx(assets_path)
    technicians = load_technicians_xlsx(techs_path)
    requesters, task_requests, work_orders = load_tasks_xlsx(tasks_path)

    log.info(
        "seed_parsed",
        departments=len(departments),
        assets=len(assets),
        technicians=len(technicians),
        requesters=len(requesters),
        task_requests=len(task_requests),
        work_orders=len(work_orders),
    )

    if dry_run:
        log.info("seed_dry_run_complete — no DB writes performed")
        return

    async with db_context() as db:
        if reset:
            log.warning("seed_reset_tables — deleting all seed rows")
            await reset_seed_tables(db)

        log.info("seed_writing_departments")
        await upsert_departments(db, departments)

        log.info("seed_writing_assets")
        await upsert_assets(db, assets)

        log.info("seed_writing_technicians")
        await upsert_technicians(db, technicians)

        log.info("seed_writing_requesters")
        await upsert_requesters(db, requesters)

        log.info("seed_writing_task_requests")
        await upsert_task_requests(db, task_requests)

        log.info("seed_writing_work_orders")
        await upsert_work_orders(db, work_orders)

    log.info("seed_complete")


def main() -> None:
    parser = argparse.ArgumentParser(description="RT Knits CMMS database seeder")
    parser.add_argument("--reset", action="store_true", help="Delete all rows before seeding")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no DB writes")
    args = parser.parse_args()
    asyncio.run(run_seed(reset=args.reset, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
