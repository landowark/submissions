"""tweaking submission sample association

Revision ID: 70d5a751f579
Revises: 97392dda5436
Create Date: 2024-01-25 13:39:34.163501

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '70d5a751f579'
down_revision = '97392dda5436'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('_submissionsampleassociation', schema=None) as batch_op:
        batch_op.alter_column('id',
               existing_type=sa.INTEGER(),
               nullable=False)
        batch_op.create_unique_constraint("ssa_id_unique", ['id'])

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('_submissionsampleassociation', schema=None) as batch_op:
        batch_op.drop_constraint("ssa_id_unique", type_='unique')
        batch_op.alter_column('id',
               existing_type=sa.INTEGER(),
               nullable=False)

    # ### end Alembic commands ###
