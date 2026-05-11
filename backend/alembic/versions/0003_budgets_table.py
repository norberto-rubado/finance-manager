"""add budgets table

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-11 21:59:55.168434

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "budgets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"],
            name=op.f("fk_budgets_category_id_categories"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name=op.f("fk_budgets_user_id_users"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_budgets")),
    )
    op.create_index(
        "ix_budgets_user_period",
        "budgets",
        ["user_id", "period_year", "period_month"],
        unique=False,
    )
    # category_id NOT NULL 时的唯一:同月同 category 只能一条
    op.create_index(
        "uq_budget_period_category",
        "budgets",
        ["user_id", "period_year", "period_month", "category_id"],
        unique=True,
        postgresql_where=sa.text("category_id IS NOT NULL"),
    )
    # category_id IS NULL 时的唯一:同月总预算只能一条
    op.create_index(
        "uq_budget_period_total",
        "budgets",
        ["user_id", "period_year", "period_month"],
        unique=True,
        postgresql_where=sa.text("category_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_budget_period_total",
        table_name="budgets",
        postgresql_where=sa.text("category_id IS NULL"),
    )
    op.drop_index(
        "uq_budget_period_category",
        table_name="budgets",
        postgresql_where=sa.text("category_id IS NOT NULL"),
    )
    op.drop_index("ix_budgets_user_period", table_name="budgets")
    op.drop_table("budgets")
