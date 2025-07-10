"""
Models for the main procedure and sample types.
"""
from __future__ import annotations

import itertools
import pickle
from copy import deepcopy
from getpass import getuser
import logging, uuid, tempfile, re, base64, numpy as np, pandas as pd, types, sys
from inspect import isclass
from io import BytesIO
from zipfile import ZipFile, BadZipfile
from tempfile import TemporaryDirectory, TemporaryFile
from operator import itemgetter
from pprint import pformat

import openpyxl
from pandas import DataFrame
from sqlalchemy.ext.hybrid import hybrid_property

from frontend.widgets.functions import select_save_file
from . import Base, BaseClass, Reagent, SubmissionType, KitType, ClientLab, Contact, LogMixin, Procedure, \
    kittype_procedure

from sqlalchemy import Column, String, TIMESTAMP, INTEGER, ForeignKey, JSON, FLOAT, case, func, Table, Sequence
from sqlalchemy.orm import relationship, validates, Query
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.exc import OperationalError as AlcOperationalError, IntegrityError as AlcIntegrityError, StatementError, \
    ArgumentError
from sqlite3 import OperationalError as SQLOperationalError, IntegrityError as SQLIntegrityError
from openpyxl import Workbook
from openpyxl.drawing.image import Image as OpenpyxlImage
from tools import row_map, setup_lookup, jinja_template_loading, rreplace, row_keys, check_key_or_attr, Result, Report, \
    report_result, create_holidays_for_year, check_dictionary_inclusion_equality, is_power_user
from datetime import datetime, date
from typing import List, Any, Tuple, Literal, Generator, Type, TYPE_CHECKING
from pathlib import Path
from jinja2.exceptions import TemplateNotFound
from jinja2 import Template
from PIL import Image

if TYPE_CHECKING:
    from backend.db.models.kits import ProcedureType, Procedure

logger = logging.getLogger(f"submissions.{__name__}")


class ClientSubmission(BaseClass, LogMixin):
    """
    Object for the client procedure from which all procedure objects will be created.
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    submitter_plate_id = Column(String(127), unique=True)  #: The number given to the procedure by the submitting lab
    submitted_date = Column(TIMESTAMP)  #: Date procedure received
    clientlab = relationship("ClientLab", back_populates="clientsubmission")  #: client org
    clientlab_id = Column(INTEGER, ForeignKey("_clientlab.id", ondelete="SET NULL",
                                              name="fk_BS_sublab_id"))  #: client lab id from _organizations
    submission_category = Column(String(64))
    sample_count = Column(INTEGER)  #: Number of sample in the procedure
    comment = Column(JSON)
    run = relationship("Run", back_populates="clientsubmission")  #: many-to-one relationship
    contact = relationship("Contact", back_populates="clientsubmission")  #: client org
    contact_id = Column(INTEGER, ForeignKey("_contact.id", ondelete="SET NULL",
                                            name="fk_BS_contact_id"))  #: client lab id from _organizations
    submissiontype_name = Column(String, ForeignKey("_submissiontype.name", ondelete="SET NULL",
                                                    name="fk_BS_subtype_name"))  #: name of joined procedure type
    submissiontype = relationship("SubmissionType", back_populates="clientsubmission")  #: archetype of this procedure
    cost_centre = Column(
        String(64))  #: Permanent storage of used cost centre in case organization field changed in the future.

    clientsubmissionsampleassociation = relationship(
        "ClientSubmissionSampleAssociation",
        back_populates="clientsubmission",
        cascade="all, delete-orphan",
    )  #: Relation to ClientSubmissionSampleAssociation

    sample = association_proxy("clientsubmissionsampleassociation",
                               "sample")  #, creator=lambda sample: ClientSubmissionSampleAssociation(

    # sample=sample))  #: Association proxy to ClientSubmissionSampleAssociation.sample

    @hybrid_property
    def name(self):
        return self.submitter_plate_id

    @classmethod
    @setup_lookup
    def query(cls,
              submissiontype: str | SubmissionType | None = None,
              submissiontype_name: str | None = None,
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
            submission_type (str | models.SubmissionType | None, optional): Submission type of interest. Defaults to None.
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
            logger.debug(f"Start date: {start_date}, end date: {end_date}")
            query = query.filter(cls.submitted_date.between(start_date, end_date))
        # NOTE: by rsl number (returns only a single value)
        match submitter_plate_id:
            case str():
                query = query.filter(cls.submitter_plate_id == submitter_plate_id)
                limit = 1
            case _:
                pass
        match submissiontype_name:
            case str():
                query = query.filter(cls.submissiontype_name == submissiontype_name)
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
        # query = query.order_by(cls.submitted_date.desc())
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
            # dicto, _ = self.kittype.construct_xl_map_for_use(self.proceduretype)
            # sample = self.generate_associations(name="clientsubmissionsampleassociation")
            samples = None
            runs = [item.to_dict(full_data=True) for item in self.run]
            # custom = self.custom
        else:
            samples = None
            custom = None
            runs = None
        try:
            comments = self.comment
        except Exception as e:
            logger.error(f"Error setting comment: {self.comment}, {e}")
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
        output["abbreviation"] = self.submissiontype.defaults['abbreviation']
        output["submission_category"] = self.submission_category
        output["sample"] = samples
        output["comment"] = comments
        output["contact"] = contact
        output["contact_phone"] = contact_phone
        # output["custom"] = custom
        output["run"] = runs
        output['name'] = self.name
        return output

    def add_sample(self, sample: Sample):
        try:
            assert isinstance(sample, Sample)
        except AssertionError:
            logger.warning(f"Converting {sample} to sql.")
            sample = sample.to_sql()
        logger.debug(sample.__dict__)
        try:
            row = sample._misc_info['row']
        except (KeyError, AttributeError):
            row = 0
        try:
            column = sample._misc_info['column']
        except KeyError:
            column = 0
        logger.debug(f"Sample: {sample}")
        submission_rank = sample._misc_info['submission_rank']
        assoc = ClientSubmissionSampleAssociation(
            sample=sample,
            submission=self,
            submission_rank=submission_rank,
            row=row,
            column=column
        )
        return assoc

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
        logger.debug("Add Run")
        from frontend.widgets.sample_checker import SampleChecker
        samples = [sample.to_pydantic() for sample in self.clientsubmissionsampleassociation]
        checker = SampleChecker(parent=None, title="Create Run", samples=samples, clientsubmission=self)
        if checker.exec():
            run = Run(clientsubmission=self, rsl_plate_number=checker.rsl_plate_number)
            active_samples = [sample for sample in samples if sample.enabled]
            logger.debug(active_samples)
            for sample in active_samples:
                sample = sample.to_sql()
                logger.debug(f"Sample: {sample.id}")
                if sample not in run.sample:
                    assoc = run.add_sample(sample)
                    # assoc.save()
            run.save()
        else:
            logger.warning("Run cancelled.")
        obj.set_data()

    def edit(self, obj):
        logger.debug("Edit")

    def add_comment(self, obj):
        logger.debug("Add Comment")

    # def show_details(self, obj):
    #     logger.debug("Show Details")
    #     from frontend.widgets.submission_details import SubmissionDetails
    #     dlg = SubmissionDetails(parent=obj, sub=self)
    #     if dlg.exec():
    #         pass

    def details_dict(self, **kwargs):
        output = super().details_dict(**kwargs)
        output['clientlab'] = output['clientlab'].details_dict()
        output['contact'] = output['contact'].details_dict()
        output['submissiontype'] = output['submissiontype'].details_dict()
        output['run'] = [run.details_dict() for run in output['run']]
        output['sample'] = [sample.details_dict() for sample in output['clientsubmissionsampleassociation']]
        output['name'] = self.name
        output['client_lab'] = output['clientlab']
        output['submission_type'] = output['submissiontype']
        output['excluded'] = ['run', "sample", "clientsubmissionsampleassociation", "excluded",
                              "expanded", 'clientlab', 'submissiontype', 'id']
        output['expanded'] = ["clientlab", "contact", "submissiontype"]
        return output

    def to_pydantic(self, filepath: Path | str | None = None, **kwargs):
        output = super().to_pydantic(filepath=filepath, **kwargs)
        output.template_file = self.template_file
        return output


class Run(BaseClass, LogMixin):
    """
    Object for an entire procedure procedure. Links to client procedure, reagents, equipment, process
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    rsl_plate_number = Column(String(32), unique=True, nullable=False)  #: RSL name (e.g. RSL-22-0012)
    clientsubmission_id = Column(INTEGER, ForeignKey("_clientsubmission.id", ondelete="SET NULL",
                                                     name="fk_BS_clientsub_id"))  #: client lab id from _organizations)
    clientsubmission = relationship("ClientSubmission", back_populates="run")
    started_date = Column(TIMESTAMP)  #: Date this procedure was started.
    run_cost = Column(
        FLOAT(2))  #: total cost of running the plate. Set from constant and mutable kittype costs at time of creation.
    signed_by = Column(String(32))  #: user name of person who submitted the procedure to the database.
    comment = Column(JSON)  #: user notes
    custom = Column(JSON)

    completed_date = Column(TIMESTAMP)

    procedure = relationship("Procedure", back_populates="run", uselist=True)

    runsampleassociation = relationship(
        "RunSampleAssociation",
        back_populates="run",
        cascade="all, delete-orphan",
    )  #: Relation to ClientSubmissionSampleAssociation

    sample = association_proxy("runsampleassociation",
                               "sample", creator=lambda sample: RunSampleAssociation(
            sample=sample))  #: Association proxy to ClientSubmissionSampleAssociation.sample

    # NOTE: Allows for subclassing into ex. BacterialCulture, Wastewater, etc.
    # __mapper_args__ = {
    #     "polymorphic_identity": "Basic Submission",
    #     "polymorphic_on": case(
    #
    #         (submissiontype_name == "Wastewater", "Wastewater"),
    #         (submissiontype_name == "Wastewater Artic", "Wastewater Artic"),
    #         (submissiontype_name == "Bacterial Culture", "Bacterial Culture"),
    #
    #         else_="Basic Submission"
    #     ),
    #     "with_polymorphic": "*",
    # }

    def __repr__(self) -> str:
        return f"<Submission({self.name})>"

    @hybrid_property
    def name(self):
        return self.rsl_plate_number

    @hybrid_property
    def plate_number(self):
        return self.rsl_plate_number

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
        logger.debug(f"Submission type for get default info: {submissiontype}")
        if isinstance(submissiontype, SubmissionType):
            st = submissiontype
        else:
            st = cls.get_submission_type(submissiontype)
        if st is None:
            logger.error("No default info for Run.")
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
                # return SubmissionType.query(cls.__mapper_args__['polymorphic_identity'])
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
            procedures = [item.to_dict(full_data=True) for item in self.procedure]
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
        # logger.debug(f"Submission samples:{pformat(submission_samples)}")
        active_samples = [sample.details_dict() for sample in output['runsampleassociation']
                          if sample.sample.sample_id in [s.sample_id for s in submission_samples]]
        # logger.debug(f"Active samples:{pformat(active_samples)}")
        for sample in active_samples:
            sample['active'] = True
        inactive_samples = [sample.details_dict() for sample in submission_samples if
                            sample.name not in [s['sample_id'] for s in active_samples]]
        # logger.debug(f"Inactive samples:{pformat(inactive_samples)}")
        for sample in inactive_samples:
            sample['active'] = False
        # output['sample'] = [sample.details_dict() for sample in output['runsampleassociation']]
        output['sample'] = active_samples + inactive_samples
        output['procedure'] = [procedure.details_dict() for procedure in output['procedure']]
        output['permission'] = is_power_user()
        output['excluded'] = ['procedure', "runsampleassociation", 'excluded', 'expanded', 'sample', 'id', 'custom',
                              'permission']
        output['sample_count'] = self.sample_count
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
                # logger.debug(f"Sub results: {run}")
                query_out.append(subs)
            query_out = list(itertools.chain.from_iterable(query_out))
        else:
            query_out = cls.query(page_size=0, start_date=start_date, end_date=end_date)
        records = []
        for sub in query_out:
            output = sub.to_dict(full_data=True)
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
        # try:
        #     cols_count_96 = self.column_count
        # except Exception as e:
        #     logger.error(f"Column count error: {e}")
        # # NOTE: Get kittype associated with this procedure
        # # logger.debug(f"Checking associations with procedure type: {self.submissiontype_name}")
        # assoc = next((item for item in self.kittype.kit_submissiontype_associations if
        #               item.proceduretype == self.submission_type),
        #              None)
        # # logger.debug(f"Got association: {assoc}")
        # # NOTE: If every individual cost is 0 this is probably an old plate.
        # if all(item == 0.0 for item in [assoc.constant_cost, assoc.mutable_cost_column, assoc.mutable_cost_sample]):
        #     try:
        #         self.run_cost = self.kittype.cost_per_run
        #     except Exception as e:
        #         logger.error(f"Calculation error: {e}")
        # else:
        #     try:
        #         self.run_cost = assoc.constant_cost + (assoc.mutable_cost_column * cols_count_96) + (
        #                 assoc.mutable_cost_sample * int(self.sample_count))
        #     except Exception as e:
        #         logger.error(f"Calculation error: {e}")
        # self.run_cost = round(self.run_cost, 2)
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
        # logger.debug(f"sample list for plate map: {pformat(sample_list)}")
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
        subs = [item.to_dict() for item in
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
            case "kittype":
                field_value = KitType.query(name=value)
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
                        logger.debug(f"Existing value is {pformat(existing)}")
                        if value in ['', 'null', None]:
                            logger.error(f"No value given, not setting.")
                            return
                        if existing is None:
                            existing = []
                        # if value in existing:
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

    # def update_reagentassoc(self, reagent: Reagent, role: str):
    #     # NOTE: get the first reagent assoc that fills the given reagentrole.
    #     try:
    #         assoc = next(item for item in self.submission_reagent_associations if
    #                      item.reagent and role in [role.name for role in item.reagent.equipmentrole])
    #         assoc.reagent = reagent
    #     except StopIteration as e:
    #         logger.error(f"Association for {role} not found, creating new association.")
    #         assoc = ProcedureReagentAssociation(procedure=self, reagent=reagent)
    #         self.submission_reagent_associations.append(assoc)

    def to_pydantic(self, backup: bool = False) -> "PydSubmission":
        """
        Converts this instance into a PydSubmission

        Returns:
            PydSubmission: converted object.
        """
        from backend.validators import PydRun
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
                case "clientsubmission":
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
        # logger.debug(f"Class for regex: {cls}")
        try:
            regex = cls.get_submission_type(submission_type).defaults['regex']
        except AttributeError as e:
            logger.error(f"Couldn't get procedure type for {cls.__mapper_args__['polymorphic_identity']}")
            regex = None
        try:
            regex = re.compile(rf"{regex}", flags=re.IGNORECASE | re.VERBOSE)
        except re.error as e:
            regex = cls.construct_regex()
        # logger.debug(f"Returning regex: {regex}")
        return regex

    # NOTE: Polymorphic functions

    @classproperty
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
        # from ... import RunReagentAssociation
        # NOTE: if you go back to using 'model' change the appropriate cls to model in the query filters
        # if submissiontype is not None:
        #     model = cls.find_polymorphic_subclass(polymorphic_identity=submissiontype)
        # elif len(kwargs) > 0:
        #     # NOTE: find the subclass containing the relevant attributes
        #     model = cls.find_polymorphic_subclass(attrs=kwargs)
        # else:
        #     model = cls
        query: Query = cls.__database_session__.query(cls)
        if start_date is not None and end_date is None:
            logger.warning(f"Start date with no end date, using today.")
            end_date = date.today()
        if end_date is not None and start_date is None:
            # NOTE: this query returns a tuple of (object, datetime), need to get only datetime.
            start_date = cls.__database_session__.query(cls, func.min(cls.submitted_date)).first()[1]
            logger.warning(f"End date with no start date, using first procedure date: {start_date}")
        if start_date is not None:
            # match start_date:
            #     case date():
            #         pass
            #     case datetime():
            #         start_date = start_date.date()
            #     case int():
            #         start_date = datetime.fromordinal(
            #             datetime(1900, 1, 1).toordinal() + start_date - 2).date()
            #     case _:
            #         start_date = parse(start_date).date()
            # # start_date = start_date.strftime("%Y-%m-%d")
            # match end_date:
            #     case date():
            #         pass
            #     case datetime():
            #         end_date = end_date  # + timedelta(days=1)
            #         # pass
            #     case int():
            #         end_date = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + end_date - 2).date()  # \
            #         # + timedelta(days=1)
            #     case _:
            #         end_date = parse(end_date).date()  # + timedelta(days=1)
            # # end_date = end_date.strftime("%Y-%m-%d")
            # start_date = datetime.combine(start_date, datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S.%f")
            # end_date = datetime.combine(end_date, datetime.max.time()).strftime("%Y-%m-%d %H:%M:%S.%f")
            # # if start_date == end_date:
            # #     start_date = start_date.strftime("%Y-%m-%d %H:%M:%S.%f")
            # #     query = query.filter(model.submitted_date == start_date)
            # # else:
            start_date = cls.rectify_query_date(start_date)
            end_date = cls.rectify_query_date(end_date, eod=True)
            logger.debug(f"Start date: {start_date}, end date: {end_date}")
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
        # query = query.order_by(cls.submitted_date.desc())
        # NOTE: Split query results into pages of size {page_size}
        if page_size > 0:
            query = query.limit(page_size)
        page = page - 1
        if page is not None:
            query = query.offset(page * page_size)
        return cls.execute_query(query=query, limit=limit, **kwargs)

    # @classmethod
    # def query_or_create(cls, submissiontype: str | SubmissionType | None = None, **kwargs) -> Run:
    #     """
    #     Returns object from db if exists, else, creates new. Due to need for user input, doesn't see much use ATM.
    #
    #     Args:
    #         submissiontype (str | SubmissionType | None, optional): Submission type to be created. Defaults to None.
    #
    #     Raises:
    #         ValueError: Raised if no kwargs passed.
    #         ValueError: Raised if disallowed key is passed.
    #
    #     Returns:
    #         cls: A Run subclass instance.
    #     """
    #     code = 0
    #     msg = ""
    #     report = Report()
    #     disallowed = ["id"]
    #     if kwargs == {}:
    #         raise ValueError("Need to narrow down query or the first available instance will be returned.")
    #     sanitized_kwargs = {k: v for k, v in kwargs.items() if k not in disallowed}
    #     instance = cls.query(submissiontype=submissiontype, limit=1, **sanitized_kwargs)
    #     if instance is None:
    #         used_class = cls.find_polymorphic_subclass(attrs=kwargs, polymorphic_identity=submissiontype)
    #         instance = used_class(**sanitized_kwargs)
    #         match submissiontype:
    #             case str():
    #                 submissiontype = SubmissionType.query(name=submissiontype)
    #             case _:
    #                 pass
    #         instance.proceduretype = submissiontype
    #         instance.submissiontype_name = submissiontype.name
    #         if "submitted_date" not in kwargs.keys():
    #             instance.submitted_date = date.today()
    #     else:
    #         from frontend.widgets.pop_ups import QuestionAsker
    #         logger.warning(f"Found existing instance: {instance}, asking to overwrite.")
    #         #     code = 1
    #         #     msg = "This procedure already exists.\nWould you like to overwrite?"
    #         # report.add_result(Result(msg=msg, code=code))
    #         dlg = QuestionAsker(title="Overwrite?",
    #                             message="This procedure already exists.\nWould you like to overwrite?")
    #         if dlg.exec():
    #             pass
    #         else:
    #             code = 1
    #             msg = "This procedure already exists.\nWould you like to overwrite?"
    #             report.add_result(Result(msg=msg, code=code))
    #             return None, report
    #     return instance, report

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
        logger.debug(output)
        return output

    def add_procedure(self, obj, proceduretype_name: str):
        from frontend.widgets.procedure_creation import ProcedureCreation
        procedure_type = next(
            (proceduretype for proceduretype in self.allowed_procedures if proceduretype.name == proceduretype_name))
        logger.debug(f"Got ProcedureType: {procedure_type}")
        dlg = ProcedureCreation(parent=obj, procedure=procedure_type.construct_dummy_procedure(run=self))
        if dlg.exec():
            sql, _ = dlg.return_sql()
            logger.debug(f"Output run samples:\n{pformat(sql.run.sample)}")
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

    # def show_details(self, obj):
    #     """
    #     Creates Widget for showing procedure details.
    #
    #     Args:
    #         obj (Widget): Parent widget
    #     """
    #     from frontend.widgets.submission_details import SubmissionDetails
    #     dlg = SubmissionDetails(parent=obj, sub=self)
    #     if dlg.exec():
    #         pass

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
        logger.debug(obj)
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
                row, column = plate_dict[submission_rank]
                ranked_samples.append(dict(well_id=sample.sample_id, sample_id=sample.sample_id, row=row, column=column,
                                           submission_rank=submission_rank, background_color="#6ffe1d"))
            else:
                unranked_samples.append(sample)
        possible_ranks = (item for item in list(plate_dict.keys()) if
                          item not in [sample['submission_rank'] for sample in ranked_samples])
        # logger.debug(possible_ranks)
        # possible_ranks = (plate_dict[idx] for idx in possible_ranks)
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
        # logger.debug(f"Final padded list:\n{pformat(list(sorted(padded_list, key=itemgetter('submission_rank'))))}")
        return list(sorted(padded_list, key=itemgetter('submission_rank')))


class SampleType(BaseClass):
    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(64), nullable=False, unique=True)  #: identification from submitter

    sample = relationship("Sample", back_populates="sampletype", uselist=True)


# NOTE: Sample Classes

class Sample(BaseClass, LogMixin):
    """
    Base of basic sample which polymorphs into BCSample and WWSample
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    sample_id = Column(String(64), nullable=False, unique=True)  #: identification from submitter
    sampletype_id = Column(INTEGER, ForeignKey("_sampletype.id", ondelete="SET NULL",
                                               name="fk_SAMP_sampletype_id"))
    sampletype = relationship("SampleType", back_populates="sample")
    # misc_info = Column(JSON)
    control = relationship("Control", back_populates="sample", uselist=False)

    sampleclientsubmissionassociation = relationship(
        "ClientSubmissionSampleAssociation",
        back_populates="sample",
        cascade="all, delete-orphan",
    )  #: associated procedure

    clientsubmission = association_proxy("sampleclientsubmissionassociation",
                                         "clientsubmission")  #: proxy of associated procedure

    samplerunassociation = relationship(
        "RunSampleAssociation",
        back_populates="sample",
        cascade="all, delete-orphan",
    )  #: associated procedure

    run = association_proxy("samplerunassociation", "run")  #: proxy of associated procedure

    sampleprocedureassociation = relationship(
        "ProcedureSampleAssociation",
        back_populates="sample",
        cascade="all, delete-orphan",
    )

    procedure = association_proxy("sampleprocedureassociation", "procedure")

    @hybrid_property
    def name(self):
        return self.sample_id

    def __repr__(self) -> str:
        try:
            return f"<{self.sampletype.name.replace('_', ' ').title().replace(' ', '')}({self.sample_id})>"
        except AttributeError:
            return f"<Sample({self.sample_id})>"

    @classproperty
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
        try:
            sample_type = self.sampletype.name
        except AttributeError:
            sample_type = "NA"
        sample = dict(
            sample_id=self.sample_id,
            sampletype=sample_type
        )
        if full_data:
            sample['clientsubmission'] = sorted([item.to_sub_dict() for item in self.sampleclientsubmissionassociation],
                                                key=itemgetter('submitted_date'))
        return sample

    def to_pydantic(self):
        from backend.validators import PydSample
        return PydSample(**self.to_sub_dict())

    def set_attribute(self, name: str, value):
        """
        Custom attribute setter (depreciated over built-in __setattr__)

        Args:
            name (str): name of attribute
            value (_type_): value to be set to attribute
        """
        try:
            setattr(self, name, value)
        except AttributeError:
            logger.error(f"Attribute {name} not found")

    @classmethod
    @setup_lookup
    def query(cls,
              sample_id: str | None = None,
              sampletype: str | SampleType | None = None,
              limit: int = 0,
              **kwargs
              ) -> Sample | List[Sample]:
        """
        Lookup sample in the database by a number of parameters.

        Args:
            sample_id (str | None, optional): Name of the sample (limits results to 1). Defaults to None.
            sampletype (str | None, optional): Sample type. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            models.Sample|List[models.Sample]: Sample(s) of interest.
        """
        query = cls.__database_session__.query(cls)
        match sampletype:
            case str():
                query = query.join(SampleType).filter(SampleType.name == sampletype)
            case SampleType():
                query = query.filter(cls.sampletype == sampletype)
            case _:
                pass
        match sample_id:
            case str():
                query = query.filter(cls.sample_id == sample_id)
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit, **kwargs)

    @classmethod
    def fuzzy_search(cls,
                     sampletype: str | Sample | None = None,
                     **kwargs
                     ) -> List[Sample]:
        """
        Allows for fuzzy search of sample.

        Args:
            sampletype (str | BasicSample | None, optional): Type of sample. Defaults to None.

        Returns:
            List[Sample]: List of sample that match kwarg search parameters.
        """
        query: Query = cls.__database_session__.query(cls)
        match sampletype:
            case str():
                query = query.join(SampleType).filter(SampleType.name == sampletype)
            case SampleType():
                query = query.filter(cls.sampletype == sampletype)
            case _:
                pass
        for k, v in kwargs.items():
            search = f"%{v}%"
            try:
                attr = getattr(cls, k)
                # NOTE: the secret sauce is in attr.like
                query = query.filter(attr.like(search))
            except (ArgumentError, AttributeError) as e:
                logger.error(f"Attribute {k} unavailable due to:\n\t{e}\nSkipping.")
        return query.limit(50).all()

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

    # id = Column(INTEGER, unique=True, nullable=False, autoincrement=True)  #: id to be used for inheriting purposes
    sample_id = Column(INTEGER, ForeignKey("_sample.id"), primary_key=True)  #: id of associated sample
    clientsubmission_id = Column(INTEGER, ForeignKey("_clientsubmission.id"),
                                 primary_key=True)  #: id of associated procedure
    row = Column(INTEGER)
    column = Column(INTEGER)
    submission_rank = Column(INTEGER, primary_key=True, default=0)  #: Location in sample list
    # NOTE: reference to the Submission object
    clientsubmission = relationship("ClientSubmission",
                                    back_populates="clientsubmissionsampleassociation")  #: associated procedure

    # NOTE: reference to the Sample object
    sample = relationship("Sample", back_populates="sampleclientsubmissionassociation")  #: associated sample

    def __init__(self, submission: ClientSubmission = None, sample: Sample = None, row: int = 0, column: int = 0,
                 submission_rank: int = 0, **kwargs):
        super().__init__()
        self.clientsubmission = submission
        self.sample = sample
        self.row = row
        self.column = column
        self.submission_rank = submission_rank
        # if id is not None:
        #     self.id = id
        # else:
        #     self.id = self.__class__.autoincrement_id()
        for k, v in kwargs.items():
            try:
                self.__setattr__(k, v)
            except AttributeError:
                logger.error(f"Couldn't set {k} to {v}")

    def __repr__(self) -> str:
        try:
            return f"<{self.__class__.__name__}({self.clientsubmission.submitter_plate_id} & {self.sample.sample_id})"
        except AttributeError as e:
            logger.error(f"Unable to construct __repr__ due to: {e}")
            return super().__repr__()

    def to_sub_dict(self) -> dict:
        """
        Returns a sample dictionary updated with instance information

        Returns:
            dict: Updated dictionary with row, column and well updated
        """
        # NOTE: Get associated sample info
        sample = self.sample.to_sub_dict()
        sample['sample_id'] = self.sample.sample_id
        sample['row'] = self.row
        sample['column'] = self.column
        try:
            sample['well'] = f"{row_map[self.row]}{self.column}"
        except KeyError as e:
            logger.error(f"Unable to find row {self.row} in row_map.")
            sample['Well'] = None
        sample['plate_name'] = self.clientsubmission.submitter_plate_id
        sample['positive'] = False
        sample['submitted_date'] = self.clientsubmission.submitted_date
        sample['submission_rank'] = self.submission_rank
        return sample

    def details_dict(self, **kwargs):
        output = super().details_dict()
        # NOTE: Figure out how to merge the misc_info if doing .update instead.
        relevant = {k: v for k, v in output.items() if k not in ['sample']}
        # logger.debug(f"Relevant info from assoc output: {pformat(relevant)}")
        output = output['sample'].details_dict()
        misc = output['misc_info']
        # logger.debug(f"Output from sample: {pformat(output)}")
        output.update(relevant)
        output['misc_info'] = misc
        # output['sample'] = temp
        # output.update(output['sample'].details_dict())
        return output

    def to_pydantic(self) -> "PydSample":
        """
        Creates a pydantic model for this sample.

        Returns:
            PydSample: Pydantic Model
        """
        from backend.validators import PydSample
        return PydSample(**self.to_sub_dict())

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

    # @classmethod
    # def autoincrement_id(cls) -> int:
    #     """
    #     Increments the association id automatically
    #
    #     Returns:
    #         int: incremented id
    #     """
    #     if cls.__name__ == "ClientSubmissionSampleAssociation":
    #         model = cls
    #     else:
    #         model = next((base for base in cls.__bases__ if base.__name__ == "ClientSubmissionSampleAssociation"),
    #                      ClientSubmissionSampleAssociation)
    #     try:
    #         return max([item.id for item in model.query()]) + 1
    #     except ValueError as e:
    #         logger.error(f"Problem incrementing id: {e}")
    #         return 1

    # @classmethod
    # def find_polymorphic_subclass(cls, polymorphic_identity: str | None = None) -> ClientSubmissionSampleAssociation:
    #     """
    #     Retrieves subclasses of ClientSubmissionSampleAssociation based on type name.
    #
    #     Args:
    #         polymorphic_identity (str | None, optional): Name of subclass fed to polymorphic identity. Defaults to None.
    #
    #     Returns:
    #         ClientSubmissionSampleAssociation: Subclass of interest.
    #     """
    #     if isinstance(polymorphic_identity, dict):
    #         polymorphic_identity = polymorphic_identity['value']
    #     if polymorphic_identity is None:
    #         model = cls
    #     else:
    #         try:
    #             model = cls.__mapper__.polymorphic_map[polymorphic_identity].class_
    #         except Exception as e:
    #             logger.error(f"Could not get polymorph {polymorphic_identity} of {cls} due to {e}")
    #             model = cls
    #     return model

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
            run (models.Run | str | None, optional): Submission of interest. Defaults to None.
            sample (models.Sample | str | None, optional): Sample of interest. Defaults to None.
            row (int, optional): Row of the sample location on procedure plate. Defaults to 0.
            column (int, optional): Column of the sample location on the procedure plate. Defaults to 0.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.
            chronologic (bool, optional): Return results in chronologic order. Defaults to False.

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

    # id = Column(INTEGER, unique=True, nullable=False)  #: id to be used for inheriting purposes
    sample_id = Column(INTEGER, ForeignKey("_sample.id"), primary_key=True)  #: id of associated sample
    run_id = Column(INTEGER, ForeignKey("_run.id"), primary_key=True)  #: id of associated procedure
    # row = Column(INTEGER)  #: row on the 96 well plate
    # column = Column(INTEGER)  #: column on the 96 well plate
    # misc_info = Column(JSON)

    # NOTE: reference to the Submission object

    run = relationship(Run,
                       back_populates="runsampleassociation")  #: associated procedure

    # NOTE: reference to the Sample object
    sample = relationship(Sample, back_populates="samplerunassociation")  #: associated sample

    def __init__(self, run: Run = None, sample: Sample = None, row: int = 1, column: int = 1, **kwargs):
        self.run = run
        self.sample = sample
        self.row = row
        self.column = column
        for k, v in kwargs.items():
            try:
                self.__setattr__(k, v)
            except AttributeError:
                logger.error(f"Couldn't set {k} to {v}")

    def __repr__(self) -> str:
        try:
            return f"<{self.__class__.__name__}({self.run.rsl_plate_number} & {self.sample.sample_id})"
        except AttributeError as e:
            logger.error(f"Unable to construct __repr__ due to: {e}")
            return super().__repr__()

    def to_sub_dict(self) -> dict:
        """
        Returns a sample dictionary updated with instance information

        Returns:
            dict: Updated dictionary with row, column and well updated
        """
        # NOTE: Get associated sample info
        sample = self.sample.to_sub_dict()
        sample['name'] = self.sample.sample_id
        # sample['row'] = self.row
        # sample['column'] = self.column
        # try:
        #     sample['well'] = f"{row_map[self.row]}{self.column}"
        # except KeyError as e:
        #     logger.error(f"Unable to find row {self.row} in row_map.")
        #     sample['Well'] = None
        sample['plate_name'] = self.run.rsl_plate_number
        sample['positive'] = False
        return sample

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
            sample (models.Sample | str | None, optional): Sample of interest. Defaults to None.
            row (int, optional): Row of the sample location on procedure plate. Defaults to 0.
            column (int, optional): Column of the sample location on the procedure plate. Defaults to 0.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.
            chronologic (bool, optional): Return results in chronologic order. Defaults to False.

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
        # logger.debug(f"Relevant info from assoc output: {pformat(relevant)}")
        output = output['sample'].details_dict()
        misc = output['misc_info']
        # logger.debug(f"Output from sample: {pformat(output)}")
        output.update(relevant)
        output['misc_info'] = misc
        return output


class ProcedureSampleAssociation(BaseClass):
    id = Column(INTEGER, unique=True, nullable=False)
    procedure_id = Column(INTEGER, ForeignKey("_procedure.id"), primary_key=True)  #: id of associated procedure
    sample_id = Column(INTEGER, ForeignKey("_sample.id"), primary_key=True)  #: id of associated equipment
    row = Column(INTEGER)
    column = Column(INTEGER)

    procedure = relationship(Procedure,
                             back_populates="proceduresampleassociation")  #: associated procedure

    sample = relationship(Sample, back_populates="sampleprocedureassociation")  #: associated equipment

    results = relationship("Results", back_populates="sampleprocedureassociation")

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

    def __init__(self, new_id: int | None = None, **kwarg):
        if new_id:
            self.id = new_id
        else:
            self.id = self.__class__.autoincrement_id()
        super().__init__(**kwarg)

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
        misc = output['misc_info']
        output.update(relevant)
        output['misc_info'] = misc
        output['results'] = [result.details_dict() for result in output['results']]
        return output
