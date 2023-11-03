'''
Contains pydantic models and accompanying validators
'''
import uuid
from pydantic import BaseModel, field_validator, Field
from datetime import date, datetime, timedelta
from dateutil.parser import parse
from dateutil.parser._parser import ParserError
from typing import List, Any, Tuple
from . import RSLNamer
from pathlib import Path
import re
import logging
from tools import check_not_nan, convert_nans_to_nones, Settings, jinja_template_loading
from backend.db.models import *
from sqlalchemy.exc import InvalidRequestError, StatementError
from PyQt6.QtWidgets import QComboBox, QWidget
from pprint import pformat
from openpyxl import load_workbook

logger = logging.getLogger(f"submissions.{__name__}")

class PydReagent(BaseModel):
    ctx: Settings
    lot: str|None
    type: str|None
    expiry: date|None
    name: str|None
    missing: bool = Field(default=True)

    @field_validator("type", mode='before')
    @classmethod
    def remove_undesired_types(cls, value):
        match value:
            case "atcc":
                return None
            case _:
                return value
            
    @field_validator("type")
    @classmethod
    def rescue_type_with_lookup(cls, value, values):
        if value == None and values.data['lot'] != None:
            try:
                # return lookup_reagents(ctx=values.data['ctx'], lot_number=values.data['lot']).name
                return Reagent.query(lot_number=values.data['lot'].name)
            except AttributeError:
                return value
        return value

    @field_validator("lot", mode='before')
    @classmethod
    def rescue_lot_string(cls, value):
        if value != None:
            return convert_nans_to_nones(str(value))
        return value
    
    @field_validator("lot")
    @classmethod
    def enforce_lot_string(cls, value):
        if value != None:
            return value.upper()
        return value
            
    @field_validator("expiry", mode="before")
    @classmethod
    def enforce_date(cls, value):
        if value != None:
            match value:
                case int():
                    return datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value - 2).date()
                case str():
                    return parse(value)
                case date():
                    return value
                case _:
                    return convert_nans_to_nones(str(value))
        if value == None:
            value = date.today()
        return value
    
    @field_validator("name", mode="before")
    @classmethod
    def enforce_name(cls, value, values):
        if value != None:
            return convert_nans_to_nones(str(value))
        else:
            return values.data['type']

    def toSQL(self) -> Tuple[Reagent, dict]:
        result = None
        logger.debug(f"Reagent SQL constructor is looking up type: {self.type}, lot: {self.lot}")
        # reagent = lookup_reagents(ctx=self.ctx, lot_number=self.lot)
        reagent = Reagent.query(lot_number=self.lot)
        logger.debug(f"Result: {reagent}")
        if reagent == None:
            reagent = Reagent()
            for key, value in self.__dict__.items():
                if isinstance(value, dict):
                    value = value['value']
                logger.debug(f"Reagent info item for {key}: {value}")
                # set fields based on keys in dictionary
                match key:
                    case "lot":
                        reagent.lot = value.upper()
                    case "expiry":
                        reagent.expiry = value
                    case "type":
                        # reagent_type = lookup_reagent_types(ctx=self.ctx, name=value)
                        reagent_type = ReagentType.query(name=value)
                        if reagent_type != None:
                            reagent.type.append(reagent_type)
                    case "name":
                        reagent.name = value
            # add end-of-life extension from reagent type to expiry date
            # NOTE: this will now be done only in the reporting phase to account for potential changes in end-of-life extensions
        return reagent, result

    def toForm(self, parent:QWidget, extraction_kit:str) -> QComboBox:
        from frontend.custom_widgets.misc import ReagentFormWidget
        return ReagentFormWidget(parent=parent, reagent=self, extraction_kit=extraction_kit)
    
class PydSample(BaseModel, extra='allow'):

    submitter_id: str
    sample_type: str
    row: int|List[int]|None
    column: int|List[int]|None

    @field_validator("row", "column")
    @classmethod
    def row_int_to_list(cls, value):
        if isinstance(value, int):
            return [value]
        return value
    
    @field_validator("submitter_id", mode="before")
    @classmethod
    def int_to_str(cls, value):
        return str(value)
    
    def toSQL(self, ctx:Settings, submission):
        result = None
        self.__dict__.update(self.model_extra)
        logger.debug(f"Here is the incoming sample dict: \n{self.__dict__}")
        # instance = lookup_samples(ctx=ctx, submitter_id=self.submitter_id)
        instance = BasicSample.query(submitter_id=self.submitter_id)
        if instance == None:
            logger.debug(f"Sample {self.submitter_id} doesn't exist yet. Looking up sample object with polymorphic identity: {self.sample_type}")
            instance = BasicSample.find_polymorphic_subclass(polymorphic_identity=self.sample_type)()
        for key, value in self.__dict__.items():
            # logger.debug(f"Setting sample field {key} to {value}")
            match key:
                case "row" | "column":
                    continue
                case _:
                    instance.set_attribute(name=key, value=value)
        for row, column in zip(self.row, self.column):
            logger.debug(f"Looking up association with identity: ({submission.submission_type_name} Association)")
            # association = lookup_submission_sample_association(ctx=ctx, submission=submission, row=row, column=column)
            association = SubmissionSampleAssociation.query(submission=submission, row=row, column=column)
            logger.debug(f"Returned association: {association}")
            if association == None or association == []:
                logger.debug(f"Looked up association at row {row}, column {column} didn't exist, creating new association.")
                association = SubmissionSampleAssociation.find_polymorphic_subclass(polymorphic_identity=f"{submission.submission_type_name} Association")
                association = association(submission=submission, sample=instance, row=row, column=column)
                instance.sample_submission_associations.append(association)
        return instance, result

class PydSubmission(BaseModel, extra='allow'):
    ctx: Settings
    filepath: Path
    submission_type: dict|None
    # For defaults
    submitter_plate_num: dict|None = Field(default=dict(value=None, missing=True), validate_default=True)
    rsl_plate_num: dict|None = Field(default=dict(value=None, missing=True), validate_default=True)
    submitted_date: dict|None
    submitting_lab: dict|None
    sample_count: dict|None
    extraction_kit: dict|None
    technician: dict|None
    submission_category: dict|None = Field(default=dict(value=None, missing=True), validate_default=True)
    reagents: List[dict]|List[PydReagent] = []
    samples: List[Any]

    @field_validator("submitter_plate_num")
    @classmethod
    def enforce_with_uuid(cls, value):
        logger.debug(f"submitter plate id: {value}")
        if value['value'] == None or value['value'] == "None":
            return dict(value=uuid.uuid4().hex.upper(), missing=True)
        else:
            return value
    
    @field_validator("submitted_date", mode="before")
    @classmethod
    def rescue_date(cls, value):
        if value == None:
            return dict(value=date.today(), missing=True)
        return value

    @field_validator("submitted_date")
    @classmethod
    def strip_datetime_string(cls, value):
        if isinstance(value['value'], datetime):
            return value
        if isinstance(value['value'], date):
            return value
        if isinstance(value['value'], int):
            return dict(value=datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value['value'] - 2).date(), missing=True)
        string = re.sub(r"(_|-)\d$", "", value['value'])
        try:
            output = dict(value=parse(string).date(), missing=True)
        except ParserError as e:
            logger.error(f"Problem parsing date: {e}")
            try:
                output = dict(value=parse(string.replace("-","")).date(), missing=True)
            except Exception as e:
                logger.error(f"Problem with parse fallback: {e}")
        return output
        
    @field_validator("submitting_lab", mode="before")
    @classmethod
    def rescue_submitting_lab(cls, value):
        if value == None:
            return dict(value=None, missing=True)
        return value

    @field_validator("rsl_plate_num", mode='before')
    @classmethod
    def rescue_rsl_number(cls, value):
        if value == None:
            return dict(value=None, missing=True)
        return value

    @field_validator("rsl_plate_num")
    @classmethod
    def rsl_from_file(cls, value, values):
        logger.debug(f"RSL-plate initial value: {value['value']}")
        sub_type = values.data['submission_type']['value']
        if check_not_nan(value['value']):
            # if lookup_submissions(ctx=values.data['ctx'], rsl_number=value['value']) == None:
            if BasicSubmission.query(rsl_number=value['value']) == None:
                return dict(value=value['value'], missing=False)
            else:
                logger.warning(f"Submission number {value} already exists in DB, attempting salvage with filepath")
                # output = RSLNamer(ctx=values.data['ctx'], instr=values.data['filepath'].__str__(), sub_type=sub_type).parsed_name
                output = RSLNamer(ctx=values.data['ctx'], instr=values.data['filepath'].__str__(), sub_type=sub_type).parsed_name
                return dict(value=output, missing=True)
        else:
            output = RSLNamer(ctx=values.data['ctx'], instr=values.data['filepath'].__str__(), sub_type=sub_type).parsed_name
            return dict(value=output, missing=True)

    @field_validator("technician", mode="before")
    @classmethod
    def rescue_tech(cls, value):
        if value == None:
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
        return value
    
    @field_validator("sample_count", mode='before')
    @classmethod
    def rescue_sample_count(cls, value):
        if value == None:
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
        if value == None:
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
        # else:
        #     return dict(value="RSL Name not found.")
        else:
            return dict(value=RSLNamer(ctx=values.data['ctx'], instr=values.data['filepath'].__str__()).submission_type.title(), missing=True)
        
    @field_validator("submission_category")
    @classmethod
    def rescue_category(cls, value, values):
        if value['value'] not in ["Research", "Diagnostic", "Surveillance"]:
            value['value'] = values.data['submission_type']['value']
        return value

    def handle_duplicate_samples(self):
        submitter_ids = list(set([sample.submitter_id for sample in self.samples]))
        output = []
        for id in submitter_ids:
            relevants = [item for item in self.samples if item.submitter_id==id]
            if len(relevants) <= 1:
                output += relevants
            else:
                rows = [item.row[0] for item in relevants]
                columns = [item.column[0] for item in relevants]
                dummy = relevants[0]
                dummy.row = rows
                dummy.column = columns
                output.append(dummy)
        self.samples = output

    def improved_dict(self, dictionaries:bool=True):
        fields = list(self.model_fields.keys()) + list(self.model_extra.keys())
        if dictionaries:
            output = {k:getattr(self, k) for k in fields}
        else:
            output = {k:(getattr(self, k) if not isinstance(getattr(self, k), dict) else getattr(self, k)['value']) for k in fields}
        return output

    def find_missing(self):
        info = {k:v for k,v in self.improved_dict().items() if isinstance(v, dict)}
        missing_info = {k:v for k,v in info.items() if v['missing']}
        missing_reagents = [reagent for reagent in self.reagents if reagent.missing]
        return missing_info, missing_reagents

    def toSQL(self):
        code = 0
        msg = None
        status = None
        self.__dict__.update(self.model_extra)
        # instance = lookup_submissions(ctx=self.ctx, rsl_number=self.rsl_plate_num['value'])
        instance = BasicSubmission.query(rsl_number=self.rsl_plate_num['value'])
        if instance == None:
            instance = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=self.submission_type)()
        else:
            code = 1
            msg = "This submission already exists.\nWould you like to overwrite?"
        self.handle_duplicate_samples()
        logger.debug(f"Here's our list of duplicate removed samples: {self.samples}")
        for key, value in self.__dict__.items():
            if isinstance(value, dict):
                value = value['value']
            logger.debug(f"Setting {key} to {value}")
            # set fields based on keys in dictionary
            match key:
                case "extraction_kit":
                    logger.debug(f"Looking up kit {value}")
                    # field_value = lookup_kit_types(ctx=self.ctx, name=value)
                    field_value = KitType.query(name=value)
                    logger.debug(f"Got {field_value} for kit {value}")
                case "submitting_lab":
                    logger.debug(f"Looking up organization: {value}")
                    # field_value = lookup_organizations(ctx=self.ctx, name=value)
                    field_value = Organization.query(name=value)
                    logger.debug(f"Got {field_value} for organization {value}")
                case "submitter_plate_num":
                    logger.debug(f"Submitter plate id: {value}")
                    field_value = value
                case "samples":
                    # instance = construct_samples(ctx=ctx, instance=instance, samples=value)
                    for sample in value:
                        # logger.debug(f"Parsing {sample} to sql.")
                        sample, _ = sample.toSQL(ctx=self.ctx, submission=instance)
                        # instance.samples.append(sample)
                    continue
                case "reagents":
                    field_value = [reagent['value'].toSQL()[0] if isinstance(reagent, dict) else reagent.toSQL()[0] for reagent in value]
                case "submission_type":
                    # field_value = lookup_submission_type(ctx=self.ctx, name=value)
                    field_value = SubmissionType.query(name=value)
                case "sample_count":
                    if value == None:
                        field_value = len(self.samples)
                    else:
                        field_value = value
                case "ctx" | "csv" | "filepath":
                    continue
                case _:
                    field_value = value
            # insert into field
            try:
                setattr(instance, key, field_value)
            except AttributeError as e:
                logger.debug(f"Could not set attribute: {key} to {value} due to: \n\n {e}")
                continue
            except KeyError:
                continue
        try:
            logger.debug(f"Calculating costs for procedure...")
            instance.calculate_base_cost()
        except (TypeError, AttributeError) as e:
            logger.debug(f"Looks like that kit doesn't have cost breakdown yet due to: {e}, using full plate cost.")
            instance.run_cost = instance.extraction_kit.cost_per_run
        logger.debug(f"Calculated base run cost of: {instance.run_cost}")
        # Apply any discounts that are applicable for client and kit.
        try:
            logger.debug("Checking and applying discounts...")
            # discounts = [item.amount for item in lookup_discounts(ctx=self.ctx, kit_type=instance.extraction_kit, organization=instance.submitting_lab)]
            discounts = [item.amount for item in Discount.query(kit_type=instance.extraction_kit, organization=instance.submitting_lab)]
            logger.debug(f"We got discounts: {discounts}")
            if len(discounts) > 0:
                discounts = sum(discounts)
                instance.run_cost = instance.run_cost - discounts
        except Exception as e:
            logger.error(f"An unknown exception occurred when calculating discounts: {e}")
        # We need to make sure there's a proper rsl plate number
        logger.debug(f"We've got a total cost of {instance.run_cost}")
        try:
            logger.debug(f"Constructed instance: {instance.to_string()}")
        except AttributeError as e:
            logger.debug(f"Something went wrong constructing instance {self.rsl_plate_num}: {e}")
        logger.debug(f"Constructed submissions message: {msg}")
        return instance, {'code':code, 'message':msg, 'status':"Information"}
    
    def toForm(self, parent:QWidget):
        from frontend.custom_widgets.misc import SubmissionFormWidget
        return SubmissionFormWidget(parent=parent, **self.improved_dict())

    def autofill_excel(self, missing_only:bool=True):
        if missing_only:
            info, reagents = self.find_missing()
        else:
            info = {k:v for k,v in self.improved_dict().items() if isinstance(v, dict)}
            reagents = self.reagents
        if len(reagents + list(info.keys())) == 0:
            return None
        logger.debug(f"We have blank info and/or reagents in the excel sheet.\n\tLet's try to fill them in.")
        # extraction_kit = lookup_kit_types(ctx=self.ctx, name=self.extraction_kit['value'])
        extraction_kit = KitType.query(name=self.extraction_kit['value'])
        logger.debug(f"We have the extraction kit: {extraction_kit.name}")
        excel_map = extraction_kit.construct_xl_map_for_use(self.submission_type['value'])
        logger.debug(f"Extraction kit map:\n\n{pformat(excel_map)}")
        logger.debug(f"Missing reagents going into autofile: {pformat(reagents)}")
        logger.debug(f"Missing info going into autofile: {pformat(info)}")
        new_reagents = []
        for reagent in reagents:
            new_reagent = {}
            new_reagent['type'] = reagent.type
            new_reagent['lot'] = excel_map[new_reagent['type']]['lot']
            new_reagent['lot']['value'] = reagent.lot
            new_reagent['expiry'] = excel_map[new_reagent['type']]['expiry']
            new_reagent['expiry']['value'] = reagent.expiry
            new_reagent['sheet'] = excel_map[new_reagent['type']]['sheet']
            # name is only present for Bacterial Culture
            try:
                new_reagent['name'] = excel_map[new_reagent['type']]['name']
                new_reagent['name']['value'] = reagent.name
            except Exception as e:
                logger.error(f"Couldn't get name due to {e}")
            new_reagents.append(new_reagent)
        new_info = []
        for k,v in info.items():
            try:
                new_item = {}
                new_item['type'] = k
                new_item['location'] = excel_map['info'][k]
                new_item['value'] = v['value']
                new_info.append(new_item)
            except KeyError:
                logger.error(f"Unable to fill in {k}, not found in relevant info.")
        logger.debug(f"New reagents: {new_reagents}")
        logger.debug(f"New info: {new_info}")
        # open a new workbook using openpyxl
        workbook = load_workbook(self.filepath)
        # get list of sheet names
        sheets = workbook.sheetnames
        # logger.debug(workbook.sheetnames)
        for sheet in sheets:
            # open sheet
            worksheet=workbook[sheet]
            # Get relevant reagents for that sheet
            sheet_reagents = [item for item in new_reagents if sheet in item['sheet']]
            for reagent in sheet_reagents:
                # logger.debug(f"Attempting to write lot {reagent['lot']['value']} in: row {reagent['lot']['row']}, column {reagent['lot']['column']}")
                worksheet.cell(row=reagent['lot']['row'], column=reagent['lot']['column'], value=reagent['lot']['value'])
                # logger.debug(f"Attempting to write expiry {reagent['expiry']['value']} in: row {reagent['expiry']['row']}, column {reagent['expiry']['column']}")
                worksheet.cell(row=reagent['expiry']['row'], column=reagent['expiry']['column'], value=reagent['expiry']['value'])
                try:
                    # logger.debug(f"Attempting to write name {reagent['name']['value']} in: row {reagent['name']['row']}, column {reagent['name']['column']}")
                    worksheet.cell(row=reagent['name']['row'], column=reagent['name']['column'], value=reagent['name']['value'])
                except Exception as e:
                    logger.error(f"Could not write name {reagent['name']['value']} due to {e}")
            # Get relevant info for that sheet
            sheet_info = [item for item in new_info if sheet in item['location']['sheets']]
            for item in sheet_info:
                logger.debug(f"Attempting: {item['type']} in row {item['location']['row']}, column {item['location']['column']}")
                worksheet.cell(row=item['location']['row'], column=item['location']['column'], value=item['value'])
            # Hacky way to pop in 'signed by'
        # custom_parser = get_polymorphic_subclass(BasicSubmission, info['submission_type'])
        custom_parser = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=self.submission_type['value'])
        workbook = custom_parser.custom_autofill(workbook)
        return workbook

    def construct_filename(self):
        env = jinja_template_loading()
        template = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=self.submission_type).filename_template()
        logger.debug(f"Using template string: {template}")
        template = env.from_string(template)
        return template.render(**self.improved_dict(dictionaries=False))

class PydContact(BaseModel):

    name: str
    phone: str|None
    email: str|None

    def toSQL(self, ctx):
        return Contact(name=self.name, phone=self.phone, email=self.email)

class PydOrganization(BaseModel):

    name: str
    cost_centre: str
    contacts: List[PydContact]|None

    def toSQL(self, ctx):
        instance = Organization()
        for field in self.model_fields:
            match field:
                case "contacts":
                    value = [item.toSQL(ctx) for item in getattr(self, field)]
                case _:
                    value = getattr(self, field)
            instance.set_attribute(name=field, value=value)
        return instance

class PydReagentType(BaseModel):

    name: str
    eol_ext: timedelta|int|None
    uses: dict|None
    required: int|None = Field(default=1)

    @field_validator("eol_ext")
    @classmethod
    def int_to_timedelta(cls, value):
        if isinstance(value, int):
            return timedelta(days=value)
        return value
    
    def toSQL(self, ctx:Settings, kit:KitType):
        # instance: ReagentType = lookup_reagent_types(ctx=ctx, name=self.name)
        instance: ReagentType = ReagentType.query(name=self.name)
        if instance == None:
            instance = ReagentType(name=self.name, eol_ext=self.eol_ext)
        logger.debug(f"This is the reagent type instance: {instance.__dict__}")
        try:
            # assoc = lookup_reagenttype_kittype_association(ctx=ctx, reagent_type=instance, kit_type=kit)
            assoc = KitTypeReagentTypeAssociation.query(reagent_type=instance, kit_type=kit)
        except StatementError:
            assoc = None
        if assoc == None:
            assoc = KitTypeReagentTypeAssociation(kit_type=kit, reagent_type=instance, uses=self.uses, required=self.required)
            # kit.kit_reagenttype_associations.append(assoc)
        return instance
    
class PydKit(BaseModel):

    name: str
    reagent_types: List[PydReagentType] = []

    def toSQL(self, ctx):
        result = dict(message=None, status='Information')
        # instance = lookup_kit_types(ctx=ctx, name=self.name)
        instance = KitType.query(name=self.name)
        if instance == None:
            instance = KitType(name=self.name)
            # instance.reagent_types = [item.toSQL(ctx, instance) for item in self.reagent_types]
            [item.toSQL(ctx, instance) for item in self.reagent_types]
        return instance, result


