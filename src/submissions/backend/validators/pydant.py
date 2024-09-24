'''
Contains pydantic models and accompanying validators
'''
from __future__ import annotations
import sys
import uuid, re, logging, csv
from pydantic import BaseModel, field_validator, Field, model_validator
from datetime import date, datetime, timedelta
from dateutil.parser import parse
from dateutil.parser import ParserError
from typing import List, Tuple, Literal
from . import RSLNamer
from pathlib import Path
from tools import check_not_nan, convert_nans_to_nones, Report, Result
from backend.db.models import *
from sqlalchemy.exc import StatementError, IntegrityError
from PyQt6.QtWidgets import QWidget

logger = logging.getLogger(f"submissions.{__name__}")


class PydReagent(BaseModel):
    lot: str | None
    role: str | None
    expiry: date | Literal['NA'] | None
    name: str | None
    missing: bool = Field(default=True)
    comment: str | None = Field(default="", validate_default=True)

    @field_validator('comment', mode='before')
    @classmethod
    def create_comment(cls, value):
        if value is None:
            return ""
        return value

    @field_validator("role", mode='before')
    @classmethod
    def remove_undesired_types(cls, value):
        match value:
            case "atcc":
                return None
            case _:
                return value

    @field_validator("role")
    @classmethod
    def rescue_type_with_lookup(cls, value, values):
        if value is None and values.data['lot'] is not None:
            try:
                # return lookup_reagents(ctx=values.data['ctx'], lot_number=values.data['lot']).name
                return Reagent.query(lot_number=values.data['lot'].name)
            except AttributeError:
                return value
        return value

    @field_validator("lot", mode='before')
    @classmethod
    def rescue_lot_string(cls, value):
        if value is not None:
            return convert_nans_to_nones(str(value))
        return value

    @field_validator("lot")
    @classmethod
    def enforce_lot_string(cls, value):
        if value is not None:
            return value.upper()
        return value

    @field_validator("expiry", mode="before")
    @classmethod
    def enforce_date(cls, value):
        if value is not None:
            match value:
                case int():
                    return datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value - 2).date()
                case 'NA':
                    return value
                case str():
                    return parse(value)
                case date():
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
            return convert_nans_to_nones(str(value))
        else:
            return values.data['role']

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

    def toSQL(self, submission: BasicSubmission | str = None) -> Tuple[Reagent, SubmissionReagentAssociation, Report]:
        """
        Converts this instance into a backend.db.models.kit.Reagent instance

        Returns:
            Tuple[Reagent, Report]: Reagent instance and result of function
        """
        report = Report()
        # logger.debug("Adding extra fields.")
        if self.model_extra is not None:
            self.__dict__.update(self.model_extra)
        # logger.debug(f"Reagent SQL constructor is looking up type: {self.type}, lot: {self.lot}")
        reagent = Reagent.query(lot_number=self.lot, name=self.name)
        # logger.debug(f"Result: {reagent}")
        if reagent is None:
            reagent = Reagent()
            for key, value in self.__dict__.items():
                if isinstance(value, dict):
                    value = value['value']
                # logger.debug(f"Reagent info item for {key}: {value}")
                # NOTE: set fields based on keys in dictionary
                match key:
                    case "lot":
                        reagent.lot = value.upper()
                    case "role":
                        reagent_role = ReagentRole.query(name=value)
                        if reagent_role is not None:
                            reagent.role.append(reagent_role)
                    case "comment":
                        continue
                    case "expiry":
                        if isinstance(value, str):
                            value = date(year=1970, month=1, day=1)
                        reagent.expiry = value
                    case _:
                        try:
                            reagent.__setattr__(key, value)
                        except AttributeError:
                            logger.error(f"Couldn't set {key} to {value}")
                if submission is not None and reagent not in submission.reagents:
                    assoc = SubmissionReagentAssociation(reagent=reagent, submission=submission)
                    assoc.comments = self.comment
                    # reagent.reagent_submission_associations.append(assoc)
                else:
                    assoc = None
            report.add_result(Result(owner=__name__, code=0, msg="New reagent created.", status="Information"))
        else:
            if submission is not None and reagent not in submission.reagents:
                assoc = SubmissionReagentAssociation(reagent=reagent, submission=submission)
                assoc.comments = self.comment
                # reagent.reagent_submission_associations.append(assoc)
            else:
                assoc = None
                # add end-of-life extension from reagent type to expiry date
                # NOTE: this will now be done only in the reporting phase to account for potential changes in end-of-life extensions
        return reagent, assoc, report


class PydSample(BaseModel, extra='allow'):
    submitter_id: str
    sample_type: str
    row: int | List[int] | None
    column: int | List[int] | None
    assoc_id: int | List[int | None] | None = Field(default=None, validate_default=True)
    submission_rank: int | List[int] | None = Field(default=0, validate_default=True)

    @model_validator(mode='after')
    @classmethod
    def validate_model(cls, data):
        # logger.debug(f"Data for pydsample: {data}")
        model = BasicSample.find_polymorphic_subclass(polymorphic_identity=data.sample_type)
        for k, v in data.model_extra.items():
            # print(k, v)
            if k in model.timestamps():
                if isinstance(v, str):
                    v = datetime.strptime(v, "%Y-%m-%d")
                data.__setattr__(k, v)
                # print(dir(data))
        # logger.debug(f"Data coming out of validation: {pformat(data)}")
        return data

    @field_validator("row", "column", "assoc_id", "submission_rank")
    @classmethod
    def row_int_to_list(cls, value):
        match value:
            case int() | None:
                return [value]
            case _:
                return value

    @field_validator("submitter_id", mode="before")
    @classmethod
    def int_to_str(cls, value):
        return str(value)

    def improved_dict(self) -> dict:
        """
        Constructs a dictionary consisting of model.fields and model.extras

        Returns:
            dict: Information dictionary
        """
        fields = list(self.model_fields.keys()) + list(self.model_extra.keys())
        return {k: getattr(self, k) for k in fields}

    def toSQL(self, submission: BasicSubmission | str = None) -> Tuple[BasicSample, Result]:
        """
        Converts this instance into a backend.db.models.submissions.Sample object

        Args:
            submission (BasicSubmission | str, optional): Submission joined to this sample. Defaults to None.

        Returns:
            Tuple[BasicSample, Result]: Sample object and result object.
        """
        report = None
        self.__dict__.update(self.model_extra)
        # logger.debug(f"Here is the incoming sample dict: \n{self.__dict__}")
        instance = BasicSample.query_or_create(sample_type=self.sample_type, submitter_id=self.submitter_id)
        for key, value in self.__dict__.items():
            match key:
                case "row" | "column":
                    continue
                case _:
                    # logger.debug(f"Setting sample field {key} to {value}")
                    instance.__setattr__(key, value)
        out_associations = []
        if submission is not None:
            if isinstance(submission, str):
                submission = BasicSubmission.query(rsl_plate_num=submission)
            assoc_type = submission.submission_type_name
            for row, column, aid, submission_rank in zip(self.row, self.column, self.assoc_id, self.submission_rank):
                # logger.debug(f"Looking up association with identity: ({submission.submission_type_name} Association)")
                # logger.debug(f"Looking up association with identity: ({assoc_type} Association)")
                association = SubmissionSampleAssociation.query_or_create(association_type=f"{assoc_type} Association",
                                                                          submission=submission,
                                                                          sample=instance,
                                                                          row=row, column=column, id=aid,
                                                                          submission_rank=submission_rank,
                                                                          **self.model_extra)
                # logger.debug(f"Using submission_sample_association: {association}")
                try:
                    # instance.sample_submission_associations.append(association)
                    out_associations.append(association)
                except IntegrityError as e:
                    logger.error(f"Could not attach submission sample association due to: {e}")
                    instance.metadata.session.rollback()
        return instance, out_associations, report

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


class PydTips(BaseModel):
    name: str
    lot: str | None = Field(default=None)
    role: str

    def to_sql(self, submission: BasicSubmission) -> SubmissionTipsAssociation:
        """
        Con

        Args:
            submission (BasicSubmission): A submission object to associate tips represented here.

        Returns:
            SubmissionTipsAssociation: Association between queried tips and submission
        """
        tips = Tips.query(name=self.name, lot=self.lot, limit=1)
        assoc = SubmissionTipsAssociation.query(tip_id=tips.id, submission_id=submission.id, role=self.role, limit=1)
        if assoc is None:
            assoc = SubmissionTipsAssociation(submission=submission, tips=tips, role_name=self.role)
        return assoc


class PydEquipment(BaseModel, extra='ignore'):
    asset_number: str
    name: str
    nickname: str | None
    processes: List[str] | None
    role: str | None
    tips: List[PydTips] | None = Field(default=None)

    @field_validator('processes', mode='before')
    @classmethod
    def make_empty_list(cls, value):
        # logger.debug(f"Pydantic value: {value}")
        value = convert_nans_to_nones(value)
        if value is None:
            value = ['']
        if len(value) == 0:
            value = ['']
        try:
            value = [item.strip() for item in value]
        except AttributeError:
            pass
        return value

    def toSQL(self, submission: BasicSubmission | str = None) -> Tuple[Equipment, SubmissionEquipmentAssociation]:
        """
        Creates Equipment and SubmssionEquipmentAssociations for this PydEquipment

        Args:
            submission ( BasicSubmission | str ): BasicSubmission of interest

        Returns:
            Tuple[Equipment, SubmissionEquipmentAssociation]: SQL objects
        """
        if isinstance(submission, str):
            logger.info(f"Got string, querying {submission}")
            submission = BasicSubmission.query(rsl_number=submission)
        equipment = Equipment.query(asset_number=self.asset_number)
        if equipment is None:
            logger.error("No equipment found. Returning None.")
            return
        if submission is not None:
            # NOTE: Need to make sure the same association is not added to the submission
            try:
                assoc = SubmissionEquipmentAssociation.query(equipment_id=equipment.id, submission_id=submission.id,
                                                         role=self.role, limit=1)
            except TypeError as e:
                logger.error(f"Couldn't get association due to {e}, returning...")
                return equipment, None
            if assoc is None:
                assoc = SubmissionEquipmentAssociation(submission=submission, equipment=equipment)
                process = Process.query(name=self.processes[0])
                if process is None:
                    logger.error(f"Found unknown process: {process}.")
                assoc.process = process
                assoc.role = self.role
            else:
                logger.warning(f"Found already existing association: {assoc}")
                assoc = None
        else:
            logger.warning(f"No submission found")
            assoc = None
        return equipment, assoc

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
    submission_type: dict | None
    # For defaults
    submitter_plate_num: dict | None = Field(default=dict(value=None, missing=True), validate_default=True)
    submitted_date: dict | None
    rsl_plate_num: dict | None = Field(default=dict(value=None, missing=True), validate_default=True)
    submitted_date: dict | None = Field(default=dict(value=date.today(), missing=True), validate_default=True)
    submitting_lab: dict | None
    sample_count: dict | None
    extraction_kit: dict | None
    technician: dict | None
    submission_category: dict | None = Field(default=dict(value=None, missing=True), validate_default=True)
    comment: dict | None = Field(default=dict(value="", missing=True), validate_default=True)
    reagents: List[dict] | List[PydReagent] = []
    samples: List[PydSample]
    equipment: List[PydEquipment] | None = []
    cost_centre: dict | None = Field(default=dict(value=None, missing=True), validate_default=True)
    contact: dict | None = Field(default=dict(value=None, missing=True), validate_default=True)

    @field_validator('equipment', mode='before')
    @classmethod
    def convert_equipment_dict(cls, value):
        # logger.debug(f"Equipment: {value}")

        if isinstance(value, dict):
            return value['value']
        return value

    @field_validator('comment', mode='before')
    @classmethod
    def create_comment(cls, value):
        if value is None:
            return ""
        return value

    @field_validator("submitter_plate_num")
    @classmethod
    def enforce_with_uuid(cls, value):
        # logger.debug(f"submitter_plate_num coming into pydantic: {value}")
        if value['value'] in [None, "None"]:
            return dict(value=uuid.uuid4().hex.upper(), missing=True)
        else:
            return value

    @field_validator("submitted_date", mode="before")
    @classmethod
    def rescue_date(cls, value):
        # logger.debug(f"\n\nDate coming into pydantic: {value}\n\n")
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
                return value
            case datetime():
                return value.date()
            case int():
                return dict(value=datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value['value'] - 2).date(),
                            missing=True)
            case str():
                string = re.sub(r"(_|-)\d$", "", value['value'])
                try:
                    output = dict(value=parse(string).date(), missing=True)
                except ParserError as e:
                    logger.error(f"Problem parsing date: {e}")
                    try:
                        output = dict(value=parse(string.replace("-", "")).date(), missing=True)
                    except Exception as e:
                        logger.error(f"Problem with parse fallback: {e}")
                return output
            case _:
                raise ValueError(f"Could not get datetime from {value['value']}")

    @field_validator("submitting_lab", mode="before")
    @classmethod
    def rescue_submitting_lab(cls, value):
        if value is None:
            return dict(value=None, missing=True)
        return value

    @field_validator("submitting_lab")
    @classmethod
    def lookup_submitting_lab(cls, value):
        if isinstance(value['value'], str):
            # logger.debug(f"Looking up organization {value['value']}")
            try:
                value['value'] = Organization.query(name=value['value']).name
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
                                 obj_type=Organization)

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
        # logger.debug(f"RSL-plate initial value: {value['value']} and other values: {values.data}")
        sub_type = values.data['submission_type']['value']
        if check_not_nan(value['value']):
            return value
        else:
            # logger.debug("Constructing plate sub_type.")
            if "pytest" in sys.modules and sub_type.replace(" ", "") == "BasicSubmission":
                output = "RSL-BS-Test001"
            else:
                output = RSLNamer(filename=values.data['filepath'].__str__(), sub_type=sub_type,
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

    @field_validator("extraction_kit", mode='before')
    @classmethod
    def rescue_kit(cls, value):
        if check_not_nan(value):
            if isinstance(value, str):
                return dict(value=value, missing=False)
            elif isinstance(value, dict):
                return value
        else:
            raise ValueError(f"No extraction kit found.")
        if value is None:
            return dict(value=None, missing=True)
        return value

    @field_validator("submission_type", mode='before')
    @classmethod
    def make_submission_type(cls, value, values):
        if not isinstance(value, dict):
            value = {"value": value}
        if check_not_nan(value['value']):
            value = value['value'].title()
            return dict(value=value, missing=False)
        else:
            # return dict(value=RSLNamer(instr=values.data['filepath'].__str__()).submission_type.title(), missing=True)
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
        if value['value'] not in ["Research", "Diagnostic", "Surveillance", "Validation"]:
            value['value'] = values.data['submission_type']['value']
        return value

    @field_validator("samples")
    @classmethod
    def assign_ids(cls, value, values):
        starting_id = SubmissionSampleAssociation.autoincrement_id()
        output = []
        for iii, sample in enumerate(value, start=starting_id):
            sample.assoc_id = [iii]
            output.append(sample)
        return output

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
        # logger.debug(f"Value coming in for cost_centre: {value}")
        match value['value']:
            case None:
                from backend.db.models import Organization
                org = Organization.query(name=values.data['submitting_lab']['value'])
                try:
                    return dict(value=org.cost_centre, missing=True)
                except AttributeError:
                    return dict(value="xxx", missing=True)
            case _:
                return value

    @field_validator("contact")
    @classmethod
    def get_contact_from_org(cls, value, values):
        # logger.debug(f"Checking on value: {value}")
        match value:
            case dict():
                if isinstance(value['value'], tuple):
                    value['value'] = value['value'][0]
            case tuple():
                value = dict(value=value[0], missing=False)
            case _:
                value = dict(value=value, missing=False)
        check = Contact.query(name=value['value'])
        if check is None:
            org = Organization.query(name=values.data['submitting_lab']['value'])
            contact = org.contacts[0].name
            # logger.debug(f"Pulled: {contact}")
            if isinstance(contact, tuple):
                contact = contact[0]
            return dict(value=contact, missing=True)
        else:
            return value

    def __init__(self, **data):
        super().__init__(**data)
        # this could also be done with default_factory
        self.submission_object = BasicSubmission.find_polymorphic_subclass(
            polymorphic_identity=self.submission_type['value'])
        self.namer = RSLNamer(self.rsl_plate_num['value'], sub_type=self.submission_type['value'])

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
        Collapses multiple samples with same submitter id into one with lists for rows, columns.
        Necessary to prevent trying to create duplicate samples in SQL creation.
        """
        submitter_ids = list(set([sample.submitter_id for sample in self.samples]))
        output = []
        for id in submitter_ids:
            relevants = [item for item in self.samples if item.submitter_id == id]
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

    # TODO: Return samples, reagents, etc to dictionaries as well.
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
            output['samples'] = [item.improved_dict() for item in self.samples]
            try:
                output['equipment'] = [item.improved_dict() for item in self.equipment]
            except TypeError:
                pass
        else:
            # logger.debug("Extracting 'value' from attributes")
            output = {k: (getattr(self, k) if not isinstance(getattr(self, k), dict) else getattr(self, k)['value']) for
                      k in fields}

        return output

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

    def to_sql(self) -> Tuple[BasicSubmission, Report]:
        """
        Converts this instance into a backend.db.models.submissions.BasicSubmission instance

        Returns:
            Tuple[BasicSubmission, Result]: BasicSubmission instance, result object
        """
        # self.__dict__.update(self.model_extra)
        report = Report()
        dicto = self.improved_dict()
        instance, result = BasicSubmission.query_or_create(submission_type=self.submission_type['value'],
                                                           rsl_plate_num=self.rsl_plate_num['value'])
        report.add_result(result)
        self.handle_duplicate_samples()
        # logger.debug(f"Here's our list of duplicate removed samples: {self.samples}")
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
            # logger.debug(f"Setting {key} to {value}")
            match key:
                # case "custom":
                #     instance.custom = value
                case "reagents":
                    if report.results[0].code == 1:
                        instance.submission_reagent_associations = []
                    # logger.debug(f"Looking through {self.reagents}")
                    for reagent in self.reagents:
                        reagent, assoc, _ = reagent.toSQL(submission=instance)
                        # logger.debug(f"Association: {assoc}")
                        if assoc is not None:  # and assoc not in instance.submission_reagent_associations:
                            instance.submission_reagent_associations.append(assoc)
                        # instance.reagents.append(reagent)
                case "samples":
                    for sample in self.samples:
                        sample, associations, _ = sample.toSQL(submission=instance)
                        # logger.debug(f"Sample SQL object to be added to submission: {sample.__dict__}")
                        for assoc in associations:
                            if assoc is not None and assoc not in instance.submission_sample_associations:
                                instance.submission_sample_associations.append(assoc)
                case "equipment":
                    # logger.debug(f"Equipment: {pformat(self.equipment)}")
                    for equip in self.equipment:
                        if equip is None:
                            continue
                        equip, association = equip.toSQL(submission=instance)
                        if association is not None:
                            instance.submission_equipment_associations.append(association)
                case "tips":
                    for tips in self.tips:
                        if tips is None:
                            continue
                        # logger.debug(f"Converting tips: {tips} to sql.")
                        try:
                            association = tips.to_sql(submission=instance)
                        except AttributeError:
                            continue
                        if association is not None and association not in instance.submission_tips_associations:
                            # association.save()
                            instance.submission_tips_associations.append(association)
                case item if item in instance.jsons():
                    # logger.debug(f"{item} is a json.")
                    try:
                        ii = value.items()
                    except AttributeError:
                        ii = {}
                    logger.debug(f"ii is {ii}, value is {value}")
                    for k, v in ii:
                        logger.debug(f"k is {k}, v is {v}")
                        if isinstance(v, datetime):
                            value[k] = v.strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            value[k] = v
                    instance.set_attribute(key=key, value=value)
                case _:
                    try:
                        instance.set_attribute(key=key, value=value)
                    except AttributeError as e:
                        logger.error(f"Could not set attribute: {key} to {value} due to: \n\n {e}")
                        continue
                    except KeyError:
                        continue
        try:
            # logger.debug(f"Calculating costs for procedure...")
            instance.calculate_base_cost()
        except (TypeError, AttributeError) as e:
            # logger.debug(f"Looks like that kit doesn't have cost breakdown yet due to: {e}, using full plate cost.")
            try:
                instance.run_cost = instance.extraction_kit.cost_per_run
            except AttributeError:
                instance.run_cost = 0
        # logger.debug(f"Calculated base run cost of: {instance.run_cost}")
        # NOTE: Apply any discounts that are applicable for client and kit.
        try:
            # logger.debug("Checking and applying discounts...")
            discounts = [item.amount for item in
                         Discount.query(kit_type=instance.extraction_kit, organization=instance.submitting_lab)]
            # logger.debug(f"We got discounts: {discounts}")
            if len(discounts) > 0:
                instance.run_cost = instance.run_cost - sum(discounts)
        except Exception as e:
            logger.error(f"An unknown exception occurred when calculating discounts: {e}")
        # We need to make sure there's a proper rsl plate number
        # logger.debug(f"We've got a total cost of {instance.run_cost}")
        # try:
        #     logger.debug(f"Constructed instance: {instance}")
        # except AttributeError as e:
        #     logger.debug(f"Something went wrong constructing instance {self.rsl_plate_num}: {e}")
        # logger.debug(f"Constructed submissions message: {msg}")
        return instance, report

    def to_form(self, parent: QWidget, disable:list|None=None):
        """
        Converts this instance into a frontend.widgets.submission_widget.SubmissionFormWidget

        Args:
            parent (QWidget): parent widget of the constructed object

        Returns:
            SubmissionFormWidget: Submission form widget
        """
        from frontend.widgets.submission_widget import SubmissionFormWidget
        # logger.debug(f"Disable: {disable}")
        return SubmissionFormWidget(parent=parent, submission=self, disable=disable)

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
        # logger.debug(f"Using template string: {template}")
        render = self.namer.construct_export_name(template=template, **self.improved_dict(dictionaries=False)).replace(
            "/", "")
        # logger.debug(f"Template rendered as: {render}")
        return render

    # @report_result
    def check_kit_integrity(self, extraction_kit: str | dict | None = None) -> Tuple[List[PydReagent], Report]:
        """
        Ensures all reagents expected in kit are listed in Submission
       
        Args:
            reagenttypes (list | None, optional): List to check against complete list. Defaults to None.

        Returns:
            Report: Result object containing a message and any missing components.
        """
        report = Report()
        # logger.debug(f"Extraction kit: {extraction_kit}. Is it a string? {isinstance(extraction_kit, str)}")
        if isinstance(extraction_kit, str):
            extraction_kit = dict(value=extraction_kit)
        if extraction_kit is not None and extraction_kit != self.extraction_kit['value']:
            self.extraction_kit['value'] = extraction_kit['value']
        # logger.debug(f"Looking up {self.extraction_kit['value']}")
        ext_kit = KitType.query(name=self.extraction_kit['value'])
        ext_kit_rtypes = [item.to_pydantic() for item in
                          ext_kit.get_reagents(required=True, submission_type=self.submission_type['value'])]
        # logger.debug(f"Kit reagents: {ext_kit_rtypes}")
        # logger.debug(f"Submission reagents: {self.reagents}")
        # NOTE: Exclude any reagenttype found in this pyd not expected in kit.
        expected_check = [item.role for item in ext_kit_rtypes]
        output_reagents = [rt for rt in self.reagents if rt.role in expected_check]
        # logger.debug(f"Already have these reagent types: {output_reagents}")
        missing_check = [item.role for item in output_reagents]
        missing_reagents = [rt for rt in ext_kit_rtypes if rt.role not in missing_check]
        missing_reagents += [rt for rt in output_reagents if rt.missing]
        output_reagents += [rt for rt in missing_reagents if rt not in output_reagents]
        # logger.debug(f"Missing reagents types: {missing_reagents}")
        # NOTE: if lists are equal return no problem
        if len(missing_reagents) == 0:
            result = None
        else:
            result = Result(
                msg=f"The excel sheet you are importing is missing some reagents expected by the kit.\n\nIt looks like you are missing: {[item.role.upper() for item in missing_reagents]}\n\nAlternatively, you may have set the wrong extraction kit.\n\nThe program will populate lists using existing reagents.\n\nPlease make sure you check the lots carefully!",
                status="Warning")
        report.add_result(result)
        return output_reagents, report

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


class PydContact(BaseModel):
    name: str
    phone: str | None
    email: str | None

    def toSQL(self) -> Contact:
        """
        Converts this instance into a backend.db.models.organization.Contact instance

        Returns:
            Contact: Contact instance
        """
        return Contact(name=self.name, phone=self.phone, email=self.email)


class PydOrganization(BaseModel):
    name: str
    cost_centre: str
    contacts: List[PydContact] | None

    def toSQL(self) -> Organization:
        """
        Converts this instance into a backend.db.models.organization.Organization instance.

        Returns:
           Organization: Organization instance
        """
        instance = Organization()
        for field in self.model_fields:
            match field:
                case "contacts":
                    value = [item.to_sql() for item in getattr(self, field)]
                case _:
                    value = getattr(self, field)
            # instance.set_attribute(name=field, value=value)
            instance.__setattr__(name=field, value=value)
        return instance


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

    def toSQL(self, kit: KitType) -> ReagentRole:
        """
        Converts this instance into a backend.db.models.ReagentType instance

        Args:
            kit (KitType): KitType joined to the reagentrole

        Returns:
            ReagentRole: ReagentType instance
        """
        instance: ReagentRole = ReagentRole.query(name=self.name)
        if instance is None:
            instance = ReagentRole(name=self.name, eol_ext=self.eol_ext)
        # logger.debug(f"This is the reagent type instance: {instance.__dict__}")
        try:
            assoc = KitTypeReagentRoleAssociation.query(reagent_role=instance, kit_type=kit)
        except StatementError:
            assoc = None
        if assoc is None:
            assoc = KitTypeReagentRoleAssociation(kit_type=kit, reagent_role=instance, uses=self.uses,
                                                  required=self.required)
        return instance


class PydKit(BaseModel):
    name: str
    reagent_roles: List[PydReagentRole] = []

    def toSQL(self) -> Tuple[KitType, Report]:
        """
        Converts this instance into a backend.db.models.kits.KitType instance

        Returns:
            Tuple[KitType, Report]: KitType instance and report of results.
        """
        report = Report()
        instance = KitType.query(name=self.name)
        if instance is None:
            instance = KitType(name=self.name)
            [item.toSQL(instance) for item in self.reagent_roles]
        return instance, report


class PydEquipmentRole(BaseModel):
    name: str
    equipment: List[PydEquipment]
    processes: List[str] | None

    def to_form(self, parent, used: list) -> "RoleComboBox":
        """
        Creates a widget for user input into this class.

        Args:
            parent (_type_): parent widget
            used (list): list of equipment already added to submission

        Returns:
            RoleComboBox: widget
        """
        from frontend.widgets.equipment_usage import RoleComboBox
        return RoleComboBox(parent=parent, role=self, used=used)
