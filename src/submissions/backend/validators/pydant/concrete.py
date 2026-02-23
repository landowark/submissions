
from __future__ import annotations
from pprint import pformat
import csv, logging, re, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import ClassVar, Generator, List, Tuple, TYPE_CHECKING
from pydantic import Field, field_validator, model_validator
from PyQt6.QtWidgets import QWidget
from dateutil.parser import parse, ParserError
from backend.validators import RSLNamer
from backend.validators.pydant import PydConcrete
from backend.validators.pydant.abstract import PydEquipmentRole, PydProcedureType, PydReagent, PydResultsType, PydReagentRole
from tools import Alert, Report, check_not_nan, find_first_matching_dict, report_result, row_keys, sort_dict_by_list, timezone
if TYPE_CHECKING:
    from backend.db.models.submissions import Run

logger = logging.getLogger(f"submissions.{__name__}")


class PydResults(PydConcrete, arbitrary_types_allowed=True):

    result: dict = Field(default={}, repr=False)
    resultstype: str | PydResultsType = Field(default="NA")
    image: None | bytes = Field(default=None, repr=False)
    procedure: str | PydProcedure | None = Field(default=None)
    sample: str | PydSample | None = Field(default=None)
    date_analyzed: datetime | None = Field(default=None, repr=False, validate_default=True)

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

    def to_sql(self):
        from backend.db.models import Results, ProcedureSampleAssociation, Procedure
        sql, _ = Results.query_or_create(resultstype=self.resultstype, result=self.result)
        try:
            check = sql.image
        except FileNotFoundError:
            check = False
        if not check:
            sql.image = self.image
        if not sql.date_analyzed:
            sql.date_analyzed = self.date_analyzed
        match self.parent:
            case ProcedureSampleAssociation():
                sql.sampleprocedureassociation = self.parent
            case Procedure():
                sql.procedure = self.parent
            case _:
                logger.error("Improper association found.")
        return sql


class PydReagentLot(PydConcrete):

    lot: str = Field(default="NA", description="Lot number of this reagent.")
    reagent: str | PydReagent | None = Field(default=None, description="Type of reagent this lot is.")
    reagentrole: str | None = Field(default=None, repr=False)
    expiry: datetime = Field(default = None, description="Expiry date of this reagent lot.", validate_default=True)
    missing: bool = Field(default=True, repr=False)
    active: bool = Field(default=True, description="Is this lot currently in use?", repr=False)

    @field_validator("active", mode="before")
    @classmethod
    def active_bool(cls, value):
        return bool(value)

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
            return f"{reagent} - {self.lot}"

    def to_sql(self, update: bool = True):
        from backend.db.models import ReagentLot
        self.sql_instance: ReagentLot = super().to_sql(update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.reagent = self.reagent
        return self.sql_instance, None


class PydDiscount(PydConcrete):

    description: str = Field(default="NA", description="Brief description of this discount.")
    proceduretype: str | None = Field(default="NA", description="ProcedureType this discount applies to.", repr=False)
    clientlab: str | None = Field(default="NA", description="ClientLab this discount applies to.", repr=False)
    amount: float = Field(default=0.0, description="Amount (dollars) of discount to apply.")

    def to_sql(self, update: bool = True):
        from backend.db.models import Discount
        self.sql_instance: Discount = super().to_sql(update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.proceduretype = self.proceduretype
        self.sql_instance.clientlab = self.clientlab
        return self.sql_instance, None


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

    # @model_validator(mode="after")
    # def populate_sql_instance(self) -> "PydSample":
    #     """
    #     Ensure that a usable SQL `Sample` instance exists after PydSample
    #     initialization. If the prepared `sql_instance` does not have a
    #     SQLAlchemy `_sa_instance_state` (i.e. it's a plain/unsaved object),
    #     populate its important fields from the pydantic model so that
    #     downstream assignment to association setters does not end up
    #     converting it to None due to missing `sample_id`.
    #     """
    #     # Attempt to get existing sql_instance (may be None)
    #     sql_inst = getattr(self, "sql_instance", None)
    #     # If no sql_instance yet, ask super to prepare a blank one (no DB write)
    #     if sql_inst is None:
    #         try:
    #             res = super().to_sql(update=False)
    #             # super().to_sql may return (instance, None) in this codebase
    #             if isinstance(res, tuple):
    #                 sql_inst = res[0]
    #             else:
    #                 sql_inst = res
    #         except Exception:
    #             sql_inst = None
    #     # If we have a sql instance and it's not a bound SA instance, populate fields
    #     if sql_inst is not None and not hasattr(sql_inst, "_sa_instance_state"):
    #         try:
    #             # set sample_id only if valid
    #             if getattr(self, "sample_id", None) and PydSample.is_sample_id_valid(self.sample_id):
    #                 sql_inst.sample_id = self.sample_id
    #         except Exception:
    #             pass
    #         try:
    #             # Ensure misc_info exists and populate common metadata
    #             try:
    #                 misc = sql_inst._misc_info
    #                 if misc is None:
    #                     sql_inst._misc_info = {}
    #             except Exception:
    #                 sql_inst._misc_info = {}
    #             # populate rank/row/column/enabled/is_control where present
    #             meta = {
    #                 "rank": getattr(self, "rank", None),
    #                 "row": getattr(self, "row", None),
    #                 "column": getattr(self, "column", None),
    #                 "enabled": getattr(self, "enabled", None),
    #                 "is_control": getattr(self, "is_control", None),
    #             }
    #             for k, v in meta.items():
    #                 if v is not None:
    #                     sql_inst._misc_info[k] = v
    #         except Exception:
    #             pass
    #         # Attach back to pyd instance for later use
    #         try:
    #             self.sql_instance = sql_inst
    #         except Exception:
    #             pass
    #     return self
    
    @property
    def constructed_name(self):
        return self.sample_id
    
    # @property
    # def improved_dict(self) -> dict:
    #     output = super().improved_dict
    #     output['name'] = self.sample_id
    #     return output

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
                return False
        if sample_id.lower().startswith("blank"):
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
    procedure: List[str] = Field(default_factory=list, repr=False)
    equipmentrole: List[str] | List[dict] = Field(default_factory=list, description="Roles this equipment can fill.", repr=False)
    
    @field_validator("manufacturer", "ref", mode="before")
    @classmethod
    def validate_optional_strings(cls, value):
        if value is None:
            return "NA"
        return value

    @field_validator('nickname')
    @classmethod
    def set_nickname_to_name(cls, value, values):
        if not value or value == "NA":
            value = values.data['name']
        return value

    def to_sql(self, update: bool = True):
        from backend.db.models import Equipment
        self.sql_instance: Equipment = super().to_sql(update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.procedure = self.procedure
        self.sql_instance.equipmentrole = self.equipmentrole
        return self.sql_instance, None


class PydContact(PydConcrete):

    name: str = Field(default="NA", description="Name of this contact.")
    tel: str = Field(default="000-000-0000", description="Phone number of this contact.")
    email: str = Field(default="NA", description="Email address of this contact.")
    clientlab: List[str] = Field(default_factory=list)

    @field_validator("tel")
    @classmethod
    def enforce_phone_number(cls, value):
        area_regex = re.compile(r"^\(?(\d{3})\)?(-| )?")
        if len(value) > 8:
            match = area_regex.match(value)
            value = area_regex.sub(f"({match.group(1).strip()}) ", value)
        return value

    def to_sql(self, update: bool = True):
        from backend.db.models import Contact
        self.sql_instance: Contact = super().to_sql(update=update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.clientlab = self.clientlab
        return self.sql_instance, None


class PydClientLab(PydConcrete):

    name: str = Field(default="NA", description="Name of this Client Lab.")
    cost_centre: str = Field(default="NA", description="Default cost centre for this Client Lab.", repr=False)
    contact: List[str] = Field(default_factory=list, description="Contacts for this Client Lab.", repr=False)

    def to_sql(self, update: bool = True):
        from backend.db.models import ClientLab
        self.sql_instance: ClientLab = super().to_sql(update=update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.contact = self.contact
        return self.sql_instance, None


class PydProcessVersion(PydConcrete, extra="allow", arbitrary_types_allowed=True):
    
    version: float = Field(default=1.0, description="Version number of this process.")
    date_verified: datetime = Field(default_factory=datetime.now, description="Date this version was verified.", validate_default=True)
    project: str = Field(default="NA", description="Project this process version is for.")
    active: bool = Field(default=True, description="Is this the active version?")
    process: str = Field(default="NA", description="Process this is a version of.")

    field_validator("date_verified", mode="before")
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
    
    @field_validator("active", mode="before")
    @classmethod
    def int_to_bool(cls, value):
        if value is None:
            value = True
        if isinstance(value, str):
            if value.lower() in ["false", "0", "no", "off"]:
                value = False
            else:
                value = True
        if isinstance(value, int):
            value = bool(value)
        return value
    
    # @field_validator("active")
    # @classmethod
    # def enforce_active(cls, value):
        
    #     return value

    def to_sql(self, update: bool = True):
        from backend.db.models import ProcessVersion
        self.sql_instance: ProcessVersion = super().to_sql(update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.process = self.process
        return self.sql_instance, None

    
class PydProcedure(PydConcrete, arbitrary_types_allowed=True):
    
    proceduretype: str | PydProcedureType | None = Field(default=None)
    run: str | PydRun | None = Field(default=None)
    technician: dict = Field(default=dict(value="NA", missing=True), repr=False)
    repeat: bool = Field(default=False, repr=False)
    repeat_of: str | PydProcedure | None = Field(default=None, repr=False)
    name: dict = Field(default_factory=lambda: {"value": "NA", "missing": True}, validate_default=True)
    platemap: str | None = Field(default=None, repr=False)
    reagentlot: List[str] | List[PydProcedureReagentLotAssociation] = Field(default_factory=list, repr=False)
    sample: List[str | PydSample] = Field(default_factory=list, repr=False)
    equipment: List[str] | List[PydProcedureEquipmentAssociation] = Field(default_factory=list, repr=False)
    results: List[dict] | List[PydResults] = Field(default_factory=list, repr=False)
    started_date: datetime = Field(default_factory=datetime.now, repr=False)
    completed_date: datetime | None = Field(default_factory=datetime.now, repr=False)

    @field_validator("technician", mode="before")#"kittype", mode="before")
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
                value = ProcedureType.query(name=value['name']).to_pydantic()
            case str():
                value = ProcedureType.query(name=value).to_pydantic()
            case ProcedureType():
                value = value.to_pydantic()
            case PydProcedureType():
                value = value
            case _:
                pass
        return value

    @field_validator("run")
    @classmethod
    def lookup_run(cls, value):
        from backend.db.models import Run
        # When converting a Run -> PydRun the procedure dicts include the run
        # as a simple name string. Converting that string back into a full
        # PydRun here would cause a recursive conversion: Run.to_pydantic ->
        # PydProcedure -> lookup_run -> Run.to_pydantic -> ... leading to
        # infinite recursion. Instead, keep the run as the simple string name
        # (or the found SQL Run) and let higher-level code handle converting
        # to a PydRun only when it's safe to do so.
        if isinstance(value, str):
            # Do NOT call Run.query(...).to_pydantic() here to avoid recursion.
            # Return the raw name so downstream consumers can access it safely.
            return value
        # If a Run SQL instance was supplied directly, leave it as-is (don't
        # convert to pydantic here).
        return value
    
    @field_validator("repeat_of")
    @classmethod
    def drop_empty_string(cls, value):
        if value == "":
            value = None
        return value
    
    @field_validator("name", mode="before")
    @classmethod
    def name_to_dict(cls, value):
        if isinstance(value, str):
            missing = False
            if value in [None, "", "NA"]:
                missing = True
            value = dict(value=value, missing=missing)
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

    @model_validator(mode="after")
    def validate_this(self) -> PydProcedure:
        # At this point, ALL fields (including defaults) are populated on 'self'
        if self.name.get("value") == "NA":
            # 1. Resolve Procedure Type
            pt_name = getattr(self.proceduretype, "name", str(self.proceduretype)) if self.proceduretype else "Unassigned ProcedureType"
            if isinstance(pt_name, dict):
                pt_name = pt_name.get("value", "Unassigned ProcedureType")
            # 2. Resolve Run
            run_id = getattr(self.run, "rsl_plate_number", str(self.run)) if self.run else "Unassigned Run"
            if isinstance(run_id, dict):
                run_id = run_id.get("value", "Unassigned Run")
            # 3. Resolve Repeat
            rep_suffix = f" ({getattr(self.repeat_of, 'name', str(self.repeat_of))})" if self.repeat_of else ""
            # Update the instance directly
            self.name = {"value": f"{run_id}-{pt_name}{rep_suffix}", "missing": True}
        return self

    @field_validator("started_date", mode="before")
    @classmethod
    def create_started_date(cls, value):
        if not value:
            value = datetime.now()
        return value

    @field_validator("sample", mode="before")
    @classmethod
    def convert_association(cls, value):
        output = None
        if isinstance(value, list):
            output = []
            for sample in value:
                match sample:
                    case PydProcedureSampleAssociation():
                        output.append(sample.sample)
                    case PydSample() | str():
                        output.append(sample)
                    case dict():
                        output.append(PydSample(**sample))
                    case _:
                        logger.error(f"Unmatched type {type(sample)} for sample")
                        continue
        return output

    def __init__(self, **data):
        super().__init__(**data)
        if isinstance(self.run, PydRun):
            run = self.run.name
        else:
            run = self.run
        if isinstance(self.proceduretype, PydProcedureType):
            proceduretype = self.proceduretype.name
        else:
            proceduretype = self.proceduretype
        if isinstance(self.repeat_of, PydProcedure):
            repeat_of = f" ({self.repeat_of.name})"
        elif isinstance(self.repeat_of, str):
            repeat_of = f" ({self.repeat_of})"
        else:
            repeat_of = ""
        self.name = dict(value=f"{run}-{proceduretype}{repeat_of}-{self.started_date.strftime("%Y-%m-%d %H:%M:%S")}", missing=False)

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
        # Build a new ordered list of samples matching the sample_list order.
        new_samples: List[PydSample] = []
        for iii, sample_dict in enumerate(sample_list, start=1):
            # logger.debug(f"Sample: {sample_dict}")
            sample_id = sample_dict.get('sample_id', '')
            # normalize blank markers
            if isinstance(sample_id, str) and sample_id.startswith("blank_"):
                sample_id = ""
            try:
                row, column = self.proceduretype.ranked_plate[sample_dict['index']]
            except KeyError:
                continue
            try:
                sample = find_first_matching_dict(self.sample, "sample_id", sample_dict['sample_id'])
            except StopIteration:
                sample = PydSample(sample_id=sample_id)
            # Do NOT change the sample_id (we want to preserve the existing sample's identity).
            # Update position/rank/control/classification metadata.
            sample.row = row
            sample.column = column
            sample.rank = int(sample_dict.get('index', iii))
            # try:
            #     well_class = sample_dict.get('class', '').replace("well ", "").split(" ")[0]
            # except IndexError:
            #     well_class = ""
            well_class = next((item for item in sample_dict.get('class', '').replace("well ", "").split(" ") if item in ['negativecontrol', 'positivecontrol']), "")
            # logger.debug(f"Got well_class: {well_class}")
            match well_class:
                case "negativecontrol":
                    sample.is_control = -1
                case "positivecontrol":
                    sample.is_control = 1
                case _:
                    sample.is_control = 0
            new_samples.append(sample)
        # Replace the sample list with the reordered list. Preserve any samples not present in
        # sample_list by appending them after the ordered ones (so they are not lost).
        remaining = []#[s for s in self.sample if s not in new_samples]
        self.sample = sorted(new_samples + remaining, key=lambda x: (x.column, x.row))
        logger.debug(f"Rearranged samples:\n{pformat(self.sample)}")

    def update_reagents(self, reagentrole: str, name: str, lot: str, expiry: str|None=None, checked:bool=True):
        from backend.db.models import ReagentLot
        try:
            removable = next((item for item in self.reagentlot if reagentrole in (rr.name for rr in item.reagentlot.sql_instance.reagent.reagentrole)), None)
        except AttributeError as e:
            raise e
        if removable:
            idx = self.reagentlot.index(removable)
            self.reagentlot.remove(removable)
        else:
            idx = 0
        reagentlot = ReagentLot.query(reagent=name, lot=lot, limit=1)
        if not reagentlot:
            logger.warning(f"Could not find reagentlot {name} to update.")
            return
        # else:
        reagentlot = reagentlot.to_pydantic()
        # logger.debug(f"Found insertable: {reagentlot}")
        insertable = PydProcedureReagentLotAssociation(reagentlot=reagentlot, procedure=self, reagentrole=reagentrole)
        if checked:
            self.reagentlot.insert(idx, insertable)
        # logger.info(f"Updated reagentlot to: {[item.name for item in self.reagentlot]}")

    def update_equipment(self, equipmentrole: str, equipment: str, processversion: str, tips: str, checked: bool=True):
        from backend.db.models import Equipment, ProcessVersion, TipsLot
        equipment_of_interest: PydProcedureEquipmentAssociation = next(
                (item for item in self.equipment if item.equipmentrole == equipmentrole), None)
        equipment = Equipment.query(name=equipment)
        if equipment_of_interest:
            eoi = self.equipment.pop(self.equipment.index(equipment_of_interest))
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
        # logger.info(f"Updated equipment to {self.equipment}")

    @classmethod
    def update_new_reagents(cls, reagent: PydReagent):
        reg = reagent.to_sql()
        reg.save()

    def to_sql(self, update: bool = True):
        from backend.db.models import Procedure
        self.sql_instance: Procedure = super().to_sql(update=update)
        if not update:
            return self.sql_instance, None
        logger.debug(f"Coming into sql: {pformat(self.improved_dict['sample'])}")
        self.sql_instance.proceduretype = self.proceduretype
        self.sql_instance.run = self.run
        self.sql_instance.repeat_of = self.repeat_of
        self.sql_instance.reagentlot = self.reagentlot
        # Convert pyd samples to SQL Sample instances before assigning.
        # Use update=True only when the sample_id does not already exist in DB;
        # otherwise use update=False to avoid unnecessary writes.
        samples_sql = []
        from backend.db.models import Sample as SQLSample, ProcedureSampleAssociation
        for sample in self.sample:
            row, column = self.proceduretype.ranked_plate[sample.rank]
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
            # Fallback: try to call to_sql on unknown types
            # try:
            #     result = sample.to_sql(update=False)
            #     if isinstance(result, tuple):
            #         sql_sample = result[0]
            #     else:
            #         sql_sample = result
            #     # if isinstance(sql_sample, SQLSample):
            #     #     logger.debug(f"Adding Assoc: {sql_sample}, {self.sql_instance}, rank {sample.rank}")
            #     #     samples_sql.append(ProcedureSampleAssociation(sample=sql_sample, procedure=self.sql_instance, rank=sample.rank))
            # except Exception as e:
            #     logger.error(f"Could not create sql_sample for {sample} due to {e}")
            #     continue
            # # if isinstance(sql_sample, SQLSample):
            # logger.debug(f"Adding Assoc: {sql_sample}, {self.sql_instance}, rank {sample.rank}")
            # samples_sql.append(ProcedureSampleAssociation(sample=sql_sample, procedure=self.sql_instance, rank=sample.rank))
        self.sql_instance.sample = samples_sql
        self.sql_instance.equipment = self.equipment
        # NOTE: At this point, results will likely be an empty list.
        self.sql_instance.results = self.results
        # logger.debug(f"Coming out of sql: {pformat(self.sql_instance.__dict__)}")
        return self.sql_instance, None
    
    def check_reagent_expiries(self, exempt: List[str] = []) -> Report:
        """
        Determines which reagents in a run are expired. Should be moved to Procedure.

        Args:
            exempt (List[PydReagent]): List of reagents that won't be checked.

        Returns:
            Report: A Report instance.
        """
        from backend.db.models import Reagent, ProcedureReagentLotAssociation
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
        output['excluded'] = ["excluded", "results", "sample_results", "reagentlot", "proceduresampleassociation", "procedurereagentlotassociation", "reagent",
                              "procedureequipmentassociation", "platemap", "sample", "result", "equipment"]
        if isinstance(output['proceduretype'], PydProcedureType):
            output['proceduretype'] = output['proceduretype'].name
        if isinstance(output['run'], PydRun):
            output['run'] = output['run'].name
        output['platemap'] = self.make_procedure_platemap()
        
        return output

    def reorder_proceduretype_by_procedure(self):
        proceduretype_dict = self.proceduretype.improved_dict_expand_fields([
            {
                "reagentrole":[
                        {"reagent":["reagentlot"]}]
                        
            }, 
            {
                "equipmentrole": [
                        {"equipmentroleequipmentassociation":["equipment", "process"]}]
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
        regex = re.compile(r".*R\d$")
        # proceduretype_dict['previous'] = [""] + [item.name for item in self.run.procedure if item.proceduretype.name == self.proceduretype.name and not bool(regex.match(item.name))]
        proceduretype_dict['previous'] = [""] + [
            item.name for item in self.run.sql_instance.procedure if 
            item.proceduretype.name == self.proceduretype.sql_instance.name 
            and not bool(regex.match(item.name))
        ]
        proceduretype_dict['platemap'] = procedure_dict['platemap']
        return proceduretype_dict
    
    def make_procedure_platemap(self):
        from backend.validators.pydant import PydProcedureType
        #proceduretype: PydProcedureType = self.proceduretype.to_pydantic()
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

    key_value_order: ClassVar = ["submitter_plate_id",
                       "submitted_date",
                       "clientlab",
                       "contact",
                       "contact_email",
                       "cost_centre",
                       "submissiontype",
                       "sample_count",
                       "submission_category"]

    filepath: Path | None = Field(default=None)
    submissiontype: dict | None
    submitted_date: dict | None = Field(default=dict(value=date.today(), missing=True), validate_default=True)
    clientlab: dict | None
    sample_count: dict | None = Field(default=dict(value=0, missing=True), validate_default=True)
    full_batch_size: int | dict = Field(default=0)
    submission_category: dict | None = Field(default=dict(value=None, missing=True), validate_default=True)
    comment: dict | None = Field(default=dict(value="", missing=True), validate_default=True)
    cost_centre: dict | None = Field(default=dict(value=None, missing=True), validate_default=True)
    contact: dict | None = Field(default=dict(value=None, missing=True), validate_default=True)
    submitter_plate_id: dict | None = Field(default=dict(value=None, missing=True), validate_default=True)
    sample: List[str] | List[PydSample] | None = Field(default=[])

    @field_validator("submissiontype", "clientlab", "contact", mode="before")
    @classmethod
    def enforce_value(cls, value):
        if isinstance(value, str):
            value = dict(value=value, missing=False)
        return value

    @field_validator("submitted_date", mode="before")
    @classmethod
    def enforce_submitted_date(cls, value):
        match value:
            case str():
                value = dict(value=datetime.strptime(value, "%Y-%m-%d %H:%M:%S").date(), missing=False)
            case datetime():
                value = dict(value=value, missing=False)
            case date():
                value = dict(value=datetime.combine(value, datetime.min.time()), missing=False)
            case _:
                pass
        return value

    @field_validator("submitter_plate_id", mode="before")
    @classmethod
    def enforce_submitter_plate_id(cls, value):
        if isinstance(value, str):
            value = dict(value=value, missing=False)
        return value

    @field_validator("submission_category", mode="before")
    @classmethod
    def enforce_submission_category_id(cls, value):
        if isinstance(value, str):
            value = dict(value=value, missing=False)
        return value

    @field_validator("sample_count", mode="before")
    @classmethod
    def enforce_sample_count(cls, value):
        if value is None:
            value = dict(value=0, missing=True)
        if isinstance(value, str) or isinstance(value, int):
            value = dict(value=value, missing=False)
        return value

    @field_validator("sample_count")
    @classmethod
    def enforce_integer(cls, value):
        if not value['value']:
            value['value'] = 0
        try:
            value['value'] = int(value['value'])
        except (ValueError, TypeError):
            raise TypeError(f"sample count value must be an integer")
        return value

    @field_validator("submitter_plate_id")
    @classmethod
    def create_submitter_plate_num(cls, value, values):
        if value['value'] in [None, "None"]:
            match values.data['submitted_date']['value']:
                case datetime():
                    submitted_date = values.data['submitted_date']['value'].strftime("%Y-%m-%d %H:%M:%S")
                case date():
                    submitted_date = datetime.combine(values.data['submitted_date']['value'], datetime.now().time()).strftime("%Y-%m-%d %H:%M:%S")
                case _:
                    submitted_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            val = f"{values.data['clientlab']['value']}-{values.data['submission_category']['value']}-{submitted_date}"
            return dict(value=val, missing=True)
        else:
            value['value'] = value['value'].strip()
            return value

    @field_validator("submitted_date")
    @classmethod
    def rescue_date(cls, value):
        if not value:
            value = dict(value=None)
        try:
            check = value['value'] is None
        except TypeError:
            check = True
        if check:
            value.update(dict(value=date.today(), missing=True))
        else:
            match value['value']:
                case str():
                    value['value'] = date.strptime(value['value'], "%Y-%m-%d")
                case _:
                    pass
        value['value'] = datetime.combine(value['value'], datetime.now().time())
        return value

    @field_validator("submission_category")
    @classmethod
    def enforce_typing(cls, value, values):
        if not value['value'] in ["Research", "Diagnostic", "Surveillance", "Validation"]:
            try:
                value['value'] = values.data['submissiontype']['value']
            except (AttributeError, KeyError):
                value['value'] = "NA"
        return value

    @field_validator("comment", mode="before")
    @classmethod
    def convert_comment_string(cls, value):
        if isinstance(value, str):
            value = dict(value=value, missing=True)
        return value

    @field_validator("full_batch_size")
    @classmethod
    def dict_to_int(cls, value):
        if isinstance(value, dict):
            value = value['value']
        value = int(value)
        return value

    @field_validator("cost_centre", mode="before")
    @classmethod
    def str_to_dict(cls, value):
        if isinstance(value, str):
            value = dict(value=value)
        return value

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

    def to_sql(self, update: bool = True):
        from backend.db.models import ClientSubmission
        self.sql_instance: ClientSubmission = super().to_sql(update)

        # Ensure clientlab and contact relationships are applied to the SQL
        # instance. SQL model setters (ClientSubmission.clientlab/contact)
        # accept strings, dicts or pyd models. Incoming pyd fields may be of
        # the shape {'value': 'Name', 'missing': False} - convert those to
        # {'name': 'Name'} so the SQL setters can resolve them correctly.
        try:
            cl = self.clientlab
            if isinstance(cl, dict) and 'value' in cl:
                cl = {'name': cl['value']}
            self.sql_instance.clientlab = cl
        except Exception:
            logger.debug(f"No clientlab to set for {self}")

        try:
            ct = self.contact
            if isinstance(ct, dict) and 'value' in ct:
                ct = {'name': ct['value']}
            self.sql_instance.contact = ct
        except Exception:
            logger.error(f"No contact to set for {self}")
        
        try:
            st = self.submissiontype
            if isinstance(st, dict) and 'value' in st:
                st = {'name': st['value']}
            self.sql_instance.submissiontype = st
        except Exception:
            logger.error(f"No contact to set for {self}")
        
        self.sql_instance.sample = self.sample
        return self.sql_instance, None
    
    @property
    def max_sample_rank(self) -> int:
        output: int = self.full_batch_size
        if output > 0:
            return output
        else:
            return max([item.submission_rank for item in self.sample])

    @property
    def improved_dict(self) -> dict:
        output = super().improved_dict
        output['run'] = [item.to_pydantic().improved_dict for item in self.sql_instance.run]
        # output['sample'] = self.sample
        output['clientlab'] = output['clientlab']
        try:
            output['contact_email'] = output['contact']['email']
        except TypeError:
            pass
        return sort_dict_by_list(output, self.key_value_order)

    @property
    def filename_template(self):
        # try:
        #     submissiontype = SubmissionType.query(name=self.submissiontype['value'])
        # except KeyError as e:
        #     submissiontype = SubmissionType.query(name=self.submissiontype['name'])
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
        output = super().to_html(**details)
        return output


class PydRun(PydConcrete):  #, extra='allow'):

    clientsubmission: PydClientSubmission | str | None = Field(default=None, repr=False)
    rsl_plate_number: dict | None = Field(default=dict(value=None, missing=True), validate_default=True)
    started_date: dict | None = Field(default=dict(value=date.today(), missing=True), validate_default=True, repr=False)
    completed_date: dict | None = Field(default=dict(value=date.today(), missing=True), validate_default=True, repr=False)
    sample_count: dict | None
    comment: dict | None = Field(default=dict(value="", missing=True), validate_default=True, repr=False)
    sample: List[PydSample] | Generator = Field(default=[], repr=False)
    run_cost: float | dict = Field(default=dict(value=0.0, missing=True), repr=False)
    signed_by: str | dict = Field(default="", validate_default=True, repr=False)
    procedure: List[PydProcedure] | Generator = Field(default=[], repr=False)

    @field_validator("signed_by")
    @classmethod
    def rescue_signed_by(cls, value):
        if isinstance(value, str):
            value = dict(value=value, missing=True)
        return value

    @field_validator("run_cost")
    @classmethod
    def rescue_run_cost(cls, value):
        if isinstance(value, float):
            value = dict(value=value, missing=False)
        return value

    @field_validator("started_date", mode="before")
    @classmethod
    def rescue_start_date(cls, value):
        try:
            check = value['value'] is None
        except TypeError:
            check = True
        if check:
            return dict(value=date.today(), missing=True)
        return value

    @field_validator("completed_date", mode="before")
    @classmethod
    def rescue_completed_date(cls, value):
        try:
            check = value['value'] is None
        except TypeError:
            check = True
        if check:
            return dict(value=date.today(), missing=True)
        return value

    @field_validator("started_date")
    @classmethod
    def strip_started_datetime_string(cls, value):
        match value['value']:
            case datetime():
                output = value['value']
            case date():
                output = datetime.combine(value['value'], datetime.min.time())
            case int():
                output = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value['value'] - 2)
            case str():
                string = re.sub(r"(_|-)\d(R\d)?$", "", value['value'])
                try:
                    output = parse(string)
                    value['missing'] = True
                except ParserError as e:
                    logger.error(f"Problem parsing date: {e}")
                    try:
                        output = parse(string.replace("-", ""))
                        value['missing'] = True
                    except Exception as e:
                        logger.error(f"Problem with parse fallback: {e}")
                        return value
            case _:
                raise ValueError(f"Unmatched value {value['value']} for datetime")
        value['value'] = output.replace(tzinfo=timezone)
        return value

    @field_validator("completed_date")
    @classmethod
    def strip_completed_datetime_string(cls, value):
        match value['value']:
            case datetime():
                output = value['value']
            case date():
                output = datetime.combine(value['value'], datetime.min.time())
            case int():
                output = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value['value'] - 2)
            case str():
                string = re.sub(r"(_|-)\d(R\d)?$", "", value['value'])
                try:
                    output = dict(value=parse(string).date(), missing=True)
                except ParserError as e:
                    logger.error(f"Problem parsing date: {e}")
                    try:
                        output = parse(string.replace("-", "")).date()
                    except Exception as e:
                        logger.error(f"Problem with parse fallback: {e}")
                        return value
            case _:
                raise ValueError(f"Could not get datetime from {value['value']}")
        value['value'] = output.replace(tzinfo=timezone)
        return value

    @field_validator("rsl_plate_number", mode='before')
    @classmethod
    def rescue_rsl_number(cls, value):
        if value is None:
            return dict(value=None, missing=True)
        return value

    @field_validator("rsl_plate_number")
    @classmethod
    def rsl_from_file(cls, value, values):
        sub_type = values.data.get('clientsubmission', None)
        try:
            assert sub_type is not None
        except AssertionError:
            raise KeyError(f"'clientsubmission' not found in {pformat(values.data)}")
        if check_not_nan(value['value']):
            value['value'] = value['value'].strip()
            return value
        else:
            output = RSLNamer(filename=sub_type.filepath.__str__(), submission_type=sub_type.submissiontype,
                                  data=values.data).parsed_name
            return dict(value=output, missing=True)

    @field_validator("sample_count", mode='before')
    @classmethod
    def rescue_sample_count(cls, value):
        if value is None:
            return dict(value=None, missing=True)
        return value

    @field_validator("sample", mode="before")
    @classmethod
    def expand_samples(cls, value):
        if isinstance(value, Generator):
            return [PydSample(**sample) for sample in value]
        return value

    def __init__(self, **data):
        super().__init__(**data)
        # NOTE: this could also be done with default_factory
        # from backend.db.models import ClientSubmission
        clientsub = self.sql_instance.clientsubmission
        try:
            submission_type = clientsub.submissiontype
        except AttributeError:
            submission_type = "Default SubmissionType"
        self.namer = RSLNamer(submission_type=submission_type)

    def to_sql(self, update: bool = True):
        from backend.db.models import Run
        self.sql_instance: Run = super().to_sql(update=update)
        if not update:
            return self.sql_instance, None
        logger.debug(f"Coming into sql: {pformat(self.__dict__)}")
        self.sql_instance.clientsubmission = self.clientsubmission
        self.sql_instance.procedure = self.procedure
        self.sql_instance.sample = [sample for sample in self.sample if PydSample.is_sample_id_valid(sample)]
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
            template = "{{rsl_plate_number}}{% if _clientsubmission %}_{{_clientsubmission.submitter_plate_id}}{% endif %}_{{_completed_date}}"
        render = self.namer.construct_export_name(template=template, **self.improved_dict).replace(
            "/", "")
        return render

    @property
    def improved_dict(self) -> dict:
        output = super().improved_dict
        output['procedure'] = [item.to_pydantic().improved_dict for item in self.sql_instance.procedure]
        output['excluded'] = ["excluded", "sample", "procedure", "runsampleassociation", "permission", "namer", "filepath"]
        return output

    def to_html(self, **kwargs):
        details = self.improved_dict_expand_fields(fields=['procedure', 'sample'])
        logger.debug(f"Run details:\n{pformat(details['procedure'])}")
        output = super().to_html(**details)
        return output


class PydTipsLot(PydConcrete):
    
    lot: str = Field(default="NA", description="Lot number of the tips")
    expiry: datetime = Field(default_factory=lambda: datetime.now() + timedelta(365), description="Expiry date of the tips", validate_default=True)
    active: bool = Field(default=True, description="Is this tips lot active?", validate_default=True)
    tips: str = Field(default="NA", description="The Tips this lot belongs to.", repr=True)

    @field_validator("tips", mode="before")
    @classmethod
    def make_default_tips(cls, value):
        if value is None:
            value = ""
        return value

    @field_validator("expiry")
    @classmethod
    def parse_expiry(cls, value):
        if not value:
            value = date.today()
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
    
    @field_validator("active", mode="before")
    @classmethod
    def int_to_bool(cls, value):
        if isinstance(value, int):
            value = bool(value)
        return value

    def to_sql(self, update: bool = True):
        from backend.db.models import TipsLot
        self.sql_instance: TipsLot = super().to_sql(update=update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.tips = self.tips
        return self.sql_instance, None


class PydProcedureSampleAssociation(PydConcrete):

    row: int = Field(default=0)
    column: int = Field(default=0)
    procedure_rank: int = Field(default=0)  #: Location in sample list
    procedure: str | PydProcedure = Field(default="NA")
    sample: str | PydSample = Field(default="NA")
    results: List[dict] | List[PydResults] = Field(default_factory=list, repr=False)
    enabled: bool = Field(default=True)

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

    def to_sql(self, update: bool = True):
        from backend.db.models import ProcedureSampleAssociation
        self.sql_instance: ProcedureSampleAssociation = super().to_sql(update=update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.procedure = self.procedure
        self.sql_instance.sample = self.sample
        self.sql_instance.results = self.results
        return self.sql_instance, None


class PydProcedureEquipmentAssociation(PydConcrete):

    start_time: datetime = Field(default_factory=datetime.now, description="Start time of equipment use", validate_default=True)
    end_time: datetime = Field(default_factory=datetime.now, description="End time of equipment use", validate_default=True)
    procedure: str | dict | PydProcedure = Field(default="NA")
    equipment: str | dict | PydEquipment = Field(default="NA")
    equipmentrole: str | dict | PydEquipmentRole = Field(default="NA")
    processversion: str | dict | PydProcessVersion | None = Field(default=None)
    tipslot: List[str] | List[dict] | List[PydTipsLot] = Field(default_factory=list)

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def set_starttime(cls, value):
        if not value:
            value = datetime.now()
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

    def to_sql(self, update: bool = True):
        from backend.db.models import ProcedureEquipmentAssociation
        self.sql_instance: ProcedureEquipmentAssociation = super().to_sql(update=update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.equipment = self.equipment
        self.sql_instance.equipmentrole = self.equipmentrole
        self.sql_instance.processversion = self.processversion
        self.sql_instance.tipslot = self.tipslot
        return self.sql_instance, None


class PydProcedureReagentLotAssociation(PydConcrete):

    procedure: str | dict | PydProcedure = Field(default="NA")
    reagentlot: str | dict | PydReagentLot = Field(default="NA")
    reagentrole: str | dict | PydReagentRole = Field(default="NA", repr=False)
    
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

    def to_sql(self, update: bool = True):
        from backend.db.models import ProcedureReagentLotAssociation
        self.sql_instance: ProcedureReagentLotAssociation = super().to_sql(update=update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.procedure = self.procedure
        self.sql_instance.reagentlot = self.reagentlot
        self.sql_instance.reagentrole = self.reagentrole
        return self.sql_instance, None
        # NOTE: Handle repeat naming.
        

class PydClientSubmissionSampleAssociation(PydConcrete):

    row: int = Field(default=0)
    column: int = Field(default=0)
    submission_rank: int = Field(default=0)  #: Location in sample list
    clientsubmission: str | dict | PydClientSubmission = Field(default="NA")
    sample: str | dict | PydSample = Field(default="NA")

    def to_sql(self, update: bool = True):
        from backend.db.models import ClientSubmissionSampleAssociation
        self.sql_instance: ClientSubmissionSampleAssociation = super().to_sql(update=update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.clientsubmission = self.clientsubmission
        self.sql_instance.sample = self.sample
        return self.sql_instance, None
    