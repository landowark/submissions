"""
All abstract pyd models and associations between abstracts.
"""
from __future__ import annotations
import re
import logging, sys, numpy as np
from pprint import pformat
from datetime import timedelta
from typing import List, TYPE_CHECKING, Literal, Annotated
from pydantic import computed_field, field_validator, Field
from backend.validators.pydant import PydAbstract, RelationshipField
from backend.validators.shared import coerce_int_to_bool, coerce_none_to_na
from tools import jinja_template_loading
if TYPE_CHECKING:
    from .concrete import PydSample

logger = logging.getLogger(f"submissions.{__name__}")


class PydReagent(PydAbstract):

    reagentrole: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, description="Roles this reagent can fill.", repr=False)
    eol_ext: int = Field(default=0, description="Extension of Life (days)")
    name: str = Field(default="NA", validate_default=True, description="Name of this reagent.")
    manufacturer: str | None = Field(default="NA", description="Company that makes this reagent.")
    ref: str | None = Field(default="NA", description="Manufacturer's reference number")
    comment: str = Field(default="", validate_default=True)
    cost_per_ml: float = Field(default=0.00, description="Cost of a millilitre of this reagent.")
    reagentlot: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, description="Lot numbers of this reagent.", repr=False)

    _validate_na = field_validator("manufacturer", "ref")(coerce_none_to_na)
    
    @field_validator("eol_ext", mode="before")
    @classmethod
    def timedelta_to_int(cls, value):
        if isinstance(value, timedelta):
            return value.days
        return value
    

class PydTips(PydAbstract):

    tipslot: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, description="Lots of this tip archetype", repr=False)
    manufacturer: str = Field(default="NA", description="Company that makes these tips")
    capacity: int = Field(default=1000, description="Maximum volume (uL).")
    ref: str = Field(default="NA", description="Reference number from manufacturer.")
    process: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, description="List of processes using these tips.", repr=False)
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


class PydReagentRole(PydAbstract):

    name: str = Field(default="NA", description="Name of this reagent role.")
    reagent: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, description="Reagents filling this role.", repr=False)
    proceduretype: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, description="ProcedureTypes using this role", repr=False)


class PydEquipmentRole(PydAbstract):

    name: str = Field(default="NA", description="Name of this equipment role.")
    equipment: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, description="Equipment this role can use.", repr=False)
    proceduretype: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, description="ProcedureTypes using this role", repr=False)


class PydProcess(PydAbstract):
    
    name: str = Field(default="NA", description="Name of this process.")
    tips: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, description="Tips used by this process.", repr=False)
    processversion: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, description="Versions of this process.", repr=False)


class PydResultsType(PydAbstract):

    name: str = Field(default="NA")
    results: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, repr=False)
    proceduretype: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, repr=False)


class PydSubmissionType(PydAbstract):
    
    name: str = Field(default="NA", description="Name of this Submission Type.")
    defaults: dict = Field(default_factory=dict, repr=False)
    file_name_template: str = Field(default="", repr=False, validate_default=True)
    turnaround_time: int = Field(default=3, description="Days allowed for processing.", repr=False)
    abbreviation: str = Field(default="XX", description="Shorthand to be used in naming convention (RSL-XX-YYYYMMMDD-1).")
    clientsubmission: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, repr=False)
    proceduretype: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, description="ProcedureTypes this type uses.", repr=False)

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


class PydProcedureType(PydAbstract):
    
    name: str = Field(default="NA", description="Name of this Procedure Type.")
    plate_columns: int = Field(default=0, description="If this uses a plate, this is the column count.")
    plate_rows: int = Field(default=0, description="If this uses a plate, this is the row count.")
    plate_cost: float = Field(default=0.00, description="Minimum cost of running a plate.")
    procedure: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, repr=False)
    submissiontype: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, description="Submission Types using this type.", repr=False, validate_default=True)
    resultstype: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, description="Results Types used by this type.", repr=False)
    equipmentrole: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, description="Equipment roles used by this type.", repr=False)
    reagentrole: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, description="Reagent roles used by this type.", repr=False)
    
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
        for row, column in self.make_ranked_plate().values():

            sample = next((sample for sample in sample_dicts if sample.row == row and sample.column == column),
                          PydSample(sample_id="", row=row, column=column, enabled=False, background_color="white"))
            output.append(sample)
        return output
    
    def make_ranked_plate(self, direction: Literal["row", "col"] = "row") -> dict:
        """
        Creates a dictionary of rows and columns for an associated plate.

        Returns:
            dict: (rank: {row: value, column: value})
        """
        if direction == "row":
            matrix = np.array([[0 for yyy in range(1, self.plate_rows + 1)] for xxx in range(1, self.plate_columns + 1)])
        else:
            matrix = np.array([[0 for xxx in range(1, self.plate_columns + 1 )] for yyy in range(1, self.plate_rows + 1 )])
        return {iii: (item[0][1] + 1, item[0][0] + 1) for iii, item in enumerate(np.ndenumerate(matrix), start=1)}

    @property
    def allowed_result_methods(self) -> List[str]:
        return self.sql_instance.allowed_result_methods
    
    @property
    def preprocessing_methods(self):
        return self.sql_instance.preprocessing_methods
    
    def get_well_index(self, cell_id: str = None, row_idx: int = None, col_idx: int = None, direction: Literal['col', 'row'] = 'col'):
        """
        Finds the 1-based index of a cell.
        direction='col': Top-to-bottom, then left-to-right (A1, B1, C1...)
        direction='row': Left-to-right, then top-to-bottom (A1, A2, A3...)
        """
        if row_idx is None or col_idx is None:
            if not cell_id:
                raise ValueError("Either cell_id or both row_idx and col_idx must be provided.")
                
            match = re.match(r"([A-Z]+)([0-9]+)", cell_id, re.I)
            if not match:
                raise ValueError("Invalid cell ID format.")
            
            row_str, col_str = match.groups()
            
            # Convert Row Letter to 0-based index
            row_idx = 0
            for char in row_str.upper():
                row_idx = row_idx * 26 + (ord(char) - ord('A') + 1)
            row_idx -= 1 
            
            # Convert Column to 0-based index
            col_idx = int(col_str) - 1

        else:
            row_idx -= 1
            col_idx -= 1
        
        # Validation
        if row_idx >= self.plate_rows or col_idx >= self.plate_columns:
            raise IndexError(f"Indices ({row_idx}, {col_idx}) are outside the {self.plate_rows}x{self.plate_columns} grid.")

        if direction.lower() == 'col':
            # Vertical: (Columns passed * rows per column) + current row
            return (col_idx * self.plate_rows) + (row_idx + 1)
        else:
            # Horizontal: (Rows passed * columns per row) + current column
            return (row_idx * self.plate_columns) + (col_idx + 1)


class PydProcedureTypeReagentRoleAssociation(PydAbstract):

    proceduretype: Annotated[str, RelationshipField(uselist=False)] = Field(default="NA")
    reagentrole: Annotated[str, RelationshipField(uselist=False)] = Field(default="NA")
    always_used: bool = Field(default=True, description="If true, this reagent role is always required for the procedure type.")
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
    

class PydProcedureTypeEquipmentRoleAssociation(PydAbstract):

    proceduretype: Annotated[str, RelationshipField(uselist=False)] = Field(default="NA")
    equipmentrole: Annotated[str, RelationshipField(uselist=False)] = Field(default="NA")
    always_used: bool = Field(default=True, description="If true, this equipment role is always required for the procedure type.")

    _validate_na = field_validator("always_used", mode="before")(coerce_int_to_bool)
    
    @classproperty
    def aliases(cls) -> List[str]:
        return super().aliases + ["equipmentroleproceduretypeassociation"]


class PydEquipmentRoleEquipmentAssociation(PydAbstract):

    equipmentrole: Annotated[str, RelationshipField(uselist=False)] = Field(default="NA")
    equipment: Annotated[str, RelationshipField(uselist=False)] = Field(default="NA")
    process: Annotated[List[str | dict], RelationshipField(uselist=True)] = Field(default_factory=list, description="Processes using this equipment role-equipment association.")

    @classproperty
    def aliases(cls) -> List[str]:
        return super().aliases + ["equipmentequipmentroleassociation"]


class PydReagentRoleReagentAssociation(PydAbstract):

    reagentrole: Annotated[str, RelationshipField(uselist=False)] = Field(default="NA") 
    reagent: Annotated[str, RelationshipField(uselist=False)] = Field(default="NA")
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
