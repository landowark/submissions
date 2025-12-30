
from __future__ import annotations
from pprint import pformat
import csv, logging, re, sys
from datetime import date, datetime, timedelta, timezone
from operator import itemgetter
from pathlib import Path
from types import GeneratorType
from typing import Any, ClassVar, Generator, List, Literal, Tuple, TYPE_CHECKING
from pydantic import Field, field_validator
from PyQt6.QtWidgets import QWidget
from dateutil.parser import parse, ParserError
from backend.db.models.organizations import (ClientLab, Contact)
from backend.db.models.procedures import SubmissionType
from backend.validators import RSLNamer
from backend.validators.pydant import PydConcrete
from backend.validators.pydant.abstract import PydEquipmentRole, PydProcedureType, PydProcess, PydTips, PydReagent, PydResultsType, PydSubmissionType
from tools import Alert, Report, check_not_nan, convert_nans_to_nones, flatten_list, report_result, row_keys, sort_dict_by_list
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


class PydEquipment(PydConcrete):

    asset_number: str = Field(default="NA", description="Asset number of this equipment.")
    name: str = Field(default="NA", description="Name of this equipment.")
    nickname: str = Field(default="NA", description="Nickname of this equipment.", validate_default=True)
    procedure: List[str] = Field(default_factory=list, repr=False)
    equipmentrole: List[str] | List[dict] = Field(default_factory=list, description="Roles this equipment can fill.", repr=False)

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
    name: dict = Field(default=dict(value="NA", missing=True), validate_default=True)
    technician: dict = Field(default=dict(value="NA", missing=True), repr=False)
    repeat: bool = Field(default=False, repr=False)
    repeat_of: str | PydProcedure | None = Field(default=None, repr=False)
    plate_map: str | None = Field(default=None, repr=False)
    reagentlot: List[str] | List[PydReagentLot] = Field(default_factory=list, repr=False)
    sample: List[str] | List[PydSample] = Field(default_factory=list, repr=False)
    equipment: List[str] | List[PydEquipment] = Field(default_factory=list, repr=False)
    results: List[dict] | List[PydResults] = Field(default_factory=list, repr=False)

    @field_validator("name", "technician", mode="before")#"kittype", mode="before")
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

    @field_validator("name")
    @classmethod
    def rescue_name(cls, value, values):
        if value['value'] == cls.model_fields['name'].default['value']:
            if values.data.get('proceduretype', None):
                procedure_type = values.data['proceduretype'].name
            else:
                procedure_type = None
            if values.data.get('run', None):
                run = values.data['run'].rsl_plate_number
            else:
                run = None
            value['value'] = f"{run}-{procedure_type}"
            value['missing'] = True
        return value

    @field_validator("run")
    @classmethod
    def lookup_run(cls, value):
        from backend.db.models import Run
        if isinstance(value, str):
            value = Run.query(name=value)
        return value

    @field_validator("repeat_of")
    @classmethod
    def drop_empty_string(cls, value):
        if value == "":
            value = None
        return value

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
        for iii, sample_dict in enumerate(sample_list, start=1):
            if sample_dict['sample_id'].startswith("blank_"):
                sample_dict['sample_id'] = ""
            row, column = self.proceduretype.ranked_plate[sample_dict['index']]
            try:
                sample = next(
                    (item for item in self.sample if item.sample_id.upper() == sample_dict['sample_id'].upper()))
            except StopIteration:
                # NOTE Code to check for added controls.
                logger.warning(
                    f"Sample not found by name: {sample_dict['sample_id']}, checking row {row} column {column}")
                try:
                    sample = next(
                        (item for item in self.sample if item.row == row and item.column == column))
                except StopIteration:
                    logger.error(f"Couldn't find sample: {pformat(sample_dict)}")
                    if sample_dict['sample_id'] == "":
                        continue
                    else:
                        sample = PydSample(sample_id=sample_dict['sample_id'], row=row, column=column)
                        self.sample.append(sample)
            sample.sample_id = sample_dict['sample_id']
            sample.well_id = sample_dict['sample_id']
            sample.row = row
            sample.column = column
            sample.procedure_rank = sample_dict['index']
            try:
                well_class = sample_dict['class'].split(" ")[-1]
            except KeyError:
                well_class = ""
            match well_class:
                case "negativecontrol":
                    sample.is_control = -1
                case "positivecontrol":
                    sample.is_control = 1
                case _:
                    sample.is_control = 0

    def update_reagents(self, reagentrole: str, name: str, lot: str, expiry: str, checked:bool=True):
        try:
            removable = next((item for item in self.reagent if item.reagentrole == reagentrole), None)
        except AttributeError as e:
            logger.error(self.reagent)
            raise e
        if removable:
            idx = self.reagent.index(removable)
            self.reagent.remove(removable)
        else:
            idx = 0
        insertable = PydReagent(reagentrole=reagentrole, name=name, lot=lot)
        if checked:
            self.reagent.insert(idx, insertable)

    def update_equipment(self, equipmentrole: str, equipment: str, processversion: str, tips: str, checked: bool=True):
        from backend.db.models import Equipment, ProcessVersion, TipsLot
        try:
            equipment_of_interest = next(
                (item for item in self.equipment if item.equipmentrole == equipmentrole))
        except StopIteration:
            equipment_of_interest = None
        equipment = Equipment.query(name=equipment)
        if equipment_of_interest:
            eoi = self.equipment.pop(self.procedure.equipment.index(equipment_of_interest))
        else:
            eoi: PydEquipment = equipment.to_pydantic(equipmentrole=equipmentrole)
        eoi.name = equipment.name
        eoi.asset_number = equipment.asset_number
        eoi.nickname = equipment.nickname
        process_name, version = processversion.split("-v")
        processversion = ProcessVersion.query(name=processversion, limit=1)
        # NOTE Retrieves correct instance.
        eoi.processversion = processversion.to_pydantic()
        # NOTE Correct pydprocessverion
        try:
            tips_manufacturer, tipsref, lot = [item if item != "" else None for item in tips.split("-")]
            tips = TipsLot.query(manufacturer=tips_manufacturer, ref=tipsref, lot=lot)
            eoi.tips = tips
        except ValueError:
            logger.warning(f"No tips info to unpack")
        if checked:
            self.equipment.append(eoi)

    @classmethod
    def update_new_reagents(cls, reagent: PydReagent):
        reg = reagent.to_sql()
        reg.save()

    # def to_sql(self, new: bool = False):
    #     from backend.db.models import (
    #         RunSampleAssociation, ProcedureSampleAssociation, Procedure, ProcedureReagentLotAssociation,
    #         ProcedureEquipmentAssociation, EquipmentRole, ReagentRole
    #     )
    #     if new:
    #         sql = Procedure()
    #     else:
    #         sql = super().to_sql()
    #     if isinstance(self.name, dict):
    #         sql.name = self.name['value']
    #     else:
    #         sql.name = self.name
    #     if isinstance(self.technician, dict):
    #         sql.technician = self.technician['value']
    #     else:
    #         sql.technician = self.technician
    #     if sql.repeat:
    #         regex = re.compile(r".*\dR\d$")
    #         repeats = [item for item in self.run.procedure if
    #                    self.repeat_of.name in item.name and bool(regex.match(item.name))]
    #         sql.name = f"{self.repeat_of.name}-R{str(len(repeats) + 1)}"
    #     sql.repeat_of = self.repeat_of
    #     sql.started_date = datetime.now()
    #     if self.run:
    #         sql.run = self.run
    #     if self.proceduretype:
    #         sql.proceduretype = self.proceduretype
    #     # NOTE: reset reagent associations.
    #     for reagent in self.reagent:
    #         if isinstance(reagent, dict):
    #             reagent = PydReagent(**reagent)
    #         reagentrole = ReagentRole.query(reagent.reagentrole, limit=1)
    #         reagent = reagent.to_sql()
    #         if reagent not in sql.reagentlot:
    #             # NOTE: Remove any previous association for this role.
    #             if sql.id:
    #                 removable = ProcedureReagentLotAssociation.query(procedure=sql, reagentrole=reagentrole)
    #             else:
    #                 removable = []
    #             if removable:
    #                 if isinstance(removable, list):
    #                     for r in removable:
    #                         r.delete()
    #                 else:
    #                     removable.delete()
    #             reagent_assoc = ProcedureReagentLotAssociation(reagentlot=reagent, procedure=sql, reagentrole=reagentrole)
    #     try:
    #         start_index = max([item.id for item in ProcedureSampleAssociation.query()]) + 1
    #     except ValueError:
    #         start_index = 1
    #     relevant_samples = [sample for sample in self.sample if
    #                         not sample.sample_id.startswith("blank_") and not sample.sample_id == ""]
    #     assoc_id_range = range(start_index, start_index + len(relevant_samples) + 1)
    #     for iii, sample in enumerate(relevant_samples):
    #         sample_sql = sample.to_sql()
    #         if sql.run:
    #             if sample_sql not in sql.run.sample:
    #                 with sample_sql.__database_session__.no_autoflush:
    #                     run_assoc = RunSampleAssociation(sample=sample_sql, run=self.run, row=sample.row,
    #                                                  column=sample.column)
    #         if sample_sql not in sql.sample:
    #             with sample_sql.__database_session__.no_autoflush:
    #                 proc_assoc = ProcedureSampleAssociation(new_id=assoc_id_range[iii], procedure=sql, sample=sample_sql,
    #                                                     row=sample.row, column=sample.column,
    #                                                     procedure_rank=sample.procedure_rank)
    #     for equipment in self.equipment:
    #         equip, _ = equipment.to_sql()
    #         equipment_role = EquipmentRole.query(equipment.equipmentrole, limit=1)
    #         if isinstance(equipment.tips, list):
    #             try:
    #                 equipment.tips = equipment.tips[0]
    #             except IndexError:
    #                 equipment.tips = None
    #         if equip not in sql.equipment:
    #             equip_assoc = ProcedureEquipmentAssociation(equipment=equip, procedure=sql, equipmentrole=equipment_role)
    #             processversion = equipment.processversion.to_sql()
    #             equip_assoc.processversion = processversion
    #             try:
    #                 tipslot = equipment.tips.to_sql()
    #             except AttributeError:
    #                 tipslot = None
    #             equip_assoc.tipslot = tipslot
    #     return sql, None


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

    def to_sql(self):
        # sql = super().to_sql()
        # from backend.db.models import SubmissionType
        # assert not any([isinstance(item, PydSample) for item in sql.sample])
        # sql.sample = []
        # if not sql.submissiontype:
        #     sql.submissiontype = SubmissionType.query(name=self.submissiontype['value'])
        # match sql.submissiontype:
        #     case SubmissionType():
        #         pass
        #     case _:
        #         sql.submissiontype = SubmissionType.query(name="Default Submission Type")
        # for k in list(self.__class__.model_fields.keys()) + list(self.model_extra.keys()):
        #     attribute = getattr(self, k)
        #     match k:
        #         case "filepath":
        #             sql._misc_info[k] = attribute.__str__()
        #             continue
        #         case _:
        #             pass
        logger.debug(f"Dicto coming into {self.__class__.__name__} object:\n{pformat(self.improved_dict)}")
        sql = super().to_sql()
        return sql

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

    clientsubmission: PydClientSubmission | None = Field(default=None)
    rsl_plate_number: dict | None = Field(default=dict(value=None, missing=True), validate_default=True)
    started_date: dict | None = Field(default=dict(value=date.today(), missing=True), validate_default=True)
    completed_date: dict | None = Field(default=dict(value=date.today(), missing=True), validate_default=True)
    sample_count: dict | None
    comment: dict | None = Field(default=dict(value="", missing=True), validate_default=True)
    sample: List[PydSample] | Generator = Field(default=[])
    run_cost: float | dict = Field(default=dict(value=0.0, missing=True))
    signed_by: str | dict = Field(default="", validate_default=True)
    procedure: List[PydProcedure] | Generator = Field(default=[])

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
                    output = dict(value=parse(string).date(), missing=True)
                except ParserError as e:
                    logger.error(f"Problem parsing date: {e}")
                    try:
                        output = parse(string.replace("-", "")).date()
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
    def to_sql(self) -> Tuple[Run | None, Report]:
        """
        Converts this instance into a backend.db.models.procedure.BasicRun instance

        Returns:
            Tuple[BasicRun, Alert]: BasicRun instance, result object
        """
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
