
class PydResults(PydConcrete, arbitrary_types_allowed=True):

    result: dict = Field(default={})
    result_type: str = Field(default="NA")
    img: None | bytes = Field(default=None)
    parent: Any | None = Field(default=None)
    date_analyzed: datetime | None = Field(default=None)

    @field_validator("date_analyzed")
    @classmethod
    def set_today(cls, value):
        match value:
            case str():
                value = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            case datetime():
                pass
            case date():
                value = datetime.combine(value, datetime.max.time())
            case _:
                value = datetime.now()
        return value

    def to_sql(self):
        from backend.db.models import Results, ProcedureSampleAssociation, Procedure
        sql, _ = Results.query_or_create(result_type=self.result_type, result=self.results)
        try:
            check = sql.image
        except FileNotFoundError:
            check = False
        if not check:
            sql.image = self.img
        if not sql.date_analyzed:
            sql.date_analyzed = self.date_analyzed
        match self.parent:
            case ProcedureSampleAssociation():
                sql.sampleprocedureassociation = self.parent
            case Procedure():
                sql.procedure = self.parent
            case _:
                logger.error("Improper association found.")
        return sql


class PydReagentLot(PydConcrete):

    lot: str | None
    name: str | None = Field(default=None) #:attr Derived from Reagent
    expiry: date | datetime | Literal['NA'] | None = Field(default=None, validate_default=True)
    missing: bool = Field(default=True)
    comment: str | None = Field(default="", validate_default=True)


class PydSample(PydConcrete):

    sample_id: str
    submission_rank: int | List[int] | None = Field(default=0, validate_default=True)
    enabled: bool = Field(default=True)
    row: int = Field(default=0)
    column: int = Field(default=0)
    results: List[PydResults] | PydResults = Field(default=[])
    is_control: int = Field(default=0)

    @field_validator('is_control', mode='before')
    @classmethod
    def enforce_value_range(cls, value):
        if value is None:
            value = 0
        if value >= 1:
            value = 1
        elif value <= -1:
            value = -1
        else:
            value = 0
        return value

    @field_validator("sample_id", mode="before")
    @classmethod
    def int_to_str(cls, value):
        return str(value)

    @field_validator("sample_id")
    @classmethod
    def strip_sub_id(cls, value):
        match value:
            case dict():
                value['value'] = value['value'].strip().upper()
            case str():
                value = value.strip().upper()
            case _:
                pass
        return value

    @field_validator("row", mode="before")
    @classmethod
    def row_str_to_int(cls, value):
        if isinstance(value, str):
            try:
                value = row_keys[value]
            except KeyError:
                value = 0
        return value

    @field_validator("column", mode="before")
    @classmethod
    def column_str_to_int(cls, value):
        if isinstance(value, str):
            value = 0
        return value

    def improved_dict(self, dictionaries: bool = True) -> dict:
        output = super().improved_dict(dictionaries=dictionaries)
        output['name'] = self.sample_id
        return output

    def to_sql(self):
        sql = super().to_sql()
        sql._misc_info["submission_rank"] = self.submission_rank
        return sql


class PydEquipment(PydBaseClass):

    asset_number: str
    name: str
    nickname: str | None
    processes: List[PydProcess] | PydProcess | None
    processversion: PydProcessVersion | None = Field(default=None)
    equipmentrole: str | PydEquipmentRole | None
    tips: List[PydTips] | PydTips | None = Field(default=[])

    @field_validator('equipmentrole', mode='before')
    @classmethod
    def get_role_name(cls, value):
        from backend.db.models import EquipmentRole
        match value:
            case list():
                value = value[0]
            case GeneratorType():
                value = next(value)
            case _:
                pass
        if isinstance(value, EquipmentRole):
            value = value.name
        return value

    @field_validator('processes', mode='before')
    @classmethod
    def process_to_pydantic(cls, value, values):
        from backend.db.models import ProcessVersion, Process
        if isinstance(value, GeneratorType):
            value = [item for item in value]
        value = convert_nans_to_nones(value)
        if not value:
            value = []
        match value:
            case ProcessVersion():
                value = value.to_pydantic(pyd_model_name="PydProcess")
            case _:
                try:
                    for process in value:
                        match process:
                            case Process():
                                if values.data['name'] in [item.name for item in process.equipment]:
                                    return process.to_pydantic()
                                return None
                            case str():
                                return process
                except AttributeError as e:
                    logger.error(f"Process Validation error due to {e}")
                    value = []
        return value

    @field_validator('tips', mode='before')
    @classmethod
    def tips_to_pydantic(cls, value, values):
        from backend.db.models import TipsLot
        if isinstance(value, GeneratorType):
            value = [item for item in value]
        value = convert_nans_to_nones(value)
        if not value:
            value = []
        match value:
            case TipsLot():
                value = value.to_pydantic(pyd_model_name="PydTips")
            case dict():
                value = PydTips(**value)
            case _:
                pass
        return value

    @report_result
    def to_sql(self, procedure: Procedure | str = None, proceduretype: ProcedureType | str = None) -> Tuple[
        Equipment, ProcedureEquipmentAssociation]:
        """
        Creates Equipment and SubmssionEquipmentAssociations for this PydEquipment

        Args:
            procedure ( BasicRun | str ): BasicRun of interest

        Returns:
            Tuple[Equipment, RunEquipmentAssociation]: SQL objects
        """
        from backend.db.models import Equipment, ProcedureEquipmentAssociation, Process, EquipmentRole
        report = Report()
        if isinstance(procedure, str):
            procedure = Procedure.query(name=procedure)
        # if isinstance(proceduretype, str):
        #     proceduretype = ProcedureType.query(name=proceduretype)
        equipment = Equipment.query(asset_number=self.asset_number)
        if equipment is None:
            logger.error("No equipment found. Returning None.")
            return None, None
        if procedure is not None:
            # NOTE: Need to make sure the same association is not added to the procedure
            try:
                assoc, new = ProcedureEquipmentAssociation.query_or_create(equipment=equipment, procedure=procedure,
                                                                           equipmentrole=self.equipmentrole, limit=1)
            except TypeError as e:
                logger.error(f"Couldn't get association due to {e}, returning...")
                return None, None
            if new:
                # TODO: This seems precarious. What if there is more than one process?
                # NOTE: It looks like the way fetching the process is done in the SQL model, this shouldn't be a problem, but I'll include a failsafe.
                if len(self.processes) > 1:
                    process = Process.query(proceduretype=procedure.submissiontype, equipmentrole=self.role, limit=1)
                else:
                    process = Process.query(name=self.processes[0], limit=1)
                if process is None:
                    logger.error(f"Found unknown process: {process}.")
                assoc.process = process
                assoc.equipmentrole = EquipmentRole.query(name=self.equipmentrole, limit=1)
            else:
                logger.warning(f"Found already existing association: {assoc}")
                assoc = None
        else:
            logger.warning(f"No procedure found")
            assoc = None
        return equipment, assoc, report

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


class PydContact(PydConcrete):

    name: str
    phone: str | None
    email: str | None

    @field_validator("phone")
    @classmethod
    def enforce_phone_number(cls, value):
        area_regex = re.compile(r"^\(?(\d{3})\)?(-| )?")
        if len(value) > 8:
            match = area_regex.match(value)
            value = area_regex.sub(f"({match.group(1).strip()}) ", value)
        return value

    @report_result
    def to_sql(self) -> Tuple[Contact, Report]:
        """
        Converts this instance into a backend.db.models.organization. Contact instance.
        Does not query for existing contact.

        Returns:
            Contact: Contact instance
        """
        report = Report()
        instance = Contact.query(name=self.name, phone=self.phone, email=self.email)
        if not instance or isinstance(instance, list):
            instance = Contact()
        try:
            all_fields = self.model_fields + self.model_extra
        except TypeError:
            all_fields = self.model_fields
        for field in all_fields:
            value = getattr(self, field)
            match field:
                case "organization":
                    value = [ClientLab.query(name=value)]
                case _:
                    pass
            try:
                instance.__setattr__(field, value)
            except AttributeError as e:
                logger.error(f"Could not set {instance} {field} to {value} due to {e}")
        return instance, report


class PydClientLab(PydConcrete):

    name: str
    cost_centre: str
    contact: List[PydContact] | None

    @field_validator("contact", mode="before")
    @classmethod
    def string_to_list(cls, value):
        if isinstance(value, str):
            value = Contact.query(name=value)
            try:
                value = [value.to_pydantic()]
            except AttributeError:
                return None
        return value

    @report_result
    def to_sql(self) -> ClientLab:
        """
        Converts this instance into a backend.db.models.organization.Organization instance.

        Returns:
           Organization: Organization instance
        """
        report = Report()
        instance = ClientLab()
        for field in self.model_fields:
            match field:
                case "contact":
                    value = getattr(self, field)
                    if value:
                        value = [item.to_sql() for item in value if item]
                case _:
                    value = getattr(self, field)
            if value:
                setattr(instance, field, value)
        return instance, report


class PydProcessVersion(PydConcrete, extra="allow", arbitrary_types_allowed=True):
    
    version: float
    name: str

    @field_validator("name")
    @classmethod
    def split_name(cls, value):
        if "-" in value:
            value = value.split("-")[0]
        return value

    def to_sql(self):
        from backend.db.models import ProcessVersion
        instance = ProcessVersion.query(name=self.name, version=self.version, limit=1)
        if not instance:
            logger.warning(f"PV: Gonna have to make a new process version {self.version}")
            instance = ProcessVersion()
        return instance

