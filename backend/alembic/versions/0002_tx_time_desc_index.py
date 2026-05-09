"""tx_time desc index

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-09 00:00:00.000000

把 ix_transactions_user_tx_time 从 (user_id, tx_time) 改成 (user_id, tx_time DESC),
对齐 spec § 4.2 主查询路径要求。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_transactions_user_tx_time", table_name="transactions")
    op.create_index(
        "ix_transactions_user_tx_time",
        "transactions",
        ["user_id", sa.text("tx_time DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_user_tx_time", table_name="transactions")
    op.create_index(
        "ix_transactions_user_tx_time",
        "transactions",
        ["user_id", "tx_time"],
        unique=False,
    )
