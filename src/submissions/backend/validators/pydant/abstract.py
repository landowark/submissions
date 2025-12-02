
import logging
from datetime import datetime, timedelta
from types import GeneratorType
from typing import List, Tuple
from pydantic import field_validator, Field
from backend.db.models.procedures import Procedure, Reagent, Tips
from backend.validators.pydant import PydAbstract
from backend.db.models import BaseClass
from tools import Report, convert_nans_to_nones, report_result

logger = logging.getLogger(f"submissions.{__name__}")

class PydReagent(PydAbstract):

    reagentrole: List[str] | List[dict] = Field(default_factory=list, description="Roles this reagent can fill.")
    eol_ext: timedelta | int = Field(default_factory=timedelta, description="Extension of Life (days)")
    name: str = Field(default="NA", validate_default=True, description="Name of this reagent.")
    comment: str = Field(default="", validate_default=True)
    cost_per_ml: float = Field(default=0.00, description="Cost of a millilitre of this reagent.")
    reagentlot: List[str] | List[dict] = Field(default_factory=list, description="Lot numbers of this reagent.")

    def improved_dict(self) -> dict:
        """
        Constructs a dictionary consisting of model.fields and model.extras

        Returns:
            dict: Information dictionary
        """
        try:
            extras = list(self.model_extra.keys())
        except AttributeError:
            extras = []
        fields = list(self.model_fields.keys()) + extras
        return {k: getattr(self, k) for k in fields}

    @report_result
    def to_sql(self, procedure: Procedure | str = None) -> Tuple[Reagent, Report]:
        """
        Converts this instance into a backend.db.models.procedures.ReagentLot instance

        Returns:
            Tuple[Reagent, Report]: Reagent instance and result of function
        """
        from backend.db.models import ReagentLot, Reagent
        report = Report()
        if self.model_extra is not None:
            self.__dict__.update(self.model_extra)
        reagentlot, new = ReagentLot.query_or_create(lot=self.lot, name=self.name)
        if new:
            reagent = Reagent.query(name=self.name, limit=1)
            reagentlot.reagent = reagent
            reagentlot.expiry = self.expiry
            if isinstance(reagentlot.expiry, str):
                reagentlot.expiry = datetime.combine(datetime.strptime(reagentlot.expiry, "%Y-%m-%d"), datetime.max.time())
        return reagentlot, report


class PydTips(PydAbstract):

    name: str
    lot: str | None = Field(default=None)

    @report_result
    def to_sql(self) -> Tuple[Tips, Report]:
        """
        Convert this object to the SQL version for database storage.

        Returns:
            SubmissionTipsAssociation: Association between queried tips and procedure
        """
        from backend.db.models import TipsLot
        report = Report()
        tips = TipsLot.query(lot=self.lot, limit=1)
        return tips, report


class PydReagentRole(PydAbstract):

    name: str
    eol_ext: timedelta | int | None
    uses: dict | None
    required: int | None = Field(default=1)

    @field_validator("eol_ext")
    @classmethod
    def int_to_timedelta(cls, value):
        if isinstance(value, int):
            return timedelta(days=value)
        return value


class PydEquipmentRole(PydAbstract):

    name: str
    equipment: List[str]
    process: List[str] | None

    @field_validator("process", mode="before")
    @classmethod
    def expand_processes(cls, value):
        if isinstance(value, GeneratorType):
            value = [item for item in value]
        return value


class PydProcess(PydAbstract, extra="allow"):
    name: str
    version: str = Field(default="1.0")
    tips: List[PydTips]

    @field_validator("tips", mode="before")
    @classmethod
    def enforce_list(cls, value):
        if not isinstance(value, list):
            value = [value]
        output = []
        for v in value:
            if issubclass(v.__class__, BaseClass):
                output.append(v.name)
            else:
                output.append(v)
        return output

    @field_validator("tips", mode="before")
    @classmethod
    def validate_tips(cls, value):
        if not value:
            return []
        value = [item for item in value if item]
        return value

    @field_validator("version", mode="before")
    @classmethod
    def enforce_float_string(cls, value):
        if isinstance(value, float):
            value = str(value)
        return value
