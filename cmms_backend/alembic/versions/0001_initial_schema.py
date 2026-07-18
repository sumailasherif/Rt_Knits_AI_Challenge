"""Initial schema — all CMMS tables

Revision ID: 0001
Revises:
Create Date: 2025-07-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enable pgvector extension (needed for future embedding columns) ────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── department ─────────────────────────────────────────────────────────────
    op.create_table(
        "department",
        sa.Column("dept_id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
    )
    op.create_index("ix_department_name", "department", ["name"], unique=True)

    # ── technician ─────────────────────────────────────────────────────────────
    op.create_table(
        "technician",
        sa.Column("tech_id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column(
            "trade",
            sa.Enum("Mechanical", "Electrical", "Civil", "Plumbing", "IT", "General",
                    name="trade_enum"),
            nullable=False,
        ),
        sa.Column(
            "pool",
            sa.Enum("LTKTech", "DyeTech", "General", name="pool_enum"),
            nullable=False,
            server_default="General",
        ),
        sa.Column("phone_number", sa.String(20), nullable=False),
        sa.Column("on_shift", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("reward_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("max_concurrent_jobs", sa.Integer, nullable=False, server_default="2"),
    )
    op.create_index("ix_technician_phone_number", "technician", ["phone_number"], unique=True)
    op.create_index("ix_technician_trade", "technician", ["trade"])
    op.create_index("ix_technician_pool", "technician", ["pool"])

    # ── requester ──────────────────────────────────────────────────────────────
    op.create_table(
        "requester",
        sa.Column("requester_id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("phone_number", sa.String(20), nullable=False),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column(
            "dept_id",
            sa.String(36),
            sa.ForeignKey("department.dept_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
    )
    op.create_index("ix_requester_phone_number", "requester", ["phone_number"], unique=True)
    op.create_index("ix_requester_dept_id", "requester", ["dept_id"])

    # ── asset ──────────────────────────────────────────────────────────────────
    op.create_table(
        "asset",
        sa.Column("asset_id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("model_number", sa.String(100), nullable=True),
        sa.Column("serial_number", sa.String(100), nullable=True),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column(
            "dept_id",
            sa.String(36),
            sa.ForeignKey("department.dept_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("required_trade", sa.String(80), nullable=True),
        sa.Column("is_critical", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("ix_asset_name", "asset", ["name"])
    op.create_index("ix_asset_category", "asset", ["category"])
    op.create_index("ix_asset_serial_number", "asset", ["serial_number"], unique=True)

    # ── knowledge_doc ──────────────────────────────────────────────────────────
    op.create_table(
        "knowledge_doc",
        sa.Column("doc_id", sa.String(36), primary_key=True),
        sa.Column(
            "asset_id",
            sa.String(36),
            sa.ForeignKey("asset.asset_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_type",
            sa.Enum("manual", "SOP", "history", name="source_type_enum"),
            nullable=False,
        ),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("raw_content", sa.Text, nullable=True),
        sa.Column("embedding_ref", sa.String(200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_knowledge_doc_asset_id", "knowledge_doc", ["asset_id"])

    # ── task_request ───────────────────────────────────────────────────────────
    op.create_table(
        "task_request",
        sa.Column("request_id", sa.String(36), primary_key=True),
        sa.Column(
            "requester_id",
            sa.String(36),
            sa.ForeignKey("requester.requester_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            sa.String(36),
            sa.ForeignKey("asset.asset_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("raw_text", sa.Text, nullable=True),
        sa.Column("photo_url", sa.String(500), nullable=True),
        sa.Column("audio_transcription", sa.Text, nullable=True),
        sa.Column("structured_fault", sa.Text, nullable=True),
        sa.Column("whatsapp_message_id", sa.String(200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_task_request_requester_id", "task_request", ["requester_id"])
    op.create_index("ix_task_request_asset_id", "task_request", ["asset_id"])
    op.create_index(
        "ix_task_request_whatsapp_message_id", "task_request", ["whatsapp_message_id"], unique=True
    )

    # ── work_order ─────────────────────────────────────────────────────────────
    op.create_table(
        "work_order",
        sa.Column("wo_id", sa.String(36), primary_key=True),
        sa.Column(
            "request_id",
            sa.String(36),
            sa.ForeignKey("task_request.request_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "asset_id",
            sa.String(36),
            sa.ForeignKey("asset.asset_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "priority",
            sa.Enum("P0", "P1", "P2", name="priority_enum"),
            nullable=False,
            server_default="P2",
        ),
        sa.Column(
            "status",
            sa.Enum(
                "Open", "Queued", "Assigned", "InProgress", "Paused", "Completed", "Cancelled",
                name="wo_status_enum",
            ),
            nullable=False,
            server_default="Open",
        ),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("required_trade", sa.String(80), nullable=True),
        sa.Column("assigned_techs", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("estimated_minutes", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_work_order_priority", "work_order", ["priority"])
    op.create_index("ix_work_order_status", "work_order", ["status"])
    op.create_index("ix_work_order_request_id", "work_order", ["request_id"])
    op.create_index("ix_work_order_asset_id", "work_order", ["asset_id"])

    # ── assignment ─────────────────────────────────────────────────────────────
    op.create_table(
        "assignment",
        sa.Column("assignment_id", sa.String(36), primary_key=True),
        sa.Column(
            "wo_id",
            sa.String(36),
            sa.ForeignKey("work_order.wo_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tech_id",
            sa.String(36),
            sa.ForeignKey("technician.tech_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completion_notes", sa.Text, nullable=True),
        sa.Column("is_preempted", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_index("ix_assignment_wo_id", "assignment", ["wo_id"])
    op.create_index("ix_assignment_tech_id", "assignment", ["tech_id"])

    # ── daily_plan ─────────────────────────────────────────────────────────────
    op.create_table(
        "daily_plan",
        sa.Column("plan_id", sa.String(36), primary_key=True),
        sa.Column(
            "tech_id",
            sa.String(36),
            sa.ForeignKey("technician.tech_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("plan_date", sa.Date, nullable=False),
        sa.Column("items", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("conflict_note", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_daily_plan_tech_id", "daily_plan", ["tech_id"])
    op.create_index("ix_daily_plan_plan_date", "daily_plan", ["plan_date"])

    # ── feedback ───────────────────────────────────────────────────────────────
    op.create_table(
        "feedback",
        sa.Column("feedback_id", sa.String(36), primary_key=True),
        sa.Column(
            "wo_id",
            sa.String(36),
            sa.ForeignKey("work_order.wo_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requester_id",
            sa.String(36),
            sa.ForeignKey("requester.requester_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_feedback_rating_range"),
    )
    op.create_index("ix_feedback_wo_id", "feedback", ["wo_id"], unique=True)
    op.create_index("ix_feedback_requester_id", "feedback", ["requester_id"])


def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_table("daily_plan")
    op.drop_table("assignment")
    op.drop_table("work_order")
    op.drop_table("task_request")
    op.drop_table("knowledge_doc")
    op.drop_table("asset")
    op.drop_table("requester")
    op.drop_table("technician")
    op.drop_table("department")
    # Drop custom enums
    for enum_name in [
        "source_type_enum", "priority_enum", "wo_status_enum", "trade_enum", "pool_enum"
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
    op.execute("DROP EXTENSION IF EXISTS vector")
