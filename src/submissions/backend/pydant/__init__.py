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

    

class PydSubmission(BaseModel, extra=Extra.allow):
    ctx: Settings
    filepath: Path
    submission_type: str|dict|None
    submitter_plate_num: str|None
    rsl_plate_num: str|dict|None
    submitted_date: date|dict
    submitting_lab: str|None
    sample_count: int
    extraction_kit: str|dict|None
    technician: str|dict|None
    reagents: List[PydReagent] = []
    samples: List[Any]
    # missing_fields: List[str] = []
    
    @field_validator("submitted_date", mode="before")
    @classmethod
    def strip_datetime_string(cls, value):
        if not check_not_nan(value):
            value = date.today()
        if isinstance(value, datetime):
            return dict(value=value, parsed=True)
        if isinstance(value, date):
            return value
        string = re.sub(r"(_|-)\d$", "", value)
        try:
            output = dict(value=parse(string).date(), parsed=False)
        except ParserError as e:
            logger.error(f"Problem parsing date: {e}")
            try:
                output = dict(value=parse(string.replace("-","")).date(), parsed=False)
            except Exception as e:
                logger.error(f"Problem with parse fallback: {e}")
        return output

    @field_validator("submitter_plate_num")
    @classmethod
    def enforce_with_uuid(cls, value):
        if value == None or value == "" or value == "None":
            return uuid.uuid4().hex.upper()
        else:
            return value
        
    @field_validator("submitting_lab", mode="before")
    @classmethod
    def transform_nan(cls, value):
        return convert_nans_to_nones(value)

    @field_validator("rsl_plate_num", mode='before')
    @classmethod
    def rsl_from_file(cls, value, values):
        logger.debug(f"RSL-plate initial value: {value}")
        if isinstance(values.data['submission_type'], dict):
            sub_type = values.data['submission_type']['value']
        elif isinstance(values.data['submission_type'], str):
            sub_type = values.data['submission_type']
        if check_not_nan(value):
            if lookup_submission_by_rsl_num(ctx=values.data['ctx'], rsl_num=value) == None:
                return dict(value=value, parsed=True)
            else:
                logger.warning(f"Submission number {value} already exists in DB, attempting salvage with filepath")
                output = RSLNamer(ctx=values.data['ctx'], instr=values.data['filepath'].__str__(), sub_type=sub_type).parsed_name
                return dict(value=output, parsed=False)
        else:
            output = RSLNamer(ctx=values.data['ctx'], instr=values.data['filepath'].__str__(), sub_type=sub_type).parsed_name
            return dict(value=output, parsed=False)

    @field_validator("technician", mode="before")
    @classmethod
    def enforce_tech(cls, value):
        if check_not_nan(value):
            if isinstance(value, dict):
                value['value'] = re.sub(r"\: \d", "", value['value'])
                return value
            else:
                return dict(value=re.sub(r"\: \d", "", value), parsed=True)
        else:
            return dict(value="Unnamed", parsed=False)
        return value
    
    @field_validator("reagents")
    @classmethod
    def remove_atcc(cls, value):
        return_val = []
        for reagent in value:
            logger.debug(f"Pydantic reagent: {reagent}")
            if reagent.type == None:
                continue
            else:
                return_val.append(reagent)
        return return_val
        
    @field_validator("sample_count", mode='before')
    @classmethod
    def enforce_sample_count(cls, value):
        if check_not_nan(value):
            return int(value)
        else:
            return convert_nans_to_nones(value)
        
    @field_validator("extraction_kit", mode='before')
    @classmethod
    def get_kit_if_none(cls, value):
        # from frontend.custom_widgets.pop_ups import KitSelector
        if check_not_nan(value):
            if isinstance(value, str):
                return dict(value=value, parsed=True)
            elif isinstance(value, dict):
                return value
        else:
            raise ValueError(f"No extraction kit found.")
            
    
    @field_validator("submission_type", mode='before')
    @classmethod
    def make_submission_type(cls, value, values):
        if check_not_nan(value):
            if isinstance(value, dict):
                value['value'] = value['value'].title()
                return value
            elif isinstance(value, str):
                return dict(value=value.title(), parsed=False)
        else:
            return dict(value=RSLNamer(ctx=values.data['ctx'], instr=values.data['filepath'].__str__()).submission_type.title(), parsed=False)
