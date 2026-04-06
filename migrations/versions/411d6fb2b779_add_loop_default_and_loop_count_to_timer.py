"""Add loop_default and loop_count to Timer

Revision ID: 411d6fb2b779
Revises: b2c3d4e5f6g7
Create Date: 2026-04-04 09:01:07.007062

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '411d6fb2b779'
down_revision = 'b2c3d4e5f6g7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('timer', schema=None) as batch_op:
        batch_op.add_column(sa.Column('loop_default', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('loop_count', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('timer', schema=None) as batch_op:
        batch_op.drop_column('loop_count')
        batch_op.drop_column('loop_default')
