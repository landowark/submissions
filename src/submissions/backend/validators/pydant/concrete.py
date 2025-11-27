
class PydResults(PydBaseClass, arbitrary_types_allowed=True):

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


class PydReagentLot(PydBaseClass):

    lot: str | None
    name: str | None = Field(default=None) #:attr Derived from Reagent
    expiry: date | datetime | Literal['NA'] | None = Field(default=None, validate_default=True)
    missing: bool = Field(default=True)
    comment: str | None = Field(default="", validate_default=True)

