'''
Contains pydantic models and accompanying validators
'''
from __future__ import annotations
from operator import attrgetter
import uuid, re, logging
from pydantic import BaseModel, field_validator, Field
from datetime import date, datetime, timedelta
from dateutil.parser import parse
from dateutil.parser._parser import ParserError
from typing import List, Tuple
from . import RSLNamer
from pathlib import Path
from tools import check_not_nan, convert_nans_to_nones, Report, Result, row_map
from backend.db.models import *
from sqlalchemy.exc import StatementError, IntegrityError
from PyQt6.QtWidgets import QComboBox, QWidget
from openpyxl import load_workbook, Workbook
from io import BytesIO

logger = logging.getLogger(f"submissions.{__name__}")

class PydReagent(BaseModel):
    
    lot: str|None
    type: str|None
    expiry: date|None
    name: str|None
    missing: bool = Field(default=True)
    comment: str|None = Field(default="", validate_default=True)

    @field_validator('comment', mode='before')
    @classmethod
    def create_comment(cls, value):
        if value == None:
            return ""
        return value

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

    def toSQL(self, submission:BasicSubmission|str=None) -> Tuple[Reagent, Report]:
        """
        Converts this instance into a backend.db.models.kit.Reagent instance

        Returns:
            Tuple[Reagent, Report]: Reagent instance and result of function
        """        
        report = Report()
        # logger.debug("Adding extra fields.")
        if self.model_extra != None:
            self.__dict__.update(self.model_extra)
        logger.debug(f"Reagent SQL constructor is looking up type: {self.type}, lot: {self.lot}")
        reagent = Reagent.query(lot_number=self.lot, name=self.name)
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
                    case "type":
                        reagent_type = ReagentType.query(name=value)
                        if reagent_type != None:
                            reagent.type.append(reagent_type)
                    case "comment":
                        continue
                    case _:
                        try:
                            reagent.__setattr__(key, value)
                        except AttributeError:
                            logger.error(f"Couldn't set {key} to {value}")
                if submission != None:
                    assoc = SubmissionReagentAssociation(reagent=reagent, submission=submission)
                    assoc.comments = self.comment
                    reagent.reagent_submission_associations.append(assoc)
            # add end-of-life extension from reagent type to expiry date
            # NOTE: this will now be done only in the reporting phase to account for potential changes in end-of-life extensions
        return reagent, report
    
class PydSample(BaseModel, extra='allow'):

    submitter_id: str
    sample_type: str
    row: int|List[int]|None
    column: int|List[int]|None
    assoc_id: int|List[int]|None = Field(default=None)

    @field_validator("row", "column", "assoc_id")
    @classmethod
    def row_int_to_list(cls, value):
        if isinstance(value, int):
            return [value]
        return value
    
    @field_validator("submitter_id", mode="before")
    @classmethod
    def int_to_str(cls, value):
        return str(value)
    
    def toSQL(self, submission:BasicSubmission|str=None) -> Tuple[BasicSample, Result]:
        """
        Converts this instance into a backend.db.models.submissions.Sample object

        Args:
            submission (BasicSubmission | str, optional): Submission joined to this sample. Defaults to None.

        Returns:
            Tuple[BasicSample, Result]: Sample object and result object.
        """        
        report = None
        self.__dict__.update(self.model_extra)
        logger.debug(f"Here is the incoming sample dict: \n{self.__dict__}")
        instance = BasicSample.query_or_create(sample_type=self.sample_type, submitter_id=self.submitter_id)
        for key, value in self.__dict__.items():
            # logger.debug(f"Setting sample field {key} to {value}")
            match key:
                case "row" | "column":
                    continue
                case _:
                    # instance.set_attribute(name=key, value=value)
                    instance.__setattr__(key, value)
        out_associations = []
        if submission != None:
            assoc_type = self.sample_type.replace("Sample", "").strip()
            for row, column, id in zip(self.row, self.column, self.assoc_id):
                logger.debug(f"Looking up association with identity: ({submission.submission_type_name} Association)")
                logger.debug(f"Looking up association with identity: ({assoc_type} Association)")
                association = SubmissionSampleAssociation.query_or_create(association_type=f"{assoc_type} Association", 
                                                                            submission=submission, 
                                                                            sample=instance, 
                                                                            row=row, column=column, id=id)
                # logger.debug(f"Using submission_sample_association: {association}")
                try:
                    # instance.sample_submission_associations.append(association)
                    out_associations.append(association)
                except IntegrityError as e:
                    logger.error(f"Could not attach submission sample association due to: {e}")
                    instance.metadata.session.rollback()
        return instance, out_associations, report

class PydEquipment(BaseModel, extra='ignore'):

    asset_number: str
    name: str
    nickname: str|None
    processes: List[str]|None
    role: str|None

    @field_validator('processes', mode='before')
    @classmethod
    def make_empty_list(cls, value):
        # logger.debug(f"Pydantic value: {value}")
        value = convert_nans_to_nones(value)
        if value == None:
            value = ['']
        if len(value)==0:
            value=['']
        return value

    def toSQL(self, submission:BasicSubmission|str=None) -> Tuple[Equipment, SubmissionEquipmentAssociation]:
        """
        Creates Equipment and SubmssionEquipmentAssociations for this PydEquipment

        Args:
            submission ( BasicSubmission | str ): BasicSubmission of interest

        Returns:
            Tuple[Equipment, SubmissionEquipmentAssociation]: SQL objects
        """        
        if isinstance(submission, str):
            submission = BasicSubmission.query(rsl_number=submission)
        equipment = Equipment.query(asset_number=self.asset_number)
        if equipment == None:
            return
        if submission != None:
            assoc = SubmissionEquipmentAssociation(submission=submission, equipment=equipment)
            process = Process.query(name=self.processes[0])
            if process == None:
                # logger.debug("Adding in unknown process.")
                from frontend.widgets.pop_ups import QuestionAsker
                dlg = QuestionAsker(title="Add Process?", message=f"Unable to find {self.processes[0]} in the database.\nWould you like to add it?")
                if dlg.exec():
                    kit = submission.extraction_kit
                    submission_type = submission.submission_type
                    process = Process(name=self.processes[0])
                    process.kit_types.append(kit)
                    process.submission_types.append(submission_type)
                    process.equipment.append(equipment)
                    process.save()
            assoc.process = process
            assoc.role = self.role
        else:
            assoc = None
        return equipment, assoc

class PydSubmission(BaseModel, extra='allow'):
    filepath: Path
    submission_type: dict|None
    # For defaults
    submitter_plate_num: dict|None = Field(default=dict(value=None, missing=True), validate_default=True)
    submitted_date: dict|None
    rsl_plate_num: dict|None = Field(default=dict(value=None, missing=True), validate_default=True)
    submitted_date: dict|None
    submitting_lab: dict|None
    sample_count: dict|None
    extraction_kit: dict|None
    technician: dict|None
    submission_category: dict|None = Field(default=dict(value=None, missing=True), validate_default=True)
    comment: dict|None = Field(default=dict(value="", missing=True), validate_default=True)
    reagents: List[dict]|List[PydReagent] = []
    samples: List[PydSample]
    equipment: List[PydEquipment]|None =[]

    @field_validator('equipment', mode='before')
    @classmethod
    def convert_equipment_dict(cls, value):
        logger.debug(f"Equipment: {value}")
        if isinstance(value, dict):
            return value['value']
        return value

    @field_validator('comment', mode='before')
    @classmethod
    def create_comment(cls, value):
        if value == None:
            return ""
        return value

    @field_validator("submitter_plate_num")
    @classmethod
    def enforce_with_uuid(cls, value):
        # logger.debug(f"submitter_plate_num coming into pydantic: {value}")
        if value['value'] == None or value['value'] == "None":
            return dict(value=uuid.uuid4().hex.upper(), missing=True)
        else:
            return value
    
    @field_validator("submitted_date", mode="before")
    @classmethod
    def rescue_date(cls, value):
        logger.debug(f"\n\nDate coming into pydantic: {value}\n\n")
        try:
            check = value['value'] == None
        except TypeError:
            check = True
        if check:
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
        logger.debug(f"RSL-plate initial value: {value['value']} and other values: {values.data}")
        sub_type = values.data['submission_type']['value']
        if check_not_nan(value['value']):
            return value
        else:
            output = RSLNamer(filename=values.data['filepath'].__str__(), sub_type=sub_type, data=values.data).parsed_name
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

    def set_attribute(self, key, value):
        self.__setattr__(name=key, value=value)

    def handle_duplicate_samples(self):
        """
        Collapses multiple samples with same submitter id into one with lists for rows, columns.
        Necessary to prevent trying to create duplicate samples in SQL creation.
        """        
        submitter_ids = list(set([sample.submitter_id for sample in self.samples]))
        output = []
        for id in submitter_ids:
            relevants = [item for item in self.samples if item.submitter_id==id]
            if len(relevants) <= 1:
                output += relevants
            else:
                rows = [item.row[0] for item in relevants]
                columns = [item.column[0] for item in relevants]
                ids = [item.assoc_id[0] for item in relevants]
                dummy = relevants[0]
                dummy.assoc_id = ids
                dummy.row = rows
                dummy.column = columns
                output.append(dummy)
        self.samples = output

    def improved_dict(self, dictionaries:bool=True) -> dict:
        """
        Adds model_extra to fields.

        Args:
            dictionaries (bool, optional): Are dictionaries expected as input? i.e. Should key['value'] be retrieved. Defaults to True.

        Returns:
            dict: This instance as a dictionary
        """        
        fields = list(self.model_fields.keys()) + list(self.model_extra.keys())
        if dictionaries:
            output = {k:getattr(self, k) for k in fields}
        else:
            # logger.debug("Extracting 'value' from attributes")
            output = {k:(getattr(self, k) if not isinstance(getattr(self, k), dict) else getattr(self, k)['value']) for k in fields}
        return output

    def find_missing(self) -> Tuple[dict, dict]:
        """
        Retrieves info and reagents marked as missing.

        Returns:
            Tuple[dict, dict]: Dict for missing info, dict for missing reagents.
        """        
        info = {k:v for k,v in self.improved_dict().items() if isinstance(v, dict)}
        missing_info = {k:v for k,v in info.items() if v['missing']}
        missing_reagents = [reagent for reagent in self.reagents if reagent.missing]
        return missing_info, missing_reagents

    def toSQL(self) -> Tuple[BasicSubmission, Result]:
        """
        Converts this instance into a backend.db.models.submissions.BasicSubmission instance

        Returns:
            Tuple[BasicSubmission, Result]: BasicSubmission instance, result object
        """        
        # self.__dict__.update(self.model_extra)
        dicto = self.improved_dict()
        instance, code, msg = BasicSubmission.query_or_create(submission_type=self.submission_type['value'], rsl_plate_num=self.rsl_plate_num['value'])
        result = Result(msg=msg, code=code)
        self.handle_duplicate_samples()
        logger.debug(f"Here's our list of duplicate removed samples: {self.samples}")
        # for key, value in self.__dict__.items():
        for key, value in dicto.items():
            if isinstance(value, dict):
                value = value['value']
            logger.debug(f"Setting {key} to {value}")
            match key:
                case "samples":
                    for sample in self.samples:
                        sample, associations, _ = sample.toSQL(submission=instance)
                        # logger.debug(f"Sample SQL object to be added to submission: {sample.__dict__}")
                        for assoc in associations:
                            instance.submission_sample_associations.append(assoc)
                case "equipment":
                    logger.debug(f"Equipment: {pformat(self.equipment)}")
                    try:
                        if equip == None:
                            continue
                    except UnboundLocalError:
                        continue
                    for equip in self.equipment:
                        equip, association = equip.toSQL(submission=instance)
                        if association != None:
                            association.save()
                            logger.debug(f"Equipment association SQL object to be added to submission: {association.__dict__}")
                            instance.submission_equipment_associations.append(association)
                case _:
                    try:
                        instance.set_attribute(key=key, value=value)
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
            try:
                instance.run_cost = instance.extraction_kit.cost_per_run
            except AttributeError:
                instance.run_cost = 0
        logger.debug(f"Calculated base run cost of: {instance.run_cost}")
        # Apply any discounts that are applicable for client and kit.
        try:
            logger.debug("Checking and applying discounts...")
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
        return instance, result
    
    def toForm(self, parent:QWidget):
        """
        Converts this instance into a frontend.widgets.submission_widget.SubmissionFormWidget

        Args:
            parent (QWidget): parent widget of the constructed object

        Returns:
            SubmissionFormWidget: Submission form widget
        """        
        from frontend.widgets.submission_widget import SubmissionFormWidget
        return SubmissionFormWidget(parent=parent, submission=self)

    def autofill_excel(self, missing_only:bool=True, backup:bool=False) -> Workbook:
        """
        Fills in relevant information/reagent cells in an excel workbook.

        Args:
            missing_only (bool, optional): Only fill missing items or all. Defaults to True.
            backup (bool, optional): Do a full backup of the submission (adds samples). Defaults to False.

        Returns:
            Workbook: Filled in workbook
        """        
        # open a new workbook using openpyxl
        if self.filepath.stem.startswith("tmp"):
            template = SubmissionType.query(name=self.submission_type['value']).template_file
            workbook = load_workbook(BytesIO(template))
            missing_only = False
        else:    
            try:
                workbook = load_workbook(self.filepath)
            except Exception as e:
                logger.error(f"Couldn't open workbook due to {e}")
                template = SubmissionType.query(name=self.submission_type).template_file
                workbook = load_workbook(BytesIO(template))
                missing_only = False
        if missing_only:
            info, reagents = self.find_missing()
        else:
            info = {k:v for k,v in self.improved_dict().items() if isinstance(v, dict)}
            reagents = self.reagents
        if len(reagents + list(info.keys())) == 0:
            # logger.warning("No info to fill in, returning")
            return None
        logger.debug(f"We have blank info and/or reagents in the excel sheet.\n\tLet's try to fill them in.")
        # extraction_kit = lookup_kit_types(ctx=self.ctx, name=self.extraction_kit['value'])
        extraction_kit = KitType.query(name=self.extraction_kit['value'])
        logger.debug(f"We have the extraction kit: {extraction_kit.name}")
        excel_map = extraction_kit.construct_xl_map_for_use(self.submission_type['value'])
        # logger.debug(f"Extraction kit map:\n\n{pformat(excel_map)}")
        # logger.debug(f"Missing reagents going into autofile: {pformat(reagents)}")
        # logger.debug(f"Missing info going into autofile: {pformat(info)}")
        new_reagents = []
        # logger.debug("Constructing reagent map and values")
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
        # logger.debug("Constructing info map and values")
        for k,v in info.items():
            try:
                new_item = {}
                new_item['type'] = k
                new_item['location'] = excel_map['info'][k]
                match k:
                    case "comment":
                        if v['value'] is not None:
                            new_item['value'] = "--".join([comment['text'] for comment in v['value']])
                        else:
                            new_item['value'] = None
                    case _:
                        new_item['value'] = v['value']
                new_info.append(new_item)
            except KeyError:
                logger.error(f"Unable to fill in {k}, not found in relevant info.")
        logger.debug(f"New reagents: {new_reagents}")
        logger.debug(f"New info: {new_info}")
        # get list of sheet names
        for sheet in workbook.sheetnames:
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
            new_info = [item for item in new_info if isinstance(item['location'], dict)]
            sheet_info = [item for item in new_info if sheet in item['location']['sheets']]
            for item in sheet_info:
                logger.debug(f"Attempting: {item['type']} in row {item['location']['row']}, column {item['location']['column']}")
                worksheet.cell(row=item['location']['row'], column=item['location']['column'], value=item['value'])
            # Hacky way to pop in 'signed by'
        custom_parser = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=self.submission_type['value'])
        workbook = custom_parser.custom_autofill(workbook, info=self.improved_dict(), backup=backup)
        return workbook
    
    def autofill_samples(self, workbook:Workbook) -> Workbook:
        """
        Fill in sample rows on the excel sheet

        Args:
            workbook (Workbook): Input excel workbook

        Returns:
            Workbook: Updated excel workbook
        """        
        sample_info = SubmissionType.query(name=self.submission_type['value']).info_map['samples']
        logger.debug(f"Sample info: {pformat(sample_info)}")
        logger.debug(f"Workbook sheets: {workbook.sheetnames}")
        worksheet = workbook[sample_info["lookup_table"]['sheet']]
        # logger.debug("Sorting samples by row/column")
        samples = sorted(self.samples, key=attrgetter('column', 'row'))
        submission_obj = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=self.submission_type)
        # custom function to adjust values for writing.
        samples = submission_obj.adjust_autofill_samples(samples=samples)
        logger.debug(f"Samples: {pformat(samples)}")
        # Fail safe against multiple instances of the same sample
        for iii, sample in enumerate(samples, start=1):
            logger.debug(f"Sample: {sample}")
            # custom function to find the row of this sample
            row = submission_obj.custom_sample_autofill_row(sample, worksheet=worksheet)
            logger.debug(f"Writing to {row}")
            if row == None:
                row = sample_info['lookup_table']['start_row'] + iii
            fields = [field for field in list(sample.model_fields.keys()) + list(sample.model_extra.keys()) if field in sample_info['sample_columns'].keys()]
            logger.debug(f"Here are the fields we are going to fill:\n\t{fields}")
            for field in fields:
                column = sample_info['sample_columns'][field]
                value = getattr(sample, field)
                match value:
                    case list():
                        value = value[0]
                    case _:
                        value = value
                if field == "row":
                    value = row_map[value]
                worksheet.cell(row=row, column=column, value=value)
        return workbook
    
    def autofill_equipment(self, workbook:Workbook) -> Workbook:
        """
        Fill in equipment on the excel sheet

        Args:
            workbook (Workbook): Input excel workbook

        Returns:
            Workbook: Updated excel workbook
        """        
        equipment_map = SubmissionType.query(name=self.submission_type['value']).construct_equipment_map()
        logger.debug(f"Equipment map: {equipment_map}")
        # See if all equipment has a location map
        # If not, create a new sheet to store them in.
        if not all([len(item.keys()) > 1 for item in equipment_map]):
            logger.warning("Creating 'Equipment' sheet to hold unmapped equipment")
            workbook.create_sheet("Equipment")
        equipment = []
        # logger.debug("Contructing equipment info map/values")
        for ii, equip in enumerate(self.equipment, start=1):
            loc = [item for item in equipment_map if item['role'] == equip.role][0]
            try:
                loc['name']['value'] = equip.name
                loc['process']['value'] = equip.processes[0]
            except KeyError:
                loc['name'] = dict(row=ii, column=2)
                loc['process'] = dict(row=ii, column=3)
                loc['name']['value'] = equip.name
                loc['process']['value'] = equip.processes[0]
                loc['sheet'] = "Equipment"
            equipment.append(loc)
        logger.debug(f"Using equipment: {equipment}")
        for sheet in workbook.sheetnames:
            logger.debug(f"Looking at: {sheet}")
            worksheet = workbook[sheet]
            relevant = [item for item in equipment if item['sheet'] == sheet]
            for rel in relevant:
                match sheet:
                    case "Equipment":
                        worksheet.cell(row=rel['name']['row'], column=1, value=rel['role'])
                    case _:
                        pass
                worksheet.cell(row=rel['name']['row'], column=rel['name']['column'], value=rel['name']['value'])
                worksheet.cell(row=rel['process']['row'], column=rel['process']['column'], value=rel['process']['value'])
        return workbook

    def construct_filename(self) -> str:
        """
        Creates filename for this instance

        Returns:
            str: Output filename
        """        
        template = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=self.submission_type).filename_template()
        # logger.debug(f"Using template string: {template}")
        render = RSLNamer.construct_export_name(template=template, **self.improved_dict(dictionaries=False)).replace("/", "")
        # logger.debug(f"Template rendered as: {render}")
        return render

    def check_kit_integrity(self, reagenttypes:list=[], extraction_kit:str|dict|None=None) -> Tuple[List[PydReagent], Report]:
        """
        Ensures all reagents expected in kit are listed in Submission
       
        Args:
            reagenttypes (list | None, optional): List to check against complete list. Defaults to None.

        Returns:
            Report: Result object containing a message and any missing components.
        """    
        report = Report()
        logger.debug(f"Extraction kit: {extraction_kit}. Is it a string? {isinstance(extraction_kit, str)}")
        if isinstance(extraction_kit, str):
            extraction_kit = dict(value=extraction_kit)
        if extraction_kit is not None:
            if extraction_kit != self.extraction_kit['value']:
                self.extraction_kit['value'] = extraction_kit['value']
                reagenttypes = []
            else:
                reagenttypes = [item.type for item in self.reagents]
        else:
            reagenttypes = [item.type for item in self.reagents]
        logger.debug(f"Looking up {self.extraction_kit['value']}")
        ext_kit = KitType.query(name=self.extraction_kit['value'])
        ext_kit_rtypes = [item.to_pydantic() for item in ext_kit.get_reagents(required=True, submission_type=self.submission_type['value'])]
        logger.debug(f"Kit reagents: {ext_kit_rtypes}")
        logger.debug(f"Submission reagents: {self.reagents}")
        # check if lists are equal
        # check = set(ext_kit_rtypes) == set(reagenttypes)
        # logger.debug(f"Checking if reagents match kit contents: {check}")
        # # what reagent types are in both lists?
        # missing = list(set(ext_kit_rtypes).difference(reagenttypes))
        missing = []
        # output_reagents = self.reagents
        output_reagents = ext_kit_rtypes
        logger.debug(f"Already have these reagent types: {reagenttypes}")
        for rt in ext_kit_rtypes:
            if rt.type not in reagenttypes:
                missing.append(rt)
                if rt.type not in [item.type for item in output_reagents]:
                    output_reagents.append(rt)
        logger.debug(f"Missing reagents types: {missing}")
        # if lists are equal return no problem
        if len(missing)==0:
            result = None
        else:
            result = Result(msg=f"The submission you are importing is missing some reagents expected by the kit.\n\nIt looks like you are missing: {[item.type.upper() for item in missing]}\n\nAlternatively, you may have set the wrong extraction kit.\n\nThe program will populate lists using existing reagents.\n\nPlease make sure you check the lots carefully!", status="Warning")
        report.add_result(result)
        return output_reagents, report

class PydContact(BaseModel):
    
    name: str
    phone: str|None
    email: str|None

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
    contacts: List[PydContact]|None

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
                    value = [item.toSQL() for item in getattr(self, field)]
                case _:
                    value = getattr(self, field)
            # instance.set_attribute(name=field, value=value)
            instance.__setattr__(name=field, value=value)
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
    
    def toSQL(self, kit:KitType) -> ReagentType:
        """
        Converts this instance into a backend.db.models.ReagentType instance

        Args:
            kit (KitType): KitType joined to the reagenttype

        Returns:
            ReagentType: ReagentType instance
        """        
        instance: ReagentType = ReagentType.query(name=self.name)
        if instance == None:
            instance = ReagentType(name=self.name, eol_ext=self.eol_ext)
        logger.debug(f"This is the reagent type instance: {instance.__dict__}")
        try:
            assoc = KitTypeReagentTypeAssociation.query(reagent_type=instance, kit_type=kit)
        except StatementError:
            assoc = None
        if assoc == None:
            assoc = KitTypeReagentTypeAssociation(kit_type=kit, reagent_type=instance, uses=self.uses, required=self.required)
        return instance
    
class PydKit(BaseModel):

    name: str
    reagent_types: List[PydReagentType] = []

    def toSQL(self) -> Tuple[KitType, Report]:
        """
        Converts this instance into a backend.db.models.kits.KitType instance

        Returns:
            Tuple[KitType, Report]: KitType instance and report of results.
        """        
        report = Report()
        instance = KitType.query(name=self.name)
        if instance == None:
            instance = KitType(name=self.name)
            [item.toSQL(instance) for item in self.reagent_types]
        return instance, report

class PydEquipmentRole(BaseModel):

    name: str
    equipment: List[PydEquipment]
    processes: List[str]|None
    
    def toForm(self, parent, used:list) -> "RoleComboBox":
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
    