"""add personal_rating and personal_notes to book

Revision ID: a1b2c3d4e5f6
Revises: 5dbf1c0fd07d
Create Date: 2026-06-29 00:01:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = '5dbf1c0fd07d'
branch_labels = None
depends_on = None


def upgrade():
    # Idempotent: the app's startup db.create_all() may already have added them.
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('book')}
    with op.batch_alter_table('book') as batch_op:
        if 'personal_rating' not in existing:
            batch_op.add_column(sa.Column('personal_rating', sa.Float(), nullable=True))
        if 'personal_notes' not in existing:
            batch_op.add_column(sa.Column('personal_notes', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('book') as batch_op:
        batch_op.drop_column('personal_notes')
        batch_op.drop_column('personal_rating')
