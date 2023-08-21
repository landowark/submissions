"""rebuild database

Revision ID: b879020f2a91
Revises: 
Create Date: 2023-08-02 09:16:12.792995

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b879020f2a91'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('_contacts',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=True),
    sa.Column('email', sa.String(length=64), nullable=True),
    sa.Column('phone', sa.String(length=32), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('_control_types',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('targets', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('_kits',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=True),
    sa.Column('used_for', sa.JSON(), nullable=True),
    sa.Column('cost_per_run', sa.FLOAT(precision=2), nullable=True),
    sa.Column('mutable_cost_column', sa.FLOAT(precision=2), nullable=True),
    sa.Column('mutable_cost_sample', sa.FLOAT(precision=2), nullable=True),
    sa.Column('constant_cost', sa.FLOAT(precision=2), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('_organizations',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=True),
    sa.Column('cost_centre', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('_reagent_types',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=True),
    sa.Column('eol_ext', sa.Interval(), nullable=True),
    sa.Column('last_used', sa.String(length=32), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('_samples',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('submitter_id', sa.String(length=64), nullable=False),
    sa.Column('sample_type', sa.String(length=32), nullable=True),
    sa.Column('ww_processing_num', sa.String(length=64), nullable=True),
    sa.Column('rsl_number', sa.String(length=64), nullable=True),
    sa.Column('collection_date', sa.TIMESTAMP(), nullable=True),
    sa.Column('testing_type', sa.String(length=64), nullable=True),
    sa.Column('site_status', sa.String(length=64), nullable=True),
    sa.Column('notes', sa.String(length=2000), nullable=True),
    sa.Column('ct_n1', sa.FLOAT(precision=2), nullable=True),
    sa.Column('ct_n2', sa.FLOAT(precision=2), nullable=True),
    sa.Column('n1_status', sa.String(length=32), nullable=True),
    sa.Column('n2_status', sa.String(length=32), nullable=True),
    sa.Column('seq_submitted', sa.BOOLEAN(), nullable=True),
    sa.Column('ww_seq_run_id', sa.String(length=64), nullable=True),
    sa.Column('pcr_results', sa.JSON(), nullable=True),
    sa.Column('well_24', sa.String(length=8), nullable=True),
    sa.Column('organism', sa.String(length=64), nullable=True),
    sa.Column('concentration', sa.String(length=16), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('submitter_id')
    )
    op.create_table('_discounts',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('kit_id', sa.INTEGER(), nullable=True),
    sa.Column('client_id', sa.INTEGER(), nullable=True),
    sa.Column('name', sa.String(length=128), nullable=True),
    sa.Column('amount', sa.FLOAT(precision=2), nullable=True),
    sa.ForeignKeyConstraint(['client_id'], ['_organizations.id'], name='fk_org_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['kit_id'], ['_kits.id'], name='fk_kit_type_id', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('_orgs_contacts',
    sa.Column('org_id', sa.INTEGER(), nullable=True),
    sa.Column('contact_id', sa.INTEGER(), nullable=True),
    sa.ForeignKeyConstraint(['contact_id'], ['_contacts.id'], ),
    sa.ForeignKeyConstraint(['org_id'], ['_organizations.id'], )
    )
    op.create_table('_reagents',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('type_id', sa.INTEGER(), nullable=True),
    sa.Column('name', sa.String(length=64), nullable=True),
    sa.Column('lot', sa.String(length=64), nullable=True),
    sa.Column('expiry', sa.TIMESTAMP(), nullable=True),
    sa.ForeignKeyConstraint(['type_id'], ['_reagent_types.id'], name='fk_reagent_type_id', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('_reagenttypes_kittypes',
    sa.Column('reagent_types_id', sa.INTEGER(), nullable=False),
    sa.Column('kits_id', sa.INTEGER(), nullable=False),
    sa.Column('uses', sa.JSON(), nullable=True),
    sa.Column('required', sa.INTEGER(), nullable=True),
    sa.ForeignKeyConstraint(['kits_id'], ['_kits.id'], ),
    sa.ForeignKeyConstraint(['reagent_types_id'], ['_reagent_types.id'], ),
    sa.PrimaryKeyConstraint('reagent_types_id', 'kits_id')
    )
    op.create_table('_submissions',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('rsl_plate_num', sa.String(length=32), nullable=False),
    sa.Column('submitter_plate_num', sa.String(length=127), nullable=True),
    sa.Column('submitted_date', sa.TIMESTAMP(), nullable=True),
    sa.Column('submitting_lab_id', sa.INTEGER(), nullable=True),
    sa.Column('sample_count', sa.INTEGER(), nullable=True),
    sa.Column('extraction_kit_id', sa.INTEGER(), nullable=True),
    sa.Column('submission_type', sa.String(length=32), nullable=True),
    sa.Column('technician', sa.String(length=64), nullable=True),
    sa.Column('reagents_id', sa.String(), nullable=True),
    sa.Column('extraction_info', sa.JSON(), nullable=True),
    sa.Column('run_cost', sa.FLOAT(precision=2), nullable=True),
    sa.Column('uploaded_by', sa.String(length=32), nullable=True),
    sa.Column('comment', sa.JSON(), nullable=True),
    sa.Column('pcr_info', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['extraction_kit_id'], ['_kits.id'], name='fk_BS_extkit_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['reagents_id'], ['_reagents.id'], name='fk_BS_reagents_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['submitting_lab_id'], ['_organizations.id'], name='fk_BS_sublab_id', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('rsl_plate_num'),
    sa.UniqueConstraint('submitter_plate_num')
    )
    op.create_table('_control_samples',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('parent_id', sa.String(), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('submitted_date', sa.TIMESTAMP(), nullable=True),
    sa.Column('contains', sa.JSON(), nullable=True),
    sa.Column('matches', sa.JSON(), nullable=True),
    sa.Column('kraken', sa.JSON(), nullable=True),
    sa.Column('submission_id', sa.INTEGER(), nullable=True),
    sa.Column('refseq_version', sa.String(length=16), nullable=True),
    sa.Column('kraken2_version', sa.String(length=16), nullable=True),
    sa.Column('kraken2_db_version', sa.String(length=32), nullable=True),
    sa.ForeignKeyConstraint(['parent_id'], ['_control_types.id'], name='fk_control_parent_id'),
    sa.ForeignKeyConstraint(['submission_id'], ['_submissions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('_reagents_submissions',
    sa.Column('reagent_id', sa.INTEGER(), nullable=True),
    sa.Column('submission_id', sa.INTEGER(), nullable=True),
    sa.ForeignKeyConstraint(['reagent_id'], ['_reagents.id'], ),
    sa.ForeignKeyConstraint(['submission_id'], ['_submissions.id'], )
    )
    op.create_table('_submission_sample',
    sa.Column('sample_id', sa.INTEGER(), nullable=False),
    sa.Column('submission_id', sa.INTEGER(), nullable=False),
    sa.Column('row', sa.INTEGER(), nullable=True),
    sa.Column('column', sa.INTEGER(), nullable=True),
    sa.ForeignKeyConstraint(['sample_id'], ['_samples.id'], ),
    sa.ForeignKeyConstraint(['submission_id'], ['_submissions.id'], ),
    sa.PrimaryKeyConstraint('sample_id', 'submission_id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('_submission_sample')
    op.drop_table('_reagents_submissions')
    op.drop_table('_control_samples')
    op.drop_table('_submissions')
    op.drop_table('_reagenttypes_kittypes')
    op.drop_table('_reagents')
    op.drop_table('_orgs_contacts')
    op.drop_table('_discounts')
    op.drop_table('_samples')
    op.drop_table('_reagent_types')
    op.drop_table('_organizations')
    op.drop_table('_kits')
    op.drop_table('_control_types')
    op.drop_table('_contacts')
    # ### end Alembic commands ###