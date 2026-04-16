"""
All abstract pyd models and associations between abstracts.
"""
from __future__ import annotations
import logging, sys, numpy as np
from pprint import pformat
from datetime import timedelta
from typing import List, TYPE_CHECKING
from pydantic import computed_field, field_validator, Field
from backend.validators.pydant import PydAbstract
from tools import jinja_template_loading
if TYPE_CHECKING:
    from .concrete import PydSample

logger = logging.getLogger(f"submissions.{__name__}")


class PydReagent(PydAbstract):

    reagentrole: List[str] | List[dict] = Field(default_factory=list, description="Roles this reagent can fill.", repr=False)
    eol_ext: int = Field(default=0, description="Extension of Life (days)")
    name: str = Field(default="NA", validate_default=True, description="Name of this reagent.")
    manufacturer: str | None = Field(default="NA", description="Company that makes this reagent.")
    ref: str | None = Field(default="NA", description="Manufacturer's reference number")
    comment: str = Field(default="", validate_default=True)
    cost_per_ml: float = Field(default=0.00, description="Cost of a millilitre of this reagent.")
    reagentlot: List[str] | List[dict] = Field(default_factory=list, description="Lot numbers of this reagent.", repr=False)

    @field_validator("manufacturer", "ref")
    @classmethod
    def validate_optional_strings(cls, value):
        if value is None:
            return "NA"
        return value
    
    @field_validator("eol_ext", mode="before")
    @classmethod
    def timedelta_to_int(cls, value):
        if isinstance(value, timedelta):
            return value.days
        return value
    
    def to_sql(self, update: bool = True):
        # self.name = self.name.replace("-", ":")
        from backend.db.models import Reagent
        self.sql_instance: Reagent = super().to_sql(update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.reagentrole = self.reagentrole
        self.sql_instance.reagentlot = self.reagentlot
        return self.sql_instance, None


class PydTips(PydAbstract):

    tipslot: List[str] | List[dict] = Field(default_factory=list, description="Lots of this tip archetype", repr=False)
    manufacturer: str = Field(default="NA", description="Company that makes these tips")
    capacity: int = Field(default=1000, description="Maximum volume (uL).")
    ref: str = Field(default="NA", description="Reference number from manufacturer.")
    process: List[str] | List[dict] = Field(default_factory=list, description="List of processes using these tips.", repr=False)
    cost_per_tip: float = Field(default=0.00, description="Cost of a single tip.")

    @computed_field
    @property
    def name(self) -> str:
        return f"{self.manufacturer} - {self.ref}({self.capacity}uL)"

    @property
    def improved_dict(self) -> dict:
        output = super().improved_dict
        output['name'] = self.name
        return output

    def to_sql(self, update: bool = True):
        from backend.db.models import Tips
        self.sql_instance: Tips = super().to_sql(update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.tipslot = self.tipslot
        self.sql_instance.process = self.process
        return self.sql_instance, None 
    

class PydReagentRole(PydAbstract):

    name: str = Field(default="NA", description="Name of this reagent role.")
    reagent: List[str] | List[dict] = Field(default_factory=list, description="Reagents filling this role.", repr=False)
    proceduretype: List[str] | List[dict] = Field(default_factory=list, description="ProcedureTypes using this role", repr=False)

    def to_sql(self, update: bool = True):
        from backend.db.models import ReagentRole
        self.sql_instance: ReagentRole = super().to_sql(update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.proceduretype = self.proceduretype
        self.sql_instance.reagent = self.reagent
        return self.sql_instance, None


class PydEquipmentRole(PydAbstract):

    name: str = Field(default="NA", description="Name of this equipment role.")
    equipment: List[str] | List[dict] = Field(default_factory=list, description="Equipment this role can use.", repr=False)
    proceduretype: List[str] | List[dict] = Field(default_factory=list, description="ProcedureTypes using this role", repr=False)

    def to_sql(self, update: bool = True):
        from backend.db.models import EquipmentRole
        self.sql_instance: EquipmentRole = super().to_sql(update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.proceduretype = self.proceduretype
        self.sql_instance.equipment = self.equipment
        return self.sql_instance, None


class PydProcess(PydAbstract):
    
    name: str = Field(default="NA", description="Name of this process.")
    tips: List[str] | List[dict] = Field(default_factory=list, description="Tips used by this process.", repr=False)
    processversion: List[str] | List[dict] = Field(default_factory=list, description="Versions of this process.", repr=False)

    def to_sql(self, update: bool = True):
        from backend.db.models import Process
        self.sql_instance: Process = super().to_sql(update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.tips = self.tips
        self.sql_instance.processversion = self.processversion
        return self.sql_instance, None

    
class PydResultsType(PydAbstract):

    name: str = Field(default="NA")
    results: List[str] | List[dict] = Field(default_factory=list, repr=False)
    proceduretype: List[str] | List[dict] = Field(default_factory=list, repr=False)

    def to_sql(self, update: bool = True):
        self.sql_instance = super().to_sql(update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.proceduretype = self.proceduretype
        # NOTE: At this point, results will likely be an empty list.
        self.sql_instance.results = self.results
        return self.sql_instance, None


class PydSubmissionType(PydAbstract):
    
    name: str = Field(default="NA", description="Name of this Submission Type.")
    defaults: dict = Field(default_factory=dict, repr=False)
    file_name_template: str = Field(default="", repr=False, validate_default=True)
    turnaround_time: int = Field(default=3, description="Days allowed for processing.", repr=False)
    abbreviation: str = Field(default="XX", description="Shorthand to be used in naming convention (RSL-XX-YYYYMMMDD-1).")
    clientsubmission: List[str] | List[dict] = Field(default_factory=list, repr=False)
    proceduretype: List[str] | List[dict] = Field(default_factory=list, description="ProcedureTypes this type uses.", repr=False)

    @field_validator("file_name_template", mode="before")
    @classmethod
    def set_default_template(cls, value):
        if value == None:
            value = "{{rsl_plate_number}}{% if _clientsubmission %}_{{_clientsubmission.submitter_plate_id}}{% endif %}_{{_completed_date}}"
        return value

    @field_validator("file_name_template")
    @classmethod
    def validate_template(cls, value: str) -> str | None:
        if value == "":
            value = "{{rsl_plate_number}}{% if _clientsubmission %}_{{_clientsubmission.submitter_plate_id}}{% endif %}_{{_completed_date}}"
        return value
    
    @field_validator("proceduretype")
    @classmethod
    def validate_proceduretype(cls, value, values) -> List[str]:
        if not value and values.data.get("name", "Default SubmissionType") == "Default SubmissionType":
            from backend.db.models import ProcedureType
            value = [item.name for item in ProcedureType.query()]
        return value
    
    @field_validator("abbreviation", mode="before")
    @classmethod
    def validate_abbreviation(cls, value):
        if not value:
            value = "XX"
        return value

    def update_instrumentedattribute(self, key, value):
        """
        Updates all instrumented attributes to match the current state of the pydantic model.
        """
        if self.name == "Default SubmissionType":
            logger.error("Cannot update Default SubmissionType directly.")
            return
        super().update_instrumentedattribute(key, value)
    
    def remove_relationship(self, field: str, value: str):
        """
        Removes a relationship from a list field. (Overrides PydBaseClass method)
        The override is largely redundant as this is also handled in javascript,
        but this double-checks that the "Default SubmissionType" is not removed.

        Args:
            field (str): Field name
            value (str): The value to remove from the relationship.
        """
        if field == "proceduretype" and self.name == "Default SubmissionType":
            logger.error("Cannot remove proceduretypes from Default SubmissionType.")
            return
        super().remove_relationship(field, value)

    def to_sql(self, update: bool = True):
        from backend.db.models import SubmissionType
        self.sql_instance: SubmissionType = super().to_sql(update)
        self.sql_instance.file_name_template = self.file_name_template
        self.sql_instance.abbreviation = self.abbreviation
        if not update:
            return self.sql_instance, None
        self.sql_instance.proceduretype = self.proceduretype
        self.sql_instance.clientsubmission = self.clientsubmission
        return self.sql_instance, None


class PydProcedureType(PydAbstract):
    
    name: str = Field(default="NA", description="Name of this Procedure Type.")
    plate_columns: int = Field(default=0, description="If this uses a plate, this is the column count.")
    plate_rows: int = Field(default=0, description="If this uses a plate, this is the row count.")
    plate_cost: float = Field(default=0.00, description="Minimum cost of running a plate.")
    procedure: List[str] | List[dict] = Field(default_factory=list, repr=False)
    submissiontype: List[str] | List[dict] = Field(default_factory=list, description="Submission Types using this type.", repr=False, validate_default=True)
    resultstype: List[str] | List[dict] = Field(default_factory=list, description="Results Types used by this type.", repr=False)
    equipmentrole: List[str] | List[dict] = Field(default_factory=list, description="Equipment roles used by this type.", repr=False)
    reagentrole: List[str] | List[dict] = Field(default_factory=list, description="Reagent roles used by this type.", repr=False)
    
    @field_validator("submissiontype", "resultstype", "equipmentrole", "reagentrole", mode="before")
    @classmethod
    def validate_lists(cls, value) -> List[str]:
        if value is None:
            return []
        return value

    @field_validator("submissiontype")
    @classmethod
    def validate_submissiontype(cls, value) -> List[str]:
        if not value:
            value = ["Default SubmissionType"]
        return value

    def remove_relationship(self, field: str, value: str):
        """
        Removes a relationship from a list field. (Overrides PydBaseClass method)
        The override is largely redundant as this is also handled in javascript,
        but this double-checks that the "Default SubmissionType" is not removed.

        Args:
            field (str): Field name
            value (str): The value to remove from the relationship.
        """
        if field == "submissiontype" and value == "Default SubmissionType":
            logger.error("Cannot remove default submission type.")
            return
        super().remove_relationship(field=field, value=value)

    def construct_plate_map(self, sample_dicts: List[PydSample], creation:bool=True, vw_modifier:float=1.0) -> str:
        """
        Constructs an html based plate map for procedure details.

        Args:
            sample_list (list): List of procedure sample
            plate_rows (int, optional): Number of rows in the plate. Defaults to 8.
            plate_columns (int, optional): Number of columns in the plate. Defaults to 12.

        Returns:
            str: html output string.
        """
        if self.plate_rows == 0 or self.plate_columns == 0:
            return "<br/>"
        sample_dicts = self.pad_sample_dicts(sample_dicts=sample_dicts)
        vw = round((-0.07 * len(sample_dicts)) + (12.2 * vw_modifier), 1)
        # NOTE: An overly complicated list comprehension create a list of sample locations
        # NOTE: next will return a blank cell if no value found for row/column
        env = jinja_template_loading()
        template = env.get_template("support/plate_map.html")
        html = template.render(plate_rows=self.plate_rows, plate_columns=self.plate_columns, samples=sample_dicts,
                               vw=vw, creation=creation)
        return html + "<br/>"
    
    def pad_sample_dicts(self, sample_dicts: List[PydSample]) -> List[PydSample]:
        """
        Pads out a list of sample dicts to the length of an associated plate.
        
        Returns:
            List[PydSample]: Padded list.
        """
        from backend.validators.pydant import PydSample
        output = []
        for row, column in self.ranked_plate.values():

            sample = next((sample for sample in sample_dicts if sample.row == row and sample.column == column),
                          PydSample(sample_id="", row=row, column=column, enabled=False, background_color="white"))
            output.append(sample)
        return output
    
    @property
    def ranked_plate(self) -> dict:
        """
        Creates a dictionary of rows and columns for an associated plate.

        Returns:
            dict: (rank: {row: value, column: value})
        """
        matrix = np.array([[0 for yyy in range(1, self.plate_rows + 1)] for xxx in range(1, self.plate_columns + 1)])
        return {iii: (item[0][1] + 1, item[0][0] + 1) for iii, item in enumerate(np.ndenumerate(matrix), start=1)}

    def to_sql(self, update: bool = True):
        from backend.db.models import ProcedureType
        self.sql_instance: ProcedureType = super().to_sql(update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.procedure = self.procedure
        self.sql_instance.submissiontype = self.submissiontype
        self.sql_instance.equipmentrole = self.equipmentrole
        self.sql_instance.reagentrole = self.reagentrole
        self.sql_instance.resultstype = self.resultstype
        return self.sql_instance, None

    @property
    def allowed_result_methods(self) -> List[str]:
        return self.sql_instance.allowed_result_methods


class PydProcedureTypeReagentRoleAssociation(PydAbstract):

    proceduretype: str = Field(default="NA")
    reagentrole: str = Field(default="NA")
    last_used: str = Field(default="NA")

    @field_validator("last_used", mode="before")
    @classmethod
    def create_last_used(cls, value):
        if value is None:
            return "NA"
        return value
    
    @classproperty
    def aliases(cls) -> List[str]:
        return super().aliases + ["reagentroleproceduretypeassociation"]
    
    def to_sql(self, update: bool = True):
        from backend.db.models import ProcedureTypeReagentRoleAssociation
        self.sql_instance: ProcedureTypeReagentRoleAssociation = super().to_sql(update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.proceduretype = self.proceduretype
        self.sql_instance.reagentrole = self.reagentrole
        return self.sql_instance, None


class PydProcedureTypeEquipmentRoleAssociation(PydAbstract):

    proceduretype: str = Field(default="NA")
    equipmentrole: str = Field(default="NA")
    static: bool = Field(default=True, description="If true, this equipment role is always required for the procedure type.")

    @field_validator("static", mode="before")
    @classmethod
    def int_to_bool(cls, value):
        if isinstance(value, int):
            value = bool(value)
        return value
    
    @field_validator("static")
    @classmethod
    def enforce_active(cls, value):
        if value is None:
            value = True
        if isinstance(value, str):
            if value.lower() in ["false", "0", "no", "off"]:
                value = False
            else:
                value = True
        return value
    
    @classproperty
    def aliases(cls) -> List[str]:
        return super().aliases + ["equipmentroleproceduretypeassociation"]

    def to_sql(self, update: bool = True):
        from backend.db.models import ProcedureTypeEquipmentRoleAssociation
        self.sql_instance: ProcedureTypeEquipmentRoleAssociation = super().to_sql(update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.proceduretype = self.proceduretype
        self.sql_instance.equipmentrole = self.equipmentrole
        return self.sql_instance, None


class PydEquipmentRoleEquipmentAssociation(PydAbstract):

    equipmentrole: str = Field(default="NA")
    equipment: str = Field(default="NA")
    process: List[str] | List[dict] = Field(default_factory=list, description="Processes using this equipment role-equipment association.")

    @classproperty
    def aliases(cls) -> List[str]:
        return super().aliases + ["equipmentequipmentroleassociation"]

    def to_sql(self, update: bool = True):
        from backend.db.models import EquipmentRoleEquipmentAssociation
        self.sql_instance: EquipmentRoleEquipmentAssociation = super().to_sql(update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.equipmentrole = self.equipmentrole
        self.sql_instance.equipment = self.equipment
        self.sql_instance.process = self.process
        return self.sql_instance, None


class PydReagentRoleReagentAssociation(PydAbstract):

    reagentrole: str = Field(default="NA") 
    reagent: str = Field(default="NA")
    ml_used_per_sample: float = Field(default=0.000, description="Amount of this reagent used per sample")

    @field_validator("ml_used_per_sample", mode="before")
    @classmethod
    def set_ml(cls, value):
        if value is None:
            value = 0.000
        return value

    @classproperty
    def aliases(cls) -> List[str]:
        return super().aliases + ["reagentreagentroleassociation"]

    def to_sql(self, update: bool = True):
        from backend.db.models import ReagentRoleReagentAssociation
        self.sql_instance: ReagentRoleReagentAssociation = super().to_sql(update)
        if not update:
            return self.sql_instance, None
        self.sql_instance.reagentrole = self.reagentrole
        self.sql_instance.reagent = self.reagent
        return self.sql_instance, None
