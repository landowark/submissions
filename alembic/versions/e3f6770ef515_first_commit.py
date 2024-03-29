"""First Commit

Revision ID: e3f6770ef515
Revises: 
Create Date: 2024-01-22 14:01:02.958292

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e3f6770ef515'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('_basicsample',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('submitter_id', sa.String(length=64), nullable=False),
    sa.Column('sample_type', sa.String(length=32), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('submitter_id')
    )
    op.create_table('_contact',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=True),
    sa.Column('email', sa.String(length=64), nullable=True),
    sa.Column('phone', sa.String(length=32), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('_controltype',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('targets', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('_equipment',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=True),
    sa.Column('nickname', sa.String(length=64), nullable=True),
    sa.Column('asset_number', sa.String(length=16), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('_equipmentrole',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('_kittype',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('_organization',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=True),
    sa.Column('cost_centre', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('_process',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('_reagenttype',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=True),
    sa.Column('eol_ext', sa.Interval(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('_submissiontype',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=True),
    sa.Column('info_map', sa.JSON(), nullable=True),
    sa.Column('template_file', sa.BLOB(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('_bacterialculturesample',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('organism', sa.String(length=64), nullable=True),
    sa.Column('concentration', sa.String(length=16), nullable=True),
    sa.ForeignKeyConstraint(['id'], ['_basicsample.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('_discount',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('kit_id', sa.INTEGER(), nullable=True),
    sa.Column('client_id', sa.INTEGER(), nullable=True),
    sa.Column('name', sa.String(length=128), nullable=True),
    sa.Column('amount', sa.FLOAT(precision=2), nullable=True),
    sa.ForeignKeyConstraint(['client_id'], ['_organization.id'], name='fk_org_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['kit_id'], ['_kittype.id'], name='fk_kit_type_id', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('_equipment_processes',
    sa.Column('process_id', sa.INTEGER(), nullable=True),
    sa.Column('equipment_id', sa.INTEGER(), nullable=True),
    sa.ForeignKeyConstraint(['equipment_id'], ['_equipment.id'], ),
    sa.ForeignKeyConstraint(['process_id'], ['_process.id'], )
    )
    op.create_table('_equipmentroles_equipment',
    sa.Column('equipment_id', sa.INTEGER(), nullable=True),
    sa.Column('equipmentroles_id', sa.INTEGER(), nullable=True),
    sa.ForeignKeyConstraint(['equipment_id'], ['_equipment.id'], ),
    sa.ForeignKeyConstraint(['equipmentroles_id'], ['_equipmentrole.id'], )
    )
    op.create_table('_equipmentroles_processes',
    sa.Column('process_id', sa.INTEGER(), nullable=True),
    sa.Column('equipmentrole_id', sa.INTEGER(), nullable=True),
    sa.ForeignKeyConstraint(['equipmentrole_id'], ['_equipmentrole.id'], ),
    sa.ForeignKeyConstraint(['process_id'], ['_process.id'], )
    )
    op.create_table('_kittypereagenttypeassociation',
    sa.Column('reagent_types_id', sa.INTEGER(), nullable=False),
    sa.Column('kits_id', sa.INTEGER(), nullable=False),
    sa.Column('submission_type_id', sa.INTEGER(), nullable=False),
    sa.Column('uses', sa.JSON(), nullable=True),
    sa.Column('required', sa.INTEGER(), nullable=True),
    sa.Column('last_used', sa.String(length=32), nullable=True),
    sa.ForeignKeyConstraint(['kits_id'], ['_kittype.id'], ),
    sa.ForeignKeyConstraint(['reagent_types_id'], ['_reagenttype.id'], ),
    sa.ForeignKeyConstraint(['submission_type_id'], ['_submissiontype.id'], ),
    sa.PrimaryKeyConstraint('reagent_types_id', 'kits_id', 'submission_type_id')
    )
    op.create_table('_kittypes_processes',
    sa.Column('process_id', sa.INTEGER(), nullable=True),
    sa.Column('kit_id', sa.INTEGER(), nullable=True),
    sa.ForeignKeyConstraint(['kit_id'], ['_kittype.id'], ),
    sa.ForeignKeyConstraint(['process_id'], ['_process.id'], )
    )
    op.create_table('_orgs_contacts',
    sa.Column('org_id', sa.INTEGER(), nullable=True),
    sa.Column('contact_id', sa.INTEGER(), nullable=True),
    sa.ForeignKeyConstraint(['contact_id'], ['_contact.id'], ),
    sa.ForeignKeyConstraint(['org_id'], ['_organization.id'], )
    )
    op.create_table('_reagent',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('type_id', sa.INTEGER(), nullable=True),
    sa.Column('name', sa.String(length=64), nullable=True),
    sa.Column('lot', sa.String(length=64), nullable=True),
    sa.Column('expiry', sa.TIMESTAMP(), nullable=True),
    sa.ForeignKeyConstraint(['type_id'], ['_reagenttype.id'], name='fk_reagent_type_id', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('_submissiontypeequipmentroleassociation',
    sa.Column('equipmentrole_id', sa.INTEGER(), nullable=False),
    sa.Column('submissiontype_id', sa.INTEGER(), nullable=False),
    sa.Column('uses', sa.JSON(), nullable=True),
    sa.Column('static', sa.INTEGER(), nullable=True),
    sa.ForeignKeyConstraint(['equipmentrole_id'], ['_equipmentrole.id'], ),
    sa.ForeignKeyConstraint(['submissiontype_id'], ['_submissiontype.id'], ),
    sa.PrimaryKeyConstraint('equipmentrole_id', 'submissiontype_id')
    )
    op.create_table('_submissiontypekittypeassociation',
    sa.Column('submission_types_id', sa.INTEGER(), nullable=False),
    sa.Column('kits_id', sa.INTEGER(), nullable=False),
    sa.Column('mutable_cost_column', sa.FLOAT(precision=2), nullable=True),
    sa.Column('mutable_cost_sample', sa.FLOAT(precision=2), nullable=True),
    sa.Column('constant_cost', sa.FLOAT(precision=2), nullable=True),
    sa.ForeignKeyConstraint(['kits_id'], ['_kittype.id'], ),
    sa.ForeignKeyConstraint(['submission_types_id'], ['_submissiontype.id'], ),
    sa.PrimaryKeyConstraint('submission_types_id', 'kits_id')
    )
    op.create_table('_submissiontypes_processes',
    sa.Column('process_id', sa.INTEGER(), nullable=True),
    sa.Column('equipmentroles_id', sa.INTEGER(), nullable=True),
    sa.ForeignKeyConstraint(['equipmentroles_id'], ['_submissiontype.id'], ),
    sa.ForeignKeyConstraint(['process_id'], ['_process.id'], )
    )
    op.create_table('_wastewatersample',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('ww_processing_num', sa.String(length=64), nullable=True),
    sa.Column('ww_full_sample_id', sa.String(length=64), nullable=True),
    sa.Column('rsl_number', sa.String(length=64), nullable=True),
    sa.Column('collection_date', sa.TIMESTAMP(), nullable=True),
    sa.Column('received_date', sa.TIMESTAMP(), nullable=True),
    sa.Column('notes', sa.String(length=2000), nullable=True),
    sa.Column('sample_location', sa.String(length=8), nullable=True),
    sa.ForeignKeyConstraint(['id'], ['_basicsample.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('_basicsubmission',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('rsl_plate_num', sa.String(length=32), nullable=False),
    sa.Column('submitter_plate_num', sa.String(length=127), nullable=True),
    sa.Column('submitted_date', sa.TIMESTAMP(), nullable=True),
    sa.Column('submitting_lab_id', sa.INTEGER(), nullable=True),
    sa.Column('sample_count', sa.INTEGER(), nullable=True),
    sa.Column('extraction_kit_id', sa.INTEGER(), nullable=True),
    sa.Column('submission_type_name', sa.String(), nullable=True),
    sa.Column('technician', sa.String(length=64), nullable=True),
    sa.Column('reagents_id', sa.String(), nullable=True),
    sa.Column('extraction_info', sa.JSON(), nullable=True),
    sa.Column('pcr_info', sa.JSON(), nullable=True),
    sa.Column('run_cost', sa.FLOAT(precision=2), nullable=True),
    sa.Column('uploaded_by', sa.String(length=32), nullable=True),
    sa.Column('comment', sa.JSON(), nullable=True),
    sa.Column('submission_category', sa.String(length=64), nullable=True),
    sa.ForeignKeyConstraint(['extraction_kit_id'], ['_kittype.id'], name='fk_BS_extkit_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['reagents_id'], ['_reagent.id'], name='fk_BS_reagents_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['submission_type_name'], ['_submissiontype.name'], name='fk_BS_subtype_name', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['submitting_lab_id'], ['_organization.id'], name='fk_BS_sublab_id', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('rsl_plate_num'),
    sa.UniqueConstraint('submitter_plate_num')
    )
    op.create_table('_reagenttypes_reagents',
    sa.Column('reagent_id', sa.INTEGER(), nullable=True),
    sa.Column('reagenttype_id', sa.INTEGER(), nullable=True),
    sa.ForeignKeyConstraint(['reagent_id'], ['_reagent.id'], ),
    sa.ForeignKeyConstraint(['reagenttype_id'], ['_reagenttype.id'], )
    )
    op.create_table('_bacterialculture',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['_basicsubmission.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('_control',
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
    sa.Column('sample_id', sa.INTEGER(), nullable=True),
    sa.ForeignKeyConstraint(['parent_id'], ['_controltype.id'], name='fk_control_parent_id'),
    sa.ForeignKeyConstraint(['sample_id'], ['_basicsample.id'], name='cont_BCS_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['submission_id'], ['_basicsubmission.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('_submissionequipmentassociation',
    sa.Column('equipment_id', sa.INTEGER(), nullable=False),
    sa.Column('submission_id', sa.INTEGER(), nullable=False),
    sa.Column('role', sa.String(length=64), nullable=False),
    sa.Column('process_id', sa.INTEGER(), nullable=True),
    sa.Column('start_time', sa.TIMESTAMP(), nullable=True),
    sa.Column('end_time', sa.TIMESTAMP(), nullable=True),
    sa.Column('comments', sa.String(length=1024), nullable=True),
    sa.ForeignKeyConstraint(['equipment_id'], ['_equipment.id'], ),
    sa.ForeignKeyConstraint(['process_id'], ['_process.id'], name='SEA_Process_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['submission_id'], ['_basicsubmission.id'], ),
    sa.PrimaryKeyConstraint('equipment_id', 'submission_id', 'role')
    )
    op.create_table('_submissionreagentassociation',
    sa.Column('reagent_id', sa.INTEGER(), nullable=False),
    sa.Column('submission_id', sa.INTEGER(), nullable=False),
    sa.Column('comments', sa.String(length=1024), nullable=True),
    sa.ForeignKeyConstraint(['reagent_id'], ['_reagent.id'], ),
    sa.ForeignKeyConstraint(['submission_id'], ['_basicsubmission.id'], ),
    sa.PrimaryKeyConstraint('reagent_id', 'submission_id')
    )
    op.create_table('_submissionsampleassociation',
    sa.Column('sample_id', sa.INTEGER(), nullable=False),
    sa.Column('submission_id', sa.INTEGER(), nullable=False),
    sa.Column('row', sa.INTEGER(), nullable=False),
    sa.Column('column', sa.INTEGER(), nullable=False),
    sa.Column('base_sub_type', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['sample_id'], ['_basicsample.id'], ),
    sa.ForeignKeyConstraint(['submission_id'], ['_basicsubmission.id'], ),
    sa.PrimaryKeyConstraint('submission_id', 'row', 'column')
    )
    op.create_table('_wastewater',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('ext_technician', sa.String(length=64), nullable=True),
    sa.Column('pcr_technician', sa.String(length=64), nullable=True),
    sa.ForeignKeyConstraint(['id'], ['_basicsubmission.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('_wastewaterartic',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('artic_technician', sa.String(length=64), nullable=True),
    sa.Column('dna_core_submission_number', sa.String(length=64), nullable=True),
    sa.ForeignKeyConstraint(['id'], ['_basicsubmission.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('_wastewaterassociation',
    sa.Column('sample_id', sa.INTEGER(), nullable=False),
    sa.Column('submission_id', sa.INTEGER(), nullable=False),
    sa.Column('ct_n1', sa.FLOAT(precision=2), nullable=True),
    sa.Column('ct_n2', sa.FLOAT(precision=2), nullable=True),
    sa.Column('n1_status', sa.String(length=32), nullable=True),
    sa.Column('n2_status', sa.String(length=32), nullable=True),
    sa.Column('pcr_results', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['sample_id'], ['_submissionsampleassociation.sample_id'], ),
    sa.ForeignKeyConstraint(['submission_id'], ['_submissionsampleassociation.submission_id'], ),
    sa.PrimaryKeyConstraint('sample_id', 'submission_id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('_wastewaterassociation')
    op.drop_table('_wastewaterartic')
    op.drop_table('_wastewater')
    op.drop_table('_submissionsampleassociation')
    op.drop_table('_submissionreagentassociation')
    op.drop_table('_submissionequipmentassociation')
    op.drop_table('_control')
    op.drop_table('_bacterialculture')
    op.drop_table('_reagenttypes_reagents')
    op.drop_table('_basicsubmission')
    op.drop_table('_wastewatersample')
    op.drop_table('_submissiontypes_processes')
    op.drop_table('_submissiontypekittypeassociation')
    op.drop_table('_submissiontypeequipmentroleassociation')
    op.drop_table('_reagent')
    op.drop_table('_orgs_contacts')
    op.drop_table('_kittypes_processes')
    op.drop_table('_kittypereagenttypeassociation')
    op.drop_table('_equipmentroles_processes')
    op.drop_table('_equipmentroles_equipment')
    op.drop_table('_equipment_processes')
    op.drop_table('_discount')
    op.drop_table('_bacterialculturesample')
    op.drop_table('_submissiontype')
    op.drop_table('_reagenttype')
    op.drop_table('_process')
    op.drop_table('_organization')
    op.drop_table('_kittype')
    op.drop_table('_equipmentrole')
    op.drop_table('_equipment')
    op.drop_table('_controltype')
    op.drop_table('_contact')
    op.drop_table('_basicsample')
    # ### end Alembic commands ###
