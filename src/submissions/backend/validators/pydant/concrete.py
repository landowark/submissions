
from __future__ import annotations
from pprint import pformat
import csv, logging, re, sys
from datetime import date, datetime, timedelta, timezone
from operator import itemgetter
from pathlib import Path
from types import GeneratorType
from typing import Any, ClassVar, Generator, List, Literal, Tuple, TYPE_CHECKING
from pydantic import Field, ValidationInfo, field_validator, model_validator
from PyQt6.QtWidgets import QWidget
from dateutil.parser import parse, ParserError
from backend.db.models.organizations import (ClientLab, Contact)
from backend.db.models.procedures import SubmissionType
from backend.validators import RSLNamer
from backend.validators.pydant import PydConcrete
from backend.validators.pydant.abstract import PydEquipmentRole, PydProcedureType, PydProcess, PydTips, PydReagent, PydResultsType, PydSubmissionType, PydReagentRole
from tools import Alert, Report, check_not_nan, convert_nans_to_nones, flatten_list, report_result, row_keys, sort_dict_by_list, timezone
if TYPE_CHECKING:
    from backend.db.models.submissions import Run

logger = logging.getLogger(f"submissions.{__name__}")


class PydResults(PydConcrete, arbitrary_types_allowed=True):

    result: dict = Field(default={}, repr=False)
    result_type: str | PydResultsType = Field(default="NA")
    image: None | bytes = Field(default=None, repr=False)
    procedure: str | PydProcedure | None = Field(default=None)#, description="Parent procedure this result is associated with.")
    sample: str | PydSample | None = Field(default=None)#, description="Parent sample this result is associated with.")
    date_analyzed: datetime | None = Field(default=None, repr=False, description="Date this result was analyzed.", validate_default=True)

    @field_validator("date_analyzed")
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
        sql, _ = Results.query_or_create(result_type=self.result_type, result=self.results)
        try:
            check = sql.image
        except FileNotFoundError:
            check = False
        if not check:
            sql.image = self.img
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
    expiry: datetime = Field(default = None, description="Expiry date of this reagent lot.", validate_default=True)
    missing: bool = Field(default=True, repr=False)
    active: bool = Field(default=True)

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
            return f"{reagent}-{self.lot}"
        except AttributeError:
            return f"{reagent}-{self.lot}"


class PydDiscount(PydConcrete):

    description: str = Field(default="NA", description="Brief description of this discount.")
    proceduretype: str | None = Field(default="NA", description="ProcedureType this discount applies to.", repr=False)
    clientlab: str | None = Field(default="NA", description="ClientLab this discount applies to.", repr=False)
    amount: float = Field(default=0.0, description="Amount (dollars) of discount to apply.")


class PydSample(PydConcrete):

    sample_id: str
    rank: int | List[int] | None = Field(default=0, validate_default=True)
    enabled: bool = Field(default=True, repr=False)
    row: int = Field(default=0, repr=False)
    column: int = Field(default=0, repr=False)
    results: List[PydResults] | PydResults = Field(default=[], repr=False)
    is_control: int = Field(default=0, repr=False)

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
        if isinstance(value, str):
            try:
                value = row_keys[value]
            except KeyError:
                value = 0
        return value

    @field_validator("column", mode="before")
    @classmethod
    def column_str_to_int(cls, value):
        if isinstance(value, str):
            value = 0
        return value

    @property
    def constructed_name(self):
        return self.sample_id
    
    @property
    def improved_dict(self) -> dict:
        output = super().improved_dict
        output['name'] = self.sample_id
        return output

    def to_sql(self):
        # logger.debug(f"Dict to sample sql: {pformat(self.improved_dict())}")
        sql = super().to_sql()
        sql._misc_info["rank"] = self.rank
        return sql

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
    procedure: List[str] = Field(default_factory=list, repr=False)
    equipmentrole: List[str] | List[dict] = Field(default_factory=list, description="Roles this equipment can fill.", repr=False)
    # equipmentrole: str | dict = Field(default="NA", description="Roles this equipment can fill.", repr=False)
    processversion: List[str] | List[dict] | None = Field(default_factory=list, repr=False)
    # processversion: str | dict | None = Field(default=None, repr=False)
    tipslot: List[str] | List[dict] | None = Field(default_factory=list, repr=False)

    @field_validator('nickname')
    @classmethod
    def set_nickname_to_name(cls, value, values):
        if not value or value == "NA":
            value = values.data['name']
        return value


class PydContact(PydConcrete):

    name: str = Field(default="NA", description="Name of this contact.")
    tel: str = Field(default="000-000-0000", description="Phone number of this contact.")
    email: str = Field(default="NA", description="Email address of this contact.")

    @field_validator("tel")
    @classmethod
    def enforce_phone_number(cls, value):
        area_regex = re.compile(r"^\(?(\d{3})\)?(-| )?")
        if len(value) > 8:
            match = area_regex.match(value)
            value = area_regex.sub(f"({match.group(1).strip()}) ", value)
        return value

    # @report_result
    # def to_sql(self) -> Tuple[Contact, Report]:
    #     """
    #     Converts this instance into a backend.db.models.organization. Contact instance.
    #     Does not query for existing contact.

    #     Returns:
    #         Contact: Contact instance
    #     """
    #     report = Report()
    #     instance = Contact.query(name=self.name, phone=self.phone, email=self.email)
    #     if not instance or isinstance(instance, list):
    #         instance = Contact()
    #     try:
    #         all_fields = self.model_fields + self.model_extra
    #     except TypeError:
    #         all_fields = self.model_fields
    #     for field in all_fields:
    #         value = getattr(self, field)
    #         match field:
    #             case "organization":
    #                 value = [ClientLab.query(name=value)]
    #             case _:
    #                 pass
    #         try:
    #             instance.__setattr__(field, value)
    #         except AttributeError as e:
    #             logger.error(f"Could not set {instance} {field} to {value} due to {e}")
    #     return instance, report


class PydClientLab(PydConcrete):

    name: str = Field(default="NA", description="Name of this Client Lab.")
    cost_centre: str = Field(default="NA", description="Default cost centre for this Client Lab.", repr=False)
    contact: List[str] = Field(default_factory=list, description="Contacts for this Client Lab.", repr=False)

    # @field_validator("contact", mode="before")
    # @classmethod
    # def string_to_list(cls, value):
    #     if isinstance(value, str):
    #         value = Contact.query(name=value)
    #         try:
    #             value = [value.to_pydantic()]
    #         except AttributeError:
    #             return None
    #     return value

    # @report_result
    # def to_sql(self) -> ClientLab:
        
        # Converts this instance into a backend.db.models.organization.Organization instance.

        # Returns:
        #    Organization: Organization instance
        # """
        # report = Report()
        # instance = ClientLab()
        # for field in self.model_fields:
        #     match field:
        #         case "contact":
        #             value = getattr(self, field)
        #             if value:
        #                 value = [item.to_sql() for item in value if item]
        #         case _:
        #             value = getattr(self, field)
        #     if value:
        #         setattr(instance, field, value)
        # return instance, report


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
        if isinstance(value, int):
            value = bool(value)
        return value
    
    @field_validator("active")
    @classmethod
    def enforce_active(cls, value):
        if value is None:
            value = True
        if isinstance(value, str):
            if value.lower() in ["false", "0", "no", "off"]:
                value = False
            else:
                value = True
        return value


    # @field_validator("name")
    # @classmethod
    # def split_name(cls, value):
    #     if "-" in value:
    #         value = value.split("-")[0]
    #     return value

    # def to_sql(self):
    #     from backend.db.models import ProcessVersion
    #     instance = ProcessVersion.query(name=self.name, version=self.version, limit=1)
    #     if not instance:
    #         logger.warning(f"PV: Gonna have to make a new process version {self.version}")
    #         instance = ProcessVersion()
    #     return instance


class PydProcedure(PydConcrete, arbitrary_types_allowed=True):
    
    proceduretype: str | PydProcedureType | None = Field(default=None)
    run: str | PydRun | None = Field(default=None)
    technician: dict = Field(default=dict(value="NA", missing=True), repr=False)
    repeat: bool = Field(default=False, repr=False)
    repeat_of: str | PydProcedure | None = Field(default=None, repr=False)
    name: dict = Field(default_factory=lambda: {"value": "NA", "missing": True}, validate_default=True)
    plate_map: str | None = Field(default=None, repr=False)
    reagentlot: List[str] | List[PydProcedureReagentLotAssociation] = Field(default_factory=list, repr=False)
    sample: List[str] | List[PydSample] = Field(default_factory=list, repr=False)
    equipment: List[str] | List[PydProcedureEquipmentAssociation] = Field(default_factory=list, repr=False)
    results: List[dict] | List[PydResults] = Field(default_factory=list, repr=False)

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
        if isinstance(value, str):
            value = Run.query(name=value)
            if value:
                value = value.to_pydantic()
        return value
    
    @field_validator("repeat_of")
    @classmethod
    def drop_empty_string(cls, value):
        if value == "":
            value = None
        return value
    
    # @field_validator("name", mode="after")
    # @classmethod
    # def validate_name_default(cls, value: Any, info: ValidationInfo) -> dict:
    #     # Check if we are using the default "NA" value
    #     print(info)
    #     sys.exit()
    #     if isinstance(value, dict) and value.get("value") == "NA":
    #         # Access other fields from info.data (populated in order of definition)
    #         run = info.data.get("run")
    #         proceduretype = info.data.get("proceduretype")
    #         repeat_of = info.data.get("repeat_of")
    #         # Format logic (adjusting for potential Pydantic objects)
    #         run_str = getattr(run, "rsl_plate_number", str(run)) if run else "Unassigned Run"
    #         pt_str = getattr(proceduretype, "name", str(proceduretype)) if proceduretype else "Unassigned ProcedureType"
    #         rep_str = f" ({getattr(repeat_of, 'name', str(repeat_of))})" if repeat_of else ""
            
    #         return {"value": f"{run_str}-{pt_str}{rep_str}", "missing": True}
        
    #     return value

    @model_validator(mode="after")
    def rescue_name(self) -> PydProcedure:
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

    # @model_validator(mode="after")
    # # @classmethod
    # def validate_model(self, data):

    #     if data.name == self.__class__.model_fields['name'].default['value'] or data.name.get('value') == "NA":
    #         proceduretype = data.proceduretype
    #         if proceduretype:
    #             if isinstance(proceduretype, PydProcedureType):
    #                 proceduretype = proceduretype.name
    #             elif isinstance(proceduretype, str):
    #                 pass
    #             else:
    #                 proceduretype = f"ProcedureType {type(proceduretype)}"
    #         else:
    #             proceduretype = "Unassigned ProcedureType"
    #         run = data.run
    #         if run:
    #             if isinstance(run, PydRun):
    #                 run = run.rsl_plate_number
    #             elif isinstance(run, str):
    #                 pass
    #             else:
    #                 run = f"Run {type(run)}"
    #         else:
    #             run = "Unassigned Run"
    #         repeat_of = data.repeat_of
    #         if repeat_of:
    #             if isinstance(repeat_of, PydProcedure):
    #                 repeat_of = f" ({repeat_of.name})"
    #             elif isinstance(run, str):
    #                 repeat_of = f" ({repeat_of})"
    #             else:
    #                 repeat_of = ""
    #         else:
    #             repeat_of = ""
    #         setattr(data, 'name', dict(value=f"{run}-{proceduretype}{repeat_of}", missing=True))
    #     return data


    @property
    def rows_columns_count(self) -> tuple[int, int]:
        from backend.db.models import Procedure
        try:
            proc: ProcedureType = Procedure.query(name=self.name).proceduretype
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

    def reorder_reagents(self, reagentrole: str, options: list):
        reagent_used = next((reagent for reagent in self.reagent if reagent.reagentrole == reagentrole), None)
        if not reagent_used:
            return options
        roi = next((item for item in options if item.lot == reagent_used.lot and item.name == reagent_used.name), None)
        if not roi:
            return options
        options.insert(0, options.pop(options.index(roi)))
        return options

    def update_samples(self, sample_list: List[dict]):
        from backend.db.models import Sample
        # Build a new ordered list of samples matching the sample_list order.
        new_samples: List[PydSample] = []
        for iii, sample_dict in enumerate(sample_list, start=1):
            sample_id = sample_dict.get('sample_id', '')
            # normalize blank markers
            if isinstance(sample_id, str) and sample_id.startswith("blank_"):
                sample_id = ""

            row, column = self.proceduretype.ranked_plate[sample_dict['index']]

            # try to find existing sample by id (case-insensitive)
            sample = None
            if sample_id:
                sample_sql = Sample.query(sample_id=sample_id, limit=1)
                sample = next((item for item in self.sample if (item.sample_id or "").upper() == sample_id.upper()), None)

            # fallback: match by row/column
            if not sample:
                sample = next((item for item in self.sample if item.row == row and item.column == column), None)

            # If still not found, and sample_id is empty, skip (was blank)
            if not sample and sample_id == "":
                continue

            # If still not found, create a new sample
            if not sample:
                
                sample = PydSample(sample_id=sample_id, row=row, column=column, sql_instance=sample_sql)
                # also add to original collection so future lookups can find it
                self.sample.append(sample)

            # Do NOT change the sample_id (we want to preserve the existing sample's identity).
            # Update position/rank/control/classification metadata.
            sample.row = row
            sample.column = column
            sample.procedure_rank = sample_dict.get('index', 0)
            sample.sql_instance = sample_sql
            try:
                well_class = sample_dict.get('class', '').split(" ")[-1]
            except IndexError:
                well_class = ""
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
        remaining = [s for s in self.sample if s not in new_samples]
        self.sample = new_samples + remaining

    def update_reagents(self, reagentrole: str, name: str, lot: str, expiry: str|None=None, checked:bool=True):
        from backend.db.models import ReagentLot
        logger.debug(self.reagentlot)
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
        logger.debug(f"Found insertable: {reagentlot}")
        insertable = PydProcedureReagentLotAssociation(reagentlot=reagentlot, procedure=self, reagentrole=reagentrole)
        if checked:
            self.reagentlot.insert(idx, insertable)
        logger.debug(f"Updated reagentlot to: {[item.name for item in self.reagentlot]}")

    def update_equipment(self, equipmentrole: str, equipment: str, processversion: str, tips: str, checked: bool=True):
        from backend.db.models import Equipment, ProcessVersion, TipsLot
        logger.debug(f"Searching for equipment role: {equipmentrole} in {pformat([item.improved_dict for item in self.equipment])}")
        try:
            equipment_of_interest: PydProcedureEquipmentAssociation = next(
                (item for item in self.equipment if item.equipmentrole == equipmentrole))
        except StopIteration:
            equipment_of_interest = None
        logger.debug(f"Got equipment of interest: {equipment_of_interest}")
        equipment = Equipment.query(name=equipment)
        if equipment_of_interest:
            eoi = self.equipment.pop(self.equipment.index(equipment_of_interest))
        else:
            eoi = PydProcedureEquipmentAssociation(equipment=equipment.to_pydantic(), equipmentrole=equipmentrole, procedure=self)
        # eoi.name = equipment.name
        # eoi.asset_number = equipment.asset_number
        # eoi.nickname = equipment.nickname
        # eoi.equipmentrole = equipmentrole
        process_name, version = processversion.split("-v")
        processversion = ProcessVersion.query(name=processversion, limit=1)
        # NOTE Retrieves correct instance.
        eoi.processversion = processversion.to_pydantic()
        # NOTE Correct pydprocessverion
        for tipslot in tips:
            try:
                tips_manufacturer, tipsref, lot = [item if item != "" else None for item in tipslot.split("-")]
                tips = TipsLot.query(manufacturer=tips_manufacturer, ref=tipsref, lot=lot)
                eoi.tips = tips.to_pydantic()
            except ValueError:
                logger.warning(f"No tips info to unpack")
        if checked:
            self.equipment.append(eoi)

    @classmethod
    def update_new_reagents(cls, reagent: PydReagent):
        reg = reagent.to_sql()
        reg.save()

    def to_sql(self, update: bool = True):
        self.sql_instance = super().to_sql(update=update)
        if not update:
            return self.sql_instance, None
        # from backend.db.models import Sample, Equipment, Results, ReagentLot, Run
        # logger.debug(f"PydProcedure.proceduretype = {self.proceduretype}")
        logger.debug(f"Coming into sql: {pformat(self.__dict__)}")
        self.sql_instance.proceduretype = self.proceduretype
        self.sql_instance.run = self.run
        self.sql_instance.repeat_of = self.repeat_of
        self.sql_instance.reagentlot = self.reagentlot
        self.sql_instance.sample = self.sample
        self.sql_instance.equipment = self.equipment
        # NOTE: At this point, results will likely be an empty list.
        self.sql_instance.results = self.results
        return self.sql_instance, None
 

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
    sample_count: dict | None
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
            raise f"sample count value must be an integer"
        return value

    @field_validator("submitter_plate_id")
    @classmethod
    def create_submitter_plate_num(cls, value, values):
        if value['value'] in [None, "None"]:
            val = f"{values.data['submissiontype']['value']}-{values.data['submission_category']['value']}-{values.data['submitted_date']['value']}"
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
        return ClientSubmissionFormWidget(parent=parent, clientsubmission=self, samples=samples, disable=disable)

    # def to_sql(self):
        
    #     return sql, None

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
        output['sample'] = self.sample
        output['clientlab'] = output['clientlab']
        try:
            output['contact_email'] = output['contact']['email']
        except TypeError:
            pass
        return sort_dict_by_list(output, self.key_value_order)
        # return output

    @property
    def filename_template(self):
        try:
            submissiontype = SubmissionType.query(name=self.submissiontype['value'])
        except KeyError as e:
            submissiontype = SubmissionType.query(name=self.submissiontype['name'])
        return submissiontype.defaults['filename_template']


class PydRun(PydConcrete):  #, extra='allow'):

    clientsubmission: PydClientSubmission | None = Field(default=None, repr=False)
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
        sub_type = values.data['clientsubmission']
        if check_not_nan(value['value']):
            value['value'] = value['value'].strip()
            return value
        else:
            if "pytest" in sys.modules and sub_type.replace(" ", "") == "BasicRun":
                output = "RSL-BS-Test001"
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

    def __init__(self, run_custom: bool = False, **data):
        super().__init__(**data)
        # NOTE: this could also be done with default_factory
        submission_type = self.clientsubmission.submissiontype
        self.namer = RSLNamer(self.rsl_plate_number['value'], submission_type=submission_type)

    def set_attribute(self, key: str, value):
        """
        Better handling of attribute setting.

        Args:
            key (str): Name of field to set
            value (_type_): Value to set field to.
        """
        self.__setattr__(name=key, value=value)

    def handle_duplicate_samples(self):
        """
        Collapses multiple sample with same submitter id into one with lists for rows, columns.
        Necessary to prevent trying to create duplicate sample in SQL creation.
        """
        submitter_ids = list(set([sample.sample_id for sample in self.samples]))
        output = []
        for id in submitter_ids:
            relevants = [item for item in self.samples if item.sample_id == id]
            if len(relevants) <= 1:
                output += relevants
            else:
                rows = [item.row[0] for item in relevants]
                columns = [item.column[0] for item in relevants]
                ids = [item.assoc_id[0] for item in relevants]
                ranks = [item.submission_rank[0] for item in relevants]
                dummy = relevants[0]
                dummy.assoc_id = ids
                dummy.row = rows
                dummy.column = columns
                dummy.submission_rank = ranks
                output.append(dummy)
        self.samples = output

    def filter_field(self, key: str) -> Any:
        """
        Attempts to get value from field dictionary

        Args:
            key (str): name of the field of interest

        Returns:
            Any (): Value found.
        """
        item = getattr(self, key)
        match item:
            case dict():
                try:
                    item = item['value']
                except KeyError:
                    logger.error(f"Couldn't get dict value: {item}")
            case _:
                pass
        return item

    def find_missing(self) -> Tuple[dict, dict]:
        """
        Retrieves info and reagents marked as missing.

        Returns:
            Tuple[dict, dict]: Dict for missing info, dict for missing reagents.
        """
        info = {k: v for k, v in self.improved_dict.items() if isinstance(v, dict)}
        missing_info = {k: v for k, v in info.items() if v['missing']}
        missing_reagents = [reagent for reagent in self.reagents if reagent.missing]
        return missing_info, missing_reagents

    @report_result
    def to_sql(self, update: bool = True) -> Tuple[Run | None, Report]:
        """
        Converts this instance into a backend.db.models.procedure.BasicRun instance

        Returns:
            Tuple[BasicRun, Alert]: BasicRun instance, result object
        """
        if not update:
            return self.sql_instance, None
        from backend.db.models import Run
        report = Report()
        # dicto = self.improved_dict()
        instance, result = Run.query_or_create(submissiontype=self.submission_type['value'],
                                               rsl_plate_number=self.rsl_plate_number['value'])
        if instance is None:
            report.add_result(Alert(msg="Overwrite Cancelled."))
            return None, report
        report.add_result(result)
        self.handle_duplicate_samples()
        for key, value in self.improved_dict.items():
            if isinstance(value, dict):
                try:
                    value = value['value']
                except KeyError:
                    if key == "custom":
                        pass
                    else:
                        continue
            if value is None:
                continue
            match key:
                case "reagents":
                    for reagent in self.reagents:
                        reagent = reagent.to_sql(submission=instance)
                case "sample":
                    for sample in self.samples:
                        sample, associations, _ = sample.to_sql(run=instance)
                        for assoc in associations:
                            if assoc is not None:
                                if assoc not in instance.clientsubmissionsampleassociation:
                                    instance.clientsubmissionsampleassociation.append(assoc)
                                else:
                                    logger.warning(f"Sample association {assoc} is already present in {instance}")
                case "equipment":
                    for equip in self.equipment:
                        if equip is None:
                            continue
                        equip, association = equip.to_sql(procedure=instance, kittype=self.extraction_kit)
                        if association is not None:
                            instance.submission_equipment_associations.append(association)
                case "tips":
                    for tips in self.tips:
                        if tips is None:
                            continue
                        try:
                            association = tips.to_sql(procedure=instance)
                        except AttributeError:
                            continue
                        if association is not None:
                            if association not in instance.submission_tips_associations:
                                instance.submission_tips_associations.append(association)
                            else:
                                logger.warning(f"Tips association {association} is already present in {instance}")
                case item if item in instance.timestamps:
                    logger.warning(f"Incoming timestamp key: {item}, with value: {value}")
                    if isinstance(value, date):
                        value = datetime.combine(value, datetime.now().time())
                        value = value.replace(tzinfo=timezone)
                    elif isinstance(value, str):
                        value: datetime = datetime.strptime(value, "%Y-%m-%d")
                        value = value.replace(tzinfo=timezone)
                    else:
                        value = value
                    instance.set_attribute(key=key, value=value)
                case item if item in instance.jsons:
                    try:
                        ii = value.items()
                    except AttributeError:
                        ii = {}
                    for k, v in ii:
                        if isinstance(v, datetime):
                            value[k] = v.strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            pass
                    instance.set_attribute(key=key, value=value)
                case _:
                    try:
                        check = instance.__getattribute__(key) != value
                    except AttributeError:
                        continue
                    if check:
                        try:
                            instance.set_attribute(key=key, value=value)
                        except AttributeError as e:
                            logger.error(f"Could not set attribute: {key} to {value} due to: \n\n {e}")
                            continue
                        except KeyError:
                            continue
                    else:
                        logger.warning(f"{key} already == {value} so no updating.")
        try:
            instance.calculate_base_cost()
        except (TypeError, AttributeError) as e:
            logger.error(f"Looks like that kittype doesn't have cost breakdown yet due to: {e}, using 0.")
            try:
                instance.run_cost = instance.extraction_kit.cost_per_run
            except AttributeError:
                instance.run_cost = 0
        # NOTE: Apply any discounts that are applicable for client and kittype.
        try:
            discounts = [item.amount for item in
                         Discount.query(kittype=instance.extraction_kit, organization=instance.clientlab)]
            if len(discounts) > 0:
                instance.run_cost = instance.run_cost - sum(discounts)
        except Exception as e:
            logger.error(f"An unknown exception occurred when calculating discounts: {e}")
        return instance, report

    def to_form(self, parent: QWidget, disable: list | None = None):
        """
        Converts this instance into a frontend.widgets.submission_widget.SubmissionFormWidget

        Args:
            disable (list, optional): a list of widgets to be disabled in the form. Defaults to None.
            parent (QWidget): parent widget of the constructed object

        Returns:
            SubmissionFormWidget: Submission form widget
        """
        from frontend.widgets.submission_widget import SubmissionFormWidget
        return SubmissionFormWidget(parent=parent, pyd=self, disable=disable)

    def construct_filename(self) -> str:
        """
        Creates filename for this instance

        Returns:
            str: Output filename
        """
        try:
            template = self.clientsubmission.filename_template
        except KeyError as e:
            template = "{{ rsl_plate_number }} - {{ clientsubmission.clientlab.name }} - {{ clientsubmission.submitter_plate_id['value'] }}"
        render = self.namer.construct_export_name(template=template, **self.improved_dict(dictionaries=False)).replace(
            "/", "")
        return render

    def check_reagent_expiries(self, exempt: List[PydReagent] = []):
        report = Report()
        expired = []
        for reagent in self.reagents:
            if reagent not in exempt:
                role_eol = ReagentRole.query(name=reagent.role).eol_ext
                try:
                    dt = datetime.combine(reagent.expiry, datetime.max.time())
                except TypeError:
                    continue
                if datetime.now() > dt + role_eol:
                    expired.append(f"{reagent.role}, {reagent.lot}: {reagent.expiry.date()} + {role_eol.days}")
        if expired:
            output = '\n'.join(expired)
            result = Alert(status="Warning",
                            msg=f"The following reagents are expired:\n\n{output}"
                            )
            report.add_result(result)
        return report

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

    @property
    def sample_list(self) -> List[dict]:
        samples = []
        for sample in self.samples:
            sample = sample.improved_dict
            sample['row'] = sample['row'][0]
            sample['column'] = sample['column'][0]
            sample['submission_rank'] = sample['submission_rank'][0]
            samples.append(sample)
        samples = sorted(samples, key=itemgetter("submission_rank"))
        return samples


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


class PydProcedureEquipmentAssociation(PydConcrete):

    start_time: datetime = Field(default_factory=datetime.now, description="Start time of equipment use", validate_default=True)
    end_time: datetime = Field(default_factory=datetime.now, description="End time of equipment use", validate_default=True)
    procedure: str | dict | PydProcedure = Field(default="NA")
    equipment: str | dict | PydEquipment = Field(default="NA")
    equipmentrole: str | dict | PydEquipmentRole = Field(default="NA")
    processversion: str | dict | PydProcessVersion | None = Field(default=None)
    tipslot: List[str] | List[dict] | List[PydTipsLot] = Field(default_factory=list)

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
        self.sql_instance = super().to_sql(update=update)
        if not update:
            return self.sql_instance, None
        # sql.procedure = self.procedure
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
        self.sql_instance = super().to_sql(update=update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.procedure = self.procedure
        self.sql_instance.reagentlot = self.reagentlot
        self.sql_instance.reagentrole = self.reagentrole
        return self.sql_instance, None
        # NOTE: Handle repeat naming.
        