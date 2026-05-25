# Validators Review: Streamlining & Interoperability with `backend.db.models`
### Branch: `landowark-patch-1`

---

## Overview

The validator layer is architecturally well-conceived. `PydBaseClass` provides automatic `sql_instance` binding, `prevalidate` strips leading underscores from keys to reconcile Pydantic and SQLAlchemy naming, and `to_sql()` / `to_pydantic()` give a clean round-trip. The main drag on the codebase comes from **three recurring patterns** that could each be centralised, and a handful of structural issues that create inconsistencies between the layers.

---

## 1. The `{value, missing}` wrapper dict is an ad-hoc type — replace with a proper Pydantic type

**Where it appears:** `PydClientSubmission` and `PydRun` — almost every field.

```python
# PydClientSubmission
submitted_date: dict | None = Field(default=dict(value=date.today(), missing=True))
cost_centre:    dict | None = Field(default=dict(value=None, missing=True))
contact:        dict | None = Field(default=dict(value=None, missing=True))
rsl_plate_number: dict | None = Field(default=dict(value=None, missing=True))   # PydRun
```

Each of these is a two-key dict `{value: ..., missing: bool}` carrying both the field value and a flag indicating whether it was populated from the source file or is a generated default. Pydantic models exist to replace untyped dicts with structured types — leaving these as raw `dict` means:

- Every consumer must know the internal structure (`value['value']`, `value['missing']`), creating invisible coupling.
- Validation is duplicated: `rescue_submitted_date`, `enforce_submitted_date`, `enforce_value`, `str_to_dict`, `enforce_submitter_plate_id` all exist solely to normalise strings/dates/scalars into this wrapper.
- `filter_field()` in `PydBaseClass` exists to unwrap it — a symptom that the type is leaking out of its container.
- `normalize_dict_field()` is re-implemented separately inside both `PydProcedure.to_sql()` and `PydClientSubmission.to_sql()`.

**Recommendation:** Replace the `{value, missing}` pattern with a typed generic:

```python
from pydantic import BaseModel
from typing import Generic, TypeVar

T = TypeVar("T")

class SourcedField(BaseModel, Generic[T]):
    """
    Wraps a field value with a flag indicating whether it was parsed
    from the source document or generated as a fallback default.
    """
    value: T | None = None
    missing: bool = True

    @classmethod
    def from_raw(cls, raw) -> "SourcedField[T]":
        """Coerce a raw scalar, string, or existing dict into a SourcedField."""
        if isinstance(raw, dict) and "value" in raw:
            return cls(**raw)
        if raw is None:
            return cls(value=None, missing=True)
        return cls(value=raw, missing=False)
```

Then on `PydClientSubmission`:
```python
submitted_date:    SourcedField[datetime] = Field(default_factory=lambda: SourcedField(value=datetime.now(), missing=True))
cost_centre:       SourcedField[str]      = Field(default_factory=lambda: SourcedField(value=None, missing=True))
rsl_plate_number:  SourcedField[str]      = Field(default_factory=lambda: SourcedField(value=None, missing=True))
```

`filter_field()` becomes `field.value`; the twelve ad-hoc `enforce_*/rescue_*` validators collapse into `SourcedField.from_raw()` called from a single `model_validator`; and `normalize_dict_field()` in `to_sql()` disappears entirely since `self.submitted_date.value` already gives the unwrapped value.

---

## 2. `to_sql()` relationship assignment is duplicated across all 20+ concrete classes

**Where it appears:** Every `to_sql()` override in `abstract.py` and `concrete.py`.

The pattern is:
```python
def to_sql(self, update: bool = True):
    from backend.db.models import SomeModel
    self.sql_instance: SomeModel = super().to_sql(update)
    if not update:
        return self.sql_instance, None
    self.sql_instance.relationship_a = self.relationship_a
    self.sql_instance.relationship_b = self.relationship_b
    return self.sql_instance, None
```

Each subclass repeats the guard, the import, and the assignment. The only variation between classes is *which* relationships are assigned. `PydBaseClass.to_sql()` already handles `ColumnProperty` fields — the only reason subclasses need to override is to assign relationship fields, which the base class currently skips with `case _: pass`.

**Recommendation:** Declare which relationships each Pydantic class "owns" as a class variable, and let the base `to_sql()` handle the loop:

```python
# In PydBaseClass
_relationship_fields: ClassVar[List[str]] = []

def to_sql(self, update: bool = True) -> models.BaseClass:
    ...
    # existing ColumnProperty loop
    if update:
        for field in self._relationship_fields:
            value = getattr(self, field, None)
            if value is not None:
                try:
                    setattr(self.sql_instance, field, value)
                except Exception as e:
                    logger.error(f"Could not set relationship {field} on {self.sql_instance}: {e}")
    return self.sql_instance
```

Then each subclass reduces to:
```python
class PydReagent(PydAbstract):
    _relationship_fields = ["reagentrole", "reagentlot"]
    # no to_sql override needed

class PydEquipmentRole(PydAbstract):
    _relationship_fields = ["equipment", "proceduretype"]
    # no to_sql override needed
```

Classes with genuinely bespoke logic (`PydProcedure`, `PydClientSubmission`, `PydRun`) still override `to_sql()` — but the boilerplate guard and simple relationship assignments are gone.

The `return (self.sql_instance, None)` tuple is also worth addressing: the second element is `None` in every single implementation. It appears to be a vestige of an older design. The callers that destructure `result, _ = some_pyd.to_sql()` add noise. Either define the return type as `BaseClass` and update callers, or document what the second element is for, since it currently carries no information.

---

## 3. `prevalidate` silently drops keys that don't match SQLAlchemy fields

**File:** `pydant/__init__.py`, lines 107–127.

```python
@model_validator(mode="before")
@classmethod
def prevalidate(cls, data):
    sql_fields = [k for k, v in cls._sql_class.__dict__.items() if isinstance(v, InstrumentedAttribute)]
    output = {}
    for key, value in items:
        new_key = key.replace("_", "")
        if new_key in sql_fields:
            output[new_key] = value
        else:
            output[key] = value   # ← key kept as-is if not in sql_fields
    return output
```

The intent is to strip leading underscores from keys that correspond to SQLAlchemy attributes (e.g. `_reagentrole` → `reagentrole`). But the matching is done against `cls._sql_class.__dict__`, which only includes attributes defined directly on that class — not inherited ones. `BaseClass` attributes like `_misc_info` will never appear in `ReagentRole.__dict__`, so `_misc_info` will never be normalised regardless of what arrives.

More critically, the `new_key = key.replace("_", "")` call removes **all** underscores, not just a leading one. A key like `submitted_date` becomes `submitteddate`, which doesn't match any field. This means data coming from the DB via `details_dict` (which preserves `submitted_date` with its underscore) may silently fail to populate the Pydantic field if the model uses `submitted_date` as the field name.

**Recommendation:**

```python
@model_validator(mode="before")
@classmethod
def prevalidate(cls, data: dict) -> dict:
    """Strip leading underscores from keys that correspond to SQLAlchemy attributes."""
    if not isinstance(data, dict):
        return data
    # Use sql_inspect to include inherited attributes
    try:
        from sqlalchemy import inspect as sql_inspect
        mapper = sql_inspect(cls._sql_class)
        sql_field_names = {attr.key for attr in mapper.column_attrs} | \
                          {rel.key for rel in mapper.relationships}
    except Exception:
        sql_field_names = set()
    output = {}
    for key, value in data.items():
        stripped = key.lstrip("_")   # strip leading underscores only
        if stripped in sql_field_names and key != stripped:
            output[stripped] = value
        else:
            output[key] = value
    return output
```

---

## 4. `generate_blank_sql_instance` creates a DB-bound object eagerly on every instantiation

**File:** `pydant/__init__.py`, lines 87–92.

```python
@field_validator("sql_instance", mode="before")
@classmethod
def generate_blank_sql_instance(cls, value):
    if value is None:
        value = cls._sql_class()    # ← constructs a SQLAlchemy object and adds it to the session
    return value
```

Every time a Pydantic model is instantiated without a `sql_instance`, this calls `cls._sql_class()` — which calls `BaseClass.__init__()`, which is registered with SQLAlchemy's unit of work. Depending on the session's `autoflush` setting, this may try to INSERT a blank row. It also means that constructing e.g. `PydSample(sample_id="TEST")` for validation purposes (in a test, a parser, or a form) causes a side effect in the database session.

Evidence of the problem: `PydBaseClass.to_sql()` contains `assert self.sql_instance is not None` — if this was truly guaranteed by the validator, the assertion would be redundant.

**Recommendation:** Defer the SQL instance creation to `to_sql()` and leave `sql_instance` as `None` unless explicitly provided:

```python
sql_instance: BaseClass | None = Field(default=None, repr=False, exclude=True)

@field_validator("sql_instance", mode="before")
@classmethod
def validate_sql_instance(cls, value):
    # Accept an existing instance; do not create one speculatively.
    if value is not None and not isinstance(value, BaseClass):
        logger.warning(f"sql_instance for {cls.__name__} is not a BaseClass; ignoring.")
        return None
    return value

def to_sql(self, update: bool = True) -> models.BaseClass:
    if self.sql_instance is None:
        # Resolve via query_or_create so we reuse existing DB rows
        instance, _ = self._sql_class.query_or_create(**self._sql_lookup_kwargs())
        self.sql_instance = instance
    ...
```

Where `_sql_lookup_kwargs()` returns the minimal fields needed to identify the object (typically just `name` or `lot`), which subclasses can override. This also removes the need for `update=False` as a "don't persist" flag, since construction is now decoupled from persistence.

---

## 5. `PydProcessVersion.parse_date_verified` validator is missing its decorator

**File:** `concrete.py`, lines 383–396.

```python
field_validator("date_verified", mode="before")    # ← missing the @ symbol
@classmethod
def parse_date_verified(cls, value):
    ...
```

The `@` is absent, so `field_validator(...)` is evaluated as a standalone expression and immediately discarded. `parse_date_verified` is never registered as a validator. `date_verified` will therefore never be coerced from `str` or `date` — any non-`datetime` value will cause a `ValidationError` when Pydantic tries to set the field, since the type annotation is `datetime`.

**Fix:**
```python
@field_validator("date_verified", mode="before")
@classmethod
def parse_date_verified(cls, value):
    ...
```

---

## 6. `validate_optional_strings` is re-declared on two unrelated classes

**Files:** `abstract.py` `PydReagent` (lines 30–35), `concrete.py` `PydEquipment` (lines 311–316).

```python
# PydReagent
@field_validator("manufacturer", "ref")
@classmethod
def validate_optional_strings(cls, value):
    if value is None:
        return "NA"
    return value

# PydEquipment — identical body, identical name
@field_validator("manufacturer", "ref", mode="before")
@classmethod
def validate_optional_strings(cls, value):
    if value is None:
        return "NA"
    return value
```

Also: `active_bool` (`PydReagentLot` line 99), `int_to_bool` (`PydProcessVersion` line ~460, `PydTipsLot` line 1460), `parse_expiry` (`PydReagentLot` line 104, `PydTipsLot` line 1441) — all near-identical bodies across unrelated classes.

**Recommendation:** Define a small set of reusable validator functions and attach them explicitly:

```python
# In pydant/__init__.py or a validators/shared.py

def coerce_none_to_na(value: str | None) -> str:
    return "NA" if value is None else value

def coerce_int_to_bool(value) -> bool:
    return bool(value) if isinstance(value, int) else value

def parse_optional_datetime(value) -> datetime | None:
    if not value:
        return None
    match value:
        case str():
            try: return parse(value)
            except ParserError: return None
        case date():
            return datetime.combine(value, datetime.min.time())
        case datetime():
            return value
        case _:
            return None
```

Then on each class:
```python
class PydReagent(PydAbstract):
    _validate_na = field_validator("manufacturer", "ref")(coerce_none_to_na)

class PydEquipment(PydConcrete):
    _validate_na = field_validator("manufacturer", "ref", mode="before")(coerce_none_to_na)
```

The `parse_expiry` duplicate between `PydReagentLot` and `PydTipsLot` is almost identical but has a different fallback (`timedelta(days=365)` vs `datetime.max.time()`). These should either be unified with a parameter, or clearly documented as intentionally different.

---

## 7. `ClientSubmissionNamer` resolves `submissiontype` inconsistently in its `__init__`

**File:** `validators/__init__.py`, lines 38–46.

```python
def __init__(self, filepath, submissiontype=None, data=None, **kwargs):
    super().__init__(filepath=filepath)
    if not submissiontype:                          # branch A
        self.submissiontype = self.retrieve_submissiontype()
    if isinstance(submissiontype, str):             # branch B
        self.submissiontype = SubmissionType.query(name=submissiontype)
```

If `submissiontype` is a `SubmissionType` instance (the third possible input type), neither branch runs, and `self.submissiontype` is never set. A later access raises `AttributeError`. The `elif` that should cover the `SubmissionType` case is missing.

Additionally, branch A and branch B are independent `if` statements, not `if/elif`. If `submissiontype` is a non-empty string, branch A is skipped (correct), but branch B also sets `self.submissiontype` — so the two branches can't interfere here. However, if `submissiontype` evaluates to falsy (empty string, `0`), both branch A runs *and* branch B runs (since an empty string is a `str`), meaning `retrieve_submissiontype()` runs and then is immediately overwritten by `SubmissionType.query(name="")`.

**Fix:**
```python
def __init__(self, filepath, submissiontype=None, data=None, **kwargs):
    super().__init__(filepath=filepath)
    match submissiontype:
        case None | "":
            self.submissiontype = self.retrieve_submissiontype()
        case str():
            self.submissiontype = SubmissionType.query(name=submissiontype)
        case SubmissionType():
            self.submissiontype = submissiontype
        case _:
            logger.warning(f"Unrecognised submissiontype type {type(submissiontype)}, falling back to retrieval.")
            self.submissiontype = self.retrieve_submissiontype()
```

---

## 8. `PydRun.__init__` makes a DB query unconditionally on every instantiation

**File:** `concrete.py`, lines 1371–1380.

```python
def __init__(self, **data):
    super().__init__(**data)
    clientsub = self.sql_instance.clientsubmission    # ← DB access
    try:
        submission_type = clientsub.submissiontype
    except AttributeError:
        submission_type = "Default SubmissionType"
    self.namer = RSLNamer(submission_type=submission_type)
```

`self.sql_instance.clientsubmission` is a SQLAlchemy relationship access that triggers a lazy-load query on every `PydRun()` construction — including in tests, in list comprehensions, and in the parsers. If the session is closed or the relationship is not loaded, this raises `DetachedInstanceError`.

`self.namer` is only used in `export_filename`, not in validation. Creating it eagerly in `__init__` couples the Pydantic model's construction to DB state.

**Recommendation:** Make `namer` a cached property so the DB access only happens when `export_filename` is actually called:

```python
@cached_property
def namer(self) -> RSLNamer:
    try:
        submission_type = self.sql_instance.clientsubmission.submissiontype
    except AttributeError:
        submission_type = "Default SubmissionType"
    return RSLNamer(submission_type=submission_type)
```

Remove the `__init__` override entirely — `PydBaseClass.__init__` (via Pydantic) is sufficient.

---

## 9. `subclasses` classproperty only traverses two levels deep

**File:** `pydant/__init__.py`, lines 558–568.

```python
@classproperty
def subclasses(cls) -> Generator[PydBaseClass, None, None]:
    for class_ in PydBaseClass.__subclasses__():        # level 1: PydAbstract, PydConcrete
        for subclass in class_.__subclasses__():        # level 2: PydReagent, PydRun, etc.
            yield subclass
```

This works today because the hierarchy is exactly two levels deep (`PydBaseClass → PydAbstract/PydConcrete → concrete models`). If a third level is ever added (e.g. `PydRun → PydSpecialRun`), `PydSpecialRun` will be silently omitted from `subclasses`, breaking `get_association_class()` and `get_managables()` without any error.

**Recommendation:** Use a recursive generator that walks the full tree:

```python
@classproperty
def subclasses(cls) -> Generator[type[PydBaseClass], None, None]:
    def _walk(klass):
        for sub in klass.__subclasses__():
            yield sub
            yield from _walk(sub)
    yield from _walk(PydBaseClass)
```

---

## Summary

| # | Issue | Severity | Files |
|---|-------|----------|-------|
| 1 | `{value, missing}` raw dicts as ad-hoc type — replace with `SourcedField[T]` | High | `concrete.py` |
| 2 | `to_sql()` relationship assignment duplicated 20+ times — use `_relationship_fields` | Medium-High | `abstract.py`, `concrete.py` |
| 3 | `prevalidate` uses `.replace("_", "")` (removes all underscores) and misses inherited attributes | Medium | `pydant/__init__.py` |
| 4 | `generate_blank_sql_instance` eagerly creates DB-bound objects — decouple construction from persistence | Medium | `pydant/__init__.py` |
| 5 | `PydProcessVersion.parse_date_verified` missing `@` — validator never runs | High (silent) | `concrete.py` |
| 6 | `validate_optional_strings`, `int_to_bool`, `parse_expiry` duplicated across classes | Low-Medium | `abstract.py`, `concrete.py` |
| 7 | `ClientSubmissionNamer.__init__` drops `SubmissionType` instances; `if`/`if` instead of `if`/`elif` | Medium | `validators/__init__.py` |
| 8 | `PydRun.__init__` makes unconditional DB query — move to `cached_property` | Medium | `concrete.py` |
| 9 | `subclasses` only traverses two levels — breaks if hierarchy deepens | Low | `pydant/__init__.py` |