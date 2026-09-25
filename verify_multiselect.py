#!/usr/bin/env python
"""Verify multiselect field flows through construct_dummy_procedure to template."""
import sys
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

sys.path.insert(0, r'C:\Users\lwark\Documents\python\submissions\src\submissions')

from tools import ctx, render_details_template
from backend.db.models import Base, ProcedureType, ReagentRole, ProcedureTypeReagentRoleAssociation

# Set up in-memory database
engine = create_engine('sqlite://')
Session = scoped_session(sessionmaker(bind=engine))
ctx.database = type('DB', (), {'session': Session, 'engine': engine})()
ctx.directories = type('D', (), {'main': r'C:\Users\lwark\Documents\python\submissions'})()
Base.metadata.create_all(engine)

# Create minimal ProcedureType with multiselect ReagentRole
session = Session()
pt = ProcedureType(name='Omega Bacterial Extraction', plate_rows=8, plate_columns=12, plate_cost=0)
rr = ReagentRole(name='Omega Positive Control')

session.add_all([pt, rr])
session.commit()

# Create association with multiselect=True
assoc = ProcedureTypeReagentRoleAssociation(proceduretype=pt, reagentrole=rr, _always_used=1)
assoc.multiselect = True
session.add(assoc)
session.commit()

# Query and construct dummy procedure
pt_q = ProcedureType.query(name='Omega Bacterial Extraction', limit=1)
print('✓ QUERY_RESULT:', pt_q)
print('✓ ASSOCIATION_MULTISELECT:', pt_q.proceduretypereagentroleassociation[0].multiselect)

p = pt_q.construct_dummy_procedure()
rr_list = p.proceduretype.improved_dict['reagentrole']
has_omega_multi = any(
    item.get('name') == 'Omega Positive Control' and item.get('multiselect') is True
    for item in rr_list
)
print('✓ IMPROVED_DICT_REAGENTROLE:', rr_list)
print('✓ HAS_MULTIPLE_ON_OMEGA:', has_omega_multi)

# Render template
html = render_details_template(
    template='procedure_creation',
    proceduretype=p.proceduretype.improved_dict,
    run={'plate_number': 'RSL-TEST-240925-1'},
    procedure=p.improved_dict,
    platemap='',
    now=datetime.now(),
    preprocessing_buttons=[],
    edit=False,
)

# Check HTML output
idx = html.find('Omega Positive Control')
if idx > 0:
    snippet = html[max(0, idx-200):idx+500]
    has_multiple_attr = 'multiple' in snippet
    print(f'✓ FOUND_IN_HTML: idx={idx}, has_multiple_attr={has_multiple_attr}')
    print('HTML snippet:', snippet)
else:
    print('✗ NOT_FOUND_IN_HTML')

print('✓ ALL_CHECKS_PASSED' if has_omega_multi and has_multiple_attr else '✗ FAILED')
