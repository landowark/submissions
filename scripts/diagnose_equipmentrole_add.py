import os, sys, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "submissions"))
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

ROLE, EQUIP = sys.argv[1], sys.argv[2]
PROCS = sys.argv[3].split(",") if len(sys.argv) > 3 else None

from backend.db.models import EquipmentRole, Equipment, Process
role = EquipmentRole.query(ROLE, limit=1)
print("Role:", role)
print(" assocs: ", [(getattr(a.equipment, "name", None), [p.name for p in a.processes]) for a in role.equipmentroleequipmentassociation])
print(  "Equipment row:", Equipment.query(name=EQUIP, limit=1))
for p in PROCS:
    print("  Process row:", p, Process.query(name=p, limit=1))
pyd = role.to_pydantic()
print("PYD.new", pyd.new, "PYD.equipment:", pyd.equipment)
pyd.add_relationship("equipment", EQUIP, {"process": PROCS} if PROCS else {})
print("AFTER add_relationship:", pyd.equipment)
sql = pyd.to_sql()
sql = sql[0] if isinstance(sql, tuple) else sql
print("AFTER to_sql:", [getattr(e, "name", None) for e in sql.equipment])
session = sql.__database_session__
try:
    session.flush(); print("FLUSH OK -- the write would have succeeded")
except Exception as e:

    print("FLUSH FAILED:", e)
finally:
    session.rollback(); print("(rolled back, database untouched)")