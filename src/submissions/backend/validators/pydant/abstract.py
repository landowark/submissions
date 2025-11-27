


class PydReagent(PydAbstract):

    reagentrole: str | None
    name: str | None = Field(default=None, validate_default=True)
    missing: bool = Field(default=True)
    comment: str | None = Field(default="", validate_default=True)

    @field_validator('comment', mode='before')
    @classmethod
    def create_comment(cls, value):
        if value is None:
            return ""
        return value

    # @field_validator("reagentrole", mode='before')
    # @classmethod
    # def remove_undesired_types(cls, value):
    #     match value:
    #         case "atcc":
    #             return None
    #         case _:
    #             return value

    @field_validator("reagentrole")
    @classmethod
    def rescue_type_with_lookup(cls, value, values):
        if value is None and values.data['lot'] is not None:
            try:
                return Reagent.query(lot=values.data['lot']).name
            except AttributeError:
                return value
        return value

    @field_validator("name", mode="before")
    @classmethod
    def enforce_name(cls, value, values):
        if value is not None:
            return convert_nans_to_nones(str(value).strip())
        else:
            return values.data['reagentrole'].strip()

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


class PydTips(PydBaseClass):

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

