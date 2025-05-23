"""
Contains pydantic models and accompanying validators
"""
from __future__ import annotations
import uuid, re, logging, csv, sys, string
from pydantic import BaseModel, field_validator, Field, model_validator, PrivateAttr
from datetime import date, datetime, timedelta
from dateutil.parser import parse
from dateutil.parser import ParserError
from typing import List, Tuple, Literal
from types import GeneratorType
from . import RSLNamer
from pathlib import Path
from tools import check_not_nan, convert_nans_to_nones, Report, Result, timezone
from backend.db import models
from backend.db.models import *
from sqlalchemy.exc import StatementError, IntegrityError
from sqlalchemy.orm.properties import ColumnProperty
from sqlalchemy.orm.relationships import _RelationshipDeclared
from sqlalchemy.orm.attributes import InstrumentedAttribute
from PyQt6.QtWidgets import QWidget

logger = logging.getLogger(f"procedure.{__name__}")


class PydBaseClass(BaseModel, extra='allow', validate_assignment=True):
    _sql_object: ClassVar = None

    @model_validator(mode="before")
    @classmethod
    def prevalidate(cls, data):
        sql_fields = [k for k, v in cls._sql_object.__dict__.items() if isinstance(v, InstrumentedAttribute)]
        output = {}
        for key, value in data.items():
            new_key = key.replace("_", "")
            if new_key in sql_fields:
                output[new_key] = value
            else:
                output[key] = value
        return output

    @model_validator(mode='after')
    @classmethod
    def validate_model(cls, data):
        # _sql_object = getattr(models, cls.__name__.replace("Pyd", ""))

        # total_dict = data.model_fields.update(data.model_extra)
        for key, value in data.model_extra.items():
            if key in cls._sql_object.timestamps:
                if isinstance(value, str):
                    data.__setattr__(key, datetime.strptime(value, "%Y-%m-%d"))
            if key == "row" and isinstance(value, str):
                if value.lower() in string.ascii_lowercase[0:8]:
                    try:
                        value = row_keys[value]
                    except KeyError:
                        value = value
                data.__setattr__(key, value)
        return data

    def __init__(self, **data):
        # NOTE: Grab the sql model for validation purposes.
        self.__class__._sql_object = getattr(models, self.__class__.__name__.replace("Pyd", ""))
        super().__init__(**data)

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
        return output

    def to_sql(self):
        dicto = self.improved_dict(dictionaries=False)
        logger.debug(f"Dicto: {dicto}")
        sql, _ = self._sql_object().query_or_create(**dicto)

        return sql


class PydReagent(BaseModel):
    lot: str | None
    reagentrole: str | None
    expiry: date | datetime | Literal['NA'] | None = Field(default=None, validate_default=True)
    name: str | None = Field(default=None, validate_default=True)
    missing: bool = Field(default=True)
    comment: str | None = Field(default="", validate_default=True)

    @field_validator('comment', mode='before')
    @classmethod
    def create_comment(cls, value):
        if value is None:
            return ""
        return value

    @field_validator("reagentrole", mode='before')
    @classmethod
    def remove_undesired_types(cls, value):
        match value:
            case "atcc":
                return None
            case _:
                return value

    @field_validator("reagentrole")
    @classmethod
    def rescue_type_with_lookup(cls, value, values):
        if value is None and values.data['lot'] is not None:
            try:
                return Reagent.query(lot=values.data['lot']).name
            except AttributeError:
                return value
        return value

    @field_validator("lot", mode='before')
    @classmethod
    def rescue_lot_string(cls, value):
        if value is not None:
            return convert_nans_to_nones(str(value).strip())
        return value

    @field_validator("lot")
    @classmethod
    def enforce_lot_string(cls, value):
        if value is not None:
            return value.upper().strip()
        return value

    @field_validator("expiry", mode="before")
    @classmethod
    def enforce_date(cls, value):
        if value is not None:
            match value:
                case int():
                    return datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value - 2)
                case 'NA':
                    return value
                case str():
                    return parse(value)
                case date():
                    return datetime.combine(value, datetime.max.time())
                case datetime():
                    return value
                case _:
                    return convert_nans_to_nones(str(value))
        if value is None:
            value = date.today()
        return value

    @field_validator("expiry")
    @classmethod
    def date_na(cls, value):
        if isinstance(value, date) and value.year == 1970:
            value = "NA"
        return value

    @field_validator("name", mode="before")
    @classmethod
    def enforce_name(cls, value, values):
        if value is not None:
            return convert_nans_to_nones(str(value).strip())
        else:
            return values.data['reagentrole'].strip()

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

    @report_result
    def to_sql(self, procedure: Procedure | str = None) -> Tuple[Reagent, Report]:
        """
        Converts this instance into a backend.db.models.kittype.Reagent instance

        Returns:
            Tuple[Reagent, Report]: Reagent instance and result of function
        """
        report = Report()
        if self.model_extra is not None:
            self.__dict__.update(self.model_extra)
        reagent = Reagent.query(lot=self.lot, name=self.name)
        # logger.debug(f"Reagent: {reagent}")
        if reagent is None:
            reagent = Reagent()
            for key, value in self.__dict__.items():
                if isinstance(value, dict):
                    value = value['value']
                # NOTE: reagent method sets fields based on keys in dictionary
                reagent.set_attribute(key, value)
                if procedure is not None and reagent not in procedure.reagents:
                    assoc = ProcedureReagentAssociation(reagent=reagent, procedure=procedure)
                    assoc.comments = self.comment
                else:
                    assoc = None
        else:
            if submission is not None and reagent not in submission.reagents:
                submission.update_reagentassoc(reagent=reagent, role=self.role)
        return reagent, report


class PydSample(PydBaseClass):
    sample_id: str
    sampletype: str | None = Field(default=None)
    submission_rank: int | List[int] | None = Field(default=0, validate_default=True)
    enabled: bool = Field(default=True)

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


class PydTips(BaseModel):
    name: str
    lot: str | None = Field(default=None)
    tiprole: str

    @field_validator('tiprole', mode='before')
    @classmethod
    def get_role_name(cls, value):
        if isinstance(value, TipRole):
            value = value.name
        return value

    @report_result
    def to_sql(self, procedure: Run) -> ProcedureTipsAssociation:
        """
        Convert this object to the SQL version for database storage.

        Args:
            procedure (BasicRun): A procedure object to associate tips represented here.

        Returns:
            SubmissionTipsAssociation: Association between queried tips and procedure
        """
        report = Report()
        tips = Tips.query(name=self.name, limit=1)
        # logger.debug(f"Tips query has yielded: {tips}")
        assoc = ProcedureTipsAssociation.query_or_create(tips=tips, procedure=procedure, role=self.role, limit=1)
        return assoc, report


class PydEquipment(BaseModel, extra='ignore'):
    asset_number: str
    name: str
    nickname: str | None
    process: List[str] | None
    equipmentrole: str | None
    tips: List[PydTips] | None = Field(default=None)

    @field_validator('equipmentrole', mode='before')
    @classmethod
    def get_role_name(cls, value):
        if isinstance(value, EquipmentRole):
            value = value.name
        return value

    @field_validator('process', mode='before')
    @classmethod
    def make_empty_list(cls, value):
        if isinstance(value, GeneratorType):
            value = [item.name for item in value]
        value = convert_nans_to_nones(value)
        if not value:
            value = ['']
        try:
            value = [item.strip() for item in value]
        except AttributeError:
            pass
        return value

    @report_result
    def to_sql(self, procedure: Procedure | str = None, kittype: KitType | str = None) -> Tuple[
        Equipment, ProcedureEquipmentAssociation]:
        """
        Creates Equipment and SubmssionEquipmentAssociations for this PydEquipment

        Args:
            procedure ( BasicRun | str ): BasicRun of interest

        Returns:
            Tuple[Equipment, RunEquipmentAssociation]: SQL objects
        """
        report = Report()
        if isinstance(procedure, str):
            procedure = Procedure.query(name=procedure)
        if isinstance(kittype, str):
            kittype = KitType.query(name=kittype)
        equipment = Equipment.query(asset_number=self.asset_number)
        if equipment is None:
            logger.error("No equipment found. Returning None.")
            return
        if procedure is not None:
            # NOTE: Need to make sure the same association is not added to the procedure
            try:
                assoc = ProcedureEquipmentAssociation.query(equipment_id=equipment.id, submission_id=procedure.id,
                                                            equipmentrole=self.equipmentrole, limit=1)
            except TypeError as e:
                logger.error(f"Couldn't get association due to {e}, returning...")
                assoc = None
            if assoc is None:
                assoc = ProcedureEquipmentAssociation(submission=procedure, equipment=equipment)
                # TODO: This seems precarious. What if there is more than one process?
                # NOTE: It looks like the way fetching the process is done in the SQL model, this shouldn't be a problem, but I'll include a failsafe.
                # NOTE: I need to find a way to filter this by the kittype involved.
                if len(self.processes) > 1:
                    process = Process.query(proceduretype=procedure.get_submission_type(), kittype=kittype,
                                            equipmentrole=self.role)
                else:
                    process = Process.query(name=self.processes[0])
                if process is None:
                    logger.error(f"Found unknown process: {process}.")
                # logger.debug(f"Using process: {process}")
                assoc.process = process
                assoc.equipmentrole = self.role
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


class PydSubmission(BaseModel, extra='allow'):
    filepath: Path
    submissiontype: dict | None
    submitter_plate_id: dict | None = Field(default=dict(value=None, missing=True), validate_default=True)
    rsl_plate_num: dict | None = Field(default=dict(value=None, missing=True), validate_default=True)
    submitted_date: dict | None = Field(default=dict(value=date.today(), missing=True), validate_default=True)
    clientlab: dict | None
    sample_count: dict | None
    kittype: dict | None
    technician: dict | None
    submission_category: dict | None = Field(default=dict(value=None, missing=True), validate_default=True)
    comment: dict | None = Field(default=dict(value="", missing=True), validate_default=True)
    reagent: List[dict] | List[PydReagent] = []
    sample: List[PydSample] | Generator
    equipment: List[PydEquipment] | None = []
    cost_centre: dict | None = Field(default=dict(value=None, missing=True), validate_default=True)
    contact: dict | None = Field(default=dict(value=None, missing=True), validate_default=True)
    tips: List[PydTips] | None = []

    @field_validator("tips", mode="before")
    @classmethod
    def expand_tips(cls, value):
        if isinstance(value, dict):
            value = value['value']
        if isinstance(value, Generator):
            return [PydTips(**tips) for tips in value]
        if not value:
            return []
        return value

    @field_validator('equipment', mode='before')
    @classmethod
    def convert_equipment_dict(cls, value):
        if isinstance(value, dict):
            return value['value']
        if isinstance(value, Generator):
            return [PydEquipment(**equipment) for equipment in value]
        if not value:
            return []
        return value

    @field_validator('comment', mode='before')
    @classmethod
    def create_comment(cls, value):
        if value is None:
            return ""
        return value

    @field_validator("submitter_plate_id")
    @classmethod
    def enforce_with_uuid(cls, value):
        if value['value'] in [None, "None"]:
            return dict(value=uuid.uuid4().hex.upper(), missing=True)
        else:
            value['value'] = value['value'].strip()
            return value

    @field_validator("submitted_date", mode="before")
    @classmethod
    def rescue_date(cls, value):
        try:
            check = value['value'] is None
        except TypeError:
            check = True
        if check:
            return dict(value=date.today(), missing=True)
        return value

    @field_validator("submitted_date")
    @classmethod
    def strip_datetime_string(cls, value):
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

    @field_validator("clientlab", mode="before")
    @classmethod
    def rescue_submitting_lab(cls, value):
        if value is None:
            return dict(value=None, missing=True)
        return value

    @field_validator("clientlab")
    @classmethod
    def lookup_submitting_lab(cls, value):
        if isinstance(value['value'], str):
            try:
                value['value'] = ClientLab.query(name=value['value']).name
            except AttributeError:
                value['value'] = None
        if value['value'] is None:
            value['missing'] = True
            if "pytest" in sys.modules:
                value['value'] = "Nosocomial"
                return value
            from frontend.widgets.pop_ups import ObjectSelector
            dlg = ObjectSelector(title="Missing Submitting Lab",
                                 message="We need a submitting lab. Please select from the list.",
                                 obj_type=ClientLab)
            if dlg.exec():
                value['value'] = dlg.parse_form()
            else:
                value['value'] = None
        return value

    @field_validator("rsl_plate_num", mode='before')
    @classmethod
    def rescue_rsl_number(cls, value):
        if value is None:
            return dict(value=None, missing=True)
        return value

    @field_validator("rsl_plate_num")
    @classmethod
    def rsl_from_file(cls, value, values):
        sub_type = values.data['proceduretype']['value']
        if check_not_nan(value['value']):
            value['value'] = value['value'].strip()
            return value
        else:
            if "pytest" in sys.modules and sub_type.replace(" ", "") == "BasicRun":
                output = "RSL-BS-Test001"
            else:
                output = RSLNamer(filename=values.data['filepath'].__str__(), submission_type=sub_type,
                                  data=values.data).parsed_name
            return dict(value=output, missing=True)

    @field_validator("technician", mode="before")
    @classmethod
    def rescue_tech(cls, value):
        if value is None:
            return dict(value=None, missing=True)
        return value

    @field_validator("technician")
    @classmethod
    def enforce_tech(cls, value):
        if check_not_nan(value['value']):
            value['value'] = re.sub(r"\: \d", "", value['value'])
            return value
        else:
            return dict(value=convert_nans_to_nones(value['value']), missing=True)

    @field_validator("sample_count", mode='before')
    @classmethod
    def rescue_sample_count(cls, value):
        if value is None:
            return dict(value=None, missing=True)
        return value

    @field_validator("kittype", mode='before')
    @classmethod
    def rescue_kit(cls, value):
        if check_not_nan(value):
            if isinstance(value, str):
                return dict(value=value, missing=False)
            elif isinstance(value, dict):
                return value
        else:
            raise ValueError(f"No extraction kittype found.")
        if value is None:
            # NOTE: Kit selection is done in the clientsubmissionparser, so should not be necessary here.
            return dict(value=None, missing=True)
        return value

    @field_validator("submissiontype", mode='before')
    @classmethod
    def make_submission_type(cls, value, values):
        if not isinstance(value, dict):
            value = dict(value=value)
        if check_not_nan(value['value']):
            value = value['value'].title()
            return dict(value=value, missing=False)
        else:
            return dict(value=RSLNamer.retrieve_submission_type(filename=values.data['filepath']).title(), missing=True)

    @field_validator("submission_category", mode="before")
    @classmethod
    def create_category(cls, value):
        if not isinstance(value, dict):
            return dict(value=value, missing=True)
        return value

    @field_validator("submission_category")
    @classmethod
    def rescue_category(cls, value, values):
        if isinstance(value['value'], str):
            value['value'] = value['value'].title()
        if value['value'] not in ["Research", "Diagnostic", "Surveillance", "Validation"]:
            value['value'] = values.data['proceduretype']['value']
        return value

    @field_validator("reagent", mode="before")
    @classmethod
    def expand_reagents(cls, value):
        if isinstance(value, Generator):
            return [PydReagent(**reagent) for reagent in value]
        return value

    @field_validator("sample", mode="before")
    @classmethod
    def expand_samples(cls, value):
        if isinstance(value, Generator):
            return [PydSample(**sample) for sample in value]
        return value

    @field_validator("sample")
    @classmethod
    def assign_ids(cls, value):
        starting_id = ClientSubmissionSampleAssociation.autoincrement_id()
        for iii, sample in enumerate(value, start=starting_id):
            # NOTE: Why is this a list? Answer: to zip with the lists of rows and columns in case of multiple of the same sample.
            sample.assoc_id = [iii]
        return value

    @field_validator("cost_centre", mode="before")
    @classmethod
    def rescue_cost_centre(cls, value):
        match value:
            case dict():
                return value
            case _:
                return dict(value=value, missing=True)

    @field_validator("cost_centre")
    @classmethod
    def get_cost_centre(cls, value, values):
        match value['value']:
            case None:
                from backend.db.models import Organization
                org = Organization.query(name=values.data['clientlab']['value'])
                try:
                    return dict(value=org.cost_centre, missing=True)
                except AttributeError:
                    return dict(value="xxx", missing=True)
            case _:
                return value

    @field_validator("contact")
    @classmethod
    def get_contact_from_org(cls, value, values):
        # logger.debug(f"Value coming in: {value}")
        match value:
            case dict():
                if isinstance(value['value'], tuple):
                    value['value'] = value['value'][0]
            case tuple():
                value = dict(value=value[0], missing=False)
            case _:
                value = dict(value=value, missing=False)
        # logger.debug(f"Value after match: {value}")
        check = Contact.query(name=value['value'])
        # logger.debug(f"Check came back with {check}")
        if not isinstance(check, Contact):
            org = values.data['clientlab']['value']
            # logger.debug(f"Checking organization: {org}")
            if isinstance(org, str):
                org = ClientLab.query(name=values.data['clientlab']['value'], limit=1)
            if isinstance(org, ClientLab):
                contact = org.contact[0].name
            else:
                logger.warning(f"All attempts at defaulting Contact failed, returning: {value}")
                return value
            if isinstance(contact, tuple):
                contact = contact[0]
            value = dict(value=f"Defaulted to: {contact}", missing=False)
            # logger.debug(f"Value after query: {value}")
            return value
        else:
            # logger.debug(f"Value after bypass check: {value}")
            return value

    def __init__(self, run_custom: bool = False, **data):
        super().__init__(**data)
        # NOTE: this could also be done with default_factory
        self.submission_object = Run.find_polymorphic_subclass(
            polymorphic_identity=self.submission_type['value'])
        self.namer = RSLNamer(self.rsl_plate_num['value'], submission_type=self.submission_type['value'])
        if run_custom:
            self.submission_object.custom_validation(pyd=self)

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
            output['reagents'] = [item.improved_dict() for item in self.reagents]
            output['sample'] = [item.improved_dict() for item in self.samples]
            try:
                output['equipment'] = [item.improved_dict() for item in self.equipment]
            except TypeError:
                pass
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
    def to_sql(self) -> Tuple[BasicRun | None, Report]:
        """
        Converts this instance into a backend.db.models.procedure.BasicRun instance

        Returns:
            Tuple[BasicRun, Result]: BasicRun instance, result object
        """
        report = Report()
        dicto = self.improved_dict()
        # logger.debug(f"Pydantic procedure type: {self.proceduretype['value']}")
        # logger.debug(f"Pydantic improved_dict: {pformat(dicto)}")
        instance, result = BasicRun.query_or_create(submissiontype=self.submission_type['value'],
                                                    rsl_plate_num=self.rsl_plate_num['value'])
        # logger.debug(f"Created or queried instance: {instance}")
        if instance is None:
            report.add_result(Result(msg="Overwrite Cancelled."))
            return None, report
        report.add_result(result)
        self.handle_duplicate_samples()
        for key, value in dicto.items():
            # logger.debug(f"Checking key {key}, value {value}")
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
                    # logger.debug(f"Validating json value: {item} to value:{pformat(value)}")
                    try:
                        ii = value.items()
                    except AttributeError:
                        ii = {}
                    for k, v in ii:
                        if isinstance(v, datetime):
                            value[k] = v.strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            pass
                    # logger.debug(f"Setting json value: {item} to value:{pformat(value)}")
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
        try:
            logger.debug(f"PCR info: {self.pcr_info}")
        except AttributeError:
            pass
        return SubmissionFormWidget(parent=parent, pyd=self, disable=disable)

    def to_writer(self) -> "SheetWriter":
        """
        Sends data here to the sheet writer.

        Returns:
            SheetWriter: Sheetwriter object that will perform writing.
        """
        from backend.excel.writer import SheetWriter
        return SheetWriter(self)

    def construct_filename(self) -> str:
        """
        Creates filename for this instance

        Returns:
            str: Output filename
        """
        template = self.submission_object.filename_template()
        render = self.namer.construct_export_name(template=template, **self.improved_dict(dictionaries=False)).replace(
            "/", "")
        return render

    def check_kit_integrity(self, extraction_kit: str | dict | None = None, exempt: List[PydReagent] = []) -> Tuple[
        List[PydReagent], Report, List[PydReagent]]:
        """
        Ensures all reagents expected in kittype are listed in Submission
       
        Args:
            extraction_kit (str | dict | None, optional): kittype to be checked. Defaults to None.
            exempt (List[PydReagent], optional): List of reagents that don't need to be checked. Defaults to []

        Returns:
            Tuple[List[PydReagent], Report]: List of reagents and Result object containing a message and any missing components.
        """
        report = Report()
        # logger.debug(f"The following reagents are exempt from the kittype integrity check:\n{exempt}")
        if isinstance(extraction_kit, str):
            extraction_kit = dict(value=extraction_kit)
        if extraction_kit is not None and extraction_kit != self.extraction_kit['value']:
            self.extraction_kit['value'] = extraction_kit['value']
        ext_kit = KitType.query(name=self.extraction_kit['value'])
        ext_kit_rtypes = [item.to_pydantic() for item in
                          ext_kit.get_reagents(required_only=True, proceduretype=self.submission_type['value'])]
        # NOTE: Exclude any reagenttype found in this pydclientsubmission not expected in kittype.
        expected_check = [item.equipmentrole for item in ext_kit_rtypes]
        output_reagents = [rt for rt in self.reagents if rt.role in expected_check]
        missing_check = [item.role for item in output_reagents]
        missing_reagents = [rt for rt in ext_kit_rtypes if
                            rt.equipmentrole not in missing_check and rt.equipmentrole not in exempt]
        # logger.debug(f"Missing reagents: {missing_reagents}")
        missing_reagents += [rt for rt in output_reagents if rt.missing]
        output_reagents += [rt for rt in missing_reagents if rt not in output_reagents]
        # NOTE: if lists are equal return no problem
        if len(missing_reagents) == 0:
            result = None
        else:
            result = Result(
                msg=f"The excel sheet you are importing is missing some reagents expected by the kittype.\n\nIt looks like you are missing: {[item.equipmentrole.upper() for item in missing_reagents]}\n\nAlternatively, you may have set the wrong extraction kittype.\n\nThe program will populate lists using existing reagents.\n\nPlease make sure you check the lots carefully!",
                status="Warning")
        report.add_result(result)
        return output_reagents, report, missing_reagents

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
            result = Result(status="Warning",
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
            # logger.debug(f"Match: {match.group(1)}")
            value = area_regex.sub(f"({match.group(1).strip()}) ", value)
            # logger.debug(f"Output phone: {value}")
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
                    value = [Organization.query(name=value)]
                case _:
                    pass
            try:
                instance.__setattr__(field, value)
            except AttributeError as e:
                logger.error(f"Could not set {instance} {field} to {value} due to {e}")
        return instance, report


class PydOrganization(BaseModel):
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
            logger.debug(f"Setting {field} to {value}")
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

    @report_result
    def to_sql(self, kit: KitType) -> ReagentRole:
        """
        Converts this instance into a backend.db.models.ReagentType instance

        Args:
            kit (KitType): KitType joined to the reagentrole

        Returns:
            ReagentRole: ReagentType instance
        """
        report = Report()
        instance: ReagentRole = ReagentRole.query(name=self.name)
        if instance is None:
            instance = ReagentRole(name=self.name, eol_ext=self.eol_ext)
        try:
            assoc = KitTypeReagentRoleAssociation.query(reagentrole=instance, kittype=kit)
        except StatementError:
            assoc = None
        if assoc is None:
            assoc = KitTypeReagentRoleAssociation(kittype=kit, reagentrole=instance, uses=self.uses,
                                                  required=self.required)
        return instance, report


class PydKitType(BaseModel):
    name: str
    reagent_roles: List[PydReagent] = []

    @report_result
    def to_sql(self) -> Tuple[KitType, Report]:
        """
        Converts this instance into a backend.db.models.kits.KitType instance

        Returns:
            Tuple[KitType, Report]: KitType instance and report of results.
        """
        report = Report()
        instance = KitType.query(name=self.name)
        if instance is None:
            instance = KitType(name=self.name)
            for role in self.reagent_roles:
                role.to_sql(instance)
        return instance, report


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

    def to_form(self, parent, used: list) -> "RoleComboBox":
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


# class PydPCRControl(BaseModel):
#
#     name: str
#     subtype: str
#     target: str
#     ct: float
#     reagent_lot: str
#     submitted_date: datetime  #: Date submitted to Robotics
#     procedure_id: int
#     controltype_name: str
#
#     @report_result
#     def to_sql(self):
#         report = Report
#         instance = PCRControl.query(name=self.name)
#         if not instance:
#             instance = PCRControl()
#         for key in self.model_fields:
#             field_value = self.__getattribute__(key)
#             if instance.__getattribute__(key) != field_value:
#                 instance.__setattr__(key, field_value)
#         return instance, report
#
#
# class PydIridaControl(BaseModel, extra='ignore'):
#
#     name: str
#     contains: list | dict  #: unstructured hashes in contains.tsv for each organism
#     matches: list | dict  #: unstructured hashes in matches.tsv for each organism
#     kraken: list | dict  #: unstructured output from kraken_report
#     subtype: Literal["ATCC49226", "ATCC49619", "EN-NOS", "EN-SSTI", "MCS-NOS", "MCS-SSTI", "SN-NOS", "SN-SSTI"]
#     refseq_version: str  #: version of refseq used in fastq parsing
#     kraken2_version: str
#     kraken2_db_version: str
#     sample_id: int
#     submitted_date: datetime  #: Date submitted to Robotics
#     procedure_id: int
#     controltype_name: str
#
#     @field_validator("refseq_version", "kraken2_version", "kraken2_db_version", mode='before')
#     @classmethod
#     def enforce_string(cls, value):
#         if not value:
#             value = ""
#         return value
#
#     @report_result
#     def to_sql(self):
#         report = Report()
#         instance = IridaControl.query(name=self.name)
#         if not instance:
#             instance = IridaControl()
#         for key in self.model_fields:
#             field_value = self.__getattribute__(key)
#             if instance.__getattribute__(key) != field_value:
#                 instance.__setattr__(key, field_value)
#         return instance, report


class PydProcess(BaseModel, extra="allow"):
    name: str
    version: str = Field(default="1")
    submissiontype: List[str]
    equipment: List[str]
    equipmentrole: List[str]
    kittype: List[str]
    tiprole: List[str]

    @field_validator("submissiontype", "equipment", "equipmentrole", "kittype", "tiprole", mode="before")
    @classmethod
    def enforce_list(cls, value):
        if not isinstance(value, list):
            return [value]
        return value

    @report_result
    def to_sql(self):
        report = Report()
        instance = Process.query(name=self.name)
        if not instance:
            instance = Process()
        fields = [item for item in self.model_fields]
        for field in fields:
            logger.debug(f"Field: {field}")
            try:
                field_type = getattr(instance.__class__, field).property
            except AttributeError:
                logger.error(f"No attribute: {field} in {instance.__class__}")
                continue
            match field_type:
                case _RelationshipDeclared():
                    logger.debug(f"{field} is a relationship with {field_type.entity.class_}")
                    query_str = getattr(self, field)
                    if isinstance(query_str, list):
                        query_str = query_str[0]
                    if query_str in ["", " ", None]:
                        continue
                    logger.debug(f"Querying {field_type.entity.class_} with name {query_str}")
                    field_value = field_type.entity.class_.query(name=query_str)
                    logger.debug(f"{field} query result: {field_value}")
                case ColumnProperty():
                    logger.debug(f"{field} is a property.")
                    field_value = getattr(self, field)
            instance.set_attribute(key=field, value=field_value)
        return instance, report


class PydElastic(BaseModel, extra="allow", arbitrary_types_allowed=True):
    """Allows for creation of arbitrary pydantic models"""
    instance: BaseClass

    @report_result
    def to_sql(self):
        # print(self.instance)
        fields = [item for item in self.model_extra]
        for field in fields:
            try:
                field_type = getattr(self.instance.__class__, field).property
            except AttributeError:
                logger.error(f"No attribute: {field} in {self.instance.__class__}")
                continue
            match field_type:
                case _RelationshipDeclared():
                    # logger.debug(f"{field} is a relationship with {field_type.entity.class_}")
                    field_value = field_type.entity.class_.argument.query(name=getattr(self, field))
                    # logger.debug(f"{field} query result: {field_value}")
                case ColumnProperty():
                    # logger.debug(f"{field} is a property.")
                    field_value = getattr(self, field)
            self.instance.__setattr__(field, field_value)
        return self.instance


# NOTE: Generified objects below:

class PydProcedure(PydBaseClass, arbitrary_types_allowed=True):
    proceduretype: ProcedureType | None = Field(default=None)
    name: dict = Field(default=dict(value="NA", missing=True), validate_default=True)
    technician: dict = Field(default=dict(value="NA", missing=True))
    repeat: bool = Field(default=False)
    kittype: dict = Field(default=dict(value="NA", missing=True))
    possible_kits: list | None = Field(default=[], validate_default=True)
    plate_map: str | None = Field(default=None)
    reagent: list | None = Field(default=[])
    reagentrole: dict | None = Field(default={}, validate_default=True)

    @field_validator("name")
    @classmethod
    def rescue_name(cls, value, values):
        if value['value'] == cls.model_fields['name'].default['value']:
            if values.data['proceduretype']:
                value['value'] = values.data['proceduretype'].name
        return value

    @field_validator("possible_kits")
    @classmethod
    def rescue_possible_kits(cls, value, values):
        if not value:
            if values.data['proceduretype']:
                value = [kittype.name for kittype in values.data['proceduretype'].kittype]
        return value

    @field_validator("name", "technician", "kittype")
    @classmethod
    def set_colour(cls, value):
        if value["missing"]:
            value["colour"] = "FE441D"
        else:
            value["colour"] = "6ffe1d"
        return value

    @field_validator("reagentrole")
    @classmethod
    def rescue_reagentrole(cls, value, values):
        if not value:
            if values.data['kittype']['value'] != cls.model_fields['kittype'].default['value']:
                kittype = KitType.query(name=values.data['kittype']['value'])
                value = {item.name: item.reagents for item in kittype.reagentrole}
        return value

    def update_kittype_reagentroles(self, kittype: str | KitType):
        if kittype == self.__class__.model_fields['kittype'].default['value']:
            return
        if isinstance(kittype, str):
            kittype_obj = KitType.query(name=kittype)
        try:
            self.reagentrole = {item.name: item.reagents for item in
                                kittype_obj.get_reagents(proceduretype=self.proceduretype)}
        except AttributeError:
            self.reagentrole = {}
        self.possible_kits.insert(0, self.possible_kits.pop(self.possible_kits.index(kittype)))


class PydClientSubmission(PydBaseClass):
    # sql_object: ClassVar = ClientSubmission

    filepath: Path
    submissiontype: dict | None
    submitted_date: dict | None = Field(default=dict(value=date.today(), missing=True), validate_default=True)
    clientlab: dict | None
    sample_count: dict | None
    submission_category: dict | None = Field(default=dict(value=None, missing=True), validate_default=True)
    comment: dict | None = Field(default=dict(value="", missing=True), validate_default=True)
    cost_centre: dict | None = Field(default=dict(value=None, missing=True), validate_default=True)
    contact: dict | None = Field(default=dict(value=None, missing=True), validate_default=True)
    submitter_plate_id: dict | None = Field(default=dict(value=None, missing=True), validate_default=True)

    @field_validator("sample_count")
    @classmethod
    def enforce_integer(cls, value):
        try:
            value['value'] = int(value['value'])
        except ValueError:
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
        try:
            check = value['value'] is None
        except TypeError:
            check = True
        if check:
            return dict(value=date.today(), missing=True)
        else:
            match value['value']:
                case str():
                    value['value'] = datetime.strptime(value['value'], "%Y-%m-%d")
                    value['value'] = datetime.combine(value['value'], datetime.now().time())
                case _:
                    pass
        return value

    @field_validator("submission_category")
    @classmethod
    def enforce_typing(cls, value, values):
        if not value['value'] in ["Research", "Diagnostic", "Surveillance", "Validation"]:
            try:
                value['value'] = values.data['submissiontype']['value']
            except AttributeError:
                value['value'] = "NA"
        return value

    def to_form(self, parent: QWidget, samples: List = [], disable: list | None = None):
        """
        Converts this instance into a frontend.widgets.submission_widget.SubmissionFormWidget

        Args:
            samples ():
            disable (list, optional): a list of widgets to be disabled in the form. Defaults to None.
            parent (QWidget): parent widget of the constructed object

        Returns:
            SubmissionFormWidget: Submission form widget
        """
        from frontend.widgets.submission_widget import ClientSubmissionFormWidget
        return ClientSubmissionFormWidget(parent=parent, clientsubmission=self, samples=samples, disable=disable)
