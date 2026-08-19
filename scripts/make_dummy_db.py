"""
Build a populated dummy database straight from the SQLAlchemy models.

The schema is created with ``Base.metadata.create_all`` rather than by running the
alembic migrations, so the result always matches the models as they exist in the
working tree. Nothing here touches a real database: the target file is created
fresh (and refused if it already exists unless ``--force`` is given).

Usage::

    QT_QPA_PLATFORM=offscreen python scripts/make_dummy_db.py
    QT_QPA_PLATFORM=offscreen python scripts/make_dummy_db.py --out /tmp/dummy.db --force

The models import the frontend at module load, so PyQt6 must be installed and
``QT_QPA_PLATFORM=offscreen`` is needed on a headless machine.
"""
from __future__ import annotations

import argparse
import platform
import sys
from datetime import datetime, timedelta
from pathlib import Path
from random import Random

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src" / "submissions"

# --------------------------------------------------------------------------- #
# The app imports its own modules as top-level names (``tools``, ``backend``,   #
# ``frontend``), so ``src/submissions`` has to be importable before anything    #
# else happens.                                                                #
# --------------------------------------------------------------------------- #
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def ensure_minimal_config() -> None:
    """
    Guarantee ``tools.Settings`` finds a config file, without clobbering a real one.

    ``ctx`` is built at import time and needs a database entry it can turn into an
    engine. If the developer already has a config we leave it completely alone --
    the engine it produces is thrown away and replaced further down anyway.
    """
    os_config_dir = "AppData/local" if platform.system() == "Windows" else ".config"
    aux = Path.home() / os_config_dir / "submissions_tng" / "config"
    if aux.joinpath("config.yml").exists():
        return
    if Path.home().joinpath(".submissions_tng", "config.yml").exists():
        return
    aux.mkdir(parents=True, exist_ok=True)
    aux.joinpath("config.yml").write_text(
        "database:\n"
        "  schema: sqlite\n"
        f"  path: {REPO_ROOT}\n"
        "  name: dummy_submissions\n"
    )


def make_lot_fk_resolvable() -> bool:
    """
    Add a UNIQUE constraint to ``_reagentlot.lot`` in the in-memory metadata, before
    the tables are created.

    ``ProcedureTypeReagentRoleAssociation.last_used_lot`` is declared
    ``ForeignKey("_reagentlot.lot")``, but ``lot`` is neither a primary key nor
    unique. SQLite calls a foreign key whose parent column has no unique index
    malformed and reports "foreign key mismatch" when either end is written to --
    and ``backend/db`` sets ``PRAGMA foreign_keys=ON`` for every sqlite connection.
    With the schema exactly as the models declare it, that means every write to
    ``_proceduretypereagentroleassociation`` fails, and so does any flush that
    inserts more than one ``ReagentLot`` at once (SQLAlchemy's multi-row INSERT
    path trips the check; a single-row insert happens to slip past it).

    Making ``lot`` unique is one of the two fixes the model needs (the other being
    to retarget the foreign key at ``_reagentlot.id``); it is the one that keeps the
    ``_last_used`` relationship's join condition inferrable, so it is what this
    script uses. Only the generated file is affected -- the models are untouched.
    """
    from sqlalchemy import UniqueConstraint

    from backend.db.models import Base

    table = Base.metadata.tables["_reagentlot"]
    if any(isinstance(c, UniqueConstraint) and set(c.columns) == {table.c.lot}
           for c in table.constraints):
        return False
    table.append_constraint(UniqueConstraint("lot", name="uq_reagentlot_lot"))
    return True


def build_schema(target: Path, enforce_fks: bool):
    """
    Create every table defined by the models in a fresh sqlite file and point
    ``ctx`` at it, so model queries executed during seeding hit the dummy database.
    """
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import scoped_session, sessionmaker

    import tools
    from backend.db.models import Base

    engine = create_engine(f"sqlite:///{target}")

    if not enforce_fks:
        # ``backend.db`` registers a global connect listener that turns foreign
        # keys on for every engine. Ours is registered afterwards on this engine
        # only, so it wins for the duration of seeding. The generated graph is
        # internally consistent regardless; this only sidesteps the malformed
        # ``last_used_lot`` constraint (see drop_last_used_lot_fk).
        @event.listens_for(engine, "connect")
        def _relax_foreign_keys(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=OFF")
            cursor.close()

    Base.metadata.create_all(engine)

    session = scoped_session(sessionmaker(bind=engine))
    tools.ctx.database.engine = engine
    tools.ctx.database.session = session
    tools.ctx.database.schema = "sqlite"
    tools.ctx.database.path = str(target.parent)
    tools.ctx.database.name = target.stem
    return engine, session


# --------------------------------------------------------------------------- #
# Seed data.                                                                   #
#                                                                              #
# Each phase commits before the next begins: the models' setters resolve        #
# strings/dicts by querying the database, so a catalog row has to be persisted  #
# before anything is allowed to refer to it by name.                            #
# --------------------------------------------------------------------------- #
FIRST_NAMES = ["Ada", "Grace", "Rosalind", "Barbara", "Katherine", "Jennifer",
               "Tu", "Chien-Shiung", "Esther", "Flossie"]
LAST_NAMES = ["Lovelace", "Hopper", "Franklin", "McClintock", "Johnson", "Doudna",
              "Youyou", "Wu", "Lederberg", "Wong-Staal"]


def seed_config_items(session):
    """Rows that ``Settings.set_from_db`` reads back on the next app start."""
    from backend.db.models import ConfigItem

    items = {
        "power_users": ["lwark", "styson", "ruwang"],
        "super_users": ["lwark"],
        "startup_scripts": {"hello": None},
        "teardown_scripts": {"goodbye": None},
    }
    for key, value in items.items():
        session.add(ConfigItem(key=key, value=value))
    session.commit()


def seed_organizations(session, rng: Random):
    from backend.db.models import ClientLab, Contact

    contacts = []
    for iii in range(6):
        first, last = FIRST_NAMES[iii], LAST_NAMES[iii]
        contacts.append(Contact(
            name=f"{first} {last}",
            email=f"{first.lower()}.{last.lower().replace('-', '')}@example.org",
            tel=f"204-555-{rng.randint(1000, 9999)}",
        ))
    session.add_all(contacts)
    session.commit()

    labs = []
    for iii, name in enumerate(["Enteric Diseases", "Wastewater Surveillance",
                                "Vector-Borne Diseases", "Bacterial Pathogens"]):
        lab = ClientLab(name=name, cost_centre=f"CC-{6100 + iii * 10}")
        lab.contact = [contacts[iii], contacts[iii + 2]]
        labs.append(lab)
    session.add_all(labs)
    session.commit()
    return labs, contacts


def seed_reagents(session, rng: Random):
    """Reagent roles, the concrete reagents that fill them, and their lots."""
    from backend.db.models import (Reagent, ReagentLot, ReagentRole,
                                   ReagentRoleReagentAssociation)

    role_specs = {
        "Lysis Buffer": [("Omega Lysis Buffer BL", "Omega Bio-tek", "OM-BL-500", 0.35, 0.30)],
        "Proteinase K": [("Proteinase K Solution", "Omega Bio-tek", "OM-PK-100", 1.10, 0.02)],
        "Wash Buffer": [("Wash Buffer HBC", "Omega Bio-tek", "OM-HBC-250", 0.22, 0.50),
                        ("DNA Wash Buffer", "Omega Bio-tek", "OM-DWB-500", 0.18, 0.70)],
        "Elution Buffer": [("Elution Buffer TE", "Omega Bio-tek", "OM-TE-100", 0.15, 0.10)],
        "Magnetic Beads": [("Mag-Bind Particles CNR", "Omega Bio-tek", "OM-CNR-50", 4.75, 0.02)],
        "Master Mix": [("TaqPath 1-Step Master Mix", "Thermo Fisher", "TF-A15299", 12.40, 0.01),
                       ("Luna Universal qPCR Mix", "NEB", "NEB-M3003", 9.85, 0.01)],
        "Primer Probe Mix": [("N1/N2 Primer Probe Mix", "IDT", "IDT-10006713", 22.00, 0.002)],
        "Library Prep Kit": [("Nextera XT DNA Library Kit", "Illumina", "ILL-FC-131", 48.00, 0.005)],
        "Molecular Grade Water": [("Nuclease-Free Water", "Invitrogen", "INV-AM9937", 0.05, 1.00)],
    }

    roles, reagents, lots = {}, {}, {}
    for role_name, reagent_specs in role_specs.items():
        role = ReagentRole(name=role_name)
        session.add(role)
        roles[role_name] = role
        for name, manufacturer, ref, cost_per_ml, ml_per_sample in reagent_specs:
            reagent = Reagent(name=name, manufacturer=manufacturer, ref=ref,
                              cost_per_ml=cost_per_ml)
            session.add(reagent)
            reagents[name] = reagent
            # The role<->reagent link carries the per-sample volume used for costing.
            session.add(ReagentRoleReagentAssociation(
                reagentrole=role, reagent=reagent, ml_used_per_sample=ml_per_sample))
    session.commit()

    for name, reagent in reagents.items():
        for iii in range(rng.randint(1, 3)):
            lot = ReagentLot(
                lot=f"{reagent.ref}-{rng.randint(100000, 999999)}",
                reagent=reagent,
                expiry=datetime.now() + timedelta(days=rng.randint(-60, 720)),
                active=1,
            )
            lot._scan_ids = []
            session.add(lot)
            lots.setdefault(name, []).append(lot)
    session.commit()
    return roles, reagents, lots


def seed_equipment(session, rng: Random):
    """Equipment roles, instruments, the processes they run, and tip stock."""
    from backend.db.models import (Equipment, EquipmentRole,
                                   EquipmentRoleEquipmentAssociation, Process,
                                   ProcessVersion, Tips, TipsLot)

    role_specs = {
        "Liquid Handler": [("Hamilton Microlab STAR", "Hamilton", "HAM-STAR-01"),
                           ("Hamilton Microlab NIMBUS", "Hamilton", "HAM-NIMB-01")],
        "Centrifuge": [("Eppendorf 5810R", "Eppendorf", "EPP-5810-01")],
        "Bead Basher": [("Omni Bead Ruptor 24", "Omni International", "OMNI-BR24-01")],
        "Thermocycler": [("Applied Biosystems QuantStudio 5", "Thermo Fisher", "ABI-QS5-01"),
                         ("Bio-Rad C1000 Touch", "Bio-Rad", "BR-C1000-01")],
        "Plate Reader": [("Qubit Flex Fluorometer", "Thermo Fisher", "TF-QFLEX-01")],
    }

    roles, equipment = {}, {}
    for role_name, specs in role_specs.items():
        role = EquipmentRole(name=role_name)
        session.add(role)
        roles[role_name] = role
        for name, manufacturer, asset_number in specs:
            item = Equipment(
                name=name,
                manufacturer=manufacturer,
                ref=asset_number.split("-")[1],
                serial_number=f"SN{rng.randint(100000, 999999)}",
                asset_number=asset_number,
                nickname=name.split()[-1],
            )
            item._calibration_date = datetime.now() - timedelta(days=rng.randint(10, 340))
            session.add(item)
            equipment[name] = item
    session.commit()

    # Tips are consumables bound to the processes that consume them.
    tips = {}
    for manufacturer, capacity, ref, cost in [("Hamilton", 1000, "HAM-235904", 0.08),
                                              ("Hamilton", 300, "HAM-235903", 0.06),
                                              ("Hamilton", 50, "HAM-235902", 0.05)]:
        tip = Tips(manufacturer=manufacturer, capacity=capacity, ref=ref, cost_per_tip=cost)
        session.add(tip)
        tips[ref] = tip
    session.commit()

    tipslots = {}
    for ref, tip in tips.items():
        for iii in range(2):
            slot = TipsLot(tips=tip, lot=f"{ref}-L{rng.randint(1000, 9999)}",
                           expiry=datetime.now() + timedelta(days=rng.randint(120, 900)),
                           active=1)
            session.add(slot)
            tipslots.setdefault(ref, []).append(slot)
    session.commit()

    # A Process is a named method; ProcessVersions are its revisions over time.
    process_specs = {
        "Omega Bacterial Extraction": ("Liquid Handler", ["HAM-235904", "HAM-235903"]),
        "Magnetic Bead Cleanup": ("Liquid Handler", ["HAM-235903"]),
        "Bead Bashing 5 min": ("Bead Basher", []),
        "Plate Spin 3000rpm": ("Centrifuge", []),
        "TaqPath qPCR 45 cycles": ("Thermocycler", []),
        "Nextera XT Tagmentation": ("Liquid Handler", ["HAM-235902"]),
        "Qubit dsDNA HS Assay": ("Plate Reader", []),
    }
    processes, processversions = {}, {}
    for process_name, (role_name, tip_refs) in process_specs.items():
        process = Process(name=process_name)
        process.tips = [tips[ref] for ref in tip_refs]
        session.add(process)
        processes[process_name] = process
        session.commit()
        # Two versions each: an older retired one and the current active one.
        for version, active, age in ((1.0, 0, 900), (2.0, 1, 120)):
            pv = ProcessVersion(process=process, version=version, active=active,
                                project="Routine Diagnostics",
                                date_verified=datetime.now() - timedelta(days=age))
            session.add(pv)
            if active:
                processversions[process_name] = pv
    session.commit()

    # Wire each instrument to the role it fills, and to the processes it can run.
    for role_name, specs in role_specs.items():
        for name, *_ in specs:
            assoc = EquipmentRoleEquipmentAssociation(
                equipmentrole=roles[role_name], equipment=equipment[name])
            assoc.process = [process for process, (r, _) in process_specs.items()
                             if r == role_name]
            session.add(assoc)
    session.commit()
    return roles, equipment, processes, processversions, tips, tipslots


def seed_types(session, reagent_roles, equipment_roles):
    """Submission types, the procedure types they contain, and results types."""
    from backend.db.models import (ProcedureType,
                                   ProcedureTypeEquipmentRoleAssociation,
                                   ProcedureTypeReagentRoleAssociation,
                                   ResultsType, SubmissionType)

    resultstype_specs = {
        "Qubit Concentration": dict(
            info={"instrument": "Qubit Flex", "assay": "dsDNA HS"},
            samples={"concentration": "ng/uL", "volume": "uL"},
            info_key_order=["instrument", "assay"],
            sample_key_order=["concentration", "volume"],
        ),
        "Diomni PCR": dict(
            info={"instrument": "QuantStudio 5", "software": "Design & Analysis"},
            samples={"ct": "cycle threshold", "call": "detection call"},
            info_key_order=["instrument", "software"],
            sample_key_order=["ct", "call"],
        ),
        "Gel Image": dict(
            info={"instrument": "E-Gel Reader"},
            samples={"band": "band present"},
            info_key_order=["instrument"],
            sample_key_order=["band"],
        ),
        # The Irida Controls tab is not optional: KrakenViewer.__init__ raises
        # ValueError unless a results type with exactly this name exists, and then
        # reads saved_settings['projects']. An empty project map leaves the tab
        # inert, which is what we want -- a populated one would have the app
        # reaching out to the live Irida Next API on startup.
        "Irida Kraken": dict(
            info={"source": "Irida Next"},
            samples={"fraction_total_reads": "fraction of total reads"},
            info_key_order=["source"],
            sample_key_order=["fraction_total_reads"],
            saved_settings={"projects": {}},
        ),
    }
    resultstypes = {}
    for name, spec in resultstype_specs.items():
        # NOTE: saved_settings must be passed explicitly -- ResultsType.__init__
        # defaults it to [] and its setter rejects anything that isn't a dict.
        spec = dict(saved_settings={}) | spec
        resultstypes[name] = ResultsType(name=name, **spec)
        session.add(resultstypes[name])
    session.commit()

    proceduretype_specs = {
        "DNA Extraction": dict(
            rows=8, columns=12, cost=32.50,
            reagents=["Lysis Buffer", "Proteinase K", "Wash Buffer", "Elution Buffer",
                      "Magnetic Beads", "Molecular Grade Water"],
            equipment=["Liquid Handler", "Centrifuge", "Bead Basher"],
            results=["Qubit Concentration"],
        ),
        "Library Prep": dict(
            rows=8, columns=12, cost=118.00,
            reagents=["Library Prep Kit", "Magnetic Beads", "Molecular Grade Water"],
            equipment=["Liquid Handler", "Thermocycler"],
            results=["Qubit Concentration", "Gel Image"],
        ),
        "qPCR": dict(
            rows=8, columns=12, cost=44.25,
            reagents=["Master Mix", "Primer Probe Mix", "Molecular Grade Water"],
            equipment=["Liquid Handler", "Thermocycler"],
            results=["Diomni PCR"],
        ),
        "Artic Amplification": dict(
            rows=16, columns=24, cost=96.75,
            reagents=["Master Mix", "Primer Probe Mix", "Magnetic Beads"],
            equipment=["Liquid Handler", "Thermocycler"],
            results=["Gel Image"],
        ),
    }
    submissiontype_specs = {
        "Bacterial Culture": dict(abbreviation="BAC", turnaround=timedelta(days=5),
                                  procedures=["DNA Extraction", "Library Prep"]),
        "Wastewater": dict(abbreviation="WW", turnaround=timedelta(days=2),
                           procedures=["DNA Extraction", "qPCR"]),
        "Wastewater Artic": dict(abbreviation="WWA", turnaround=timedelta(days=7),
                                 procedures=["DNA Extraction", "Artic Amplification"]),
    }

    # Submission types are created first, and every procedure type is handed its
    # submission types explicitly. ProcedureType.__init__ falls back to
    # ``self.submissiontype = ["Default SubmissionType"]`` when the kwarg is absent,
    # and that name resolves to None unless such a row exists -- which then makes
    # the flush fail with "Can't flush None value found in collection". The
    # placeholder row below keeps that fallback path working for anything created
    # later through the UI.
    submissiontypes = {}
    for name, spec in list(submissiontype_specs.items()) + [("Default SubmissionType", None)]:
        if spec is None:
            st = SubmissionType(name=name, defaults={})
        else:
            st = SubmissionType(
                name=name,
                defaults={},
                regex=rf"(?P<{spec['abbreviation']}>RSL-{spec['abbreviation']}-\d{{2}}-\d{{4}})",
            )
            st.abbreviation = spec["abbreviation"]
            st.turnaround_time = spec["turnaround"]
            st._info_sheets = [dict(sheet="Submission Info", start_row=1)]
            st._sample_sheets = [dict(sheet="Sample List", start_row=1)]
        session.add(st)
        submissiontypes[name] = st
    session.commit()

    proceduretypes = {}
    for name, spec in proceduretype_specs.items():
        owners = [st_name for st_name, st_spec in submissiontype_specs.items()
                  if name in st_spec["procedures"]]
        pt = ProcedureType(name=name, plate_rows=spec["rows"],
                           plate_columns=spec["columns"], plate_cost=spec["cost"],
                           submissiontype=[submissiontypes[o] for o in owners])
        pt.resultstype = [resultstypes[r] for r in spec["results"]]
        session.add(pt)
        proceduretypes[name] = pt
    session.commit()

    for name, spec in proceduretype_specs.items():
        pt = proceduretypes[name]
        for iii, role_name in enumerate(spec["reagents"]):
            session.add(ProcedureTypeReagentRoleAssociation(
                proceduretype=pt, reagentrole=reagent_roles[role_name],
                # The last two roles of each type are treated as optional extras.
                _always_used=int(iii < len(spec["reagents"]) - 1)))
        for iii, role_name in enumerate(spec["equipment"]):
            session.add(ProcedureTypeEquipmentRoleAssociation(
                proceduretype=pt, equipmentrole=equipment_roles[role_name],
                _always_used=int(iii == 0)))
    session.commit()

    return submissiontypes, proceduretypes, resultstypes, submissiontype_specs


def seed_discounts(session, labs, proceduretypes):
    from backend.db.models import Discount

    session.add(Discount(clientlab=labs[0], proceduretype=proceduretypes["DNA Extraction"],
                         description="Volume agreement 2026", amount=5.00))
    session.add(Discount(clientlab=labs[1], proceduretype=proceduretypes["qPCR"],
                         description="Surveillance program subsidy", amount=12.50))
    session.commit()


def seed_submissions(session, rng: Random, labs, contacts, submissiontypes,
                     submissiontype_specs, proceduretypes, reagent_roles, reagent_lots,
                     equipment_roles, equipment, processversions, tipslots,
                     resultstypes, submission_count: int):
    """
    The transactional half: submissions -> runs -> procedures -> results.

    Every submission gets samples, one run, and one procedure per procedure type
    of its submission type. Roughly the last quarter of the runs are left
    incomplete so date-range and turnaround queries have both states to chew on.
    """
    from backend.db.models import (ClientSubmission, ClientSubmissionSampleAssociation,
                                   Procedure, ProcedureEquipmentAssociation,
                                   ProcedureEquipmentTipslotAssociation,
                                   ProcedureReagentLotAssociation,
                                   ProcedureSampleAssociation, Results, Run,
                                   RunSampleAssociation, Sample)

    equipment_by_role = {}
    for role_name, role in equipment_roles.items():
        equipment_by_role[role_name] = [assoc.equipment for assoc
                                        in role.equipmentroleequipmentassociation]

    reagent_lots_by_role = {}
    for role_name, role in reagent_roles.items():
        pool = []
        for reagent in role.reagent:
            pool += reagent_lots.get(reagent.name, [])
        reagent_lots_by_role[role_name] = pool

    submissions, runs, samples = [], [], []
    # ``submissiontypes`` also holds the "Default SubmissionType" placeholder, which
    # has no procedures of its own and so gets no submissions.
    type_names = list(submissiontype_specs)

    for iii in range(submission_count):
        type_name = type_names[iii % len(type_names)]
        submissiontype = submissiontypes[type_name]
        abbreviation = submissiontype_specs[type_name]["abbreviation"]
        lab = labs[iii % len(labs)]
        # Walk backwards through time so the newest submissions are last.
        submitted = datetime.now() - timedelta(days=(submission_count - iii) * 3,
                                               hours=rng.randint(0, 8))
        sample_count = rng.choice([8, 12, 16, 24, 32])

        submission = ClientSubmission(
            submitter_plate_id=f"{abbreviation}-PLATE-{2600 + iii}",
            submitted_date=submitted,
            clientlab=lab,
            contact=lab.contact[0],
            submissiontype=submissiontype,
            submission_category="Surveillance" if iii % 2 else "Diagnostic",
            full_batch_size=96,
            cost_centre=lab.cost_centre,
        )
        session.add(submission)
        session.commit()

        submission_samples = []
        for jjj in range(sample_count):
            # Two controls per plate, in the first and last positions.
            is_control = jjj in (0, sample_count - 1)
            sample = Sample(
                sample_id=(f"{abbreviation}-CTRL-{iii:03d}-{jjj:02d}" if is_control
                           else f"{abbreviation}-{submitted:%Y%m%d}-{iii:03d}{jjj:03d}"),
                _is_control=int(is_control),
            )
            session.add(sample)
            submission_samples.append(sample)
            samples.append(sample)
        session.commit()

        for jjj, sample in enumerate(submission_samples):
            session.add(ClientSubmissionSampleAssociation(
                clientsubmission=submission, sample=sample, rank=jjj + 1))
        session.commit()

        # The final quarter of submissions are still in progress.
        in_progress = iii >= submission_count - max(1, submission_count // 4)
        started = submitted + timedelta(days=1)
        run = Run(
            rsl_plate_number=f"RSL-{abbreviation}-{submitted:%y}-{1000 + iii}",
            clientsubmission=submission,
            started_date=started,
        )
        if not in_progress:
            run.completed_date = started + timedelta(days=rng.randint(1, 4))
            run.signed_by = rng.choice(["lwark", "styson", "ruwang"])
            run.comment = [dict(user="lwark", text="Reviewed and released.",
                                time=(started + timedelta(days=5)).isoformat())]
        session.add(run)
        session.commit()

        for jjj, sample in enumerate(submission_samples):
            session.add(RunSampleAssociation(run=run, sample=sample, rank=jjj + 1))
        session.commit()
        runs.append(run)
        submissions.append(submission)

        # In-progress runs carry their full slate of procedures, none of them
        # finished. That shape is only safe because such runs are left unsigned:
        # ``Run.completed_date`` short-circuits on ``if not self._signed_by`` before
        # it reaches ``max([proc.completed_date for proc in self.procedure])``, which
        # still does not drop Nones and so still raises TypeError on any *signed*
        # run whose procedures are not all complete.
        planned = submissiontype_specs[type_name]["procedures"]
        for kkk, pt_name in enumerate(planned):
            proceduretype = proceduretypes[pt_name]
            procedure_started = started + timedelta(days=kkk, hours=rng.randint(1, 6))
            procedure_done = None if in_progress else procedure_started + timedelta(hours=rng.randint(2, 9))
            procedure = Procedure(
                proceduretype=proceduretype,
                run=run,
                started_date=procedure_started,
                completed_date=procedure_done,
                technician=rng.choice(["lwark", "styson", "ruwang", "jsmith"]),
            )
            procedure._cost = proceduretype.plate_cost
            session.add(procedure)
            session.commit()

            # Lay the samples out down the columns of the plate.
            rows = proceduretype.plate_rows or 8
            for jjj, sample in enumerate(submission_samples):
                session.add(ProcedureSampleAssociation(
                    procedure=procedure, sample=sample, rank=jjj + 1,
                    row=(jjj % rows) + 1, column=(jjj // rows) + 1))
            session.commit()

            for role_name in [assoc.reagentrole.name for assoc
                              in proceduretype.proceduretypereagentroleassociation]:
                pool = reagent_lots_by_role.get(role_name) or []
                if not pool:
                    continue
                session.add(ProcedureReagentLotAssociation(
                    procedure=procedure, reagentlot=rng.choice(pool),
                    reagentrole=reagent_roles[role_name]))
            session.commit()

            for role_name in [assoc.equipmentrole.name for assoc
                              in proceduretype.proceduretypeequipmentroleassociation]:
                pool = equipment_by_role.get(role_name) or []
                if not pool:
                    continue
                instrument = rng.choice(pool)
                # Pick a process this instrument's role can actually run.
                runnable = {p.name for assoc in instrument.equipmentequipmentroleassociation
                            for p in assoc.process}
                candidates = [pv for name, pv in processversions.items() if name in runnable]
                assoc = ProcedureEquipmentAssociation(
                    procedure=procedure,
                    equipment=instrument,
                    equipmentrole=equipment_roles[role_name],
                    processversion=rng.choice(candidates) if candidates else None,
                )
                assoc._start_time = procedure_started
                assoc._end_time = procedure_done
                assoc._calibration_date = instrument.calibration_date
                session.add(assoc)
                session.commit()
                # Liquid handlers consume tips; nothing else does.
                if role_name == "Liquid Handler":
                    slot = rng.choice(tipslots[rng.choice(list(tipslots))])
                    session.add(ProcedureEquipmentTipslotAssociation(
                        procedureequipmentassociation=assoc, tipslot=slot))
                    session.commit()

            if in_progress:
                continue

            # One procedure-level result record, plus one per sample.
            for resultstype in proceduretype.resultstype:
                session.add(Results(
                    procedure=procedure,
                    resultstype=resultstype,
                    date_analyzed=procedure_done,
                    result={key: value for key, value in resultstype.info.items()},
                ))
                for assoc in procedure.proceduresampleassociation:
                    result = _fake_sample_result(rng, resultstype.name)
                    if result is None:
                        continue
                    record = Results(
                        procedure=procedure,
                        resultstype=resultstype,
                        sampleprocedureassociation=assoc,
                        date_analyzed=procedure_done,
                        result=result,
                    )
                    record._is_sample = 1
                    session.add(record)
            session.commit()

    return submissions, runs, samples


def _fake_sample_result(rng: Random, resultstype_name: str) -> dict | None:
    """Plausible per-sample values for each results type."""
    match resultstype_name:
        case "Qubit Concentration":
            return dict(concentration=round(rng.uniform(0.5, 85.0), 2), volume=50)
        case "Diomni PCR":
            ct = round(rng.uniform(14.0, 39.5), 2)
            return dict(ct=ct, call="Detected" if ct < 37 else "Not Detected")
        case "Gel Image":
            return dict(band=rng.choice(["Present", "Present", "Present", "Absent"]))
        case _:
            return None


def summarize(session) -> str:
    from backend.db.models import Base

    from sqlalchemy import func, select

    lines = []
    for table in sorted(Base.metadata.tables.values(), key=lambda t: t.name):
        count = session.execute(select(func.count()).select_from(table)).scalar_one()
        lines.append(f"  {table.name:<45} {count:>6}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "dummy_submissions.db",
                        help="path of the sqlite file to create")
    parser.add_argument("--force", action="store_true",
                        help="overwrite the target file if it already exists")
    parser.add_argument("--submissions", type=int, default=12,
                        help="how many client submissions to generate")
    parser.add_argument("--seed", type=int, default=20260818,
                        help="RNG seed, so runs are reproducible")
    parser.add_argument("--faithful-fks", action="store_true",
                        help="emit the schema exactly as the models declare it, without "
                             "adding UNIQUE(_reagentlot.lot). Seeding then has to run with "
                             "foreign keys off, and the app cannot write reagent role "
                             "associations to the result")
    args = parser.parse_args()

    target = args.out.expanduser().resolve()
    if target.exists():
        if not args.force:
            print(f"{target} already exists. Pass --force to replace it.", file=sys.stderr)
            return 1
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)

    ensure_minimal_config()
    if not args.faithful_fks and make_lot_fk_resolvable():
        print("Added UNIQUE(_reagentlot.lot) so the last_used_lot foreign key is valid "
              "under SQLite (pass --faithful-fks to reproduce the models verbatim).")
    engine, session = build_schema(target, enforce_fks=not args.faithful_fks)
    rng = Random(args.seed)

    try:
        seed_config_items(session)
        labs, contacts = seed_organizations(session, rng)
        reagent_roles, reagents, reagent_lots = seed_reagents(session, rng)
        (equipment_roles, equipment, processes,
         processversions, tips, tipslots) = seed_equipment(session, rng)
        (submissiontypes, proceduretypes, resultstypes,
         submissiontype_specs) = seed_types(session, reagent_roles, equipment_roles)
        seed_discounts(session, labs, proceduretypes)
        seed_submissions(session, rng, labs, contacts, submissiontypes,
                         submissiontype_specs, proceduretypes, reagent_roles,
                         reagent_lots, equipment_roles, equipment, processversions,
                         tipslots, resultstypes, args.submissions)
    finally:
        session.commit()

    print(f"\nWrote dummy database to {target}\n")
    print(summarize(session))

    # The connect listener puts sqlite in WAL mode; fold the log back into the
    # main file so the result is a single self-contained .db that can be copied.
    from sqlalchemy import text
    session.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
    session.commit()
    session.remove()
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
