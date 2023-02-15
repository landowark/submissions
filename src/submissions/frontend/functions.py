# from ..models import *
from backend.db.models import *
import logging
import numpy as np

logger = logging.getLogger(f"submissions.{__name__}")

def check_kit_integrity(sub:BasicSubmission):
    ext_kit_rtypes = [reagenttype.name for reagenttype in sub.extraction_kit.reagent_types]
    logger.debug(f"Kit reagents: {ext_kit_rtypes}")
    reagenttypes = [reagent.type.name for reagent in sub.reagents]
    logger.debug(f"Submission reagents: {reagenttypes}")
    check = set(ext_kit_rtypes) == set(reagenttypes)
    logger.debug(f"Checking if reagents match kit contents: {check}")
    common = list(set(ext_kit_rtypes).intersection(reagenttypes))
    logger.debug(f"common reagents types: {common}")
    if check:
        result = None
    else:
        result = {'message' : f"Couldn't verify reagents match listed kit components.\n\nIt looks like you are missing: {[x.upper() for x in ext_kit_rtypes if x not in common]}\n\nAlternatively, you may have set the wrong extraction kit."}
    return result
    

