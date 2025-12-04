from __future__ import annotations
import logging, sys
from typing import List
from pydantic import field_validator, Field
from backend.validators.pydant import PydAbstract

logger = logging.getLogger(f"submissions.{__name__}")


class PydReagent(PydAbstract):

    reagentrole: List[str] | List[dict] = Field(default_factory=list, description="Roles this reagent can fill.", repr=False)
    eol_ext: int = Field(default=0, description="Extension of Life (days)")
    name: str = Field(default="NA", validate_default=True, description="Name of this reagent.")
    comment: str = Field(default="", validate_default=True)
    cost_per_ml: float = Field(default=0.00, description="Cost of a millilitre of this reagent.")
    reagentlot: List[str] | List[dict] = Field(default_factory=list, description="Lot numbers of this reagent.", repr=False)
    
    
class PydTips(PydAbstract):

    tipslot: List[str] | List[dict] = Field(default_factory=list, description="Lots of this tip archetype", repr=False)
    manufacturer: str = Field(default="NA", description="Company that makes these tips")
    capacity: int = Field(default=1000, description="Maximum volume (uL).")
    ref: str = Field(default="NA", description="Reference number from manufacturer.")
    process: List[str] | List[dict] = Field(default_factory=list, description="List of processes using these tips.", repr=False) 
    

class PydReagentRole(PydAbstract):

    name: str = Field(default="NA", description="Name of this reagent role.")
    reagent: List[str] | List[dict] = Field(default_factory=list, description="Reagents filling this role.", alias="reagentrolereagentassociation", repr=False)
    proceduretype: List[str] | List[dict] = Field(default_factory=list, description="ProcedureTypes using this role", alias="proceduretypreagentroleassociation", repr=False)


class PydEquipmentRole(PydAbstract):

    name: str = Field(default="NA", description="Name of this equipment role.")
    equipment: List[str] | List[dict] = Field(default_factory=list, description="Equipment this role can use.", alias="equipmentroleequipmentassociation", repr=False)
    proceduretype: List[str] | List[dict] = Field(default_factory=list, description="ProcedureTypes using this role", alias="proceduretypequipmentroleassociation", repr=False)


class PydProcess(PydAbstract):
    
    name: str = Field(default="NA", description="Name of this process.")
    tips: List[str] | List[dict] = Field(default_factory=list, description="Tips used by this process.", repr=False)
    processversion: List[str] | List[dict] = Field(default_factory=list, description="Versions of this process.", repr=False)

    
class PydResultsType(PydAbstract):

    name: str = Field(default="NA", description="Brief description of this type.")
    results: List[dict] = Field(default_factory=list, repr=False)
    proceduretype: List[str] | List[dict] = Field(default_factory=list, description="ProcedureTypes using this type.", repr=False)


class PydSubmissionType(PydAbstract):
    
    name: str = Field(default="NA", description="Name of this Submission Type.")
    defaults: dict = Field(default_factory=dict, repr=False)
    clientsubmission: List[str] | List[dict] = Field(default_factory=list, repr=False)
    proceduretype: List[str] | List[dict] = Field(default_factory=list, description="ProcedureTypes this type uses.", repr=False)


class PydProcedureType(PydAbstract):
    
    name: str = Field(default="NA", description="Name of this Procedure Type.")
    plate_columns: int = Field(default=0, description="If this uses a plate, this is the column count.")
    plate_rows: int = Field(default=0, description="If this uses a plate, this is the row count.")
    plate_cost: float = Field(default=0.00, description="Minimum cost of running a plate.")
    procedure: List[str] | List[dict] = Field(default_factory=list, repr=False)
    submissiontype: List[str] | List[dict] = Field(default_factory=list, description="Submission Types using this type.", repr=False)
    resultstype: List[str] | List[dict] = Field(default_factory=list, description="Results Types used by this type.", repr=False)
    equipmentrole: List[str] | List[dict] = Field(default_factory=list, description="Equipment roles used by this type.", alias="proceduretypeequipmentroleassociation", repr=False)
    reagentrole: List[str] | List[dict] = Field(default_factory=list, description="Reagent roles used by this type.", alias="proceduretypereagentroleassociation", repr=False)
    testbool: bool = Field(default=False, description="A test boolean field.", repr=False)

