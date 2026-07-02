import sys
from pathlib import Path
from datetime import datetime
src = Path('src/submissions').resolve()
if str(src) not in sys.path:
    sys.path.insert(0, str(src))
import tools
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from backend.db.models import Base, Run, ProcedureType, Procedure, ReagentRole, Reagent, ReagentLot, ProcedureReagentLotAssociation, ProcedureTypeReagentRoleAssociation, ClientSubmission, ReagentRoleReagentAssociation

engine = create_engine('sqlite://', connect_args={'check_same_thread': False})
Session = scoped_session(sessionmaker(bind=engine))
Base.metadata.create_all(engine)
tools.ctx.database.engine = engine
tools.ctx.database.session = Session
tools.ctx.database.schema = 'sqlite'

session = Session()
cs = ClientSubmission(submitter_plate_id='SUB1', submitted_date=datetime.now(), full_batch_size=1)
session.add(cs)
run = Run(clientsubmission=cs, rsl_plate_number='RUN1')
proc_type = ProcedureType(name='TestProc')
reagentrole = ReagentRole(name='Extraction')
reagent = Reagent(name='OmegaKit')
reagent_assoc = ReagentRoleReagentAssociation(reagentrole=reagentrole, reagent=reagent)
ptrra = ProcedureTypeReagentRoleAssociation(proceduretype=proc_type, reagentrole=reagentrole)
procedure = Procedure(run=run, proceduretype=proc_type)
reagentlot = ReagentLot(reagent=reagent, lot='LOT1', expiry=datetime(2026,12,31), active=True)
prla = ProcedureReagentLotAssociation(procedure=procedure, reagentlot=reagentlot, reagentrole=reagentrole)
session.add_all([run, proc_type, reagentrole, reagent, reagent_assoc, ptrra, procedure, reagentlot, prla])
session.commit()

pyd_proc = procedure.to_pydantic()
print('reagentlot raw', pyd_proc.reagentlot)
for i, rl in enumerate(pyd_proc.reagentlot):
    print('item', i, type(rl), repr(rl))
    try:
        print('  attr procedure', getattr(rl, 'procedure', None))
        print('  attr reagentlot', getattr(rl, 'reagentlot', None))
        print('  attr reagentrole', getattr(rl, 'reagentrole', None))
    except Exception as e:
        print('  attr error', e)
print('proceduretype_dict start')
d = pyd_proc.reorder_proceduretype_by_procedure()
import json
print(json.dumps(d['reagentrole'], indent=2, default=str))
session.close()
