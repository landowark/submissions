'''
Contains all models for sqlalchemy
'''
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
metadata = Base.metadata

from .controls import Control, ControlType
from .kits import KitType, ReagentType, Reagent, Discount, KitTypeReagentTypeAssociation, SubmissionType, SubmissionTypeKitTypeAssociation
from .organizations import Organization, Contact
# from .samples import WWSample, BCSample, BasicSample
from .submissions import BasicSubmission, BacterialCulture, Wastewater, WastewaterArtic, WastewaterSample, BacterialCultureSample, BasicSample, SubmissionSampleAssociation, WastewaterAssociation
