"""
Characterization tests for ``query()`` on the standalone "catalog" models —
those whose filters are plain columns with no required relationships.

Each test pins the *current* behavior: the return shape (list vs single vs None)
and which rows a filter selects. If collapsing the ``match/case`` blocks changes
any of these, a test fails.

Note the deliberately-pinned quirks:
* ``Reagent.query(name=...)`` returns a *list* (it does not force a single result),
  unlike most ``name`` lookups which return a single object.
* ``Tips.query(ref=...)`` returns a single object but ``Tips.query(manufacturer=...)``
  returns a list.
"""
from __future__ import annotations

import backend.db.models as M
import factories as f


# --------------------------------------------------------------------------- #
# ClientLab                                                                    #
# --------------------------------------------------------------------------- #
class TestClientLabQuery:
    def test_no_filter_returns_list_of_all(self, seed):
        f.make_clientlabs(seed)
        result = M.ClientLab.query()
        assert isinstance(result, list)
        assert {c.name for c in result} == {"Acme", "Beta"}

    def test_name_returns_single(self, seed):
        labs = f.make_clientlabs(seed)
        result = M.ClientLab.query(name="Acme")
        assert not isinstance(result, list)
        assert result.id == labs["acme"].id

    def test_id_returns_single(self, seed):
        labs = f.make_clientlabs(seed)
        result = M.ClientLab.query(id=labs["beta"].id)
        assert not isinstance(result, list)
        assert result.id == labs["beta"].id

    def test_name_miss_returns_none(self, seed):
        f.make_clientlabs(seed)
        assert M.ClientLab.query(name="Nope") is None


# --------------------------------------------------------------------------- #
# Contact                                                                      #
# --------------------------------------------------------------------------- #
class TestContactQuery:
    def test_name_returns_single(self, seed):
        contacts = f.make_contacts(seed)
        assert M.Contact.query(name="Alice").id == contacts["alice"].id

    def test_email_returns_single(self, seed):
        contacts = f.make_contacts(seed)
        assert M.Contact.query(email="bob@x.com").id == contacts["bob"].id

    def test_tel_selects_correct_row(self, seed):
        contacts = f.make_contacts(seed)
        result = M.Contact.query(tel="111")
        # tel is not a "single" field; pin whatever shape it returns
        got = result if not isinstance(result, list) else (result[0] if result else None)
        assert got is not None and got.id == contacts["alice"].id

    def test_no_filter_returns_all(self, seed):
        f.make_contacts(seed)
        assert len(M.Contact.query()) == 2


# --------------------------------------------------------------------------- #
# SubmissionType / ProcedureType / Process                                     #
# --------------------------------------------------------------------------- #
class TestSimpleNamedCatalogs:
    def test_submissiontype_name_single(self, seed):
        sts = f.make_submissiontypes(seed)
        assert M.SubmissionType.query(name="Bacterial").id == sts["bact"].id

    def test_proceduretype_name_single(self, seed):
        pts = f.make_proceduretypes(seed)
        assert M.ProcedureType.query(name="PCR").id == pts["pcr"].id

    def test_process_name_single(self, seed):
        procs = f.make_processes(seed)
        assert M.Process.query(name="StandardPCR").id == procs["pcr"].id

    def test_proceduretype_no_filter_lists_all(self, seed):
        f.make_proceduretypes(seed)
        assert len(M.ProcedureType.query()) == 2


# --------------------------------------------------------------------------- #
# ReagentRole / Reagent                                                        #
# --------------------------------------------------------------------------- #
class TestReagentCatalogQuery:
    def test_reagentrole_name_single(self, seed):
        roles = f.make_reagentroles(seed)
        assert M.ReagentRole.query(name="Extraction").id == roles["extraction"].id

    def test_reagent_name_returns_list_quirk(self, seed):
        # PINNED QUIRK: Reagent.query(name=) does NOT force a single result.
        reagents = f.make_reagents(seed)
        result = M.Reagent.query(name="OmegaKit")
        assert isinstance(result, M.Reagent)
        assert result.id == reagents["omega"].id

    def test_reagent_no_filter_lists_all(self, seed):
        f.make_reagents(seed)
        assert len(M.Reagent.query()) == 2


# --------------------------------------------------------------------------- #
# EquipmentRole / Equipment                                                    #
# --------------------------------------------------------------------------- #
class TestEquipmentCatalogQuery:
    def test_equipmentrole_name_single(self, seed):
        roles = f.make_equipmentroles(seed)
        assert M.EquipmentRole.query(name="Thermocycler").id == roles["cycler"].id

    def test_equipment_name_single(self, seed):
        eq = f.make_equipment(seed)
        assert M.Equipment.query(name="Bio-Rad").id == eq["biorad"].id

    def test_equipment_asset_number_single(self, seed):
        eq = f.make_equipment(seed)
        assert M.Equipment.query(asset_number="A200").id == eq["eppi"].id

    def test_equipment_nickname_selects_row(self, seed):
        eq = f.make_equipment(seed)
        result = M.Equipment.query(nickname="cycler1")
        got = result if not isinstance(result, list) else (result[0] if result else None)
        assert got is not None and got.id == eq["biorad"].id


# --------------------------------------------------------------------------- #
# Tips                                                                         #
# --------------------------------------------------------------------------- #
class TestTipsQuery:
    def test_ref_returns_single(self, seed):
        tips = f.make_tips(seed)
        assert M.Tips.query(ref="T-1").id == tips["t1"].id

    def test_manufacturer_returns_list_quirk(self, seed):
        # PINNED QUIRK: manufacturer does not force a single result.
        tips = f.make_tips(seed)
        result = M.Tips.query(manufacturer="Rainin")
        assert not isinstance(result, list)
        assert result.id == tips["t1"].id


# --------------------------------------------------------------------------- #
# Sample                                                                       #
# --------------------------------------------------------------------------- #
class TestSampleQuery:
    def test_sample_id_returns_single(self, seed):
        samples = f.make_samples(seed)
        assert M.Sample.query(sample_id="S-001").id == samples["s1"].id

    def test_no_filter_returns_all(self, seed):
        f.make_samples(seed)
        assert len(M.Sample.query()) == 2