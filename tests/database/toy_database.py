"""Utility to create an in-memory toy database for tests.

Usage:
    from backend.db.toy_database import make_toy_db
    engine, session = make_toy_db(populate=True)

This module dynamically imports all modules from `backend.db.models`, creates
an in-memory SQLite engine, binds a Session, assigns it to `tools.ctx.database_session`
so model classmethods that expect `ctx.database_session` will work, then
creates all tables from the declarative base. Optionally it will insert a
small set of fixture rows.
"""
from __future__ import annotations
from datetime import date, timedelta
from pprint import pformat
import os, sys, logging
sys.path.append("C:\\Users\\lwark\\Documents\\python\\submissions\\src\\submissions")
# os.chdir("C:\\Users\\lwark\\Documents\\python\\submissions\\src\\submissions")
import pkgutil
import importlib
from typing import Tuple

from sqlalchemy import JSON, create_engine, Table, Column, INTEGER, String, MetaData, TIMESTAMP
from sqlalchemy.orm import sessionmaker, Session
# from .custom_resources import Reagent

logger = logging.getLogger(f"testing.{__name__}")

def _import_all_model_submodules(package) -> None:
    """Import all submodules in a package so model classes are registered.

    package: the imported package object (backend.db.models)
    """
    path = getattr(package, "__path__", None)
    if not path:
        return
    for finder, name, ispkg in pkgutil.iter_modules(path):
        # skip underscore-hidden modules if any
        if name.startswith("__"):
            continue
        importlib.import_module(f"{package.__name__}.{name}")


def make_toy_db(populate: bool = False) -> Tuple[object, Session]:
    """Create an in-memory SQLite DB wired to this project's models.

    Returns: (engine, session)
    """
    # Import models package and all submodules so declarative classes are
    # registered against the Base.
    # from tools import ctx
    import backend.db.models as models_pkg
    from tools import ctx

    _import_all_model_submodules(models_pkg)

    # The package defines Base via declarative_base()
    try:
        Base = getattr(models_pkg, "Base")
    except AttributeError:
        raise RuntimeError("Could not find Base in backend.db.models")

    # Create in-memory sqlite engine and session
    engine = create_engine("sqlite:///:memory:", echo=False, future=True)
    # Keep objects populated after commit for easier inspection in tests
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    session = SessionLocal()

    # Attach session to ctx so model classmethods that read ctx.database_session work
    try:
        ctx.database_session = session
    except Exception:
        # If ctx is a simple object without attribute assignment support, set as attribute anyway
        setattr(ctx, "database_session", session)

    # Create all tables
    audit_log = Table("_auditlog", Base.metadata, 
                      Column("id", INTEGER, primary_key=True, autoincrement=True),
                      Column("user", String(64)),
                      Column("time", TIMESTAMP),
                      Column("object", String(64)),
                      Column("changes", JSON),
                      extend_existing=True
                      )
    Base.metadata.create_all(bind=engine)

    created = {}
    if populate:
        try:
            created = _populate_minimal(session, models_pkg)
        except Exception:
            # don't fail creation if populate has issues; return session for caller to inspect
            pass
    # print("Created toy database with objects:", pformat(created))
    return engine, session


def _populate_minimal(session: Session, models_pkg) -> dict:
    """Insert a tiny set of fixture rows for common models.

    This keeps the dataset minimal so tests can rely on a few known rows.
    """
    BaseClass = getattr(models_pkg, "BaseClass")
    # modules = [org_mod, proc_mod, subs_mod]
    order_list = [
        "ClientLab",
        "Contact",
        "SubmissionType",
        "ProcedureType",
        "ReagentRole",
        "Reagent",
        "ReagentLot",
        "EquipmentRole",
        "Equipment",
        "Process",
        "ProcessVersion",
        "Tips",
        "TipsLot",
        "Sample",
        "ClientSubmission",
        "Run",
        "Procedure",
        "ResultsType",
        "Results"
    ]
    models = {cl.__qualname__: cl for cl in BaseClass.find_subclasses()}
    created = {}
    
    for item in order_list:
        model: BaseClass = models.get(item)
        
        try:
            match model.__name__:
                case "ClientLab":
                    instance = model(
                        name="Test Lab", 
                        cost_centre="XXXXXX", 
                    )
                    instance.contact=created.get("Contact", None)

                case "Contact":
                    instance = model(
                        name="Johnny Test",
                        email="jtest@email.com",
                        tel="(555) 555-5555"
                    )
                    instance.clientlab = created.get("ClientLab", None)
                    
                case "SubmissionType":
                    instance = model(
                        # NOTE: must be named Default SubmissionType to prevent errors in ProcedureType
                        name="Default SubmissionType",
                        defaults = {},
                        file_name_template="{{rsl_plate_number}}{% if _clientsubmission %}_{{_clientsubmission.submitter_plate_id}}{% endif %}_{{_completed_date}}",
                        regex=None,
                    )
                    instance.turnaround_time=5
                    instance.abbreviation="XX"
                    instance.clientsubmission=created.get("ClientSubmission", None)
                    instance.proceduretype=created.get("ProcedureType", None)
                    
                case "ProcedureType":
                    instance = model(
                        name="Test ProcedureType",
                        plate_columns=12,
                        plate_rows=8,
                        plate_cost=1.00,
                    )
                    instance.procedure=created.get("Procedure", [])
                    instance.submissiontype=created.get("SubmissionType", [])
                    instance.resultstype=created.get("ResultsType", [])
                    instance.discount=created.get("Discount", [])
                    instance.equipmentrole=created.get("EquipmentRole", [])
                    instance.reagentrole = created.get("ReagentRole", [])

                case "ReagentRole":
                    instance = model(
                        name="Test ReagentRole"
                    )
                    instance.proceduretype=created.get("ProcedureType", [])
                    instance.reagent=created.get("Reagent", [])
                    
                case "Reagent":
                    instance = model(
                        name="Test Solution",
                        cost_per_ml=0.50
                    )
                    instance.eol_ext = 30
                    instance.reagentlot=created.get("ReagentLot", [])
                    reagentrole=created.get("ReagentRole", [])
                    if reagentrole:
                        from backend.db.models import ReagentRoleReagentAssociation
                        assoc = ReagentRoleReagentAssociation(reagentrole=reagentrole, reagent=instance, ml_used_per_sample=0.5)
                    

                case "ReagentLot":
                    instance = model(
                        lot="012345",
                        active=True
                    )
                    instance.expiry=date(year=date.today().year + 1, month=date.today().month, day=date.today().day)
                    instance.reagent=created.get("Reagent", None)
                    instance.procedure=created.get("Procedure", [])
                    
                case "Procedure":
                    instance = model(
                        completed_date=date.today(),
                        started_date=date.today() - timedelta(days=1),
                        technician="Bob Redshirt",
                        results=[])
                    instance.proceduretype=created.get("ProcedureType", None)
                    instance.run=created.get("Run", None)
                    instance.sample=created.get("Sample", [])
                    instance.reagentlot=created.get("ReagentLot", [])
                    instance.procedurereagentlotassociation[0].reagentrole = created.get("ReagentRole", None)
                    instance.equipment=created.get("Equipment", [])
                    instance.procedureequipmentassociation[0].equipmentrole = created.get("EquipmentRole", None)
                    instance.procedureequipmentassociation[0].processversion = created.get("ProcessVersion", None)
                    tipslot = created.get("TipsLot", [])
                    if tipslot:
                        tipslot.procedureequipmenttipslotassociation=instance.procedureequipmentassociation[0]
                    
                case "EquipmentRole":
                    instance = model(
                        name="Test EquipmentRole"
                    )
                    instance.proceduretype=created.get("ProcedureType", [])
                    instance.equipment=created.get("Equipment", [])
                    
                case "Equipment":
                    instance = model(
                        name="Test Instrument",
                        nickname="Testerino",
                        asset_number="000000"
                    )
                    instance.procedure=created.get("Procedure", [])
                    instance.equipmentrole=created.get("EquipmentRole", [])
                    
                case "Process":
                    assoc = created.get("EquipmentRole", None)
                    if not assoc:
                        assoc = created.get("Equipment", None)
                        try:
                            assoc = assoc.equipmentequipmentroleassociation[0]
                        except IndexError:
                            assoc = None
                    else:
                        assoc = assoc.equipmentroleequipmentassociation[0]
                    instance = model(
                        name="Test Process"
                    )
                    instance.tips=created.get("Tips", [])
                    instance.processversion=created.get("ProcessVersion", [])
                    instance.equipmentroleequipmentassociation=assoc

                case "ProcessVersion":
                    assoc = created.get("Procedure", None)
                    if not assoc:
                        assoc = created.get("Equipment", None)
                        try:
                            assoc = assoc.equipmentprocedureassociation
                        except IndexError:
                            assoc = None
                    else:
                        assoc = assoc.procedureequipmentassociation
                    instance = model(
                        version=1.0,
                        date_verified=date.today(),
                        project="NA",
                        active=True
                    )
                    instance.process=created.get("Process", None)
                    instance.procedureequipmentassociation=assoc
                    
                case "Tips":
                    instance = model(
                        manufacturer="ACME Tips",
                        capacity=1000,
                        ref="XXXX"
                    )
                    instance.tipslot=created.get("TipsLot", [])
                    instance.process=created.get("Process", [])
                    
                case "TipsLot":
                    instance = model(
                        lot="098765",
                        expiry=date(year=date.today().year + 1, month=date.today().month, day=date.today().day),
                        active=True
                    )
                    instance.tips=created.get("Tips", None)
                case "ResultsType":
                    instance = model(
                        name="Test ResultsType",
                        info={},
                        samples={}
                    )
                    instance.results=created.get("Results", [])
                    instance.proceduretype=created.get("ProcedureType", [])
                    
                case "Results":
                    assoc = created.get("Procedure", None)
                    if not assoc:
                        assoc = created.get("Sample", None)
                        try:
                            assoc = assoc.sampleprocedureassociation[0]
                        except IndexError:
                            pass
                    else:
                        assoc = assoc.proceduresampleassociation[0]
                    instance = model(
                        result={},
                        date_analyzed=date.today(),
                        procedure=None,
                        img=None
                    )
                    instance.sampleprocedureassociation=assoc
                    instance.resultstype=created.get("ResultsType", None)
                    
                case "ClientSubmission":
                    instance = model(
                        submitter_plate_id="Test ClientSubmission",
                        submitted_date=date.today() - timedelta(days=1),
                        submission_category="Test Category",
                        full_batch_size=96,
                        comments = {},
                        cost_centre="XXXXXX"
                    )
                    instance.clientlab=created.get("ClientLab", None)
                    instance.run=created.get("Run", None)
                    instance.contact=created.get("Contact", None)
                    instance.submissiontype=created.get("SubmissionType", None)
                    instance.sample=created.get("Sample", None)
                    
                case "Run":
                    instance = model(
                        rsl_plate_number="RSL-XX-20260202-1",
                        
                        completed_date=date.today(),
                        started_date=date.today() - timedelta(days=1),
                        comment={}
                    )
                    instance.clientsubmission=created.get("ClientSubmission", None)
                    instance.procedure=created.get("Procedure", [])
                    instance.sample=created.get("Sample", [])
                case "Sample":
                    instance = model(
                        sample_id="Test Sample",
                        is_control=True
                    )
                    instance.clientsubmission=created.get("ClientSubmission", [])
                    instance.run=created.get("Run", [])
                    instance.procedure=created.get("Procedure", [])
                case _:
                    print(f"Unmatched Model {model.__name__}")
                    continue
        except Exception as e:
            instance = None
        try:
            # instance = obj(**{k: v for k, v in kwargs.items() if v is not None})
            session.add(instance)
            session.flush()  # get PKs where possible
            created[model.__name__] = instance
        except Exception as e:
            # If the simple creation fails, rollback the session to a
            # clean state and continue with other classes.
            logger.error(f"Error creating fixture for {model.__name__}: {e}")
            session.rollback()
            created[model.__name__] = None
            continue

    try:
        session.commit()
    except Exception:
        session.rollback()
    # return the list of created objects for inspection if caller wants it
    return created
    


if __name__ == "__main__":
    e, s = make_toy_db(populate=True)
    print("Toy DB ready", e, s)
