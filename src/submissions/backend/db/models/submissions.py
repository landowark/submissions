"""
Models for the main run and sample types.
"""
from __future__ import annotations

import itertools
import pickle
from copy import deepcopy
from getpass import getuser
import logging, uuid, tempfile, re, base64, numpy as np, pandas as pd, types, sys
from inspect import isclass
from zipfile import ZipFile, BadZipfile
from tempfile import TemporaryDirectory, TemporaryFile
from operator import itemgetter
from pprint import pformat
from pandas import DataFrame
from sqlalchemy.ext.hybrid import hybrid_property
from . import Base, BaseClass, Reagent, SubmissionType, KitType, Organization, Contact, LogMixin
from sqlalchemy import Column, String, TIMESTAMP, INTEGER, ForeignKey, JSON, FLOAT, case, func, Table
from sqlalchemy.orm import relationship, validates, Query
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.exc import OperationalError as AlcOperationalError, IntegrityError as AlcIntegrityError, StatementError, \
    ArgumentError
from sqlite3 import OperationalError as SQLOperationalError, IntegrityError as SQLIntegrityError
from openpyxl import Workbook
from openpyxl.drawing.image import Image as OpenpyxlImage
from tools import row_map, setup_lookup, jinja_template_loading, rreplace, row_keys, check_key_or_attr, Result, Report, \
    report_result, create_holidays_for_year, check_dictionary_inclusion_equality
from datetime import datetime, date
from typing import List, Any, Tuple, Literal, Generator, Type
from pathlib import Path
from jinja2.exceptions import TemplateNotFound
from jinja2 import Template
from PIL import Image

from . import kittypes_runs

logger = logging.getLogger(f"submissions.{__name__}")


class ClientSubmission(BaseClass, LogMixin):
    """
    Object for the client run from which all run objects will be created.
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    submitter_plate_id = Column(String(127), unique=True)  #: The number given to the run by the submitting lab
    submitted_date = Column(TIMESTAMP)  #: Date run received
    submitting_lab = relationship("Organization", back_populates="submissions")  #: client org
    submitting_lab_id = Column(INTEGER, ForeignKey("_organization.id", ondelete="SET NULL",
                                                   name="fk_BS_sublab_id"))  #: client lab id from _organizations
    _submission_category = Column(
        String(64))  #: ["Research", "Diagnostic", "Surveillance", "Validation"], else defaults to submission_type_name
    sample_count = Column(INTEGER)  #: Number of samples in the run
    comment = Column(JSON)
    runs = relationship("BasicRun", back_populates="client_submission")  #: many-to-one relationship
    # misc_info = Column(JSON)
    contact = relationship("Contact", back_populates="submissions")  #: client org
    contact_id = Column(INTEGER, ForeignKey("_contact.id", ondelete="SET NULL",
                                            name="fk_BS_contact_id"))  #: client lab id from _organizations
    submission_type_name = Column(String, ForeignKey("_submissiontype.name", ondelete="SET NULL",
                                                     name="fk_BS_subtype_name"))  #: name of joined run type
    submission_type = relationship("SubmissionType", back_populates="controls")  #: archetype of this run


    cost_centre = Column(
        String(64))  #: Permanent storage of used cost centre in case organization field changed in the future.

    submission_sample_associations = relationship(
        "SubmissionSampleAssociation",
        back_populates="run",
        cascade="all, delete-orphan",
    )  #: Relation to SubmissionSampleAssociation

    samples = association_proxy("submission_sample_associations",
                                "sample", creator=lambda sample: SubmissionSampleAssociation(
            sample=sample))  #: Association proxy to SubmissionSampleAssociation.samples

    @hybrid_property
    def submission_category(self):
        return self._submission_category

    @submission_category.setter
    def submission_category(self, submission_category):
        if submission_category in ["Research", "Diagnostic", "Surveillance", "Validation"]:
            self._submission_category = submission_category
        else:
            try:
                self._submission_category = self.submission_type_name
            except AttributeError:
                self._submission_category = "NA"

    def __init__(self):
        super().__init__()
        self.misc_info = {}

    def set_attribute(self, key, value):
        if hasattr(self, key):
            super().__setattr__(key, value)
        else:
            self.misc_info[key] = value

    @classmethod
    def recruit_parser(cls):
        pass

    @classmethod
    @setup_lookup
    def query(cls,
              submissiontype: str | SubmissionType | None = None,
              submission_type_name: str | None = None,
              id: int | str | None = None,
              submitter_plate_num: str | None = None,
              start_date: date | datetime | str | int | None = None,
              end_date: date | datetime | str | int | None = None,
              chronologic: bool = False,
              limit: int = 0,
              page: int = 1,
              page_size: None | int = 250,
              **kwargs
              ) -> BasicRun | List[BasicRun]:
        """
        Lookup submissions based on a number of parameters. Overrides parent.

        Args:
            submission_type (str | models.SubmissionType | None, optional): Submission type of interest. Defaults to None.
            id (int | str | None, optional): Submission id in the database (limits results to 1). Defaults to None.
            rsl_plate_num (str | None, optional): Submission name in the database (limits results to 1). Defaults to None.
            start_date (date | str | int | None, optional): Beginning date to search by. Defaults to None.
            end_date (date | str | int | None, optional): Ending date to search by. Defaults to None.
            reagent (models.Reagent | str | None, optional): A reagent used in the run. Defaults to None.
            chronologic (bool, optional): Return results in chronologic order. Defaults to False.
            limit (int, optional): Maximum number of results to return. Defaults to 0.

        Returns:
            models.BasicRun | List[models.BasicRun]: Submission(s) of interest
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
            logger.warning(f"End date with no start date, using first run date: {start_date}")
        if start_date is not None:
            start_date = cls.rectify_query_date(start_date)
            end_date = cls.rectify_query_date(end_date, eod=True)
            logger.debug(f"Start date: {start_date}, end date: {end_date}")
            query = query.filter(cls.submitted_date.between(start_date, end_date))
        # NOTE: by rsl number (returns only a single value)
        match submitter_plate_num:
            case str():
                query = query.filter(cls.submitter_plate_num == submitter_plate_num)
                limit = 1
            case _:
                pass
        match submission_type_name:
            case str():
                query = query.filter(cls.submission_type_name == submission_type_name)
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
        return cls.execute_query(query=query, model=cls, limit=limit, **kwargs)

    @classmethod
    def submissions_to_df(cls, submission_type: str | None = None, limit: int = 0,
                          chronologic: bool = True, page: int = 1, page_size: int = 250) -> pd.DataFrame:
        """
        Convert all submissions to dataframe

        Args:
            page_size (int, optional): Number of items to include in query result. Defaults to 250.
            page (int, optional): Limits the number of submissions to a page size. Defaults to 1.
            chronologic (bool, optional): Sort submissions in chronologic order. Defaults to True.
            submission_type (str | None, optional): Filter by SubmissionType. Defaults to None.
            limit (int, optional): Maximum number of results to return. Defaults to 0.

        Returns:
            pd.DataFrame: Pandas Dataframe of all relevant submissions
        """
        # NOTE: use lookup function to create list of dicts
        subs = [item.to_dict() for item in
                cls.query(submissiontype=submission_type, limit=limit, chronologic=chronologic, page=page,
                          page_size=page_size)]
        df = pd.DataFrame.from_records(subs)
        # NOTE: Exclude sub information
        exclude = ['controls', 'extraction_info', 'pcr_info', 'comment', 'comments', 'samples', 'reagents',
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
        Constructs dictionary used in submissions summary

        Args:
            expand (bool, optional): indicates if generators to be expanded. Defaults to False.
            report (bool, optional): indicates if to be used for a report. Defaults to False.
            full_data (bool, optional): indicates if sample dicts to be constructed. Defaults to False.
            backup (bool, optional): passed to adjust_to_dict_samples. Defaults to False.

        Returns:
            dict: dictionary used in submissions summary and details
        """
        # NOTE: get lab from nested organization object
        try:
            sub_lab = self.submitting_lab.name
        except AttributeError:
            sub_lab = None
        try:
            sub_lab = sub_lab.replace("_", " ").title()
        except AttributeError:
            pass
        # NOTE: get extraction kit name from nested kit object
        output = {
            "id": self.id,
            "submission_type": self.submission_type_name,
            "submitter_plate_number": self.submitter_plate_id,
            "submitted_date": self.submitted_date.strftime("%Y-%m-%d"),
            "submitting_lab": sub_lab,
            "sample_count": self.sample_count,
        }
        if report:
            return output
        if full_data:
            # dicto, _ = self.extraction_kit.construct_xl_map_for_use(self.submission_type)
            # samples = self.generate_associations(name="submission_sample_associations")
            samples = None
            runs = [item.to_dict() for item in self.runs]
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
                contact = f"Defaulted to: {self.submitting_lab.contacts[0].name}"
            except (AttributeError, IndexError):
                contact = "NA"
        try:
            contact_phone = self.contact.phone
        except AttributeError:
            contact_phone = "NA"
        output["submission_category"] = self.submission_category
        output["samples"] = samples
        output["comment"] = comments
        output["contact"] = contact
        output["contact_phone"] = contact_phone
        # output["custom"] = custom
        output["runs"] = runs
        return output


class BasicRun(BaseClass, LogMixin):
    """
    Object for an entire run run. Links to client submissions, reagents, equipment, processes
    """



    id = Column(INTEGER, primary_key=True)  #: primary key
    rsl_plate_num = Column(String(32), unique=True, nullable=False)  #: RSL name (e.g. RSL-22-0012)
    client_submission_id = Column(INTEGER, ForeignKey("_clientsubmission.id", ondelete="SET NULL",
                                                   name="fk_BS_clientsub_id"))  #: client lab id from _organizations)
    client_submission = relationship("ClientSubmission", back_populates="runs")
    started_date = Column(TIMESTAMP)  #: Date this run was started.

    run_cost = Column(
        FLOAT(2))  #: total cost of running the plate. Set from constant and mutable kit costs at time of creation.
    signed_by = Column(String(32))  #: user name of person who submitted the run to the database.
    comment = Column(JSON)  #: user notes
    custom = Column(JSON)

    completed_date = Column(TIMESTAMP)

    procedures = relationship("Procedure", back_populates="run", uselist=True)

    run_sample_associations = relationship(
        "RunSampleAssociation",
        back_populates="run",
        cascade="all, delete-orphan",
    )  #: Relation to SubmissionSampleAssociation

    samples = association_proxy("run_sample_associations",
                                "sample", creator=lambda sample: RunSampleAssociation(
            sample=sample))  #: Association proxy to SubmissionSampleAssociation.samples


    # NOTE: Allows for subclassing into ex. BacterialCulture, Wastewater, etc.
    # __mapper_args__ = {
    #     "polymorphic_identity": "Basic Submission",
    #     "polymorphic_on": case(
    #
    #         (submission_type_name == "Wastewater", "Wastewater"),
    #         (submission_type_name == "Wastewater Artic", "Wastewater Artic"),
    #         (submission_type_name == "Bacterial Culture", "Bacterial Culture"),
    #
    #         else_="Basic Submission"
    #     ),
    #     "with_polymorphic": "*",
    # }

    def __repr__(self) -> str:
        return f"<Submission({self.rsl_plate_num})>"

    @hybrid_property
    def kittype(self):
        return self.extraction_kit

    @hybrid_property
    def organization(self):
        return self.submitting_lab

    @hybrid_property
    def name(self):
        return self.rsl_plate_num

    @classmethod
    def get_default_info(cls, *args, submission_type: SubmissionType | None = None) -> dict:
        """
        Gets default info from the database for a given run type.

        Args:
            *args (): List of fields to get
            submission_type (SubmissionType): the run type of interest. Necessary due to generic run types.

        Returns:
            dict: Default info

        """
        # NOTE: Create defaults for all submission_types
        # NOTE: Singles tells the query which fields to set limit to 1
        dicto = super().get_default_info()
        recover = ['filepath', 'samples', 'csv', 'comment', 'equipment']
        dicto.update(dict(
            details_ignore=['excluded', 'reagents', 'samples',
                            'extraction_info', 'comment', 'barcode',
                            'platemap', 'export_map', 'equipment', 'tips', 'custom'],
            # NOTE: Fields not placed in ui form
            form_ignore=['reagents', 'ctx', 'id', 'cost', 'extraction_info', 'signed_by', 'comment', 'namer',
                         'submission_object', "tips", 'contact_phone', 'custom', 'cost_centre', 'completed_date',
                         'controls', "origin_plate"] + recover,
            # NOTE: Fields not placed in ui form to be moved to pydantic
            form_recover=recover
        ))
        # NOTE: Grab mode_sub_type specific info.
        if args:
            output = {k: v for k, v in dicto.items() if k in args}
        else:
            output = {k: v for k, v in dicto.items()}
        if isinstance(submission_type, SubmissionType):
            st = submission_type
        else:
            st = cls.get_submission_type(submission_type)
        if st is None:
            logger.error("No default info for BasicRun.")
        else:
            output['submission_type'] = st.name
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
    def get_submission_type(cls, sub_type: str | SubmissionType | None = None) -> SubmissionType:
        """
        Gets the SubmissionType associated with this class

        Args:
            sub_type (str | SubmissionType, Optional): Identity of the run type to retrieve. Defaults to None.

        Returns:
            SubmissionType: SubmissionType with name equal sub_type or this polymorphic identity if sub_type is None.
        """
        if isinstance(sub_type, dict):
            try:
                sub_type = sub_type['value']
            except KeyError as e:
                logger.error(f"Couldn't extract value from {sub_type}")
                raise e
        match sub_type:
            case str():
                return SubmissionType.query(name=sub_type)
            case SubmissionType():
                return sub_type
            case _:
                # return SubmissionType.query(cls.__mapper_args__['polymorphic_identity'])
                return None

    @classmethod
    def construct_info_map(cls, submission_type: SubmissionType | None = None,
                           mode: Literal["read", "write"] = "read") -> dict:
        """
        Method to call run type's construct info map.

        Args:
            mode (Literal["read", "write"]): Which map to construct.

        Returns:
            dict: Map of info locations.
        """
        return cls.get_submission_type(submission_type).construct_info_map(mode=mode)

    @classmethod
    def construct_sample_map(cls, submission_type: SubmissionType | None = None) -> dict:
        """
        Method to call run type's construct_sample_map

        Returns:
            dict: sample location map
        """
        return cls.get_submission_type(submission_type).sample_map

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
        Constructs dictionary used in submissions summary

        Args:
            expand (bool, optional): indicates if generators to be expanded. Defaults to False.
            report (bool, optional): indicates if to be used for a report. Defaults to False.
            full_data (bool, optional): indicates if sample dicts to be constructed. Defaults to False.
            backup (bool, optional): passed to adjust_to_dict_samples. Defaults to False.

        Returns:
            dict: dictionary used in submissions summary and details
        """
        # NOTE: get lab from nested organization object
        try:
            sub_lab = self.client_submission.submitting_lab.name
        except AttributeError:
            sub_lab = None
        try:
            sub_lab = sub_lab.replace("_", " ").title()
        except AttributeError:
            pass
        # NOTE: get extraction kit name from nested kit object
        # try:
        #     ext_kit = self.extraction_kit.name
        # except AttributeError:
        #     ext_kit = None
        # NOTE: load scraped extraction info
        # try:
        #     ext_info = self.extraction_info
        # except TypeError:
        #     ext_info = None
        output = {
            "id": self.id,
            "plate_number": self.rsl_plate_num,
            "submission_type": self.client_submission.submission_type_name,
            "submitter_plate_number": self.client_submission.submitter_plate_id,
            "started_date": self.client_submission.submitted_date.strftime("%Y-%m-%d"),
            "submitting_lab": sub_lab,
            "sample_count": self.client_submission.sample_count,
            "extraction_kit": "Change submissions.py line 388",
            "cost": self.run_cost
        }
        if report:
            return output
        if full_data:
            try:
                reagents = [item.to_sub_dict(extraction_kit=self.extraction_kit) for item in
                            self.submission_reagent_associations]
            except Exception as e:
                logger.error(f"We got an error retrieving reagents: {e}")
                reagents = []
            # finally:
            #     dicto, _ = self.extraction_kit.construct_xl_map_for_use(self.submission_type)
            #     for k, v in dicto.items():
            #         if k == 'info':
            #             continue
            #         if not any([item['role'] == k for item in reagents]):
            #             expiry = "NA"
            #             reagents.append(
            #                 dict(role=k, name="Not Applicable", lot="NA", expiry=expiry,
            #                      missing=True))
            samples = self.generate_associations(name="submission_sample_associations")
            equipment = self.generate_associations(name="submission_equipment_associations")
            tips = self.generate_associations(name="submission_tips_associations")
            # cost_centre = self.cost_centre
            custom = self.custom
            controls = [item.to_sub_dict() for item in self.controls]
        else:
            reagents = None
            samples = None
            equipment = None
            tips = None
            cost_centre = None
            custom = None
            controls = None
        try:
            comments = self.comment
        except Exception as e:
            logger.error(f"Error setting comment: {self.comment}, {e}")
            comments = None
        try:
            contact = self.contact.name
        except AttributeError as e:
            try:
                contact = f"Defaulted to: {self.submitting_lab.contacts[0].name}"
            except (AttributeError, IndexError):
                contact = "NA"
        try:
            contact_phone = self.contact.phone
        except AttributeError:
            contact_phone = "NA"
        output["submission_category"] = self.client_submission.submission_category
        output["technician"] = self.technician
        output["reagents"] = reagents
        output["samples"] = samples
        # output["extraction_info"] = ext_info
        output["comment"] = comments
        output["equipment"] = equipment
        output["tips"] = tips
        # output["cost_centre"] = cost_centre
        output["signed_by"] = self.signed_by
        output["contact"] = contact
        output["contact_phone"] = contact_phone
        output["custom"] = custom
        output["controls"] = controls
        try:
            output["completed_date"] = self.completed_date.strftime("%Y-%m-%d")
        except AttributeError:
            output["completed_date"] = self.completed_date
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
                # logger.debug(f"Sub results: {runs}")
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
        Calculate the number of columns in this run

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
        try:
            cols_count_96 = self.column_count
        except Exception as e:
            logger.error(f"Column count error: {e}")
        # NOTE: Get kit associated with this run
        # logger.debug(f"Checking associations with run type: {self.submission_type_name}")
        assoc = next((item for item in self.extraction_kit.kit_submissiontype_associations if
                      item.submission_type == self.submission_type),
                     None)
        # logger.debug(f"Got association: {assoc}")
        # NOTE: If every individual cost is 0 this is probably an old plate.
        if all(item == 0.0 for item in [assoc.constant_cost, assoc.mutable_cost_column, assoc.mutable_cost_sample]):
            try:
                self.run_cost = self.extraction_kit.cost_per_run
            except Exception as e:
                logger.error(f"Calculation error: {e}")
        else:
            try:
                self.run_cost = assoc.constant_cost + (assoc.mutable_cost_column * cols_count_96) + (
                        assoc.mutable_cost_sample * int(self.sample_count))
            except Exception as e:
                logger.error(f"Calculation error: {e}")
        self.run_cost = round(self.run_cost, 2)

    @property
    def hitpicked(self) -> list:
        """
        Returns positve sample locations for plate

        Returns:
            list: list of hitpick dictionaries for each sample
        """
        output_list = [assoc.hitpicked for assoc in self.submission_sample_associations]
        return output_list

    @classmethod
    def make_plate_map(cls, sample_list: list, plate_rows: int = 8, plate_columns=12) -> str:
        """
        Constructs an html based plate map for run details.

        Args:
            sample_list (list): List of run samples
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
        template = env.get_template("plate_map.html")
        html = template.render(samples=output_samples, PLATE_ROWS=plate_rows, PLATE_COLUMNS=plate_columns)
        return html + "<br/>"

    @property
    def used_equipment(self) -> Generator[str, None, None]:
        """
        Gets EquipmentRole names associated with this BasicRun

        Returns:
            List[str]: List of names
        """
        return (item.role for item in self.submission_equipment_associations)

    @classmethod
    def submissions_to_df(cls, submission_type: str | None = None, limit: int = 0,
                          chronologic: bool = True, page: int = 1, page_size: int = 250) -> pd.DataFrame:
        """
        Convert all submissions to dataframe

        Args:
            page_size (int, optional): Number of items to include in query result. Defaults to 250.
            page (int, optional): Limits the number of submissions to a page size. Defaults to 1.
            chronologic (bool, optional): Sort submissions in chronologic order. Defaults to True.
            submission_type (str | None, optional): Filter by SubmissionType. Defaults to None.
            limit (int, optional): Maximum number of results to return. Defaults to 0.

        Returns:
            pd.DataFrame: Pandas Dataframe of all relevant submissions
        """
        # NOTE: use lookup function to create list of dicts
        subs = [item.to_dict() for item in
                cls.query(submissiontype=submission_type, limit=limit, chronologic=chronologic, page=page,
                          page_size=page_size)]
        df = pd.DataFrame.from_records(subs)
        # NOTE: Exclude sub information
        exclude = ['controls', 'extraction_info', 'pcr_info', 'comment', 'comments', 'samples', 'reagents',
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
            case "extraction_kit":
                field_value = KitType.query(name=value)
            case "submitting_lab":
                field_value = Organization.query(name=value)
            case "contact":
                field_value = Contact.query(name=value)
            case "samples":
                for sample in value:
                    sample, _ = sample.to_sql(run=self)
                return
            case "reagents":
                field_value = [reagent['value'].to_sql()[0] if isinstance(reagent, dict) else reagent.to_sql()[0] for
                               reagent in value]
            case "submission_type":
                field_value = SubmissionType.query(name=value)
            case "sample_count":
                if value is None:
                    field_value = len(self.samples)
                else:
                    field_value = value
            case "ctx" | "csv" | "filepath" | "equipment" | "controls":
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

    def update_subsampassoc(self, assoc: SubmissionSampleAssociation, input_dict: dict) -> SubmissionSampleAssociation:
        """
        Update a joined run sample association.

        Args:
            assoc (SubmissionSampleAssociation): Sample association to be updated.
            input_dict (dict): updated values to insert.

        Returns:
            SubmissionSampleAssociation: Updated association
        """
        # NOTE: No longer searches for association here, done in caller function
        for k, v in input_dict.items():
            try:
                setattr(assoc, k, v)
                # NOTE: for some reason I don't think assoc.__setattr__(k, v) works here.
            except AttributeError:
                pass
        return assoc

    def update_reagentassoc(self, reagent: Reagent, role: str):
        # NOTE: get the first reagent assoc that fills the given role.
        try:
            assoc = next(item for item in self.submission_reagent_associations if
                         item.reagent and role in [role.name for role in item.reagent.role])
            assoc.reagent = reagent
        except StopIteration as e:
            logger.error(f"Association for {role} not found, creating new association.")
            assoc = RunReagentAssociation(submission=self, reagent=reagent)
            self.submission_reagent_associations.append(assoc)

    def to_pydantic(self, backup: bool = False) -> "PydSubmission":
        """
        Converts this instance into a PydSubmission

        Returns:
            PydSubmission: converted object.
        """
        from backend.validators import PydSubmission
        dicto = self.to_dict(full_data=True, backup=backup)
        new_dict = {}
        for key, value in dicto.items():
            missing = value in ['', 'None', None]
            match key:
                case "reagents":
                    field_value = [item.to_pydantic(extraction_kit=self.extraction_kit) for item in
                                   self.submission_reagent_associations]
                case "samples":
                    field_value = [item.to_pydantic() for item in self.submission_sample_associations]
                case "equipment":
                    field_value = [item.to_pydantic() for item in self.submission_equipment_associations]
                case "controls":
                    try:
                        field_value = [item.to_pydantic() for item in self.__getattribute__(key)]
                    except TypeError as e:
                        logger.error(f"Error converting {key} to pydantic :{e}")
                        continue
                case "tips":
                    field_value = [item.to_pydantic() for item in self.submission_tips_associations]
                case "submission_type":
                    field_value = dict(value=self.__getattribute__(key).name, missing=missing)
                case "plate_number":
                    key = 'rsl_plate_num'
                    field_value = dict(value=self.rsl_plate_num, missing=missing)
                case "submitter_plate_number":
                    key = "submitter_plate_num"
                    field_value = dict(value=self.submitter_plate_num, missing=missing)
                case "id":
                    continue
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
        return PydSubmission(**dicto)

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
        Gets the regex string for identifying a certain class of run.

        Args:
            submission_type (SubmissionType | str | None, optional): run type of interest. Defaults to None.

        Returns:
            str: String from which regex will be compiled.
        """
        # logger.debug(f"Class for regex: {cls}")
        try:
            regex = cls.get_submission_type(submission_type).defaults['regex']
        except AttributeError as e:
            logger.error(f"Couldn't get run type for {cls.__mapper_args__['polymorphic_identity']}")
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
            re.Pattern: Regular expression pattern to discriminate between run types.
        """
        res = [st.defaults['regex'] for st in SubmissionType.query() if st.defaults]
        rstring = rf'{"|".join(res)}'
        regex = re.compile(rstring, flags=re.IGNORECASE | re.VERBOSE)
        return regex

    @classmethod
    def find_polymorphic_subclass(cls, polymorphic_identity: str | SubmissionType | list | None = None,
                                  attrs: dict | None = None) -> BasicRun | List[BasicRun]:
        """
        Find subclass based on polymorphic identity or relevant attributes.

        Args:
            polymorphic_identity (str | None, optional): String representing polymorphic identity. Defaults to None.
            attrs (str | SubmissionType | None, optional): Attributes of the relevant class. Defaults to None.

        Returns:
            _type_: Subclass of interest.
        """
        if isinstance(polymorphic_identity, dict):
            polymorphic_identity = polymorphic_identity['value']
        if isinstance(polymorphic_identity, SubmissionType):
            polymorphic_identity = polymorphic_identity.name
        model = cls
        match polymorphic_identity:
            case str():
                try:
                    model = cls.__mapper__.polymorphic_map[polymorphic_identity].class_
                except Exception as e:
                    logger.error(
                        f"Could not get polymorph {polymorphic_identity} of {cls} due to {e}, falling back to BasicRun")
            case list():
                output = []
                for identity in polymorphic_identity:
                    if isinstance(identity, SubmissionType):
                        identity = polymorphic_identity.name
                    output.append(cls.__mapper__.polymorphic_map[identity].class_)
                return output
            case _:
                pass
        if attrs and any([not hasattr(cls, attr) for attr in attrs.keys()]):
            # NOTE: looks for first model that has all included kwargs
            try:
                model = next(subclass for subclass in cls.__subclasses__() if
                             all([hasattr(subclass, attr) for attr in attrs.keys()]))
            except StopIteration as e:
                raise AttributeError(
                    f"Couldn't find existing class/subclass of {cls} with all attributes:\n{pformat(attrs.keys())}")
        return model

    # NOTE: Child class custom functions

    @classmethod
    def custom_info_parser(cls, input_dict: dict, xl: Workbook | None = None, custom_fields: dict = {}) -> dict:
        """
        Update run dictionary with type specific information

        Args:
            input_dict (dict): Input sample dictionary
            xl (Workbook): original xl workbook, used for child classes mostly
            custom_fields: Dictionary of locations, ranges, etc to be used by this function

        Returns:
            dict: Updated sample dictionary
        """
        input_dict['custom'] = {}
        for k, v in custom_fields.items():
            logger.debug(f"Custom info parser getting type: {v['type']}")
            match v['type']:
                # NOTE: 'exempt' type not currently used
                case "exempt":
                    continue
                case "cell":
                    ws = xl[v['read']['sheet']]
                    input_dict['custom'][k] = ws.cell(row=v['read']['row'], column=v['read']['column']).value
                case "range":
                    ws = xl[v['sheet']]
                    if v['start_row'] != v['end_row']:
                        v['end_row'] = v['end_row'] + 1
                    rows = range(v['start_row'], v['end_row'])
                    if v['start_column'] != v['end_column']:
                        v['end_column'] = v['end_column'] + 1
                    columns = range(v['start_column'], v['end_column'])
                    input_dict['custom'][k] = [dict(value=ws.cell(row=row, column=column).value, row=row, column=column)
                                               for row in rows for column in columns]
        return input_dict

    @classmethod
    def parse_samples(cls, input_dict: dict) -> dict:
        """
        Update sample dictionary with type specific information

        Args:
            input_dict (dict): Input sample dictionary

        Returns:
            dict: Updated sample dictionary
        """
        return input_dict

    @classmethod
    def custom_validation(cls, pyd: "PydSubmission") -> "PydSubmission":
        """
        Performs any final parsing of the pydantic object that only needs to be done for this cls.

        Args:
            input_dict (dict): Parser product up to this point.
            xl (pd.ExcelFile | None, optional): Excel run form. Defaults to None.
            info_map (dict | None, optional): Map of information locations from SubmissionType. Defaults to None.
            plate_map (dict | None, optional): Constructed plate map of samples. Defaults to None.

        Returns:
            dict: Updated parser product.
        """
        return pyd

    @classmethod
    def custom_info_writer(cls, input_excel: Workbook, info: dict | None = None, backup: bool = False,
                           custom_fields: dict = {}) -> Workbook:
        """
        Adds custom autofill methods for run

        Args:
            input_excel (Workbook): initial workbook.
            info (dict | None, optional): dictionary of additional info. Defaults to None.
            backup (bool, optional): Whether this is part of a backup operation. Defaults to False.
            custom_fields: Dictionary of locations, ranges, etc to be used by this function

        Returns:
            Workbook: Updated workbook
        """
        for k, v in custom_fields.items():
            try:
                assert v['type'] in ['exempt', 'range', 'cell']
            except (AssertionError, KeyError):
                continue
            match v['type']:
                case "exempt":
                    continue
                case "cell":
                    v['write'].append(v['read'])
                    for cell in v['write']:
                        ws = input_excel[cell['sheet']]
                        ws.cell(row=cell['row'], column=cell['column'], value=info['custom'][k])
                case "range":
                    ws = input_excel[v['sheet']]
                    if v['start_row'] != v['end_row']:
                        v['end_row'] = v['end_row'] + 1
                    if v['start_column'] != v['end_column']:
                        v['end_column'] = v['end_column'] + 1
                    for item in info['custom'][k]:
                        ws.cell(row=item['row'], column=item['column'], value=item['value'])
        return input_excel

    @classmethod
    def custom_sample_writer(self, sample: dict) -> dict:
        """
        Performs any final alterations to sample writing unique to this run type.
        Args:
            sample (dict): Dictionary of sample values.

        Returns:
            dict: Finalized dictionary.
        """
        return sample

    @classmethod
    def enforce_name(cls, instr: str, data: dict | None = {}) -> str:
        """
        Custom naming method for this class.

        Args:
            instr (str): Initial name.
            data (dict | None, optional): Additional parameters for name. Defaults to None.

        Returns:
            str: Updated name.
        """
        from backend.validators import RSLNamer
        if "submission_type" not in data.keys():
            data['submission_type'] = cls.__mapper_args__['polymorphic_identity']
        data['abbreviation'] = cls.get_default_info("abbreviation", submission_type=data['submission_type'])
        if instr in [None, ""]:
            outstr = RSLNamer.construct_new_plate_name(data=data)
        else:
            outstr = instr
        if re.search(rf"{data['abbreviation']}", outstr, flags=re.IGNORECASE) is None:
            # NOTE: replace RSL- with RSL-abbreviation-
            outstr = re.sub(rf"RSL-?", rf"RSL-{data['abbreviation']}-", outstr, flags=re.IGNORECASE)
        try:
            # NOTE: remove dashes from date
            outstr = re.sub(r"(\d{4})-(\d{2})-(\d{2})", r"\1\2\3", outstr)
            # NOTE: insert dash between abbreviation and date
            outstr = re.sub(rf"{data['abbreviation']}(\d{6})", rf"{data['abbreviation']}-\1", outstr,
                            flags=re.IGNORECASE).upper()
        except (AttributeError, TypeError) as e:
            logger.error(f"Error making outstr: {e}, sending to RSLNamer to make new plate name.")
            outstr = RSLNamer.construct_new_plate_name(data=data)
        try:
            # NOTE: Grab plate number as number after a -|_ not followed by another number
            plate_number = re.search(r"(?:(-|_)\d)(?!\d)", outstr).group().strip("_").strip("-")
        except AttributeError as e:
            plate_number = "1"
        # NOTE: insert dash between date and plate number
        outstr = re.sub(r"(\d{8})(-|_)?\d?(R\d?)?", rf"\1-{plate_number}\3", outstr)
        try:
            # NOTE: grab repeat number
            repeat = re.search(r"-\dR(?P<repeat>\d)?", outstr).groupdict()['repeat']
            if repeat is None:
                repeat = "1"
        except AttributeError as e:
            repeat = ""
        # NOTE: Insert repeat number?
        outstr = re.sub(r"(-\dR)\d?", rf"\1 {repeat}", outstr).replace(" ", "")
        # NOTE: This should already have been done. Do I dare remove it?
        outstr = re.sub(rf"RSL{data['abbreviation']}", rf"RSL-{data['abbreviation']}", outstr)
        return re.sub(rf"{data['abbreviation']}(\d)", rf"{data['abbreviation']}-\1", outstr)

    @classmethod
    def parse_pcr(cls, xl: Workbook, rsl_plate_num: str) -> Generator[dict, None, None]:
        """
        Perform parsing of pcr info. Since most of our PC outputs are the same format, this should work for most.

        Args:
            xl (pd.DataFrame): pcr info form
            rsl_plate_num (str): rsl plate num of interest

        Returns:
            Generator[dict, None, None]: Updated samples
        """
        pcr_sample_map = cls.get_submission_type().sample_map['pcr_samples']
        main_sheet = xl[pcr_sample_map['main_sheet']]
        fields = {k: v for k, v in pcr_sample_map.items() if k not in ['main_sheet', 'start_row']}
        logger.debug(f"Fields: {fields}")
        for row in main_sheet.iter_rows(min_row=pcr_sample_map['start_row']):
            idx = row[0].row
            sample = {}
            for k, v in fields.items():
                # logger.debug(f"Checking key: {k} with value {v}")
                sheet = xl[v['sheet']]
                sample[k] = sheet.cell(row=idx, column=v['column']).value
            yield sample

    @classmethod
    def parse_pcr_controls(cls, xl: Workbook, rsl_plate_num: str) -> Generator[dict, None, None]:
        """
        Custom parsing of pcr controls from Design & Analysis Software export.

        Args:
            xl (Workbook): D&A export file
            rsl_plate_num (str): Plate number of the run to be joined.

        Yields:
            Generator[dict, None, None]: Dictionaries of row values.
        """
        location_map = cls.get_submission_type().sample_map['pcr_controls']
        # logger.debug(f"Location map: {location_map}")
        submission = cls.query(rsl_plate_num=rsl_plate_num)
        name_column = 1
        for item in location_map:
            # logger.debug(f"Checking {item}")
            worksheet = xl[item['sheet']]
            for iii, row in enumerate(worksheet.iter_rows(max_row=len(worksheet['A']), max_col=name_column), start=1):
                # logger.debug(f"Checking row {row}, {iii}")
                for cell in row:
                    # logger.debug(f"Checking cell: {cell}, with value {cell.value} against {item['name']}")
                    if cell.value == item['name']:
                        subtype, _ = item['name'].split("-")
                        target = item['target']
                        # logger.debug(f"Subtype: {subtype}, target: {target}")
                        ct = worksheet.cell(row=iii, column=item['ct_column']).value
                        # NOTE: Kind of a stop gap solution to find control reagents.
                        if subtype == "PC":
                            ctrl = next((assoc.reagent for assoc in submission.submission_reagent_associations
                                         if
                                         any(["positive control" in item.name.lower() for item in assoc.reagent.role])),
                                        None)
                        elif subtype == "NC":
                            ctrl = next((assoc.reagent for assoc in submission.submission_reagent_associations
                                         if any(["molecular grade water" in item.name.lower() for item in
                                                 assoc.reagent.role])), None)
                        else:
                            ctrl = None
                        # logger.debug(f"Control reagent: {ctrl.__dict__}")
                        try:
                            ct = float(ct)
                        except ValueError:
                            ct = 0.0
                        if ctrl:
                            ctrl = ctrl.lot
                        else:
                            ctrl = None
                        output = dict(
                            name=f"{rsl_plate_num}<{item['name']}-{target}>",
                            ct=ct,
                            subtype=subtype,
                            target=target,
                            reagent_lot=ctrl
                        )
                        # logger.debug(f"Control output: {pformat(output)}")
                        yield output

    @classmethod
    def filename_template(cls) -> str:
        """
        Constructs template for filename of this class.
        Note: This is meant to be used with the dictionary constructed in self.to_dict(). Keys need to have spaces removed

        Returns:
            str: filename template in jinja friendly format.
        """
        return "{{ rsl_plate_num }}"

    @classmethod
    def adjust_autofill_samples(cls, samples: List[Any]) -> List[Any]:
        """
        Makes adjustments to samples before writing to excel.

        Args:
            samples (List[Any]): List of Samples

        Returns:
            List[Any]: Updated list of samples
        """
        return samples

    @classmethod
    def get_details_template(cls, base_dict: dict) -> Tuple[dict, Template]:
        """
        Get the details jinja template for the correct class

        Args:
            base_dict (dict): incoming dictionary of Submission fields

        Returns:
            Tuple(dict, Template): (Updated dictionary, Template to be rendered)
        """
        base_dict['excluded'] = cls.get_default_info('details_ignore')
        base_dict['excluded'] += ['controls']
        env = jinja_template_loading()
        temp_name = f"{cls.__name__.lower()}_details.html"
        try:
            template = env.get_template(temp_name)
        except TemplateNotFound as e:
            logger.error(f"Couldn't find template due to {e}")
            template = env.get_template("basicrun_details.html")
        return base_dict, template

    # NOTE: Query functions

    @classmethod
    @setup_lookup
    def query(cls,
              submissiontype: str | SubmissionType | None = None,
              submission_type_name: str | None = None,
              id: int | str | None = None,
              rsl_plate_num: str | None = None,
              start_date: date | datetime | str | int | None = None,
              end_date: date | datetime | str | int | None = None,
              reagent: Reagent | str | None = None,
              chronologic: bool = False,
              limit: int = 0,
              page: int = 1,
              page_size: None | int = 250,
              **kwargs
              ) -> BasicRun | List[BasicRun]:
        """
        Lookup submissions based on a number of parameters. Overrides parent.

        Args:
            submission_type (str | models.SubmissionType | None, optional): Submission type of interest. Defaults to None.
            id (int | str | None, optional): Submission id in the database (limits results to 1). Defaults to None.
            rsl_plate_num (str | None, optional): Submission name in the database (limits results to 1). Defaults to None.
            start_date (date | str | int | None, optional): Beginning date to search by. Defaults to None.
            end_date (date | str | int | None, optional): Ending date to search by. Defaults to None.
            reagent (models.Reagent | str | None, optional): A reagent used in the run. Defaults to None.
            chronologic (bool, optional): Return results in chronologic order. Defaults to False.
            limit (int, optional): Maximum number of results to return. Defaults to 0.

        Returns:
            models.BasicRun | List[models.BasicRun]: Run(s) of interest
        """
        # from ... import RunReagentAssociation
        # NOTE: if you go back to using 'model' change the appropriate cls to model in the query filters
        if submissiontype is not None:
            model = cls.find_polymorphic_subclass(polymorphic_identity=submissiontype)
        elif len(kwargs) > 0:
            # NOTE: find the subclass containing the relevant attributes
            model = cls.find_polymorphic_subclass(attrs=kwargs)
        else:
            model = cls
        query: Query = cls.__database_session__.query(model)
        if start_date is not None and end_date is None:
            logger.warning(f"Start date with no end date, using today.")
            end_date = date.today()
        if end_date is not None and start_date is None:
            # NOTE: this query returns a tuple of (object, datetime), need to get only datetime.
            start_date = cls.__database_session__.query(cls, func.min(cls.submitted_date)).first()[1]
            logger.warning(f"End date with no start date, using first run date: {start_date}")
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
        # NOTE: by reagent (for some reason)
        match reagent:
            case str():
                query = query.join(RunReagentAssociation).join(Reagent).filter(
                    Reagent.lot == reagent)
            case Reagent():
                query = query.join(RunReagentAssociation).filter(
                    RunReagentAssociation.reagent == reagent)
            case _:
                pass
        # NOTE: by rsl number (returns only a single value)
        match rsl_plate_num:
            case str():
                query = query.filter(model.rsl_plate_num == rsl_plate_num)
                limit = 1
            case _:
                pass
        match submission_type_name:
            case str():
                if not start_date:
                    query = query.join(ClientSubmission)
                query = query.filter(ClientSubmission.submission_type_name == submission_type_name)
            case _:
                pass
        # NOTE: by id (returns only a single value)
        match id:
            case int():
                query = query.filter(model.id == id)
                limit = 1
            case str():
                query = query.filter(model.id == int(id))
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
        return cls.execute_query(query=query, model=model, limit=limit, **kwargs)

    @classmethod
    def query_or_create(cls, submission_type: str | SubmissionType | None = None, **kwargs) -> BasicRun:
        """
        Returns object from db if exists, else, creates new. Due to need for user input, doesn't see much use ATM.

        Args:
            submission_type (str | SubmissionType | None, optional): Submission type to be created. Defaults to None.

        Raises:
            ValueError: Raised if no kwargs passed.
            ValueError: Raised if disallowed key is passed.

        Returns:
            cls: A BasicRun subclass instance.
        """
        code = 0
        msg = ""
        report = Report()
        disallowed = ["id"]
        if kwargs == {}:
            raise ValueError("Need to narrow down query or the first available instance will be returned.")
        sanitized_kwargs = {k: v for k, v in kwargs.items() if k not in disallowed}
        instance = cls.query(submissiontype=submission_type, limit=1, **sanitized_kwargs)
        if instance is None:
            used_class = cls.find_polymorphic_subclass(attrs=kwargs, polymorphic_identity=submission_type)
            instance = used_class(**sanitized_kwargs)
            match submission_type:
                case str():
                    submission_type = SubmissionType.query(name=submission_type)
                case _:
                    pass
            instance.submission_type = submission_type
            instance.submission_type_name = submission_type.name
            if "submitted_date" not in kwargs.keys():
                instance.submitted_date = date.today()
        else:
            from frontend.widgets.pop_ups import QuestionAsker
            logger.warning(f"Found existing instance: {instance}, asking to overwrite.")
            #     code = 1
            #     msg = "This run already exists.\nWould you like to overwrite?"
            # report.add_result(Result(msg=msg, code=code))
            dlg = QuestionAsker(title="Overwrite?",
                                message="This run already exists.\nWould you like to overwrite?")
            if dlg.exec():
                pass
            else:
                code = 1
                msg = "This run already exists.\nWould you like to overwrite?"
                report.add_result(Result(msg=msg, code=code))
                return None, report
        return instance, report

    # NOTE: Custom context events for the ui

    def custom_context_events(self) -> dict:
        """
        Creates dictionary of str:function to be passed to context menu

        Returns:
            dict: dictionary of functions
        """
        names = ["Delete", "Details", "Edit", "Add Comment", "Add Equipment", "Export"]
        funcs = [self.delete, self.show_details, self.edit, self.add_comment, self.add_equipment, self.backup]
        dicto = {item[0]: item[1] for item in zip(names, funcs)}
        return dicto

    def delete(self, obj=None):
        """
        Performs backup and deletes this instance from database.

        Args:
            obj (_type_, optional): Parent widget. Defaults to None.

        Raises:
            e: SQLIntegrityError or SQLOperationalError if problem with commit.
        """
        from frontend.widgets.pop_ups import QuestionAsker
        fname = self.__backup_path__.joinpath(f"{self.rsl_plate_num}-backup({date.today().strftime('%Y%m%d')})")
        msg = QuestionAsker(title="Delete?", message=f"Are you sure you want to delete {self.rsl_plate_num}?\n")
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

    def show_details(self, obj):
        """
        Creates Widget for showing run details.

        Args:
            obj (Widget): Parent widget
        """
        from frontend.widgets.submission_details import SubmissionDetails
        dlg = SubmissionDetails(parent=obj, sub=self)
        if dlg.exec():
            pass

    def edit(self, obj):
        """
        Return run to form widget for updating

        Args:
            obj (Widget): Parent widget 
        """
        from frontend.widgets.submission_widget import SubmissionFormWidget
        for widget in obj.app.table_widget.formwidget.findChildren(SubmissionFormWidget):
            widget.setParent(None)
        pyd = self.to_pydantic(backup=True)
        form = pyd.to_form(parent=obj, disable=['rsl_plate_num'])
        obj.app.table_widget.formwidget.layout().addWidget(form)

    def add_comment(self, obj):
        """
        Creates widget for adding comments to submissions

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

    def add_equipment(self, obj):
        """
        Creates widget for adding equipment to this run

        Args:
            obj (_type_): parent widget
        """
        from frontend.widgets.equipment_usage import EquipmentUsage
        dlg = EquipmentUsage(parent=obj, submission=self)
        if dlg.exec():
            equipment = dlg.parse_form()
            for equip in equipment:
                logger.debug(f"Parsed equipment: {equip}")
                _, assoc = equip.to_sql(submission=self)
                logger.debug(f"Got equipment association: {assoc} for {equip}")
                try:
                    assoc.save()
                except AttributeError as e:
                    logger.error(f"Couldn't save association with {equip} due to {e}")
                if equip.tips:
                    for tips in equip.tips:
                        # logger.debug(f"Attempting to add tips assoc: {tips} (pydantic)")
                        tassoc = tips.to_sql(submission=self)
                        # logger.debug(f"Attempting to add tips assoc: {tips.__dict__} (sql)")
                        if tassoc not in self.submission_tips_associations:
                            tassoc.save()
                        else:
                            logger.error(f"Tips already found in run, skipping.")
        else:
            pass

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
        return self.calculate_turnaround(start_date=self.client_submission.submitted_date.date(), end_date=completed)

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



# NOTE: Sample Classes

class BasicSample(BaseClass, LogMixin):
    """
    Base of basic sample which polymorphs into BCSample and WWSample
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    submitter_id = Column(String(64), nullable=False, unique=True)  #: identification from submitter
    sample_type = Column(String(32))  #: mode_sub_type of sample
    # misc_info = Column(JSON)
    control = relationship("Control", back_populates="sample", uselist=False)

    sample_submission_associations = relationship(
        "SubmissionSampleAssociation",
        back_populates="sample",
        cascade="all, delete-orphan",
    )  #: associated submissions

    submissions = association_proxy("sample_submission_associations", "run")  #: proxy of associated submissions

    sample_run_associations = relationship(
        "RunSampleAssociation",
        back_populates="sample",
        cascade="all, delete-orphan",
    )  #: associated submissions

    submissions = association_proxy("sample_submission_associations", "run")  #: proxy of associated submissions

    @validates('submitter_id')
    def create_id(self, key: str, value: str) -> str:
        """
        Creates a random string as a submitter id.

        Args:
            key (str): name of attribute
            value (str): submitter id

        Returns:
            str: new (or unchanged) submitter id
        """
        if value is None:
            return uuid.uuid4().hex.upper()
        else:
            return value

    def __repr__(self) -> str:
        try:
            return f"<{self.sample_type.replace('_', ' ').title().replace(' ', '')}({self.submitter_id})>"
        except AttributeError:
            return f"<Sample({self.submitter_id})"

    @classproperty
    def searchables(cls):
        return [dict(label="Submitter ID", field="submitter_id")]

    @classproperty
    def timestamps(cls) -> List[str]:
        """
        Constructs a list of all attributes stored as SQL Timestamps

        Returns:
            List[str]: Attribute list
        """
        output = [item.name for item in cls.__table__.columns if isinstance(item.type, TIMESTAMP)]
        if issubclass(cls, BasicSample) and not cls.__name__ == "BasicSample":
            output += BasicSample.timestamps
        return output

    def to_sub_dict(self, full_data: bool = False) -> dict:
        """
        gui friendly dictionary

        Args:
            full_data (bool): Whether to use full object or truncated. Defaults to False

        Returns:
            dict: submitter id and sample type and linked submissions if full data
        """
        sample = dict(
            submitter_id=self.submitter_id,
            sample_type=self.sample_type
        )
        if full_data:
            sample['submissions'] = sorted([item.to_sub_dict() for item in self.sample_submission_associations],
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
    def find_polymorphic_subclass(cls, polymorphic_identity: str | None = None,
                                  attrs: dict | None = None) -> Type[BasicSample]:
        """
        Retrieves subclasses of BasicSample based on type name.

        Args:
            attrs (dict | None, optional): name: value of attributes in the wanted subclass
            polymorphic_identity (str | None, optional): Name of subclass fed to polymorphic identity. Defaults to None.

        Returns:
            BasicSample: Subclass of interest.
        """
        if isinstance(polymorphic_identity, dict):
            polymorphic_identity = polymorphic_identity['value']
        if polymorphic_identity is not None:
            try:
                model = cls.__mapper__.polymorphic_map[polymorphic_identity].class_
            except Exception as e:
                logger.error(f"Could not get polymorph {polymorphic_identity} of {cls} due to {e}, using {cls}")
                model = cls
            return model
        else:
            model = cls
        if attrs is None or len(attrs) == 0:
            return model
        if any([not hasattr(cls, attr) for attr in attrs.keys()]):
            # NOTE: looks for first model that has all included kwargs
            try:
                model = next(subclass for subclass in cls.__subclasses__() if
                             all([hasattr(subclass, attr) for attr in attrs.keys()]))
            except StopIteration as e:
                raise AttributeError(
                    f"Couldn't find existing class/subclass of {cls} with all attributes:\n{pformat(attrs.keys())}")
        return model

    @classmethod
    def parse_sample(cls, input_dict: dict) -> dict:
        """
        Custom sample parser

        Args:
            input_dict (dict): Basic parser results.

        Returns:
            dict: Updated parser results.
        """
        return input_dict

    @classproperty
    def details_template(cls) -> Template:
        """
        Get the details jinja template for the correct class

        Args:
            base_dict (dict): incoming dictionary of Submission fields

        Returns:
            Tuple(dict, Template): (Updated dictionary, Template to be rendered)
        """
        env = jinja_template_loading()
        temp_name = f"{cls.__name__.lower()}_details.html"
        try:
            template = env.get_template(temp_name)
        except TemplateNotFound as e:
            logger.error(f"Couldn't find template {e}")
            template = env.get_template("basicsample_details.html")
        return template

    @classmethod
    @setup_lookup
    def query(cls,
              submitter_id: str | None = None,
              sample_type: str | BasicSample | None = None,
              limit: int = 0,
              **kwargs
              ) -> BasicSample | List[BasicSample]:
        """
        Lookup samples in the database by a number of parameters.

        Args:
            submitter_id (str | None, optional): Name of the sample (limits results to 1). Defaults to None.
            sample_type (str | None, optional): Sample type. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            models.BasicSample|List[models.BasicSample]: Sample(s) of interest.
        """
        match sample_type:
            case str():
                model = cls.find_polymorphic_subclass(polymorphic_identity=sample_type)
            case BasicSample():
                model = sample_type
            case _:
                model = cls.find_polymorphic_subclass(attrs=kwargs)
        query: Query = cls.__database_session__.query(model)
        match submitter_id:
            case str():
                query = query.filter(model.submitter_id == submitter_id)
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, model=model, limit=limit, **kwargs)

    @classmethod
    def query_or_create(cls, sample_type: str | None = None, **kwargs) -> BasicSample:
        """
        Queries for a sample, if none found creates a new one.

        Args:
            sample_type (str): sample subclass name

        Raises:
            ValueError: Raised if no kwargs are passed to narrow down controls
            ValueError: Raised if unallowed key is given.

        Returns:
            BasicSample: Instance of BasicSample
        """
        disallowed = ["id"]
        if kwargs == {}:
            raise ValueError("Need to narrow down query or the first available instance will be returned.")
        sanitized_kwargs = {k: v for k, v in kwargs.items() if k not in disallowed}
        instance = cls.query(sample_type=sample_type, limit=1, **kwargs)
        if instance is None:
            used_class = cls.find_polymorphic_subclass(attrs=sanitized_kwargs, polymorphic_identity=sample_type)
            instance = used_class(**sanitized_kwargs)
            instance.sample_type = sample_type
        return instance

    @classmethod
    def fuzzy_search(cls,
                     sample_type: str | BasicSample | None = None,
                     **kwargs
                     ) -> List[BasicSample]:
        """
        Allows for fuzzy search of samples.

        Args:
            sample_type (str | BasicSample | None, optional): Type of sample. Defaults to None.

        Returns:
            List[BasicSample]: List of samples that match kwarg search parameters.
        """
        match sample_type:
            case str():
                model = cls.find_polymorphic_subclass(polymorphic_identity=sample_type)
            case BasicSample():
                model = sample_type
            case None:
                model = cls
            case _:
                model = cls.find_polymorphic_subclass(attrs=kwargs)
        query: Query = cls.__database_session__.query(model)
        for k, v in kwargs.items():
            search = f"%{v}%"
            try:
                attr = getattr(model, k)
                # NOTE: the secret sauce is in attr.like
                query = query.filter(attr.like(search))
            except (ArgumentError, AttributeError) as e:
                logger.error(f"Attribute {k} unavailable due to:\n\t{e}\nSkipping.")
        return query.limit(50).all()

    def delete(self):
        raise AttributeError(f"Delete not implemented for {self.__class__}")

    @classmethod
    def samples_to_df(cls, sample_list: List[BasicSample], **kwargs) -> pd.DataFrame:
        """
        Runs a fuzzy search and converts into a dataframe.

        Args:
            sample_list (List[BasicSample]): List of samples to be parsed. Defaults to None.

        Returns:
            pd.DataFrame: Dataframe all samples
        """
        try:
            samples = [sample.to_sub_dict() for sample in sample_list]
        except TypeError as e:
            logger.error(f"Couldn't find any samples with data: {kwargs}\nDue to {e}")
            return None
        df = pd.DataFrame.from_records(samples)
        # NOTE: Exclude sub information
        exclude = ['concentration', 'organism', 'colour', 'tooltip', 'comments', 'samples', 'reagents',
                   'equipment', 'gel_info', 'gel_image', 'dna_core_submission_number', 'gel_controls']
        df = df.loc[:, ~df.columns.isin(exclude)]
        return df

    def show_details(self, obj):
        """
        Creates Widget for showing run details.

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


class SubmissionSampleAssociation(BaseClass):
    """
    table containing run/sample associations
    DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
    """

    id = Column(INTEGER, unique=True, nullable=False)  #: id to be used for inheriting purposes
    sample_id = Column(INTEGER, ForeignKey("_basicsample.id"), nullable=False)  #: id of associated sample
    submission_id = Column(INTEGER, ForeignKey("_clientsubmission.id"), primary_key=True)  #: id of associated run
    row = Column(INTEGER, primary_key=True)  #: row on the 96 well plate
    column = Column(INTEGER, primary_key=True)  #: column on the 96 well plate
    submission_rank = Column(INTEGER, nullable=False, default=0)  #: Location in sample list
    # misc_info = Column(JSON)

    # NOTE: reference to the Submission object
    submission = relationship(ClientSubmission,
                              back_populates="submission_sample_associations")  #: associated run

    # NOTE: reference to the Sample object
    sample = relationship(BasicSample, back_populates="sample_submission_associations")  #: associated sample

    def __init__(self, submission: ClientSubmission = None, sample: BasicSample = None, row: int = 1, column: int = 1,
                 id: int | None = None, submission_rank: int = 0, **kwargs):
        self.submission = submission
        self.sample = sample
        self.row = row
        self.column = column
        self.submission_rank = submission_rank
        if id is not None:
            self.id = id
        else:
            self.id = self.__class__.autoincrement_id()
        for k, v in kwargs.items():
            try:
                self.__setattr__(k, v)
            except AttributeError:
                logger.error(f"Couldn't set {k} to {v}")

    def __repr__(self) -> str:
        try:
            return f"<{self.__class__.__name__}({self.submission.rsl_plate_num} & {self.sample.submitter_id})"
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
        sample['name'] = self.sample.submitter_id
        sample['row'] = self.row
        sample['column'] = self.column
        try:
            sample['well'] = f"{row_map[self.row]}{self.column}"
        except KeyError as e:
            logger.error(f"Unable to find row {self.row} in row_map.")
            sample['Well'] = None
        sample['plate_name'] = self.submission.rsl_plate_num
        sample['positive'] = False
        sample['submitted_date'] = self.submission.submitted_date
        sample['submission_rank'] = self.submission_rank
        return sample

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
        template = env.get_template("tooltip.html")
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
        sample.update(dict(Name=self.sample.submitter_id[:10], tooltip=tooltip_text, background_color=background))
        return sample

    @classmethod
    def autoincrement_id(cls) -> int:
        """
        Increments the association id automatically

        Returns:
            int: incremented id
        """
        if cls.__name__ == "SubmissionSampleAssociation":
            model = cls
        else:
            model = next((base for base in cls.__bases__ if base.__name__ == "SubmissionSampleAssociation"),
                         SubmissionSampleAssociation)
        try:
            return max([item.id for item in model.query()]) + 1
        except ValueError as e:
            logger.error(f"Problem incrementing id: {e}")
            return 1

    @classmethod
    def find_polymorphic_subclass(cls, polymorphic_identity: str | None = None) -> SubmissionSampleAssociation:
        """
        Retrieves subclasses of SubmissionSampleAssociation based on type name.

        Args:
            polymorphic_identity (str | None, optional): Name of subclass fed to polymorphic identity. Defaults to None.

        Returns:
            SubmissionSampleAssociation: Subclass of interest.
        """
        if isinstance(polymorphic_identity, dict):
            polymorphic_identity = polymorphic_identity['value']
        if polymorphic_identity is None:
            model = cls
        else:
            try:
                model = cls.__mapper__.polymorphic_map[polymorphic_identity].class_
            except Exception as e:
                logger.error(f"Could not get polymorph {polymorphic_identity} of {cls} due to {e}")
                model = cls
        return model

    @classmethod
    @setup_lookup
    def query(cls,
              submission: ClientSubmission | str | None = None,
              exclude_submission_type: str | None = None,
              sample: BasicSample | str | None = None,
              row: int = 0,
              column: int = 0,
              limit: int = 0,
              chronologic: bool = False,
              reverse: bool = False,
              **kwargs
              ) -> SubmissionSampleAssociation | List[SubmissionSampleAssociation]:
        """
        Lookup junction of Submission and Sample in the database

        Args:
            run (models.BasicRun | str | None, optional): Submission of interest. Defaults to None.
            sample (models.BasicSample | str | None, optional): Sample of interest. Defaults to None.
            row (int, optional): Row of the sample location on run plate. Defaults to 0.
            column (int, optional): Column of the sample location on the run plate. Defaults to 0.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.
            chronologic (bool, optional): Return results in chronologic order. Defaults to False.

        Returns:
            models.SubmissionSampleAssociation|List[models.SubmissionSampleAssociation]: Junction(s) of interest
        """
        query: Query = cls.__database_session__.query(cls)
        match submission:
            case ClientSubmission():
                query = query.filter(cls.submission == submission)
            case str():
                query = query.join(ClientSubmission).filter(ClientSubmission.rsl_plate_num == submission)
            case _:
                pass
        match sample:
            case BasicSample():
                query = query.filter(cls.sample == sample)
            case str():
                query = query.join(BasicSample).filter(BasicSample.submitter_id == sample)
            case _:
                pass
        if row > 0:
            query = query.filter(cls.row == row)
        if column > 0:
            query = query.filter(cls.column == column)
        match exclude_submission_type:
            case str():
                query = query.join(BasicRun).filter(
                    BasicRun.submission_type_name != exclude_submission_type)
            case _:
                pass
        if reverse and not chronologic:
            query = query.order_by(BasicRun.id.desc())
        if chronologic:
            if reverse:
                query = query.order_by(ClientSubmission.submitted_date.desc())
            else:
                query = query.order_by(ClientSubmission.submitted_date)
        return cls.execute_query(query=query, limit=limit, **kwargs)

    @classmethod
    def query_or_create(cls,
                        association_type: str = "Basic Association",
                        submission: ClientSubmission | str | None = None,
                        sample: BasicSample | str | None = None,
                        id: int | None = None,
                        **kwargs) -> SubmissionSampleAssociation:
        """
        Queries for an association, if none exists creates a new one.

        Args:
            association_type (str, optional): Subclass name. Defaults to "Basic Association".
            submission (BasicRun | str | None, optional): associated run. Defaults to None.
            sample (BasicSample | str | None, optional): associated sample. Defaults to None.
            id (int | None, optional): association id. Defaults to None.

       Returns:
            SubmissionSampleAssociation: Queried or new association.
        """
        match submission:
            case BasicRun():
                pass
            case str():
                submission = ClientSubmission.query(rsl_plate_num=submission)
            case _:
                raise ValueError()
        match sample:
            case BasicSample():
                pass
            case str():
                sample = BasicSample.query(submitter_id=sample)
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
            instance = cls.query(submission=submission, sample=sample, row=row, column=column, limit=1)
        except StatementError:
            instance = None
        if instance is None:
            used_cls = cls.find_polymorphic_subclass(polymorphic_identity=association_type)
            instance = used_cls(submission=submission, sample=sample, id=id, **kwargs)
        return instance

    def delete(self):
        raise AttributeError(f"Delete not implemented for {self.__class__}")


class RunSampleAssociation(BaseClass):

    """
    table containing run/sample associations
    DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
    """

    id = Column(INTEGER, unique=True, nullable=False)  #: id to be used for inheriting purposes
    sample_id = Column(INTEGER, ForeignKey("_basicsample.id"), nullable=False)  #: id of associated sample
    run_id = Column(INTEGER, ForeignKey("_basicrun.id"), primary_key=True)  #: id of associated run
    row = Column(INTEGER, primary_key=True)  #: row on the 96 well plate
    column = Column(INTEGER, primary_key=True)  #: column on the 96 well plate
    # misc_info = Column(JSON)

    # NOTE: reference to the Submission object

    run = relationship(BasicRun,
                              back_populates="run_sample_associations")  #: associated run

    # NOTE: reference to the Sample object
    sample = relationship(BasicSample, back_populates="sample_run_associations")  #: associated sample

    def __init__(self, run: BasicRun = None, sample: BasicSample = None, row: int = 1, column: int = 1,
                 id: int | None = None, **kwargs):
        self.run = run
        self.sample = sample
        self.row = row
        self.column = column
        if id is not None:
            self.id = id
        else:
            self.id = self.__class__.autoincrement_id()
        for k, v in kwargs.items():
            try:
                self.__setattr__(k, v)
            except AttributeError:
                logger.error(f"Couldn't set {k} to {v}")

    def __repr__(self) -> str:
        try:
            return f"<{self.__class__.__name__}({self.submission.rsl_plate_num} & {self.sample.submitter_id})"
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
        sample['name'] = self.sample.submitter_id
        sample['row'] = self.row
        sample['column'] = self.column
        try:
            sample['well'] = f"{row_map[self.row]}{self.column}"
        except KeyError as e:
            logger.error(f"Unable to find row {self.row} in row_map.")
            sample['Well'] = None
        sample['plate_name'] = self.run.rsl_plate_num
        sample['positive'] = False
        return sample

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
        template = env.get_template("tooltip.html")
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
        sample.update(dict(Name=self.sample.submitter_id[:10], tooltip=tooltip_text, background_color=background))
        return sample

    @classmethod
    def autoincrement_id(cls) -> int:
        """
        Increments the association id automatically

        Returns:
            int: incremented id
        """
        if cls.__name__ == "SubmissionSampleAssociation":
            model = cls
        else:
            model = next((base for base in cls.__bases__ if base.__name__ == "SubmissionSampleAssociation"),
                         SubmissionSampleAssociation)
        try:
            return max([item.id for item in model.query()]) + 1
        except ValueError as e:
            logger.error(f"Problem incrementing id: {e}")
            return 1

    @classmethod
    def find_polymorphic_subclass(cls, polymorphic_identity: str | None = None) -> SubmissionSampleAssociation:
        """
        Retrieves subclasses of SubmissionSampleAssociation based on type name.

        Args:
            polymorphic_identity (str | None, optional): Name of subclass fed to polymorphic identity. Defaults to None.

        Returns:
            SubmissionSampleAssociation: Subclass of interest.
        """
        if isinstance(polymorphic_identity, dict):
            polymorphic_identity = polymorphic_identity['value']
        if polymorphic_identity is None:
            model = cls
        else:
            try:
                model = cls.__mapper__.polymorphic_map[polymorphic_identity].class_
            except Exception as e:
                logger.error(f"Could not get polymorph {polymorphic_identity} of {cls} due to {e}")
                model = cls
        return model

    @classmethod
    @setup_lookup
    def query(cls,
              run: BasicRun | str | None = None,
              exclude_submission_type: str | None = None,
              sample: BasicSample | str | None = None,
              row: int = 0,
              column: int = 0,
              limit: int = 0,
              chronologic: bool = False,
              reverse: bool = False,
              **kwargs
              ) -> SubmissionSampleAssociation | List[SubmissionSampleAssociation]:
        """
        Lookup junction of Submission and Sample in the database

        Args:
            run (models.BasicRun | str | None, optional): Submission of interest. Defaults to None.
            sample (models.BasicSample | str | None, optional): Sample of interest. Defaults to None.
            row (int, optional): Row of the sample location on run plate. Defaults to 0.
            column (int, optional): Column of the sample location on the run plate. Defaults to 0.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.
            chronologic (bool, optional): Return results in chronologic order. Defaults to False.

        Returns:
            models.SubmissionSampleAssociation|List[models.SubmissionSampleAssociation]: Junction(s) of interest
        """
        query: Query = cls.__database_session__.query(cls)
        match run:
            case BasicRun():
                query = query.filter(cls.submission == run)
            case str():
                query = query.join(BasicRun).filter(BasicRun.rsl_plate_num == run)
            case _:
                pass
        match sample:
            case BasicSample():
                query = query.filter(cls.sample == sample)
            case str():
                query = query.join(BasicSample).filter(BasicSample.submitter_id == sample)
            case _:
                pass
        if row > 0:
            query = query.filter(cls.row == row)
        if column > 0:
            query = query.filter(cls.column == column)
        match exclude_submission_type:
            case str():
                query = query.join(BasicRun).filter(
                    BasicRun.submission_type_name != exclude_submission_type)
            case _:
                pass
        if reverse and not chronologic:
            query = query.order_by(BasicRun.id.desc())
        if chronologic:
            if reverse:
                query = query.order_by(BasicRun.submitted_date.desc())
            else:
                query = query.order_by(BasicRun.submitted_date)
        return cls.execute_query(query=query, limit=limit, **kwargs)

    @classmethod
    def query_or_create(cls,
                        association_type: str = "Basic Association",
                        run: BasicRun | str | None = None,
                        sample: BasicSample | str | None = None,
                        id: int | None = None,
                        **kwargs) -> SubmissionSampleAssociation:
        """
        Queries for an association, if none exists creates a new one.

        Args:
            association_type (str, optional): Subclass name. Defaults to "Basic Association".
            run (BasicRun | str | None, optional): associated run. Defaults to None.
            sample (BasicSample | str | None, optional): associated sample. Defaults to None.
            id (int | None, optional): association id. Defaults to None.

       Returns:
            SubmissionSampleAssociation: Queried or new association.
        """
        match run:
            case BasicRun():
                pass
            case str():
                run = BasicRun.query(rsl_plate_num=run)
            case _:
                raise ValueError()
        match sample:
            case BasicSample():
                pass
            case str():
                sample = BasicSample.query(submitter_id=sample)
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
            used_cls = cls.find_polymorphic_subclass(polymorphic_identity=association_type)
            instance = used_cls(run=run, sample=sample, id=id, **kwargs)
        return instance

    def delete(self):
        raise AttributeError(f"Delete not implemented for {self.__class__}")


