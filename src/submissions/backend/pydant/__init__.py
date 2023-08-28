import uuid
from pydantic import BaseModel, field_validator, model_validator, Extra
from datetime import date, datetime
from dateutil.parser import parse
from dateutil.parser._parser import ParserError
from typing import List, Any
from tools import RSLNamer
from pathlib import Path
import re
import logging
from tools import check_not_nan, convert_nans_to_nones, Settings
import numpy as np
from backend.db.functions import lookup_submission_by_rsl_num



logger = logging.getLogger(f"submissions.{__name__}")

class PydReagent(BaseModel):
    type: str|None
    lot: str|None
    exp: date|None
    name: str|None

    @field_validator("type", mode='before')
    @classmethod
    def remove_undesired_types(cls, value):
        match value:
            case "atcc":
                return None
            case _:
                return value

    @field_validator("lot", mode='before')
    @classmethod
    def enforce_lot_string(cls, value):
        if value != None:
            return convert_nans_to_nones(str(value))
        return value
            
    @field_validator("exp", mode="before")
    @classmethod
    def enforce_date(cls, value):
        # if isinstance(value, float) or value == np.nan:
        #     raise ValueError(f"Date cannot be a float: {value}")
        # else:
        #     return value
        if value != None:
            return convert_nans_to_nones(str(value))
        return value
    
    @field_validator("name", mode="before")
    @classmethod
    def enforce_name(cls, value, values):
        if value != None:
            return convert_nans_to_nones(str(value))
        else:
            return values.data['type']

    

class PydSubmission(BaseModel, extra=Extra.allow):
    ctx: Settings
    filepath: Path
    submission_type: dict|None
    submitter_plate_num: dict|None
    rsl_plate_num: dict|None
    submitted_date: dict|None
    submitting_lab: dict|None
    sample_count: dict|None
    extraction_kit: dict|None
    technician: dict|None
    reagents: List[dict] = []
    samples: List[Any]
    # missing_fields: List[str] = []
    
    @field_validator("submitter_plate_num")
    @classmethod
    def rescue_submitter_id(cls, value):
        if value == None:
            return dict(value=None, parsed=False)
        return value

    @field_validator("submitter_plate_num")
    @classmethod
    def enforce_with_uuid(cls, value):
        logger.debug(f"submitter plate id: {value}")
        if value['value'] == None:
            return dict(value=uuid.uuid4().hex.upper(), parsed=False)
        else:
            return value
    
    @field_validator("submitted_date", mode="before")
    @classmethod
    def rescue_date(cls, value):
        if value == None:
            return dict(value=date.today(), parsed=False)
        return value

    @field_validator("submitted_date")
    @classmethod
    def strip_datetime_string(cls, value):
        if isinstance(value['value'], datetime):
            return value
        if isinstance(value['value'], date):
            return value
        if isinstance(value['value'], int):
            return dict(value=datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value['value'] - 2).date(), parsed=False)
        string = re.sub(r"(_|-)\d$", "", value['value'])
        try:
            output = dict(value=parse(string).date(), parsed=False)
        except ParserError as e:
            logger.error(f"Problem parsing date: {e}")
            try:
                output = dict(value=parse(string.replace("-","")).date(), parsed=False)
            except Exception as e:
                logger.error(f"Problem with parse fallback: {e}")
        return output
        
    @field_validator("submitting_lab", mode="before")
    @classmethod
    def rescue_submitting_lab(cls, value):
        if value == None:
            return dict(value=None, parsed=False)
        return value

    @field_validator("rsl_plate_num", mode='before')
    @classmethod
    def rescue_rsl_number(cls, value):
        if value == None:
            return dict(value=None, parsed=False)
        return value

    @field_validator("rsl_plate_num")
    @classmethod
    def rsl_from_file(cls, value, values):
        logger.debug(f"RSL-plate initial value: {value['value']}")
        # if isinstance(values.data['submission_type'], dict):
        #     sub_type = values.data['submission_type']['value']
        # elif isinstance(values.data['submission_type'], str):
        sub_type = values.data['submission_type']['value']
        if check_not_nan(value['value']):
            if lookup_submission_by_rsl_num(ctx=values.data['ctx'], rsl_num=value['value']) == None:
                return dict(value=value['value'], parsed=True)
            else:
                logger.warning(f"Submission number {value} already exists in DB, attempting salvage with filepath")
                output = RSLNamer(ctx=values.data['ctx'], instr=values.data['filepath'].__str__(), sub_type=sub_type).parsed_name
                return dict(value=output, parsed=False)
        else:
            output = RSLNamer(ctx=values.data['ctx'], instr=values.data['filepath'].__str__(), sub_type=sub_type).parsed_name
            return dict(value=output, parsed=False)

    @field_validator("technician", mode="before")
    @classmethod
    def rescue_tech(cls, value):
        if value == None:
            return dict(value=None, parsed=False)
        return value

    @field_validator("technician")
    @classmethod
    def enforce_tech(cls, value):
        if check_not_nan(value['value']):
            value['value'] = re.sub(r"\: \d", "", value['value'])
            return value
        else:
            return dict(value=convert_nans_to_nones(value['value']), parsed=False)
        return value
    
    # @field_validator("reagents")
    # @classmethod
    # def remove_atcc(cls, value):
    #     return_val = []
    #     for reagent in value:
    #         logger.debug(f"Pydantic reagent: {reagent}")
    #         if reagent['value'].type == None:
    #             continue
    #         else:
    #             return_val.append(reagent)
    #     return return_val
        
    @field_validator("sample_count", mode='before')
    @classmethod
    def rescue_sample_count(cls, value):
        if value == None:
            return dict(value=None, parsed=False)
        return value
        
    @field_validator("extraction_kit", mode='before')
    @classmethod
    def rescue_kit(cls, value):
        # from frontend.custom_widgets.pop_ups import KitSelector
        # if check_not_nan(value):
        #     if isinstance(value, str):
        #         return dict(value=value, parsed=True)
        #     elif isinstance(value, dict):
        #         return value
        # else:
        #     raise ValueError(f"No extraction kit found.")
        if value == None:
            return dict(value=None, parsed=False)
        return value
            
    @field_validator("submission_type", mode='before')
    @classmethod
    def make_submission_type(cls, value, values):
        if check_not_nan(value['value']):
            value = value['value'].title()
            return dict(value=value, parsed=True)
        else:
            return dict(value=RSLNamer(ctx=values.data['ctx'], instr=values.data['filepath'].__str__()).submission_type.title(), parsed=False)
