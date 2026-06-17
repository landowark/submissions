"""
Characterization tests for ``query()`` on models whose filters include
relationships or depend on a parent row: ``ReagentLot``, ``TipsLot``,
``ProcessVersion`` and ``Discount``.

These exercise the relationship-coercion path in particular — passing a filter as
either a model *instance* or its *name string* — which is the most intricate part
of the ``match/case`` blocks being collapsed.

Pinned behaviors confirmed against the live models:
* ``ReagentLot.query(lot=...)`` -> single object; ``ReagentLot.query(name=...)``
  -> ``None`` (the ``name`` hybrid is not the lot string, so it never matches a
  bare lot value).
* ``ReagentLot.query(reagent=<instance|"name">)`` -> list of that reagent's lots.
* ``TipsLot.query(name=...)`` -> ``None`` (same reasoning as ReagentLot).
* ``ProcessVersion.query(name=...)`` matches the *version*, not the process name,
  so a process name returns an empty list.
"""
from __future__ import annotations

import backend.db.models as M
import factories as f


# --------------------------------------------------------------------------- #
# ReagentLot                                                                   #
# --------------------------------------------------------------------------- #
class TestReagentLotQuery:
    def _setup(self, seed):
        reagents = f.make_reagents(seed)
        lots = f.make_reagentlots(seed, reagents["omega"])
        return reagents, lots

    def test_lot_returns_single(self, seed):
        _, lots = self._setup(seed)
        result = M.ReagentLot.query(lot="LOT1")
        assert not isinstance(result, list)
        assert result.id == lots["lot1"].id

    def test_no_filter_lists_all(self, seed):
        self._setup(seed)
        assert len(M.ReagentLot.query()) == 2

    def test_name_does_not_match_bare_lot(self, seed):
        # PINNED: ReagentLot.name is not the lot string, so name="LOT1" misses.
        self._setup(seed)
        assert M.ReagentLot.query(name="LOT1") is None

    def test_reagent_by_instance_returns_its_lots(self, seed):
        reagents, lots = self._setup(seed)
        result = M.ReagentLot.query(reagent=reagents["omega"])
        assert isinstance(result, list)
        assert {r.id for r in result} == {lots["lot1"].id, lots["lot2"].id}

    def test_reagent_by_name_string_matches_instance(self, seed):
        # The string-coercion branch must resolve to the same rows as the
        # instance branch — the key invariant when collapsing the match blocks.
        reagents, _ = self._setup(seed)
        by_instance = M.ReagentLot.query(reagent=reagents["omega"])
        by_string = M.ReagentLot.query(reagent="OmegaKit")
        assert {r.id for r in by_string} == {r.id for r in by_instance}

    def test_reagent_no_match_returns_empty(self, seed):
        # _setup seeds both OmegaKit (with lots) and Qiagen (without any lots).
        self._setup(seed)
        result = M.ReagentLot.query(reagent="Qiagen")
        assert result is None


# --------------------------------------------------------------------------- #
# TipsLot                                                                      #
# --------------------------------------------------------------------------- #
class TestTipsLotQuery:
    def test_lot_returns_single(self, seed):
        tips = f.make_tips(seed)
        lots = f.make_tipslots(seed, tips["t1"])
        result = M.TipsLot.query(lot="TLOT1")
        assert not isinstance(result, list)
        assert result.id == lots["tl1"].id

    def test_name_does_not_match_bare_lot(self, seed):
        tips = f.make_tips(seed)
        f.make_tipslots(seed, tips["t1"])
        assert M.TipsLot.query(name="TLOT1") is None

    def test_no_filter_lists_all(self, seed):
        tips = f.make_tips(seed)
        f.make_tipslots(seed, tips["t1"])
        assert len(M.TipsLot.query()) == 2


# --------------------------------------------------------------------------- #
# ProcessVersion                                                               #
# --------------------------------------------------------------------------- #
class TestProcessVersionQuery:
    def test_version_filter_selects_row(self, seed):
        procs = f.make_processes(seed)
        versions = f.make_processversions(seed, procs["pcr"])
        result = M.ProcessVersion.query(version="1.0")
        ids = [r.id for r in result] if isinstance(result, list) else [result.id]
        assert versions["v1"].id in ids

    def test_process_name_does_not_match_version_name(self, seed):
        # PINNED: name filters the version label, not the parent process name.
        procs = f.make_processes(seed)
        f.make_processversions(seed, procs["pcr"])
        result = M.ProcessVersion.query(name="StandardPCR")
        assert not isinstance(result, list)

    def test_no_filter_lists_all(self, seed):
        procs = f.make_processes(seed)
        f.make_processversions(seed, procs["pcr"])
        assert len(M.ProcessVersion.query()) == 2


# --------------------------------------------------------------------------- #
# Discount                                                                     #
# --------------------------------------------------------------------------- #
class TestDiscountQuery:
    def _setup(self, seed):
        labs = f.make_clientlabs(seed)
        pts = f.make_proceduretypes(seed)
        discounts = f.make_discounts(seed, labs["acme"], pts["pcr"])
        return labs, pts, discounts

    def test_clientlab_instance_selects_discount(self, seed):
        labs, _, discounts = self._setup(seed)
        result = M.Discount.query(clientlab=labs["acme"])
        assert not isinstance(result, list)
        assert hasattr(result, "id")

    def test_proceduretype_instance_selects_discount(self, seed):
        _, pts, discounts = self._setup(seed)
        result = M.Discount.query(proceduretype=pts["pcr"])
        assert not isinstance(result, list)
        assert hasattr(result, "id")

    def test_clientlab_with_no_discount_returns_empty(self, seed):
        labs, _, _ = self._setup(seed)
        result = M.Discount.query(clientlab=labs["beta"])
        assert result is None