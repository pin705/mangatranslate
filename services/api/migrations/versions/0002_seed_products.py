"""seed default credit packs (placeholder prices; edit in /admin/system)

Revision ID: 0002
Revises: 0001
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

PRODUCTS = [
    ("starter", "Starter", 100, 49_000, 10),
    ("pro", "Pro", 500, 199_000, 20),
    ("power", "Power", 2000, 699_000, 30),
]


def upgrade() -> None:
    products = sa.table("products", sa.column("id", sa.Uuid), sa.column("code", sa.String), sa.column("name", sa.String),
                        sa.column("credits", sa.Integer), sa.column("price_amount", sa.BigInteger),
                        sa.column("currency", sa.String), sa.column("active", sa.Boolean),
                        sa.column("sort_order", sa.Integer))
    op.bulk_insert(products, [
        {"id": uuid.uuid4(), "code": c, "name": n, "credits": cr, "price_amount": p, "currency": "VND",
         "active": True, "sort_order": s} for c, n, cr, p, s in PRODUCTS
    ])


def downgrade() -> None:
    op.execute("DELETE FROM products WHERE code IN ('starter', 'pro', 'power')")
