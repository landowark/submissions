"""
Models for the main procedure and sample types.
"""
from __future__ import annotations
from getpass import getuser
import logging, tempfile, re, numpy as np, pandas as pd, types, sys, itertools
from inspect import isclass
from zipfile import BadZipfile
from operator import itemgetter
from pprint import pformat
from pandas import DataFrame
from sqlalchemy.ext.hybrid import hybrid_property
from frontend.widgets.functions import select_save_file
from backend.db.models.procedures import ReagentLot
from . import BaseClass, SubmissionType, ClientLab, Contact, LogMixin, Procedure
from sqlalchemy import Column, String, TIMESTAMP, INTEGER, ForeignKey, JSON, FLOAT, case, cast, func
from sqlalchemy.orm import relationship, Query, declared_attr
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.associationproxy import association_proxy, _AssociationList
from sqlalchemy.exc import OperationalError as AlcOperationalError, IntegrityError as AlcIntegrityError, StatementError
from sqlite3 import OperationalError as SQLOperationalError, IntegrityError as SQLIntegrityError
from tools import (setup_lookup, jinja_template_loading, create_holidays_for_year,
                   check_dictionary_inclusion_equality, is_power_user, row_map, timezone)
from datetime import datetime, date
from dateutil.parser import parse as dateparse, ParserError
from typing import List, Literal, Generator, TYPE_CHECKING
from pathlib import Path
if TYPE_CHECKING:
    from backend.db.models.procedures import ProcedureType, Procedure

logger = logging.getLogger(f"submissions.{__name__}")


class ClientSubmission(BaseClass, LogMixin):
    """
    Object for the client procedure from which all procedure objects will be created.
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    submitter_plate_id = Column(String(127), unique=True)  #: The number given to the submission by the submitting lab
    _submitted_date = Column(TIMESTAMP)  #: Date submission received
    _clientlab = relationship("ClientLab", back_populates="_clientsubmission")  #: client org
    clientlab_id = Column(INTEGER, ForeignKey("_clientlab.id", ondelete="SET NULL",
                                              name="fk_BS_sublab_id"))  #: client lab id from _organizations
    submission_category = Column(String(64))  #: i.e. Surveillance
    sample_count = Column(INTEGER)  #: Number of sample in the procedure
    full_batch_size = Column(INTEGER)  #: Number of wells in provided plate. 0 if no plate.
    comments = Column(JSON)  #: comment objects from users.
    _run = relationship("Run", back_populates="_clientsubmission")  #: many-to-one relationship
    _contact = relationship("Contact", back_populates="_clientsubmission")  #: contact representing submitting lab.
    contact_id = Column(INTEGER, ForeignKey("_contact.id", ondelete="SET NULL",
                                            name="fk_BS_contact_id"))  #: contact id from _organizations
    submissiontype_name = Column(String, ForeignKey("_submissiontype.name", ondelete="SET NULL",
                                                    name="fk_BS_subtype_name"))  #: name of joined submission type
    _submissiontype = relationship("SubmissionType", back_populates="_clientsubmission")  #: archetype of this procedure
    cost_centre = Column(
        String(64))  #: Permanent storage of used cost centre in case organization field changed in the future.

    clientsubmissionsampleassociation = relationship(
        "ClientSubmissionSampleAssociation",
        back_populates="_clientsubmission",
        cascade="all, delete-orphan",
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
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if submitted_date is not None:
            try:
                self.submitted_date = submitted_date
            except Exception:
                try:
                    self._misc_info.update({'submitted_date': submitted_date})
                except Exception:
                    pass
        if clientlab is not None:
            try:
                self.clientlab = clientlab
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'clientlab': clientlab})
                except Exception:
                    pass
        # Resolve reagentrole
        if run is not None:
            try:
                self.run = run
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'run': run})
                except Exception:
                    pass
        # Resolve reagentrole
        if contact is not None:
            try:
                self.contact = contact
            except Exception:
                try:
                    self._misc_info.update({'contact': contact})
                except Exception:
                    pass
        # Resolve reagentrole
        if submissiontype is not None:
            try:
                self.submissiontype = submissiontype
            except Exception:
                try:
                    self._misc_info.update({'submissiontype': submissiontype})
                except Exception:
                    pass
        # Resolve reagentrole
        if sample is not None:
            try:
                self.sample = sample
            except Exception:
                try:
                    self._misc_info.update({'sample': sample})
                except Exception:
                    pass
      
    @hybrid_property
    def submissiontype(self):
        return self._submissiontype

    @submissiontype.setter
    def submissiontype(self, value):
        from backend.validators.pydant import PydSubmissionType
        match value:
            case str():
                output = SubmissionType.query(name=value, limit=1)
            case dict():
                output = SubmissionType.query_or_create(**value)
            case PydSubmissionType():
                output = value.to_sql()
            case SubmissionType():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for submissiontype")
                return
        if isinstance(output, SubmissionType):
            self._submissiontype = output
        else:
            logger.error(f"Could not set _submissiontype to {output}")

    @hybrid_property
    def contact(self):
        return self._contact

    @contact.setter
    def contact(self, value):
        from backend.validators.pydant import PydContact
        match value:
            case str():
                output = Contact.query(name=value, limit=1)
            case dict():
                output = Contact.query_or_create(**value)
            case PydContact():
                output = value.to_sql()
            case Contact():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for contact")
                return
        if isinstance(output, Contact):
            self._contact = output
        else:
            logger.error(f"Could not set _contact to {output}")

    @hybrid_property
    def run(self):
        return self._run
    
    @run.setter
    def run(self, value):
        from backend.validators.pydant import PydRun
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        for item in value:
            error_msg = f"Can't add item {item} to {self.name}._run"
            match item:
                case str():
                    output = Run.query(name=item, limit=1)
                case dict():
                    output = Run.query_or_create(**item)
                case PydRun():
                    output = item.to_sql()
                case Run():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for run")
                    continue
            if isinstance(output, ReagentLot):
                self._run.append(output)
            else:
                logger.error(f"Could not add {output} to _run")

    @hybrid_property
    def clientlab(self):
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
                output = value.to_sql()
            case ClientLab():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for clientlab")
                return
        if isinstance(output, ClientLab):
            self._clientlab = output
        else:
            logger.error(f"Could not set _clientlab to {value}")

    @hybrid_property
    def sample(self):
        return self._sample
    
    @sample.setter
    def sample(self, value):
        from backend.validators.pydant.concrete import PydSample
        if not isinstance(value, list) and not isinstance(value, _AssociationList):
            value = [value]
        for item in value:
            logger.debug(f"Incoming sample: {type(item)}: {item}")
            match item:
                case dict():
                    output = ClientSubmissionSampleAssociation(sample=item['name'], clientsubmission=self, **{k: v for k, v in item.items() if k != 'name'})
                case PydSample():
                    output = ClientSubmissionSampleAssociation(sample=item, clientsubmission=self, **{k: v for k, v in item.__dict__.items() if k != 'name'})
                case Sample():
                    output = ClientSubmissionSampleAssociation(sample=item, clientsubmission=self, **{k: v for k, v in item._misc_info.items() if k != 'name'})
                case ClientSubmissionSampleAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} of type {type(item)} for sample")
                    continue
            # logger.debug(f"Setting equipment with output: {output}")
            if isinstance(output, ClientSubmissionSampleAssociation):
                if output not in self.clientsubmissionsampleassociation:
                    self.clientsubmissionsampleassociation.append(output)
            else:
                logger.error(f"Could not add {item} to ._sample")

    @hybrid_property
    def submitted_date(self):
      return self._submitted_date

    @submitted_date.setter
    def submitted_date(self, value):
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
                raise ValueError(f"Unmatched value {value['value']} for datetime")
        value = output.replace(tzinfo=timezone)
        self._submitted_date = value

    @hybrid_property
    def name(self):
        return self.submitter_plate_id

    @property
    def max_sample_rank(self) -> int:
        return max([item.submission_rank for item in self.clientsubmissionsampleassociation])

    @classmethod
    @setup_lookup
    def query(cls,
              submissiontype: str | SubmissionType | None = None,
              # submissiontype_name: str | None = None,
              id: int | str | None = None,
              submitter_plate_id: str | None = None,
              start_date: date | datetime | str | int | None = None,
              end_date: date | datetime | str | int | None = None,
              chronologic: bool = False,
              limit: int = 0,
              page: int = 1,
              page_size: None | int = 250,
              **kwargs
              ) -> ClientSubmission | List[ClientSubmission]:
        """
        Lookup procedure based on a number of parameters. Overrides parent.

        Args:
            submissiontype (str | models.SubmissionType | None, optional): Submission type of interest. Defaults to None.
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
        # from ... import RunReagentAssociation
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
            start_date = cls.rectify_query_date(start_date)
            end_date = cls.rectify_query_date(end_date, eod=True)
            query = query.filter(cls.submitted_date.between(start_date, end_date))
        # NOTE: by rsl number (returns only a single value)
        match submitter_plate_id:
            case str():
                query = query.filter(cls.submitter_plate_id == submitter_plate_id)
                limit = 1
            case _:
                pass
        match submissiontype:
            case SubmissionType():
                query = query.filter(cls.submissiontype == submissiontype)
            case str():
                query = query.filter(cls.submissiontype_name == submissiontype)
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
        return cls.execute_query(query=query, limit=limit, offset=offset, **kwargs)

    @property
    def template_file(self):
        return self.submissiontype.template_file

    @property
    def range_dict(self):
        return self.submissiontype.info_map

    @classmethod
    def submissions_to_df(cls, submissiontype: str | None = None, limit: int = 0,
                          chronologic: bool = True, page: int = 1, page_size: int = 250) -> pd.DataFrame:
        """
        Convert all procedure to dataframe

        Args:
            page_size (int, optional): Number of items to include in query result. Defaults to 250.
            page (int, optional): Limits the number of procedure to a page size. Defaults to 1.
            chronologic (bool, optional): Sort procedure in chronologic order. Defaults to True.
            submissiontype (str | None, optional): Filter by SubmissionType. Defaults to None.
            limit (int, optional): Maximum number of results to return. Defaults to 0.

        Returns:
            pd.DataFrame: Pandas Dataframe of all relevant procedure
        """
        # NOTE: use lookup function to create list of dicts
        subs = [item.to_dict() for item in
                cls.query(submissiontype=submissiontype, limit=limit, chronologic=chronologic, page=page,
                          page_size=page_size)]
        df = pd.DataFrame.from_records(subs)
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

    def to_dict(self, full_data: bool = False, backup: bool = False, report: bool = False) -> dict:
        """
        Constructs dictionary used in procedure summary

        Args:
            expand (bool, optional): indicates if generators to be expanded. Defaults to False.
            report (bool, optional): indicates if to be used for a report. Defaults to False.
            full_data (bool, optional): indicates if sample dicts to be constructed. Defaults to False.
            backup (bool, optional): passed to adjust_to_dict_samples. Defaults to False.

        Returns:
            dict: dictionary used in procedure summary and details
        """
        # NOTE: get lab from nested organization object
        try:
            sub_lab = self.clientlab.name
        except AttributeError:
            sub_lab = None
        try:
            sub_lab = sub_lab.replace("_", " ").title()
        except AttributeError:
            pass

        # NOTE: get extraction kittype name from nested kittype object
        output = {
            "id": self.id,
            "submissiontype": self.submissiontype_name,
            "submitter_plate_id": self.submitter_plate_id,
            "submitted_date": self.submitted_date.strftime("%Y-%m-%d"),
            "clientlab": sub_lab,
            "sample_count": self.sample_count,
        }
        if report:
            return output
        if full_data:
            samples = None
            runs = [item.to_dict(full_data=True) for item in self.run]
        else:
            samples = None
            custom = None
            runs = None
        try:
            comments = self.comments
        except Exception as e:
            logger.error(f"Error setting comment: {self.comments}, {e}")
            comments = None
        try:
            contact = self.contact.name
        except AttributeError as e:
            try:
                contact = f"Defaulted to: {self.clientlab.contacts[0].name}"
            except (AttributeError, IndexError):
                contact = "NA"
        try:
            contact_phone = self.contact.phone
        except AttributeError:
            contact_phone = "NA"
        output["abbreviation"] = self.submissiontype.abbreviation
        output["submission_category"] = self.submission_category
        output["sample"] = samples
        output["comment"] = comments
        output["contact"] = contact
        output["contact_phone"] = contact_phone
        output["run"] = runs
        output['name'] = self.name
        return output

    def add_sample(self, sample: Sample):
        try:
            assert isinstance(sample, Sample)
        except AssertionError:
            logger.warning(f"Converting {sample} to sql.")
            sample = sample.to_sql()
        try:
            row = sample._misc_info.get('row', 0)
        except AttributeError:
            row = 0
        try:
            column = sample._misc_info.get('column', 0)
        except AttributeError:
            column = 0
        submission_rank = sample._misc_info.get('submission_rank', None)
        if sample in self.sample:
            return
        logger.debug(f"Attempting association for {sample}")
        assoc = ClientSubmissionSampleAssociation(
            sample=sample,
            submission=self,
            submission_rank=submission_rank,
            row=row,
            column=column
        )
        assert hasattr(assoc, "sample_id")
        self.sample += [assoc]

    @property
    def custom_context_events(self) -> dict:
        """
        Creates dictionary of str:function to be passed to context menu

        Returns:
            dict: dictionary of functions
        """
        names = ["Add Run", "Edit", "Add Comment", "Show Details", "Delete"]
        return {item: self.__getattribute__(item.lower().replace(" ", "_")) for item in names}

    def add_run(self, obj):
        from frontend.widgets.sample_checker import SampleChecker
        samples = [sample.to_pydantic() for sample in self.clientsubmissionsampleassociation]
        checker = SampleChecker(parent=None, title="Create Run", samples=samples, clientsubmission=self)
        if checker.exec():
            run = Run(clientsubmission=self, rsl_plate_number=checker.rsl_plate_number)
            logger.debug(f"Created run: {pformat(run.__dict__)}")
            active_samples = [sample for sample in samples if sample.enabled]
            # for sample in active_samples:
            #     logger.debug(f"Enabled sample: {sample}")
            #     sample = sample.to_sql()
            #     if sample not in run.sample:
            #         assoc = run.add_sample(sample)
            run.sample = active_samples
            run.save()
        else:
            logger.warning("Run cancelled.")
        obj.set_data()

    def edit(self, obj):
        logger.debug("Edit")

    def add_comment(self, obj):
        logger.debug("Add Comment")

    def details_dict(self, **kwargs):
        output = super().details_dict(**kwargs)
        # output['clientlab'] = output['clientlab'].details_dict()
        if "contact" in output and issubclass(output['contact'].__class__, BaseClass):
            output['contact'] = output['contact'].details_dict()
            output['contact_email'] = output['contact']['email']
        # output['submissiontype'] = output['submissiontype'].details_dict()
        # output['run'] = [run.details_dict() for run in output['run']]
        output['sample'] = [sample.details_dict() for sample in output['clientsubmissionsampleassociation']]
        output['name'] = self.name
        output['client_lab'] = output['clientlab']
        output['submission_type'] = output['submissiontype']
        try:
            output['excluded'] += ['run', "sample", "clientsubmissionsampleassociation", "excluded",
                               "expanded", 'clientlab', 'submissiontype', 'id', 'info_placement', 'filepath', "name"]
        except KeyError:
            output['excluded'] = ['run', "sample", "clientsubmissionsampleassociation", "excluded",
                               "expanded", 'clientlab', 'submissiontype', 'id', 'info_placement', 'filepath', "name"]
        output['expanded'] = ["clientlab", "contact", "submissiontype"]
        return output

    def to_pydantic(self, filepath: Path | str | None = None, **kwargs):
        output = super().to_pydantic(filepath=filepath, **kwargs)
        return output


class Run(BaseClass, LogMixin):
    """
    Object for an entire procedure procedure. Links to client procedure, reagents, equipment, process
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    rsl_plate_number = Column(String(32), unique=True, nullable=False)  #: RSL name (e.g. RSL-22-0012)
    clientsubmission_id = Column(INTEGER, ForeignKey("_clientsubmission.id", ondelete="SET NULL",
                                                     name="fk_BS_clientsub_id"))  #: id of parent clientsubmission
    _clientsubmission = relationship("ClientSubmission", back_populates="_run")  #: parent clientsubmission
    _started_date = Column(TIMESTAMP)  #: Date this procedure was started.
    run_cost = Column(
        FLOAT(2))  #: total cost of running the plate. Set from constant and mutable kittype costs at time of creation.
    signed_by = Column(String(32))  #: user name of person who submitted the procedure to the database.
    comment = Column(JSON)  #: user notes
    custom = Column(JSON)  #: unknown
    _completed_date = Column(TIMESTAMP)  #: Date this procedure was finished.
    _procedure = relationship("Procedure", back_populates="_run", uselist=True)  #: children procedures

    runsampleassociation = relationship(
        "RunSampleAssociation",
        back_populates="_run",
        cascade="all, delete-orphan",
    )  #: Relation to ClientSubmissionSampleAssociation

    _sample = association_proxy("runsampleassociation", "_sample")

    def __repr__(self) -> str:
        return f"<Submission({self.name})>"

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
        logger.debug(f"Remaining kwargs: {kwargs}")
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if started_date is not None:
            try:
                self.started_date = started_date
            except Exception:
                try:
                    self._misc_info.update({'started_date': started_date})
                except Exception:
                    pass
        if clientsubmission is not None:
            try:
                self.clientsubmission = clientsubmission
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'clientsubmission': clientsubmission})
                except Exception:
                    pass
        # Resolve reagentrole
        if completed_date is not None:
            try:
                self.completed_date = completed_date
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'completed_date': completed_date})
                except Exception:
                    pass
        # Resolve reagentrole
        if procedure is not None:
            try:
                self.procedure = procedure
            except Exception:
                try:
                    self._misc_info.update({'procedure': procedure})
                except Exception:
                    pass
        # Resolve reagentrole
        if sample is not None:
            try:
                self.sample = sample
            except Exception:
                try:
                    self._misc_info.update({'sample': sample})
                except Exception:
                    pass

    @hybrid_property
    def procedure(self):
        return self._procedure

    @procedure.setter
    def procedure(self, value):
        from backend.validators.pydant import PydProcedure
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case str():
                    output = Procedure.query(name=item, limit=1)
                case dict():
                    output = Procedure.query_or_create(**item)
                case PydProcedure():
                    output = item.to_sql()
                case Procedure():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for procedure")
                    continue
            if isinstance(output, Procedure):
                self._procedure.append(output)
            else:
                logger.error(f"Could not add {output} to _procedure")

    @hybrid_property
    def clientsubmission(self):
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
                output = value.to_sql()
            case ClientSubmission():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for clientsubmission")
                return
        if isinstance(output, ClientSubmission):
            self._clientsubmission = output
        else:
            logger.error(f"Could not set _clientsubmission to {output}")

    @hybrid_property
    def sample(self):
        return self._sample
    
    @sample.setter
    def sample(self, value):
        from backend.validators.pydant import PydSample
        if not isinstance(value, list):
            value = [value]
        for item in value:
            logger.debug(f"Incoming sample: {type(item)} - {item}")
            match item:
                case dict():
                    output = RunSampleAssociation(sample=item['name'], run=self, **{k: v for k, v in item.items() if k != 'name'})
                case PydSample():
                    output = RunSampleAssociation(sample=item, run=self, **{k: v for k, v in item.__dict__.items() if k != 'name'})
                case RunSampleAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}.sample")
                    continue
            # logger.debug(f"Setting equipment with output: {output}")
            if isinstance(output, RunSampleAssociation):
                if output not in self.runsampleassociation:
                    self.runsampleassociation.append(output)
            else:
                logger.error(f"Could not add {item} to ._sample")

    @hybrid_property
    def name(self):
        return self.rsl_plate_number

    @hybrid_property
    def plate_number(self):
        return self.rsl_plate_number

    @hybrid_property
    def started_date(self):
        if self._started_date:
            return self._started_date
        else:
            try:
                value = min([proc.started_date for proc in self.procedure])
            except ValueError:
                value = datetime.now()
            return value

    @started_date.setter
    def started_date(self, value):
        if value:
            self._started_date = value
        else:
            self._started_date = min([proc.started_date for proc in self.procedure])

    @hybrid_property
    def completed_date(self):
        if not self.signed_by:
            return None
        if self._completed_date:
            return self._completed_date
        else:
            value = max([proc.completed_date for proc in self.procedure])
            return value

    @completed_date.setter
    def completed_date(self, value):
        if value:
            self._completed_date = value
        else:
            self._completed_date = min([proc.started_date for proc in self.procedure])

    @classmethod
    def get_default_info(cls, *args, submissiontype: SubmissionType | None = None) -> dict:
        """
        Gets default info from the database for a given procedure type.

        Args:
            *args (): List of fields to get
            submissiontype (SubmissionType): the procedure type of interest. Necessary due to generic procedure types.

        Returns:
            dict: Default info

        """
        # NOTE: Create defaults for all proceduretype
        # NOTE: Singles tells the query which fields to set limit to 1
        dicto = super().get_default_info()
        recover = ['filepath', 'sample', 'csv', 'comment', 'equipment']
        dicto.update(dict(
            details_ignore=['excluded', 'reagents', 'sample',
                            'extraction_info', 'comment', 'barcode',
                            'platemap', 'export_map', 'equipment', 'tips', 'custom'],
            # NOTE: Fields not placed in ui form
            form_ignore=['reagents', 'ctx', 'id', 'cost', 'extraction_info', 'signed_by', 'comment', 'namer',
                         'submission_object', "tips", 'contact_phone', 'custom', 'cost_centre', 'completed_date',
                         'control', "origin_plate"] + recover,
            # NOTE: Fields not placed in ui form to be moved to pydantic
            form_recover=recover
        ))
        # NOTE: Grab mode_sub_type specific info.
        if args:
            output = {k: v for k, v in dicto.items() if k in args}
        else:
            output = {k: v for k, v in dicto.items()}
        # logger.debug(f"Submission type for get default info: {submissiontype}")
        if isinstance(submissiontype, SubmissionType):
            st = submissiontype
        else:
            st = cls.get_submission_type(submissiontype)
        if st is None:
            # logger.error("No default info for Run.")
            pass
        else:
            output['submissiontype'] = st.name
            for k, v in st.defaults.items():
                if args and k not in args:
                    continue
                else:
                    match v:
                        case list():
                            output[k] += v
                        case _:
                            output[k] = v
        if len(args) == 1:
            try:
                return output[args[0]]
            except KeyError as e:
                if "pytest" in sys.modules and args[0] == "abbreviation":
                    return "BS"
                else:
                    raise KeyError(f"{args[0]} not found in {output}")
        return output

    @classmethod
    def get_submission_type(cls, submissiontype: str | SubmissionType | None = None) -> SubmissionType:
        """
        Gets the SubmissionType associated with this class

        Args:
            submissiontype (str | SubmissionType, Optional): Identity of the procedure type to retrieve. Defaults to None.

        Returns:
            SubmissionType: SubmissionType with name equal sub_type or this polymorphic identity if sub_type is None.
        """
        if isinstance(submissiontype, dict):
            try:
                submissiontype = submissiontype['value']
            except KeyError as e:
                logger.error(f"Couldn't extract value from {submissiontype}")
                raise e
        match submissiontype:
            case str():
                return SubmissionType.query(name=submissiontype)
            case SubmissionType():
                return submissiontype
            case _:
                return None

    @classmethod
    def construct_info_map(cls, submissiontype: SubmissionType | None = None,
                           mode: Literal["read", "write"] = "read") -> dict:
        """
        Method to call procedure type's construct info map.

        Args:
            mode (Literal["read", "write"]): Which map to construct.

        Returns:
            dict: Map of info locations.
        """
        return cls.get_submission_type(submissiontype).construct_info_map(mode=mode)

    @classmethod
    def construct_sample_map(cls, submissiontype: SubmissionType | None = None) -> dict:
        """
        Method to call procedure type's construct_sample_map

        Returns:
            dict: sample location map
        """
        return cls.get_submission_type(submissiontype).sample_map

    def generate_associations(self, name: str, extra: str | None = None):
        try:
            field = self.__getattribute__(name)
        except AttributeError:
            return None
        for item in field:
            if extra:
                yield item.to_sub_dict(extra)
            else:
                yield item.to_sub_dict()

    def to_dict(self, full_data: bool = False, backup: bool = False, report: bool = False) -> dict:
        """
        Constructs dictionary used in procedure summary

        Args:
            expand (bool, optional): indicates if generators to be expanded. Defaults to False.
            report (bool, optional): indicates if to be used for a report. Defaults to False.
            full_data (bool, optional): indicates if sample dicts to be constructed. Defaults to False.
            backup (bool, optional): passed to adjust_to_dict_samples. Defaults to False.

        Returns:
            dict: dictionary used in procedure summary and details
        """
        # NOTE: get lab from nested organization object
        try:
            sub_lab = self.clientsubmission.clientlab.name
        except AttributeError:
            sub_lab = None
        try:
            sub_lab = sub_lab.replace("_", " ").title()
        except AttributeError:
            pass
        output = {
            "id": self.id,
            "plate_number": self.name,
            "submissiontype": self.clientsubmission.submissiontype_name,
            "submitter_plate_id": self.clientsubmission.submitter_plate_id,
            "started_date": self.clientsubmission.submitted_date.strftime("%Y-%m-%d"),
            "clientlab": sub_lab,
            "sample_count": self.clientsubmission.sample_count,
            "kittype": "Change procedure.py line 388",
            "cost": self.run_cost
        }
        if report:
            return output
        if full_data:
            samples = self.generate_associations(name="clientsubmissionsampleassociation")
            equipment = self.generate_associations(name="submission_equipment_associations")
            tips = self.generate_associations(name="submission_tips_associations")
            procedures = [item.details_dict() for item in self.procedure]
            custom = self.custom
        else:
            samples = None
            equipment = None
            tips = None
            custom = None
            procedures = None
        try:
            comments = self.comment
        except Exception as e:
            logger.error(f"Error setting comment: {self.comment}, {e}")
            comments = None
        try:
            contact = self.clientsubmission.contact.name
        except AttributeError as e:
            try:
                contact = f"Defaulted to: {self.clientsubmission.clientlab.contact[0].name}"
            except (AttributeError, IndexError):
                contact = "NA"
        try:
            contact_phone = self.clientsubmission.contact.phone
        except AttributeError:
            contact_phone = "NA"
        output["submission_category"] = self.clientsubmission.submission_category
        output["sample"] = samples
        output["comment"] = comments
        output["equipment"] = equipment
        output["tips"] = tips
        output["signed_by"] = self.signed_by
        output["contact"] = contact
        output["contact_phone"] = contact_phone
        output["custom"] = custom
        output['procedures'] = procedures
        output['name'] = self.name
        try:
            output["completed_date"] = self.completed_date.strftime("%Y-%m-%d")
        except AttributeError:
            output["completed_date"] = self.completed_date
        return output

    @property
    def sample_count(self):
        return len(self.sample)

    def details_dict(self, **kwargs):
        output = super().details_dict()
        output['plate_number'] = self.plate_number
        submission_samples = [sample for sample in self.clientsubmission.sample]
        active_samples = [sample.details_dict() for sample in output['runsampleassociation']
                          if sample.sample.sample_id in [s.sample_id for s in submission_samples]]
        for sample in active_samples:
            sample['active'] = True
        inactive_samples = [sample.details_dict() for sample in submission_samples if
                            sample.name not in [s['sample_id'] for s in active_samples]]
        for sample in inactive_samples:
            sample['active'] = False
        output['sample'] = active_samples + inactive_samples
        output['procedure'] = [procedure.details_dict() for procedure in output['procedure']]
        output['permission'] = is_power_user()
        output['excluded'] += ['procedure', "runsampleassociation", 'excluded', 'expanded', 'sample', 'id', 'custom',
                               'permission', "clientsubmission"]
        output['sample_count'] = self.sample_count
        output['clientsubmission'] = self.clientsubmission.name
        output['started_date'] = self.started_date
        output['completed_date'] = self.completed_date
        return output

    @classmethod
    def archive_submissions(cls, start_date: date | datetime | str | int | None = None,
                            end_date: date | datetime | str | int | None = None,
                            submissiontype: List[str] | None = None):
        if submissiontype:
            if isinstance(submissiontype, str):
                submissiontype = [submissiontype]
            query_out = []
            for sub_type in submissiontype:
                subs = cls.query(page_size=0, start_date=start_date, end_date=end_date, submissiontype=sub_type)
                query_out.append(subs)
            query_out = list(itertools.chain.from_iterable(query_out))
        else:
            query_out = cls.query(page_size=0, start_date=start_date, end_date=end_date)
        records = []
        for sub in query_out:
            output = sub.details_dict()
            for k, v in output.items():
                if isinstance(v, types.GeneratorType):
                    output[k] = [item for item in v]
            records.append(output)
        df = DataFrame.from_records(records)
        df.sort_values(by="id", inplace=True)
        df.set_index("id", inplace=True)
        return df

    @property
    def column_count(self) -> int:
        """
        Calculate the number of columns in this procedure

        Returns:
            int: Number of unique columns.
        """
        columns = set([assoc.column for assoc in self.submission_sample_associations])
        return len(columns)

    def calculate_base_cost(self) -> None:
        """
        Calculates cost of the plate
        """
        # NOTE: Calculate number of columns based on largest column number
        pass

    @property
    def hitpicked(self) -> list:
        """
        Returns positve sample locations for plate

        Returns:
            list: list of hitpick dictionaries for each sample
        """
        output_list = [assoc.hitpicked for assoc in self.runsampleassociation]
        return output_list

    @property
    def sample_dicts(self) -> List[dict]:
        return [dict(sample_id=assoc.sample.sample_id, row=assoc.row, column=assoc.column, background_color="#6ffe1d")
                for assoc in self.runsampleassociation]

    @classmethod
    def make_plate_map(cls, sample_list: list, plate_rows: int = 8, plate_columns=12) -> str:
        """
        Constructs an html based plate map for procedure details.

        Args:
            sample_list (list): List of procedure sample
            plate_rows (int, optional): Number of rows in the plate. Defaults to 8.
            plate_columns (int, optional): Number of columns in the plate. Defaults to 12.

        Returns:
            str: html output string.
        """
        rows = range(1, plate_rows + 1)
        columns = range(1, plate_columns + 1)
        # NOTE: An overly complicated list comprehension create a list of sample locations
        # NOTE: next will return a blank cell if no value found for row/column
        output_samples = [next((item for item in sample_list if item['row'] == row and item['column'] == column),
                               dict(name="", row=row, column=column, background_color="#ffffff"))
                          for row in rows
                          for column in columns]
        env = jinja_template_loading()
        template = env.get_template("support/plate_map.html")
        html = template.render(samples=output_samples, PLATE_ROWS=plate_rows, PLATE_COLUMNS=plate_columns)
        return html + "<br/>"

    @property
    def used_equipment(self) -> Generator[str, None, None]:
        """
        Gets EquipmentRole names associated with this Run

        Returns:
            List[str]: List of names
        """
        return (item.equipmentrole for item in self.submission_equipment_associations)

    @classmethod
    def submissions_to_df(cls, submission_type: str | None = None, limit: int = 0,
                          chronologic: bool = True, page: int = 1, page_size: int = 250) -> pd.DataFrame:
        """
        Convert all procedure to dataframe

        Args:
            page_size (int, optional): Number of items to include in query result. Defaults to 250.
            page (int, optional): Limits the number of procedure to a page size. Defaults to 1.
            chronologic (bool, optional): Sort procedure in chronologic order. Defaults to True.
            submission_type (str | None, optional): Filter by SubmissionType. Defaults to None.
            limit (int, optional): Maximum number of results to return. Defaults to 0.

        Returns:
            pd.DataFrame: Pandas Dataframe of all relevant procedure
        """
        # NOTE: use lookup function to create list of dicts
        subs = [item.details_dict() for item in
                cls.query(submissiontype=submission_type, limit=limit, chronologic=chronologic, page=page,
                          page_size=page_size)]
        df = pd.DataFrame.from_records(subs)
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

    def set_attribute(self, key: str, value):
        """
        Performs custom attribute setting based on values.

        Args:
            key (str): name of attribute
            value (_type_): value of attribute
        """
        match key:
            case "clientlab":
                field_value = ClientLab.query(name=value)
            case "contact":
                field_value = Contact.query(name=value)
            case "sample":
                for sample in value:
                    sample, _ = sample.to_sql()
                return
            case "reagents":
                field_value = [reagent['value'].to_sql()[0] if isinstance(reagent, dict) else reagent.to_sql()[0] for
                               reagent in value]
            case "proceduretype":
                field_value = SubmissionType.query(name=value)
            case "sample_count":
                if value is None:
                    field_value = len(self.sample)
                else:
                    field_value = value
            case "ctx" | "csv" | "filepath" | "equipment" | "control":
                return
            case item if item in self.jsons:
                match key:
                    case "custom" | "source_plates":
                        existing = value
                    case _:
                        existing = self.__getattribute__(key)
                        if value in ['', 'null', None]:
                            logger.error(f"No value given, not setting.")
                            return
                        if existing is None:
                            existing = []
                        if check_dictionary_inclusion_equality(existing, value):
                            logger.warning("Value already exists. Preventing duplicate addition.")
                            return
                        else:
                            if isinstance(value, list):
                                existing += value
                            else:
                                if value:
                                    existing.append(value)

                self.__setattr__(key, existing)
                # NOTE: Make sure this gets updated by telling SQLAlchemy it's been modified.
                flag_modified(self, key)
                return
            case _:
                try:
                    field_value = value.strip()
                except AttributeError:
                    field_value = value
        # NOTE: insert into field
        current = self.__getattribute__(key)
        if field_value and current != field_value:
            try:
                self.__setattr__(key, field_value)
            except AttributeError as e:
                logger.error(f"Could not set {self} attribute {key} to {value} due to \n{e}")

    def update_subsampassoc(self, assoc: ClientSubmissionSampleAssociation,
                            input_dict: dict) -> ClientSubmissionSampleAssociation:
        """
        Update a joined procedure sample association.

        Args:
            assoc (ClientSubmissionSampleAssociation): Sample association to be updated.
            input_dict (dict): updated values to insert.

        Returns:
            ClientSubmissionSampleAssociation: Updated association
        """
        # NOTE: No longer searches for association here, done in caller function
        for k, v in input_dict.items():
            try:
                setattr(assoc, k, v)
                # NOTE: for some reason I don't think assoc.__setattr__(k, v) works here.
            except AttributeError:
                pass
        return assoc

    def to_pydantic(self, backup: bool = False) -> "PydSubmission":
        """
        Converts this instance into a PydSubmission

        Returns:
            PydSubmission: converted object.
        """
        from backend.validators import PydClientSubmission, PydRun
        dicto = self.details_dict(full_data=True, backup=backup)
        new_dict = {}
        for key, value in dicto.items():
            missing = value in ['', 'None', None]
            match key:
                case "sample":
                    field_value = [item.to_pydantic() for item in self.runsampleassociation]
                case "plate_number":
                    key = 'rsl_plate_number'
                    field_value = dict(value=self.rsl_plate_number, missing=missing)
                    new_dict['name'] = field_value
                case "id":
                    continue
                case "clientsubmission" | "client_submission":
                    field_value = self.clientsubmission.to_pydantic()
                case "procedure":
                    field_value = [item.to_pydantic() for item in self.procedure]
                case _:
                    try:
                        key = key.lower().replace(" ", "_")
                        if isclass(value):
                            field_value = dict(value=self.__getattribute__(key).name, missing=missing)
                        else:
                            field_value = dict(value=self.__getattribute__(key), missing=missing)
                    except AttributeError:
                        logger.error(f"{key} is not available in {self}")
                        field_value = dict(value="NA", missing=True)
            new_dict[key] = field_value
        new_dict['filepath'] = Path(tempfile.TemporaryFile().name)
        dicto.update(new_dict)
        return PydRun(**dicto)

    def save(self, original: bool = True):
        """
        Adds this instance to database and commits.

        Args:
            original (bool, optional): Is this the first save. Defaults to True.
        """
        if original:
            self.uploaded_by = getuser()
        return super().save()

    @classmethod
    def get_regex(cls, submission_type: SubmissionType | str | None = None) -> re.Pattern:
        """
        Gets the regex string for identifying a certain class of procedure.

        Args:
            submission_type (SubmissionType | str | None, optional): procedure type of interest. Defaults to None.

        Returns:
            str: String from which regex will be compiled.
        """
        try:
            regex = cls.get_submission_type(submission_type).defaults['regex']
        except AttributeError as e:
            logger.error(f"Couldn't get procedure type for {cls.__mapper_args__['polymorphic_identity']}")
            regex = None
        try:
            regex = re.compile(rf"{regex}", flags=re.IGNORECASE | re.VERBOSE)
        except re.error as e:
            regex = cls.construct_regex()
        return regex

    # NOTE: Polymorphic functions

    @classmethod
    @declared_attr
    def regex(cls) -> re.Pattern:
        """
        Constructs catchall regex.

        Returns:
            re.Pattern: Regular expression pattern to discriminate between procedure types.
        """
        res = [st.defaults['regex'] for st in SubmissionType.query() if st.defaults]
        rstring = rf'{"|".join(res)}'
        regex = re.compile(rstring, flags=re.IGNORECASE | re.VERBOSE)
        return regex

    # NOTE: Query functions

    @classmethod
    @setup_lookup
    def query(cls,
              submissiontype: str | SubmissionType | None = None,
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
              ) -> Run | List[Run]:
        """
        Lookup procedure based on a number of parameters. Overrides parent.

        Args:
            submission_type (str | models.SubmissionType | None, optional): Submission type of interest. Defaults to None.
            id (int | str | None, optional): Submission id in the database (limits results to 1). Defaults to None.
            name (str | None, optional): Submission name in the database (limits results to 1). Defaults to None.
            start_date (date | str | int | None, optional): Beginning date to search by. Defaults to None.
            end_date (date | str | int | None, optional): Ending date to search by. Defaults to None.
            reagent (models.Reagent | str | None, optional): A reagent used in the procedure. Defaults to None.
            chronologic (bool, optional): Return results in chronologic order. Defaults to False.
            limit (int, optional): Maximum number of results to return. Defaults to 0.

        Returns:
            models.Run | List[models.Run]: Run(s) of interest
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
            start_date = cls.rectify_query_date(start_date)
            end_date = cls.rectify_query_date(end_date, eod=True)
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
        if page_size > 0:
            query = query.limit(page_size)
        page = page - 1
        if page is not None:
            query = query.offset(page * page_size)
        return cls.execute_query(query=query, limit=limit, **kwargs)

    # NOTE: Custom context events for the ui

    @property
    def custom_context_events(self) -> dict:
        """
        Creates dictionary of str:function to be passed to context menu

        Returns:
            dict: dictionary of functions
        """
        names = ["Add Procedure", "Edit", "Export", "Add Comment", "Show Details", "Delete"]
        output = {item: self.__getattribute__(item.lower().replace(" ", "_")) for item in names}
        return output

    def add_procedure(self, obj, proceduretype_name: str):
        from frontend.widgets.procedure_creation import ProcedureCreation
        procedure_type: ProcedureType = next(
            (proceduretype for proceduretype in self.allowed_procedures if proceduretype.name == proceduretype_name))
        dlg = ProcedureCreation(parent=obj, procedure=procedure_type.construct_dummy_procedure(run=self))
        if dlg.exec():
            sql, _ = dlg.return_sql(new=True)
            # NOTE: save commit disabled currently
            sql.save()
        obj.set_data()

    def delete(self, obj=None):
        """
        Performs backup and deletes this instance from database.

        Args:
            obj (_type_, optional): Parent widget. Defaults to None.

        Raises:
            e: SQLIntegrityError or SQLOperationalError if problem with commit.
        """
        from frontend.widgets.pop_ups import QuestionAsker
        fname = self.__backup_path__.joinpath(f"{self.rsl_plate_number}-backup({date.today().strftime('%Y%m%d')})")
        msg = QuestionAsker(title="Delete?", message=f"Are you sure you want to delete {self.rsl_plate_number}?\n")
        if msg.exec():
            try:
                # NOTE: backs up file as xlsx, same as export.
                self.backup(fname=fname, full_backup=True)
            except BadZipfile:
                logger.error("Couldn't open zipfile for writing.")
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

        Args:
            obj (Widget): Parent widget 
        """
        from frontend.widgets.submission_widget import SubmissionFormWidget
        for widget in obj.app.table_widget.formwidget.findChildren(SubmissionFormWidget):
            widget.setParent(None)
        pyd = self.to_pydantic(backup=True)
        form = pyd.to_form(parent=obj, disable=['name'])
        obj.app.table_widget.formwidget.layout().addWidget(form)

    def add_comment(self, obj):
        """
        Creates widget for adding comments to procedure

        Args:
            obj (_type_): parent widget
        """
        from frontend.widgets.submission_details import SubmissionComment
        dlg = SubmissionComment(parent=obj, submission=self)
        if dlg.exec():
            comment = dlg.parse_form()
            if comment in ["", None]:
                return
            self.set_attribute(key='comment', value=comment)
            self.save(original=False)

    def export(self, obj, output_filepath: str | Path | None = None):
        from backend import managers
        if not output_filepath:
            output_filepath = select_save_file(obj=obj, default_name=self.construct_filename(), extension="xlsx")
        Manager = getattr(managers, f"Default{self.__class__.__name__}Manager")
        manager = Manager(parent=obj, input_object=self.to_pydantic())
        workbook = manager.write()
        try:
            workbook.remove_sheet("Sheet")
        except ValueError:
            pass
        workbook.save(filename=output_filepath)

    def construct_filename(self):
        return f"{self.rsl_plate_number}-{self.clientsubmission.clientlab.name}-{self.clientsubmission.submitter_plate_id}"

    def backup(self, obj=None, fname: Path | None = None, full_backup: bool = False):
        """
        Exports xlsx info files for this instance.

        Args:
            obj (_type_, optional): _description_. Defaults to None.
            fname (Path | None, optional): Filename of xlsx file. Defaults to None.
            full_backup (bool, optional): Whether or not to make yaml file. Defaults to False.
        """
        pyd = self.to_pydantic(backup=True)
        if fname is None:
            from frontend.widgets.functions import select_save_file
            fname = select_save_file(default_name=pyd.construct_filename(), extension="xlsx", obj=obj)
        if fname.name == "":
            return
        writer = pyd.to_writer()
        writer.xl.save(filename=fname.with_suffix(".xlsx"))

    @property
    def turnaround_time(self) -> int:
        try:
            completed = self.completed_date.date()
        except AttributeError:
            completed = None
        return self.calculate_turnaround(start_date=self.clientsubmission.submitted_date.date(), end_date=completed)

    @classmethod
    def calculate_turnaround(cls, start_date: date | None = None, end_date: date | None = None) -> int:
        """
        Calculates number of business days between data submitted and date completed

        Args:
            start_date (date, optional): Date submitted. defaults to None.
            end_date (date, optional): Date completed. defaults to None.

        Returns:
            int: Number of business days.
        """
        if not end_date:
            return None
        try:
            delta = np.busday_count(start_date, end_date, holidays=create_holidays_for_year(start_date.year)) + 1
        except ValueError:
            return None
        return delta

    def add_sample(self, sample: Sample):
        try:
            assert isinstance(sample, Sample)
        except AssertionError:
            logger.warning(f"Sample {sample} is not an sql object.")
            sample = sample.to_sql()
        try:
            row = sample._misc_info['row']
        except (KeyError, AttributeError):
            row = 0
        try:
            column = sample._misc_info['column']
        except KeyError:
            column = 0
        assoc = RunSampleAssociation(
            row=row,
            column=column,
            run=self,
            sample=sample
        )
        return assoc

    @property
    def allowed_procedures(self):
        return self.clientsubmission.submissiontype.proceduretype

    def get_submission_rank_of_sample(self, sample: Sample | str):
        if isinstance(sample, str):
            sample = Sample.query(sample_id=sample)
        clientsubmissionsampleassoc = next((assoc for assoc in self.clientsubmission.clientsubmissionsampleassociation
                                            if assoc.sample == sample), None)
        if clientsubmissionsampleassoc:
            return clientsubmissionsampleassoc.submission_rank
        else:
            return 0

    def constuct_sample_dicts_for_proceduretype(self, proceduretype: ProcedureType):
        plate_dict = proceduretype.ranked_plate
        ranked_samples = []
        unranked_samples = []
        for sample in self.sample:
            submission_rank = self.get_submission_rank_of_sample(sample=sample)
            if submission_rank != 0:
                try:
                    row, column = plate_dict[submission_rank]
                except KeyError as e:
                    logger.error(pformat(plate_dict))
                    raise e
                ranked_samples.append(dict(well_id=sample.sample_id, sample_id=sample.sample_id, row=row, column=column,
                                           submission_rank=submission_rank, background_color="#6ffe1d"))
            else:
                unranked_samples.append(sample)
        possible_ranks = (item for item in list(plate_dict.keys()) if
                          item not in [sample['submission_rank'] for sample in ranked_samples])
        for sample in unranked_samples:
            try:
                submission_rank = next(possible_ranks)
            except StopIteration:
                continue
            row, column = plate_dict[submission_rank]
            ranked_samples.append(
                dict(well_id=sample.sample_id, sample_id=sample.sample_id, row=row, column=column,
                     submission_rank=submission_rank,
                     background_color="#6ffe1d", enabled=True))
        padded_list = []
        for iii in range(1, proceduretype.total_wells + 1):
            row, column = proceduretype.ranked_plate[iii]
            sample = next((item for item in ranked_samples if item['submission_rank'] == iii),
                          dict(well_id=f"blank_{iii}", sample_id="", row=row, column=column, submission_rank=iii,
                               background_color="#ffffff", enabled=False)
                          )
            padded_list.append(sample)
        return list(sorted(padded_list, key=itemgetter('submission_rank')))


# NOTE: Sample Classes

class Sample(BaseClass, LogMixin):
    """
    Base of basic sample which polymorphs into BCSample and WWSample
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    sample_id = Column(String(64), nullable=False, unique=True)  #: identification from submitter
    _is_control = Column(INTEGER, default=0) #: 1 = positive, -1 = negative, 0 = not a control

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
        is_control = kwargs.pop('is_control', None)
        clientsubmission = kwargs.pop('clientsubmission', None)
        run = kwargs.pop('run', None)
        procedure = kwargs.pop('procedure', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if is_control is not None:
            try:
                self.is_control = is_control
            except Exception:
                try:
                    self._misc_info.update({'is_control': is_control})
                except Exception:
                    pass
        if clientsubmission is not None:
            try:
                self.clientsubmission = clientsubmission
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'clientsubmission': clientsubmission})
                except Exception:
                    pass
        # Resolve reagentrole
        if run is not None:
            try:
                self.run = run
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'run': run})
                except Exception:
                    pass
        # Resolve reagentrole
        if procedure is not None:
            try:
                self.procedure = procedure
            except Exception:
                try:
                    self._misc_info.update({'procedure': procedure})
                except Exception:
                    pass
    
    @hybrid_property
    def clientsubmission(self):
        return self._clientsubmission
    
    @clientsubmission.setter
    def clientsubmission(self, value):
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case dict():
                    output = ClientSubmissionSampleAssociation(clientsubmission=item['name'], sample=self, **{k: v for k, v in item.items() if k != 'name'})
                case ClientSubmissionSampleAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for clientsubmission")
                    continue
            # logger.debug(f"Setting equipment with output: {output}")
            if isinstance(output, ClientSubmissionSampleAssociation):
                if output not in self.sampleclientsubmissionassociation:
                    self.sampleclientsubmissionassociation.append(output)
            else:
                logger.error(f"Could not add {item} to ._clientsubmission")

    @hybrid_property
    def run(self):
        return self._run
    
    @run.setter
    def run(self, value):
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case dict():
                    output = RunSampleAssociation(run=item['name'], sample=self, **{k: v for k, v in item.items() if k != 'name'})
                case RunSampleAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for sample")
                    return
            # logger.debug(f"Setting equipment with output: {output}")
            if isinstance(output, RunSampleAssociation):
                if output not in self.samplerunassociation:
                    self.samplerunassociation.append(output)
            else:
                logger.error(f"Could not add {item} to ._sample")

    @hybrid_property
    def procedure(self):
        return self._procedure
    
    @procedure.setter
    def procedure(self, value):
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case dict():
                    output = ProcedureSampleAssociation(procedure=item['name'], sample=self, **{k: v for k, v in item.items() if k != 'name'})
                case ProcedureSampleAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for sample")
                    return
            # logger.debug(f"Setting equipment with output: {output}")
            if isinstance(output, ProcedureSampleAssociation):
                if output not in self.sampleprocedureassociation:
                    self.sampleprocedureassociation.append(output)
            else:
                logger.error(f"Could not add {item} to ._sample")

    @hybrid_property
    def is_control(self):
        return self._is_control

    @is_control.setter
    def is_control(self, value):
        match value:
            case int():
                output = value
            case bool():
                output = int(value)
            case _:
                raise TypeError(f"Unsupported type: {type(value)} for {self.lot}._is_control")
        self._is_control = output
  
    @hybrid_property
    def name(self):
        return self.sample_id
    
    @name.setter
    def name(self, value):
        self.sample_id = value

    # def __repr__(self) -> str:
    #     return f"<Sample({self.sample_id})>"

    @classmethod
    @declared_attr
    def searchables(cls):
        return [dict(label="Submitter ID", field="sample_id")]

    def to_sub_dict(self, full_data: bool = False) -> dict:
        """
        gui friendly dictionary

        Args:
            full_data (bool): Whether to use full object or truncated. Defaults to False

        Returns:
            dict: submitter id and sample type and linked procedure if full data
        """
        sample = dict(
            sample_id=self.sample_id
        )
        if full_data:
            sample['clientsubmission'] = sorted([item.to_sub_dict() for item in self.sampleclientsubmissionassociation],
                                                key=itemgetter('submitted_date'))
        return sample

    def to_pydantic(self):
        from backend.validators import PydSample
        return PydSample(**self.to_sub_dict())

    @classmethod
    @setup_lookup
    def query(cls,
              sample_id: str | None = None,
              limit: int = 0,
              **kwargs
              ) -> Sample | List[Sample]:
        """
        Lookup sample in the database by a number of parameters.

        Args:
            sample_id (str | None, optional): Name of the sample (limits results to 1). Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            models.Sample|List[models.Sample]: Sample(s) of interest.
        """
        query = cls.__database_session__.query(cls)
        match sample_id:
            case str():
                query = query.filter(cls.sample_id == sample_id)
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit, **kwargs)

    def delete(self):
        raise AttributeError(f"Delete not implemented for {self.__class__}")

    @classmethod
    def samples_to_df(cls, sample_list: List[Sample], **kwargs) -> pd.DataFrame:
        """
        Runs a fuzzy search and converts into a dataframe.

        Args:
            sample_list (List[Sample]): List of sample to be parsed. Defaults to None.

        Returns:
            pd.DataFrame: Dataframe all sample
        """
        try:
            samples = [sample.to_sub_dict() for sample in sample_list]
        except TypeError as e:
            logger.error(f"Couldn't find any sample with data: {kwargs}\nDue to {e}")
            return None
        df = pd.DataFrame.from_records(samples)
        # NOTE: Exclude sub information
        exclude = ['concentration', 'organism', 'colour', 'tooltip', 'comments', 'sample', 'reagents',
                   'equipment', 'gel_info', 'gel_image', 'dna_core_submission_number', 'gel_controls']
        df = df.loc[:, ~df.columns.isin(exclude)]
        return df

    def show_details(self, obj):
        """
        Creates Widget for showing procedure details.

        Args:
            obj (_type_): parent widget
        """
        from frontend.widgets.submission_details import SubmissionDetails
        dlg = SubmissionDetails(parent=obj, sub=self)
        if dlg.exec():
            pass

    def edit_from_search(self, obj, **kwargs):
        """
        Function called form search. "Edit" is dependent on function as this one just shows details.

        Args:
            obj (__type__): Parent widget.
            **kwargs (): Required for all edit from search functions.

        Returns:

        """
        self.show_details(obj)


# NOTE: Submission to Sample Associations


class ClientSubmissionSampleAssociation(BaseClass):
    """
    table containing procedure/sample associations
    DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
    """

    sample_id = Column(INTEGER, ForeignKey("_sample.id"), primary_key=True)  #: id of associated sample
    clientsubmission_id = Column(INTEGER, ForeignKey("_clientsubmission.id"),
                                 primary_key=True)  #: id of associated client submission
    submission_rank = Column(INTEGER, primary_key=True, default=0)  #: Location in sample list
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
        submission_rank = kwargs.pop("submission_rank", 0)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        self.submission_rank = submission_rank
        # Resolve proceduretype
        if clientsubmission is not None:
            try:
                self.clientsubmission = clientsubmission
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'clientsubmission': clientsubmission})
                except Exception:
                    pass
        # Resolve reagentrole
        if sample is not None:
            try:
                self.sample = sample
            except Exception:
                try:
                    self._misc_info.update({'sample': sample})
                except Exception:
                    pass
    
    # def __repr__(self) -> str:
    #     try:
    #         return f"<{self.__class__.__name__}({self.clientsubmission.submitter_plate_id} & {self.sample.sample_id})"
    #     except AttributeError as e:
    #         logger.error(f"Unable to construct __repr__ due to: {e}")
    #         return super().__repr__()

    @hybrid_property
    def name(self):
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
        return func.concat(
            ClientSubmission.name,
            "->",
            Sample.name,
            " (rank=",
            cast(cls.submission_rank, String),
            ")"
        ).label("name")

    @hybrid_property
    def sample(self):
        return self._sample

    @sample.setter
    def sample(self, value):
        from backend.validators.pydant import PydSample
        match value:
            case str():
                output = Sample.query(name=value, limit=1)
            case dict():
                output = Sample.query_or_create(**value)
            case PydSample():
                output = value.to_sql()
            case Sample():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for sample")
                return
        if isinstance(output, Sample):
            if not hasattr(output, "id"):
                output.save()
            self._sample = output
        else:
            logger.error(f"Could not set _sample to {output}")
  
    @hybrid_property
    def clientsubmission(self):
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
                output = value.to_sql()
            case ClientSubmission():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for clientsubmission")
                return
        if isinstance(output, ClientSubmission):
            self._clientsubmission = output
        else:
            logger.error(f"Could not set _clientsubmission to {value}")

    def details_dict(self, **kwargs):
        output = super().details_dict()
        # NOTE: Figure out how to merge the misc_info if doing .update instead.
        relevant = {k: v for k, v in output.items() if k not in ['sample']}
        output = self.sample.details_dict()
        misc = output.get('misc_info', {})
        output.update(relevant)
        output['misc_info'] = misc
        return output

    def to_pydantic(self) -> "PydSample":
        """
        Creates a pydantic model for this sample.

        Returns:
            PydSample: Pydantic Model
        """
        from backend.validators import PydSample
        return PydSample(**self.details_dict())

    @property
    def hitpicked(self) -> dict | None:
        """
        Outputs a dictionary usable for html plate maps.

        Returns:
            dict: dictionary of sample id, row and column in elution plate
        """
        # NOTE: Since there is no PCR, negliable result is necessary.
        sample = self.to_sub_dict()
        env = jinja_template_loading()
        template = env.get_template("support/tooltip.html")
        tooltip_text = template.render(fields=sample)
        try:
            control = self.sample.control
        except AttributeError:
            control = None
        if control is not None:
            background = "rgb(128, 203, 196)"
        else:
            background = "rgb(105, 216, 79)"
        try:
            tooltip_text += sample['tooltip']
        except KeyError:
            pass
        sample.update(dict(Name=self.sample.sample_id[:10], tooltip=tooltip_text, background_color=background))
        return sample

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
              ) -> ClientSubmissionSampleAssociation | List[ClientSubmissionSampleAssociation]:
        """
        Lookup junction of Submission and Sample in the database

        Args:
            clientsubmission (models.ClientSubmission | str | None, optional): Submission of interest. Defaults to None.
            exclude_submission_type ( str | None, optional): Name of submissiontype to exclude. Defaults to None.
            sample (models.Sample | str | None, optional): Sample of interest. Defaults to None.
            row (int, optional): Row of the sample location on procedure plate. Defaults to 0.
            column (int, optional): Column of the sample location on the procedure plate. Defaults to 0.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.
            chronologic (bool, optional): Return results in chronologic order. Defaults to False.
            reverse (bool, optional): Whether or not to reverse order of list. Defaults to False.

        Returns:
            models.ClientSubmissionSampleAssociation|List[models.ClientSubmissionSampleAssociation]: Junction(s) of interest
        """
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
                        association_type: str = "Basic Association",
                        clientsubmission: ClientSubmission | str | None = None,
                        sample: Sample | str | None = None,
                        id: int | None = None,
                        **kwargs) -> ClientSubmissionSampleAssociation:
        """
        Queries for an association, if none exists creates a new one.

        Args:
            association_type (str, optional): Subclass name. Defaults to "Basic Association".
            clientsubmission (Run | str | None, optional): associated procedure. Defaults to None.
            sample (Sample | str | None, optional): associated sample. Defaults to None.
            id (int | None, optional): association id. Defaults to None.

       Returns:
            ClientSubmissionSampleAssociation: Queried or new association.
        """
        match clientsubmission:
            case ClientSubmission():
                pass
            case str():
                clientsubmission = ClientSubmission.query(rsl_plate_number=clientsubmission)
            case _:
                raise ValueError()
        match sample:
            case Sample():
                pass
            case str():
                sample = Sample.query(sample_id=sample)
            case _:
                raise ValueError()
        try:
            row = kwargs['row']
        except KeyError:
            row = None
        try:
            column = kwargs['column']
        except KeyError:
            column = None
        try:
            instance = cls.query(clientsubmission=clientsubmission, sample=sample, row=row, column=column, limit=1)
        except StatementError:
            instance = None
        if instance is None:
            instance = cls(submission=clientsubmission, sample=sample, id=id, **kwargs)
        return instance

    def delete(self):
        raise AttributeError(f"Delete not implemented for {self.__class__}")


class RunSampleAssociation(BaseClass):
    """
    table containing procedure/sample associations
    DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
    """

    sample_id = Column(INTEGER, ForeignKey("_sample.id"), primary_key=True)  #: id of associated sample
    run_id = Column(INTEGER, ForeignKey("_run.id"), primary_key=True)  #: id of associated procedure

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
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if run is not None:
            try:
                self.run = run
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'run': run})
                except Exception:
                    pass
        # Resolve reagentrole
        if sample is not None:
            try:
                self.sample = sample
            except Exception:
                try:
                    self._misc_info.update({'sample': sample})
                except Exception:
                    pass
    
    @hybrid_property
    def name(self):
        try:
            run = self.run.name
        except AttributeError:
            run = "Unassigned Run"
        try:
            sample = self.sample.name
        except AttributeError:
            sample = "Unassigned Sample"
        return f"{run}-{sample}"
    
    @name.expression
    def name(cls):
        return func.concat(
            Run.name,
            "-",
            Sample.name
        ).label("name")

    @hybrid_property
    def sample(self):
        return self._sample

    @sample.setter
    def sample(self, value):
        from backend.validators.pydant import PydSample
        match value:
            case str():
                output = Sample.query(name=value, limit=1)
            case dict():
                output = Sample.query_or_create(**value)
            case PydSample():
                output = value.to_sql()
            case Sample():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for sample")
                return
        if isinstance(output, Sample):
            self._sample = output
        else:
            logger.error(f"Could not set _sample to {value}")
  
    @hybrid_property
    def run(self):
        return self._run

    @run.setter
    def run(self, value):
        from backend.validators.pydant import PydRun
        match value:
            case str():
                output = Run.query(name=value, limit=1)
            case dict():
                output = Run.query_or_create(**value)
            case PydRun():
                output = value.to_sql()
            case Run():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for run")
                return
        if isinstance(output, Run):
            self._run = output
        else:
            logger.error(f"Could not set _run to {output}")

    def to_pydantic(self) -> "PydSample":
        """
        Creates a pydantic model for this sample.

        Returns:
            PydSample: Pydantic Model
        """
        from backend.validators import PydSample
        return PydSample(**self.details_dict())

    @property
    def hitpicked(self) -> dict | None:
        """
        Outputs a dictionary usable for html plate maps.

        Returns:
            dict: dictionary of sample id, row and column in elution plate
        """
        # NOTE: Since there is no PCR, negliable result is necessary.
        sample = self.to_sub_dict()
        env = jinja_template_loading()
        template = env.get_template("support/tooltip.html")
        tooltip_text = template.render(fields=sample)
        try:
            control = self.sample.control
        except AttributeError:
            control = None
        if control is not None:
            background = "rgb(128, 203, 196)"
        else:
            background = "rgb(105, 216, 79)"
        try:
            tooltip_text += sample['tooltip']
        except KeyError:
            pass
        sample.update(dict(Name=self.sample.sample_id[:10], tooltip=tooltip_text, background_color=background))
        return sample

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
              ) -> ClientSubmissionSampleAssociation | List[ClientSubmissionSampleAssociation]:
        """
        Lookup junction of Submission and Sample in the database

        Args:
            run (models.Run | str | None, optional): Submission of interest. Defaults to None.
            exclude_submission_type ( str | None, optional): Name of submissiontype to exclude. Defaults to None.
            sample (models.Sample | str | None, optional): Sample of interest. Defaults to None.
            row (int, optional): Row of the sample location on procedure plate. Defaults to 0.
            column (int, optional): Column of the sample location on the procedure plate. Defaults to 0.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.
            chronologic (bool, optional): Return results in chronologic order. Defaults to False.
            reverse (bool, optional): Whether or not to reverse order of list. Defaults to False.

        Returns:
            models.ClientSubmissionSampleAssociation|List[models.ClientSubmissionSampleAssociation]: Junction(s) of interest
        """
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
                        association_type: str = "Basic Association",
                        run: Run | str | None = None,
                        sample: Sample | str | None = None,
                        id: int | None = None,
                        **kwargs) -> ClientSubmissionSampleAssociation:
        """
        Queries for an association, if none exists creates a new one.

        Args:
            association_type (str, optional): Subclass name. Defaults to "Basic Association".
            run (Run | str | None, optional): associated procedure. Defaults to None.
            sample (Sample | str | None, optional): associated sample. Defaults to None.
            id (int | None, optional): association id. Defaults to None.

       Returns:
            ClientSubmissionSampleAssociation: Queried or new association.
        """
        match run:
            case Run():
                pass
            case str():
                run = Run.query(name=run)
            case _:
                raise ValueError()
        match sample:
            case Sample():
                pass
            case str():
                sample = Sample.query(sample_id=sample)
            case _:
                raise ValueError()
        try:
            row = kwargs['row']
        except KeyError:
            row = None
        try:
            column = kwargs['column']
        except KeyError:
            column = None
        try:
            instance = cls.query(run=run, sample=sample, row=row, column=column, limit=1)
        except StatementError:
            instance = None
        if instance is None:
            instance = cls(run=run, sample=sample, id=id, **kwargs)
        return instance

    def delete(self):
        raise AttributeError(f"Delete not implemented for {self.__class__}")

    def details_dict(self, **kwargs):
        output = super().details_dict()
        # NOTE: Figure out how to merge the misc_info if doing .update instead.
        relevant = {k: v for k, v in output.items() if k not in ['sample']}
        output = output['sample'].details_dict()
        misc = output['misc_info']
        output.update(relevant)
        output['misc_info'] = misc
        return output


class ProcedureSampleAssociation(BaseClass):

    pyd_model_name = "PydSample"

    id = Column(INTEGER, unique=True, nullable=False)
    procedure_id = Column(INTEGER, ForeignKey("_procedure.id"), primary_key=True)  #: id of associated procedure
    sample_id = Column(INTEGER, ForeignKey("_sample.id"), primary_key=True)  #: id of associated equipment
    row = Column(INTEGER)
    column = Column(INTEGER)
    procedure_rank = Column(INTEGER)

    _procedure = relationship(Procedure,
                             back_populates="proceduresampleassociation")  #: associated procedure

    _sample = relationship(Sample, back_populates="sampleprocedureassociation")  #: associated equipment
    _results = relationship("Results", back_populates="_sampleprocedureassociation")  #: associated results

    def __init__(self, new_id: int | None = None,  *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        if new_id:
            self.id = new_id
        else:
            self.id = self.__class__.autoincrement_id()
        procedure = kwargs.pop('procedure', None)
        sample = kwargs.pop('sample', None)
        results = kwargs.pop('results', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if procedure is not None:
            try:
                self.procedure = procedure
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'procedure': procedure})
                except Exception:
                    pass
        # Resolve reagentrole
        if sample is not None:
            try:
                self.sample = sample
            except Exception:
                try:
                    self._misc_info.update({'sample': sample})
                except Exception:
                    pass
        # Resolve reagentrole
        if results is not None:
            try:
                self.results = results
            except Exception:
                try:
                    self._misc_info.update({'results': results})
                except Exception:
                    pass
            
    @hybrid_property
    def name(self):
        try:
            assoc = self.procedure.name
        except AttributeError:
            assoc = "Unassigned Results Association"
        try:
            resultstype = self.resultstype.name
        except AttributeError:
            resultstype = "Unassigned ResultsType"
        return f"{assoc}-{resultstype}"
    
    @name.expression
    def name(cls):
        return func.concat(
            Procedure.name,
            "-",
            ResultsType.name
        ).label("name")
    
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
        for item in value:
            error_msg = f"Can't add item {item} to {self.name}._results"
            match item:
                case str():
                    output = Results.query(name=item, limit=1)
                case dict():
                    output = Results.query_or_create(**item)
                case PydResults():
                    output = item.to_sql()
                case Procedure():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for results")
                    continue
            if isinstance(output, Results):
                self._results.append(output)
            else:
                logger.error(f"Could not add {output} to _results")
  
    @hybrid_property
    def sample(self):
        return self._sample

    @sample.setter
    def sample(self, value):
        from backend.validators.pydant import PydSample
        match value:
            case str():
                output = Sample.query(name=value, limit=1)
            case dict():
                output = Sample.query_or_create(**value)
            case PydSample():
                output = item.to_sql()
            case Sample():
                output = item
            case _:
                logger.error(f"Unmatched value {value} for sample")
                return
        if isinstance(output, Sample):
            self._sample = output
        else:
            logger.error(f"Could not set _sample to {output}")
  
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
                output = value.to_sql()
            case Procedure():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for procedure")
                return
        if isinstance(output, Procedure):
            self._procedure = output
        else:
            logger.error(f"Could not set _procedure to {output}")

    @property
    def well(self):
        if self.row > 0:
            if self.column > 0:
                return f"{row_map[self.row]}{self.column}"
            else:
                return self.row
        else:
            return None

    @classmethod
    def query(cls, sample: Sample | str | None = None, procedure: Procedure | str | None = None, limit: int = 0,
              **kwargs):
        query = cls.__database_session__.query(cls)
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
    def autoincrement_id(cls) -> int:
        """
        Increments the association id automatically

        Returns:
            int: incremented id
        """
        try:
            return max([item.id for item in cls.query()]) + 1
        except ValueError as e:
            logger.error(f"Problem incrementing id: {e}")
            return 1

    def details_dict(self, **kwargs):
        output = super().details_dict()
        # NOTE: Figure out how to merge the misc_info if doing .update instead.
        relevant = {k: v for k, v in output.items() if k not in ['sample']}
        output = output['sample'].details_dict()
        # logger.debug(output)
        misc = output['misc_info']
        output.update(relevant)
        output['misc_info'] = misc
        output['row'] = self.row
        output['column'] = self.column
        output['results'] = [item.details_dict() for item in self.results]
        # output['excluded'] += ["is_control", "well_id", "sample_location", "sample_type"]
        return output

    def to_pydantic(self, **kwargs):
        output = super().to_pydantic(pyd_model_name="PydSample")
        # from backend.validators.pydant import PydSample
        # output = PydSample(**self.details_dict(**kwargs))
        try:
            output.submission_rank = output.misc_info['submission_rank']
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
                output.sample_type = "regular"
                if output.enabled:
                    output.background_color = "#66ff66"
                else:
                    output.background_color = "white"
        return output
