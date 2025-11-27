"""
Contains pydantic models and accompanying validators
"""
from __future__ import annotations
import re, logging, csv, sys, string
from operator import itemgetter
from pprint import pformat
from pydantic import BaseModel, field_validator, Field, model_validator
from datetime import date, datetime, timedelta
from dateutil.parser import parse
from dateutil.parser import ParserError
from typing import List, Tuple, Literal, Generator, TYPE_CHECKING
from types import GeneratorType
from . import RSLNamer
from pathlib import Path
from tools import check_not_nan, convert_nans_to_nones, Report, Alert, timezone, sort_dict_by_list, row_keys, flatten_list
from backend.db import models
from backend.db.models import *
from sqlalchemy.orm.properties import ColumnProperty
from sqlalchemy.orm.relationships import _RelationshipDeclared
from sqlalchemy.orm.attributes import InstrumentedAttribute
from PyQt6.QtWidgets import QWidget
if TYPE_CHECKING:
    from frontend import RoleComboBox


logger = logging.getLogger(f"submission.{__name__}")


class PydBaseClass(BaseModel, extra='allow'):#, validate_assignment=True):

    # _sql_object: ClassVar = None
    key_value_order: ClassVar = []

    @classproperty
    def _sql_name(cls) -> str:
        return cls.__name__.replace("Pyd", "")

    @classproperty
    def _sql_object(cls):
        return getattr(models, cls._sql_name)

    @model_validator(mode="before")
    @classmethod
    def prevalidate(cls, data):
        sql_fields = [k for k, v in cls._sql_object.__dict__.items() if isinstance(v, InstrumentedAttribute)]
        output = {}
        match data:
            case dict():
                try:
                    items = data.items()
                except AttributeError as e:
                    logger.error(f"Could not prevalidate {cls.__name__} due to {e} for {pformat(data)}")
                    return data
                for key, value in items:
                    new_key = key.replace("_", "")
                    if new_key in sql_fields:
                        output[new_key] = value
                    else:
                        output[key] = value
            case _:
                output = data
        return output

    @model_validator(mode='after')
    @classmethod
    def validate_model(cls, data):
        for key, value in data.model_extra.items():
            # NOTE: make sure all date variables are date objects.
            if key in cls._sql_object.timestamps:
                if isinstance(value, str):
                    data.__setattr__(key, datetime.strptime(value, "%Y-%m-%d"))
            # NOTE: translate row letter to an integer
            if key == "row" and isinstance(value, str):
                if value.lower() in string.ascii_lowercase[0:8]:
                    try:
                        value = row_keys[value]
                    except KeyError:
                        value = value
                data.__setattr__(key, value)
        return data

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

    def improved_dict(self, dictionaries: bool = True) -> dict:
        """
        Adds model_extra to fields.

        Args:
            dictionaries (bool, optional): Are dictionaries expected as input? i.e. Should key['value'] be retrieved. Defaults to True.

        Returns:
            dict: This instance as a dictionary
        """
        fields = list(self.model_fields.keys()) + list(self.model_extra.keys())
        if dictionaries:
            output = {k: getattr(self, k) for k in fields}
        else:
            output = {k: self.filter_field(k) for k in fields}
        if "misc_info" in output.keys():
            for k, v in output['misc_info'].items():
                if k not in output.keys():
                    output[k] = v
            del output['misc_info']
        return output

    def to_sql(self):
        dicto = self.improved_dict(dictionaries=False)
        sql, new = self._sql_object.query_or_create(**dicto)
        if new:
            logger.warning(f"Creating new {self._sql_object} with values:\n{pformat(dicto)}")
        return sql

    @property
    def fields(self) -> list:
        """
        Retrieves list of field names.

        Returns:
            list: List of field names.
        """
        output = []
        for k, v in self.improved_dict().items():
            match v:
                case str() | int() | float() | datetime() | date():
                    output.append(k)
                case x if issubclass(v.__class__, PydBaseClass):
                    output.append(k)
                case _:
                    continue
        return list(set(output))





class PydEquipment(PydBaseClass):

    asset_number: str
    name: str
    nickname: str | None
    processes: List[PydProcess] | PydProcess | None
    processversion: PydProcessVersion | None = Field(default=None)
    equipmentrole: str | PydEquipmentRole | None
    tips: List[PydTips] | PydTips | None = Field(default=[])

    @field_validator('equipmentrole', mode='before')
    @classmethod
    def get_role_name(cls, value):
        from backend.db.models import EquipmentRole
        match value:
            case list():
                value = value[0]
            case GeneratorType():
                value = next(value)
            case _:
                pass
        if isinstance(value, EquipmentRole):
            value = value.name
        return value

    @field_validator('processes', mode='before')
    @classmethod
    def process_to_pydantic(cls, value, values):
        from backend.db.models import ProcessVersion, Process
        if isinstance(value, GeneratorType):
            value = [item for item in value]
        value = convert_nans_to_nones(value)
        if not value:
            value = []
        match value:
            case ProcessVersion():
                value = value.to_pydantic(pyd_model_name="PydProcess")
            case _:
                try:
                    for process in value:
                        match process:
                            case Process():
                                if values.data['name'] in [item.name for item in process.equipment]:
                                    return process.to_pydantic()
                                return None
                            case str():
                                return process
                except AttributeError as e:
                    logger.error(f"Process Validation error due to {e}")
                    value = []
        return value

    @field_validator('tips', mode='before')
    @classmethod
    def tips_to_pydantic(cls, value, values):
        from backend.db.models import TipsLot
        if isinstance(value, GeneratorType):
            value = [item for item in value]
        value = convert_nans_to_nones(value)
        if not value:
            value = []
        match value:
            case TipsLot():
                value = value.to_pydantic(pyd_model_name="PydTips")
            case dict():
                value = PydTips(**value)
            case _:
                pass
        return value

    @report_result
    def to_sql(self, procedure: Procedure | str = None, proceduretype: ProcedureType | str = None) -> Tuple[
        Equipment, ProcedureEquipmentAssociation]:
        """
        Creates Equipment and SubmssionEquipmentAssociations for this PydEquipment

        Args:
            procedure ( BasicRun | str ): BasicRun of interest

        Returns:
            Tuple[Equipment, RunEquipmentAssociation]: SQL objects
        """
        from backend.db.models import Equipment, ProcedureEquipmentAssociation, Process, EquipmentRole
        report = Report()
        if isinstance(procedure, str):
            procedure = Procedure.query(name=procedure)
        # if isinstance(proceduretype, str):
        #     proceduretype = ProcedureType.query(name=proceduretype)
        equipment = Equipment.query(asset_number=self.asset_number)
        if equipment is None:
            logger.error("No equipment found. Returning None.")
            return None, None
        if procedure is not None:
            # NOTE: Need to make sure the same association is not added to the procedure
            try:
                assoc, new = ProcedureEquipmentAssociation.query_or_create(equipment=equipment, procedure=procedure,
                                                                           equipmentrole=self.equipmentrole, limit=1)
            except TypeError as e:
                logger.error(f"Couldn't get association due to {e}, returning...")
                return None, None
            if new:
                # TODO: This seems precarious. What if there is more than one process?
                # NOTE: It looks like the way fetching the process is done in the SQL model, this shouldn't be a problem, but I'll include a failsafe.
                if len(self.processes) > 1:
                    process = Process.query(proceduretype=procedure.submissiontype, equipmentrole=self.role, limit=1)
                else:
                    process = Process.query(name=self.processes[0], limit=1)
                if process is None:
                    logger.error(f"Found unknown process: {process}.")
                assoc.process = process
                assoc.equipmentrole = EquipmentRole.query(name=self.equipmentrole, limit=1)
            else:
                logger.warning(f"Found already existing association: {assoc}")
                assoc = None
        else:
            logger.warning(f"No procedure found")
            assoc = None
        return equipment, assoc, report

    def improved_dict(self) -> dict:
        """
        Constructs a dictionary consisting of model.fields and model.extras

        Returns:
            dict: Information dictionary
        """
        try:
            extras = list(self.model_extra.keys())
        except AttributeError:
            extras = []
        fields = list(self.model_fields.keys()) + extras
        return {k: getattr(self, k) for k in fields}


class PydContact(BaseModel):

    name: str
    phone: str | None
    email: str | None

    @field_validator("phone")
    @classmethod
    def enforce_phone_number(cls, value):
        area_regex = re.compile(r"^\(?(\d{3})\)?(-| )?")
        if len(value) > 8:
            match = area_regex.match(value)
            value = area_regex.sub(f"({match.group(1).strip()}) ", value)
        return value

    @report_result
    def to_sql(self) -> Tuple[Contact, Report]:
        """
        Converts this instance into a backend.db.models.organization. Contact instance.
        Does not query for existing contact.

        Returns:
            Contact: Contact instance
        """
        report = Report()
        instance = Contact.query(name=self.name, phone=self.phone, email=self.email)
        if not instance or isinstance(instance, list):
            instance = Contact()
        try:
            all_fields = self.model_fields + self.model_extra
        except TypeError:
            all_fields = self.model_fields
        for field in all_fields:
            value = getattr(self, field)
            match field:
                case "organization":
                    value = [ClientLab.query(name=value)]
                case _:
                    pass
            try:
                instance.__setattr__(field, value)
            except AttributeError as e:
                logger.error(f"Could not set {instance} {field} to {value} due to {e}")
        return instance, report


class PydClientLab(BaseModel):

    name: str
    cost_centre: str
    contact: List[PydContact] | None

    @field_validator("contact", mode="before")
    @classmethod
    def string_to_list(cls, value):
        if isinstance(value, str):
            value = Contact.query(name=value)
            try:
                value = [value.to_pydantic()]
            except AttributeError:
                return None
        return value

    @report_result
    def to_sql(self) -> ClientLab:
        """
        Converts this instance into a backend.db.models.organization.Organization instance.

        Returns:
           Organization: Organization instance
        """
        report = Report()
        instance = ClientLab()
        for field in self.model_fields:
            match field:
                case "contact":
                    value = getattr(self, field)
                    if value:
                        value = [item.to_sql() for item in value if item]
                case _:
                    value = getattr(self, field)
            if value:
                setattr(instance, field, value)
        return instance, report


class PydReagentRole(BaseModel):

    name: str
    eol_ext: timedelta | int | None
    uses: dict | None
    required: int | None = Field(default=1)

    @field_validator("eol_ext")
    @classmethod
    def int_to_timedelta(cls, value):
        if isinstance(value, int):
            return timedelta(days=value)
        return value


class PydEquipmentRole(BaseModel):

    name: str
    equipment: List[PydEquipment]
    process: List[str] | None

    @field_validator("process", mode="before")
    @classmethod
    def expand_processes(cls, value):
        if isinstance(value, GeneratorType):
            value = [item for item in value]
        return value

    def to_form(self, parent, used: list) -> RoleComboBox:
        """
        Creates a widget for user input into this class.

        Args:
            parent (_type_): parent widget
            used (list): list of equipment already added to procedure

        Returns:
            RoleComboBox: widget
        """
        from frontend.widgets.equipment_usage import RoleComboBox
        return RoleComboBox(parent=parent, role=self, used=used)


class PydProcess(PydBaseClass, extra="allow"):
    name: str
    version: str = Field(default="1.0")
    tips: List[PydTips]

    @field_validator("tips", mode="before")
    @classmethod
    def enforce_list(cls, value):
        if not isinstance(value, list):
            value = [value]
        output = []
        for v in value:
            if issubclass(v.__class__, BaseClass):
                output.append(v.name)
            else:
                output.append(v)
        return output

    @field_validator("tips", mode="before")
    @classmethod
    def validate_tips(cls, value):
        if not value:
            return []
        value = [item for item in value if item]
        return value

    @field_validator("version", mode="before")
    @classmethod
    def enforce_float_string(cls, value):
        if isinstance(value, float):
            value = str(value)
        return value

    @report_result
    def to_sql(self):
        from backend.db.models import ProcessVersion
        report = Report()
        name = self.name.split("-")[0]
        # NOTE: can't use query_or_create due to name not being part of ProcessVersion
        logger.debug(f"Querying name: {name}, version: {self.version}")
        instance = ProcessVersion.query(name=name, version=float(self.version), limit=1)
        if not instance:
            logger.warning(f"Gonna have to make a new process version {self.version}")
            instance = ProcessVersion()
        logger.debug(f"Got instance: {instance.__dict__}")
        return instance, report


class PydProcessVersion(PydBaseClass, extra="allow", arbitrary_types_allowed=True):
    version: float
    name: str

    @field_validator("name")
    @classmethod
    def split_name(cls, value):
        if "-" in value:
            value = value.split("-")[0]
        return value

    def to_sql(self):
        from backend.db.models import ProcessVersion
        instance = ProcessVersion.query(name=self.name, version=self.version, limit=1)
        if not instance:
            logger.warning(f"PV: Gonna have to make a new process version {self.version}")
            instance = ProcessVersion()
        return instance


class PydProcedure(PydBaseClass, arbitrary_types_allowed=True):
    proceduretype: Any | None = Field(default=None)
    run: Any | str | None = Field(default=None)
    name: dict = Field(default=dict(value="NA", missing=True), validate_default=True)
    technician: dict = Field(default=dict(value="NA", missing=True))
    repeat: bool = Field(default=False)
    repeat_of: Any | None = Field(default=None)
    plate_map: str | None = Field(default=None)
    reagent: list | None = Field(default=[])
    reagentrole: dict | None = Field(default={}, validate_default=True)
    sample: List[PydSample] = Field(default=[])
    equipment: List[PydEquipment] = Field(default=[])
    result: List[PydResults] | List[dict] = Field(default=[])

    @field_validator("name", "technician", mode="before")#"kittype", mode="before")
    @classmethod
    def convert_to_dict(cls, value):
        if not value:
            value = "NA"
        if isinstance(value, str):
            value = dict(value=value, missing=False)
        return value

    @field_validator("proceduretype", mode="before")
    @classmethod
    def lookup_proceduretype(cls, value):
        from backend.db.models import ProcedureType
        match value:
            case dict():
                value = ProcedureType.query(name=value['name'])
            case str():
                value = ProcedureType.query(name=value)
            case _:
                pass
        return value

    @field_validator("name")
    @classmethod
    def rescue_name(cls, value, values):
        if value['value'] == cls.model_fields['name'].default['value']:
            if values.data['proceduretype']:
                procedure_type = values.data['proceduretype'].name
            else:
                procedure_type = None
            if values.data['run']:
                run = values.data['run'].rsl_plate_number
            else:
                run = None
            value['value'] = f"{run}-{procedure_type}"
            value['missing'] = True
        return value

    @field_validator("name", "technician")#, "kittype")
    @classmethod
    def set_colour(cls, value):
        try:
            if value["missing"]:
                value["colour"] = "FE441D"
            else:
                value["colour"] = "6FFE1D"
        except KeyError:
            pass
        return value

    @field_validator("reagentrole")
    @classmethod
    def rescue_reagentrole(cls, value, values):
        if not value:
            value = {}
            for reagentrole in values.data['proceduretype'].reagentrole:
                reagents = [reagent.lot_dicts for reagent in reagentrole.reagent]
                value[reagentrole.name] = flatten_list(reagents)
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
        insertable = PydReagent(reagentrole=reagentrole, name=name, lot=lot, expiry=expiry)
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
        processversion = ProcessVersion.query(name=process_name, version=version, limit=1)
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

    def to_sql(self, new: bool = False):
        from backend.db.models import (
            RunSampleAssociation, ProcedureSampleAssociation, Procedure, ProcedureReagentLotAssociation,
            ProcedureEquipmentAssociation, EquipmentRole, ReagentRole
        )
        if new:
            sql = Procedure()
        else:
            sql = super().to_sql()
        if isinstance(self.name, dict):
            sql.name = self.name['value']
        else:
            sql.name = self.name
        if isinstance(self.technician, dict):
            sql.technician = self.technician['value']
        else:
            sql.technician = self.technician
        if sql.repeat:
            regex = re.compile(r".*\dR\d$")
            repeats = [item for item in self.run.procedure if
                       self.repeat_of.name in item.name and bool(regex.match(item.name))]
            sql.name = f"{self.repeat_of.name}-R{str(len(repeats) + 1)}"
        sql.repeat_of = self.repeat_of
        sql.started_date = datetime.now()
        if self.run:
            sql.run = self.run
        if self.proceduretype:
            sql.proceduretype = self.proceduretype
        # NOTE: reset reagent associations.
        for reagent in self.reagent:
            if isinstance(reagent, dict):
                reagent = PydReagent(**reagent)
            reagentrole = ReagentRole.query(reagent.reagentrole, limit=1)
            reagent = reagent.to_sql()
            if reagent not in sql.reagentlot:
                # NOTE: Remove any previous association for this role.
                if sql.id:
                    removable = ProcedureReagentLotAssociation.query(procedure=sql, reagentrole=reagentrole)
                else:
                    removable = []
                if removable:
                    if isinstance(removable, list):
                        for r in removable:
                            r.delete()
                    else:
                        removable.delete()
                reagent_assoc = ProcedureReagentLotAssociation(reagentlot=reagent, procedure=sql, reagentrole=reagentrole)
        try:
            start_index = max([item.id for item in ProcedureSampleAssociation.query()]) + 1
        except ValueError:
            start_index = 1
        relevant_samples = [sample for sample in self.sample if
                            not sample.sample_id.startswith("blank_") and not sample.sample_id == ""]
        assoc_id_range = range(start_index, start_index + len(relevant_samples) + 1)
        for iii, sample in enumerate(relevant_samples):
            sample_sql = sample.to_sql()
            if sql.run:
                if sample_sql not in sql.run.sample:
                    with sample_sql.__database_session__.no_autoflush:
                        run_assoc = RunSampleAssociation(sample=sample_sql, run=self.run, row=sample.row,
                                                     column=sample.column)
            if sample_sql not in sql.sample:
                with sample_sql.__database_session__.no_autoflush:
                    proc_assoc = ProcedureSampleAssociation(new_id=assoc_id_range[iii], procedure=sql, sample=sample_sql,
                                                        row=sample.row, column=sample.column,
                                                        procedure_rank=sample.procedure_rank)
        for equipment in self.equipment:
            equip, _ = equipment.to_sql()
            equipment_role = EquipmentRole.query(equipment.equipmentrole, limit=1)
            if isinstance(equipment.tips, list):
                try:
                    equipment.tips = equipment.tips[0]
                except IndexError:
                    equipment.tips = None
            if equip not in sql.equipment:
                equip_assoc = ProcedureEquipmentAssociation(equipment=equip, procedure=sql, equipmentrole=equipment_role)
                processversion = equipment.processversion.to_sql()
                equip_assoc.processversion = processversion
                try:
                    tipslot = equipment.tips.to_sql()
                except AttributeError:
                    tipslot = None
                equip_assoc.tipslot = tipslot
        return sql, None


class PydClientSubmission(PydBaseClass):

    key_value_order = ["submitter_plate_id",
                       "submitted_date",
                       "client_lab",
                       "contact",
                       "contact_email",
                       "cost_centre",
                       "submission_type",
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
    sample: List[PydSample] | None = Field(default=[])

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
            case date():
                value = dict(value=value, missing=False)
            case datetime():
                value = dict(value=value.date(), missing=False)
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
        sql = super().to_sql()
        from backend.db.models import SubmissionType
        assert not any([isinstance(item, PydSample) for item in sql.sample])
        sql.sample = []
        if not sql.submissiontype:
            sql.submissiontype = SubmissionType.query(name=self.submissiontype['value'])
        match sql.submissiontype:
            case SubmissionType():
                pass
            case _:
                sql.submissiontype = SubmissionType.query(name="Default")
        for k in list(self.model_fields.keys()) + list(self.model_extra.keys()):
            attribute = getattr(self, k)
            match k:
                case "filepath":
                    sql._misc_info[k] = attribute.__str__()
                    continue
                case _:
                    pass
        return sql

    @property
    def max_sample_rank(self) -> int:
        output = self.full_batch_size
        if output > 0:
            return output
        else:
            return max([item.submission_rank for item in self.sample])

    def improved_dict(self, dictionaries: bool = True) -> dict:
        output = super().improved_dict(dictionaries=dictionaries)
        output['sample'] = self.sample
        output['client_lab'] = output['clientlab']
        try:
            output['contact_email'] = output['contact']['email']
        except TypeError:
            pass
        return sort_dict_by_list(output, self.key_value_order)

    @property
    def filename_template(self):
        try:
            submissiontype = SubmissionType.query(name=self.submissiontype['value'])
        except KeyError as e:
            submissiontype = SubmissionType.query(name=self.submissiontype['name'])
        return submissiontype.defaults['filename_template']


class PydRun(PydBaseClass):  #, extra='allow'):

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
            case date():
                output = datetime.combine(value['value'], datetime.min.time())
            case datetime():
                pass
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

    @field_validator("completed_date")
    @classmethod
    def strip_completed_datetime_string(cls, value):
        match value['value']:
            case date():
                output = datetime.combine(value['value'], datetime.min.time())
            case datetime():
                pass
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

    def improved_dict(self, dictionaries: bool = True) -> dict:
        """
        Adds model_extra to fields.

        Args:
            dictionaries (bool, optional): Are dictionaries expected as input? i.e. Should key['value'] be retrieved. Defaults to True.

        Returns:
            dict: This instance as a dictionary
        """
        fields = list(self.model_fields.keys()) + list(self.model_extra.keys())
        if dictionaries:
            output = {k: getattr(self, k) for k in fields}
            # output['reagents'] = [item.improved_dict() for item in self.reagents]
            output['sample'] = [item.improved_dict() for item in self.sample]
            # try:
            #     output['equipment'] = [item.improved_dict() for item in self.equipment]
            # except TypeError:
            #     pass
        else:
            output = {k: self.filter_field(k) for k in fields}
        return output

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
        info = {k: v for k, v in self.improved_dict().items() if isinstance(v, dict)}
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
        report = Report()
        dicto = self.improved_dict()
        instance, result = Run.query_or_create(submissiontype=self.submission_type['value'],
                                               rsl_plate_number=self.rsl_plate_number['value'])
        if instance is None:
            report.add_result(Alert(msg="Overwrite Cancelled."))
            return None, report
        report.add_result(result)
        self.handle_duplicate_samples()
        for key, value in dicto.items():
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
            sample = sample.improved_dict()
            sample['row'] = sample['row'][0]
            sample['column'] = sample['column'][0]
            sample['submission_rank'] = sample['submission_rank'][0]
            samples.append(sample)
        samples = sorted(samples, key=itemgetter("submission_rank"))
        return samples
