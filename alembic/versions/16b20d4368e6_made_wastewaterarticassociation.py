"""Made WastewaterArticAssociation

Revision ID: 16b20d4368e6
Revises: d2b094cfa308
Create Date: 2024-06-13 12:16:48.385516

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '16b20d4368e6'
down_revision = 'd2b094cfa308'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('_wastewaterarticassociation',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('source_plate', sa.String(length=16), nullable=True),
    sa.Column('source_plate_number', sa.INTEGER(), nullable=True),
    sa.Column('source_well', sa.String(length=8), nullable=True),
    sa.Column('ct', sa.String(length=8), nullable=True),
    sa.ForeignKeyConstraint(['id'], ['_submissionsampleassociation.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # with op.batch_alter_table('_submissionsampleassociation', schema=None) as batch_op:
    #     batch_op.create_unique_constraint(None, ['id'])
    #
    # with op.batch_alter_table('_submissiontipsassociation', schema=None) as batch_op:
    #     batch_op.alter_column('role_name',
    #            existing_type=sa.INTEGER(),
    #            type_=sa.String(length=32),
    #            existing_nullable=True)

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('_submissiontipsassociation', schema=None) as batch_op:
        batch_op.alter_column('role_name',
               existing_type=sa.String(length=32),
               type_=sa.INTEGER(),
               existing_nullable=True)

    with op.batch_alter_table('_submissionsampleassociation', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='unique')

    op.drop_table('_wastewaterarticassociation')
    # ### end Alembic commands ###
