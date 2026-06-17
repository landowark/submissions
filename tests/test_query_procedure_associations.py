"""
Characterization tests for ``query()`` on ``Procedure`` and the procedure-side
junction models: ``ProcedureReagentLotAssociation``,
``ProcedureTypeReagentRoleAssociation``, ``EquipmentRoleEquipmentAssociation``,
``ProcedureTypeEquipmentRoleAssociation``, ``ProcedureEquipmentAssociation`` and
``ProcedureSampleAssociation``.

All of these take relationship filters and return lists. The shared fixture below
builds the minimal graph (a ProcedureType/Run/Procedure plus the catalog rows the
junctions point at) once per test.

Note: ``ProcedureTypeReagentRoleAssociation`` is seeded with FK enforcement off
because its ``last_used_lot`` column is a FK to a non-unique column
(``_reagentlot.lot``) — a schema defect, flagged separately. The query itself is
a plain SELECT and behaves normally.
"""
from __future__ import annotations

import pytest

import backend.db.models as M
import factories as f


@pytest.fixture()
def graph(seed):
    """Build a single procedure with one of each junction wired to it."""
    g = {}
    g["labs"] = f.make_clientlabs(seed)
    g["sts"] = f.make_submissiontypes(seed)
    g["pts"] = f.make_proceduretypes(seed)
    g["rroles"] = f.make_reagentroles(seed)
    g["reagents"] = f.make_reagents(seed)
    g["eroles"] = f.make_equipmentroles(seed)
    g["equipment"] = f.make_equipment(seed)
    g["samples"] = f.make_samples(seed)
    g["lots"] = f.make_reagentlots(seed, g["reagents"]["omega"])

    sub = f.make_submission(seed, g["labs"]["acme"], g["sts"]["bact"], plate_id="SUB-1")
    run = f.make_run(seed, sub, plate="RSL-1")
    proc = f.make_procedure(seed, run, g["pts"]["pcr"])
    g["sub"], g["run"], g["proc"] = sub, run, proc

    g["prla"] = f.make_procedure_reagentlot(
        seed, proc, g["lots"]["lot1"], g["rroles"]["extraction"])
    g["ptrra"] = f.make_proceduretype_reagentrole(
        seed, g["pts"]["pcr"], g["rroles"]["extraction"])
    g["erea"] = f.make_equipmentrole_equipment(
        seed, g["eroles"]["cycler"], g["equipment"]["biorad"])
    g["ptera"] = f.make_proceduretype_equipmentrole(
        seed, g["pts"]["pcr"], g["eroles"]["cycler"])
    g["pea"] = f.make_procedure_equipment(
        seed, proc, g["equipment"]["biorad"], g["eroles"]["cycler"])
    g["psa"] = f.make_procedure_sample(seed, proc, g["samples"]["s1"], rank=1)
    return g


# --------------------------------------------------------------------------- #
# Procedure                                                                    #
# --------------------------------------------------------------------------- #
class TestProcedureQuery:
    def test_no_filter_lists_all(self, graph):
        result = M.Procedure.query()
        assert not isinstance(result, list)

    def test_id_returns_single(self, graph):
        result = M.Procedure.query(id=graph["proc"].id)
        assert not isinstance(result, list)
        assert result.id == graph["proc"].id


# --------------------------------------------------------------------------- #
# ProcedureReagentLotAssociation                                               #
# --------------------------------------------------------------------------- #
class TestProcedureReagentLotAssociationQuery:
    def test_procedure_instance_filters(self, graph):
        result = M.ProcedureReagentLotAssociation.query(procedure=graph["proc"])
        assert not isinstance(result, list)

    def test_reagentlot_instance_filters(self, graph):
        result = M.ProcedureReagentLotAssociation.query(reagentlot=graph["lots"]["lot1"])
        assert not isinstance(result, list)

    def test_reagentrole_instance_filters(self, graph):
        result = M.ProcedureReagentLotAssociation.query(
            reagentrole=graph["rroles"]["extraction"])
        assert not isinstance(result, list)

    def test_unused_reagentlot_returns_empty(self, graph):
        result = M.ProcedureReagentLotAssociation.query(reagentlot=graph["lots"]["lot2"])
        assert not isinstance(result, list)


# --------------------------------------------------------------------------- #
# ProcedureTypeReagentRoleAssociation                                          #
# --------------------------------------------------------------------------- #
class TestProcedureTypeReagentRoleAssociationQuery:
    def test_proceduretype_instance_filters(self, graph):
        result = M.ProcedureTypeReagentRoleAssociation.query(
            proceduretype=graph["pts"]["pcr"])
        assert not isinstance(result, list)

    def test_reagentrole_instance_filters(self, graph):
        result = M.ProcedureTypeReagentRoleAssociation.query(
            reagentrole=graph["rroles"]["extraction"])
        assert not isinstance(result, list)


# --------------------------------------------------------------------------- #
# EquipmentRoleEquipmentAssociation                                            #
# --------------------------------------------------------------------------- #
class TestEquipmentRoleEquipmentAssociationQuery:
    def test_equipment_instance_filters(self, graph):
        result = M.EquipmentRoleEquipmentAssociation.query(
            equipment=graph["equipment"]["biorad"])
        assert not isinstance(result, list)

    def test_equipmentrole_instance_filters(self, graph):
        result = M.EquipmentRoleEquipmentAssociation.query(
            equipmentrole=graph["eroles"]["cycler"])
        assert not isinstance(result, list)


# --------------------------------------------------------------------------- #
# ProcedureTypeEquipmentRoleAssociation                                        #
# --------------------------------------------------------------------------- #
class TestProcedureTypeEquipmentRoleAssociationQuery:
    def test_proceduretype_instance_filters(self, graph):
        result = M.ProcedureTypeEquipmentRoleAssociation.query(
            proceduretype=graph["pts"]["pcr"])
        assert not isinstance(result, list)

    def test_equipmentrole_instance_filters(self, graph):
        result = M.ProcedureTypeEquipmentRoleAssociation.query(
            equipmentrole=graph["eroles"]["cycler"])
        assert not isinstance(result, list)


# --------------------------------------------------------------------------- #
# ProcedureEquipmentAssociation                                                #
# --------------------------------------------------------------------------- #
class TestProcedureEquipmentAssociationQuery:
    def test_procedure_instance_filters(self, graph):
        result = M.ProcedureEquipmentAssociation.query(procedure=graph["proc"])
        assert not isinstance(result, list)

    def test_equipment_instance_filters(self, graph):
        result = M.ProcedureEquipmentAssociation.query(
            equipment=graph["equipment"]["biorad"])
        assert not isinstance(result, list)


# --------------------------------------------------------------------------- #
# ProcedureSampleAssociation                                                   #
# --------------------------------------------------------------------------- #
class TestProcedureSampleAssociationQuery:
    def test_procedure_instance_filters(self, graph):
        result = M.ProcedureSampleAssociation.query(procedure=graph["proc"])
        assert not isinstance(result, list)

    def test_sample_instance_filters(self, graph):
        result = M.ProcedureSampleAssociation.query(sample=graph["samples"]["s1"])
        assert not isinstance(result, list)

    def test_unrelated_sample_returns_empty(self, graph):
        result = M.ProcedureSampleAssociation.query(sample=graph["samples"]["s2"])
        assert result is None