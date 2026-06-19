"""
Characterization tests for ``query_or_create`` across BaseClass subclasses.

Two distinct contracts are pinned here, because the codebase has two:

* The **base** ``BaseClass.query_or_create`` (used by every class except the two
  sample-association junctions) returns a ``(instance, is_new)`` tuple. It filters
  kwargs to mapped fields, looks up by the scalar ones via ``cls.query``, and
  creates a transient instance (not persisted) when nothing matches.

* The two **sample-association** overrides
  (``ClientSubmissionSampleAssociation``, ``RunSampleAssociation``) delegate to
  ``_query_or_create_sample_link`` and return a *bare instance* (no tuple). They
  coerce parent/sample from strings, and raise ``ValueError`` when either is
  missing or unresolvable.

These tests share the existing ``conftest`` harness and ``factories`` builders;
they add no fixtures of their own and use distinct class names so they don't
collide with the ``query`` suite.

Pinned quirk worth noting: in the base, a relationship filter passed as a *string*
(e.g. ``reagent="OmegaKit"``) does NOT find an existing row — it creates a new
one. The lookup resolves the string fine, but the post-lookup "does this instance
match every field" check compares the resolved relationship object against the
raw string and fails, forcing a create. Passing the relationship as an *instance*
works as expected. The string case is captured below so the behavior is visible
and any future fix is a deliberate, test-changing decision.
"""
from __future__ import annotations

import pytest

import backend.db.models as M
import factories as f


def _count(cls) -> int:
    """Robust row count that doesn't depend on query()'s return shape."""
    return cls.__database_session__.query(cls).count()


# --------------------------------------------------------------------------- #
# Base BaseClass.query_or_create — (instance, is_new) contract                 #
# --------------------------------------------------------------------------- #
class TestBaseQueryOrCreate:
    def test_returns_instance_new_tuple(self, seed):
        f.make_clientlabs(seed)
        result = M.ClientLab.query_or_create(name="Acme")
        assert isinstance(result, tuple) and len(result) == 2
        instance, is_new = result
        assert isinstance(instance, M.ClientLab) and isinstance(is_new, bool)

    def test_finds_existing_by_scalar(self, seed):
        labs = f.make_clientlabs(seed)
        before = _count(M.ClientLab)
        instance, is_new = M.ClientLab.query_or_create(name="Acme")
        assert is_new is False
        assert instance.id == labs["acme"].id
        assert _count(M.ClientLab) == before  # nothing created

    def test_creates_when_no_match(self, seed):
        f.make_clientlabs(seed)
        before = _count(M.ClientLab)
        instance, is_new = M.ClientLab.query_or_create(name="Gamma")
        assert is_new is True
        assert instance.name == "Gamma"
        # The new instance is transient — query_or_create does not persist it.
        assert _count(M.ClientLab) == before

    def test_ignores_unmapped_kwargs(self, seed):
        labs = f.make_clientlabs(seed)
        # 'not_a_field' isn't a mapped attribute; it should be dropped, not crash.
        instance, is_new = M.ClientLab.query_or_create(name="Acme", not_a_field="x")
        assert is_new is False
        assert instance.id == labs["acme"].id

    def test_relationship_by_instance_finds_existing(self, seed):
        reagents = f.make_reagents(seed)
        lots = f.make_reagentlots(seed, reagents["omega"])
        instance, is_new = M.ReagentLot.query_or_create(
            reagent=reagents["omega"], lot="LOT1")
        assert is_new is False
        assert instance.id == lots["lot1"].id

    def test_relationship_by_string_creates_new_known_quirk(self, seed):
        # PINNED QUIRK: a relationship passed as a string fails the post-lookup
        # all-fields check (resolved instance != raw string) and creates new.
        reagents = f.make_reagents(seed)
        f.make_reagentlots(seed, reagents["omega"])
        instance, is_new = M.ReagentLot.query_or_create(
            reagent="OmegaKit", lot="LOT1")
        assert is_new is True


# --------------------------------------------------------------------------- #
# Sample-association overrides — bare-instance contract                        #
# --------------------------------------------------------------------------- #
class TestSampleAssociationQueryOrCreate:
    def _submission(self, seed):
        labs = f.make_clientlabs(seed)
        sts = f.make_submissiontypes(seed)
        samples = f.make_samples(seed)
        sub = f.make_submission(seed, labs["acme"], sts["bact"], plate_id="SUB-1")
        return sub, samples

    # -- ClientSubmissionSampleAssociation -- #
    def test_returns_bare_instance_not_tuple(self, seed):
        sub, samples = self._submission(seed)
        f.link_sample_to_submission(seed, sub, samples["s1"], rank=1)
        result = M.ClientSubmissionSampleAssociation.query_or_create(
            clientsubmission=sub, sample=samples["s1"])
        assert not isinstance(result, tuple)
        assert isinstance(result, M.ClientSubmissionSampleAssociation)

    def test_finds_existing_link(self, seed):
        sub, samples = self._submission(seed)
        link = f.link_sample_to_submission(seed, sub, samples["s1"], rank=1)
        before = _count(M.ClientSubmissionSampleAssociation)
        got = M.ClientSubmissionSampleAssociation.query_or_create(
            clientsubmission=sub, sample=samples["s1"])
        assert got is link                       # identity map returns the same row
        assert _count(M.ClientSubmissionSampleAssociation) == before

    def test_creates_new_link(self, seed):
        sub, samples = self._submission(seed)
        link = f.link_sample_to_submission(seed, sub, samples["s1"], rank=1)
        made = M.ClientSubmissionSampleAssociation.query_or_create(
            clientsubmission=sub, sample=samples["s2"])  # s2 not yet linked
        assert made is not link
        assert made.sample is samples["s2"]

    def test_parent_and_sample_string_coercion(self, seed):
        sub, samples = self._submission(seed)
        link = f.link_sample_to_submission(seed, sub, samples["s1"], rank=1)
        # parent by rsl_plate_number string, sample by sample_id string
        got = M.ClientSubmissionSampleAssociation.query_or_create(
            clientsubmission="SUB-1", sample="S-001")
        assert got is link

    def test_missing_sample_raises(self, seed):
        sub, _ = self._submission(seed)
        with pytest.raises(ValueError):
            M.ClientSubmissionSampleAssociation.query_or_create(
                clientsubmission=sub, sample=None)

    def test_missing_parent_raises(self, seed):
        _, samples = self._submission(seed)
        with pytest.raises(ValueError):
            M.ClientSubmissionSampleAssociation.query_or_create(
                clientsubmission=None, sample=samples["s1"])

    # -- RunSampleAssociation -- #
    def test_run_association_finds_existing(self, seed):
        sub, samples = self._submission(seed)
        run = f.make_run(seed, sub, plate="RSL-1")
        rlink = f.link_sample_to_run(seed, run, samples["s1"], rank=1)
        got = M.RunSampleAssociation.query_or_create(run=run, sample=samples["s1"])
        assert got is rlink

    def test_run_association_string_coercion(self, seed):
        sub, samples = self._submission(seed)
        run = f.make_run(seed, sub, plate="RSL-1")
        rlink = f.link_sample_to_run(seed, run, samples["s1"], rank=1)
        got = M.RunSampleAssociation.query_or_create(run="RSL-1", sample="S-001")
        assert got is rlink

    def test_run_association_creates_new(self, seed):
        sub, samples = self._submission(seed)
        run = f.make_run(seed, sub, plate="RSL-1")
        rlink = f.link_sample_to_run(seed, run, samples["s1"], rank=1)
        made = M.RunSampleAssociation.query_or_create(run=run, sample=samples["s2"])
        assert made is not rlink
        assert made.sample is samples["s2"]