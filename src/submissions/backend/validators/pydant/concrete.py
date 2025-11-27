
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


