"""added in artic information

Revision ID: aac569c672de
Revises: 64fec6271a50
Create Date: 2023-06-02 15:14:13.726489

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = 'aac569c672de'
down_revision = '64fec6271a50'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    # op.create_table('_artic_samples',
    # sa.Column('id', sa.INTEGER(), nullable=False),
    # sa.Column('well_number', sa.String(length=8), nullable=True),
    # sa.Column('rsl_plate_id', sa.INTEGER(), nullable=True),
    # sa.Column('ww_sample_full_id', sa.String(length=64), nullable=False),
    # sa.Column('lims_sample_id', sa.String(length=64), nullable=False),
    # sa.Column('ct_1', sa.FLOAT(precision=2), nullable=True),
    # sa.Column('ct_2', sa.FLOAT(precision=2), nullable=True),
    # sa.ForeignKeyConstraint(['rsl_plate_id'], ['_submissions.id'], name='fk_WWA_submission_id', ondelete='SET NULL'),
    # sa.PrimaryKeyConstraint('id')
    # )
    op.drop_table('_alembic_tmp__submissions')
    
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('_alembic_tmp__submissions',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('rsl_plate_num', sa.VARCHAR(length=32), nullable=False),
    sa.Column('submitter_plate_num', sa.VARCHAR(length=127), nullable=True),
    sa.Column('submitted_date', sa.TIMESTAMP(), nullable=True),
    sa.Column('submitting_lab_id', sa.INTEGER(), nullable=True),
    sa.Column('sample_count', sa.INTEGER(), nullable=True),
    sa.Column('extraction_kit_id', sa.INTEGER(), nullable=True),
    sa.Column('submission_type', sa.VARCHAR(length=32), nullable=True),
    sa.Column('technician', sa.VARCHAR(length=64), nullable=True),
    sa.Column('reagents_id', sa.VARCHAR(), nullable=True),
    sa.Column('extraction_info', sqlite.JSON(), nullable=True),
    sa.Column('run_cost', sa.FLOAT(), nullable=True),
    sa.Column('uploaded_by', sa.VARCHAR(length=32), nullable=True),
    sa.Column('pcr_info', sqlite.JSON(), nullable=True),
    sa.Column('comment', sqlite.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['extraction_kit_id'], ['_kits.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['reagents_id'], ['_reagents.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['submitting_lab_id'], ['_organizations.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('rsl_plate_num'),
    sa.UniqueConstraint('submitter_plate_num')
    )
    # op.drop_table('_artic_samples')
    # ### end Alembic commands ###