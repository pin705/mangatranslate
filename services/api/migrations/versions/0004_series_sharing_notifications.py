"""series + glossary, pixel-based page credits, product bonus, referrals, e-mail login codes, share links,
notifications

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "series",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("source_lang", sa.String(32), nullable=False),
        sa.Column("target_lang", sa.String(32), nullable=False),
        sa.Column("glossary", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_series_user", "series", ["user_id", "updated_at"])
    op.add_column("jobs", sa.Column("series_id", sa.Uuid(), sa.ForeignKey("series.id", ondelete="SET NULL")))
    op.create_index("ix_jobs_series_id", "jobs", ["series_id"])
    op.add_column("pages", sa.Column("credits", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("products", sa.Column("bonus_credits", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("referral_code", sa.String(16), unique=True))
    op.add_column("users", sa.Column("referred_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")))

    op.drop_constraint("credit_transactions_kind_check", "credit_transactions", type_="check")
    op.create_check_constraint("credit_transactions_kind_check", "credit_transactions",
                               "kind IN ('signup_bonus', 'purchase', 'reserve', 'release', 'refund', 'admin_grant', "
                               "'admin_revoke', 'referral')")
    op.drop_constraint("email_tokens_purpose_check", "email_tokens", type_="check")
    op.create_check_constraint("email_tokens_purpose_check", "email_tokens", "purpose IN ('verify', 'reset', 'login')")

    op.create_table(
        "share_links",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hint", sa.String(8), nullable=False),
        sa.Column("folder", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("data", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("dedupe_key", sa.String(200), unique=True),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notifications_user", "notifications", ["user_id", "created_at"])


def downgrade() -> None:
    raise NotImplementedError("forward-only; restore from backup (docs/DISASTER_RECOVERY.md)")
