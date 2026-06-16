"""
Fixture builders for the query characterization suite.

Every helper takes the ``seed`` callable (from ``conftest``) and inserts rows via
Core inserts, returning the ORM objects. They build only as much of the relational
graph as a given query method needs, keeping each test's setup small and readable.
"""
from __future__ import annotations

import backend.db.models as M


# --- standalone catalog rows ------------------------------------------------ #
def make_clientlabs(seed):
    return {
        "acme": seed(M.ClientLab, name="Acme"),
        "beta": seed(M.ClientLab, name="Beta"),
    }


def make_contacts(seed):
    return {
        "alice": seed(M.Contact, name="Alice", email="alice@x.com", tel="111"),
        "bob": seed(M.Contact, name="Bob", email="bob@x.com", tel="222"),
    }


def make_submissiontypes(seed):
    return {
        "bact": seed(M.SubmissionType, name="Bacterial"),
        "viral": seed(M.SubmissionType, name="Viral"),
    }


def make_proceduretypes(seed):
    return {
        "pcr": seed(M.ProcedureType, name="PCR"),
        "wgs": seed(M.ProcedureType, name="WGS"),
    }


def make_reagentroles(seed):
    return {
        "extraction": seed(M.ReagentRole, name="Extraction"),
        "mastermix": seed(M.ReagentRole, name="Mastermix"),
    }


def make_reagents(seed):
    return {
        "omega": seed(M.Reagent, name="OmegaKit", manufacturer="Omega"),
        "qiagen": seed(M.Reagent, name="Qiagen", manufacturer="Qiagen"),
    }


def make_equipmentroles(seed):
    return {
        "cycler": seed(M.EquipmentRole, name="Thermocycler"),
        "hood": seed(M.EquipmentRole, name="Hood"),
    }


def make_equipment(seed):
    return {
        "biorad": seed(M.Equipment, name="Bio-Rad", asset_number="A100", _nickname="cycler1"),
        "eppi": seed(M.Equipment, name="Eppendorf", asset_number="A200", _nickname="cycler2"),
    }


def make_processes(seed):
    return {
        "pcr": seed(M.Process, name="StandardPCR"),
        "wgs": seed(M.Process, name="StandardWGS"),
    }


def make_tips(seed):
    return {
        "t1": seed(M.Tips, ref="T-1", manufacturer="Rainin", capacity=200),
        "t2": seed(M.Tips, ref="T-2", manufacturer="Sartorius", capacity=1000),
    }


def make_samples(seed):
    return {
        "s1": seed(M.Sample, sample_id="S-001"),
        "s2": seed(M.Sample, sample_id="S-002"),
    }


# --- rows with relationships ------------------------------------------------ #
def make_reagentlots(seed, reagent):
    """Two lots of one reagent, for relationship-coercion tests on ReagentLot."""
    return {
        "lot1": seed(M.ReagentLot, lot="LOT1", reagent_id=reagent.id),
        "lot2": seed(M.ReagentLot, lot="LOT2", reagent_id=reagent.id),
    }


def make_tipslots(seed, tips):
    return {
        "tl1": seed(M.TipsLot, lot="TLOT1", tips_id=tips.id),
        "tl2": seed(M.TipsLot, lot="TLOT2", tips_id=tips.id),
    }


def make_processversions(seed, process):
    return {
        "v1": seed(M.ProcessVersion, version="1.0", process_id=process.id),
        "v2": seed(M.ProcessVersion, version="2.0", process_id=process.id),
    }


def make_discounts(seed, clientlab, proceduretype):
    return {
        "d1": seed(M.Discount, clientlab_id=clientlab.id,
                   proceduretype_id=proceduretype.id, amount=10.0,
                   description="bulk"),
    }


# --- submissions graph ------------------------------------------------------ #
def make_submission(seed, clientlab=None, submissiontype=None, contact=None,
                    plate_id="SUB-001"):
    return seed(
        M.ClientSubmission,
        _submitter_plate_id=plate_id,
        clientlab_id=getattr(clientlab, "id", None),
        contact_id=getattr(contact, "id", None),
        submissiontype_name=getattr(submissiontype, "name", None),
    )


def make_run(seed, submission, plate="RSL-001"):
    return seed(M.Run, _rsl_plate_number=plate, clientsubmission_id=submission.id)


def link_sample_to_submission(seed, submission, sample, rank=1):
    return seed(
        M.ClientSubmissionSampleAssociation,
        clientsubmission_id=submission.id,
        sample_id=sample.id,
        submission_rank=rank,
    )


def link_sample_to_run(seed, run, sample, rank=1):
    return seed(
        M.RunSampleAssociation,
        run_id=run.id,
        sample_id=sample.id,
        run_rank=rank,
    )


# --- procedure graph + junctions ------------------------------------------- #
def make_procedure(seed, run, proceduretype):
    return seed(M.Procedure, run_id=run.id, proceduretype_id=proceduretype.id)


def make_procedure_reagentlot(seed, procedure, reagentlot, reagentrole):
    return seed(
        M.ProcedureReagentLotAssociation,
        procedure_id=procedure.id,
        reagentlot_id=reagentlot.id,
        reagentrole_id=reagentrole.id,
    )


def make_proceduretype_reagentrole(seed, proceduretype, reagentrole):
    # last_used_lot FK targets a non-unique column, so FK enforcement is bypassed.
    return seed(
        M.ProcedureTypeReagentRoleAssociation,
        fk_checks=False,
        proceduretype_id=proceduretype.id,
        reagentrole_id=reagentrole.id,
    )


def make_equipmentrole_equipment(seed, equipmentrole, equipment):
    return seed(
        M.EquipmentRoleEquipmentAssociation,
        equipmentrole_id=equipmentrole.id,
        equipment_id=equipment.id,
    )


def make_proceduretype_equipmentrole(seed, proceduretype, equipmentrole):
    return seed(
        M.ProcedureTypeEquipmentRoleAssociation,
        proceduretype_id=proceduretype.id,
        equipmentrole_id=equipmentrole.id,
    )


def make_procedure_equipment(seed, procedure, equipment, equipmentrole):
    return seed(
        M.ProcedureEquipmentAssociation,
        procedure_id=procedure.id,
        equipment_id=equipment.id,
        equipmentrole_id=equipmentrole.id,
    )


def make_procedure_sample(seed, procedure, sample, rank=1, _id=1):
    # ProcedureSampleAssociation.id does not autoincrement under Core insert.
    return seed(
        M.ProcedureSampleAssociation,
        id=_id,
        procedure_id=procedure.id,
        sample_id=sample.id,
        procedure_rank=rank,
    )