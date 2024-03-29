"""adding gel image, info. Again

Revision ID: 70426df72f80
Revises: c4201b0ea9fe
Create Date: 2024-01-30 08:47:22.809841

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '70426df72f80'
down_revision = 'c4201b0ea9fe'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('_wastewaterartic', schema=None) as batch_op:
        batch_op.add_column(sa.Column('gel_image', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('gel_info', sa.JSON(), nullable=True))

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('_wastewaterartic', schema=None) as batch_op:
        batch_op.drop_column('gel_info')
        batch_op.drop_column('gel_image')

    # ### end Alembic commands ###
