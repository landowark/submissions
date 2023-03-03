# from ..models import *
from backend.db.models import *
# from backend.db import lookup_kittype_by_name
import logging
import numpy as np

logger = logging.getLogger(f"submissions.{__name__}")

def check_kit_integrity(sub:BasicSubmission|KitType, reagenttypes:list|None=None) -> dict|None:
    logger.debug(type(sub))
    match sub:
        case BasicSubmission():
            ext_kit_rtypes = [reagenttype.name for reagenttype in sub.extraction_kit.reagent_types]
            reagenttypes = [reagent.type.name for reagent in sub.reagents]
        case KitType():
            ext_kit_rtypes = [reagenttype.name for reagenttype in sub.reagent_types]
    logger.debug(f"Kit reagents: {ext_kit_rtypes}")
    logger.debug(f"Submission reagents: {reagenttypes}")
    check = set(ext_kit_rtypes) == set(reagenttypes)
    logger.debug(f"Checking if reagents match kit contents: {check}")
    common = list(set(ext_kit_rtypes).intersection(reagenttypes))
    logger.debug(f"common reagents types: {common}")
    if check:
        result = None
    else:
        missing = [x for x in ext_kit_rtypes if x not in common]
        result = {'message' : f"Couldn't verify reagents match listed kit components.\n\nIt looks like you are missing: {[item.upper() for item in missing]}\n\nAlternatively, you may have set the wrong extraction kit.", 'missing': missing}
    return result



    

