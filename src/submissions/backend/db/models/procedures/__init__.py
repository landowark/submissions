"""
All reagent, procedure, equipment, and process models.

This module defines the SQLAlchemy models used for procedure management, reagent tracking, equipment assignment,
process versions, tips, and related associations. It includes rich association tables and custom property handling
for flexible input types.
"""
from __future__ import annotations
# import inspect
from pprint import pformat
from jinja2 import Template
import zipfile, logging, re, numpy as np, json
from pydantic import BaseModel
from sqlalchemy import Column, String, TIMESTAMP, JSON, INTEGER, ForeignKey, Interval, Table, FLOAT, cast, func, select
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship, Query
from sqlalchemy.ext.associationproxy import association_proxy
from datetime import date, datetime, timedelta
from dateutil.parser import parse as dateparse, ParserError
from frontend.widgets.submission_details import SubmissionComment
from tools import check_authorization, setup_lookup, flatten_list, timezone
from typing import Iterator, List, TYPE_CHECKING
from .. import BaseClass, Base, ClientLab, LogMixin
from sqlalchemy.exc import OperationalError as AlcOperationalError, IntegrityError as AlcIntegrityError
from sqlite3 import OperationalError as SQLOperationalError, IntegrityError as SQLIntegrityError
if TYPE_CHECKING:
    from backend.db.models.submissions import Run
    from backend.validators.pydant import PydProcedure, PydProcedureEquipmentAssociation

logger = logging.getLogger(f'submissions.{__name__}')


proceduretype_resulttype = Table(
    "_proceduretype_resulttype",
    Base.metadata,
    Column("proceduretype_id", INTEGER, ForeignKey("_proceduretype.id")),
    Column("resultstype_id", INTEGER, ForeignKey("_resultstype.id")),
    extend_existing=True
)


submissiontype_proceduretype = Table(
    "_submissiontype_proceduretype",
    Base.metadata,
    Column("submissiontype_id", INTEGER, ForeignKey("_submissiontype.id")),
    Column("proceduretype_id", INTEGER, ForeignKey("_proceduretype.id")),
    extend_existing=True
)


class Discount(BaseClass):
    """
    Represents a discount applied to a procedure type for a client lab.

    :ivar id: Primary key identifier for the discount
    :vartype id: int
    :ivar _proceduretype: Related procedure type
    :vartype _proceduretype: ProcedureType
    :ivar proceduretype_id: Foreign key to procedure type
    :vartype proceduretype_id: int
    :ivar _clientlab: Related client lab
    :vartype _clientlab: ClientLab
    :ivar clientlab_id: Foreign key to client lab
    :vartype clientlab_id: int
    :ivar description: Discount description
    :vartype description: str
    :ivar amount: Discount amount
    :vartype amount: float
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    _proceduretype = relationship("ProcedureType")  #: joined parent proceduretype
    proceduretype_id = Column(INTEGER, ForeignKey("_proceduretype.id", ondelete='SET NULL',
                                                  name="fk_DIS_procedure_type_id"))  #: id of joined proceduretype
    _clientlab = relationship("ClientLab")  #: joined client lab
    clientlab_id = Column(INTEGER, ForeignKey("_clientlab.id", ondelete='SET NULL',
                                     name="fk_DIS_org_id"))  #: id of joined client
    description = Column(String(128))  #: Short description
    amount = Column(FLOAT(2))  #: Dollar amount of discount

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        proceduretype = kwargs.pop('proceduretype', None)
        clientlab = kwargs.pop('clientlab', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if proceduretype is not None:
            try:
                self.proceduretype = proceduretype
            except Exception:
                logger.error(f"Couldn't set proceduretype to {proceduretype} for {self.__class__.__qualname__} with description {self.description}")
                
        # Resolve reagentrole
        if clientlab is not None:
            try:
                self.clientlab = clientlab
            except Exception:
                logger.error(f"Couldn't set clientlab to {clientlab} for {self.__class__.__qualname__} with description {self.description}")

    @hybrid_property
    def name(self):
        try:
            clientlab = self.clientlab.name
        except AttributeError:
            clientlab = "Unassigned ClientLab"
        try:
            proceduretype = self.proceduretype.name
        except AttributeError:
            proceduretype = "Unassigned ProcedureType"
        return f"{clientlab}-{proceduretype}-{str(self.amount)}"
    
    @name.expression
    def name(cls):
        clientlab_subquery = (
            select(ClientLab.name)
            .where(ClientLab.id==cls.clientlab_id)
            .correlate(cls)
            .scalar_subquery()
        )
        proceduretype_subquery = (
            select(ProcedureType.name)
            .where(ProcedureType.id==cls.proceduretype_id)
            .correlate(cls)
            .scalar_subquery()
        )
        # NOTE: Can't use f strings for this.
        return clientlab_subquery + "-" + proceduretype_subquery + "-" + cast(cls.amount, String)

    @hybrid_property
    def clientlab(self) -> ClientLab:
        return self._clientlab

    @clientlab.setter
    def clientlab(self, value):
        from backend.validators.pydant import PydClientLab
        match value:
            case str():
                output = ClientLab.query(name=value, limit=1)
            case dict():
                output = ClientLab.query_or_create(**value)
            case PydClientLab():
                output = value.to_sql(update=False)
            case ClientLab():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for .clientlab")
                # continue
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ClientLab):
            self._clientlab = output
        else:
            logger.error(f"Couldn't set _clientlab to {type(output)}")
    
    @hybrid_property
    def proceduretype(self) -> ProcedureType:
        return self._proceduretype

    @proceduretype.setter
    def proceduretype(self, value):
        from backend.validators.pydant import PydProcedureType
        match value:
            case str():
                output = ProcedureType.query(name=value, limit=1)
            case dict():
                output = ProcedureType.query_or_create(**value)
            case PydProcedureType():
                output = value.to_sql(update=False)
            case ProcedureType():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for .proceduretype")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ProcedureType):
            self._proceduretype = output
        else:
            logger.error(f"Couldn't set _proceduretype to {type(output)}")

    @classmethod
    @setup_lookup
    def query(cls,
              clientlab: ClientLab | str | int | None = None,
              proceduretype: ProcedureType | str | int | None = None,
              limit: int = 0,
              **kwargs
              ) -> Discount | List[Discount]:
        """
        Lookup discount objects by client lab and procedure type.

        :param clientlab: ClientLab receiving discount.
        :type clientlab: ClientLab | str | int | None
        :param proceduretype: Procedure type receiving discount.
        :type proceduretype: ProcedureType | str | int | None
        :return: Discount or list of Discounts matching criteria.
        :rtype: Discount | List[Discount]
        """
        query: Query = cls.__database_session__.query(cls)
        match clientlab:
            case ClientLab():
                query = query.filter(cls.clientlab==clientlab)
            case str():
                query = query.filter(cls.clientlab.name==clientlab)
            case int():
                query = query.filter(cls.clientlab.id==clientlab)
            case _:
                pass
        # query = cls._filter_relationship(query, column=cls._clientlab, value=clientlab, model=ClientLab)
        match proceduretype:
            case ProcedureType():
                query = query.filter(cls.proceduretype==proceduretype)
            case str():
                query = query.filter(cls.proceduretype.name==proceduretype)
            case int():
                query = query.filter(cls.proceduretype.id==proceduretype)
            case _:
                pass
        # query = cls._filter_relationship(query, column=cls._proceduretype, value=proceduretype, model=ProcedureType)
        return cls.execute_query(query=query, limit=limit, **kwargs)

    @check_authorization
    def save(self):
        """
        Persist this object with authorization enforcement.

        Calls the base class save implementation after authorization succeeds.
        """
        super().save()


class SubmissionType(BaseClass):
    """
    Represents a submission type and its default metadata.

    :ivar id: Primary key identifier for the submission type
    :vartype id: int
    :ivar name: Unique submission type name
    :vartype name: str
    :ivar defaults: Default JSON metadata for this type
    :vartype defaults: dict
    :ivar _file_name_template: Jinja2 filename template
    :vartype _file_name_template: str
    :ivar regex: Regex used to identify filenames of this submission type
    :vartype regex: str
    :ivar _turnaround_time: Turnaround interval for this type
    :vartype _turnaround_time: Interval|timedelta
    :ivar _abbreviation: Short abbreviation
    :vartype _abbreviation: str
    :ivar _clientsubmission: Related client submissions
    :vartype _clientsubmission: list[ClientSubmission]
    :ivar _proceduretype: Related procedure types
    :vartype _proceduretype: list[ProcedureType]
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(128), nullable=False, unique=True)  #: name of procedure type
    defaults = Column(JSON)  #: Basic information about this procedure type
    _file_name_template = Column(String(256))  #: Jinja2 template for naming files of this submission type
    regex = Column(String(1024)) #: Raw regex for finding filenames of this submission type
    _turnaround_time = Column((Interval()))
    _abbreviation = Column(String(4))
    _clientsubmission = relationship("ClientSubmission",
                                    back_populates="_submissiontype", cascade="all, delete-orphan")  #: Instances of this submission type
    _proceduretype = relationship("ProcedureType", back_populates="_submissiontype",
                                 secondary=submissiontype_proceduretype)  #: Procedures associated with this submission type

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        proceduretype = kwargs.pop('proceduretype', None)
        clientsubmission = kwargs.pop('clientsubmission', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if proceduretype is not None:
            try:
                self.proceduretype = proceduretype
            except Exception:
                logger.error(f"Couldn't set proceduretype to {proceduretype} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve clientsubmission
        if clientsubmission is not None:
            try:
                self.clientsubmission = clientsubmission
            except Exception:
                logger.error(f"Couldn't set clientsubmission to {clientsubmission} for {self.__class__.__qualname__} with name {self.name}")
    
    @hybrid_property
    def file_name_template(self):
        return self._file_name_template or "{{rsl_plate_number}}{% if _clientsubmission %}_{{_clientsubmission.submitter_plate_id}}{% endif %}{% if _completed_date %}_{{ _completed_date.strftime('%Y%m%d %H%M%S') }}{% endif %}"
    
    @file_name_template.setter
    def file_name_template(self, value):
        self._file_name_template = value or "{{rsl_plate_number}}{% if _clientsubmission %}_{{_clientsubmission.submitter_plate_id}}{% endif %}{% if _completed_date %}_{{ _completed_date.strftime('%Y-%m-%d %H:%M:%S') }}{% endif %}"

    @hybrid_property
    def clientsubmission(self):
        return self._clientsubmission

    @clientsubmission.setter
    def clientsubmission(self, value):
        from backend.validators.pydant import PydClientSubmission
        from backend.db.models.submissions import ClientSubmission
        if value is None:
            return
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = ClientSubmission.query(name=item, limit=1)
                case dict():
                    output = ClientSubmission.query_or_create(**item)
                case PydClientSubmission():
                    output = item.to_sql(update=False)
                case ClientSubmission():
                    output = item
                case _:
                    logger.error(f"Unmatched value: {item} for {self.__class__.__qualname__}.clientsubmission")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, ClientSubmission):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {output} to {self.__class__.__qualname__}._clientsubmission")
        self._clientsubmission = list_

    @hybrid_property
    def proceduretype(self):
        return self._proceduretype

    @proceduretype.setter
    def proceduretype(self, value):
        from backend.validators.pydant import PydProcedureType
        if value is None:
            return
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = ProcedureType.query(name=item, limit=1)
                case dict():
                    output = ProcedureType.query_or_create(**item)
                case PydProcedureType():
                    output = item.to_sql()
                case ProcedureType():
                    output = item
                case _:
                    logger.error(f"Unmatched value: {item} for {self.__class__.__qualname__}.proceduretype")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, ProcedureType):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {output} to {self.__class__.__qualname__}._proceduretype")
        self._proceduretype = list_
    
    @hybrid_property
    def turnaround_time(self):
        return self._turnaround_time or timedelta(days=5)
        
    @turnaround_time.setter
    def turnaround_time(self, value):
        match value:
            case int() | str():
                output = timedelta(days=int(value))
            case timedelta():
                output = value
            case _:
                logger.warning(f"Unmatched value {value} for {self.__class__.__qualname__}.turnaround_time")
                output = timedelta(days=5)
        if isinstance(output, timedelta):
            self._turnaround_time = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}.turnaround_time to {type(output)}")

    @hybrid_property
    def abbreviation(self):
        return self._abbreviation
    
    @abbreviation.setter
    def abbreviation(self, value):
        if not isinstance(value, str):
            value = str(value)
        self._abbreviation = value[0:4]

    @classmethod
    @setup_lookup
    def query(cls,
              name: str | None = None,
              abbreviation: str | None = None,
              limit: int = 0,
              **kwargs
              ) -> SubmissionType | List[SubmissionType]:
        """
        Lookup submission types by name or key.

        :param name: Name of submission type. Defaults to None.
        :type name: str | None
        :param key: A key present in the info-map to lookup. Defaults to None.
        :type key: str | None
        :param limit: Maximum number of results to return (0 = all). Defaults to 0.
        :type limit: int
        :return: SubmissionType or list of SubmissionType objects matching filter.
        :rtype: SubmissionType | List[SubmissionType]
        """
        query: Query = cls.__database_session__.query(cls)
        # query = cls._filter_scalar(query, column=cls.name, value=name)
        match name:
            case str():
                query = query.filter(cls.name == name)
                limit = 1
            case _:
                pass
        # query = cls._filter_scalar(query, column=cls.abbreviation, value=abbreviation)
        match abbreviation:
            case str():
                query = query.filter(cls.abbreviation == abbreviation)
                limit = 1
            case _:
                pass
        # args, _, _, values = inspect.getargvalues(inspect.currentframe())

        # all_args = {arg: values[arg] for arg in args if values[arg]}
        # print(all_args)
        return cls.execute_query(query=query, limit=limit, **kwargs)

    @check_authorization
    def save(self):
        """
        Adds this control to the database and commits.
        """
        super().save()

    @classproperty
    def regexes(cls) -> re.Pattern:
        """
        Construct a catchall regular expression for all submission type regexes.

        :return: compiled regular expression covering all submission types.
        :rtype: re.Pattern
        """
        res = [st.regex for st in cls.query() if st.regex]
        rstring = rf'{"|".join(res)}'
        regex = re.compile(rstring, flags=re.IGNORECASE | re.VERBOSE)
        return regex
    
    @classmethod
    def get_regex(cls, submission_type: SubmissionType | str | dict | None = None) -> re.Pattern | None:
        """
        Get a compiled regex for a submission type or submission type list.

        :param submission_type: procedure type of interest. Defaults to None.
        :type submission_type: SubmissionType | str | dict | None
        :return: compiled regular expression for the submission type, or None.
        :rtype: re.Pattern | None
        """
        if isinstance(submission_type, dict):
            submission_type = submission_type.get('value', None)
        if not isinstance(submission_type, SubmissionType):
            submission_type = cls.query(name=submission_type)
        if isinstance(submission_type, list):
            if len(submission_type) > 1:
                regex = "|".join([item.regex for item in submission_type])
            else:
                regex = submission_type[0].regex
        else:
            try:
                regex = submission_type.regex
            except AttributeError as e:
                logger.error(f"Couldn't get submission type for {submission_type.name}")
                regex = None
        if regex is not None:
            try:
                regex = re.compile(rf"{regex}", flags=re.IGNORECASE | re.VERBOSE)
            except re.error as e:
                regex = None
        return regex
    
    @property
    def template(self) -> Template:
        return Template(str(self.file_name_template))

    @classmethod
    def find_by_resultstype(cls, resultstype: ResultsType | str) -> list[SubmissionType]:
        """
        Find submission types associated with a given results type.

        :param resultstype: ResultsType or name of results type to find associated submission types for.
        :type resultstype: ResultsType | str
        :return: List of SubmissionType objects associated with the given results type.
        :rtype: list[SubmissionType]
        """
        if not resultstype:
            logger.error("No results type provided for find_by_resultstype")
            return []
        if isinstance(resultstype, str):
            resultstype = ResultsType.query(name=resultstype, limit=1)
        if isinstance(resultstype, list):
            if len(resultstype) > 1:
                logger.warning(f"Multiple results types found for {resultstype}. Using first match.")
            resultstype = resultstype[0]
        if not isinstance(resultstype, ResultsType):
            logger.error(f"Could not find results type for {resultstype}")
            return []
        submissiontypes = cls.__database_session__.query(cls).join(cls._proceduretype).join(ProcedureType._resultstype).filter(ResultsType.id == resultstype.id).all()
        return submissiontypes


class ProcedureType(BaseClass):
    """
    Represents a category of procedure and its permitted reagents, equipment, results, and submission types.

    :ivar id: Primary key identifier for the procedure type
    :vartype id: int
    :ivar name: Unique procedure type name
    :vartype name: str
    :ivar plate_columns: Number of plate columns
    :vartype plate_columns: int
    :ivar plate_rows: Number of plate rows
    :vartype plate_rows: int
    :ivar plate_cost: Cost per procedure plate
    :vartype plate_cost: float
    :ivar _procedure: Related Procedure instances
    :vartype _procedure: list[Procedure]
    :ivar _submissiontype: Related SubmissionType objects
    :vartype _submissiontype: list[SubmissionType]
    :ivar _resultstype: Related ResultsType objects
    :vartype _resultstype: list[ResultsType]
    :ivar _discount: Related Discount objects
    :vartype _discount: list[Discount]
    :ivar proceduretypeequipmentroleassociation: Equipment role associations
    :vartype proceduretypeequipmentroleassociation: list[ProcedureTypeEquipmentRoleAssociation]
    :ivar _equipmentrole: Association proxy to EquipmentRole
    :vartype _equipmentrole: list[EquipmentRole]
    :ivar proceduretypereagentroleassociation: Reagent role associations
    :vartype proceduretypereagentroleassociation: list[ProcedureTypeReagentRoleAssociation]
    :ivar _reagentrole: Association proxy to ReagentRole
    :vartype _reagentrole: list[ReagentRole]
    """
    id = Column(INTEGER, primary_key=True)
    name = Column(String(64), nullable=False, unique=True)
    plate_columns = Column(INTEGER, default=0)
    plate_rows = Column(INTEGER, default=0)
    plate_cost = Column(FLOAT(2), default=0.00)

    _procedure = relationship("Procedure",
                             back_populates="_proceduretype", cascade="all, delete-orphan")  #: Concrete control of this type.

    _submissiontype = relationship("SubmissionType", back_populates="_proceduretype",
                                  secondary=submissiontype_proceduretype)  #: run this kittype was used for

    _resultstype = relationship("ResultsType", back_populates="_proceduretype",
                                  secondary=proceduretype_resulttype)  #: run this kittype was used for
    
    _discount = relationship("Discount", back_populates="_proceduretype")

    proceduretypeequipmentroleassociation = relationship(
        "ProcedureTypeEquipmentRoleAssociation",
        back_populates="_proceduretype",
        cascade="all, delete-orphan"
    )  #: Association of equipmentroles

    _equipmentrole = association_proxy("proceduretypeequipmentroleassociation", "_equipmentrole",
                                       creator=lambda equipmentrole: ProcedureTypeEquipmentRoleAssociation(equipmentrole=equipmentrole))  #: Proxy of equipmentrole associations

    proceduretypereagentroleassociation = relationship(
        "ProcedureTypeReagentRoleAssociation",
        back_populates="_proceduretype",
        cascade="all, delete-orphan"
    )  #: triple association of KitTypes, ReagentTypes, SubmissionTypes

    _reagentrole = association_proxy("proceduretypereagentroleassociation", "_reagentrole",
                                     creator=lambda reagentrole: ProcedureTypeReagentRoleAssociation(reagentrole=reagentrole))  #: Proxy of reagentrole associations

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        procedure = kwargs.pop('procedure', None)
        submissiontype = kwargs.pop('submissiontype', None)
        resultstype = kwargs.pop('resultstype', None)
        equipmentrole = kwargs.pop('equipmentrole', None)
        reagentrole = kwargs.pop('reagentrole', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if procedure is not None:
            try:
                self.procedure = procedure
            except Exception:
                logger.error(f"Couldn't set procedure to {procedure} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve submissiontype
        if submissiontype is not None:
            try:
                self.submissiontype = submissiontype
            except Exception:
                logger.error(f"Couldn't set submissiontype to {submissiontype} for {self.__class__.__qualname__} with name {self.name}")
        else:
            self.submissiontype = ["Default SubmissionType"]
        if resultstype is not None:
            try:
                self.resultstype = resultstype
            except Exception:
                logger.error(f"Couldn't set resultstype to {resultstype} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve equipmentrole
        if equipmentrole is not None:
            try:
                self.equipmentrole = equipmentrole
            except Exception:
                logger.error(f"Couldn't set equipmentrole to {equipmentrole} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve reagentrole
        if reagentrole is not None:
            try:
                self.reagentrole = reagentrole
            except Exception:
                logger.error(f"Couldn't set reagentrole to {reagentrole} for {self.__class__.__qualname__} with name {self.name}")

    @hybrid_property
    def equipmentrole(self):
        return self._equipmentrole
    
    @equipmentrole.setter
    def equipmentrole(self, value):
        from backend.validators.pydant import PydEquipmentRole
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                # NOTE: A string is assumed to be an existing association
                case str():
                    try:
                        output = next((assoc for assoc in self.proceduretypeequipmentroleassociation if assoc.equipmentrole.name==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.equipmentrole.name for eq in self.proceduretypeequipmentroleassociation]}")
                        output = ProcedureTypeEquipmentRoleAssociation(equipmentrole=item, proceduretype=self)
                case EquipmentRole():
                    output = ProcedureTypeEquipmentRoleAssociation(equipmentrole=item, proceduretype=self, **{k: v for k, v in item.details_dict.items() if k not in ['equipmentrole', 'proceduretype', 'name']})
                case PydEquipmentRole():
                    output = ProcedureTypeEquipmentRoleAssociation(equipmentrole=item, proceduretype=self, **{k: v for k, v in item.improved_dict.items() if k not in ['equipmentrole', 'proceduretype', 'name']})
                case dict():
                    output = ProcedureTypeEquipmentRoleAssociation(equipmentrole=item, proceduretype=self, **{k: v for k, v in item.items() if k not in ['equipmentrole', 'proceduretype', 'name']})
                case ProcedureTypeEquipmentRoleAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._equipmentrole")
                    continue
            if isinstance(output, ProcedureTypeEquipmentRoleAssociation):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Couldn't add {output} to {self.__class__.__qualname__}._equipmentrole")
        self.proceduretypeequipmentroleassociation = list_
            
    @hybrid_property
    def reagentrole(self):
        return self._reagentrole    
    
    @reagentrole.setter
    def reagentrole(self, value):
        from backend.validators.pydant import PydReagentRole
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                # NOTE: A string is assumed to be an existing association
                case str():
                    try:
                        output = next((assoc for assoc in self.proceduretypereagentroleassociation if assoc.reagentrole.name==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.reagent.name for eq in self.proceduretypereagentroleassociation]}")
                        output = ProcedureTypeReagentRoleAssociation(reagentrole=item, proceduretype=self)
                case ReagentRole():
                    output = ProcedureTypeReagentRoleAssociation(reagentrole=item, proceduretype=self, **{k: v for k, v in item.details_dict.items() if k not in ['name', 'proceduretype']})
                case PydReagentRole():
                    output = ProcedureTypeReagentRoleAssociation(reagentrole=item, proceduretype=self, **{k: v for k, v in item.improved_dict.items() if k not in ['name', 'proceduretype']})
                case dict():
                    output = ProcedureTypeReagentRoleAssociation(reagentrole=item, proceduretype=self, **{k: v for k, v in item.items() if k not in ['name', 'proceduretype']})
                case ProcedureTypeReagentRoleAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {type(item)} for {self.__class__.__qualname__}._reagentrole")
                    continue
            if isinstance(output, ProcedureTypeReagentRoleAssociation):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Couldn't add {item} to {self.__class__.__qualname__}._reagentrole")
        self.proceduretypereagentroleassociation = list_

    @hybrid_property
    def resultstype(self):
        return self._resultstype

    @resultstype.setter
    def resultstype(self, value):
        from backend.validators.pydant import PydResultsType
        if value is None:
            return
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = ResultsType.query(name=item, limit=1)
                case dict():
                    output = ResultsType.query_or_create(**item)
                case PydResultsType():
                    output = item.to_sql(update=False)
                case ResultsType():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}.resultstype.")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, ResultsType):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._resultstype")
        self._resultstype = list_
    
    @hybrid_property
    def submissiontype(self):
        return self._submissiontype

    @submissiontype.setter
    def submissiontype(self, value):
        from backend.validators.pydant import PydSubmissionType
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = SubmissionType.query(name=item, limit=1)
                case dict():
                    output = SubmissionType.query_or_create(**item)
                case PydSubmissionType():
                    output = item.to_sql(update=False)
                case SubmissionType():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._submissiontype")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, SubmissionType):
                list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._submissiontype")
        # NOTE: Ensure this has access to "Default SubmissionType"
        check_subtypes = [st.name for st in list_]
        if "Default SubmissionType" not in check_subtypes:
            list_.append(SubmissionType.query(name="Default SubmissionType", limit=1))
        self._submissiontype = list_
        
    @hybrid_property
    def procedure(self):
        return self._procedure

    @procedure.setter
    def procedure(self, value):
        from backend.validators.pydant import PydProcedure
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = Procedure.query(name=item, limit=1)
                case dict():
                    output = Procedure.query_or_create(**item)
                case PydProcedure():
                    output = item.to_sql(update=False)
                case Procedure():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._procedure")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, Procedure):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}.procedure")
        self._procedure = list_

    @hybrid_property
    def discount(self):
        return self._discount

    @discount.setter
    def discount(self, value):
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case dict():
                    output = Discount.query_or_create(**item)
                case Discount():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._discount")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, Discount):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._discount")
        self._discount = list_

    @classmethod
    @setup_lookup
    def query(cls, 
              id: int | None = None, 
              name: str | None = None, 
              limit: int = 0,
              **kwargs) -> ProcedureType | List[ProcedureType]:
        """
        Lookup procedure types by id or name.

        :param id: Procedure type id. Defaults to None.
        :type id: int | None
        :param name: Procedure type name or prefix. Defaults to None.
        :type name: str | None
        :param limit: Maximum number of results to return (0 = all). Defaults to 0.
        :type limit: int
        :return: ProcedureType or list of ProcedureTypes matching filter.
        :rtype: ProcedureType | List[ProcedureType]
        """
        query: Query = cls.__database_session__.query(cls)
        match id:
            case int():
                query = query.filter(cls.id == id)
                limit = 1
            case _:
                pass
        match name:
            case str():
                # NOTE: Updated to startswith to enable search using truncated excel tab names.
                # Possible problem: Another procedure starts with same string.
                query = query.filter(cls.name.istartswith(name))
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit, **kwargs)

    def construct_dummy_procedure(self, run: Run | None = None) -> PydProcedure:
        """
        Build a PydProcedure with empty sample data for this procedure type.

        :param run: Optional Run to attach to the dummy procedure.
        :type run: Run | None
        :return: Constructed PydProcedure instance.
        :rtype: PydProcedure
        """
        from backend.validators.pydant import PydProcedure
        if run:
            samples = run.constuct_sample_dicts_for_proceduretype(proceduretype=self)
            run = run.to_pydantic()
        else:
            samples = []
        output = dict(
            proceduretype=self,
            repeat=False,
            run=run,
            sample=samples
        )
        return PydProcedure(**output)
    
    @property
    def ranked_plate(self):
        """
        Create a ranked plate mapping from plate coordinates.

        :return: dictionary mapping rank to (row, column) coordinates.
        :rtype: dict[int, tuple[int, int]]
        """
        # NOTE: rows/columns
        matrix = np.array([[0 for yyy in range(1, self.plate_rows + 1)] for xxx in range(1, self.plate_columns + 1)])
        return {iii: (item[0][1] + 1, item[0][0] + 1) for iii, item in enumerate(np.ndenumerate(matrix), start=1)}

    @property
    def total_wells(self) -> int:
        return self.plate_rows * self.plate_columns

    @property
    def allowed_result_methods(self) -> List[dict]:
        """
        Return metadata dictionaries for all result methods allowed by this procedure type.

        :return: List of result method details dictionaries.
        :rtype: list[dict]
        """
        return [item.details_dict for item in self.resultstype]
    
    @property
    def preprocessing_methods(self) -> Iterator[tuple[str, callable, ResultsType]]:
        """
        Yield preprocessing controls for each allowed result method.

        :return: Generator yielding tuples of (label, function, ResultsType).
        :rtype: Iterator[tuple[str, callable, ResultsType]]
        """
        from backend.excel.writers import results_settings
        for method in self.allowed_result_methods:
            settings_name = f"{method['name'].replace(' ', '')}Settings"
            results_type = next((item for item in self.resultstype if item.name == method['name']), None)
            if not results_type:
                continue
            try:
                func = getattr(results_settings, settings_name, None)
            except AttributeError:
                continue
            if not func:
                continue
            if func:
                yield func.label, func, results_type
            

class Procedure(BaseClass):
    """
    Represents an executed procedure within a run.

    :ivar id: Primary key identifier for the procedure
    :vartype id: int
    :ivar repeat_of_id: Foreign key to a repeated procedure
    :vartype repeat_of_id: int
    :ivar _cost: Calculated cost for the procedure
    :vartype _cost: float
    :ivar _repeat_of: Reference to the repeated procedure
    :vartype _repeat_of: Procedure|None
    :ivar _started_date: Procedure start timestamp
    :vartype _started_date: datetime|None
    :ivar _completed_date: Procedure completion timestamp
    :vartype _completed_date: datetime|None
    :ivar technician: Technician name
    :vartype technician: str
    :ivar _results: Associated results records
    :vartype _results: list[Results]
    :ivar proceduretype_id: Foreign key to the procedure type
    :vartype proceduretype_id: int
    :ivar _proceduretype: Related ProcedureType object
    :vartype _proceduretype: ProcedureType|None
    :ivar run_id: Foreign key to the parent run
    :vartype run_id: int
    :ivar _run: Related Run object
    :vartype _run: Run|None
    :ivar proceduresampleassociation: Sample associations for this procedure
    :vartype proceduresampleassociation: list[ProcedureSampleAssociation]
    :ivar _sample: Association proxy to sample objects
    :vartype _sample: list[Sample]
    :ivar procedurereagentlotassociation: Reagent lot associations for this procedure
    :vartype procedurereagentlotassociation: list[ProcedureReagentLotAssociation]
    :ivar _reagentlot: Association proxy to reagent lots
    :vartype _reagentlot: list[ReagentLot]
    :ivar procedureequipmentassociation: Equipment associations for this procedure
    :vartype procedureequipmentassociation: list[ProcedureEquipmentAssociation]
    :ivar _equipment: Association proxy to equipment objects
    :vartype _equipment: list[Equipment]
    """
    id = Column(INTEGER, primary_key=True)  #: Primary key
    repeat_of_id = Column(INTEGER, ForeignKey("_procedure.id", name="fk_repeat_id"))
    _cost = Column(FLOAT(2), default=0.00)
    _repeat_of = relationship("Procedure", remote_side=[id])
    _started_date = Column(TIMESTAMP)
    _completed_date = Column(TIMESTAMP)
    technician = Column(String(64))  #: name of processing tech(s)
    _results = relationship("Results", back_populates="_procedure", uselist=True, cascade="all, delete-orphan")  #: Results from this procedure
    proceduretype_id = Column(INTEGER, ForeignKey("_proceduretype.id", ondelete="SET NULL",
                                                  name="fk_PRO_proceduretype_id"))  #: client lab id from _organizations))
    _proceduretype = relationship("ProcedureType", back_populates="_procedure")  #: ProcedureType of this procedure
    run_id = Column(INTEGER, ForeignKey("_run.id", ondelete="CASCADE",
                                        name="fk_PRO_basicrun_id"), nullable=False)  #: id of parent run, set to CASCADE on delete to remove procedures if run is deleted
    _run = relationship("Run", back_populates="_procedure")  #: Run this procedure is part of
    _comment = Column(JSON)  #: user notes

    proceduresampleassociation = relationship(
        "ProcedureSampleAssociation",
        back_populates="_procedure",
        cascade="all, delete-orphan",
    )

    _sample = association_proxy("proceduresampleassociation", "_sample",
                                creator=lambda sample: ProcedureSampleAssociation(sample=sample))  #: Association proxy to Sample

    procedurereagentlotassociation = relationship(
        "ProcedureReagentLotAssociation",
        back_populates="_procedure",
        cascade="all, delete-orphan",
    )  #: Relation to ProcedureReagentAssociation

    _reagentlot = association_proxy("procedurereagentlotassociation", "_reagentlot",
                                    creator=lambda reagentlot: ProcedureReagentLotAssociation(reagentlot=reagentlot))  #: Association proxy to ReagentLot

    procedureequipmentassociation = relationship(
        "ProcedureEquipmentAssociation",
        back_populates="_procedure",
        cascade="all, delete-orphan"
    )  #: Relation to Equipment

    _equipment = association_proxy("procedureequipmentassociation", "_equipment")  #: Association proxy to RunEquipmentAssociation.equipment

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        repeat_of = kwargs.pop('repeat_of', None)
        started_date = kwargs.pop('started_date', datetime.now())
        completed_date = kwargs.pop('completed_date', None)
        proceduretype = kwargs.pop('proceduretype', None)
        results = kwargs.pop('results', None)
        run = kwargs.pop('run', None)
        sample = kwargs.pop('sample', None)
        reagentlot = kwargs.pop('reagentlot', None)
        equipment = kwargs.pop('equipment', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve repeat_of
        if repeat_of is not None:
            try:
                self.repeat_of = repeat_of
            except Exception:
                logger.error(f"Couldn't set repeat_of to {repeat_of} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve started_date
        if started_date is not None:
            try:
                self.started_date = started_date
            except Exception:
                logger.error(f"Couldn't set started_date to {started_date} for {self.__class__.__qualname__} with name {self.name}")
        if completed_date is not None:
            try:
                self.completed_date = completed_date
            except Exception:
                # fallback: store in misc_info if setter fails
                logger.error(f"Couldn't set completed_date to {completed_date} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve proceduretype
        if proceduretype is not None:
            try:
                self.proceduretype = proceduretype
            except Exception:
                logger.error(f"Couldn't set proceduretype to {proceduretype} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve results
        if results is not None:
            try:
                self.results = results
            except Exception:
                logger.error(f"Couldn't set results to {results} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve run
        if run is not None:
            try:
                self.run = run
            except Exception:
                logger.error(f"Couldn't set run to {run} for {self.__class__.__qualname__} with name {self.name}")
        if sample is not None:
            try:
                self.sample = sample
            except Exception:
                logger.error(f"Couldn't set sample to {sample} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve reagentlot
        if reagentlot is not None:
            try:
                self.reagentlot = reagentlot
            except Exception:
                logger.error(f"Couldn't set reagentlot to {reagentlot} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve equipment
        if equipment is not None:
            try:
                self.equipment = equipment
            except Exception:
                logger.error(f"Couldn't set equipment to {equipment} for {self.__class__.__qualname__} with name {self.name}")
        self._comment = [] if self._comment is None else self._comment

    @hybrid_property
    def name(self) -> str:
        try:
            run = self.run.name
        except AttributeError:
            run = "Unknown Run"
        try:
            proceduretype = self.proceduretype.name
        except AttributeError:
            proceduretype = "Unknown ProcedureType"
        try:
            started_date = self.started_date.strftime("%Y-%m-%d %H:%M:%S")
        except AttributeError:
            started_date = "NA"
        return f"{run} - {proceduretype} - {started_date}"  
    
    @name.expression
    def name(cls):
        from backend.db.models import Run
        # Create an alias to avoid the recursive property lookup
        run_subquery = (
            select(Run.name)
            .where(Run.id==cls.run_id)
            .scalar_subquery()
        )
        proceduretype_subquery = (
            select(ProcedureType.name)
            .where(ProcedureType.id==cls.proceduretype_id)
            .scalar_subquery()
        )
        # Use func.concat or comma-separated args in func.concat to force the || operator
        return func.coalesce(run_subquery, "Unknown Run") + \
            " - " + \
            func.coalesce(proceduretype_subquery, "Unknown ProcedureType") + \
            " - " + \
            func.coalesce(func.strftime("%Y-%m-%d %H:%M:%S", cls._started_date), "NA")

    @hybrid_property
    def reagentlot(self):
        return self._reagentlot
    
    @reagentlot.setter
    def reagentlot(self, value):
        from backend.validators.pydant import PydProcedureReagentLotAssociation
        if not isinstance(value, list):
            value = [value]
        built = []  # Clear existing associations to prevent duplicates when resetting reagent lots
        for item in value:
            match item:
                case str():
                    try:
                        output = next((assoc for assoc in self.procedurereagentlotassociation if assoc.reagentlot.name==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.reagentlot.name for eq in self.procedurereagentlotassociation]}")
                        output = ProcedureReagentLotAssociation(reagentlot=item, procedure=self)
                case PydProcedureReagentLotAssociation():
                    # If the child Pydantic object has a reference to the parent, 
                    # update its internal reference to match the current live sql_instance first.
                    output = item.to_sql()
                case dict():
                    output = ProcedureReagentLotAssociation(reagentlot=item, procedure=self, **{k: v for k, v in item.items() if k not in ['reagentlot', 'procedure']})
                case ReagentLot():
                    output = ProcedureReagentLotAssociation(reagentlot=item, procedure=self)
                case ProcedureReagentLotAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._reagentlot")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            
            if isinstance(output, ProcedureReagentLotAssociation):
                if not self.already_in_collection(output, built):
                    built.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._reagentlot")
        self.procedurereagentlotassociation = built    
        
    @hybrid_property
    def equipment(self):
        return self._equipment
    
    @equipment.setter
    def equipment(self, value):
        from backend.validators.pydant import PydEquipment, PydProcedureEquipmentAssociation
        if not isinstance(value, list):
            value = [value]
        built = []                                   # build into a temp list...
        for item in value:
            match item:
                case str():
                    output = ProcedureEquipmentAssociation(equipment=item)
                case Equipment():
                    output = ProcedureEquipmentAssociation(equipment=item)
                case PydEquipment():
                    output = ProcedureEquipmentAssociation(
                        equipment=item,
                        **{k: v for k, v in item.improved_dict.items()
                        if k not in ['name', 'procedure', 'equipment']})
                case dict():
                    output = ProcedureEquipmentAssociation(
                        equipment=item,
                        **{k: v for k, v in item.items()
                        if k not in ['name', 'procedure', 'equipment']})
                case ProcedureEquipmentAssociation():
                    output = item
                case PydProcedureEquipmentAssociation():
                    output = item.to_sql()
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._equipment")
                    continue
            if isinstance(output, tuple):            # tolerate any legacy tuple return
                output = output[0]
            if isinstance(output, ProcedureEquipmentAssociation):
                if not self.already_in_collection(output, built):
                    built.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._equipment")
        # ...then one atomic assignment. This replaces contents, sets each member's
        # back-ref to self via back_populates, and only runs if the whole list built
        # without raising. No clear-first window, and no double-add.
        self.procedureequipmentassociation = built

    @hybrid_property
    def sample(self):
        return self._sample
    
    @sample.setter
    def sample(self, value):
        from ..submissions import ProcedureSampleAssociation, Sample
        from backend.validators.pydant import PydSample, PydProcedureSampleAssociation
        if not isinstance(value, list):
            value = [value]
        self.proceduresampleassociation = []  # Clear existing associations to prevent duplicates when resetting samples
        for iii, item in enumerate(value, start=1):
            match item:
                case str():
                    try:
                        output = next((assoc for assoc in self.proceduresampleassociation if assoc.sample.name==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.sample.name for eq in self.proceduresampleassociation]}")
                        output = ProcedureSampleAssociation(sample=item, procedure=self, rank=iii)
                case PydProcedureSampleAssociation():
                    output = item.to_sql()
                case Sample():
                    output = ProcedureSampleAssociation(sample=item, procedure=self, rank=item._misc_info.get("rank", iii))
                case PydSample():
                    output = ProcedureSampleAssociation(sample=item, procedure=self, rank=getattr(item, "rank", iii), **{k: v for k, v in item.improved_dict.items() if k not in ['name', 'rank', 'sample', 'procedure']})
                case dict():
                    output = ProcedureSampleAssociation(sample=item, procedure=self, rank=item.get("rank", iii), **{k: v for k, v in item.items() if k not in ['name', 'rank', 'sample', 'procedure']})
                case ProcedureSampleAssociation():
                    output = item
                    output.procedure_rank = iii
                case _:
                    logger.error(f"Unmatched value {item} for {item.__class__.__qualname__}._sample")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            output.procedure = self
            if isinstance(output, ProcedureSampleAssociation):
                try:
                    check = output.sample.sample_id.lower().startswith(("blank", "na", "none", ""))
                except AttributeError as e:
                    logger.error(f"Couldn't get sample_id due to {e}")
                    check = True
                if check:
                    continue
                # Check for existing association by comparing all primary key values
                logger.debug(f"Checking {output} using {output.get_primary_keys()}")
                if not self.already_in_collection(output, self.proceduresampleassociation):
                    self.proceduresampleassociation.append(output)
            else:
                logger.error(f"Could not add {output} to {self.__class__.__qualname__}._sample")
        
    @hybrid_property
    def started_date(self):
        return self._started_date if self._started_date else None

    @started_date.setter
    def started_date(self, value):
        if isinstance(value, dict):
            value = value.get("value", datetime.now())
        match value:
            case datetime():
                output = value
            case date():
                output = datetime.combine(value, datetime.min.time())
            case int():
                output = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value - 2)
            case str():
                string = re.sub(r"(_|-)\d(R\d)?$", "", value)
                try:
                    output = dateparse(string)
                except ParserError as e:
                    logger.error(f"Problem parsing date: {e}")
                    try:
                        output = dateparse(string.replace("-", ""))
                    except Exception as e:
                        logger.error(f"Problem with parse fallback: {e}")
                        return value
            case _:
                raise ValueError(f"Unmatched value {value['value']} for {self.__class__.__qualname__}._started_date")
        value = output.replace(tzinfo=timezone)
        self._started_date = value

    @hybrid_property
    def completed_date(self):
        return self._completed_date if self._completed_date else None

    @completed_date.setter
    def completed_date(self, value):
        if isinstance(value, dict):
            value = value.get("value", datetime.now())
        match value:
            case datetime():
                output = value
            case date():
                output = datetime.combine(value, datetime.min.time())
            case int():
                output = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value - 2)
            case str():
                string = re.sub(r"(_|-)\d(R\d)?$", "", value)
                try:
                    output = dateparse(string)
                except ParserError as e:
                    logger.error(f"Problem parsing date: {e}")
                    try:
                        output = dateparse(string.replace("-", ""))
                    except Exception as e:
                        logger.error(f"Problem with parse fallback: {e}")
                        return value
            case _:
                raise ValueError(f"Unmatched value {value['value']} for {self.__class__.__qualname__}._completed_date")
        value = output.replace(tzinfo=timezone)
        self._completed_date = value

    @hybrid_property
    def proceduretype(self):
        return self._proceduretype

    @proceduretype.setter
    def proceduretype(self, value):
        from backend.validators.pydant import PydProcedureType
        match value:
            case str():
                output = ProcedureType.query(name=value, limit=1)
            case dict():
                output = ProcedureType.query_or_create(**value)
            case PydProcedureType():
                output = value.to_sql(update=False)
            case ProcedureType():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._proceduretype")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ProcedureType):
            self._proceduretype = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._proceduretype to {type(output)}")

    @hybrid_property
    def run(self):
        return self._run

    @run.setter
    def run(self, value):
        from backend.validators.pydant import PydRun
        from ..submissions import Run
        match value:
            case str():
                output = Run.query(name=value, limit=1)
            case dict():
                # If caller provided a clientsubmission object inside the dict, avoid
                # running Run.query_or_create which may build queries with pagination
                # applied earlier; instead construct a Run instance directly.
                if isinstance(cs, BaseClass):
                    output = Run(**value)
                else:
                    output = Run.query_or_create(**value)
            case PydRun():
                output = value.to_sql(update=False)
            case Run():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._run")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, Run):
            self._run = output
        else:
            logger.error(f"Unable to set {self.__class__.__qualname__}._run to {type(output)}")
    
    @hybrid_property
    def results(self):
        return [result for result in self._results if not result.is_sample]  # filter out sample-level results, only return procedure-level results

    @results.setter
    def results(self, value):
        from backend.validators.pydant import PydResults
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        
        for item in value:
            match item:
                case str():
                    output = Results.query(name=item, limit=1)
                case dict():
                    output = Results.query_or_create(**item)
                case PydResults():
                    output = item.to_sql()
                case Results():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._results")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, Results):
                if not self.already_in_collection(output, self._results):
                    self._results.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._results")
    
    @hybrid_property
    def repeat_of(self):
        return self._repeat_of

    @repeat_of.setter
    def repeat_of(self, value):
        from backend.validators.pydant import PydProcedure
        match value:
            case str():
                output = Procedure.query(name=value, limit=1)
            case dict():
                output = Procedure.query_or_create(**value)
            case PydProcedure():
                output = value.to_sql(update=False)
                if isinstance(output, tuple):
                    output = output[0]
            case Procedure():
                output = value
            case None:
                output = None
            case _:
                raise ValueError(f"Unmatched value {value} for {self.__class__.__qualname__}._repeat_of")
        if isinstance(output, Procedure):
            self._repeat_of = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._repeat_of to {type(output)}")
    
    @hybrid_property
    def repeat(self) -> bool:
        return self._repeat_of is not None

    @hybrid_property
    def cost(self) -> float:
        return self._cost

    @property
    def info_results(self) -> dict[str, dict]:
        grouped_results: dict[str, dict] = {}
        for result in self._results:
            if result.is_sample or result.assoc_id is not None:
                continue
            try:
                resultstype = result.resultstype.name
            except AttributeError:
                resultstype = "Unassigned ResultsType"
            
            grouped_results[resultstype] = result.to_pydantic()
        return grouped_results

    @property
    def sample_results(self) -> dict[str, list]:
        grouped_results: dict[str, list] = {}
        for result in flatten_list([[result for result in item.results] for item in self.proceduresampleassociation]):
            if not result.is_sample:
                continue
            try:
                resultstype = result.resultstype.name
            except AttributeError:
                resultstype = "Unassigned ResultsType"
            grouped_results.setdefault(resultstype, []).append(result.to_pydantic())
        return grouped_results

    @property
    def grouped_results(self) -> dict[str, dict[str, list]]:
        """Group procedure-level and sample-level results by resultstype.

        Returns a dict keyed by resultstype, with nested "procedure" and "sample"
        result lists.
        """
        grouped: dict[str, dict[str, list]] = {}
        procedure_groups = self.info_results
        sample_groups = self.sample_results

        all_resultstypes = set(procedure_groups) | set(sample_groups)
        for resultstype in all_resultstypes:
            grouped[resultstype] = {
                "info": procedure_groups.get(resultstype, None),
                "sample": sample_groups.get(resultstype, []),
            }

        return grouped

    @hybrid_property
    def comment(self):
        if not self._comment:
            return []
        return [item for item in self._comment if all(key in ['user', 'text', 'time'] for key in item.keys())]
    
    @comment.setter
    def comment(self, value):
        if not isinstance(value, dict):
            logger.error(f"Invalid comment value {value} for {self.__class__.__qualname__}, must be a dictionary.")
            return
        if value['text'] in [""]:
            return
        current = self._comment or []
        current.append(value)
        self._comment = current

    @classmethod
    @setup_lookup
    def query(cls, 
              id: int | None = None,
              name: str | None = None,
              start_date: date | datetime | str | int | None = None,
              end_date: date | datetime | str | int | None = None, 
              limit: int = 0,
              **kwargs) -> Procedure | List[Procedure]:
        """
    #     Lookup procedures by id, name, or date range.

    #     :param id: Procedure id. Defaults to None.
    #     :type id: int | None
    #     :param name: Procedure name or prefix. Defaults to None.
    #     :type name: str | None
    #     :param start_date: Start date for procedure start time. Defaults to None.
    #     :type start_date: date | datetime | str | int | None
    #     :param end_date: End date for procedure start time. Defaults to None.
    #     :type end_date: date | datetime | str | int | None
    #     :param limit: Maximum number of results to return (0 = all). Defaults to 0.
    #     :type limit: int
    #     :return: Procedure or list of Procedure objects matching filter.
    #     :rtype: Procedure | List[Procedure]
    #     """
        query: Query = cls.__database_session__.query(cls)
        if start_date is not None and end_date is None:
            logger.warning(f"Start date with no end date, using today.")
            end_date = date.today()
        if end_date is not None and start_date is None:
            # NOTE: this query returns a tuple of (object, datetime), need to get only datetime.
            start_date = cls.__database_session__.query(cls, func.min(cls.submitted_date)).first()[1]
            logger.warning(f"End date with no start date, using first procedure date: {start_date}")
        if start_date is not None:
            start_date = cls.rectify_query_date(start_date)
            end_date = cls.rectify_query_date(end_date, eod=True)
            query = query.filter(cls.started_date.between(start_date, end_date))
        match id:
            case int():
                query = query.filter(cls.id == id)
                limit = 1
            case _:
                pass
        match name:
            case str():
                # NOTE: Updated to startswith to enable search using truncated excel tab names.
                # Possible problem: Another procedure starts with same string.
                query = query.filter(cls.name.istartswith(name))
                limit = 1
            case _:
                pass
        return super().query(query=query, limit=limit, **kwargs)

    @property
    def custom_context_events(self) -> dict:
        """
        Create a mapping of event names to handler methods for context menus.

        :return: mapping of context menu labels to callable methods.
        :rtype: dict[str, callable]
        """
        names = ["Add Results", "Edit", "Add Comment", "Show Details", "Delete"]
        return {item: self.__getattribute__(item.lower().replace(" ", "_")) for item in names}

    def add_results(self, obj, resultstype_name: str):
        """
        Add results for this procedure using a manager determined by resultstype_name.

        :param obj: Parent object owning the procedure UI.
        :type obj: Any
        :param resultstype_name: Name of the result type to add.
        :type resultstype_name: str
        :return: None
        """
        resultstype = resultstype_name.replace(" ", "")
        logger.info(f"Add Results! {resultstype_name}")
        from backend.managers import results
        results_manager = getattr(results, f"{resultstype}Manager")
        rs = results_manager(procedure=self, parent=obj)
        procedure_results = rs.procedure_to_pydantic()
        samples_results = rs.samples_to_pydantic()
        if procedure_results:
            procedure_sql = procedure_results.to_sql()
        else:
            return
        if isinstance(procedure_sql, tuple):
            procedure_sql = procedure_sql[0]
        procedure_sql.save()
        for sample in samples_results:
            sample_sql = sample.to_sql()
            if isinstance(sample_sql, tuple):
                sample_sql = sample_sql[0]
            sample_sql.save()

    def edit(self, obj):
        """
        Launch the procedure edit dialog and persist updated procedure details.

        :param obj: Parent UI object used for dialog control.
        :type obj: Any
        :return: None
        """
        from frontend.widgets.procedure_creation import ProcedureCreation
        logger.debug("Edit!")
        procedure = self.construct_pyd_procedure_for_creation()
        procedure.active_reagentroles = [assoc.reagentrole.name for assoc in self.procedurereagentlotassociation]
        procedure.active_equipmentroles = [assoc.equipmentrole.name for assoc in self.procedureequipmentassociation]
        dlg = ProcedureCreation(parent=obj, procedure=procedure, edit=True)
        if dlg.exec():
            sql: Procedure = dlg.return_sql()
            sql.update_last_useds()
            # Use the edited PydProcedure from the dialog to populate SQL relationships
            pyd = dlg.procedure
            sql.sample = pyd.sample
            sql.equipment = pyd.equipment
            sql.save()
        obj.set_data()

    def add_comment(self, obj):
        """
        Add a comment to this procedure.

        This method is a placeholder for comment UI integration.

        :param obj: Parent object for the comment action.
        :type obj: Any
        :return: None
        """
        logger.debug("Add Comment!")
        dlg = SubmissionComment(parent=obj, submission=self)
        if dlg.exec():
            logger.debug(f"Comment dialog returned: {dlg.parse_form()}")
            self.comment = dlg.parse_form()
            self.save()

    @check_authorization
    def delete(self, obj):
        from frontend.widgets.pop_ups import QuestionAsker
        msg = QuestionAsker(title="Delete?", message=f"Are you sure you want to delete {self.name}?\n")
        if msg.exec():
            self.procedureequipmentassociation = []
            self.procedurereagentlotassociation = []
            self.proceduresampleassociation = []
            self.__database_session__.delete(self)
            try:
                self.__database_session__.commit()
            except (SQLIntegrityError, SQLOperationalError, AlcIntegrityError, AlcOperationalError) as e:
                self.__database_session__.rollback()
                raise e
            try:
                obj.set_data()
            except AttributeError:
                logger.error("App will not refresh data at this time.")
        
    # TODO: Convert references to details_dict_expand_fields calls so I can trim this down.
    @property
    def details_dict(self) -> dict:
        """
        Produce a JSON-serializable details dictionary for this procedure.

        :return: Detailed procedure metadata for serialization and UI display.
        :rtype: dict
        """
        output = super().details_dict
        try:
            output['proceduretype'] = output['proceduretype'].details_dict['name']
        except AttributeError:
            pass
        output['results'] = [result.details_dict for result in self.results]
        run_samples = [sample for sample in self.run.sample]
        active_samples = [sample.details_dict for sample in self.proceduresampleassociation
                          if sample.sample.sample_id in [s.sample_id for s in run_samples]]
        for sample in active_samples:
            sample['active'] = True
        inactive_samples = [sample.details_dict for sample in run_samples if
                            sample.name not in [s['sample_id'] for s in active_samples]]
        for sample in inactive_samples:
            sample['active'] = False
        output['sample'] = active_samples + inactive_samples
        output['reagent'] = [reagent.details_dict for reagent in self.procedurereagentlotassociation]
        output['equipment'] = [equipment.details_dict for equipment in self.procedureequipmentassociation]
        output['repeat'] = self.repeat
        output['run'] = self.run.name
        output['excluded'] += self.get_default_info("details_ignore")
        output['sample_count'] = len(active_samples)
        output['comment'] = self.comment
        try:
            output['clientlab'] = self.run.clientsubmission.clientlab.name
        except AttributeError:
            logger.error(f"Run: {self.run}, ClientSubmission: {self.run.clientsubmission}")
            output['clientlab'] = "Unknown"
        output['cost'] = 0.00
        return output

    def to_pydantic(self, **kwargs):
        """
        Convert this Procedure into its pydantic representation.

        :param kwargs: Additional keyword arguments for serialization.
        :type kwargs: dict
        :return: Pydantic procedure model representing this SQL object.
        :rtype: BaseModel
        """
        output = super().to_pydantic()
        output.sample = [item.to_pydantic() for item in self.proceduresampleassociation]
        output.run = self.run.to_pydantic()
        output.reagentlot = [item.to_pydantic() for item in self.procedurereagentlotassociation]
        output.equipment = [item.to_pydantic() for item in self.procedureequipmentassociation]
        output.info_results = self.info_results
        output.sample_results = self.sample_results
        return output

    def construct_pyd_procedure_for_creation(self) -> "PydProcedure":
        """Return a widget-ready PydProcedure for ProcedureCreation."""
        from backend.validators.pydant import PydProcedure, PydSample, PydReagentLot, PydProcedureReagentLotAssociation, PydProcedureSampleAssociation

        sample_list = []
        for assoc in self.proceduresampleassociation:
            sample = assoc.sample.to_pydantic() if hasattr(assoc.sample, "to_pydantic") else assoc.sample
            if isinstance(sample, PydSample):
                sample.row = assoc.row
                sample.column = assoc.column
                sample.rank = assoc.procedure_rank
                sample.enabled = getattr(assoc, "enabled", True)
                sample.control_type = ('positivecontrol' if sample.is_control == 1 else 'negativecontrol' if sample.is_control == -1 else 'regular')
            sample_list.append(sample)
        # Build a PydProcedureType instance and attach expanded relationship
        # dicts (reagentrole/equipmentrole) to its model_extra. Mark which
        # roles are already present on this Procedure with a 'filled' flag.
        try:
            pyd_proc_type = self.proceduretype.to_pydantic()
            expanded = pyd_proc_type.improved_dict_expand_fields([
                {"reagentrole": [{"reagent": ["reagentlot"]}]},
                {"equipmentrole": [{"equipmentroleequipmentassociation": ["equipment", "process"]}]}
            ])
            # annotate filled flags on expanded entries
            for item in expanded.get('reagentrole', []):
                item['filled'] = any(assoc.reagentrole.name == item.get('name') for assoc in self.procedurereagentlotassociation)
            for item in expanded.get('equipmentrole', []):
                item['filled'] = any(assoc.equipmentrole.name == item.get('name') for assoc in self.procedureequipmentassociation)
            # attach expanded dicts so templates can read them via proceduretype['reagentrole']
            pyd_proc_type.model_extra.update(expanded)
        except Exception as e:
            logger.error(f"Couldn't build expanded proceduretype for {self.__class__.__qualname__} with name {self.name}")
            logger.error(f"Error: {e}")
            pyd_proc_type = self.proceduretype.to_pydantic() if hasattr(self.proceduretype, 'to_pydantic') else self.proceduretype
        output = dict(
            proceduretype=pyd_proc_type,
            run=self.run.to_pydantic(),
            technician=self.technician,
            repeat=bool(self.repeat),
            repeat_of=self.repeat_of.to_pydantic() if self.repeat_of is not None else None,
            sample=sample_list,
            reagentlot=[item.to_pydantic() for item in self.procedurereagentlotassociation],
            equipment=[item.to_pydantic() for item in self.procedureequipmentassociation],
            results=[item.to_pydantic() for item in self.results],
            started_date=self.started_date,
            completed_date=self.completed_date,
            sql_instance=self,
        )
        pyd = PydProcedure(**output)
        return pyd

    @classmethod
    def get_default_info(cls, *args) -> dict | list | str:
        """
        Return default field visibility and serialization settings.

        :param args: Specific keys to filter in the returned dictionary.
        :type args: tuple
        :return: Default metadata configuration for this class.
        :rtype: dict | list | str
        """
        dicto = super().get_default_info()
        recover = ['filepath', 'sample', 'csv', 'comment', 'equipment']
        dicto.update(dict(
            details_ignore=['excluded', 'reagents', 'sample', 'extraction_info', 'comment', 'barcode',
                            'platemap', 'export_map', 'equipment', 'tips', 'custom', 'reagentlot', 'reagent_lot',
                            "results", "proceduresampleassociation", "sample",
                            "procedurereagentlotassociation",
                            "procedureequipmentassociation", "proceduretipsassociation", "reagent", "equipment",
                            "tips", "control"],
            # NOTE: Fields not placed in ui form
            form_ignore=['reagents', 'ctx', 'id', 'cost', 'extraction_info', 'signed_by', 'comment', 'namer',
                         'submission_object', "tips", 'contact_phone', 'custom', 'cost_centre', 'completed_date',
                         'control', "origin_plate"] + recover,
            # NOTE: Fields not placed in ui form to be moved to pydantic
            form_recover=recover
        ))
        if args:
            if len(args) > 1:
                output = {k: v for k, v in dicto.items() if k in args}
            else:
                output = dicto[args[0]]
        else:
            output = {k: v for k, v in dicto.items()}
        return output

    @property
    def submissiontype(self):
        return self.run.clientsubmission.submissiontype

    def set_cost(self):
        """
        Calculate and store the total cost of this procedure.

        The cost includes reagent volumes, tip usage, and plate cost.

        :return: None
        """
        numbers_array = []
        for reagentlotassoc in self.procedurereagentlotassociation:
            reagent = reagentlotassoc.reagentlot.reagent
            cost_per_ml = reagent.cost_per_ml
            reagentrole = reagentlotassoc.reagentrole
            rr_reg_assoc = ReagentRoleReagentAssociation.query(reagent=reagent, reagentrole=reagentrole, limit=1)
            ml_per_sample = rr_reg_assoc.ml_used_per_sample
            numbers_array.append(cost_per_ml * ml_per_sample * len(self.sample))
        for equipmentassoc in self.procedureequipmentassociation:
            for tipassoc in equipmentassoc.tipslot:
                tip = tipassoc.tips
                cost_per_tip = tip.cost_per_tip
                numbers_array.append(cost_per_tip * len(self.sample))
        samples_cost = np.sum(numbers_array)
        try:
            plate_cost = self.proceduretype.plate_cost or 0.00
        except AttributeError:
            plate_cost = 0.00
        self._cost = plate_cost + samples_cost

    def save(self):
        """
        Persist this procedure after recalculating cost and sample associations.

        :return: None
        """
        from backend.db.models import RunSampleAssociation
        self.set_cost()
        assert self.run is not None
        super().save()
        try:
            rank = max([item.run_rank for item in self.run.runsampleassociation])
        except AttributeError:
            rank = 0
        for iii, sampleassociation in enumerate(self.proceduresampleassociation, start=1):
            if not sampleassociation:
                logger.error(f"No association at rank {iii}")
                continue
            try:
                check = sampleassociation.sample.sample_id in [s.sample_id for s in self.run.sample]
            except AttributeError as e:
                logger.error(f"Couldn't get sample_id due to {e}")
                check = True
            if not check:
                assoc = RunSampleAssociation(sample=sampleassociation.sample, run=self.run, rank=rank+iii)
                assoc.save()
        
    @property
    def column_count(self) -> int:
        """
        Calculate the number of unique columns in this procedure.

        :return: number of unique columns.
        :rtype: int
        """
        columns = set([assoc.column for assoc in self.proceduresampleassociation])
        return len(columns)
    
    @property
    def row_count(self) -> int:
        """
        Calculate the number of unique rows in this procedure.

        :return: number of unique rows.
        :rtype: int
        """
        columns = set([assoc.row for assoc in self.proceduresampleassociation])
        return len(columns)
    
    def update_last_useds(self):
        """
        Update 'last used' reagent lot metadata for each reagent role in this procedure.

        :return: None
        """
        for reagentlotassoc in self.procedurereagentlotassociation:
            reagentrole = reagentlotassoc.reagentrole
            proceduretype = self.proceduretype
            assoc = ProcedureTypeReagentRoleAssociation.query(proceduretype=proceduretype, reagentrole=reagentrole, limit=1)
            if assoc:
                try:
                    assoc.update_last_used(reagentlotassoc.reagentlot)
                except Exception as e:
                    logger.error(f"Error updating last used for {assoc}: {e}")
            else:
                logger.error(f"Association not found for {reagentrole} and {proceduretype}")
                

class Results(BaseClass):
    """
    Represents result metadata and values for a procedure or sample.

    :ivar id: Primary key identifier for the result
    :vartype id: int
    :ivar _result: JSON payload containing result values
    :vartype _result: dict
    :ivar _date_analyzed: Timestamp when the result was analyzed
    :vartype _date_analyzed: datetime|None
    :ivar procedure_id: Foreign key to parent procedure
    :vartype procedure_id: int
    :ivar _procedure: Parent Procedure object
    :vartype _procedure: Procedure
    :ivar assoc_id: Foreign key to sample association
    :vartype assoc_id: int|None
    :ivar _sampleprocedureassociation: Related ProcedureSampleAssociation object
    :vartype _sampleprocedureassociation: ProcedureSampleAssociation|None
    :ivar _img: Zip archive filename for image storage
    :vartype _img: str|None
    :ivar resultstype_id: Foreign key to ResultsType
    :vartype resultstype_id: int
    :ivar _resultstype: Related ResultsType object
    :vartype _resultstype: ResultsType
    """
    id = Column(INTEGER, primary_key=True)  #: primary key
    _result = Column(JSON)  #:
    _date_analyzed = Column(TIMESTAMP)
    procedure_id = Column(INTEGER, ForeignKey("_procedure.id", ondelete='SET NULL',
                                              name="fk_RES_procedure_id"))
    _procedure = relationship("Procedure", back_populates="_results")
    assoc_id = Column(INTEGER, ForeignKey("_proceduresampleassociation.id", ondelete='SET NULL',
                                          name="fk_RES_ASSOC_id"))
    _sampleprocedureassociation = relationship("ProcedureSampleAssociation", back_populates="_results")
    _img = Column(String(128))
    _is_sample = Column(INTEGER, default=0)

    resultstype_id = Column(INTEGER, ForeignKey("_resultstype.id", ondelete='SET NULL',
                                              name="fk_RES_resultstype_id"))
    _resultstype = relationship("ResultsType", back_populates="_results")

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        date_analyzed = kwargs.pop('date_analyzed', None)
        procedure = kwargs.pop('procedure', None)
        sampleprocedureassociation = kwargs.pop('sampleprocedureassociation', None)
        image = kwargs.pop('image', None)
        resultstype = kwargs.pop('resultstype', None)
        result = kwargs.pop('result', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve procedure
        if procedure is not None:
            try:
                self.procedure = procedure
            except Exception:
                logger.error(f"Couldn't set procedure to {procedure} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve date_analyzed
        if date_analyzed is not None:
            try:
                self.date_analyzed = date_analyzed
            except Exception:
                logger.error(f"Couldn't set date_analyzed to {date_analyzed} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve sampleprocedureassociation
        if sampleprocedureassociation is not None:
            try:
                self.sampleprocedureassociation = sampleprocedureassociation
            except Exception:
                logger.error(f"Couldn't set sampleprocedureassociation to {sampleprocedureassociation} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve image
        if image is not None:
            try:
                self.image = image
            except Exception:
                pass
        # Resolve resultstype
        if resultstype is not None:
            try:
                self.resultstype = resultstype
            except Exception:
                logger.error(f"Couldn't set resultstype to {resultstype} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve result
        if result is not None:
            try:
                self.result = result
            except Exception:
                logger.error(f"Couldn't set result to {result} for {self.__class__.__qualname__} with name {self.name}")

    # TODO: Enable query from sample_association in addition to procedure

    @hybrid_property
    def result(self):
        return self._result
    
    @result.setter
    def result(self, value):
        if isinstance(value, str):
            logger.error(f"Got string {value}")
            try:
                value = json.loads(value)
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON: {e}")
        match value:
            case dict():
                self._result = value
            case _:
                logger.error(f"Unmatched value for {self.__class__.__qualname__}._result: {type(value)}")
        
    @hybrid_property
    def name(self):
        try:
            assoc = self.procedure.name
        except AttributeError:
            assoc = "Unassigned Procedure Association"
        try:
            resultstype = self.resultstype.name
        except AttributeError:
            resultstype = "Unassigned ResultsType"
        return f"{assoc} - {resultstype}"
    
    @name.expression
    def name(cls):
        procedure_subquery = (
            select(Procedure.name)
            .where(Procedure.id==cls.procedure_id)
            .correlate(cls)
            .scalar_subquery()
        )
        resultstype_subquery = (
            select(ResultsType.name)
            .where(ResultsType.id==cls.resultstype_id)
            .correlate(cls)
            .scalar_subquery()
        )
        # NOTE: Can't use f strings for this.
        return procedure_subquery + " - " + resultstype_subquery

    @hybrid_property
    def date_analyzed(self):
        return self._date_analyzed if self._date_analyzed else None
    
    @date_analyzed.setter
    def date_analyzed(self, value):
        if isinstance(value, dict):
            value = value.get("value", datetime.now())
        match value:
            case datetime():
                output = value
            case date():
                output = datetime.combine(value, datetime.now().time())
            case int():
                output = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value - 2)
            case str():
                string = re.sub(r"(_|-)\d(R\d)?$", "", value)
                try:
                    output = dateparse(string)
                except ParserError as e:
                    logger.error(f"Problem parsing date: {e}")
                    try:
                        output = dateparse(string.replace("-", ""))
                    except Exception as e:
                        logger.error(f"Problem with parse fallback: {e}")
                        return value
            case _:
                raise ValueError(f"Unmatched value {value} for {self.__class__.__qualname__}.date_analyzed")
        value = output.replace(tzinfo=timezone)
        self._date_analyzed = output

    @hybrid_property
    def resultstype(self):
        return self._resultstype

    @resultstype.setter
    def resultstype(self, value):
        from backend.validators.pydant import PydResultsType
        match value:
            case str():
                output = ResultsType.query(name=value, limit=1)
            case dict():
                output = ResultsType.query_or_create(**value)
            case PydResultsType():
                output = value.to_sql(update=False)
            case ResultsType():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._resultstype")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ResultsType):
            self._resultstype = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._resultstype to {type(output)}")
    
    @hybrid_property
    def procedure(self):
        return self._procedure

    @procedure.setter
    def procedure(self, value):
        from backend.validators.pydant import PydProcedure
        match value:
            case str():
                output = Procedure.query(name=value, limit=1)
            case dict():
                output = Procedure.query_or_create(**value)
            case PydProcedure():
                output = value.to_sql(update=False)
            case Procedure():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for procedure")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, Procedure):
            self._procedure = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._procedure to {type(output)}")

    @hybrid_property
    def sampleprocedureassociation(self):
        return self._sampleprocedureassociation

    @sampleprocedureassociation.setter
    def sampleprocedureassociation(self, value):
        """
        Input objects will be assumed to be sample only and use self.procedure to set.
        """
        from backend.validators.pydant import PydProcedureSampleAssociation
        from backend.db.models import ProcedureSampleAssociation
        try:
            proc = self.procedure
        except AttributeError as e:
            logger.critical(f"Could not get procedure for setting association.")
            raise e
        match value:
            case str():
                output = ProcedureSampleAssociation.query(sample=value, procedure=proc, limit=1)
            case dict():
                output = ProcedureSampleAssociation.query_or_create(**value)
            case PydProcedureSampleAssociation():
                output = value.to_sql(update=False)
            case ProcedureSampleAssociation():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._sampleprocedureassociation")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ProcedureSampleAssociation):
            self._sampleprocedureassociation = output
            try:
                self.procedure = output.procedure
            except Exception as e:
                logger.error(f"Problem setting procedure from sampleprocedureassociation: {e}")
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._sampleprocedureassociation to {output} of type {type(output)}")
    
    @property
    def sample_id(self):
        if self.assoc_id:
            try:
                return self.sampleprocedureassociation.sample.sample_id
            except AttributeError:
                return None
        else:
            return None

    @property
    def image(self) -> bytes | None:
        dir = self.__directory_path__.joinpath("submission_imgs.zip")
        if not self._img:
            return None
        try:
            assert dir.exists()
        except AssertionError:
            return None
        with zipfile.ZipFile(dir) as zf:
            with zf.open(self._img) as f:
                return f.read()

    @image.setter
    def image(self, value):
        self._img = value

    @hybrid_property
    def is_sample(self):
        if self._is_sample is not None:
            return bool(self._is_sample)
        else:
            return self.assoc_id is not None
        
    @is_sample.setter
    def is_sample(self, value):
        if value is None:
            value = False
        self._is_sample = int(value)

    def to_pydantic(self, pyd_model_name: str | None = None, **kwargs):
        output = super().to_pydantic(pyd_model_name=pyd_model_name, **kwargs)
        if bool(self.sample_id):
            output.sample_id = self.sample_id
            output.sample = self.sampleprocedureassociation.sample.sample_id
        if self.result:
            for k, v in self.result.items():
                setattr(output, k, v)
        return output


class ResultsType(BaseClass):

    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(64), nullable=False, unique=True)
    _info = Column(JSON) #: where to look for procedure information
    _samples = Column(JSON) # where to look for sample information
    _results = relationship("Results", back_populates="_resultstype", cascade="all, delete-orphan")
    _proceduretype = relationship(ProcedureType, back_populates="_resultstype", secondary=proceduretype_resulttype)
    _saved_settings = Column(JSON)

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        results = kwargs.pop('results', None)
        proceduretype = kwargs.pop('proceduretype', None)
        info = kwargs.pop("info", {})
        samples = kwargs.pop("samples", {})
        saved_settings = kwargs.pop("saved_settings", [])
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if proceduretype is not None:
            try:
                self.proceduretype = proceduretype
            except Exception:
                # fallback: store in misc_info if setter fails
                logger.error(f"Couldn't set proceduretype to {proceduretype} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve results
        if results is not None:
            try:
                self.results = results
            except Exception:
                logger.error(f"Couldn't set results to {results} for {self.__class__.__qualname__} with name {self.name}")
        self.info = info
        self.samples = samples
        self.saved_settings = saved_settings

    @hybrid_property
    def proceduretype(self):
        return self._proceduretype

    @proceduretype.setter
    def proceduretype(self, value):
        from backend.validators.pydant import PydProcedureType
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = ProcedureType.query(name=item, limit=1)
                case dict():
                    output = ProcedureType.query_or_create(**item)
                case PydProcedureType():
                    output = item.to_sql(update=False)
                case ProcedureType():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._proceduretype")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, ProcedureType):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._proceduretype")
        self._proceduretype = list_

    @hybrid_property
    def results(self):
        return self._results

    @results.setter
    def results(self, value):
        from backend.validators.pydant import PydResults
        from backend.db.models import Results
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = Results.query(name=item, limit=1)
                case dict():
                    output = Results.query_or_create(**item)
                case PydResults():
                    output = item.to_sql()
                case Results():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._results")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, Results):
                list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}_results")
        self._results = list_

    @hybrid_property
    def info(self) -> dict:
        return self._info
    
    @info.setter
    def info(self, value):
        if isinstance(value, dict):
            self._info = value
        else:
            raise ValueError(f"Unmatched type {type(value)} for {self.__class__.__qualname__}._info")

    @hybrid_property
    def samples(self) -> dict:
        return self._samples
    
    @samples.setter
    def samples(self, value):
        if isinstance(value, dict):
            self._samples = value
        else:
            raise ValueError(f"Unmatched type {type(value)} for {self.__class__.__qualname__}._samples")

    @hybrid_property
    def saved_settings(self):
        return self._saved_settings or []
    
    @saved_settings.setter
    def saved_settings(self, value):
        if isinstance(value, dict):
            self._saved_settings = value
        else:
            raise ValueError(f"Unmatched type {type(value)} for {self.__class__.__qualname__}._saved_settings")

    def to_pydantic(self, pyd_model_name: str | None = None, **kwargs) -> BaseModel:
        return super().to_pydantic(pyd_model_name, **kwargs)


from .equipment import *
from .reagents import *

__all__ = ["Discount", "SubmissionType", "ProcedureType", "Procedure", "Results", "ResultsType",
           "EquipmentRole", "Equipment", "EquipmentRoleEquipmentAssociation", "Process", "ProcessVersion", 
           "Tips", "TipsLot", "ProcedureEquipmentTipslotAssociation", "ProcedureEquipmentAssociation", "ProcedureTypeEquipmentRoleAssociation",
           "equipmentroleequipmentassociation_process", "process_tips",
           "ReagentRole", "Reagent", "ReagentLot", "ReagentRoleReagentAssociation", "ProcedureTypeReagentRoleAssociation", "ProcedureReagentLotAssociation"]
