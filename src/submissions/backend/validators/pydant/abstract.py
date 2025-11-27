


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


class PydReagentRole(BaseModel):

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


class PydEquipmentRole(BaseModel):

    name: str
    equipment: List[PydEquipment]
    process: List[str] | None

    @field_validator("process", mode="before")
    @classmethod
    def expand_processes(cls, value):
        if isinstance(value, GeneratorType):
            value = [item for item in value]
        return value

    def to_form(self, parent, used: list) -> RoleComboBox:
        """
        Creates a widget for user input into this class.

        Args:
            parent (_type_): parent widget
            used (list): list of equipment already added to procedure

        Returns:
            RoleComboBox: widget
        """
        from frontend.widgets.equipment_usage import RoleComboBox
        return RoleComboBox(parent=parent, role=self, used=used)


class PydProcess(PydBaseClass, extra="allow"):
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

    @report_result
    def to_sql(self):
        from backend.db.models import ProcessVersion
        report = Report()
        name = self.name.split("-")[0]
        # NOTE: can't use query_or_create due to name not being part of ProcessVersion
        logger.debug(f"Querying name: {name}, version: {self.version}")
        instance = ProcessVersion.query(name=name, version=float(self.version), limit=1)
        if not instance:
            logger.warning(f"Gonna have to make a new process version {self.version}")
            instance = ProcessVersion()
        logger.debug(f"Got instance: {instance.__dict__}")
        return instance, report

