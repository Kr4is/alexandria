"""initial schema

Revision ID: 5dbf1c0fd07d
Revises:
Create Date: 2026-06-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '5dbf1c0fd07d'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('password_hash', sa.String(length=128), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
    )
    op.create_table(
        'book',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('google_books_id', sa.String(length=50), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('authors', sa.String(length=200), nullable=True),
        sa.Column('thumbnail', sa.String(length=500), nullable=True),
        sa.Column('isbn', sa.String(length=20), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('page_count', sa.Integer(), nullable=True),
        sa.Column('categories', sa.String(length=200), nullable=True),
        sa.Column('published_year', sa.String(length=4), nullable=True),
        sa.Column('language', sa.String(length=10), nullable=True),
        sa.Column('average_rating', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('date_added', sa.DateTime(), nullable=True),
        sa.Column('date_finished', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('google_books_id'),
    )


def downgrade():
    op.drop_table('book')
    op.drop_table('user')
