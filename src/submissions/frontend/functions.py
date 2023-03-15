# from ..models import *
from backend.db.models import *
import logging

logger = logging.getLogger(f"submissions.{__name__}")

def check_kit_integrity(sub:BasicSubmission|KitType, reagenttypes:list|None=None) -> dict|None:
    """
    Ensures all reagents expected in kit are listed in Submission

    Args:
        sub (BasicSubmission | KitType): Object containing complete list of reagent types.
        reagenttypes (list | None, optional): List to check against complete list. Defaults to None.

    Returns:
        dict|None: Result object containing a message and any missing components.
    """    
    logger.debug(type(sub))
    # What type is sub?
    match sub:
        case BasicSubmission():
            ext_kit_rtypes = [reagenttype.name for reagenttype in sub.extraction_kit.reagent_types]
            # Overwrite function parameter reagenttypes
            reagenttypes = [reagent.type.name for reagent in sub.reagents]
        case KitType():
            ext_kit_rtypes = [reagenttype.name for reagenttype in sub.reagent_types]
    logger.debug(f"Kit reagents: {ext_kit_rtypes}")
    logger.debug(f"Submission reagents: {reagenttypes}")
    # check if lists are equal
    check = set(ext_kit_rtypes) == set(reagenttypes)
    logger.debug(f"Checking if reagents match kit contents: {check}")
    # what reagent types are in both lists?
    # common = list(set(ext_kit_rtypes).intersection(reagenttypes))
    missing = list(set(ext_kit_rtypes).difference(reagenttypes))
    logger.debug(f"Missing reagents types: {missing}")
    # if lists are equal return no problem
    if len(missing)==0:
        result = None
    else:
        # missing = [x for x in ext_kit_rtypes if x not in common]
        result = {'message' : f"Couldn't verify reagents match listed kit components.\n\nIt looks like you are missing: {[item.upper() for item in missing]}\n\nAlternatively, you may have set the wrong extraction kit.", 'missing': missing}
    return result


# Below is depreciated:
# def insert_reagent_import(ctx:dict, item:str, prsr:SheetParser|None=None) -> QComboBox:
#     add_widget = QComboBox()
#     add_widget.setEditable(True)
#     # Ensure that all reagenttypes have a name that matches the items in the excel parser
#     query_var = item.replace("lot_", "")
#     logger.debug(f"Query for: {query_var}")
#     if prsr != None:
#         if isinstance(prsr.sub[item], np.float64):
#             logger.debug(f"{prsr.sub[item]['lot']} is a numpy float!")
#             try:
#                 prsr.sub[item] = int(prsr.sub[item]['lot'])
#             except ValueError:
#                 pass
#     # query for reagents using type name from sheet and kit from sheet
#     logger.debug(f"Attempting lookup of reagents by type: {query_var}")
#     # below was lookup_reagent_by_type_name_and_kit_name, but I couldn't get it to work.
#     relevant_reagents = [item.__str__() for item in lookup_regent_by_type_name(ctx=ctx, type_name=query_var)]#, kit_name=prsr.sub['extraction_kit'])]
#     output_reg = []
#     for reagent in relevant_reagents:
#         if isinstance(reagent, set):
#             for thing in reagent:
#                 output_reg.append(thing)
#         elif isinstance(reagent, str):
#             output_reg.append(reagent)
#     relevant_reagents = output_reg
#     # if reagent in sheet is not found insert it into items
#     if prsr != None:
#         logger.debug(f"Relevant reagents for {prsr.sub[item]}: {relevant_reagents}")
#         if str(prsr.sub[item]['lot']) not in relevant_reagents and prsr.sub[item]['lot'] != 'nan':
#             if check_not_nan(prsr.sub[item]['lot']):
#                 relevant_reagents.insert(0, str(prsr.sub[item]['lot']))
#     logger.debug(f"New relevant reagents: {relevant_reagents}")
#     add_widget.addItems(relevant_reagents)
#     return add_widget

