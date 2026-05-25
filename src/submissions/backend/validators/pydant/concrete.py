
from __future__ import annotations
from functools import cached_property
from pprint import pformat
import csv, logging, re, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Generator, List, Tuple, TYPE_CHECKING
from pydantic import AfterValidator, ConfigDict, Field, field_validator, computed_field, model_validator
from PyQt6.QtWidgets import QWidget
from dateutil.parser import parse, ParserError
from backend.validators import RSLNamer
from backend.validators.shared import coerce_none_to_na, coerce_int_to_bool
from backend.validators.pydant import PydConcrete, SourcedField, _coerce_datetime_field, _coerce_int_field, _coerce_str_field, RelationshipField
from backend.validators.pydant.abstract import PydEquipmentRole, PydProcedureType, PydReagent, PydResultsType, PydReagentRole
from tools import Alert, Report, check_not_nan, find_first_matching_dict, row_keys, sort_dict_by_list, timezone
if TYPE_CHECKING:
    from backend.db.models.submissions import Run

logger = logging.getLogger(f"submissions.{__name__}")

def ensure_list(v: Any) -> List:
    if isinstance(v, (Generator, filter, map)):
        return list(v)
    return v


class PydResults(PydConcrete, arbitrary_types_allowed=True):

    result: dict = Field(default={}, repr=False)
    resultstype: Annotated[str | PydResultsType, RelationshipField(uselist=False)] = Field(default="NA")
    image: None | bytes = Field(default=None, repr=False)
    procedure: Annotated[str | PydProcedure | None, RelationshipField(uselist=False)] = Field(default=None)
    sample: Annotated[str | PydSample | None, RelationshipField(uselist=False)] = Field(default=None)
    date_analyzed: datetime | None = Field(default=None, repr=False, validate_default=True)
    is_sample: bool = Field(default=False, repr=False)

    @field_validator("date_analyzed", mode="before")
    @classmethod
    def parse_analyzed(cls, value):
        match value:
            case str():
                try:
                    value = parse(value)
                except ParserError:
                    value = None
            case datetime():
                pass
            case date():
                 value = datetime.combine(value, datetime.min.time())
            case _:
                value = None
        return value
    
    @computed_field
    @property
    def name(self) -> str:
        if isinstance(self.procedure, PydProcedure):
            assoc = self.procedure.name
        else:
            assoc = self.procedure
        if isinstance(self.resultstype, PydResultsType):
            resultstype = self.resultstype.name
        else:
            resultstype = self.resultstype
        return f"{assoc}-{resultstype}"

    @property
    def improved_dict(self) -> dict:
        output = super().improved_dict
        output['result'] = self.result
        if self.sample:
            output['sample_id'] = self.sample.name if isinstance(self.sample, PydSample) else self.sample
        return output

    def to_sql(self):
        from backend.db.models import Results
        sql, _ = Results.query_or_create(resultstype=self.resultstype, result=self.result)
        try:
            check = sql.image
        except FileNotFoundError:
            check = False
        if not check:
            sql.image = self.image
        if not sql.date_analyzed:
            sql.date_analyzed = self.date_analyzed
        sql.procedure = self.procedure
        sql.sampleprocedureassociation = self.sample
        return sql, None


class PydReagentLot(PydConcrete):

    lot: str = Field(default="NA", description="Lot number of this reagent.")
    reagent: Annotated[str | PydReagent | None, RelationshipField(uselist=False)] = Field(default=None, description="Type of reagent this lot is.")
    reagentrole: str | None = Field(default=None, repr=False)
    expiry: datetime = Field(default = None, description="Expiry date of this reagent lot.", validate_default=True)
    missing: bool = Field(default=True, repr=False)
    active: bool = Field(default=True, description="Is this lot currently in use?", repr=False)

    @field_validator("active", mode="before")
    @classmethod
    def active_bool(cls, value):
        return bool(value)

    # TODO: Move to shared along with PydTipsLot
    @field_validator("expiry", mode="before")
    @classmethod
    def parse_expiry(cls, value):
        if not value:
            value = date.today() + timedelta(days=365)
        match value:
            case str():
                try:
                    value = parse(value)
                except ParserError:
                    value = None
            case date() | datetime():
                value = datetime.combine(value, datetime.max.time())
            case _:
                raise ValueError(f"Could not parse expiry date: {value}")
        return value

    @computed_field
    @property
    def name(self) -> str:
        match self.reagent:
            case PydReagent():
                reagent = self.reagent.name
            case _:
                reagent = self.reagent
        try:
            return f"{reagent} - {self.lot}"
        except AttributeError:
            return f"{reagent} - Unknown Lot"

    @property
    def improved_dict(self) -> dict:
        output = super().improved_dict
        output['name'] = self.name
        return output

    # def to_sql(self, update: bool = True):
    #     from backend.db.models import ReagentLot
    #     self.sql_instance: ReagentLot = super().to_sql(update)
    #     if not update:
    #         return self.sql_instance, None
    #     self.sql_instance.reagent = self.reagent
    #     return self.sql_instance, None


class PydDiscount(PydConcrete):

    description: str = Field(default="NA", description="Brief description of this discount.")
    proceduretype: Annotated[str | None, RelationshipField(uselist=False)] = Field(default="NA", description="ProcedureType this discount applies to.", repr=False)
    clientlab: Annotated[str | None, RelationshipField(uselist=False)] = Field(default="NA", description="ClientLab this discount applies to.", repr=False)
    amount: float = Field(default=0.0, description="Amount (dollars) of discount to apply.")

    # def to_sql(self, update: bool = True):
    #     from backend.db.models import Discount
    #     self.sql_instance: Discount = super().to_sql(update)
    #     if not update:
    #         return self.sql_instance, None
    #     self.sql_instance.proceduretype = self.proceduretype
    #     self.sql_instance.clientlab = self.clientlab
    #     return self.sql_instance, None


class PydSample(PydConcrete):

    sample_id: str
    rank: int | List[int] | None = Field(default=0, validate_default=True)
    enabled: bool = Field(default=True, repr=False)
    row: int = Field(default=0)
    column: int = Field(default=0)
    results: List[PydResults] | PydResults = Field(default_factory=list, repr=False)
    is_control: int = Field(default=0)

    @field_validator('is_control', mode='before')
    @classmethod
    def enforce_value_range(cls, value):
        if value is None:
            value = 0
        if value >= 1:
            value = 1
        elif value <= -1:
            value = -1
        else:
            value = 0
        return value

    @field_validator("sample_id", mode="before")
    @classmethod
    def int_to_str(cls, value):
        return str(value)

    @field_validator("sample_id")
    @classmethod
    def strip_sub_id(cls, value):
        match value:
            case dict():
                value['value'] = value['value'].strip().upper()
            case str():
                value = value.strip().upper()
            case _:
                pass
        return value

    @field_validator("row", mode="before")
    @classmethod
    def row_str_to_int(cls, value):
        if value in [None, ""]:
            value = 0
        if isinstance(value, str):
            try:
                value = row_keys[value]
            except KeyError:
                try:
                    value = int(value)
                except ValueError:
                    value = 0
        return value

    @field_validator("column", mode="before")
    @classmethod
    def column_str_to_int(cls, value):
        if value in [None, ""]:
            value = 0
        if isinstance(value, str):
            try:
                value = int(value)
            except ValueError:
                value = 0
        return value

    @computed_field
    @property
    def name(self) -> str:
        return self.sample_id
    
    @property
    def improved_dict(self) -> dict:
        output = super().improved_dict
        output['name'] = self.name
        return output

    def to_sql(self, update: bool=True):
        # Ensure we return a SQL Sample instance that has a valid sample_id
        # When update=False callers expect a resolved SQL instance but we
        # shouldn't blindly return a blank sql_instance (which has no
        # sample_id set). Try to resolve an existing Sample by sample_id
        # first. If none exists, populate the sql_instance.sample_id so
        # that downstream association objects don't try to insert NULL.
        self.sql_instance = super().to_sql(update=update)
        try:
            # Only set the SQL sample_id when the pydantic sample_id is valid.
            # Blank/NA/placeholder IDs (e.g. "", "NA", "None") are not valid
            # and would violate the UNIQUE constraint if multiple blank sample
            # rows are created. Use the helper validator to decide.
            if not self.is_sample_id_valid(self.sample_id):
                return None, None
        except Exception:
            # Fallback: nothing we can do, return sql as-is
            pass
        if not update:
            # Try to use an existing SQL Sample if present in DB
            try:
                from backend.db.models import Sample
                existing = Sample.query(sample_id=self.sample_id, limit=1) if self.sample_id else None
            except Exception:
                existing = None
            if existing:
                return existing, None
            # If no existing object, ensure the blank sql_instance has sample_id set
            return self.sql_instance, None
        self.sql_instance.clientsubmission = getattr(self, "clientsubmission", [])
        self.sql_instance.run = getattr(self, "run", [])
        self.sql_instance.procedure = getattr(self, "procedure", [])
        self.sql_instance.rank = self.rank
        return self.sql_instance, None

    @classmethod
    def is_sample_id_valid(cls, sample: str | PydSample | dict) -> bool:
        match sample:
            case PydSample():
                sample_id = sample.sample_id
            case dict():
                sample_id = sample.get('sample_id', '')
            case str():
                sample_id = sample
            case _:
                logger.warning(f"{sample} is not a valid type")
                return False
        if sample_id.strip().lower().startswith("blank"):
            return False
        if sample_id.strip().lower() in ["", "na", "none"]:
            return False
        return True


class PydEquipment(PydConcrete):

    asset_number: str = Field(default="NA", description="Asset number of this equipment.")
    name: str = Field(default="NA", description="Name of this equipment.")
    nickname: str = Field(default="NA", description="Nickname of this equipment.", validate_default=True)
    manufacturer: str | None = Field(default="NA", description="Company that makes this equipment")
    ref: str = Field(default="NA", description="Manufacturer's reference number")
    serial_number: str = Field(default="NA", description="Manufacturer's serial number")
    procedure: Annotated[List[str], RelationshipField(uselist=True)] = Field(default_factory=list, repr=False)
    equipmentrole: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, description="Roles this equipment can fill.", repr=False)
    calibration_date: datetime = Field(default = datetime.combine(date=datetime(year=2000, month=1, day=1), time=datetime.min.time()), 
                                       description="Date of last calibration.", validate_default=True, repr=False)
    
    # @field_validator("manufacturer", "ref", mode="before")
    # @classmethod
    # def validate_optional_strings(cls, value):
    #     if value is None:
    #         return "NA"
    #     return value

    _validate_na = field_validator("manufacturer", "ref")(coerce_none_to_na)

    @field_validator('nickname')
    @classmethod
    def set_nickname_to_name(cls, value, values):
        if not value or value == "NA":
            value = values.data['name']
        return value

    # def to_sql(self, update: bool = True):
    #     from backend.db.models import Equipment
    #     self.sql_instance: Equipment = super().to_sql(update)
    #     if not update:
    #         return self.sql_instance, None
    #     self.sql_instance.procedure = self.procedure
    #     self.sql_instance.equipmentrole = self.equipmentrole
    #     return self.sql_instance, None


class PydContact(PydConcrete):

    name: str = Field(default="NA", description="Name of this contact.")
    tel: str = Field(default="000-000-0000", description="Phone number of this contact.")
    email: str = Field(default="NA", description="Email address of this contact.")
    clientlab: Annotated[List[str], RelationshipField(uselist=True)] = Field(default_factory=list)

    @field_validator("tel")
    @classmethod
    def enforce_phone_number(cls, value):
        area_regex = re.compile(r"^\(?(\d{3})\)?(-| )?")
        if len(value) > 8:
            match = area_regex.match(value)
            value = area_regex.sub(f"({match.group(1).strip()}) ", value)
        return value

    # def to_sql(self, update: bool = True):
    #     from backend.db.models import Contact
    #     self.sql_instance: Contact = super().to_sql(update=update)
    #     if not update:
    #         return self.sql_instance, None
    #     self.sql_instance.clientlab = self.clientlab
    #     return self.sql_instance, None


class PydClientLab(PydConcrete):

    name: str = Field(default="NA", description="Name of this Client Lab.")
    cost_centre: str = Field(default="NA", description="Default cost centre for this Client Lab.", repr=False)
    contact: Annotated[List[str], RelationshipField(uselist=True)] = Field(default_factory=list, description="Contacts for this Client Lab.", repr=False)

    # def to_sql(self, update: bool = True):
    #     from backend.db.models import ClientLab
    #     self.sql_instance: ClientLab = super().to_sql(update=update)
    #     if not update:
    #         return self.sql_instance, None
    #     self.sql_instance.contact = self.contact
    #     return self.sql_instance, None


class PydProcessVersion(PydConcrete, extra="allow", arbitrary_types_allowed=True):
    
    version: float = Field(default=1.0, description="Version number of this process.")
    date_verified: datetime = Field(default_factory=datetime.now, description="Date this version was verified.", validate_default=True)
    project: str = Field(default="NA", description="Project this process version is for.")
    active: bool = Field(default=True, description="Is this the active version?")
    process: Annotated[str, RelationshipField(uselist=False)] = Field(default="NA", description="Process this is a version of.")

    @field_validator("date_verified", mode="before")
    @classmethod
    def parse_date_verified(cls, value):
        if not value:
            value = date.today()
        match value:
            case str():
                try:
                    value = parse(value)
                except ParserError:
                    value = None
            case date() | datetime():
                value = datetime.combine(value, datetime.min.time())    
            case _:
                value = None
        return value
    
    _validate_na = field_validator("active", mode="before")(coerce_int_to_bool)

    # @field_validator("active", mode="before")
    # @classmethod
    # def int_to_bool(cls, value):
    #     if value is None:
    #         value = True
    #     if isinstance(value, str):
    #         if value.lower() in ["false", "0", "no", "off"]:
    #             value = False
    #         else:
    #             value = True
    #     if isinstance(value, int):
    #         value = bool(value)
    #     return value
    
    @property
    def name(self) -> str:
        process = self.process or "Unassigned"
        return f"{process} - v{str(self.version)}"

    # def to_sql(self, update: bool = True):
    #     from backend.db.models import ProcessVersion
    #     self.sql_instance: ProcessVersion = super().to_sql(update)
    #     if not update:
    #         return self.sql_instance, None
    #     self.sql_instance.process = self.process
    #     return self.sql_instance, None

    
class PydProcedure(PydConcrete, arbitrary_types_allowed=True):
    
    proceduretype: Annotated[str | PydProcedureType | None, RelationshipField(uselist=False)] = Field(default=None)
    run: Annotated[str | PydRun | None, RelationshipField(uselist=False)] = Field(default=None)
    technician: SourcedField[str] = Field(default_factory=lambda: SourcedField(value=None, missing=True), repr=False)
    repeat: bool = Field(default=False, repr=False)
    repeat_of: Annotated[str | PydProcedure | None, RelationshipField(uselist=False)] = Field(default=None, repr=False)
    platemap: str | None = Field(default=None, repr=False)
    reagentlot: Annotated[List[str | PydProcedureReagentLotAssociation], RelationshipField(uselist=True)] = Field(default_factory=list, repr=False)
    sample: Annotated[List[str | PydSample | PydProcedureSampleAssociation], RelationshipField(uselist=True)] = Field(default_factory=list, repr=False)
    equipment: Annotated[List[str | PydProcedureEquipmentAssociation], RelationshipField(uselist=True)] = Field(default_factory=list, repr=False)
    results: Annotated[List[dict | PydResults], RelationshipField(uselist=True)] = Field(default_factory=list, repr=False)
    started_date: datetime = Field(default_factory=datetime.now, repr=False)
    completed_date: datetime | None = Field(default_factory=datetime.now, repr=False)
    comment: list | None = Field(default_factory=list, repr=False, validate_default=True)

    model_config = ConfigDict(
        json_schema_extra = {"excluded": ['control', 'equipment', 'excluded', 'id', 'misc_info', 'plate_map', 'possible_kits', 'comment',
               'procedureequipmentassociation', 'procedurereagentassociation', 'proceduresampleassociation', 'proceduretipsassociation', 'reagent',
               'reagentrole', 'results', 'sample', 'tips', 'reagentlot', 'platemap', "procedurereagentlotassociation", "result", "sample_results"]}
    )

    @field_validator("technician", mode="before")
    @classmethod
    def convert_to_dict(cls, value):
        if not value:
            value = dict(value="NA", missing=True)
        if isinstance(value, str):
            value = dict(value=value, missing=False)
        return value

    @field_validator("proceduretype", mode="before")
    @classmethod
    def lookup_proceduretype(cls, value):
        from backend.db.models import ProcedureType
        match value:
            case dict():
                q = value.get("name", None) or value.get("value", None)
                value = ProcedureType.query(name=q).to_pydantic()
            case str():
                value = ProcedureType.query(name=value).to_pydantic()
            case ProcedureType():
                value = value.to_pydantic()
            case PydProcedureType():
                value = value
            case _:
                pass
        return value

    @field_validator("run", mode="before")
    @classmethod
    def lookup_run(cls, value):
        if isinstance(value, dict):
            value = value.get("value", None) or value.get("name", None)
        # When converting a Run -> PydRun the procedure dicts include the run
        # as a simple name string. Converting that string back into a full
        # PydRun here would cause a recursive conversion: Run.to_pydantic ->
        # PydProcedure -> lookup_run -> Run.to_pydantic -> ... leading to
        # infinite recursion. Instead, keep the run as the simple string name
        # (or the found SQL Run) and let higher-level code handle converting
        # to a PydRun only when it's safe to do so.
        # If a Run SQL instance was supplied directly, leave it as-is (don't
        # convert to pydantic here).
        return value

    _validate_na = field_validator("repeat", mode="before")(coerce_int_to_bool)

    # @field_validator("repeat", mode="before")
    # @classmethod
    # def enforce_bool(cls, value):
    #     if isinstance(value, dict):
    #         value = value.get("value", False)
    #     if isinstance(value, str):
    #         value = value.lower()
    #     if value in [True, "true", "yes", "on", 1, "1"]:
    #         return True
    #     else:
    #         return False
    
    @field_validator("repeat_of")
    @classmethod
    def drop_empty_string(cls, value):
        if value == "":
            value = None
        return value
    
    @field_validator("equipment", mode="before")
    @classmethod
    def validate_equipment(cls, value):
        output = []
        for item in value:
            match item:
                case dict():
                    output.append(item['name'])
                case str() | PydProcedureEquipmentAssociation():
                    output.append(item)
                case _:
                    continue
        return output

    @property
    def name(self) -> SourcedField:
        pt_name = getattr(self.proceduretype, "name", str(self.proceduretype)) if self.proceduretype else "Unassigned ProcedureType"
        if isinstance(pt_name, dict):
            pt_name = pt_name.get("value", "Unassigned ProcedureType")
        elif isinstance(pt_name, SourcedField):
            pt_name = pt_name.get("value", "Unassigned ProcedureType")
        # 2. Resolve Run
        run_id = getattr(self.run, "rsl_plate_number", str(self.run)) if self.run else "Unassigned Run"
        if isinstance(run_id, dict):
            run_id = run_id.get("value", "Unassigned Run")
        elif isinstance(run_id, SourcedField):
            run_id = run_id.get("value", "Unassigned Run")
        # Update the instance directly
        started_date = getattr(self, "started_date", None)
        if started_date is not None:
            suffix = f" - {started_date.strftime("%Y-%m-%d %H:%M:%S")}"
        else:
            suffix = ""
        # return {"value": f"{run_id} - {pt_name}{suffix}", "missing": True}
        name = f'{run_id} - {pt_name}{suffix}'
        return SourcedField(value=name, missing=True)
        
    @field_validator("started_date", mode="before")
    @classmethod
    def create_started_date(cls, value):
        if not value:
            value = datetime.now()
        if isinstance(value, dict):
            value = value.get("value", datetime.now())
        if isinstance(value, str):
            value = parse(value)
        return value
    
    @field_validator("completed_date", mode="before")
    @classmethod
    def create_completed_date(cls, value):
        if isinstance(value, dict):
            value = value.get("value", None)
        if isinstance(value, str):
            if value.lower() == "None":
                return None
            try:
                value = parse(value)
            except ValueError:
                return None
        return value

    @field_validator("sample", mode="before")
    @classmethod
    def convert_association(cls, value):
        output = None
        if isinstance(value, list):
            output = []
            for sample in value:
                match sample:
                    case PydProcedureSampleAssociation() | PydSample() | str():
                        output.append(sample)
                    case dict():
                        output.append(PydSample(**sample))
                    case _:
                        logger.error(f"Unmatched type {type(sample)} for sample")
                        continue
        return output

    @property
    def rows_columns_count(self) -> Tuple[int, int]:
        from backend.db.models import ProcedureType
        try:
            proc: ProcedureType = self.sql_instance.proceduretype
        except AttributeError as e:
            logger.error(f"Can't get rows, columns due to {e}")
            return 0, 0
        return proc.plate_rows, proc.plate_columns

    @property
    def max_sample_rank(self) -> int:
        rows, columns = self.rows_columns_count
        output = rows * columns
        if output > 0:
            return output
        else:
            try:
                return max([item.procedure_rank for item in self.sample])
            except TypeError:
                return len(self.sample)

    def update_samples(self, sample_list: List[dict]):
        from backend.db.models import Sample
        # Coming into this method, samples are dicts and 'is_control' is intact.
        # Build a new ordered list of samples matching the sample_list order.
        ranked_plate = self.proceduretype.make_ranked_plate()
        new_samples: List[PydSample] = []
        for iii, sample_dict in enumerate(sample_list, start=1):
            sample_id = sample_dict.get('sample_id', '')
            # normalize blank markers
            if isinstance(sample_id, str) and sample_id.startswith("blank_"):
                sample_id = ""
            try:
                row, column = ranked_plate.get(sample_dict['index'], (0, 0))
            except KeyError:
                row = 0
                column = 0
            try:
                row = sample_dict.get("row", row)
            except AttributeError:
                row = 0
            try:
                column = sample_dict.get("column", column)
            except AttributeError:
                column = 0    
            try:
                sample = find_first_matching_dict(self.sample, "sample_id", sample_dict['sample_id'])
            except StopIteration:
                sample = PydSample(sample_id=sample_id)
            # Do NOT change the sample_id (we want to preserve the existing sample's identity).
            # Update position/rank/control/classification metadata.
            sample.row = row
            sample.column = column
            sample.rank = int(sample_dict.get('index', iii))
            well_class = next((item for item in sample_dict.get('class', '').replace("well ", "").split(" ") if item in ['negativecontrol', 'positivecontrol']), "")
            match well_class:
                case "negativecontrol":
                    sample.is_control = -1
                case "positivecontrol":
                    sample.is_control = 1
                case _:
                    sample.is_control = sample_dict.get('is_control', 0)
            new_samples.append(sample)
        # Replace the sample list with the reordered list. Preserve any samples not present in
        # sample_list by appending them after the ordered ones (so they are not lost).
        remaining = []#[s for s in self.sample if s not in new_samples]
        self.sample = sorted(new_samples + remaining, key=lambda x: (x.column, x.row))
    
    def get_last_used(self, reagentrole: str):
        from backend.db.models import ProcedureTypeReagentRoleAssociation
        q = ProcedureTypeReagentRoleAssociation.query(proceduretype=self.proceduretype, reagentrole=reagentrole, limit=1)
        return q._last_used

    def update_reagents(self, reagentrole: str, name: str, lot: str, expiry: str | None = None, checked:bool=True):
        from backend.db.models import ReagentLot
        try:
            removable = next((item for item in self.reagentlot if reagentrole == item.reagentrole), None)
        except AttributeError as e:
            logger.error(e)
            removable = None
        if removable:
            idx = self.reagentlot.index(removable)
            self.reagentlot.remove(removable)
        else:
            idx = 0
        reagentlot = ReagentLot.query(reagent=name, lot=lot, limit=1)
        if not reagentlot:
            logger.warning(f"Could not find reagentlot {name} to update. Creating new reagentlot.")
            reagentlot = ReagentLot(reagent=name, lot=lot, active=True)
        reagentlot = reagentlot.to_pydantic()
        insertable = PydProcedureReagentLotAssociation(reagentlot=reagentlot, procedure=self, reagentrole=reagentrole)
        if checked:
            self.reagentlot.insert(idx, insertable)

    def update_equipment(self, equipmentrole: str, equipment: str, processversion: str, tips: str, checked: bool=True):
        from backend.db.models import Equipment, ProcessVersion, TipsLot
        equipment_of_interest: PydProcedureEquipmentAssociation = next((item for item in self.equipment if item.equipmentrole == equipmentrole), None)
        equipment = Equipment.query(name=equipment)
        if equipment_of_interest:
            eoi = self.equipment.pop(self.equipment.index(equipment_of_interest))
            eoi.equipment = equipment.to_pydantic()
        else:
            eoi = PydProcedureEquipmentAssociation(equipment=equipment.to_pydantic(), equipmentrole=equipmentrole, procedure=self)
        processversion = ProcessVersion.query(name=processversion, limit=1)
        # NOTE Retrieves correct instance.
        eoi.processversion = processversion.to_pydantic()
        # NOTE Correct pydprocessverion
        out_tips = []
        for tipslot in tips:
            try:
                tips_manufacturer, tipsref, lot = [item if item != "" else None for item in tipslot.split(" - ")]
                tips = TipsLot.query(manufacturer=tips_manufacturer, ref=tipsref, lot=lot)
                out_tips.append(tips.to_pydantic())
            except ValueError:
                logger.warning(f"No tips info to unpack")
        eoi.tipslot = out_tips
        if checked:
            self.equipment.append(eoi)
        
    @classmethod
    def update_new_reagents(cls, reagent: PydReagent):
        reg = reagent.to_sql()
        reg.save()

    def to_sql(self, update: bool = True):
        from backend.db.models import Procedure
        self.sql_instance: Procedure = super().to_sql(update=update)
        if not update:
            return self.sql_instance, None
        def normalize_dict_field(field_name, value):
            if not isinstance(value, dict):
                return value
            if field_name in ["technician", "started_date", "completed_date"]:
                return value.get("value")
            if field_name in ["proceduretype", "run", "repeat_of"]:
                if set(value.keys()) <= {"value", "missing"}:
                    return value["value"]
                if set(value.keys()) <= {"name", "missing"}:
                    return value["name"]
            return value
        self.sql_instance.technician = normalize_dict_field("technician", self.technician)
        self.sql_instance.started_date = normalize_dict_field("started_date", self.started_date)
        self.sql_instance.completed_date = normalize_dict_field("completed_date", self.completed_date)
        self.sql_instance.proceduretype = normalize_dict_field("proceduretype", self.proceduretype)
        self.sql_instance.run = normalize_dict_field("run", self.run)
        self.sql_instance.repeat_of = normalize_dict_field("repeat_of", self.repeat_of)
        self.sql_instance.reagentlot = self.reagentlot
        # Convert pyd samples to SQL Sample instances before assigning.
        # Use update=True only when the sample_id does not already exist in DB;
        # otherwise use update=False to avoid unnecessary writes.
        samples_sql = []
        from backend.db.models import Sample as SQLSample, ProcedureSampleAssociation
        for sample in self.sample:
            row, column = self.proceduretype.make_ranked_plate()[sample.rank]
            try:
                row = sample.row or row
            except AttributeError:
                row = 0
            try:
                column = sample.column or column
            except AttributeError:
                column = 0
            # Skip invalid/sample placeholders
            if not PydSample.is_sample_id_valid(sample):
                continue
            # If it's already a SQLSample instance, reuse it
            if isinstance(sample, SQLSample):
                samples_sql.append(ProcedureSampleAssociation(sample=sample, procedure=self.sql_instance, rank=sample.rank, row=row, column=column))
                continue
            # If it's a PydSample, decide whether to update or not based on DB
            if isinstance(sample, PydSample):
                try:
                    existing = SQLSample.query(sample_id=sample.sample_id, limit=1) if sample.sample_id else None
                except Exception:
                    existing = None
                try:
                    if existing:
                        result = sample.to_sql(update=False)
                    else:
                        result = sample.to_sql(update=True)
                    if isinstance(result, tuple):
                        sql_sample = result[0]
                    else:
                        sql_sample = result
                    if sql_sample is not None:
                        samples_sql.append(ProcedureSampleAssociation(sample=sql_sample, procedure=self.sql_instance, rank=sample.rank, row=row, column=column))
                except Exception as e:
                    # If conversion fails, skip this sample
                    logger.exception(f"Failed converting PydSample {sample} to SQL Sample due to {e}")
                continue
        self.sql_instance.sample = samples_sql
        self.sql_instance.equipment = self.equipment
        # NOTE: Preserve existing Results when editing to avoid triggering delete-orphan cascade.
        # Only update results if this is a new procedure (no id yet) or if results were explicitly modified.
        if self.sql_instance.id is None:
            # New procedure: assign the results as provided
            self.sql_instance.results = self.results
        # else: Existing procedure - preserve original Results instances to prevent orphan deletion
        return self.sql_instance, None
    
    def check_reagent_expiries(self, exempt: List[str] = []) -> Report:
        """
        Determines which reagents in a run are expired. Should be moved to Procedure.

        Args:
            exempt (List[PydReagent]): List of reagents that won't be checked.

        Returns:
            Report: A Report instance.
        """
        from backend.db.models import ProcedureReagentLotAssociation
        report = Report()
        expired = []
        for procedurereagentlotassociation in self.reagentlot:
            if isinstance(procedurereagentlotassociation, str):
                assoc = ProcedureReagentLotAssociation.query(reagentlot=procedurereagentlotassociation, procedure=self.name['value'], limit=1)
            else:
                assoc = procedurereagentlotassociation.sql_instance
            reagentlot = assoc.reagentlot
            role_eol = reagentlot.reagent.eol_ext
            if datetime.now() > reagentlot.expiry + role_eol:
                expired.append(f"{reagentlot.lot}: {reagentlot.expiry.date()} + {role_eol.days}")
        if expired:
            output = '\n'.join(expired)
            result = Alert(status="Warning",
                            msg=f"The following reagents are expired:\n\n{output}"
                            )
            report.add_result(result)
        return report
    
    @property
    def improved_dict(self) -> dict:
        output = super().improved_dict
        if isinstance(output['proceduretype'], PydProcedureType):
            output['proceduretype'] = output['proceduretype'].name
        if isinstance(output['run'], PydRun):
            output['run'] = output['run'].name
        output['platemap'] = self.make_procedure_platemap()
        # output['name'] = self.name
        return output

    def reorder_proceduretype_by_procedure(self):
        proceduretype_dict = self.proceduretype.improved_dict_expand_fields([
            {
                "reagentrole":[
                        {"reagent":["reagentlot"]}
                        ]
            }, 
            {
                "equipmentrole": [
                        {"equipmentroleequipmentassociation":["equipment", "process"]}
                        ]
            }
            ])
        procedure_dict = self.improved_dict_expand_fields([
                "procedurereagentlotassociation",
                "procedureequipmentassociation"
            ])
        for assoc in procedure_dict["procedurereagentlotassociation"]:
            reagentrole = assoc['reagentrole']
            reagent = assoc['reagent']
            reagentlot = assoc['reagentlot']
            try:
                pt_reagent = next(item['reagent'] for item in proceduretype_dict['reagentrole'] if item['name'] == reagentrole)
            except StopIteration:
                continue
            # Pull any existing reagentlots
            try:
                pt_reagentlots = next(item['reagentlot'] for item in pt_reagent if item['name'] == reagent)
            except StopIteration:
                continue
            rl_index = next((iii for iii, item in enumerate(pt_reagentlots) if item['name'] == reagentlot), 0)
            pt_reagentlots.insert(0, pt_reagentlots.pop(rl_index))
        for assoc in procedure_dict["procedureequipmentassociation"]:
            equipmentrole = assoc['equipmentrole']
            equipment = assoc['equipment']
            try:
                pt_equipment = next(item["equipmentroleequipmentassociation"] for item in proceduretype_dict['equipmentrole'] if item['name'] == equipmentrole)
            except StopIteration:
                continue
            eq_index = next((iii for iii, item in enumerate(pt_equipment) if item['equipment'] == equipment), 0)
            pt_equipment.insert(0, pt_equipment.pop(eq_index))
        for reagentrole in proceduretype_dict.get("reagentrole", []):
            for reagent in reagentrole['reagent']:
                if len(reagent['reagentlot']) < 1:
                    reagent['reagentlot'].append(dict(name="", active=True))
                else:
                    try:
                        reagent['reagentlot'].remove(dict(name="", active=True))
                    except Exception:
                        pass
                try:
                    check = "--New--" in (reagentlot['name'] for reagentlot in reagent['reagentlot'])
                except TypeError:
                    check = True
                if not check:
                    reagent['reagentlot'].append(dict(name="--New--", active=True))
                # Try to move last used to top of the list.
                last_used = self.get_last_used(reagentrole=reagentrole['name'])
                if last_used:
                    last_used = last_used.name
                else:
                    continue
                try:
                    removable = next((item for item in reagent['reagentlot'] if item['name'] == last_used))
                except StopIteration:
                    continue
                idx = reagent['reagentlot'].index(removable)
                reagent['reagentlot'].insert(0, reagent['reagentlot'].pop(idx))
        repeat_regex = re.compile(r".*R\d$")
        proceduretype_dict['previous'] = [""] + [
            item.name for item in self.run.sql_instance.procedure if 
            item.proceduretype.name == self.proceduretype.sql_instance.name 
            and not bool(repeat_regex.match(item.name))
        ]
        proceduretype_dict['platemap'] = procedure_dict['platemap']
        return proceduretype_dict
    
    def make_procedure_platemap(self):
        try:
            assert all([isinstance(s, PydSample) for s in self.sample])
            sample_dicts = self.sample
        except AssertionError:
            sample_dicts = [s.to_pydantic() for s in self.sql_instance.proceduresampleassociation]
        html = self.proceduretype.construct_plate_map(sample_dicts=sample_dicts, creation=False, vw_modifier=1.15)
        return html

    def to_html(self, **kwargs) -> str:
        # details = self.reorder_proceduretype_by_procedure()
        details = self.improved_dict
        output = super().to_html(**details)
        return output
    

class PydClientSubmission(PydConcrete):

    filepath: Path | None = Field(default=None)
    submissiontype: Annotated[SourcedField[str], RelationshipField(uselist=False)] = Field(default_factory=lambda: SourcedField(value=None, missing=True))
    # submitted_date: dict | None = Field(default=dict(value=date.today(), missing=True), validate_default=True)
    submitted_date:    SourcedField[datetime] = Field(default_factory=lambda: SourcedField(value=datetime.now(), missing=True))
    clientlab: Annotated[SourcedField[str], RelationshipField(uselist=False)]      = Field(default_factory=lambda: SourcedField(value=None, missing=True))
    sample_count: SourcedField[int] = Field(default_factory=lambda: SourcedField(value=0, missing=True))
    full_batch_size: int | dict = Field(default=0)
    submission_category: SourcedField[str] = Field(default_factory=lambda: SourcedField(value=None, missing=True))
    comment: list | None = Field(default_factory=list, repr=False, validate_default=True)
    cost_centre: SourcedField[str]      = Field(default_factory=lambda: SourcedField(value=None, missing=True))
    contact: SourcedField[str]      = Field(default_factory=lambda: SourcedField(value=None, missing=True))
    submitter_plate_id: SourcedField[str]      = Field(default_factory=lambda: SourcedField(value=None, missing=True))
    sample: Annotated[List[str | PydSample], RelationshipField(uselist=True)] = Field(default_factory=list, repr=False)
    run: Annotated[List[str | PydRun | dict ], RelationshipField(uselist=True)] = Field(default_factory=list, repr=False)

    model_config = ConfigDict(
        json_schema_extra = {
            "excluded": ['excluded', 'filepath', 'comment',
                         'sample', 
                         'run', 
                         'clientsubmissionsampleassociation',
                         'endrow', 
                         "abbreviation",
                         "full_batch_size"
                         
                         ],
            "key_value_order": ["submitter_plate_id",
                       "submitted_date",
                       "clientlab",
                       "contact",
                       "contact_email",
                       "cost_centre",
                       "submissiontype",
                       "sample_count",
                       "submission_category"]
        }
    )
    
    @field_validator("run", mode="before")
    @classmethod
    def enforce_run_list(cls, value):
        if isinstance(value, list):
            output = []
            for item in value:
                match item:
                    case str() | PydRun() | dict():
                        output.append(item)
                    case _:
                        logger.warning(f"Unmatched type {type(item)} in run list")
            return output
        else:
            match value:
                case str():
                    if value.upper() not in ["", "NA"]:
                        return [value]
                    else:                        
                        return []
                case PydRun() | dict():
                    return [value]
                case _:
                    logger.warning(f"Unmatched type {type(value)} for run field")
                    return []
                
    # @field_validator("submissiontype", "clientlab", "contact", mode="before")
    # @classmethod
    # def enforce_value(cls, value):
    #     if isinstance(value, str):
    #         value = dict(value=value, missing=False)
    #     return value

    # @field_validator("submitted_date", mode="before")
    # @classmethod
    # def enforce_submitted_date(cls, value):
    #     match value:
    #         case str():
    #             try:
    #                 value = parse(value)
    #             except ParserError:
    #                 value = None
    #             value = dict(value=value, missing=False)
    #         case datetime():
    #             value = dict(value=value, missing=False)
    #         case date():
    #             value = dict(value=datetime.combine(value, datetime.min.time()), missing=False)
    #         case _:
    #             pass
    #     return value

    # @field_validator("submitter_plate_id", mode="before")
    # @classmethod
    # def enforce_submitter_plate_id(cls, value):
    #     if isinstance(value, str):
    #         value = dict(value=value, missing=False)
    #     return value

    # @field_validator("submission_category", mode="before")
    # @classmethod
    # def enforce_submission_category_id(cls, value):
    #     if isinstance(value, str):
    #         value = dict(value=value, missing=False)
    #     return value

    # @field_validator("sample_count", mode="before")
    # @classmethod
    # def enforce_sample_count(cls, value):
    #     if value is None:
    #         value = dict(value=0, missing=True)
    #     if isinstance(value, str) or isinstance(value, int):
    #         value = dict(value=value, missing=False)
    #     return value

    # @field_validator("sample_count")
    # @classmethod
    # def enforce_integer(cls, value):
    #     if not value['value']:
    #         value['value'] = 0
    #     try:
    #         value['value'] = int(value['value'])
    #     except (ValueError, TypeError):
    #         raise TypeError(f"sample count value must be an integer, not {value['value']}")
    #     return value

    # @field_validator("submitter_plate_id")
    # @classmethod
    # def create_submitter_plate_num(cls, value, values):
    #     match value:
    #         case dict():
    #             if value['value'] in [None, "None", "NA"]:
    #                 from backend.db.models import ClientSubmission
    #                 match values.data['submitted_date']['value']:
    #                     case datetime():
    #                         submitted_date = values.data['submitted_date']['value'].strftime("%Y-%m-%d")
    #                     case date():
    #                         submitted_date = datetime.combine(values.data['submitted_date']['value'], datetime.now().time()).strftime("%Y-%m-%d")
    #                     case _:
    #                         submitted_date = datetime.now().strftime("%Y-%m-%d")
    #                 cli_lab = values.data.get('clientlab', dict(value=""))['value']
    #                 number = ClientSubmission.get_lab_submissions_by_day(clientlab=cli_lab) + 1
    #                 try:
    #                     val = f"{cli_lab}-{values.data['submission_category']['value']}-{submitted_date}-{number}"
    #                 except KeyError as e:
    #                     logger.error(values.data)
    #                     raise e
    #                 return dict(value=val, missing=True)
    #             else:
    #                 value['value'] = value['value'].strip()
    #                 return value
    #         case str():
    #             return dict(value=value, missing=False)
    #         case _:
    #             raise ValueError(f"Unmatched type {value} for PydClientSubmission._submitter_plate_id")

    # @field_validator("submitted_date")
    # @classmethod
    # def rescue_date(cls, value):
    #     if not value:
    #         value = dict(value=None)
    #     try:
    #         check = value['value'] is None
    #     except TypeError:
    #         check = True
    #     if check:
    #         value.update(dict(value=date.today(), missing=True))
    #     else:
    #         match value['value']:
    #             case str():
    #                 value['value'] = parse(value['value'])
    #             case _:
    #                 pass
    #     value['value'] = datetime.combine(value['value'], datetime.now().time())
    #     return value

    # @field_validator("submission_category")
    # @classmethod
    # def enforce_typing(cls, value, values):
        if not value['value'] in ["Research", "Diagnostic", "Surveillance", "Validation"]:
            try:
                value['value'] = values.data['submissiontype']['value']
            except (AttributeError, KeyError):
                value['value'] = "NA"
        return value

    # @field_validator("comment", mode="before")
    # @classmethod
    # def convert_comment_string(cls, value):
    #     if isinstance(value, str):
    #         value = dict(value=value, missing=True)
    #     return value

    @field_validator("full_batch_size")
    @classmethod
    def dict_to_int(cls, value):
        if isinstance(value, dict):
            value = value['value']
        value = int(value)
        return value

    # @field_validator("cost_centre", mode="before")
    # @classmethod
    # def str_to_dict(cls, value):
    #     if isinstance(value, str):
    #         value = dict(value=value)
    #     return value
    
    #   SourcedField input into a SourcedField instance.
    #
    #   This replaces ALL of the following field validators:
    #     enforce_value, enforce_submitted_date, enforce_submitter_plate_id,
    #     enforce_submission_category_id, enforce_sample_count, rescue_date,
    #     str_to_dict
    # ────────────────────────────────────────────────────────────────────────
 
    @model_validator(mode="before")
    @classmethod
    def coerce_sourced_fields(cls, data: dict) -> dict:
        """
        Normalise all SourcedField inputs before Pydantic processes them.
 
        Runs once, replacing 7 individual field validators that each did
        a fragment of the same job: wrapping a raw scalar / string / None
        into a {value, missing} dict.
        """
        if not isinstance(data, dict):
            return data
 
        # Plain string fields — submissiontype, clientlab, contact, cost_centre,
        # submission_category, submitter_plate_id
        for field in ("submissiontype", "clientlab", "contact",
                      "cost_centre", "submission_category", "submitter_plate_id"):
            if field in data:
                data[field] = _coerce_str_field(data[field])
 
        # Datetime field — submitted_date
        if "submitted_date" in data:
            data["submitted_date"] = _coerce_datetime_field(
                data["submitted_date"],
                fallback=datetime.now()
            )
 
        # Integer field — sample_count
        if "sample_count" in data:
            data["sample_count"] = _coerce_int_field(data["sample_count"])
 
        return data
 
    # ── Step 2: business-logic validators that depend on other fields
    #   now access sibling values via  values.data["field"].value
    #   instead of  values.data["field"]["value"]
    # ────────────────────────────────────────────────────────────────────────
 
    @model_validator(mode="after")
    def _validate_submission_category(self) -> "PydClientSubmission":
        valid = {"Research", "Diagnostic", "Surveillance", "Validation"}
        if self.submission_category.value not in valid:
            fallback = self.submissiontype.value or "NA"
            # Use object.__setattr__ to bypass validate_assignment
            object.__setattr__(
                self, "submission_category",
                SourcedField(value=fallback, missing=True)
            )
        return self


    @model_validator(mode="after")
    def _generate_plate_id(self) -> "PydClientSubmission":
        if self.submitter_plate_id.value not in (None, "None", "NA"):
            object.__setattr__(
                self, "submitter_plate_id",
                SourcedField(value=self.submitter_plate_id.value.strip(), missing=False)
            )
            return self

        from backend.db.models import ClientSubmission
        submitted = self.submitted_date.value
        submitted_str = submitted.strftime("%Y-%m-%d") if submitted else datetime.now().strftime("%Y-%m-%d")
        cli_lab  = self.clientlab.value or ""
        category = self.submission_category.value or "NA"
        number   = ClientSubmission.get_lab_submissions_by_day(clientlab=cli_lab) + 1

        object.__setattr__(
            self, "submitter_plate_id",
            SourcedField(
                value=f"{cli_lab}-{category}-{submitted_str}-{number}",
                missing=True
            )
        )
        return self

    @property
    def name(self):
        return self.submitter_plate_id.value

    def to_form(self, parent: QWidget, samples: List = [], disable: list | None = None):
        """
        Converts this instance into a frontend.widgets.submission_widget.SubmissionFormWidget

        Args:
            samples (list): a list of samples from this submission.
            disable (list, optional): a list of widgets to be disabled in the form. Defaults to None.
            parent (QWidget): parent widget of the constructed object

        Returns:
            SubmissionFormWidget: Submission form widget
        """
        from frontend.widgets.submission_widget import ClientSubmissionFormWidget
        if not samples:
            samples = self.sample
        # If not coming in from ClientSubmission sql -> make ranks.
        else:
            for iii, sample in enumerate(samples):
                sample.rank = iii
        return ClientSubmissionFormWidget(parent=parent, clientsubmission=self, samples=samples, disable=disable)

    # def to_sql(self, update: bool = True):
    #     from backend.db.models import ClientSubmission
    #     self.sql_instance: ClientSubmission = super().to_sql(update)

    #     def normalize_dict_field(field_name, value):
    #         if not isinstance(value, dict):
    #             return value
    #         if field_name in ["clientlab", "contact", "submissiontype"]:
    #             if "name" in value:
    #                 return value
    #             if "value" in value:
    #                 return {"name": value["value"]}
    #             return value
    #         if field_name in ["submission_category", "cost_centre", "submitter_plate_id", "submitted_date"]:
    #             return value.get("value")
    #         return value

    #     for field_name in ("clientlab", "contact", "submissiontype", "submission_category", "cost_centre", "submitted_date"):
    #         try:
    #             raw_value = getattr(self, field_name)
    #             normalized_value = normalize_dict_field(field_name, raw_value)
    #             setattr(self.sql_instance, field_name, normalized_value)
    #         except Exception as e:
    #             logger.error(f"Could not normalize {field_name} for {self}: {e}")
    #     self.sql_instance.sample = self.sample
    #     self.sql_instance.run = self.run
    #     return self.sql_instance, None

    def to_sql(self, update: bool = True):
        from backend.db.models import ClientSubmission
        # super().to_sql() handles ColumnProperty fields as before
        self.sql_instance: ClientSubmission = super().to_sql(update)
 
        # Before (today):
        #   def normalize_dict_field(field_name, value):
        #       if field_name in ["clientlab", "contact", "submissiontype"]:
        #           if "value" in value: return {"name": value["value"]}
        #       if field_name in ["submission_category", ...]:
        #           return value.get("value")
        #
        # After (with SourcedField):
        #   .value IS the unwrapped scalar — no helper needed at all.
 
        # Relationship fields that expect a name-string or {name} dict
        for field_name in ("clientlab", "contact", "submissiontype"):
            sf: SourcedField = getattr(self, field_name)
            if sf.value is not None:
                setattr(self.sql_instance, field_name, {"name": sf.value})
 
        # Scalar fields that map directly to a column
        for field_name in ("submission_category", "cost_centre", "submitted_date"):
            sf: SourcedField = getattr(self, field_name)
            setattr(self.sql_instance, field_name, sf.value)
 
        # submitter_plate_id is stored as a plain string on the SQL model
        self.sql_instance.submitter_plate_id = self.submitter_plate_id.value
 
        self.sql_instance.sample = self.sample
        self.sql_instance.run    = self.run
        return self.sql_instance, None
    
    @property
    def max_sample_rank(self) -> int:
        output: int = self.full_batch_size
        if output > 0:
            return output
        else:
            try:
                return max([getattr(item, "submission_rank", None) or getattr(item, "rank", None) for item in self.sample])
            except TypeError:
                return max([getattr(item, "submission_rank", None) for item in self.sql_instance.clientsubmissionsampleassociation])

    @property
    def improved_dict(self) -> dict:
        output = super().improved_dict
        output['run'] = [item.to_pydantic().improved_dict for item in self.sql_instance.run]
        try:
            output['contact_email'] = output['contact']['email']
        except TypeError:
            pass
        return sort_dict_by_list(output, self.class_config.key_value_order)

    @property
    def filename_template(self):
        return self.sql_instance.submissiontype.file_name_template
    
    def export_csv(self, filename: Path | str):
        try:
            worksheet = self.csv
        except AttributeError:
            logger.error("No csv found.")
            return
        if isinstance(filename, str):
            filename = Path(filename)
        with open(filename, 'w', newline="") as f:
            c = csv.writer(f)
            for r in worksheet.rows:
                c.writerow([cell.value for cell in r])

    def to_html(self, **kwargs):
        details = self.improved_dict_expand_fields(fields=[{"run":['procedure', 'sample']}, "sample"])
        details['sample'] = [sample.sample_id for sample in self.sql_instance.sample]
        # Up to this point, the samples are fine.
        output = super().to_html(**details)
        return output


class PydRun(PydConcrete):

    clientsubmission: Annotated[PydClientSubmission | str | None, RelationshipField(uselist=False)] = Field(default=None, repr=False)
    rsl_plate_number:  SourcedField[str]      = Field(default_factory=lambda: SourcedField(value=None, missing=True))
    started_date:      SourcedField[datetime] = Field(default_factory=lambda: SourcedField(value=datetime.now(), missing=True))
    completed_date:    SourcedField[datetime] = Field(default_factory=lambda: SourcedField(value=None, missing=True))
    comment: SourcedField[list] = Field(default_factory=lambda: SourcedField(value=[], missing=True))
    sample: Annotated[List[PydSample] | Generator, AfterValidator(ensure_list), RelationshipField(uselist=True)] = Field(default_factory=list, repr=False)
    run_cost:          SourcedField[float]    = Field(default_factory=lambda: SourcedField(value=0.0, missing=True))
    signed_by:         SourcedField[str]      = Field(default_factory=lambda: SourcedField(value="", missing=True))
    procedure: Annotated[List[PydProcedure] | Generator, RelationshipField(uselist=True)] = Field(default=[], repr=False)

    model_config = ConfigDict(
        json_schema_extra = {
            "excluded": ["excluded", "sample", "procedure", "runsampleassociation", "permission", "namer", "filepath"]
        }
    )

    @property
    def sample_count(self):
        v = list(self.sample)
        return len(v)

    # @field_validator("signed_by")
    # @classmethod
    # def rescue_signed_by(cls, value):
    #     if isinstance(value, str):
    #         value = dict(value=value, missing=True)
    #     return value

    # @field_validator("run_cost")
    # @classmethod
    # def rescue_run_cost(cls, value):
    #     if isinstance(value, float):
    #         value = dict(value=value, missing=False)
    #     return value

    # @field_validator("started_date", mode="before")
    # @classmethod
    # def rescue_start_date(cls, value):
    #     if not isinstance(value, dict):
    #         value = dict(value=value, missing=True)
    #     try:
    #         check = value['value'] is None
    #     except TypeError:
    #         check = True
    #     if check:
    #         return dict(value=date.today(), missing=True)
    #     return value

    # @field_validator("completed_date", mode="before")
    # @classmethod
    # def rescue_completed_date(cls, value):
    #     if not isinstance(value, dict):
    #         value = dict(value=value, missing=True)
    #     return value

    # @field_validator("started_date")
    # @classmethod
    # def strip_started_datetime_string(cls, value):
    #     match value['value']:
    #         case datetime():
    #             output = value['value']
    #         case date():
    #             output = datetime.combine(value['value'], datetime.min.time())
    #         case int():
    #             output = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value['value'] - 2)
    #         case str():
    #             string = re.sub(r"(_|-)\d(R\d)?$", "", value['value'])
    #             try:
    #                 output = parse(string)
    #                 value['missing'] = True
    #             except ParserError as e:
    #                 logger.error(f"Problem parsing date: {e}")
    #                 try:
    #                     output = parse(string.replace("-", ""))
    #                     value['missing'] = True
    #                 except Exception as e:
    #                     logger.error(f"Problem with parse fallback: {e}")
    #                     return value
    #         case _:
    #             raise ValueError(f"Unmatched value {value['value']} for datetime")
    #     value['value'] = output.replace(tzinfo=timezone)
    #     return value

    # @field_validator("completed_date")
    # @classmethod
    # def strip_completed_datetime_string(cls, value):
    #     match value['value']:
    #         case datetime():
    #             output = value['value']
    #         case date():
    #             output = datetime.combine(value['value'], datetime.min.time())
    #         case int():
    #             output = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value['value'] - 2)
    #         case str():
    #             string = re.sub(r"(_|-)\d(R\d)?$", "", value['value'])
    #             try:
    #                 output = dict(value=parse(string).date(), missing=True)
    #             except ParserError as e:
    #                 logger.error(f"Problem parsing date: {e}")
    #                 try:
    #                     output = parse(string.replace("-", "")).date()
    #                 except Exception as e:
    #                     logger.error(f"Problem with parse fallback: {e}")
    #                     return value
    #         case _:
    #             # raise ValueError(f"Could not get datetime from {value['value']}")
    #             return dict(value=None, missing=True)
    #     value['value'] = output.replace(tzinfo=timezone)
    #     return value

    # @field_validator("rsl_plate_number", mode='before')
    # @classmethod
    # def rescue_rsl_number(cls, value):
    #     if not isinstance(value, dict):
    #         if value:
    #             missing = False
    #         else:
    #             missing = True
    #         return dict(value=value, missing=missing)
    #     return value

    # @field_validator("rsl_plate_number")
    # @classmethod
    # def rsl_from_file(cls, value, values):
    #     sub_type = values.data.get('clientsubmission', None)
    #     try:
    #         assert sub_type is not None
    #     except AssertionError:
    #         raise KeyError(f"'clientsubmission' not found in {pformat(values.data)}")
    #     if check_not_nan(value.value):
    #         value.value = value.value.strip()
    #         return value
    #     else:
    #         output = RSLNamer(filename=sub_type.filepath.__str__(), submission_type=sub_type.submissiontype,
    #                               data=values.data).parsed_name
    #         return dict(value=output, missing=True)

    @model_validator(mode="before")
    @classmethod
    def coerce_sourced_fields(cls, data: dict) -> dict:
        """
        Replaces: rescue_start_date, rescue_completed_date,
                  strip_started_datetime_string, strip_completed_datetime_string,
                  rescue_run_cost, rescue_signed_by, rescue_rsl_number.
        """
        if not isinstance(data, dict):
            return data
 
        for field in ("started_date", "completed_date"):
            if field in data:
                data[field] = _coerce_datetime_field(data[field])
 
        for field in ("rsl_plate_number", "signed_by"):
            if field in data:
                data[field] = _coerce_str_field(data[field])
 
        if "run_cost" in data:
            raw = data["run_cost"]
            # run_cost is SourcedField[float], not int — handle separately
            if isinstance(raw, SourcedField):
                pass
            elif isinstance(raw, dict) and "value" in raw:
                data["run_cost"] = SourcedField(value=float(raw["value"] or 0.0),
                                                missing=raw.get("missing", True))
            else:
                data["run_cost"] = SourcedField(value=float(raw or 0.0), missing=raw is None)
        if "comment" in data:
            raw = data['comment']

        return data

    @field_validator("rsl_plate_number", mode="after")
    @classmethod
    def rsl_from_file(cls, value: SourcedField[str], values) -> SourcedField[str]:
        """
        If the RSL plate number was not parsed from the source file,
        generate it via RSLNamer.
 
        Before: value['value'], value['value'].strip()
        After:  value.value,    value.value.strip()
        """
        from tools import check_not_nan
        sub_type = values.data.get("clientsubmission", None)
        if sub_type is None:
            raise KeyError(f"'clientsubmission' missing from data")
 
        if check_not_nan(value.value):
            # Value was present — just normalise whitespace
            return SourcedField(value=value.value.strip(), missing=False)
        else:
            # Generate from filename
            from backend.validators import RSLNamer
            generated = RSLNamer(
                filename=sub_type.filepath.__str__(),
                submission_type=sub_type.submissiontype,
                data=values.data
            ).parsed_name
            return SourcedField(value=generated, missing=True)


    @field_validator("sample", mode="before")
    @classmethod
    def expand_samples(cls, value):
        if isinstance(value, Generator):
            return [PydSample(**sample) for sample in value]
        elif isinstance(value, list):
            return [PydSample(**sample) if isinstance(sample, dict) else sample for sample in value]
        return value

        # ── Step 1: a single mode="before" model_validator normalises every
    
 
    # ── to_sql: normalize_dict_field is gone ────────────────────────────────


    # def __init__(self, **data):
    #     super().__init__(**data)
    #     # NOTE: this could also be done with default_factory
    #     # from backend.db.models import ClientSubmission
    #     clientsub = self.sql_instance.clientsubmission
    #     try:
    #         submission_type = clientsub.submissiontype
    #     except AttributeError:
    #         submission_type = "Default SubmissionType"
    #     self.namer = RSLNamer(submission_type=submission_type)

    @cached_property
    def namer(self) -> RSLNamer:
        try:
            submission_type = self.sql_instance.clientsubmission.submissiontype
        except AttributeError:
            submission_type = "Default SubmissionType"
        return RSLNamer(submission_type=submission_type)

    # def to_sql(self, update: bool = True):
    #     from backend.db.models import Run
    #     self.sql_instance: Run = super().to_sql(update=update)
    #     if not update:
    #         return self.sql_instance, None
    #     self.sql_instance.clientsubmission = self.clientsubmission
    #     self.sql_instance.procedure = self.procedure
    #     self.sql_instance.sample = [sample for sample in self.sample if PydSample.is_sample_id_valid(sample)]
    #     return self.sql_instance, None

    def to_sql(self, update: bool = True):
        from backend.db.models import Run
        self.sql_instance: Run = super().to_sql(update=update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.clientsubmission = self.clientsubmission
        self.sql_instance.procedure        = self.procedure
        # .value is the unwrapped datetime — no normalize_dict_field needed
        self.sql_instance.started_date   = self.started_date.value
        self.sql_instance.completed_date = self.completed_date.value
        self.sql_instance.signed_by      = self.signed_by.value
        self.sql_instance.run_cost       = self.run_cost.value
        self.sql_instance.sample = [
            s for s in self.sample if s.__class__.__name__ == "PydSample" and
            s.__class__.is_sample_id_valid(s)
        ]
        return self.sql_instance, None


    @property
    def export_filename(self) -> str:
        """
        Creates filename for this instance

        Returns:
            str: Output filename
        """
        try:
            template = self.sql_instance.clientsubmission.submissiontype.file_name_template
        except KeyError as e:
            template = "{{ rsl_plate_number }}{% if clientsubmission %}_{{ clientsubmission }}{% endif %}{% if completed_date %}_{{ completed_date }}{% endif %}"
        render = self.namer.construct_export_name(template=template, **self.improved_dict).replace("/", "")
        return render

    @property
    def improved_dict(self) -> dict:
        output = super().improved_dict
        output['procedure'] = [item.to_pydantic().improved_dict for item in self.sql_instance.procedure]
        output['sample_count'] = self.sample_count
        return output

    def to_html(self, **kwargs):
        details = self.improved_dict_expand_fields(fields=['procedure', 'sample'])
        output = super().to_html(**details)
        return output

    def add_samples(self, samples):
        if not isinstance(samples, list):
            samples = [samples]
        for sample in samples:
            if sample not in self.sample:
                self.sample.append(sample)


class PydTipsLot(PydConcrete):
    
    lot: str = Field(default="NA", description="Lot number of the tips")
    expiry: datetime = Field(default_factory=lambda: datetime.now() + timedelta(365), description="Expiry date of the tips", validate_default=True)
    active: bool = Field(default=True, description="Is this tips lot active?", validate_default=True)
    tips: Annotated[str, RelationshipField(uselist=False)] = Field(default="NA", description="The Tips this lot belongs to.", repr=True)

    @field_validator("tips", mode="before")
    @classmethod
    def make_default_tips(cls, value):
        if value is None:
            value = ""
        return value

    # TODO: Move to shared along with PydReagentLot
    @field_validator("expiry")
    @classmethod
    def parse_expiry(cls, value):
        if not value:
            value = date.today() + timedelta(days=3650)
        match value:
            case str():
                try:
                    value = parse(value)
                except ParserError:
                    value = None
            case date() | datetime():
                value = datetime.combine(value, datetime.max.time())
            case _:
                value = None
        return value
    
    _validate_bool = field_validator("active", mode="before")(coerce_int_to_bool)

    # @field_validator("active", mode="before")
    # @classmethod
    # def int_to_bool(cls, value):
    #     if isinstance(value, int):
    #         value = bool(value)
    #     return value

    @property
    def name(self) -> str:
        try:
            manufacturer = self.sql_instance.tips.manufacturer
        except AttributeError:
            manufacturer = "Unassigned manufacturer"
        try:
            ref = self.sql_instance.tips.ref
        except AttributeError:
            ref = "Unassigned manufacturer"
        return f"{manufacturer} - {ref} - {self.lot}"

    # def to_sql(self, update: bool = True):
    #     from backend.db.models import TipsLot
    #     self.sql_instance: TipsLot = super().to_sql(update=update)
    #     if not update:
    #         return self.sql_instance, None
    #     self.sql_instance.tips = self.tips
    #     return self.sql_instance, None


class PydProcedureSampleAssociation(PydConcrete):

    row: int = Field(default=0)
    column: int = Field(default=0)
    procedure_rank: int = Field(default=0)  #: Location in sample list
    procedure: Annotated[str | PydProcedure, RelationshipField(uselist=False)] = Field(default="NA")
    sample: Annotated[str | PydSample, RelationshipField(uselist=False)] = Field(default="NA")
    results: Annotated[List[dict | PydResults], RelationshipField(uselist=True)] = Field(default_factory=list, repr=False)
    enabled: bool = Field(default=True)
    is_control: int = Field(default=0, repr=False)

    model_config = ConfigDict(
        json_schema_extra = {
            'excluded': ['excluded', 'results', 'sample', 'name', 'is_control', 'sampleclientsubmissionassociation', 'clientsubmission', 'run', 'comment',
                               'samplerunassociation', 'sampleprocedureassociation', "background_color", 'control_type', 'rank', 'enabled', "submitted_date"],
            "renderclass": "sample"
        }
    )

    @field_validator("row", mode="before")
    @classmethod
    def row_str_to_int(cls, value):
        if value is None:
            value = 0
        if isinstance(value, str):
            try:
                value = row_keys[value]
            except KeyError:
                value = 0
        return value

    @field_validator("column", mode="before")
    @classmethod
    def column_str_to_int(cls, value):
        if value is None:
            value = 0
        if isinstance(value, str):
            value = 0
        return value

    # def to_sql(self, update: bool = True):
    #     from backend.db.models import ProcedureSampleAssociation
    #     self.sql_instance: ProcedureSampleAssociation = super().to_sql(update=update)
    #     if not update:
    #         return self.sql_instance, None
    #     self.sql_instance.procedure = self.procedure
    #     self.sql_instance.sample = self.sample
    #     self.sql_instance.results = self.results
    #     return self.sql_instance, None
    
    @property
    def improved_dict(self) -> dict:
        output = super().improved_dict
        output['sample_id'] = self.sample.sample_id if isinstance(self.sample, PydSample) else self.sample
        output['procedure'] = self.procedure.name if isinstance(self.procedure, PydProcedure) else self.procedure
        return output
    
    
class PydProcedureEquipmentAssociation(PydConcrete):

    start_time: datetime = Field(default_factory=datetime.now, description="Start time of equipment use", validate_default=True)
    end_time: datetime = Field(default_factory=datetime.now, description="End time of equipment use", validate_default=True)
    procedure: Annotated[str | dict | PydProcedure, RelationshipField(uselist=False)] = Field(default="NA")
    equipment: Annotated[str | dict | PydEquipment, RelationshipField] = Field(default="NA")
    equipmentrole: Annotated[str | dict | PydEquipmentRole, RelationshipField(uselist=False)] = Field(default="NA")
    processversion: Annotated[str | dict |  PydProcessVersion | None, RelationshipField(uselist=False)] = Field(default=None)
    tipslot: Annotated[List[str | dict | PydTipsLot], RelationshipField(uselist=True)] = Field(default_factory=list)
    calibration_date: datetime = Field(default = datetime.combine(date=datetime(year=2000, month=1, day=1), time=datetime.min.time()), 
                                       description="Calibration date previous to use.", repr=False)

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def set_starttime(cls, value):
        if not value:
            value = datetime.now()
        return value
    
    @field_validator("tipslot", mode="before")
    @classmethod
    def set_tipslot(cls, value):
        if value is None:
            return []
        if isinstance(value, str) or isinstance(value, dict) or isinstance(value, dict):
            return [value]
        return value

    @property
    def constructed_name(self) -> str:
        match self.procedure:
            case str():
                procedure = self.procedure
            case dict():
                procedure = self.procedure.get('name', "Unassigned Procedure")
            case PydProcedure():
                procedure = self.procedure.name
            case _:
                procedure = "Unassigned Procedure"
        match self.equipment:
            case str():
                equipment = self.equipment
            case dict():
                equipment = self.equipment.get('name', "Unassigned Equipment")
            case PydProcedure():
                equipment = self.equipment.name
            case _:
                equipment = "Unassigned Equipment"
        return f"{procedure}->{equipment}"

    # def to_sql(self, update: bool = True):
    #     from backend.db.models import ProcedureEquipmentAssociation
    #     self.sql_instance: ProcedureEquipmentAssociation = super().to_sql(update=update)
    #     if not update:
    #         return self.sql_instance, None
    #     self.sql_instance.equipment = self.equipment
    #     self.sql_instance.equipmentrole = self.equipmentrole
    #     self.sql_instance.processversion = self.processversion
    #     self.sql_instance.tipslot = self.tipslot
    #     return self.sql_instance, None


class PydProcedureReagentLotAssociation(PydConcrete):

    procedure: Annotated[str | dict | PydProcedure, RelationshipField(uselist=False)] = Field(default="NA")
    reagentlot: Annotated[str | dict |  PydReagentLot, RelationshipField(uselist=False)] = Field(default="NA")
    reagentrole: Annotated[str | dict | PydReagentRole, RelationshipField(uselist=False)] = Field(default="NA", repr=False)
    
    @property
    def constructed_name(self) -> str:
        match self.procedure:
            case str():
                procedure = self.procedure
            case dict():
                procedure = self.procedure.get('name', "Unassigned Procedure")
            case PydProcedure():
                procedure = self.procedure.name
            case _:
                procedure = "Unassigned Procedure"
        if isinstance(procedure, dict):
            procedure = procedure.get("value", "Unassigned Procedure")
        match self.reagentlot:
            case str():
                reagentlot = self.reagentlot
            case dict():
                reagentlot = self.reagentlot.get('name', "Unassigned ReagentLot")
            case PydReagentLot():
                reagentlot = self.reagentlot.name
            case _:
                reagentlot = "Unassigned ReagentLot"
        return f"{procedure}->{reagentlot}"

    # def to_sql(self, update: bool = True):
    #     from backend.db.models import ProcedureReagentLotAssociation
    #     self.sql_instance: ProcedureReagentLotAssociation = super().to_sql(update=update)
    #     if not update:
    #         return self.sql_instance, None
    #     self.sql_instance.procedure = self.procedure
    #     self.sql_instance.reagentlot = self.reagentlot
    #     self.sql_instance.reagentrole = self.reagentrole
    #     return self.sql_instance, None
    #     # NOTE: Handle repeat naming.
        

class PydClientSubmissionSampleAssociation(PydConcrete):

    row: int = Field(default=0)
    column: int = Field(default=0)
    submission_rank: int = Field(default=0)  #: Location in sample list
    clientsubmission: Annotated[str | dict |  PydClientSubmission, RelationshipField(uselist=False)] = Field(default="NA")
    sample: Annotated[str | dict | PydSample, RelationshipField(uselist=False)] = Field(default="NA")
    enabled: bool = Field(default=True)
    comment: list | None = Field(default_factory=list, repr=False)

    # def to_sql(self, update: bool = True):
    #     from backend.db.models import ClientSubmissionSampleAssociation
    #     self.sql_instance: ClientSubmissionSampleAssociation = super().to_sql(update=update)
    #     if not update:
    #         return self.sql_instance, None
    #     self.sql_instance.clientsubmission = self.clientsubmission
    #     self.sql_instance.sample = self.sample
    #     return self.sql_instance, None
    