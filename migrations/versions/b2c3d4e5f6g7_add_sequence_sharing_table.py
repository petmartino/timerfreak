"""add sequence sharing table

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-30

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6g7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Create sequence_share table
    op.create_table('sequence_share',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sequence_id', sa.String(length=20), nullable=False),
    sa.Column('share_token', sa.String(length=50), nullable=False),
    sa.Column('is_public', sa.Boolean(), nullable=False, default=True),
    sa.Column('allow_copy', sa.Boolean(), nullable=False, default=True),
    sa.Column('view_count', sa.Integer(), nullable=False, default=0),
    sa.Column('copy_count', sa.Integer(), nullable=False, default=0),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['sequence_id'], ['sequence.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sequence_share_share_token'), 'sequence_share', ['share_token'], unique=True)
    op.create_index(op.f('ix_sequence_share_sequence_id'), 'sequence_share', ['sequence_id'], unique=False)
    op.create_index(op.f('ix_sequence_share_created_at'), 'sequence_share', ['created_at'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_sequence_share_created_at'), table_name='sequence_share')
    op.drop_index(op.f('ix_sequence_share_sequence_id'), table_name='sequence_share')
    op.drop_index(op.f('ix_sequence_share_share_token'), table_name='sequence_share')
    op.drop_table('sequence_share')
