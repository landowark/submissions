'''
Contains all models for sqlalchemy
'''
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
metadata = Base.metadata

from .controls import Control, ControlType
from .kits import KitType, ReagentType, Reagent, Discount
from .organizations import Organization, Contact
from .samples import WWSample, BCSample
from .submissions import BasicSubmission, BacterialCulture, Wastewater, WastewaterArtic
