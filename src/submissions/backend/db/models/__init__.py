'''
Contains all models for sqlalchemy
'''
from sqlalchemy.orm import declarative_base, DeclarativeMeta
import logging

Base: DeclarativeMeta = declarative_base()
metadata = Base.metadata

logger = logging.getLogger(f"submissions.{__name__}")

# def find_subclasses(parent:Any, attrs:dict|None=None, rsl_number:str|None=None) -> Any:
#     """
#     Finds subclasses of a parent that does contain all 
#     attributes if the parent does not.
#     NOTE: Depreciated, moved to classmethods in individual base models.

#     Args:
#         parent (_type_): Parent class.
#         attrs (dict): Key:Value dictionary of attributes

#     Raises:
#         AttributeError: Raised if no subclass is found.

#     Returns:
#         _type_: Parent or subclass.
#     """    
#     if len(attrs) == 0 or attrs == None:
#         return parent
#     if any([not hasattr(parent, attr) for attr in attrs]):
#         # looks for first model that has all included kwargs
#         try:
#             model = [subclass for subclass in parent.__subclasses__() if all([hasattr(subclass, attr) for attr in attrs])][0]
#         except IndexError as e:
#             raise AttributeError(f"Couldn't find existing class/subclass of {parent} with all attributes:\n{pformat(attrs)}")
#     else:
#         model = parent
#     logger.debug(f"Using model: {model}")
#     return model

from .controls import Control, ControlType
from .kits import KitType, ReagentType, Reagent, Discount, KitTypeReagentTypeAssociation, SubmissionType, SubmissionTypeKitTypeAssociation
from .organizations import Organization, Contact
from .submissions import BasicSubmission, BacterialCulture, Wastewater, WastewaterArtic, WastewaterSample, BacterialCultureSample, BasicSample, SubmissionSampleAssociation, WastewaterAssociation

