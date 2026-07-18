"""
Imports every model so Alembic autogenerate can detect all tables.
Import this module in alembic/env.py as:  from app.db.base import Base
"""
from app.db.base_class import Base  # noqa: F401

# ── Force-import every model module so metadata is populated ─────────────────
from app.db.models.department import Department  # noqa: F401
from app.db.models.requester import Requester  # noqa: F401
from app.db.models.asset import Asset  # noqa: F401
from app.db.models.knowledge_doc import KnowledgeDoc  # noqa: F401
from app.db.models.task_request import TaskRequest  # noqa: F401
from app.db.models.work_order import WorkOrder  # noqa: F401
from app.db.models.technician import Technician  # noqa: F401
from app.db.models.daily_plan import DailyPlan  # noqa: F401
from app.db.models.assignment import Assignment  # noqa: F401
from app.db.models.feedback import Feedback  # noqa: F401
