"""Adding in Equipment

Revision ID: 36a47d8837ca
Revises: 238c3c3e5863
Create Date: 2023-12-12 09:16:09.559753

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '36a47d8837ca'
down_revision = '238c3c3e5863'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('_equipment',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=True),
    sa.Column('nickname', sa.String(length=64), nullable=True),
    sa.Column('asset_number', sa.String(length=16), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('_submissiontype_equipment',
    sa.Column('equipment_id', sa.INTEGER(), nullable=False),
    sa.Column('submission_id', sa.INTEGER(), nullable=False),
    sa.Column('uses', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['equipment_id'], ['_equipment.id'], ),
    sa.ForeignKeyConstraint(['submission_id'], ['_submission_types.id'], ),
    sa.PrimaryKeyConstraint('equipment_id', 'submission_id')
    )
    op.create_table('_equipment_submissions',
    sa.Column('equipment_id', sa.INTEGER(), nullable=False),
    sa.Column('submission_id', sa.INTEGER(), nullable=False),
    sa.Column('comments', sa.String(length=1024), nullable=True),
    sa.ForeignKeyConstraint(['equipment_id'], ['_equipment.id'], ),
    sa.ForeignKeyConstraint(['submission_id'], ['_submissions.id'], ),
    sa.PrimaryKeyConstraint('equipment_id', 'submission_id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('_equipment_submissions')
    op.drop_table('_submissiontype_equipment')
    op.drop_table('_equipment')
    # ### end Alembic commands ###
