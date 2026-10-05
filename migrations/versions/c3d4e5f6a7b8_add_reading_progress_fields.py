"""add current_page, date_started, format and shelves to book

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-07-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None

NEW_COLUMNS = (
    ('current_page', sa.Integer()),
    ('date_started', sa.DateTime()),
    ('format', sa.String(length=20)),
    ('shelves', sa.String(length=200)),
)


def upgrade():
    # Idempotent: the app's startup db.create_all() may already have added them.
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('book')}
    with op.batch_alter_table('book') as batch_op:
        for name, type_ in NEW_COLUMNS:
            if name not in existing:
                batch_op.add_column(sa.Column(name, type_, nullable=True))
    # Books already in the library started when they were added (wish-list books haven't started).
    op.execute(
        "UPDATE book SET date_started = date_added "
        "WHERE date_started IS NULL AND COALESCE(status, '') != 'tbr'"
    )


def downgrade():
    with op.batch_alter_table('book') as batch_op:
        for name, _ in reversed(NEW_COLUMNS):
            batch_op.drop_column(name)
