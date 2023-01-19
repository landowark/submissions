from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()
metadata = Base.metadata

from .controls import Control, ControlType
from .kits import KitType, ReagentType, Reagent
from .submissions import BasicSubmission, BacterialCulture, Wastewater
from .organizations import Organization, Contact
from .samples import WWSample, BCSample