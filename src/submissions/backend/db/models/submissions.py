"""
Models for the main procedure and sample types.
"""
from __future__ import annotations
from logging import getLogger
from pprint import pprint
logger = getLogger(f"submissions.{__name__}")
from pydantic import BaseModel
from getpass import getuser
from itertools import chain
from types import GeneratorType, NoneType
from pandas import DataFrame
from numpy import sum as npsum, busday_count
from tempfile import NamedTemporaryFile
from uuid import uuid4
from inspect import isclass
from operator import attrgetter
from pandas import DataFrame
from sqlalchemy.ext.hybrid import hybrid_property
from . import BaseClass, SubmissionType, ClientLab, Contact, LogMixin, Procedure
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from sqlalchemy import Column, String, TIMESTAMP, INTEGER, ForeignKey, JSON, FLOAT, UniqueConstraint, cast, func, select, or_
from sqlalchemy.orm import relationship, Query, declared_attr
from sqlalchemy.ext.associationproxy import association_proxy, _AssociationList
from sqlalchemy.exc import OperationalError as AlcOperationalError, IntegrityError as AlcIntegrityError
from sqlalchemy.ext.mutable import MutableList
from sqlite3 import OperationalError as SQLOperationalError, IntegrityError as SQLIntegrityError
from tools import (
    TimeFill, check_authorization, convert_row_column_to_well, flatten_list, replace_or_prepend_prefix, setup_lookup, jinja_template_loading, create_holidays_for_year,
    is_power_user, Report, get_application_from_parent, iterable_enforcer
)
from backend.validators.shared import parse_optional_datetime, vet_comment
from datetime import datetime, date
from typing import Any, Dict, Generator, List, TYPE_CHECKING, Literal, Set
from pathlib import Path
if TYPE_CHECKING:
    from submissions.backend.db.models.procedures import ProcedureType, Procedure, Results
    from backend.validators.pydant import (
        PydSample, PydClientSubmission, PydProcedureSampleAssociation, 
        PydSubmissionType, SourcedField, PydContact, PydRun, PydClientLab,
        PydClientSubmissionSampleAssociation, PydResults
    )
    from frontend.widgets import SubmissionsTree, SubmissionFormContainer
    from frontend.widgets.omni_search import SearchResults


class ClientSubmission(BaseClass, LogMixin):
    """
    Represents a client-submitted batch of samples awaiting or undergoing analysis.

    A submission groups one or more samples, the submitting client laboratory,
    the relevant contact, and the associated processing metadata. It serves as
    the primary record tying incoming client work to the linked runs and sample
    records used throughout the workflow.

    :ivar id: Primary key identifier for the submission.
    :vartype id: int
    :ivar submitter_plate_id: Plate or batch identifier assigned by the submitting lab.
    :vartype submitter_plate_id: str
    :ivar submitted_date: Date and time the submission was received.
    :vartype submitted_date: datetime | None
    :ivar clientlab: Client laboratory associated with the submission.
    :vartype clientlab: ClientLab
    :ivar contact: Contact representing the submitting laboratory.
    :vartype contact: Contact | None
    :ivar submissiontype: Submission type defining the expected workflow and validation rules.
    :vartype submissiontype: SubmissionType | None
    :ivar run: Runs associated with this submission.
    :vartype run: list[Run]
    :ivar sample: Samples attached to the submission.
    :vartype sample: list[Sample]
    :ivar cost_centre: Cost centre stored for billing or accounting purposes.
    :vartype cost_centre: str | None
    :ivar submission_category: Classification used to describe the type of submission.
    :vartype submission_category: str | None
    """
    id = Column(INTEGER, primary_key=True)  #: primary key
    _submitter_plate_id = Column(String(127), unique=True)  #: The number given to the submission by the submitting lab
    _submitted_date = Column(TIMESTAMP)  #: Date submission received
    _clientlab = relationship("ClientLab", back_populates="_clientsubmission")  #: client org
    clientlab_id = Column(INTEGER, ForeignKey("_clientlab.id", ondelete="SET NULL", name="fk_BS_sublab_id"))  #: client lab id from _organizations
    submission_category = Column(String(64))  #: i.e. Surveillance
    # full_batch_size = Column(INTEGER)  #: Number of wells in provided plate. 0 if no plate.
    _comment = Column(MutableList.as_mutable(JSON))
    _run = relationship("Run", back_populates="_clientsubmission")  #: many-to-one relationship
    _contact = relationship("Contact", back_populates="_clientsubmission")  #: contact representing submitting lab.
    contact_id = Column(INTEGER, ForeignKey("_contact.id", ondelete="SET NULL", name="fk_BS_contact_id"))  #: contact id from _organizations
    submissiontype_name = Column(String, ForeignKey("_submissiontype.name", ondelete="SET NULL", name="fk_BS_subtype_name"))  #: name of joined submission type
    _submissiontype = relationship("SubmissionType", back_populates="_clientsubmission")  #: archetype of this procedure
    cost_centre = Column(String(64))  #: Permanent storage of used cost centre in case organization field changed in the future.

    clientsubmissionsampleassociation = relationship(
        "ClientSubmissionSampleAssociation",
        back_populates="_clientsubmission",
        cascade="all, delete-orphan",
        lazy="selectin",
    )  #: Relation to ClientSubmissionSampleAssociation

    _sample = association_proxy("clientsubmissionsampleassociation",
                               "_sample", creator=lambda sample: ClientSubmissionSampleAssociation(
                                sample=sample))  #: Association proxy to ClientSubmissionSampleAssociation.sample

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        submitted_date = kwargs.pop('submitted_date', None)
        clientlab = kwargs.pop('clientlab', None)
        run = kwargs.pop('run', None)
        contact = kwargs.pop('contact', None)
        submissiontype = kwargs.pop('submissiontype', None)
        sample = kwargs.pop('sample', None)
        submitter_plate_id = kwargs.pop("submitter_plate_id", None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        if submitter_plate_id is not None:
            self.submitter_plate_id = submitter_plate_id
        # Resolve proceduretype
        if submitted_date is not None:
            try:
                self.submitted_date = submitted_date
            except Exception:
                logger.error(f"Couldn't set submitted_date to {submitted_date} for {self.__class__.__qualname__} with name {self.name}")
        if clientlab is not None:
            try:
                self.clientlab = clientlab
            except Exception:
                logger.error(f"Couldn't set clientlab to {clientlab} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve run
        if run is not None:
            try:
                self.run = run
            except Exception:
                logger.error(f"Couldn't set run to {run} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve contact
        if contact is not None:
            try:
                self.contact = contact
            except Exception:
                logger.error(f"Couldn't set contact to {contact} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve submissiontype
        if submissiontype is not None:
            try:
                self.submissiontype = submissiontype
            except Exception:
                logger.error(f"Couldn't set submissiontype to {submissiontype} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve sample
        if sample is not None:
            try:
                self.sample = sample
            except Exception:
                logger.error(f"Couldn't set sample to {sample} for {self.__class__.__qualname__} with name {self.name}")
        self._comment = [] if self._comment is None else self._comment

    @hybrid_property
    def submitter_plate_id(self) -> str:
        """
        Gets the plate number submitted by the client lab.

        :return: self._submitter_plate_id or "Not Set"
        :rtype: str 
        """
        return self._submitter_plate_id or "Not Set"
    
    @submitter_plate_id.setter
    def submitter_plate_id(self, value: str | dict):
        """
        Sets the plate number submitted by the client lab. Defaults to a unique user id 4 string.

        :param value: Input object.
        :type value: str | dict
        """
        if isinstance(value, dict):
            value = value.get("value", uuid4().__str__())
        self._submitter_plate_id = value

    @hybrid_property
    def submissiontype(self) -> SubmissionType:
        """
        Gets the submission type of this ClientSubmission.

        :return: self._submissiontype
        :rtype: SubmissionType
        """
        return self._submissiontype

    @submissiontype.setter
    def submissiontype(self, value: str | dict | SourcedField | PydSubmissionType | SubmissionType):
        """
        Sets the submission type of this submission by parsing an input object.

        :param value: Input object
        :type value: str | dict | SourcedField, PydSubmissionType | SubmissionType
        """
        from backend.validators import PydSubmissionType, SourcedField
        match value:
            case str():
                output = SubmissionType.query(name=value, limit=1)
            case dict():
                output = SubmissionType.query_or_create(**value)
            case SourcedField():
                output = SubmissionType.query(name=value.value)
            case PydSubmissionType():
                output = value.to_sql(update=False)
            case SubmissionType():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for submissiontype")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, SubmissionType):
            self._submissiontype = output
        else:
            logger.error(f"Could not set _submissiontype to {type(output)}")

    @hybrid_property
    def contact(self) -> Contact:
        """
        Get the contact who submitted this object.

        :return: self._contact
        :rtype: Contact
        """
        return self._contact

    @contact.setter
    def contact(self, value: str | dict | PydContact | Contact):
        """
        Set the contact who submitted this object by parsing an input object.

        :param value: Input object.
        :type value: str | dict | PydContact | Contact
        """
        from backend.validators.pydant import PydContact
        match value:
            case str():
                output = Contact.query(name=value, limit=1)
            case dict():
                output = Contact.query_or_create(**value)
            case PydContact():
                output = value.to_sql(update=False)
                if isinstance(output, tuple):
                    output = output[0]
            case Contact():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for contact")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, Contact):
            self._contact = output
        else:
            logger.error(f"Could not set _contact to {type(output)}")

    @hybrid_property
    def run(self) -> List[Run]:
        """
        Get the runs created from this submission.

        :return: self._run
        :rtype: List[Run]
        """
        return self._run
    
    @run.setter
    def run(self, value: List[str | dict | PydRun | Run]):
        """
        Set the runs created from this submission by parsing a list of input objects.

        :param value: List of input objects.
        :type value: List[str | dict | PydRun | Run]
        """
        from backend.validators.pydant import PydRun
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case str():
                    output = Run.query(name=item, limit=1)
                case dict():
                    output = Run.query_or_create(**item)
                case PydRun():
                    output = item.to_sql(update=False)
                case Run():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._run")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, Run):
                self._run.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._run")

    @hybrid_property
    def clientlab(self) -> ClientLab:
        """
        Get the client lab that made this submission.

        :return: self._clientlab
        :rtype: ClientLab
        """
        return self._clientlab

    @clientlab.setter
    def clientlab(self, value: str | dict | SourcedField | PydClientLab | ClientLab):
        """
        Set the submitting client lab by parsing an input object.

        :param value: The input object
        :type value: str | dict | SourcedField | PydClientLab | ClientLab
        """
        from backend.validators.pydant import PydClientLab, SourcedField
        match value:
            case str():
                output = ClientLab.query(name=value, limit=1)
            case dict():
                output = ClientLab.query_or_create(**value)
            case SourcedField():
                output = ClientLab.query(name=value.value)
            case PydClientLab():
                output = value.to_sql(update=False)
            case ClientLab():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for clientlab")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ClientLab):
            self._clientlab = output
        else:
            logger.error(f"Could not set _clientlab to {type(output)}")

    @hybrid_property
    def sample(self) -> List[Sample]:
        """
        Get the list of samples in this submission.

        :return: self._sample
        :rtype: List[Sample]
        """
        return self._sample
    
    @sample.setter
    def sample(self, value: List[str | dict | PydSample | Sample | ClientSubmissionSampleAssociation]):
        """
        Set the list of samples in this submission by parsing a list of input objects.

        :param value: List of input objects.
        :type value: List[str | dict | PydSample | Sample | ClientSubmissionSampleAssociation]
        """
        from backend.validators.pydant.concrete import PydSample
        if not isinstance(value, list) and not isinstance(value, _AssociationList):
            value = [value]
        samples = []
        for item in value:
            if item is None:
                continue
            match item:
                case str():
                    try:
                        output = next((assoc for assoc in self.clientsubmissionsampleassociation if assoc.sample.name==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.sample.name for eq in self.clientsubmissionsampleassociation]}")
                        output = ClientSubmissionSampleAssociation(sample=item, clientsubmission=self)
                case dict():
                    output = ClientSubmissionSampleAssociation(sample=item, clientsubmission=self, **{k: v for k, v in item.items() if k != 'name'})
                case PydSample():
                    output = ClientSubmissionSampleAssociation(sample=item, clientsubmission=self, **{k: v for k, v in item.__dict__.items() if k != 'name'})
                case Sample():
                    output = ClientSubmissionSampleAssociation(sample=item, clientsubmission=self, **{k: v for k, v in item._misc_info.items() if k != 'name'})
                case ClientSubmissionSampleAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} of type {type(item)} for sample")
                    continue
            # This indicates that the setter is being run in two duplicate batches
            if isinstance(output, ClientSubmissionSampleAssociation):
                try:
                    check = PydSample.is_sample_id_valid(output.sample.sample_id)
                except AttributeError as e:
                    logger.exception(f"Couldn't get sample_id due to {e}")
                    check = True
                if not check:
                    continue
                # Check for existing association by comparing all primary key values
                is_duplicate = any(
                    all(
                        getattr(existing, pk) == getattr(output, pk)
                        for pk in output.get_primary_keys()
                    )
                    for existing in samples
                )
                if not is_duplicate and output.sample not in (s.sample for s in samples):
                    samples.append(output)
            else:
                logger.error(f"Could not add {output} to {self.__class__.__qualname__}._sample")
        # As of here, samples is empty.
        self.clientsubmissionsampleassociation = samples

    @hybrid_property
    def submitted_date(self) -> datetime:
      """
      Get the date this submission was made.

      :return: self._submitted_date
      :rtype: datetime
      """
      return self._submitted_date

    @submitted_date.setter
    def submitted_date(self, value: dict | SourcedField | str | datetime | date | int | None):
        """
        Set the date this submission was made by parsing an input value.
        Uses validators.shared.parsed_optional_datetime

        :param value: Input object.
        :type value: dict | SourcedField | str | datetime | date | int | None
        """
        self._submitted_date = parse_optional_datetime(value)

    @hybrid_property
    def completed_date(self) -> datetime | None:
        """
        Get the calculated datetime this submission was completed. Defaults to None.

        :return: max([run.completed_date for run in self.run if run.completed_date])
        :rtype: datetime | None
        """
        if self.run:
            dates = [run.completed_date for run in self.run if run.completed_date]
            if not dates:
                return None
            return max(dates, default=None)
        return None

    @hybrid_property
    def name(self) -> str:
        """
        Gets the submitter plate id.

        :return: self.submitter_plate_id
        """
        return self.submitter_plate_id

    @hybrid_property
    def comment(self) -> List[Dict[str, Any]]:
        """
        Gets comments associated with this ClientSubmission

        :return: [item for item in self._comment if all(key in ['user', 'text', 'time'] for key in item.keys())]
        :rtype: List[dict[str, Any]]
        """
        if not self._comment:
            return []
        if not isinstance(self._comment, list):
            return []
        return [item for item in self._comment if all(key in ['user', 'text', 'time'] for key in item.keys())]
    
    @comment.setter
    def comment(self, value: dict | List[dict]):
        """
        Set comments for this ClientSubmission by parsing input objects.
        Uses validators.shared.vet_comment

        :param value: Input comment(s).
        :type value: dict | List[dict]
        """
        self._comment = vet_comment(value, current=self._comment)

    @property
    def sample_count(self) -> int:
        """
        Gets number of samples in this submission.

        :return: len(self.clientsubmissionsampleassociation) 
        :rtype: int
        """
        return len(self.clientsubmissionsampleassociation)

    @property
    def max_sample_rank(self) -> int:
        """
        Gets the maximum rank of samples in this submission.

        :return: max([item.submission_rank for item in self.clientsubmissionsampleassociation]) or 0
        :rtype: int
        """
        try:
            return max([item.submission_rank for item in self.clientsubmissionsampleassociation])
        except ValueError:
            return 0

    @property
    def abbreviation(self) -> str:
        """
        Get the submission type abbreviation of this submission. Defaults to 'CC'

        :return: self.submissiontype.abbreviation or "CC"
        :rtype: str
        """
        return self.submissiontype.abbreviation or "CC"

    @classmethod
    @setup_lookup
    def query(cls,
              submissiontype: str | SubmissionType | list[str | SubmissionType] | None = None,
              clientlab: str | ClientLab | None = None,
              id: int | str | None = None,
              submitter_plate_id: str | None = None,
              start_date: date | datetime | str | int | None = None,
              end_date: date | datetime | str | int | None = None,
              chronologic: bool = False,
              limit: int = 0,
              page: int = 1,
              page_size: None | int = 250,
              **kwargs
              ):
        """
        Lookup procedure based on a number of parameters. Overrides parent.

        Args:
            submissiontype (str | SubmissionType | list[str | SubmissionType] | None, optional): Submission type(s) of interest. Defaults to None.
            id (int | str | None, optional): Submission id in the database (limits results to 1). Defaults to None.
            rsl_plate_number (str | None, optional): Submission name in the database (limits results to 1). Defaults to None.
            start_date (date | str | int | None, optional): Beginning date to search by. Defaults to None.
            end_date (date | str | int | None, optional): Ending date to search by. Defaults to None.
            reagent (models.Reagent | str | None, optional): A reagent used in the procedure. Defaults to None.
            chronologic (bool, optional): Return results in chronologic order. Defaults to False.
            limit (int, optional): Maximum number of results to return. Defaults to 0.

        Returns:
            models.Run | List[models.Run]: Submission(s) of interest
        """
        # NOTE: if you go back to using 'model' change the appropriate cls to model in the query filters
        query: Query = cls.__database_session__.query(cls)
        if start_date is not None and end_date is None:
            logger.warning(f"Start date with no end date, using today.")
            end_date = date.today()
        if end_date is not None and start_date is None:
            # NOTE: this query returns a tuple of (object, datetime), need to get only datetime.
            start_date = cls.__database_session__.query(cls, func.min(cls.submitted_date)).first()[1]
            logger.warning(f"End date with no start date, using first procedure date: {start_date}")
        if start_date is not None:
            start_date = cls.rectify_query_date(start_date, timefill=TimeFill.MIN)
            end_date = cls.rectify_query_date(end_date, timefill=TimeFill.MAX)
            query = query.filter(cls.submitted_date.between(start_date, end_date))
        # NOTE: by rsl number (returns only a single value)
        match submitter_plate_id:
            case str():
                query = query.filter(cls.submitter_plate_id == submitter_plate_id)
                limit = 1
            case _:
                pass
        match submissiontype:
            case list():
                submission_filters = []
                for st in submissiontype:
                    if isinstance(st, SubmissionType):
                        submission_filters.append(cls.submissiontype == st)
                    elif isinstance(st, str):
                        submission_filters.append(cls.submissiontype_name == st)
                if submission_filters:
                    query = query.filter(or_(*submission_filters))
            case SubmissionType():
                query = query.filter(cls.submissiontype == submissiontype)
            case str():
                query = query.filter(cls.submissiontype_name == submissiontype)
            case _:
                pass
        match clientlab:
            case ClientLab():
                query = query.filter(cls.clientlab == clientlab)
            case str():
                query = query.join(ClientLab).filter(ClientLab.name == clientlab)
            case _:
                pass
        # NOTE: by id (returns only a single value)
        match id:
            case int():
                query = query.filter(cls.id == id)
                limit = 1
            case str():
                query = query.filter(cls.id == int(id))
                limit = 1
            case _:
                pass
        # NOTE: Split query results into pages of size {page_size}
        if page_size > 0 and limit == 0:
            limit = page_size
        page = page - 1
        if page is not None:
            offset = page * page_size
        else:
            offset = None
        if chronologic:
            query = query.order_by(cls.submitted_date.desc())
        return cls.execute_query(query=query, limit=limit, offset=offset, **kwargs)

    @classmethod
    def submissions_to_df(cls, submissiontype: str | None = None, limit: int = 0,
                          chronologic: bool = True, page: int = 1, page_size: int = 250) -> DataFrame:
        """
        Convert all procedure to dataframe

        
        :param page_size: Number of items to include in query result. Defaults to 250.
        :type page_size: int
        :param page: Limits the number of procedure to a page size. Defaults to 1.
        :type page: int 
        :param chronologic: Sort procedure in chronologic order. Defaults to True.
        :type chronologic: bool
        :param submissiontype: Filter by SubmissionType. Defaults to None.
        :type submissiontype: str | None
        :param limit: Maximum number of results to return. Defaults to 0.
        :type limit: int

        :return: Pandas Dataframe of all relevant procedure
        :rtype: DataFrame:
        """
        # NOTE: use lookup function to create list of dicts
        subs = [item.details_dict for item in
                cls.query(submissiontype=submissiontype, limit=limit, chronologic=chronologic, page=page,
                          page_size=page_size)]
        df = DataFrame.from_records(subs)
        # NOTE: Exclude sub information
        exclude = ['control', 'extraction_info', 'pcr_info', 'comment', 'comments', 'sample', 'reagents',
                   'equipment', 'gel_info', 'gel_image', 'dna_core_submission_number', 'gel_controls',
                   'source_plates', 'pcr_technician', 'ext_technician', 'artic_technician', 'cost_centre',
                   'signed_by', 'artic_date', 'gel_barcode', 'gel_date', 'ngs_date', 'contact_phone', 'contact',
                   'tips', 'gel_image_path', 'custom']
        # NOTE: dataframe equals dataframe of all columns not in exclude
        df = df.loc[:, ~df.columns.isin(exclude)]
        if chronologic:
            try:
                df.sort_values(by="id", axis=0, inplace=True, ascending=False)
            except KeyError:
                logger.error("No column named 'id'")
        # NOTE: Human friendly column labels
        df.columns = [item.replace("_", " ").title() for item in df.columns]
        return df

    @property
    def custom_context_events(self) -> dict:
        """
        Creates dictionary of str:function to be passed to context menu.
        Current options: ["Add Run", "Edit", "Add Comment", "Show Details", "Delete"]

        :return: {item: self.__getattribute__(item.lower().replace(" ", "_")) for item in names}
        :rtype: dict
        """
        names = ["Add Run", "Edit", "Add Comment", "Show Details", "Delete"]
        return {item: self.__getattribute__(item.lower().replace(" ", "_")) for item in names}

    def add_run(self, obj: SubmissionsTree):
        """
        From frontend.widgets.SubmissionTree. Creates a new run from this submission.

        :param obj: Widget used as parent.
        :type obj: SubmissionsTree
        """
        from frontend.widgets.sample_checker import SampleChecker
        from backend.validators.pydant import SourcedField
        samples = [assoc.to_pydantic() for assoc in self.clientsubmissionsampleassociation]
        run = Run.construct_dummy_run(clientsubmission=self)
        logger.debug(f"Run: {run.rsl_plate_number}")
        checker = SampleChecker(parent=None, title="Create Run", samples=samples, run=run)
        if checker.exec():
            run.rsl_plate_number = SourcedField(value=checker.rsl_plate_number)
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                # Rank the selected pydantic samples, then convert them back to SQL Sample
                selected_samples = []
                for iii, sample in enumerate(samples, start=1):
                    if not sample.enabled:
                        logger.info(f"Skipping disabled sample {sample.sample_id} at rank {iii}")
                        continue
                    else:
                        sample = self.rank_sample(sample, iii)
                        selected_samples.append(sample)
                run.sample = [s for s in selected_samples]
                run = run.to_sql()             
                if isinstance(run, tuple):
                    run = run[0]
                run.save()
            finally:
                QApplication.restoreOverrideCursor()
        else:
            logger.warning("Run cancelled.")
        # Incrementally refresh just this submission's row rather than rebuilding
        # the whole tree. Fall back to a full refresh if the view predates upsert.
        if hasattr(obj, "upsert_submission"):
            obj.upsert_submission(self)
        else:
            obj.set_data()

    def edit(self, obj: SubmissionFormContainer):
        """
        Opens details of this submission in the left pane.

        :param obj: The widget to be used as parent.
        :type obj: SubmissionFormContainer
        """
        app = get_application_from_parent(obj)
        app.table_widget.formwidget.edit_submission_function(clientsubmission=self)

    def add_comment(self, obj):
        """
        Add a comment to this procedure.

        This method is a placeholder for comment UI integration.

        :param obj: Parent object for the comment action.
        :type obj: Any
        """
        logger.info("Add Comment!")
        from frontend.widgets import SubmissionComment
        dlg = SubmissionComment(parent=obj, submission=self)
        if dlg.exec():
            comment = dlg.parse_form()
            self.comment = comment
            self.save()

    def to_pydantic(self, filepath: Path | str | None = None, **kwargs) -> PydClientSubmission:
        """
        Convert this submission into a PydClientSubmission.

        :param filepath: Filepath of the parsed submission form. Defaults to None.
        :type filepath: Path | str | None
        :return: super().to_pydantic(filepath=filepath, **kwargs)
        :rtype: PydClientSubmission
        """
        output = super().to_pydantic(filepath=filepath, **kwargs)
        return output
    
    @property
    def turnaround_time(self) -> int | None:
        """
        Calculates turnaround time in days from submitted_date to completed_date of the run. 

        :return: Turnaround time in days or None if no run or completed_date. 
        :rtype: int | None: 
        """
        try:
            if self.completed_date is None:
                return None
            return (self.completed_date - self.submitted_date).days + 1
        except IndexError:
            logger.warning("No run associated with this submission, cannot calculate turnaround time.")
            return None
    
    @property
    def met_turnaround_time(self) -> bool:
        """
        Returns if this clientsubmission has met the submission type's turnaround time limit.

        :return: self.turnaround_time < self.submissiontype.turnaround_time.days
        :rtype: bool
        """
        return self.turnaround_time < self.submissiontype.turnaround_time.days if self.turnaround_time is not None and self.submissiontype.turnaround_time is not None else False

    @classmethod
    def get_lab_submissions_by_day(cls, clientlab: ClientLab | None = None, search_date: date | None = None) -> int:
        """
        Gets number of submissions a client has made on a given day. (Used to compute plate number)

        :param clientlab: Submitting lab.
        :type clientlab: ClientLab
        :param search_date: The date to be searched. Defaults to date.today
        :type search_date: date
        """
        if search_date is None:
            search_date = date.today()
        results = cls.query(clientlab=clientlab, start_date=search_date)
        return len(results)
        
    @check_authorization
    def delete(self, obj: SubmissionsTree | None =None):
        """
        Performs backup and deletes this instance from database.

        :param obj: Parent widget. Defaults to None.
        :type obj: SubmissionsTree | None

        :raises: SQLIntegrityError or SQLOperationalError if problem with commit.
        """
        from frontend.widgets.pop_ups import QuestionAsker
        msg = QuestionAsker(title="Delete?", message=f"Are you sure you want to delete {self.submitter_plate_id}?\n")
        if msg.exec():
            self.run = []
            self.clientsubmissionsampleassociation = []
            self.__database_session__.delete(self)
            try:
                self.__database_session__.commit()
            except (SQLIntegrityError, SQLOperationalError, AlcIntegrityError, AlcOperationalError) as e:
                self.__database_session__.rollback()
                raise e
            try:
                obj.set_data()
            except AttributeError:
                logger.exception("App will not refresh data at this time.")

    def get_procedure_sample_results(self, include=Set[Literal['positive', 'negative', 'samples']]) -> Generator[Results, None, None]:
        """
        Gets samples associated with this submission that are controls based on their sample_id starting with "blank", "na", "none", or being empty.

        :param include: Which control types/samples are included.
        :type include: Set[Literal['positive', 'negative', 'samples']]
        :return: List of control samples
        :rtype: Generator[Results, None, None]
        """
        for run in self.run:
            if run.completed_date is None:
                continue
            for procedure in run.procedure:
                for proceduresampleassociation in procedure.proceduresampleassociation:
                    if proceduresampleassociation.sample.is_control == 1 and "positive" not in include:
                        continue
                    elif proceduresampleassociation.sample.is_control == 0 and "samples" not in include:
                        continue
                    elif proceduresampleassociation.sample.is_control == -1 and "negative" not in include:
                        continue
                    else:
                        for result in proceduresampleassociation.results:
                            yield result

        
class Run(BaseClass, LogMixin):
    """
    Represents a single analytical run associated with a client submission.

    A run groups a plate or batch of samples through one workflow execution,
    linking the parent submission to its procedure records, sample set, and
    operational timing metadata. It is the main unit used to track the progress
    and completion of a submitted batch.

    :ivar id: Primary key identifier for the run.
    :vartype id: int
    :ivar rsl_plate_number: RSL-assigned plate number for this run.
    :vartype rsl_plate_number: str
    :ivar clientsubmission_id: Foreign key referencing the parent client submission.
    :vartype clientsubmission_id: int
    :ivar clientsubmission: Parent submission associated with the run.
    :vartype clientsubmission: ClientSubmission
    :ivar started_date: Date and time the run began.
    :vartype started_date: datetime | None
    :ivar completed_date: Date and time the run finished.
    :vartype completed_date: datetime | None
    :ivar run_cost: Total cost associated with executing the run.
    :vartype run_cost: float | None
    :ivar signed_by: User or operator who signed off on the run.
    :vartype signed_by: str | None
    :ivar comment: Free-form notes recorded for the run.
    :vartype comment: list | None
    :ivar procedure: Procedures linked to this run.
    :vartype procedure: list[Procedure]
    :ivar sample: Samples associated with this run.
    :vartype sample: list[Sample]
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    _rsl_plate_number = Column(String(32), unique=True, nullable=False)  #: RSL name (e.g. RSL-22-0012)
    clientsubmission_id = Column(INTEGER, ForeignKey("_clientsubmission.id", ondelete="CASCADE",
                                                     name="fk_BS_clientsub_id"), nullable=False)  #: id of parent clientsubmission, set to CASCADE to delete runs if clientsubmission is deleted
    _clientsubmission = relationship("ClientSubmission", back_populates="_run")  #: parent clientsubmission
    _started_date = Column(TIMESTAMP)  #: Date this procedure was started.
    _run_cost = Column(FLOAT(2))  #: total cost of running the plate. Set from constant and mutable kittype costs at time of creation.
    _signed_by = Column(String(32))  #: user name of person who submitted the procedure to the database.
    _comment = Column(MutableList.as_mutable(JSON))  #: user notes
    _completed_date = Column(TIMESTAMP)  #: Date this procedure was finished.
    _procedure = relationship("Procedure", back_populates="_run", uselist=True)  #: children procedures

    runsampleassociation = relationship(
        "RunSampleAssociation",
        back_populates="_run",
        cascade="all, delete-orphan",
    )  #: Relation to ClientSubmissionSampleAssociation

    _sample = association_proxy("runsampleassociation", "_sample")

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        started_date = kwargs.pop('started_date', None)
        clientsubmission = kwargs.pop('clientsubmission', None)
        completed_date = kwargs.pop('completed_date', None)
        procedure = kwargs.pop('procedure', None)
        sample = kwargs.pop('sample', None)
        rsl_plate_number = kwargs.pop("rsl_plate_number", None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        if clientsubmission is not None:
            try:
                self.clientsubmission = clientsubmission
            except Exception:
                logger.error(f"Couldn't set clientsubmission to {clientsubmission} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve proceduretype
        # If started_date not provided, try to default from associated clientsubmission.
        # If clientsubmission isn't set yet (e.g. when creating an empty instance to be
        # populated later by query_or_create), fall back to now to avoid AttributeError.
        if rsl_plate_number is not None:
            self.rsl_plate_number = rsl_plate_number
        if started_date is None:
            try:
                started_date = self.clientsubmission.submitted_date
            except Exception:
                started_date = datetime.now()
        try:
            self.started_date = started_date
        except Exception:
            logger.error(f"Couldn't set started_date to {started_date} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve completed_date
        if completed_date is not None:
            try:
                self.completed_date = completed_date
            except Exception:
                logger.error(f"Couldn't set completed_date to {completed_date} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve procedure
        if procedure is not None:
            try:
                self.procedure = procedure
            except Exception:
                logger.error(f"Couldn't set procedure to {procedure} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve sample
        if sample is not None:
            try:
                self.sample = sample
            except Exception:
                logger.error(f"Couldn't set sample to {sample} for {self.__class__.__qualname__} with name {self.name}")
        self._comment = [] if self._comment is None else self._comment

    @hybrid_property
    def rsl_plate_number(self) -> str:
        """
        Gets the plate number identifying this run.

        :return: self._rsl_plate_number or "Not Set"
        :rtype: str
        """
        return self._rsl_plate_number or "Not Set"
    
    @rsl_plate_number.setter
    def rsl_plate_number(self, value: dict | SourcedField | str):
        """
        Set the plate number this run will be identified by.
        Falls back to RSLNamer on failure.

        :param value: input object
        :type value: dict | SourcedField | str
        """
        from backend.validators.pydant import SourcedField
        if isinstance(value, dict):
            value = value.get("value", "NA")
        if isinstance(value, SourcedField):
            value = value.value
        if isinstance(value, str):
            self._rsl_plate_number = value
        else:
            from backend.validators import RSLNamer
            namer = RSLNamer(submission_type=self.clientsubmission.submissiontype)
            self._rsl_plate_number = namer.construct_new_plate_name(data=self.__dict__)

    @hybrid_property
    def procedure(self) -> List[Procedure]:
        """
        Get the procedures created from this run.

        :return: self._procedure
        :rtype: List[Procedure]
        """
        return self._procedure

    @procedure.setter
    def procedure(self, value: List[str | dict | PydProcedure | Procedure]):
        """
        Set the procedures created from this run by parsing input objects.

        :param value: List of input objects.
        :type value: List[str | dict | PydProcedure | Procedure]
        """
        from backend.validators.pydant import PydProcedure
        if value is None:
            value = []
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
                    logger.error(f"Unmatched value {item} for procedure")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, Procedure):
                list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._procedure")
        self._procedure = list_

    @hybrid_property
    def clientsubmission(self) -> ClientSubmission:
        """
        Gets the parent submission for this run.

        :return: self._clientsubmission
        :rtype: ClientSubmission
        """
        return self._clientsubmission

    @clientsubmission.setter
    def clientsubmission(self, value: str | dict | PydClientSubmission | ClientSubmission):
        """
        Set the parent submission for this run by parsing an input value.

        :param value: Input value.
        :type value: str | dict | PydClientSubmission | ClientSubmission
        """
        from backend.validators.pydant import PydClientSubmission
        match value:
            case str():
                output = ClientSubmission.query(name=value, limit=1)
            case dict():
                output = ClientSubmission.query_or_create(**value)
            case PydClientSubmission():
                output = value.to_sql(update=False)
            case ClientSubmission():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._clientsubmission")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ClientSubmission):
            self._clientsubmission = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._clientsubmission to {type(output)}")

    @hybrid_property
    def sample(self) -> List[Sample]:
        """
        Get the list of samples in this run.

        :return: self._sample
        :rtype: List[Sample]
        """
        return self._sample
    
    @sample.setter
    def sample(self, value: List[str | dict | PydSample | PydClientSubmissionSampleAssociation | Sample | RunSampleAssociation]):
        """
        Sets the samples for this run by parsing a list of input objects.

        :param value: List of input objects
        :type value: List[str | dict | PydSample | PydClientSubmissionSampleAssociation | Sample | RunSampleAssociation]:
        """
        from backend.validators.pydant import PydSample, PydClientSubmissionSampleAssociation
        value = iterable_enforcer(value, pass_dict=False)
        list_ = []
        for iii, item in enumerate(value):
            match item:
                case str():
                    try:
                        output = next((assoc for assoc in self.runsampleassociation if assoc.sample.sample_id==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.sample.name for eq in self.runsampleassociation]}")
                        output = RunSampleAssociation(sample=item, run=self, rank=iii)
                case dict():
                    sam = item.get("sample_id", None) or item.get("name", None) 
                    output = RunSampleAssociation(sample=sam, run=self, rank = item.get("rank", iii), **{k: v for k, v in item.items() if k not in ['sample_id', 'rank']})
                case PydSample():
                    output = RunSampleAssociation(sample=item, run=self, rank = getattr(item, "rank", iii), **{k: v for k, v in item.__dict__.items() if k not in ['sample_id', 'rank']})
                case PydClientSubmissionSampleAssociation():
                    output = RunSampleAssociation(run=self, rank = getattr(item, "rank", iii), **{k: v for k, v in item.__dict__.items() if k not in ['sample_id', 'rank']})
                case Sample():
                    output = RunSampleAssociation(sample=item, run=self, rank = getattr(item, "rank", iii))#, **{k: v for k, v in item.__dict__.items() if k not in ['name', 'rank']})
                case RunSampleAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._sample")
                    continue
            if isinstance(output, RunSampleAssociation):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {item} to {self.__class__.__qualname__}._sample")
        self.runsampleassociation = list_

    @hybrid_property
    def name(self) -> str:
        """
        Gets the rsl_plate_number. (This method exists for completeness)

        :return: self.rsl_plate_number
        :rtype: str
        """
        return self.rsl_plate_number

    @hybrid_property
    def started_date(self) -> datetime:
        """
        Gets the date this run was started.

        :return: Prefers mininum started day of included procedures. Fallback: submission submitted date or datetime.now
        :rtype: datetime
        """
        if self.procedure:
            try:
                value = min([proc.started_date for proc in self.procedure])
            except Exception as e:
                logger.error(e)
                try:
                    value = self.clientsubmission.submitted_date
                except AttributeError:
                    value = datetime.now()
        else:
            try:
                value = self.clientsubmission.submitted_date
            except AttributeError:
                value = datetime.now()
        return value

    @started_date.setter
    def started_date(self, value):
        """
        Sets the datet his run was started. (Depreciated)

        :param value: Input date
        :type value: dict | SourcedField | str | datetime | date | int | None
        """
        value = parse_optional_datetime(value)
        # if not value:
        #     value = self.clientsubmission.submitted_date
        self._started_date = value or self.clientsubmission.submitted_date

    @hybrid_property
    def completed_date(self) -> datetime | None:
        """
        Gets the date this run was completed.

        :return: self._completed_date if self._signed_by else None
        :rtype: datetime | None
        """
        # if not self._signed_by:
        #     return None
        # if self._completed_date:
        return self._completed_date if self._signed_by else None
        # dates = [proc.completed_date for proc in self.procedure if proc.completed_date]
        # return max(dates, default=None)

    @completed_date.setter
    def completed_date(self, value: dict | SourcedField | str | datetime | date | int | None):
        """
        Sets the completed date for this run. Parses input with validators.shared.parse_optional_datetime

        :param value: Input object
        :type value: dict | SourcedField | str | datetime | date | int | None
        """
        self._completed_date = parse_optional_datetime(value)

    @hybrid_property
    def comment(self) -> List[Dict[str, Any]]:
        """
        Gets any comments associated with this run.

        :return: [item for item in self._comment if all(key in ['user', 'text', 'time'] for key in item.keys())]
        :rtype: List[Dict[str, Any]]
        """
        if not self._comment:
            return []
        return [item for item in self._comment if all(key in ['user', 'text', 'time'] for key in item.keys())]
    
    @comment.setter
    def comment(self, value: dict | List[dict]):
        """
        Sets comments for this run. Parses input using validators.shared.vet_comment

        :param value: Input object.
        :type value: dict | List[dict]
        """
        self._comment = vet_comment(value, current=self._comment)

    @hybrid_property
    def run_cost(self) -> float:
        """
        Gets the stored cost of this run.

        :return: self._run_cost
        :rtype: float
        """
        return self._run_cost

    @hybrid_property
    def signed_by(self) -> str | None:
        """
        Gets the stored approver's username.

        :return: self._signed_by
        :rtype: str
        """
        return self._signed_by

    @signed_by.setter
    def signed_by(self, value: str):
        """
        Sets the approver's username.

        :param value: Input value.
        :type value: str
        """
        self._signed_by = value

    @property
    def approved(self) -> bool:
        """
        Gets whether or not this run has been approved.

        :return: True if self._signed_by else False
        :rtype: bool 
        """
        return True if self._signed_by else False

    # @classmethod
    # def get_submission_type(cls, submissiontype: str | SubmissionType | None = None) -> SubmissionType | None:
    #     """
    #     Gets the SubmissionType associated with this class

    #     :param submissiontype: Identity of the procedure type to retrieve. Defaults to None.
    #     :type submissiontype: str | SubmissionType | None
    #     :return: SubmissionType with name equal sub_type or this polymorphic identity if sub_type is None.
    #     :rtype: SubmissionType 
    #     """
    #     if isinstance(submissiontype, dict):
    #         try:
    #             submissiontype = submissiontype['value']
    #         except KeyError as e:
    #             logger.error(f"Couldn't extract value from {submissiontype}")
    #             raise e
    #     match submissiontype:
    #         case str():
    #             return SubmissionType.query(name=submissiontype)
    #         case SubmissionType():
    #             return submissiontype
    #         case _:
    #             return None

    @property
    def sample_count(self) -> int:
        """
        Gets the count of the list of samples in this run.

        :return: len(list(self.active_samples))
        :rtype: int 
        """
        return len(list(self.active_samples))

    @property
    def submission_samples(self) -> Generator[ClientSubmissionSampleAssociation, None, None]:
        """
        Gets the samples associated with this run's parent submission.

        :return: yield from self.clientsubmission.sample
        :rtype: Generator[ClientSubmissionSampleAssociation, None, None]
        """
        yield from self.clientsubmission.sample

    @property
    def active_samples(self) -> Generator[dict, None, None]:
        """
        Gets the samples that are in both this run and the clientsubmission.

        :return: Details dict for each sample in this run and the parent submission with 'active' set to true.
        :rtype: Generator[dict, None, None]
        """
        for sample in self.submission_samples:
            if sample.sample_id in [s.sample.sample_id for s in self.runsampleassociation]:
                # Create a shallow copy to safely modify the dictionary before yielding
                details = sample.details_dict.copy()
                details['active'] = True
                yield details

    @property
    def inactive_samples(self) -> Generator[dict, None, None]:
        """
        Gets the samples that are in the clientsubmission, but not in this run.

        :return: Details dict for each sample in this run and the parent submission with 'active' set to true.
        :rtype: Generator[dict, None, None]
        """
        a_s_names =  [s.get('sample_id', "") for s in self.active_samples]
        for sample in self.submission_samples:
            if sample.sample_id in a_s_names:
                continue
            details = sample.details_dict.copy()
            details['active'] = False
            yield details

    @property
    def details_dict(self) -> dict:
        """
        Gets dictionary of run attributes for display purposes.

        :return: super().details_dict with 'sample' and 'permission' set.
        :rtype: dict
        """
        output = super().details_dict
        output['sample'] = list(self.active_samples) + list(self.inactive_samples)
        output['permission'] = is_power_user()
        return output
    
    def details_dict_expand_fields(self, fields: List[str] | List[dict]) -> dict:
        """
        Gets details dict with expanded sqlalchemy objects.

        :param fields: List of fields to expand (possibly nested).
        :type fields: List[str] | List[dict]
        :return: super().details_dict_expand_fields(fields) with sample['active'] set.
        :rtype: dict
        """
        output = super().details_dict_expand_fields(fields)
        submission_samples = [sample.details_dict for sample in self.clientsubmission.sample]
        for sample in output['sample']:
            if not isinstance(sample, dict):
                continue
            sample['active'] = True if sample['sample_id'] in (item['sample_id'] for item in submission_samples) else False
        for sample in submission_samples:
            if sample['sample_id'] in (item['sample_id'] for item in output['sample']):
                continue
            else:
                sample['active'] = False
                output['sample'].append(sample)
        return output

    @classmethod
    def archive_submissions(cls, start_date: date | datetime | str | int | None = None,
                            end_date: date | datetime | str | int | None = None,
                            submissiontype: List[str] | None = None) -> DataFrame:
        """
        Get all runs from a submission type (or all if no submissiontype chose) as a Dataframe.

        :param start_date: beginning of query date range. Defaults to None.
        :type start_date: date | datetime | str | int | None
        :param end_date: end of query date range. Defaults to None.
        :type end_date: date | datetime | str | int | None
        :param submissiontype: SubmissionType of interest. Defaults to None.
        :type submissiontype: List[str] | None

        :return: Pandas dataframe of runs sorted by 'id'.
        """
        if submissiontype:
            if isinstance(submissiontype, str):
                submissiontype = [submissiontype]
            query_out = []
            for sub_type in submissiontype:
                subs = cls.query(page_size=0, start_date=start_date, end_date=end_date, submissiontype=sub_type)
                query_out.append(subs)
            query_out = list(chain.from_iterable(query_out))
        else:
            query_out = cls.query(page_size=0, start_date=start_date, end_date=end_date)
        records = []
        for sub in query_out:
            preparse = sub.details_dict
            output = {}
            output['id'] = sub.id
            output['clientlab'] = sub.clientsubmission.clientlab.name
            for k, v in preparse.items():
                match v:
                    case list() | dict() | GeneratorType():
                        continue
                    case _:
                        output[k] = v
            records.append(output)
        df = DataFrame.from_records(records)
        df.sort_values(by="id", inplace=True)
        df.set_index("id", inplace=True)
        return df

    # @property
    # def hitpicked(self) -> list:
    #     """
    #     Returns positve sample locations for plate

    #     Returns:
    #         list: list of hitpick dictionaries for each sample
    #     """
    #     output_list = [assoc.hitpicked for assoc in self.runsampleassociation]
    #     return output_list

    # @classmethod
    # def make_plate_map(cls, sample_list: List[dict], plate_rows: int = 8, plate_columns=12) -> str:
    #     """
    #     Constructs an html based plate map for procedure details.

    #     :param sample_list: List of procedure sample
    #     :type sample_list: List[dict]
    #     :param plate_rows: Number of rows in the plate. Defaults to 8.
    #     :type plate_rows: int
    #     plate_columns (int, optional): Number of columns in the plate. Defaults to 12.

    #     Returns:
    #         str: html output string.
    #     """
    #     rows = range(1, plate_rows + 1)
    #     columns = range(1, plate_columns + 1)
    #     # NOTE: An overly complicated list comprehension create a list of sample locations
    #     # NOTE: next will return a blank cell if no value found for row/column
    #     output_samples = [next((item for item in sample_list if item['row'] == row and item['column'] == column),
    #                            dict(name="", row=row, column=column, background_color="#ffffff"))
    #                       for row in rows
    #                       for column in columns]
    #     env = jinja_template_loading()
    #     template = env.get_template("support/plate_map.html")
    #     html = template.render(samples=output_samples, PLATE_ROWS=plate_rows, PLATE_COLUMNS=plate_columns)
    #     return html + "<br/>"

    def to_pydantic(self) -> PydRun:
        """
        Converts this instance into a PydRun

        :returns: converted object.
        :rtype: PydRun
        """
        from backend.validators import PydRun
        dict_ = self.details_dict
        new_dict = {}
        for key, value in dict_.items():
            missing = value in ['', 'None', None]
            match key:
                case "rsl_plate_number":
                    field_value = dict(value=self.rsl_plate_number, missing=missing)
                    new_dict['name'] = field_value
                case "id":
                    continue
                case "clientsubmission" | "client_submission":
                    field_value = self.clientsubmission.name
                case "procedure":
                    field_value = [item.details_dict for item in self.procedure]
                case "sample":
                    field_value = [assoc.sample.details_dict for assoc in self.runsampleassociation]
                case _:
                    try:
                        key = key.lower().replace(" ", "_")
                        if isclass(value):
                            field_value = dict(value=self.__getattribute__(key).name, missing=missing)
                        else:
                            field_value = dict(value=self.__getattribute__(key), missing=missing)
                    except AttributeError:
                        field_value = dict(value="NA", missing=True)
            new_dict[key] = field_value
        new_dict['filepath'] = Path(NamedTemporaryFile().name)
        new_dict['name'] = self.rsl_plate_number
        new_dict['sql_instance'] = self
        dict_.update(new_dict)
        try:
            assert dict_.get("clientsubmission", None) is not None
        except AssertionError as e:
            raise KeyError(f"Key 'clientsubmission' not found in {pformat(dict_)}")
        return PydRun(**dict_)
    
    def set_cost(self, include_repeat: bool = False):
        """
        Merges procedure costs into a cost for the whole run.

        :param include_repeat: are repeat procedures included in the cost?
        :type include_repeat: bool
        """
        # NOTE: Sum all non-repeat procedure costs.
        if include_repeat:
            cost = npsum([procedure.cost if procedure.cost else 0.00 for procedure in self.procedure])
        else:
            cost = npsum([procedure.cost if procedure.cost else 0.00 for procedure in self.procedure if not procedure.repeat])
        self._run_cost = cost

    def save(self, original: bool = True):
        """
        Adds this instance to database and commits.

        :param original: Is this the first save. Defaults to True.
        :type original: bool
        """
        if original:
            self.uploaded_by = getuser()
        self.set_cost()
        return super().save()

    @classmethod
    @setup_lookup
    def query(cls,
              submissiontype_name: str | None = None,
              id: int | str | None = None,
              name: str | None = None,
              start_date: date | datetime | str | int | None = None,
              end_date: date | datetime | str | int | None = None,
              chronologic: bool = False,
              limit: int = 0,
              page: int = 1,
              page_size: None | int = 250,
              **kwargs
              ):
        """
        Lookup procedure based on a number of parameters. Overrides parent.

        :param submissiontype_name: Submission type of interest. Defaults to None.
        :type submissiontype_name: str | None
        :param id: Submission id in the database (limits results to 1). Defaults to None.
        :type id: int | str | None
        :param name: Submission name in the database (limits results to 1). Defaults to None.
        :type name: str | None
        :param start_date: Beginning date to search by. Defaults to None.
        :type start_date: date | datetime | str | int | None
        :param end_date: Ending date to search by. Defaults to None.
        :type end_date: date | datetime | str | int | None
        :param chronologic: Return results in chronologic order. Defaults to False.
        :type chronologic: bool
        :param limit: Maximum number of results to return. Defaults to 0.
        :type limit: int
        :param page: Page number to retrieve when using pagination. Defaults to 1.
        :type page: int
        :param page_size: Number of results per page. Defaults to 250.
        :type page_size: int | None
        :returns: Run(s) of interest.
        :rtype: Run | List[Run]
        """
        query: Query = cls.__database_session__.query(cls)
        if start_date is not None and end_date is None:
            logger.warning(f"Start date with no end date, using today.")
            end_date = date.today()
        if end_date is not None and start_date is None:
            # NOTE: this query returns a tuple of (object, datetime), need to get only datetime.
            start_date = cls.__database_session__.query(cls, func.min(cls.submitted_date)).first()[1]
            logger.warning(f"End date with no start date, using first procedure date: {start_date}")
        if start_date is not None:
            start_date = cls.rectify_query_date(start_date, timefill=TimeFill.MIN)
            end_date = cls.rectify_query_date(end_date, timefill=TimeFill.MAX)
            query = query.join(ClientSubmission).filter(ClientSubmission.submitted_date.between(start_date, end_date))
        # NOTE: by rsl number (returns only a single value)
        match name:
            case str():
                query = query.filter(cls.name == name)
                limit = 1
            case _:
                pass
        match submissiontype_name:
            case str():
                if not start_date:
                    query = query.join(ClientSubmission)
                query = query.filter(ClientSubmission.submissiontype_name == submissiontype_name)
            case _:
                pass
        # NOTE: by id (returns only a single value)
        match id:
            case int():
                query = query.filter(cls.id == id)
                limit = 1
            case str():
                query = query.filter(cls.id == int(id))
                limit = 1
            case _:
                pass
        # NOTE: Split query results into pages of size {page_size}
        # Do not apply .limit()/.offset() directly on the Query here because
        # execute_query will add filters afterwards. Applying limit/offset
        # before filters causes SQLAlchemy to raise when filters are added.
        if page_size and page_size > 0:
            offset = (page - 1) * page_size if page is not None else None
            # If no explicit limit was set, limit the results to the page size
            if limit == 0:
                limit = page_size
        else:
            offset = None
        if chronologic:
            query = query.order_by(cls.started_date.desc)
        return cls.execute_query(query=query, limit=limit, offset=offset, **kwargs)

    # NOTE: Custom context events for the ui

    @property
    def custom_context_events(self) -> dict:
        """
        Creates dictionary of str:function to be passed to context menu

        Name include: ["Add Procedure", "Edit", "Export", "Add Comment", "Show Details", "Delete"]

        :return: {item: self.__getattribute__(item.lower().replace(" ", "_")) for item in names}
        :rtype: dict
        """
        names = ["Add Procedure", "Edit", "Export", "Add Comment", "Show Details", "Delete"]
        output = {item: self.__getattribute__(item.lower().replace(" ", "_")) for item in names}
        return output

    def add_procedure(self, obj: SubmissionsTree, proceduretype_name: str):
        """
        Create a new procedure for this run.

        :param obj: Widget to be used for parent dependent functions.
        :type obj: SubmissionsTree
        """
        from frontend.widgets.procedure_creation import ProcedureCreation
        procedure_type: ProcedureType = next((proceduretype for proceduretype in self.allowed_procedures if proceduretype.name == proceduretype_name))
        procedure = procedure_type.construct_dummy_procedure(run=self)
        assert len(procedure.sample) > 0
        assert procedure.run is not None
        # As of here, samples are fine.
        # Passed check
        dlg = ProcedureCreation(parent=obj, procedure=procedure)
        if dlg.exec():
            if obj:
                sql = dlg.return_sql(new=True)
                try:
                    assert len(sql.sample) == len(dlg.procedure.sample)
                    sql.update_last_useds()
                    sql.save()
                except AssertionError as e:
                    raise ValueError(f"SQL object sample length\n{pformat(sql.sample)} did not equal input sample length\n{dlg.procedure.sample}")
            else:
                pprint(dlg.debug_output())
        # Refresh only the parent submission's row instead of the entire tree.
        # Here self is the Run, so the changed submission is self.clientsubmission.
        if hasattr(obj, "upsert_submission"):
            obj.upsert_submission(self.clientsubmission)
        else:
            obj.set_data()

    @check_authorization
    def delete(self, obj=None):
        """
        Performs backup and deletes this instance from database.

        :param obj: Parent widget. Defaults to None.
        :type obj: Any
        :raises: SQLIntegrityError or SQLOperationalError if problem with commit.
        """
        from frontend.widgets.pop_ups import QuestionAsker
        msg = QuestionAsker(title="Delete?", message=f"Are you sure you want to delete {self.rsl_plate_number}?\n")
        if msg.exec():
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

    def edit(self, obj):
        """
        Return procedure to form widget for updating

        :param obj: Parent widget
        :type obj: Any
        """
        logger.info("Edit!")
        from frontend.widgets.sample_checker import SampleChecker
        samples = [sample.to_pydantic() for sample in self.sample]
        checker = SampleChecker(parent=obj, title="Edit Run", samples=samples, run=self.to_pydantic())
        if checker.exec():
            pass

    def add_comment(self, obj):
        """
        Add a comment to this procedure.

        This method is a placeholder for comment UI integration.

        :param obj: Parent object for the comment action.
        :type obj: Any
        """
        logger.info("Add Comment!")
        from frontend.widgets import SubmissionComment
        dlg = SubmissionComment(parent=obj, submission=self)
        if dlg.exec():
            comment = dlg.parse_form()
            self.comment = comment
            self.save(original=False)

    def export(self, obj, output_filepath: str | Path | None = None):
        """
        Save this run as an excel workbook.

        :param obj: Parent object for the export action.
        :type obj: Any
        :param output_filepath: Path in the folder structure to save the workbook to.
        :type output_filepath: str | Path | None
        """
        from backend import managers
        from frontend.widgets.functions import select_save_file
        Manager = getattr(managers, f"Default{self.__class__.__name__}Manager")
        manager = Manager(parent=obj, input_object=self.to_pydantic())
        default_name = manager.pyd.export_filename
        output_filepath = select_save_file(obj=obj, default_name=default_name, file_extension="xlsx")
        workbook = manager.write()
        try:
            workbook.remove_sheet("Sheet")
        except ValueError:
            pass
        workbook.save(filename=output_filepath)

    @property
    def filename(self) -> str:
        """
        Gets constructed filename (without path or suffix). Renders jinja2 template.

        :return: self.clientsubmission.submissiontype.template.render(**self.details_dict_expand_fields([{'clientsubmission':['clientlab']}]))
        :rtype: dict 
        """
        dict_ = self.details_dict_expand_fields([{'clientsubmission':['clientlab']}])
        return self.clientsubmission.submissiontype.template.render(**dict_)

    # def backup(self, obj=None, fname: Path | None = None):
    #     """
    #     Exports xlsx info files for this instance.

    #     Args:
    #         obj (_type_, optional): _description_. Defaults to None.
    #         fname (Path | None, optional): Filename of xlsx file. Defaults to None.
    #         full_backup (bool, optional): Whether or not to make yaml file. Defaults to False.
    #     """
    #     pyd = self.to_pydantic()
    #     if fname is None:
    #         from frontend.widgets.functions import select_save_file
    #         fname = select_save_file(default_name=pyd.export_filename, filetype="xlsx", obj=obj)
    #     if fname.name == "":
    #         return
    #     writer = pyd.to_writer()
    #     writer.xl.save(filename=fname.with_suffix(".xlsx"))

    @property
    def turnaround_time(self) -> int:
        """
        Gets the amount of time this run took to process.

        :return: self.calculate_turnaround(start_date=self.started_date.date(), end_date=self.completed_date.date())
        :rtype: int
        """
        try:
            completed = self.completed_date.date()
        except AttributeError:
            completed = None
        return self.calculate_turnaround(start_date=self.started_date.date(), end_date=completed)

    @classmethod
    def calculate_turnaround(cls, start_date: date | None = None, end_date: date | None = None) -> int | None:
        """
        Calculates number of business days between data submitted and date completed.

        :param start_date: Date submitted. defaults to None.
        :type start_date: date | None
        :param end_date: Date completed. defaults to None.
        :type end_date: date | None
        :return: Number of business days.
        :rtype: int | None
        """
        if not end_date:
            return None
        try:
            delta = busday_count(start_date, end_date, holidays=create_holidays_for_year(start_date.year)) + 1
        except ValueError:
            return None
        return int(delta)

    @property
    def allowed_procedures(self) -> List[ProcedureType]:
        """
        Gets the procedure types allowed in this run's parent submission type.

        :return: self.clientsubmission.submissiontype.proceduretype
        :rtype: List[ProcedureType] 
        """
        return self.clientsubmission.submissiontype.proceduretype

    def get_submission_rank_of_sample(self, sample: Sample | str) -> int:
        """
        Gets the rank in the client submission of a given sample.

        :param sample: Sample of interest.
        :type sample: Sample | str
        :return: Association.submission_rank in parent clientsubmission.clientsubmissionsampleassociation
        :rtype: int
        """
        if isinstance(sample, str):
            sample = next((sample for sample in self.sample if sample.sample_id==sample), None)
        clientsubmissionsampleassoc = next((assoc for assoc in self.clientsubmission.clientsubmissionsampleassociation
                                            if assoc.sample == sample), None)
        if clientsubmissionsampleassoc:
            return clientsubmissionsampleassoc.submission_rank
        else:
            return 0

    # def constuct_sample_dicts_for_proceduretype(self, proceduretype: ProcedureType, procedure: Procedure) -> List[PydProcedureSampleAssociation]:
    #     from backend.validators import PydProcedureSampleAssociation, PydSample
    #     plate_dict = proceduretype.ranked_plate
    #     ranked_samples = []
    #     unranked_samples = []
    #     with self.__database_session__.no_autoflush:
    #         samples = [assoc.to_PydProcedureSampleAssociation(procedure=procedure) for assoc in self.runsampleassociation]
    #     for sample in samples:
    #         submission_rank = self.get_submission_rank_of_sample(sample=sample)
    #         if submission_rank != 0:
    #             try:
    #                 sample.row, sample.column = plate_dict[submission_rank]
    #             except KeyError as e:
    #                 logger.error(pformat(plate_dict))
    #                 raise e
    #             ranked_samples.append(sample)
    #         else:
    #             unranked_samples.append(sample)
    #     possible_ranks = (item for item in list(plate_dict.keys()) if
    #                       item not in [sample.procedure_rank for sample in ranked_samples])
    #     for sample in unranked_samples:
    #         try:
    #             submission_rank = next(possible_ranks)
    #         except StopIteration:
    #             continue
    #         sample.row, sample.column = plate_dict[submission_rank]
    #         ranked_samples.append(sample)
    #     padded_list = []
    #     for iii in range(1, proceduretype.total_wells + 1):
    #         row, column = proceduretype.ranked_plate[iii]
    #         try:
    #             sample = next((item for item in ranked_samples if item.procedure_rank == iii))
    #         except StopIteration:
    #             sample = PydProcedureSampleAssociation(sample=PydSample(sample_id=""), procedure=procedure, row=row, column=column, procedure_rank=iii)

    #         padded_list.append(sample)
    #     return list(sorted(padded_list, key=attrgetter('procedure_rank')))

    @classmethod
    def construct_dummy_run(cls, clientsubmission: ClientSubmission) -> Run:
        """
        Constructs a dummy run with samples from the given client submission.

        :param clientsubmission: The client submission to base the run on. 
        :type: clientsubmission: ClientSubmission
        :return: A dummy Run instance.
        :rtype: Run
        """
        from backend.validators import PydRun, RSLNamer
        data = clientsubmission.details_dict
        rsl_plate_number = RSLNamer.construct_new_plate_name(data=data)
        dummy_run = PydRun(sample=[], clientsubmission=clientsubmission.to_pydantic(), rsl_plate_number=rsl_plate_number)
        for sample in clientsubmission.sample:
            dummy_run.sample.append(sample.to_pydantic())
        return dummy_run

# NOTE: Sample Classes

class Sample(BaseClass, LogMixin):
    """
    Represents a sample submitted for analysis.

    :ivar id: Primary key identifier for the sample.
    :vartype id: int
    :ivar sample_id: Identifier assigned by the submitter.
    :vartype sample_id: str
    :ivar is_control: Control state for the sample. 1 = positive, -1 = negative, 0 = normal.
    :vartype is_control: int
    :ivar comment: User notes associated with the sample.
    :vartype comment: list[dict] | None
    :ivar clientsubmission: Client submissions linked to the sample.
    :vartype clientsubmission: list[ClientSubmissionSampleAssociation]
    :ivar run: Runs associated with the sample.
    :vartype run: list[RunSampleAssociation]
    :ivar procedure: Procedures associated with the sample.
    :vartype procedure: list[ProcedureSampleAssociation]
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    sample_id = Column(String(64), nullable=False, unique=True)  #: identification from submitter
    _is_control = Column(INTEGER, default=0) #: 1 = positive, -1 = negative, 0 = not a control
    _comment = Column(MutableList.as_mutable(JSON))  #: user notes

    sampleclientsubmissionassociation = relationship(
        "ClientSubmissionSampleAssociation",
        back_populates="_sample",
        cascade="all, delete-orphan",
    )  #: associated procedure

    _clientsubmission = association_proxy("sampleclientsubmissionassociation",
                                         "_clientsubmission")  #: proxy of associated procedure

    samplerunassociation = relationship(
        "RunSampleAssociation",
        back_populates="_sample",
        cascade="all, delete-orphan",
    )  #: associated procedure

    _run = association_proxy("samplerunassociation", "_run")  #: proxy of associated procedure

    sampleprocedureassociation = relationship(
        "ProcedureSampleAssociation",
        back_populates="_sample",
        cascade="all, delete-orphan",
    )

    _procedure = association_proxy("sampleprocedureassociation", "_procedure")

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        clientsubmission = kwargs.pop('clientsubmission', None)
        run = kwargs.pop('run', None)
        procedure = kwargs.pop('procedure', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve clientsubmission
        if clientsubmission is not None:
            try:
                self.clientsubmission = clientsubmission
            except Exception:
                logger.error(f"Couldn't set clientsubmission to {clientsubmission} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve run
        if run is not None:
            try:
                self.run = run
            except Exception:
                logger.error(f"Couldn't set run to {run} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve procedure
        if procedure is not None:
            try:
                self.procedure = procedure
            except Exception:
                logger.error(f"Couldn't set procedure to {procedure} for {self.__class__.__qualname__} with name {self.name}")
        self._comment = [] if self._comment is None else self._comment

    @hybrid_property
    def clientsubmission(self):
        """
        Gets the client submissions associated with this sample.

        :return: self._clientsubmission
        :rtype: List[ClientSubmissionSampleAssociation]
        """
        return self._clientsubmission
    
    @clientsubmission.setter
    def clientsubmission(self, value: List[str | dict | ClientSubmissionSampleAssociation | ClientSubmission]):
        """
        Sets the the client submissions associated with this sample by parsing a list of input objects.

        :param value: List of client submission identifiers or objects.
        :type value: List[str | dict | ClientSubmissionSampleAssociation | ClientSubmission]
        """
        value = iterable_enforcer(value)
        list_ = []
        for item in value:
            match item:
                case str():
                    try:
                        output = next((assoc for assoc in self.sampleclientsubmissionassociation if assoc.clientsubmission.name==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.clientsubmission.name for eq in self.sampleclientsubmissionassociation]}")
                        output = ClientSubmissionSampleAssociation(clientsubmission=item, sample=self)
                case dict():
                    cl = item.get("name", None) or item.get("submitter_plate_id", None)
                    output = ClientSubmissionSampleAssociation(clientsubmission=cl, sample=self, **{k: v for k, v in item.items() if k != 'name'})
                case ClientSubmissionSampleAssociation():
                    output = item
                case ClientSubmission():
                    output = ClientSubmissionSampleAssociation(clientsubmission=item, sample=self)
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._clientsubmission")
                    continue
            if isinstance(output, ClientSubmissionSampleAssociation):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {item} to {self.__class__.__qualname__}._clientsubmission")
        self.sampleclientsubmissionassociation  = list_

    @hybrid_property
    def run(self):
        """
        Gets the runs associated with this sample.

        :return: self._run
        :rtype: List[RunSampleAssociation]
        """
        return self._run
    
    @run.setter
    def run(self, value: List[str | dict | RunSampleAssociation | Run]):
        """
        Set the runs associated with this sample by parsing a list of input objects.

        :param value: List of run identifiers or objects.
        :type value: List[str | dict | RunSampleAssociation | Run]
        """
        from backend.db.models import Run
        value = iterable_enforcer(value)
        list_ = []
        for item in value:
            match item:
                case str():
                    try:
                        output = next((assoc for assoc in self.samplerunassociation if assoc.run.name==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.run.name for eq in self.samplerunassociation]}")
                        output = RunSampleAssociation(run=item, sample=self)
                case dict():
                    r = item.get("name", None) or item.get("rsl_plate_number", None)
                    output = RunSampleAssociation(run=r, sample=self, **{k: v for k, v in item.items() if k not in ["rsl_plate_number", 'name']})
                case RunSampleAssociation():
                    output = item
                case Run():
                    output = RunSampleAssociation(run=item, sample=self)
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._sample")
                    return
            if isinstance(output, RunSampleAssociation):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {item} to {self.__class__.__qualname__}._run")
        self.samplerunassociation = list_

    @hybrid_property
    def procedure(self):
        """
        Gets the procedures associated with this sample.

        :return: self._procedure
        :rtype: List[Procedure]
        """
        return self._procedure
    
    @procedure.setter
    def procedure(self, value):
        value = iterable_enforcer(value)
        list_ = []
        for item in value:
            match item:
                case str():
                    try:
                        output = next((assoc for assoc in self.sampleprocedureassociation if assoc.procedure.name==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.procedure.name for eq in self.sampleprocedureassociation]}")
                        output = ProcedureSampleAssociation(procedure=item, sample=self)
                case dict():
                    output = ProcedureSampleAssociation(procedure=item['name'], sample=self, **{k: v for k, v in item.items() if k != 'name'})
                case ProcedureSampleAssociation():
                    output = item
                case Procedure():
                    output = ProcedureSampleAssociation(procedure=item, sample=self)
                case _:
                    logger.error(f"Unmatched value {item} for sample")
                    return
            if isinstance(output, ProcedureSampleAssociation):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {output} to {self.__class__.__qualname__}._sample")
        self.sampleprocedureassociation = list_

    @hybrid_property
    def is_control(self) -> int:
        """
        Gets whether this sample is a control sample. 1 = positive, -1 = negative, 0 = normal.

        :return: self._is_control
        :rtype: int
        """
        return self._is_control

    @staticmethod
    def translate_control(value, to_str:bool = False) -> int | str:
        """
        Translates the control value to either an integer or string representation.

        :param value: The control value to translate.
        :param to_str: Whether to translate to a string representation.
        :return: The translated value. If to_str is True, returns a string; otherwise, returns an integer.
        :rtype: int | str
        """
        if to_str:
            if value < 0:
                return "Negative"
            elif value > 0:
                return "Positive"
            else:
                return "Sample"
        else:
            match value:
                case int():
                    output = value
                case bool():
                    output = int(value)
                case float():
                    output = int(value)
                case str():
                    if any([value.lower().__contains__(s) for s in ["negative", "neg"]]):
                        output = -1
                    elif any([value.lower().__contains__(s) for s in ["positive", "pos"]]):
                        output = 1
                    elif any([value.lower().__contains__(s) for s in ["sample", "sam"]]):
                        output = 0
                    else:
                        raise ValueError(f"Unmatched str value for {value}")
                case _:
                    raise TypeError(f"Unsupported type: {type(value)} for {self.sample_id}._is_control")
            if output > 1:
                output = 1
            if output < -1:
                output = -1
            return output

    @is_control.setter
    def is_control(self, value: int | Literal["Positive", "Negative", "Sample"] | bool):
        """
        Set whether or not this sample is a control sample. Accepts 1, -1, 0, True, False, "Positive", "Negative", "Sample".

        :param value: The control value to set.
        :type value: int | Literal["Positive", "Negative", "Sample"] | bool
        """
        # Can't use booleanize here because we want to allow for 3 states: positive, negative, and sample.
        self._is_control = self.translate_control(value)
  
    @hybrid_property
    def name(self) -> str:
        """
        Gets the name of the sample, which is the same as the sample_id.

        :return: self.sample_id
        :rtype: str
        """
        return self.sample_id
    
    @hybrid_property
    def comment(self) -> List[dict]:
        """
        Gets the comments associated with the sample.

        :return: [item for item in self._comment if all(key in ['user', 'text', 'time'] for key in item.keys())]
        :rtype: List[dict]
        """
        if not self._comment:
            return []
        return [item for item in self._comment if all(key in ['user', 'text', 'time'] for key in item.keys())]
    
    @comment.setter
    def comment(self, value):
        """
        Sets the comments associated with the sample after vetting the input value. Uses validators.shared.vet_comment

        :param value: The comment value to set.
        :type value: dict | List[dict]
        """
        self._comment = vet_comment(value, current=self._comment)

    def abbreviation_name(self, obj: ClientSubmission | Run | None=None):
        """
        Gets the abbreviated name of the sample, which is based on the client submission abbreviation.

        :param obj: Optional object to determine the abbreviation. Can be a ClientSubmission or Run.
        :type obj: ClientSubmission | Run | None
        :return: Abbreviated name of the sample.
        :rtype: str
        """
        if len(self.clientsubmission) == 1:
            out = f"RSL-{self.clientsubmission[0].abbreviation}-" 
        else:
            match obj:
                case ClientSubmission():
                    out = f"RSL-{obj.abbreviation}-"
                case Run():
                    out = f"RSL-{obj.clientsubmission.abbreviation}-"
                case _:
                    logger.warning(f"Haven't figured out how to get a single client submission for {self.__class__.__qualname__} with name {self.name}.")
                    out = f"RSL-CC-"
        return replace_or_prepend_prefix(self.sample_id, old_prefix=r"^RSL-[A-Z]+-", new_prefix=out)

    @classmethod
    @declared_attr
    def searchables(cls) -> List[dict]:
        """
        Gets the list of searchable fields for the Sample class.

        :return: List of dictionaries containing label and field for searchable fields.
        :rtype: List[dict]
        """
        return [dict(label="Submitter ID", field="sample_id")]

    @property
    def details_dict(self) -> dict:
        """
        Gets a dictionary of the sample's details.

        :return: super().details_dict with 'sample_id' added.
        :rtype: dict
        """
        output = super().details_dict
        output['sample_id'] = self.sample_id
        return output

    def to_pydantic(self) -> PydSample:
        """
        Converts the Sample instance to a Pydantic model representation.

        :return: PydSample representation of the Sample instance.
        :rtype: PydSample
        """
        if hasattr(self, '_misc_info') and isinstance(self._misc_info, dict) and 'sample' in self._misc_info:
            try:
                self._misc_info['sample'] = self.sanitize_obj_for_json(self._misc_info['sample'])
            except TypeError:
                del self._misc_info['sample']
        output: PydSample = super().to_pydantic()
        output.results = [result.to_pydantic() for result in flatten_list([assoc.results for assoc in self.sampleprocedureassociation])]
        return output

    @classmethod
    @setup_lookup
    def query(cls,
              sample_id: str | None = None,
              limit: int = 0,
              **kwargs
              ):
        """
        Lookup sample in the database by a number of parameters.

        :param sample_id: Name of the sample (limits results to 1). Defaults to None.
        :type sample_id: str | None
        :param limit: Maximum number of results to return (0 = all). Defaults to 0.
        :type limit: int
        :param **kwargs: Additional keyword arguments for the query.
        :type **kwargs: Any
        :returns: Sample(s) of interest.
        :rtype: Sample | List[Sample]
        """
        query = cls.__database_session__.query(cls)
        match sample_id:
            case str():
                query = query.filter(cls.sample_id.endswith(sample_id))
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit, **kwargs)

    def delete(self):
        raise AttributeError(f"Delete not implemented for {self.__class__}")

    @classmethod
    def samples_to_df(cls, sample_list: List[Sample], **kwargs) -> DataFrame | None:
        """
        Runs a fuzzy search and converts into a dataframe.

        :param sample_list: List of sample to be parsed. Defaults to None.
        :type sample_list: List[Sample]
        :param **kwargs: Additional keyword arguments for the conversion.
        :type **kwargs: Any
        :return: DataFrame: Dataframe all sample
        :rtype: DataFrame | None
        """
        try:
            samples = [sample.details_dict for sample in sample_list]
        except TypeError as e:
            logger.exception(f"Couldn't find any sample with data: {kwargs}\nDue to {e}")
            return None
        df = DataFrame.from_records(samples)
        # NOTE: Exclude sub information
        exclude = ['concentration', 'organism', 'colour', 'tooltip', 'comments', 'sample', 'reagents',
                   'equipment', 'gel_info', 'gel_image', 'dna_core_submission_number', 'gel_controls',
                   'excluded', "sampleclientsubmissionassociation", "samplerunassociation", "sampleprocedureassociation",
                   "clientsubmission", "run", "procedure"]
        df = df.loc[:, ~df.columns.isin(exclude)]
        return df

    def edit_from_search(self, obj: SearchResults, **kwargs):
        """
        Function called form search. "Edit" is dependent on function as this one just shows details.

        :param obj: Parent widget for the edit action.
        :type obj: SearchResults
        """
        self.show_details(obj)

    def save(self) -> Report | NoneType:
        """
        Persist this sample to the database. If the sample_id is None or a blank/NA value, the save operation is skipped.
        """
        if self.sample_id is None:
            return
        if self.sample_id.lower() in ["", "blank", "na", "n/a", "n\\a", "none"]:
            return
        super().save()                                    

    def add_comment(self, obj):
        """
        Add a comment to this procedure.

        This method is a placeholder for comment UI integration.

        :param obj: Parent object for the comment action.
        :type obj: Any
        :return: None
        """
        logger.info("Add Comment!")
        from frontend.widgets import SubmissionComment
        dlg = SubmissionComment(parent=obj, submission=self)
        if dlg.exec():
            comment = dlg.parse_form()
            self.comment = comment
            self.save(original=False)

# NOTE: Submission to Sample Associations

class ClientSubmissionSampleAssociation(BaseClass):
    """
    Links a sample to a client submission and tracks its position within that submission.

    This association records which sample belongs to which submitted batch and the
    relative order of that sample in the submission list.

    :ivar clientsubmission_id: Foreign key for the parent client submission.
    :vartype clientsubmission_id: int
    :ivar sample_id: Foreign key for the associated sample.
    :vartype sample_id: int
    :ivar submission_rank: Position of the sample within the submission.
    :vartype submission_rank: int
    :ivar comment: User notes associated with this sample-submission link.
    :vartype comment: list[dict] | None
    :ivar clientsubmission: Parent client submission linked to this association.
    :vartype clientsubmission: ClientSubmission
    :ivar sample: Sample associated with this client submission.
    :vartype sample: Sample
    """
    
    clientsubmission_id = Column(INTEGER, ForeignKey("_clientsubmission.id", ondelete="CASCADE"), primary_key=True)  #: id of associated client submission
    sample_id = Column(INTEGER, ForeignKey("_sample.id", ondelete="RESTRICT"), primary_key=True)  #: id of associated sample
    submission_rank = Column(INTEGER, primary_key=True, default=0)  #: Location in sample list
    _comment = Column(MutableList.as_mutable(JSON))  #: user notes
    # NOTE: reference to the Submission object
    _clientsubmission = relationship("ClientSubmission",
                                    back_populates="clientsubmissionsampleassociation")  #: associated procedure

    # NOTE: reference to the Sample object
    _sample = relationship("Sample", back_populates="sampleclientsubmissionassociation")  #: associated sample

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        clientsubmission = kwargs.pop('clientsubmission', None)
        sample = kwargs.pop('sample', None)
        submission_rank = kwargs.pop("rank", 0)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if clientsubmission is not None:
            try:
                self.clientsubmission = clientsubmission
            except Exception:
                logger.error(f"Couldn't set clientsubmission to {clientsubmission} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve reagentrole
        if sample is not None:
            try:
                self.sample = sample
            except Exception:
                logger.error(f"Couldn't set sample to {sample} for {self.__class__.__qualname__} with name {self.name}")
        self.submission_rank = submission_rank
        self._comment = [] if self._comment is None else self._comment
    
    @hybrid_property
    def name(self):
        """
        Gets the calculated name of the association, which combines the client submission name, sample name, and submission rank.

        :return: {self.clientsubmission.name}->{self.sample.name} (rank={self.submission_rank})
        :rtype: str
        """
        try:
            clientsubmission = self.clientsubmission.name
        except AttributeError:
            clientsubmission = "Unassigned ClientSubmission"
        try:
            sample = self.sample.name
        except AttributeError:
            sample = "Unassigned Sample"
        try:
            submission_rank = self.submission_rank
        except AttributeError:
            submission_rank = "No Submission Rank"
        return f"{clientsubmission}->{sample} (rank={submission_rank})"
    
    @name.expression
    def name(cls):
        """
        Gets the calculated name of the association as a SQL expression, which combines the client submission name, 
        sample name, and submission rank.

        :return: SQL expression for the name of the association.
        :rtype: sqlalchemy.sql.expression.Label
        """
        clientsubmission_subquery = (
            select(ClientSubmission.name)
            .where(ClientSubmission.id==cls.clientsubmission)
            .correlate(cls)
            .scalar_subquery()
        )
        sample_subquery = (
            select(Sample.name)
            .where(Sample.id==cls.sample_id)
            .correlate(cls)
            .scalar_subquery()
        )
        # NOTE: Can't use f strings for this.
        return clientsubmission_subquery + "->" + sample_subquery + " (rank=" + cast(cls.submission_rank, String) + ")"

    @hybrid_property
    def sample(self):
        """
        Gets the sample associated with this client submission.

        :return: self._sample
        :rtype: Sample
        """
        return self._sample

    @sample.setter
    def sample(self, value: str | dict | Sample | PydSample):
        """
        Sets the sample associated with this relationship by parsing an input object.

        :param value: The sample identifier or object to set.
        :type value: str | dict | Sample | PydSample
        """
        from backend.validators.pydant import PydSample
        match value:
            case str():
                output = Sample.query(name=value, limit=1)
            case dict():
                output = Sample.query_or_create(**value)
            case PydSample():
                output = value.to_sql(update=False)
            case Sample():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for sample")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, Sample):
            if not hasattr(output, "id"):
                output.save()
            self._sample = output
        else:
            logger.error(f"{self.__class__.__qualname__} Could not set _sample to {type(output)}: {output}")
  
    @hybrid_property
    def clientsubmission(self):
        """
        Gets the client submission associated with this client submission.

        :return: self._clientsubmssion
        :rtype: ClientSubmission
        """
        return self._clientsubmission

    @clientsubmission.setter
    def clientsubmission(self, value):
        from backend.validators.pydant import PydClientSubmission
        match value:
            case str():
                output = ClientSubmission.query(name=value, limit=1)
            case dict():
                output = ClientSubmission.query_or_create(**value)
            case PydClientSubmission():
                output = value.to_sql(update=False)
            case ClientSubmission():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for clientsubmission")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ClientSubmission):
            self._clientsubmission = output
        else:
            logger.error(f"Could not set _clientsubmission to {type(output)}")

    @hybrid_property
    def comment(self) -> List[dict]:
        """
        Gets the comments associated with this sample-submission link.

        :return: [item for item in self._comment if all(key in ['user', 'text', 'time'] for key in item.keys())]
        :rtype: List[dict]
        """
        if not self._comment:
            return []
        return [item for item in self._comment if all(key in ['user', 'text', 'time'] for key in item.keys())]
    
    @comment.setter
    def comment(self, value: dict | List[dict]):
        """
        Sets the comments associated with this sample-submission link.
        Uses validators.shared.vet_comment to validate the input value.

        :param value: The comments to set.
        :type value: dict | List[dict]
        """
        self._comment = vet_comment(value, current=self._comment)

    @property
    def details_dict(self) -> dict:
        """
        Gets a dictionary of the association's details, including relevant information from the associated sample and client submission.

        :return: Dictionary containing details of the association.
        :rtype: dict
        """
        output = super().details_dict
        # NOTE: Figure out how to merge the misc_info if doing .update instead.
        relevant = {k: v for k, v in output.items() if k not in ['sample']}
        output = self.sample.details_dict
        misc = {k:v for k, v in output.get('misc_info', {}).items() if k not in ['sample']}
        output.update(relevant)
        output['misc_info'] = misc
        output['rank'] = self.submission_rank
        output['comment'] = self.comment
        output['sample'] = self.sample.sample_id
        return output

    @hybrid_property
    def abbreviation_name(self) -> str:
        """
        Gets the abbreviated name of the sample associated with this client submission, which is based on the client submission abbreviation.

        :return: Abbreviated name of the sample.
        :rtype: str
        """
        return replace_or_prepend_prefix(self.sample.sample_id, old_prefix=r"^RSL-[A-Z]+-", new_prefix=f"RSL-{self.clientsubmission.abbreviation}-")
        # return f"RSL-{self.clientsubmission.abbreviation}-{self.sample.sample_id}"

    @classmethod
    @setup_lookup
    def query(cls,
              clientsubmission: ClientSubmission | str | None = None,
              exclude_submission_type: str | None = None,
              sample: Sample | str | None = None,
              row: int = 0,
              column: int = 0,
              limit: int = 0,
              chronologic: bool = False,
              reverse: bool = False,
              **kwargs
              ):
        """
        Lookup sample in the database by a number of parameters.

        :param clientsubmission: Client submission to filter by. Can be a ClientSubmission object or a string identifier. Defaults to None.
        :type clientsubmission: ClientSubmission | str | None
        :param exclude_submission_type: Submission type to exclude from the results. Defaults to None.
        :type exclude_submission_type: str | None
        :param sample: Sample to filter by. Can be a Sample object or a string identifier. Defaults to None.
        :type sample: Sample | str | None
        :param row: Row number to filter by. Defaults to 0 (no filtering).
        :type row: int
        :param column: Column number to filter by. Defaults to 0 (no filtering).
        :type column: int
        :param limit: Maximum number of results to return (0 = all). Defaults to 0.
        :type limit: int
        :param chronologic: Whether to order results chronologically. Defaults to False.
        :type chronologic: bool
        :param reverse: Whether to reverse the order of results. Defaults to False.
        :type reverse: bool
        :param **kwargs: Additional keyword arguments for the query.
        :type **kwargs: Any
        :returns: List of matching sample-submission associations.
        :rtype: List[ClientSubmissionSampleAssociation]
        """
        row = row or 0
        column = column or 0
        query: Query = cls.__database_session__.query(cls)
        match clientsubmission:
            case ClientSubmission():
                query = query.filter(cls.clientsubmission == clientsubmission)
            case str():
                query = query.join(ClientSubmission).filter(ClientSubmission.submitter_plate_id == clientsubmission)
            case _:
                pass
        match sample:
            case Sample():
                query = query.filter(cls.sample == sample)
            case str():
                query = query.join(Sample).filter(Sample.sample_id == sample)
            case _:
                pass
        if row > 0:
            query = query.filter(cls.row == row)
        if column > 0:
            query = query.filter(cls.column == column)
        match exclude_submission_type:
            case str():
                query = query.join(ClientSubmission).filter(
                    ClientSubmission.submissiontype_name != exclude_submission_type)
            case _:
                pass
        if reverse and not chronologic:
            query = query.order_by(ClientSubmission.id.desc())
        if chronologic:
            if reverse:
                query = query.order_by(ClientSubmission.submitted_date.desc())
            else:
                query = query.order_by(ClientSubmission.submitted_date)
        return cls.execute_query(query=query, limit=limit, **kwargs)

    @classmethod
    def query_or_create(cls,
                        clientsubmission: ClientSubmission | str | None = None,
                        sample: Sample | str | None = None,
                        id: int | None = None,
                        **kwargs) -> List[Any]:
        """
        Query or create a sample link.

        :param clientsubmission: Client submission to filter by. Can be a ClientSubmission object or a string identifier. Defaults to None.
        :type clientsubmission: ClientSubmission | str | None
        :param sample: Sample to filter by. Can be a Sample object or a string identifier. Defaults to None.
        :type sample: Sample | str | None
        :param id: ID of the association to filter by. Defaults to None.
        :type id: int | None
        :param **kwargs: Additional keyword arguments for the query or creation.
        :type **kwargs: Any
        :return: List of matching or newly created sample links.
        :rtype: List[ClientSubmissionSampleAssociation]
        """
        return cls._query_or_create_sample_link(
                    parent=clientsubmission, parent_model=ClientSubmission, parent_lookup="submitter_plate_id",
                    query_kwarg="clientsubmission", ctor_kwarg="submission", sample=sample, id=id, **kwargs
                )

    def delete(self):
        raise AttributeError(f"Delete not implemented for {self.__class__}")

    @classproperty
    def aliases(cls) -> List[str]:
        """
        Gets other names the sql object of this class might go by.
        Usually this is just the lowercase name of the class without "association", 
        but this can be overridden for junction tables that might be referred 
        to by the names of the two linked tables.

        :returns: List of names
        :rtype: List[str]
        """
        return super().aliases + ["equipmentequipmentroleassociation"]

    def add_comment(self, obj):
        """
        Add a comment to this procedure.

        This method is a placeholder for comment UI integration.

        :param obj: Parent object for the comment action.
        :type obj: Any
        """
        logger.info("Add Comment!")
        from frontend.widgets import SubmissionComment
        dlg = SubmissionComment(parent=obj, submission=self)
        if dlg.exec():
            comment = dlg.parse_form()
            self.comment = comment
            self.save(original=False)

    def to_pydantic(self, **kwargs) -> PydClientSubmissionSampleAssociation:
        """
        Converts the ClientSubmissionSampleAssociation instance to a Pydantic model representation.

        :return: PydClientSubmissionSampleAssociation representation of the instance.
        :rtype: PydClientSubmissionSampleAssociation
        """
        output = super().to_pydantic(**kwargs)
        # .rank is used by runs and procedures as well.
        output.rank = self.submission_rank
        return output


class RunSampleAssociation(BaseClass):
    """
    Associates a sample with a run and records its order within that run.

    This junction object links a sample to the analytical run it belongs to and
    preserves the sample position in the run's sample list.

    :ivar run_id: Foreign key for the parent run.
    :vartype run_id: int
    :ivar sample_id: Foreign key for the associated sample.
    :vartype sample_id: int
    :ivar run_rank: Position of the sample within the run.
    :vartype run_rank: int
    :ivar comment: User notes associated with this sample-run link.
    :vartype comment: list[dict] | None
    :ivar run: Parent run linked to this association.
    :vartype run: Run
    :ivar sample: Sample associated with this run.
    :vartype sample: Sample
    """
    run_id = Column(INTEGER, ForeignKey("_run.id", ondelete="CASCADE"), primary_key=True)  #: id of associated procedure
    sample_id = Column(INTEGER, ForeignKey("_sample.id", ondelete="RESTRICT"), primary_key=True)  #: id of associated sample
    run_rank = Column(INTEGER, primary_key=True, default=0)  #: Location in sample list
    _comment = Column(MutableList.as_mutable(JSON))
    
    # NOTE: reference to the Submission object

    _run = relationship(Run,
                       back_populates="runsampleassociation")  #: associated procedure

    # NOTE: reference to the Sample object
    _sample = relationship(Sample, back_populates="samplerunassociation")  #: associated sample

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        run = kwargs.pop('run', None)
        sample = kwargs.pop('sample', None)
        run_rank = kwargs.pop("rank", 0)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        self.run_rank = run_rank
        # Resolve run
        if run is not None:
            try:
                self.run = run
            except Exception:
                logger.error(f"Couldn't set run to {run} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve sample
        if sample is not None:
            try:
                self.sample = sample
            except Exception:
                logger.error(f"Couldn't set sample to {sample} for {self.__class__.__qualname__} with name {self.name}")
    
    @hybrid_property
    def name(self) -> str:
        """
        Gets the constructed name of the association, which combines the run name, sample name, and run rank.

        :return: {self.run.name}->{self.sample.name} (rank={self.run_rank})
        :rtype: str
        """
        try:
            run = self.run.name
        except AttributeError:
            run = "Unassigned Run"
        try:
            sample = self.sample.name
        except AttributeError:
            sample = "Unassigned Sample"
        try:
            run_rank = self.run_rank
        except AttributeError:
            run_rank = "No Submission Rank"
        return f"{run}->{sample} (rank={run_rank})"
    
    @name.expression
    def name(cls):
        """
        Gets the constructed name of the association as a SQL expression, which combines the run name, sample name, and run rank.

        :return: SQL expression for the name of the association.
        :rtype: sqlalchemy.sql.expression.Label
        """
        run_subquery = (
            select(Run.name)
            .where(Run.id==cls.run_id)
            .correlate(cls)
            .scalar_subquery()
        )
        sample_subquery = (
            select(Sample.name)
            .where(Sample.id==cls.sample_id)
            .correlate(cls)
            .scalar_subquery()
        )
        # Note: Can't use f strings for this.
        return run_subquery + "->" + sample_subquery + " (rank=" + cast(cls.run_rank, String) + ")"

    @hybrid_property
    def sample(self):
        """
        Gets the list of samples associated with this run.

        :return: self._sample
        :rtype: Sample
        """
        return self._sample

    @sample.setter
    def sample(self, value: str | dict | Sample | PydSample):
        """
        Set the sample associated with this relationship by parsing an input object.

        :param value: The sample identifier or object to set.
        :type value: str | dict | Sample | PydSample
        """
        from backend.validators.pydant import PydSample
        match value:
            case str():
                output = Sample.query(name=value, limit=1)
            case dict():
                output = Sample.query_or_create(**value)
            case PydSample():
                output = value.to_sql(update=False)
            case Sample():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for sample")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, Sample):
            self._sample = output
        else:
            logger.error(f"{self.__class__.__qualname__} Could not set _sample to {type(output)}")
  
    @hybrid_property
    def run(self):
        """
        Gets the run associated with this relationship.

        :returns: self._run
        :rtype: Run
        """
        return self._run

    @run.setter
    def run(self, value: str | dict | Run | PydRun):
        """
        Sets the run associated with this relationship by parsing an input object.

        :param value: The run identifier or object to set.
        :type value: str | dict | Run | PydRun
        """
        from backend.validators.pydant import PydRun
        match value:
            case str():
                output = Run.query(name=value, limit=1)
            case dict():
                output = Run.query_or_create(**value)
            case PydRun():
                output = value.to_sql(update=False)
            case Run():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for run")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, Run):
            self._run = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._run to {type(output)}")

    @hybrid_property
    def comment(self) -> List[dict]:
        """
        Gets the comments associated with this sample-run link.

        :returns: [item for item in self._comment if all(key in ['user', 'text', 'time'] for key in item.keys())]
        :rtype: List[dict]
        """
        if not self._comment:
            return []
        return [item for item in self._comment if all(key in ['user', 'text', 'time'] for key in item.keys())]
    
    @comment.setter
    def comment(self, value: dict | List[dict]):
        """
        Sets the comments associated with this sample-run link.
        Uses validators.shared.vet_comment to validate the input value.

        :param value: The comments to set.
        :type value: dict | List[dict]
        """
        self._comment = vet_comment(value, current=self._comment)

    @hybrid_property
    def abbreviation_name(self) -> str:
        """
        Gets the abbreviated name of the sample associated with this run, which is based on the client submission abbreviation.

        :returns: Abbreviated name of the sample.
        :rtype: str
        """
        return replace_or_prepend_prefix(self.sample.sample_id, old_prefix=r"^RSL-[A-Z]+-", new_prefix=f"RSL-{self.run.clientsubmission.abbreviation}-")
        # return f"RSL-{self.run.clientsubmission.abbreviation}-{self.sample.sample_id}"

    def to_pydantic(self) -> PydSample:
        """
        Converts this sample to a pydantic model.

        :returns: Pydantic Model
        :rtype: PydSample
        """
        from backend.validators import PydSample
        return PydSample(**self.details_dict)
    
    def to_PydProcedureSampleAssociation(self, procedure):
        """
        Converts this sample to a PydProcedureSampleAssociation model for a given procedure.

        :param procedure: The procedure to associate with this sample.
        :type procedure: Procedure
        :returns: PydProcedureSampleAssociation model
        :rtype: PydProcedureSampleAssociation
        """
        from backend.validators import PydProcedureSampleAssociation
        from backend.excel import ClientSubmissionSampleParser as Parser
        sample = self.to_pydantic()
        output = PydProcedureSampleAssociation(
                        sample=self.sample.sample_id,
                        procedure=procedure.name,
                        procedure_rank = self.run_rank,
                        row = getattr(sample, "row", 0),
                        column = getattr(sample, "column", 0),
                        is_control=getattr(sample, "is_control", Parser.check_sample_id(sample_id=sample.sample_id)),
                        run=self.run.rsl_plate_number
                    )
        output.sample_id = self.sample.sample_id 
        try:
            output.submission_rank = self.misc_info.get('submission_rank', None)
        except KeyError:
            logger.error(output)
        return output

    # @property
    # def hitpicked(self) -> dict | None:
    #     """
    #     Outputs a dictionary usable for html plate maps.

    #     Returns:
    #         dict: dictionary of sample id, row and column in elution plate
    #     """
    #     # NOTE: Since there is no PCR, negliable result is necessary.
    #     sample = self.details_dict
    #     env = jinja_template_loading()
    #     template = env.get_template("support/tooltip.html")
    #     tooltip_text = template.render(fields=sample)
    #     try:
    #         control = self.sample.control
    #     except AttributeError:
    #         control = None
    #     if control is not None:
    #         background = "rgb(128, 203, 196)"
    #     else:
    #         background = "rgb(105, 216, 79)"
    #     try:
    #         tooltip_text += sample['tooltip']
    #     except KeyError:
    #         pass
    #     sample.update(dict(Name=self.sample.sample_id[:10], tooltip=tooltip_text, background_color=background))
    #     return sample

    @classmethod
    @setup_lookup
    def query(cls,
              run: Run | str | None = None,
              exclude_submission_type: str | None = None,
              sample: Sample | str | None = None,
              row: int = 0,
              column: int = 0,
              limit: int = 0,
              chronologic: bool = False,
              reverse: bool = False,
              **kwargs
              ):
        """
        Lookup sample in the database by a number of parameters.

        :param run: Run to filter by. Can be a Run object or a string identifier. Defaults to None.
        :type run: Run | str | None
        :param exclude_submission_type: Submission type to exclude. Defaults to None.
        :type exclude_submission_type: str | None
        :param sample: Sample to filter by. Can be a Sample object or a string identifier. Defaults to None.
        :type sample: Sample | str | None
        :param row: Row of the sample location on the procedure plate. Defaults to 0.
        :type row: int
        :param column: Column of the sample location on the procedure plate. Defaults to 0.
        :type column: int
        :param limit: Maximum number of results to return (0 = all). Defaults to 0.
        :type limit: int
        :param chronologic: Return results in chronologic order. Defaults to False.
        :type chronologic: bool
        :param reverse: Whether or not to reverse order of list. Defaults to False.
        :type reverse: bool
        :param **kwargs: Additional keyword arguments for the query.
        :type **kwargs: Any
        :returns: List of ClientSubmissionSampleAssociation objects matching the criteria.
        """
        row = row or 0
        column = column or 0
        query: Query = cls.__database_session__.query(cls)
        match run:
            case Run():
                query = query.filter(cls.run == run)
            case str():
                query = query.join(Run).filter(Run.rsl_plate_number == run)
            case _:
                pass
        match sample:
            case Sample():
                query = query.filter(cls.sample == sample)
            case str():
                query = query.join(Sample).filter(Sample.sample_id == sample)
            case _:
                pass
        if row > 0:
            query = query.filter(cls.row == row)
        if column > 0:
            query = query.filter(cls.column == column)
        match exclude_submission_type:
            case str():
                query = query.join(Run).join(ClientSubmission).filter(
                    ClientSubmission.submissiontype_name != exclude_submission_type)
            case _:
                pass
        if reverse and not chronologic:
            query = query.order_by(Run.id.desc())
        if chronologic:
            if reverse:
                query = query.order_by(Run.submitted_date.desc())
            else:
                query = query.order_by(Run.submitted_date)
        return cls.execute_query(query=query, limit=limit, **kwargs)

    @classmethod
    def query_or_create(cls,
                        run: Run | str | None = None,
                        sample: Sample | str | None = None,
                        id: int | None = None,
                        **kwargs) -> List[Any]:
        """
        Queries for an association, if none exists creates a new one.

        :param run: associated procedure. Defaults to None.
        :type run:  Run | str | None
        :param sample: associated sample. Defaults to None.
        :type sample: Sample | str | None
        :param id: association id. Defaults to None.
        :type id: int | None
        :returns: Queried or new association.
        :rtype: ClientSubmissionSampleAssociation
        """
        return cls._query_or_create_sample_link(
            parent=run, parent_model=Run, parent_lookup="name",
            query_kwarg="run", ctor_kwarg="run", sample=sample, id=id, **kwargs
        )

    def delete(self):
        raise AttributeError(f"Delete not implemented for {self.__class__}")

    @property
    def details_dict(self) -> dict:
        """
        Gets a dictionary of the association's details, including relevant information from the associated sample and run.

        :return: super().details_dict merged with sample details and misc_info.
        :rtype: dict
        """
        output = super().details_dict
        # NOTE: Figure out how to merge the misc_info if doing .update instead.
        relevant = {k: v for k, v in output.items() if k not in ['sample']}
        output = self.sample.details_dict
        misc = output.get('misc_info', {})
        output.update(relevant)
        output['misc_info'] = misc
        output['sql_instance'] = self.sample
        return output

    def add_comment(self, obj):
        """
        Add a comment to this procedure.

        This method is a placeholder for comment UI integration.

        :param obj: Parent object for the comment action.
        :type obj: Any
        """
        logger.info("Add Comment!")
        from frontend.widgets import SubmissionComment
        dlg = SubmissionComment(parent=obj, submission=self)
        if dlg.exec():
            comment = dlg.parse_form()
            self.comment = comment
            self.save(original=False)


class ProcedureSampleAssociation(BaseClass):
    """
    Represents the association between a procedure and a sample.

    :ivar id: Unique identifier for the association record.
    :vartype id: int
    :ivar procedure_id: Foreign key linking this association to the procedure.
    :vartype procedure_id: int
    :ivar sample_id: Foreign key linking this association to the sample.
    :vartype sample_id: int
    :ivar row: Row position of the sample within the procedure layout.
    :vartype row: int | None
    :ivar column: Column position of the sample within the procedure layout.
    :vartype column: int | None
    :ivar procedure_rank: Ordering rank for this procedure/sample pairing.
    :vartype procedure_rank: int
    :ivar _comment: Stored comment metadata associated with the relationship.
    :vartype _comment: list[dict] | None
    :ivar procedure: Procedure linked to this association.
    :vartype procedure: Procedure
    :ivar sample: Sample linked to this association.
    :vartype sample: Sample
    :ivar results: Results attached to this procedure/sample association.
    :vartype results: list[Results]
    """
    # columns: id becomes the sole PK; the old composite becomes a UNIQUE constraint
    id             = Column(INTEGER, primary_key=True, autoincrement=True)          # was: unique=True, nullable=False
    procedure_id   = Column(INTEGER, ForeignKey("_procedure.id", ondelete="CASCADE"),  nullable=False)  # drop primary_key=True
    sample_id      = Column(INTEGER, ForeignKey("_sample.id",    ondelete="RESTRICT"), nullable=False)  # drop primary_key=True
    row            = Column(INTEGER)
    column         = Column(INTEGER)
    procedure_rank = Column(INTEGER, nullable=False, default=0)                     # drop primary_key=True
    _comment = Column(MutableList.as_mutable(JSON))

    __table_args__ = (
        UniqueConstraint("procedure_id", "sample_id", "procedure_rank",
                        name="uq_proc_sample_rank"),
        {"sqlite_autoincrement": True, "extend_existing": True},   # keep extend_existing from BaseClass
    )

    _procedure = relationship(Procedure,
                             back_populates="proceduresampleassociation")  #: associated procedure

    # Explicitly cascade save-update and merge from association -> sample so that
    # adding a transient ProcedureSampleAssociation to a Session will also
    # attach (and persist) its Sample. We intentionally avoid destructive
    # cascades (like delete) here to prevent accidental deletion of Sample
    # rows when associations are removed.
    _sample = relationship(
        Sample,
        back_populates="sampleprocedureassociation",
        cascade="save-update, merge",
    )  #: associated equipment
    _results = relationship("Results", back_populates="_sampleprocedureassociation")  #: associated results

    def __init__(self, new_id: int | None = None,  *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        
        procedure = kwargs.pop('procedure', None)
        sample = kwargs.pop('sample', None)
        results = kwargs.pop('results', None)
        procedure_rank = kwargs.pop("rank", 0)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        self.procedure_rank = procedure_rank
        # Resolve proceduretype
        if procedure is not None:
            try:
                self.procedure = procedure
            except Exception:
                logger.error(f"Couldn't set procedure to {procedure} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve sample
        if sample is not None:
            try:
                self.sample = sample
            except Exception:
                logger.error(f"Couldn't set sample to {sample} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve results
        if results is not None:
            try:
                self.results = results
            except Exception:
                logger.error(f"Couldn't set results to {results} for {self.__class__.__qualname__} with name {self.name}")
        self.procedure_rank = procedure_rank
        if new_id is not None:
            self.id = new_id
        self._comment = [] if self._comment is None else self._comment

    @hybrid_property
    def sample(self):
        """
        Get the sample associated with this procedure/sample association.

        :returns: self._sample
        :rtype: Sample
        """
        return self._sample
    
    @sample.setter
    def sample(self, value: str | dict | Sample | PydSample):
        """
        Set the sample associated with this procedure/sample association by parsing an input object.

        :param value: The sample identifier or object to set.
        :type value: str | dict | Sample | PydSample
        """
        from backend.validators.pydant import PydSample
        match value:
            case str():
                output = Sample.query(name=value, limit=1)
            case dict():
                output = Sample.query_or_create(**value)
            case PydSample():
                # NOTE: If the sample hasn't already been saved, we'll have to do some updating.
                update = not hasattr(value.sql_instance, "_sa_instance_state")
                if update:
                    logger.warning(f"{value} has not been saved previously. Updating")
                output = value.to_sql(update=update)
            case Sample():
                output = value
            case _:
                logger.error(f"Unmatched value {type(value)}: {value} for {self.__class__.__qualname__}._sample")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, Sample):
            self._sample = output
        else:
            logger.error(f"{self.__class__.__qualname__} Could not set _sample to {type(output)}")
  
    @hybrid_property
    def procedure(self):
        """
        Gets the procedure associated with this procedure/sample association.

        :returns: self._procedure
        :rtype: Procedure
        """
        return self._procedure

    @procedure.setter
    def procedure(self, value: str | dict | Procedure | PydProcedure):
        """
        Set the procedure associated with this procedure/sample association by parsing an input object.

        :param value: The procedure identifier or object to set.
        :type value: str | dict | Procedure | PydProcedure
        """
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
            logger.error(f"Could not set _procedure to {type(output)}")

    @hybrid_property
    def comment(self):
        """
        Gets the comments associated with this procedure/sample association.

        :returns: [item for item in self._comment if all(key in ['user', 'text', 'time'] for key in item.keys())]
        :rtype: List[dict]
        """
        if not self._comment:
            return []
        return [item for item in self._comment if all(key in ['user', 'text', 'time'] for key in item.keys())]
    
    @comment.setter
    def comment(self, value):
        """
        Sets the comments associated with this procedure/sample association.

        :param value: The comments to set.
        :type value: List[dict]
        """
        self._comment = vet_comment(value, current=self._comment)

    def add_comment(self, obj):
        """
        Add a comment to this procedure.

        This method is a placeholder for comment UI integration.

        :param obj: Parent object for the comment action.
        :type obj: Any
        :return: None
        """
        logger.info("Add Comment!")
        from frontend.widgets import SubmissionComment
        dlg = SubmissionComment(parent=obj, submission=self)
        if dlg.exec():
            comment = dlg.parse_form()
            self.comment = comment
            self.save(original=False)

    @hybrid_property
    def abbreviation_name(self) -> str:
        """
        Gets the abbreviated name of the sample associated with this procedure, which is based on the client submission abbreviation.

        :returns: Abbreviated name of the sample.
        :rtype: str
        """
        return f"RSL-{self.procedure.run.clientsubmission.abbreviation}-{self.sample.sample_id}"
    
    @hybrid_property
    def name(self):
        """
        Gets the name of the procedure/sample association.

        :returns: {self.procedure.name}->{self.sample.name} (rank={self.procedure_rank})
        :rtype: str
        """
        try:
            procedure = self.procedure.name
        except AttributeError:
            procedure = "Unassigned Procedure"
        try:
            sample = self.sample.name
        except AttributeError:
            sample = "Unassigned Sample"
        return f"{procedure}->{sample} (rank={self.procedure_rank})"
    
    @name.expression
    def name(cls):
        """
        Gets the name of the procedure/sample association as a SQL expression.

        :returns: SQL expression for the name of the association.
        :rtype: sqlalchemy.sql.expression.Label
        """
        procedure_subquery = (
            select(Procedure.name)
            .where(Procedure.id==cls.procedure_id)
            .correlate(cls)
            .scalar_subquery()
        )
        sample_subquery = (
            select(Sample.name)
            .where(Sample.id==cls.sample_id)
            .correlate(cls)
            .scalar_subquery()
        )
        # Note: Can't use f strings for this.
        return procedure_subquery + "->" + sample_subquery + " (rank=" + cast(cls.procedure_rank, String) + ")"
    
    @hybrid_property
    def results(self):
        """
        Gets the results associated with this procedure/sample association.

        :returns: self._results
        :rtype: list[Results]
        """
        return self._results

    @results.setter
    def results(self, value: List[str | dict | Results | PydResults]):
        """
        Set results associated with this procedure/sample association by parsing an input iterable.

        :param value: An iterable of result identifiers or objects to set.
        :type value: List[str | dict | Results | PydResults]
        """
        from backend.validators.pydant import PydResults
        from backend.db.models import Results
        value = iterable_enforcer(value)
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
                    logger.error(f"Unmatched value {item} for results")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, Results):
                output.result.update(dict(sample_id=self.sample.sample_id))
                if not self.already_in_collection(output, list_):
                    list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._results")
        self._results = list_

    @property
    def well(self) -> str | None:
        """
        Gets the well position of the sample in the procedure plate based on its row and column.

        :returns: Well position in the format 'A1', 'B2', etc.
        :rtype: str | None
        """
        return convert_row_column_to_well(self.row, self.column)

    @classmethod
    def query(cls, 
              name: str | None = None,
              sample: Sample | str | None = None, 
              procedure: Procedure | str | None = None, 
              limit: int = 0,
              **kwargs):
        """
        Query for procedure/sample associations based on name, sample, and procedure.

        :param name: Name of the association to filter by. Defaults to None.
        :type name: str | None
        :param sample: Sample to filter by. Can be a Sample object or a string identifier. Defaults to None.
        :type sample: Sample | str | None
        :param procedure: Procedure to filter by. Can be a Procedure object or a string identifier. Defaults to None.
        :type procedure: Procedure | str | None
        :param limit: Maximum number of results to return (0 = all). Defaults to 0.
        :type limit: int
        :param **kwargs: Additional keyword arguments for the query.
        :type **kwargs: Any
        :returns: List of ProcedureSampleAssociation objects matching the criteria.
        :rtype: List[ProcedureSampleAssociation]
        """
        query = cls.__database_session__.query(cls)
        match name:
            case str():
                query = query.filter(cls.name == name)
            case _:
                pass
        match sample:
            case Sample():
                query = query.filter(cls.sample == sample)
            case str():
                query = query.join(Sample).filter(Sample.sample_id == sample)
            case _:
                pass
        match procedure:
            case Procedure():
                query = query.filter(cls.procedure == procedure)
            case str():
                query = query.join(Procedure).filter(Procedure.name == procedure)
            case _:
                pass
        if sample and procedure:
            limit = 1
        return cls.execute_query(query=query, limit=limit, **kwargs)

    @classmethod
    def autoincrement_id(cls, procedure_rank: int = 1) -> int:
        """
        Increments the association id automatically

        :param procedure_rank: The rank of the procedure/sample association. Defaults to 1.
        :type procedure_rank: int
        :returns: incremented id
        :rtype: int
        """
        try:
            output = max([item.id for item in cls.query()])
        except ValueError as e:
            logger.exception(f"Unable to autoincrement id due to: {e}, setting to 0")
            output = 0
        return output + procedure_rank

    @property
    def details_dict(self) -> dict:
        """
        Gets a dictionary of the association's details, including relevant information from the associated sample and run.

        :return: super().details_dict merged with sample details and misc_info.
        :rtype: dict
        """
        output = super().details_dict
        # NOTE: Figure out how to merge the misc_info if doing .update instead.
        relevant = {k: v for k, v in output.items() if k not in []}
        output = self.sample.details_dict
        assert "sample_id" in output.keys()
        misc = output.get('misc_info', {})
        output.update(relevant)
        
        output['misc_info'] = misc
        output['row'] = self.row
        output['column'] = self.column
        output['results'] = [item.details_dict for item in self.results]
        match self.sample._is_control:
            case 1:
                output['control_type'] = 'positivecontrol'
            case -1:
                output['control_type'] = 'negativecontrol'
            case _:
                output['control_type'] = 'sample'
        return output

    def to_pydantic(self, **kwargs):
        """
        Converts this procedure/sample association to a pydantic model.

        :param **kwargs: Additional keyword arguments for the pydantic model.
        :type **kwargs: Any
        :returns: Pydantic Model
        :rtype: PydProcedureSampleAssociation
        """
        output = super().to_pydantic()
        try:
            output.submission_rank = output.misc_info.get('submission_rank', None)
        except KeyError:
            logger.error(output)
        match self.sample.is_control:
            case 1:
                output.sample_type = "positivecontrol"
                output.background_color = "pink"
            case -1:
                output.sample_type = "negativecontrol"
                output.background_color = "cyan"
            case _:
                output.sample_type = "sample"
                if output.enabled:
                    output.background_color = "#66ff66"
                else:
                    output.background_color = "white"
        output.rank = self.procedure_rank
        assert output.name == self.name
        
        return output

    def save(self):
        """
        Persists the current state of the procedure/sample association to the database.
        """
        if self.sample_id in [None, ""]:
            return
        super().save()
        

__all__ = ["ClientSubmission", "Run", "Sample", "ClientSubmissionSampleAssociation", "RunSampleAssociation", "ProcedureSampleAssociation"]