import uuid
from pydantic import BaseModel, validator
from datetime import date
from typing import List, Any
from tools import RSLNamer
from pathlib import Path
import re
import logging

logger = logging.getLogger(f"submissions.{__name__}")

class PydSubmission(BaseModel):
    filepath: Path
    submission_type: str
    submitter_plate_num: str|None
    rsl_plate_num: str
    submitted_date: date
    submitting_lab: str
    sample_count: int
    extraction_kit: str
    technician: str
    reagents: List[dict]
    samples: List[Any]

    @validator("submitted_date", pre=True)
    @classmethod
    def strip_datetime_string(cls, value):
        return re.sub(r"_\d$", "", value)

    @validator("submitter_plate_num")
    @classmethod
    def enforce_with_uuid(cls, value):
        if value == None or value == "" or value == "None":
            return uuid.uuid4().hex.upper()

    @validator("rsl_plate_num", pre=True)
    @classmethod
    def rsl_from_file(cls, value, values):
        if value == None:
            logger.debug(f"Pydant values:\n{values}")
            return RSLNamer(values['filepath'].__str__()).parsed_name
        else:
            return value
        
    @validator("technician")
    @classmethod
    def enforce_tech(cls, value):
        if value == "nan" or value == "None":
            value = "Unknown"
        # elif len(value.split(",")) > 1:
        #     tech_reg = re.compile(r"\b[A-Z]{2}\b")
        #     value = ", ".join(tech_reg.findall(value))
        return value
    
    @validator("reagents")
    @classmethod
    def remove_atcc(cls, value):
        return_val = []
        for reagent in value:
            match reagent['type']:
                case 'atcc':
                    continue
                case _:
                    return_val.append(reagent)
        return return_val
