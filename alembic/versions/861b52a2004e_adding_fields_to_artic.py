"""Adding fields to Artic

Revision ID: 861b52a2004e
Revises: b744e8a452fd
Create Date: 2024-06-05 13:35:19.012337

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = '861b52a2004e'
down_revision = 'b744e8a452fd'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('_alembic_tmp__basicsubmission')
    # with op.batch_alter_table('_submissionsampleassociation', schema=None) as batch_op:
    #     batch_op.create_unique_constraint(None, ['id'])

    with op.batch_alter_table('_wastewaterartic', schema=None) as batch_op:
        batch_op.add_column(sa.Column('artic_date', sa.TIMESTAMP(), nullable=True))
        batch_op.add_column(sa.Column('ngs_date', sa.TIMESTAMP(), nullable=True))
        batch_op.add_column(sa.Column('gel_date', sa.TIMESTAMP(), nullable=True))
        batch_op.add_column(sa.Column('gel_barcode', sa.String(length=16), nullable=True))

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('_wastewaterartic', schema=None) as batch_op:
        batch_op.drop_column('gel_barcode')
        batch_op.drop_column('gel_date')
        batch_op.drop_column('ngs_date')
        batch_op.drop_column('artic_date')

    # with op.batch_alter_table('_submissionsampleassociation', schema=None) as batch_op:
    #     batch_op.drop_constraint(None, type_='unique')

    op.create_table('_alembic_tmp__basicsubmission',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('rsl_plate_num', sa.VARCHAR(length=32), nullable=False),
    sa.Column('submitter_plate_num', sa.VARCHAR(length=127), nullable=True),
    sa.Column('submitted_date', sa.TIMESTAMP(), nullable=True),
    sa.Column('submitting_lab_id', sa.INTEGER(), nullable=True),
    sa.Column('sample_count', sa.INTEGER(), nullable=True),
    sa.Column('extraction_kit_id', sa.INTEGER(), nullable=True),
    sa.Column('submission_type_name', sa.VARCHAR(), nullable=True),
    sa.Column('technician', sa.VARCHAR(length=64), nullable=True),
    sa.Column('reagents_id', sa.VARCHAR(), nullable=True),
    sa.Column('extraction_info', sqlite.JSON(), nullable=True),
    sa.Column('run_cost', sa.FLOAT(), nullable=True),
    sa.Column('signed_by', sa.VARCHAR(length=32), nullable=True),
    sa.Column('comment', sqlite.JSON(), nullable=True),
    sa.Column('submission_category', sa.VARCHAR(length=64), nullable=True),
    sa.Column('cost_centre', sa.VARCHAR(length=64), nullable=True),
    sa.Column('contact_id', sa.INTEGER(), nullable=True),
    sa.ForeignKeyConstraint(['contact_id'], ['_contact.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['extraction_kit_id'], ['_kittype.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['reagents_id'], ['_reagent.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['submission_type_name'], ['_submissiontype.name'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['submitting_lab_id'], ['_organization.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('rsl_plate_num'),
    sa.UniqueConstraint('submitter_plate_num')
    )
    # ### end Alembic commands ###