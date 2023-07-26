import uuid
from pydantic import BaseModel, field_validator, model_validator, Extra
from datetime import date, datetime
from typing import List, Any
from tools import RSLNamer
from pathlib import Path
import re
import logging
from tools import check_not_nan, convert_nans_to_nones, Settings
import numpy as np



logger = logging.getLogger(f"submissions.{__name__}")

class PydReagent(BaseModel):
    type: str|None
    lot: str|None
    exp: date|None

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
        if isinstance(value, float) or value == np.nan:
            raise ValueError(f"Date cannot be a float: {value}")
        else:
            return value

    

class PydSubmission(BaseModel, extra=Extra.allow):
    ctx: Settings
    filepath: Path
    submission_type: str|dict|None
    submitter_plate_num: str|None
    rsl_plate_num: str|dict|None
    submitted_date: date
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
            return value
        if isinstance(value, date):
            return value
        return re.sub(r"_\d$", "", value)

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
        if check_not_nan(value):
            if isinstance(value, str):
                return dict(value=value, parsed=True)
            else:
                return value
        else:
            # logger.debug(f"Pydant values:{type(values)}\n{values}")
            return dict(value=RSLNamer(ctx=values.data['ctx'], instr=values.data['filepath'].__str__()).parsed_name, parsed=False)

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
            # match reagent.type.lower():
            #     case 'atcc':
            #         continue
            #     case _:
            #         return_val.append(reagent)
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
            # raise ValueError(f"{value} could not be used to create an integer.")
            return convert_nans_to_nones(value)
        
    @field_validator("extraction_kit", mode='before')
    @classmethod
    def get_kit_if_none(cls, value, values):
        from frontend.custom_widgets.pop_ups import KitSelector
        if check_not_nan(value):
            return dict(value=value, parsed=True)
        else:
            # logger.debug(values.data)
            dlg = KitSelector(ctx=values.data['ctx'], title="Kit Needed", message="At minimum a kit is needed. Please select one.")
            if dlg.exec():
                return dict(value=dlg.getValues(), parsed=False)
            else:
                raise ValueError("Extraction kit needed.") 
            
    
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

    # @model_validator(mode="after")
    # def ensure_kit(cls, values):
    #     logger.debug(f"Model values: {values}")
    #     missing_fields = [k for k,v in values if v == None]
    #     if len(missing_fields) > 0:
    #         logger.debug(f"Missing fields: {missing_fields}")
    #         values['missing_fields'] = missing_fields
    #     return values


