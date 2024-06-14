"""
Models for the main submission and sample types.
"""
from __future__ import annotations

import sys
from getpass import getuser
import logging, uuid, tempfile, re, yaml, base64
from zipfile import ZipFile
from tempfile import TemporaryDirectory
from operator import attrgetter, itemgetter
from pprint import pformat
from . import BaseClass, Reagent, SubmissionType, KitType, Organization, Contact, Tips, TipRole, SubmissionTipsAssociation
from sqlalchemy import Column, String, TIMESTAMP, INTEGER, ForeignKey, JSON, FLOAT, case
from sqlalchemy.orm import relationship, validates, Query
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.exc import OperationalError as AlcOperationalError, IntegrityError as AlcIntegrityError, StatementError, \
    ArgumentError
from sqlite3 import OperationalError as SQLOperationalError, IntegrityError as SQLIntegrityError
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.drawing.image import Image as OpenpyxlImage
from tools import check_not_nan, row_map, setup_lookup, jinja_template_loading, rreplace
from datetime import datetime, date
from typing import List, Any, Tuple, Literal
from dateutil.parser import parse
from dateutil.parser import ParserError
from pathlib import Path
from jinja2.exceptions import TemplateNotFound
from jinja2 import Template

logger = logging.getLogger(f"submissions.{__name__}")


class BasicSubmission(BaseClass):
    """
    Concrete of basic submission which polymorphs into BacterialCulture and Wastewater
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    rsl_plate_num = Column(String(32), unique=True, nullable=False)  #: RSL name (e.g. RSL-22-0012)
    submitter_plate_num = Column(String(127), unique=True)  #: The number given to the submission by the submitting lab
    submitted_date = Column(TIMESTAMP)  #: Date submission received
    submitting_lab = relationship("Organization", back_populates="submissions")  #: client org
    submitting_lab_id = Column(INTEGER, ForeignKey("_organization.id", ondelete="SET NULL",
                                                   name="fk_BS_sublab_id"))  #: client lab id from _organizations
    sample_count = Column(INTEGER)  #: Number of samples in the submission
    extraction_kit = relationship("KitType", back_populates="submissions")  #: The extraction kit used
    extraction_kit_id = Column(INTEGER, ForeignKey("_kittype.id", ondelete="SET NULL",
                                                   name="fk_BS_extkit_id"))  #: id of joined extraction kit
    submission_type_name = Column(String, ForeignKey("_submissiontype.name", ondelete="SET NULL",
                                                     name="fk_BS_subtype_name"))  #: name of joined submission type
    technician = Column(String(64))  #: initials of processing tech(s)
    # Move this into custom types?
    reagents_id = Column(String, ForeignKey("_reagent.id", ondelete="SET NULL",
                                            name="fk_BS_reagents_id"))  #: id of used reagents
    extraction_info = Column(JSON)  #: unstructured output from the extraction table logger.
    run_cost = Column(
        FLOAT(2))  #: total cost of running the plate. Set from constant and mutable kit costs at time of creation.
    signed_by = Column(String(32))  #: user name of person who submitted the submission to the database.
    comment = Column(JSON)  #: user notes
    submission_category = Column(
        String(64))  #: ["Research", "Diagnostic", "Surveillance", "Validation"], else defaults to submission_type_name
    cost_centre = Column(
        String(64))  #: Permanent storage of used cost centre in case organization field changed in the future.
    contact = relationship("Contact", back_populates="submissions")  #: client org
    contact_id = Column(INTEGER, ForeignKey("_contact.id", ondelete="SET NULL",
                                                   name="fk_BS_contact_id"))  #: client lab id from _organizations

    submission_sample_associations = relationship(
        "SubmissionSampleAssociation",
        back_populates="submission",
        cascade="all, delete-orphan",
    )  #: Relation to SubmissionSampleAssociation

    samples = association_proxy("submission_sample_associations",
                                "sample")  #: Association proxy to SubmissionSampleAssociation.samples

    submission_reagent_associations = relationship(
        "SubmissionReagentAssociation",
        back_populates="submission",
        cascade="all, delete-orphan",
    )  #: Relation to SubmissionReagentAssociation

    reagents = association_proxy("submission_reagent_associations",
                                 "reagent")  #: Association proxy to SubmissionReagentAssociation.reagent

    submission_equipment_associations = relationship(
        "SubmissionEquipmentAssociation",
        back_populates="submission",
        cascade="all, delete-orphan"
    )  #: Relation to Equipment

    equipment = association_proxy("submission_equipment_associations",
                                  "equipment")  #: Association proxy to SubmissionEquipmentAssociation.equipment

    submission_tips_associations = relationship(
        "SubmissionTipsAssociation",
        back_populates="submission",
        cascade="all, delete-orphan")

    tips = association_proxy("submission_tips_associations",
                             "tips")

    # NOTE: Allows for subclassing into ex. BacterialCulture, Wastewater, etc.
    __mapper_args__ = {
        "polymorphic_identity": "Basic Submission",
        "polymorphic_on": submission_type_name,
        "with_polymorphic": "*",
    }

    def __repr__(self) -> str:
        """
        Returns:
            str: Representation of this BasicSubmission
        """
        submission_type = self.submission_type or "Basic"
        return f"{submission_type}Submission({self.rsl_plate_num})"

    @classmethod
    def jsons(cls) -> List[str]:
        """
        Get list of JSON db columns

        Returns:
            List[str]: List of column names
        """        
        output = [item.name for item in cls.__table__.columns if isinstance(item.type, JSON)]
        if issubclass(cls, BasicSubmission) and not cls.__name__ == "BasicSubmission":
            output += BasicSubmission.jsons()
        return output

    @classmethod
    def timestamps(cls) -> List[str]:
        """
        Get list of TIMESTAMP columns

        Returns:
            List[str]: List of column names
        """        
        output = [item.name for item in cls.__table__.columns if isinstance(item.type, TIMESTAMP)]
        if issubclass(cls, BasicSubmission) and not cls.__name__ == "BasicSubmission":
            output += BasicSubmission.timestamps()
        return output

    # TODO: Beef up this to include info_map from DB
    @classmethod
    def get_default_info(cls, *args):
        # NOTE: Create defaults for all submission_types
        parent_defs = super().get_default_info()
        recover = ['filepath', 'samples', 'csv', 'comment', 'equipment']
        dicto = dict(
            details_ignore=['excluded', 'reagents', 'samples',
                            'extraction_info', 'comment', 'barcode',
                            'platemap', 'export_map', 'equipment', 'tips'],
            # NOTE: Fields not placed in ui form
            form_ignore=['reagents', 'ctx', 'id', 'cost', 'extraction_info', 'signed_by', 'comment'] + recover,
            # NOTE: Fields not placed in ui form to be moved to pydantic
            form_recover=recover
        )
        # logger.debug(dicto['singles'])
        # NOTE: Singles tells the query which fields to set limit to 1
        dicto['singles'] = parent_defs['singles']
        # logger.debug(dicto['singles'])
        # NOTE: Grab subtype specific info.
        output = {}
        for k, v in dicto.items():
            if len(args) > 0 and k not in args:
                # logger.debug(f"Don't want {k}")
                continue
            else:
                output[k] = v
        st = cls.get_submission_type()
        if st is None:
            logger.error("No default info for BasicSubmission.")
        else:
            output['submission_type'] = st.name
            for k, v in st.defaults.items():
                if len(args) > 0 and k not in args:
                    # logger.debug(f"Don't want {k}")
                    continue
                else:
                    match v:
                        case list():
                            output[k] += v
                        case _:
                            output[k] = v
        if len(args) == 1:
            return output[args[0]]
        return output

    @classmethod
    def get_submission_type(cls) -> SubmissionType:
        """
        Gets the SubmissionType associated with this class

        Returns:
            SubmissionType: SubmissionType with name equal to this polymorphic identity
        """        
        name = cls.__mapper_args__['polymorphic_identity']
        return SubmissionType.query(name=name)

    @classmethod
    def construct_info_map(cls, mode:Literal["read", "write"]) -> dict:
        """
        Method to call submission type's construct info map.

        Args:
            mode (Literal["read", "write"]): Which map to construct.

        Returns:
            dict: Map of info locations.
        """        
        return cls.get_submission_type().construct_info_map(mode=mode)

    @classmethod
    def construct_sample_map(cls) -> dict:
        """
        Method to call submission type's construct_sample_map

        Returns:
            dict: sample location map
        """        
        return cls.get_submission_type().construct_sample_map()

    def to_dict(self, full_data: bool = False, backup: bool = False, report: bool = False) -> dict:
        """
        Constructs dictionary used in submissions summary

        Args:
            full_data (bool, optional): indicates if sample dicts to be constructed. Defaults to False.
            backup (bool, optional): passed to adjust_to_dict_samples. Defaults to False.

        Returns:
            dict: dictionary used in submissions summary and details
        """
        # NOTE: get lab from nested organization object
        # logger.debug(f"Converting {self.rsl_plate_num} to dict...")
        try:
            sub_lab = self.submitting_lab.name
        except AttributeError:
            sub_lab = None
        try:
            sub_lab = sub_lab.replace("_", " ").title()
        except AttributeError:
            pass
        # NOTE: get extraction kit name from nested kit object
        try:
            ext_kit = self.extraction_kit.name
        except AttributeError:
            ext_kit = None
        # NOTE: load scraped extraction info
        try:
            ext_info = self.extraction_info
        except TypeError:
            ext_info = None
        output = {
            "id": self.id,
            "plate_number": self.rsl_plate_num,
            "submission_type": self.submission_type_name,
            "submitter_plate_number": self.submitter_plate_num,
            "submitted_date": self.submitted_date.strftime("%Y-%m-%d"),
            "submitting_lab": sub_lab,
            "sample_count": self.sample_count,
            "extraction_kit": ext_kit,
            "cost": self.run_cost
        }
        if report:
            return output
        if full_data:
            # logger.debug(f"Attempting reagents.")
            try:
                reagents = [item.to_sub_dict(extraction_kit=self.extraction_kit) for item in
                            self.submission_reagent_associations]
                for k in self.extraction_kit.construct_xl_map_for_use(self.submission_type):
                    if k == 'info':
                        continue
                    if not any([item['role'] == k for item in reagents]):
                        reagents.append(
                            dict(role=k, name="Not Applicable", lot="NA", expiry=date(year=1970, month=1, day=1),
                                 missing=True))
            except Exception as e:
                logger.error(f"We got an error retrieving reagents: {e}")
                reagents = None
            # logger.debug(f"Running samples.")
            samples = self.adjust_to_dict_samples(backup=backup)
            # logger.debug("Running equipment")
            try:
                equipment = [item.to_sub_dict() for item in self.submission_equipment_associations]
                if not equipment:
                    equipment = None
            except Exception as e:
                logger.error(f"Error setting equipment: {e}")
                equipment = None
            try:
                tips = [item.to_sub_dict() for item in self.submission_tips_associations]
                if not tips:
                    tips = None
            except Exception as e:
                logger.error(f"Error setting tips: {e}")
                tips = None
            cost_centre = self.cost_centre
        else:
            reagents = None
            samples = None
            equipment = None
            tips = None
            cost_centre = None
        # logger.debug("Getting comments")
        try:
            comments = self.comment
        except Exception as e:
            logger.error(f"Error setting comment: {self.comment}, {e}")
            comments = None
        try:
            contact = self.contact.name
        except AttributeError as e:
            logger.error(f"Problem setting contact: {e}")
            contact = "NA"
        try:
            contact_phone = self.contact.phone
        except AttributeError:
            contact_phone = "NA"
        output["submission_category"] = self.submission_category
        output["technician"] = self.technician
        output["reagents"] = reagents
        output["samples"] = samples
        output["extraction_info"] = ext_info
        output["comment"] = comments
        output["equipment"] = equipment
        output["tips"] = tips
        output["cost_centre"] = cost_centre
        output["signed_by"] = self.signed_by
        # logger.debug(f"Setting contact to: {contact} of type: {type(contact)}")
        output["contact"] = contact
        output["contact_phone"] = contact_phone
        return output

    def calculate_column_count(self) -> int:
        """
        Calculate the number of columns in this submission 

        Returns:
            int: Number of unique columns.
        """
        # logger.debug(f"Here's the samples: {self.samples}")
        columns = set([assoc.column for assoc in self.submission_sample_associations])
        # logger.debug(f"Here are the columns for {self.rsl_plate_num}: {columns}")
        return len(columns)

    def calculate_base_cost(self):
        """
        Calculates cost of the plate
        """
        # Calculate number of columns based on largest column number
        try:
            cols_count_96 = self.calculate_column_count()
        except Exception as e:
            logger.error(f"Column count error: {e}")
        # Get kit associated with this submission
        assoc = [item for item in self.extraction_kit.kit_submissiontype_associations if
                 item.submission_type == self.submission_type][0]
        # logger.debug(f"Came up with association: {assoc}")
        # If every individual cost is 0 this is probably an old plate.
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

    def hitpick_plate(self) -> list:
        """
        Returns positve sample locations for plate

        Returns:
            list: list of htipick dictionaries for each sample
        """
        output_list = [assoc.to_hitpick() for assoc in self.submission_sample_associations]
        return output_list

    def make_plate_map(self, plate_rows: int = 8, plate_columns=12) -> str:
        """
        Constructs an html based plate map for submission details.

        Args:
            sample_list (list): List of submission samples
            plate_rows (int, optional): Number of rows in the plate. Defaults to 8.
            plate_columns (int, optional): Number of columns in the plate. Defaults to 12.

        Returns:
            str: html output string.
        """
        # logger.debug("Creating basic hitpick")
        sample_list = self.hitpick_plate()
        # logger.debug("Setting background colours")
        for sample in sample_list:
            if sample['positive']:
                sample['background_color'] = "#f10f07"
            else:
                if "colour" in sample.keys():
                    sample['background_color'] = "#69d84f"
                else:
                    sample['background_color'] = "#80cbc4"
        output_samples = []
        # logger.debug("Setting locations.")
        for column in range(1, plate_columns + 1):
            for row in range(1, plate_rows + 1):
                try:
                    well = [item for item in sample_list if item['row'] == row and item['column'] == column][0]
                except IndexError:
                    well = dict(name="", row=row, column=column, background_color="#ffffff")
                output_samples.append(well)
        env = jinja_template_loading()
        template = env.get_template("plate_map.html")
        html = template.render(samples=output_samples, PLATE_ROWS=plate_rows, PLATE_COLUMNS=plate_columns)
        return html + "<br/>"

    def get_used_equipment(self) -> List[str]:
        """
        Gets EquipmentRole names associated with this BasicSubmission

        Returns:
            List[str]: List of names
        """
        return [item.role for item in self.submission_equipment_associations]

    @classmethod
    def submissions_to_df(cls, submission_type: str | None = None, limit: int = 0, chronologic:bool=True) -> pd.DataFrame:
        """
        Convert all submissions to dataframe

        Args:
            submission_type (str | None, optional): Filter by SubmissionType. Defaults to None.
            limit (int, optional): Maximum number of results to return. Defaults to 0.

        Returns:
            pd.DataFrame: Pandas Dataframe of all relevant submissions
        """
        # logger.debug(f"Querying Type: {submission_type}")
        # logger.debug(f"Using limit: {limit}")
        # use lookup function to create list of dicts
        subs = [item.to_dict() for item in cls.query(submission_type=submission_type, limit=limit, chronologic=chronologic)]
        # logger.debug(f"Got {len(subs)} submissions.")
        df = pd.DataFrame.from_records(subs)
        # logger.debug(f"Column names: {df.columns}")
        # NOTE: Exclude sub information
        excluded = ['controls', 'extraction_info', 'pcr_info', 'comment', 'comments', 'samples', 'reagents',
                    'equipment', 'gel_info', 'gel_image', 'dna_core_submission_number', 'gel_controls',
                    'source_plates', 'pcr_technician', 'ext_technician', 'artic_technician', 'cost_centre',
                    'signed_by', 'artic_date', 'gel_barcode', 'gel_date', 'ngs_date', 'contact_phone', 'contact', 'tips']
        for item in excluded:
            try:
                df = df.drop(item, axis=1)
            except:
                logger.warning(f"Couldn't drop '{item}' column from submissionsheet df.")
        if chronologic:
            df.sort_values(by="id", axis=0, inplace=True, ascending=False)
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
                # logger.debug(f"Looking up kit {value}")
                field_value = KitType.query(name=value)
                # logger.debug(f"Got {field_value} for kit {value}")
            case "submitting_lab":
                # logger.debug(f"Looking up organization: {value}")
                field_value = Organization.query(name=value)
                # logger.debug(f"Got {field_value} for organization {value}")
            case "contact":
                field_value = Contact.query(name=value)
            case "samples":
                for sample in value:
                    # logger.debug(f"Parsing {sample} to sql.")
                    sample, _ = sample.to_sql(submission=self)
                return
            case "reagents":
                logger.debug(f"Reagents coming into SQL: {value}")
                field_value = [reagent['value'].to_sql()[0] if isinstance(reagent, dict) else reagent.to_sql()[0] for
                               reagent in value]
                logger.debug(f"Reagents coming out of SQL: {field_value}")
            case "submission_type":
                field_value = SubmissionType.query(name=value)
            case "sample_count":
                if value == None:
                    field_value = len(self.samples)
                else:
                    field_value = value
            case "ctx" | "csv" | "filepath" | "equipment":
                return
            case item if item in self.jsons():
                logger.debug(f"Setting JSON attribute.")
                existing = self.__getattribute__(key)
                if value is None or value in ['', 'null']:
                    logger.error(f"No value given, not setting.")
                    return
                if existing is None:
                    existing = []
                if value in existing:
                    logger.warning("Value already exists. Preventing duplicate addition.")
                    return
                else:
                    if isinstance(value, list):
                        existing += value
                    else:
                        if value is not None:
                            existing.append(value)
                self.__setattr__(key, existing)
                flag_modified(self, key)
                return
            case _:
                try:
                    field_value = value.strip()
                except AttributeError:
                    field_value = value
        # insert into field
        try:
            self.__setattr__(key, field_value)
        except AttributeError as e:
            logger.error(f"Could not set {self} attribute {key} to {value} due to \n{e}")

    def update_subsampassoc(self, sample: BasicSample, input_dict: dict):
        """
        Update a joined submission sample association.

        Args:
            sample (BasicSample): Associated sample.
            input_dict (dict): values to be updated

        Returns:
            Result: _description_
        """
        assoc = [item for item in self.submission_sample_associations if item.sample == sample][0]
        for k, v in input_dict.items():
            try:
                setattr(assoc, k, v)
            except AttributeError:
                logger.error(f"Can't set {k} to {v}")
        result = assoc.save()
        return result

    def to_pydantic(self, backup: bool = False) -> "PydSubmission":
        """
        Converts this instance into a PydSubmission

        Returns:
            PydSubmission: converted object.
        """
        from backend.validators import PydSubmission, PydSample, PydReagent, PydEquipment
        dicto = self.to_dict(full_data=True, backup=backup)
        # logger.debug("To dict complete")
        new_dict = {}
        for key, value in dicto.items():
            # logger.debug(f"Checking {key}")
            missing = value is None or value in ['', 'None']
            match key:
                case "reagents":
                    new_dict[key] = [PydReagent(**reagent) for reagent in value]
                case "samples":
                    new_dict[key] = [PydSample(**{k.lower().replace(" ", "_"): v for k, v in sample.items()}) for sample
                                     in dicto['samples']]
                case "equipment":
                    try:
                        new_dict[key] = [PydEquipment(**equipment) for equipment in dicto['equipment']]
                    except TypeError as e:
                        logger.error(f"Possible no equipment error: {e}")
                case "plate_number":
                    new_dict['rsl_plate_num'] = dict(value=value, missing=missing)
                case "submitter_plate_number":
                    new_dict['submitter_plate_num'] = dict(value=value, missing=missing)
                case "id":
                    pass
                case _:
                    # logger.debug(f"Setting dict {key} to {value}")
                    new_dict[key.lower().replace(" ", "_")] = dict(value=value, missing=missing)
            # logger.debug(f"{key} complete after {time()-start}")
        new_dict['filepath'] = Path(tempfile.TemporaryFile().name)
        # logger.debug("Done converting fields.")
        return PydSubmission(**new_dict)

    def save(self, original: bool = True):
        """
        Adds this instance to database and commits.

        Args:
            original (bool, optional): Is this the first save. Defaults to True.
        """
        logger.debug("Saving submission.")
        if original:
            self.uploaded_by = getuser()
        super().save()

    @classmethod
    def get_regex(cls):
        return cls.construct_regex()

    # Polymorphic functions

    @classmethod
    def construct_regex(cls) -> re.Pattern:
        """
        Constructs catchall regex.

        Returns:
            re.Pattern: Regular expression pattern to discriminate between submission types.
        """
        rstring = rf'{"|".join([item.get_regex() for item in cls.__subclasses__()])}'
        regex = re.compile(rstring, flags=re.IGNORECASE | re.VERBOSE)
        return regex

    @classmethod
    def find_polymorphic_subclass(cls, polymorphic_identity: str | SubmissionType | None = None,
                                  attrs: dict | None = None):
        """
        Find subclass based on polymorphic identity or relevant attributes.

        Args:
            polymorphic_identity (str | None, optional): String representing polymorphic identity. Defaults to None.
            attrs (str | SubmissionType | None, optional): Attributes of the relevant class. Defaults to None.

        Returns:
            _type_: Subclass of interest.
        """
        # logger.debug(f"Controlling for dict value")
        if isinstance(polymorphic_identity, dict):
            polymorphic_identity = polymorphic_identity['value']
        if isinstance(polymorphic_identity, SubmissionType):
            polymorphic_identity = polymorphic_identity.name
        model = cls
        match polymorphic_identity:
            case str():
                try:
                    logger.info(f"Recruiting: {cls}")
                    model = [item for item in cls.__subclasses__() if
                             item.__mapper_args__['polymorphic_identity'] == polymorphic_identity][0]
                except Exception as e:
                    logger.error(f"Could not get polymorph {polymorphic_identity} of {cls} due to {e}")
            case _:
                pass
        if attrs is None or len(attrs) == 0:
            return model
        if any([not hasattr(cls, attr) for attr in attrs.keys()]):
            # looks for first model that has all included kwargs
            try:
                model = [subclass for subclass in cls.__subclasses__() if
                         all([hasattr(subclass, attr) for attr in attrs.keys()])][0]
            except IndexError as e:
                raise AttributeError(
                    f"Couldn't find existing class/subclass of {cls} with all attributes:\n{pformat(attrs.keys())}")
        logger.info(f"Recruiting model: {model}")
        return model

    # Child class custom functions
    @classmethod
    def custom_info_parser(cls, input_dict: dict, xl: Workbook | None = None) -> dict:
        """
        Update submission dictionary with type specific information

        Args:
            input_dict (dict): Input sample dictionary
            xl (pd.ExcelFile): original xl workbook, used for child classes mostly

        Returns:
            dict: Updated sample dictionary
        """
        logger.info(f"Calling {cls.__mapper_args__['polymorphic_identity']} info parser.")
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
        logger.info(f"Called {cls.__mapper_args__['polymorphic_identity']} sample parser")
        return input_dict

    @classmethod
    def finalize_parse(cls, input_dict: dict, xl: pd.ExcelFile | None = None, info_map: dict | None = None) -> dict:
        """
        Performs any final custom parsing of the excel file.

        Args:
            input_dict (dict): Parser product up to this point.
            xl (pd.ExcelFile | None, optional): Excel submission form. Defaults to None.
            info_map (dict | None, optional): Map of information locations from SubmissionType. Defaults to None.
            plate_map (dict | None, optional): Constructed plate map of samples. Defaults to None.

        Returns:
            dict: Updated parser product.
        """
        logger.info(f"Called {cls.__mapper_args__['polymorphic_identity']} finalizer")
        return input_dict

    @classmethod
    def custom_info_writer(cls, input_excel: Workbook, info: dict | None = None, backup: bool = False) -> Workbook:
        """
        Adds custom autofill methods for submission

        Args:
            input_excel (Workbook): initial workbook.
            info (dict | None, optional): dictionary of additional info. Defaults to None.
            backup (bool, optional): Whether this is part of a backup operation. Defaults to False.

        Returns:
            Workbook: Updated workbook
        """
        logger.info(f"Hello from {cls.__mapper_args__['polymorphic_identity']} autofill")
        return input_excel

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
        # logger.info(f"Hello from {cls.__mapper_args__['polymorphic_identity']} Enforcer!")
        # return instr
        from backend.validators import RSLNamer
        # logger.debug(f"instr coming into {cls}: {instr}")
        # logger.debug(f"data coming into {cls}: {data}")
        defaults = cls.get_default_info("abbreviation", "submission_type")
        data['abbreviation'] = defaults['abbreviation']
        if 'submission_type' not in data.keys() or data['submission_type'] in [None, ""]:
            data['submission_type'] = defaults['submission_type']
        if instr in [None, ""]:
            # logger.debug("Sending to RSLNamer to make new plate name.")
            outstr = RSLNamer.construct_new_plate_name(data=data)
        else:
            outstr = instr
        if re.search(rf"{data['abbreviation']}", outstr, flags=re.IGNORECASE) is None:
            outstr = re.sub(rf"RSL-?", rf"RSL-{data['abbreviation']}-", outstr, flags=re.IGNORECASE)
        try:
            outstr = re.sub(r"(\d{4})-(\d{2})-(\d{2})", r"\1\2\3", outstr)
            outstr = re.sub(rf"{data['abbreviation']}(\d{6})", rf"{data['abbreviation']}-\1", outstr,
                            flags=re.IGNORECASE).upper()
        except (AttributeError, TypeError) as e:
            logger.error(f"Error making outstr: {e}, sending to RSLNamer to make new plate name.")
            outstr = RSLNamer.construct_new_plate_name(data=data)
        try:
            plate_number = re.search(r"(?:(-|_)\d)(?!\d)", outstr).group().strip("_").strip("-")
            # logger.debug(f"Plate number is: {plate_number}")
        except AttributeError as e:
            plate_number = "1"
        outstr = re.sub(r"(\d{8})(-|_)?\d?(R\d?)?", rf"\1-{plate_number}\3", outstr)
        # logger.debug(f"After addition of plate number the plate name is: {outstr}")
        try:
            repeat = re.search(r"-\dR(?P<repeat>\d)?", outstr).groupdict()['repeat']
            if repeat == None:
                repeat = "1"
        except AttributeError as e:
            repeat = ""
        outstr = re.sub(r"(-\dR)\d?", rf"\1 {repeat}", outstr).replace(" ", "")
        abb = cls.get_default_info('abbreviation')
        return re.sub(rf"{abb}(\d)", rf"{abb}-\1", outstr)

    @classmethod
    def parse_pcr(cls, xl: Workbook, rsl_plate_num: str) -> list:
        """
        Perform custom parsing of pcr info.

        Args:
            xl (pd.DataFrame): pcr info form
            rsl_plate_number (str): rsl plate num of interest

        Returns:
            list: _description_
        """
        # logger.debug(f"Hello from {cls.__mapper_args__['polymorphic_identity']} PCR parser!")
        pcr_sample_map = cls.get_submission_type().sample_map['pcr_samples']
        # logger.debug(f'sample map: {pcr_sample_map}')
        main_sheet = xl[pcr_sample_map['main_sheet']]
        samples = []
        fields = {k: v for k, v in pcr_sample_map.items() if k not in ['main_sheet', 'start_row']}
        for row in main_sheet.iter_rows(min_row=pcr_sample_map['start_row']):
            idx = row[0].row
            sample = {}
            for k, v in fields.items():
                sheet = xl[v['sheet']]
                sample[k] = sheet.cell(row=idx, column=v['column']).value
            samples.append(sample)
        return samples

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
    def custom_sample_autofill_row(cls, sample, worksheet: Worksheet) -> int:
        """
        _summary_

        Args:
            sample (_type_): _description_
            worksheet (Workbook): _description_

        Returns:
            int: _description_
        """
        return None

    @classmethod
    def adjust_autofill_samples(cls, samples: List[Any]) -> List[Any]:
        logger.info(f"Hello from {cls.__mapper_args__['polymorphic_identity']} sampler")
        return samples

    def adjust_to_dict_samples(self, backup: bool = False) -> List[dict]:
        """
        Updates sample dictionaries with custom values

        Args:
            backup (bool, optional): Whether to perform backup. Defaults to False.

        Returns:
            List[dict]: Updated dictionaries
        """
        # logger.debug(f"Hello from {self.__class__.__name__} dictionary sample adjuster.")
        return [item.to_sub_dict() for item in self.submission_sample_associations]

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
        env = jinja_template_loading()
        temp_name = f"{cls.__name__.lower()}_details.html"
        # logger.debug(f"Returning template: {temp_name}")
        try:
            template = env.get_template(temp_name)
        except TemplateNotFound as e:
            logger.error(f"Couldn't find template due to {e}")
            template = env.get_template("basicsubmission_details.html")
        return base_dict, template

    # Query functions

    @classmethod
    @setup_lookup
    def query(cls,
              submission_type: str | SubmissionType | None = None,
              id: int | str | None = None,
              rsl_plate_num: str | None = None,
              start_date: date | str | int | None = None,
              end_date: date | str | int | None = None,
              reagent: Reagent | str | None = None,
              chronologic: bool = False,
              limit: int = 0,
              **kwargs
              ) -> BasicSubmission | List[BasicSubmission]:
        """
        Lookup submissions based on a number of parameters. Overrides parent.

        Args:
            submission_type (str | models.SubmissionType | None, optional): Submission type of interest. Defaults to None.
            id (int | str | None, optional): Submission id in the database (limits results to 1). Defaults to None.
            rsl_plate_num (str | None, optional): Submission name in the database (limits results to 1). Defaults to None.
            start_date (date | str | int | None, optional): Beginning date to search by. Defaults to None.
            end_date (date | str | int | None, optional): Ending date to search by. Defaults to None.
            reagent (models.Reagent | str | None, optional): A reagent used in the submission. Defaults to None.
            chronologic (bool, optional): Return results in chronologic order. Defaults to False.
            limit (int, optional): Maximum number of results to return. Defaults to 0.

        Returns:
            models.BasicSubmission | List[models.BasicSubmission]: Submission(s) of interest
        """
        # logger.debug(f"Incoming kwargs: {kwargs}")
        # NOTE: if you go back to using 'model' change the appropriate cls to model in the query filters
        if submission_type is not None:
            model = cls.find_polymorphic_subclass(polymorphic_identity=submission_type)
        elif len(kwargs) > 0:
            # find the subclass containing the relevant attributes
            # logger.debug(f"Attributes for search: {kwargs}")
            model = cls.find_polymorphic_subclass(attrs=kwargs)
        else:
            model = cls
        query: Query = cls.__database_session__.query(model)
        if start_date is not None and end_date is None:
            logger.warning(f"Start date with no end date, using today.")
            end_date = date.today()
        if end_date is not None and start_date is None:
            logger.warning(f"End date with no start date, using Jan 1, 2023")
            start_date = date(2023, 1, 1)
        if start_date is not None:
            # logger.debug(f"Querying with start date: {start_date} and end date: {end_date}")
            match start_date:
                case date():
                    # logger.debug(f"Lookup BasicSubmission by start_date({start_date})")
                    start_date = start_date.strftime("%Y-%m-%d")
                case int():
                    # logger.debug(f"Lookup BasicSubmission by ordinal start_date {start_date}")
                    start_date = datetime.fromordinal(
                        datetime(1900, 1, 1).toordinal() + start_date - 2).date().strftime("%Y-%m-%d")
                case _:
                    # logger.debug(f"Lookup BasicSubmission by parsed str start_date {start_date}")
                    start_date = parse(start_date).strftime("%Y-%m-%d")
            match end_date:
                case date() | datetime():
                    # logger.debug(f"Lookup BasicSubmission by end_date({end_date})")
                    end_date = end_date.strftime("%Y-%m-%d")
                case int():
                    # logger.debug(f"Lookup BasicSubmission by ordinal end_date {end_date}")
                    end_date = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + end_date - 2).date().strftime(
                        "%Y-%m-%d")
                case _:
                    # logger.debug(f"Lookup BasicSubmission by parsed str end_date {end_date}")
                    end_date = parse(end_date).strftime("%Y-%m-%d")
            # logger.debug(f"Looking up BasicSubmissions from start date: {start_date} and end date: {end_date}")
            # logger.debug(f"Start date {start_date} == End date {end_date}: {start_date == end_date}")
            # logger.debug(f"Compensating for same date by using time")
            if start_date == end_date:
                start_date = datetime.strptime(start_date, "%Y-%m-%d").strftime("%Y-%m-%d %H:%M:%S.%f")
                query = query.filter(model.submitted_date == start_date)
            else:
                query = query.filter(model.submitted_date.between(start_date, end_date))
        # by reagent (for some reason)
        match reagent:
            case str():
                # logger.debug(f"Looking up BasicSubmission with reagent: {reagent}")
                query = query.join(model.submission_reagent_associations).filter(
                    SubmissionSampleAssociation.reagent.lot == reagent)
            case Reagent():
                # logger.debug(f"Looking up BasicSubmission with reagent: {reagent}")
                query = query.join(model.submission_reagent_associations).join(
                    SubmissionSampleAssociation.reagent).filter(Reagent.lot == reagent)
            case _:
                pass
        # by rsl number (returns only a single value)
        match rsl_plate_num:
            case str():
                query = query.filter(model.rsl_plate_num == rsl_plate_num)
                # logger.debug(f"At this point the query gets: {query.all()}")
                limit = 1
            case _:
                pass
        # by id (returns only a single value)
        match id:
            case int():
                # logger.debug(f"Looking up BasicSubmission with id: {id}")
                query = query.filter(model.id == id)
                limit = 1
            case str():
                # logger.debug(f"Looking up BasicSubmission with id: {id}")
                query = query.filter(model.id == int(id))
                limit = 1
            case _:
                pass
        if chronologic:
            query.order_by(cls.submitted_date)
        return cls.execute_query(query=query, model=model, limit=limit, **kwargs)

    @classmethod
    def query_or_create(cls, submission_type: str | SubmissionType | None = None, **kwargs) -> BasicSubmission:
        """
        Returns object from db if exists, else, creates new. Due to need for user input, doesn't see much use ATM.

        Args:
            submission_type (str | SubmissionType | None, optional): Submission type to be created. Defaults to None.

        Raises:
            ValueError: Raised if no kwargs passed.
            ValueError: Raised if disallowed key is passed.

        Returns:
            cls: _description_
        """
        code = 0
        msg = ""
        disallowed = ["id"]
        if kwargs == {}:
            raise ValueError("Need to narrow down query or the first available instance will be returned.")
        for key in kwargs.keys():
            if key in disallowed:
                raise ValueError(
                    f"{key} is not allowed as a query argument as it could lead to creation of duplicate objects. Use .query() instead.")
        instance = cls.query(submission_type=submission_type, limit=1, **kwargs)
        # logger.debug(f"Retrieved instance: {instance}")
        if instance is None:
            used_class = cls.find_polymorphic_subclass(attrs=kwargs, polymorphic_identity=submission_type)
            instance = used_class(**kwargs)
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
            code = 1
            msg = "This submission already exists.\nWould you like to overwrite?"
        return instance, code, msg

    # Custom context events for the ui

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
            obj (_type_, optional): Parent Widget. Defaults to None.

        Raises:
            e: _description_
        """
        from frontend.widgets.pop_ups import QuestionAsker
        # logger.debug("Hello from delete")
        fname = self.__backup_path__.joinpath(f"{self.rsl_plate_num}-backup({date.today().strftime('%Y%m%d')})")
        msg = QuestionAsker(title="Delete?", message=f"Are you sure you want to delete {self.rsl_plate_num}?\n")
        if msg.exec():
            self.backup(fname=fname, full_backup=True)
            self.__database_session__.delete(self)
            try:
                self.__database_session__.commit()
            except (SQLIntegrityError, SQLOperationalError, AlcIntegrityError, AlcOperationalError) as e:
                self.__database_session__.rollback()
                raise e
            obj.setData()

    def show_details(self, obj):
        """
        Creates Widget for showing submission details.

        Args:
            obj (_type_): parent widget
        """
        # logger.debug("Hello from details")
        from frontend.widgets.submission_details import SubmissionDetails
        dlg = SubmissionDetails(parent=obj, sub=self)
        if dlg.exec():
            pass

    def edit(self, obj):
        from frontend.widgets.submission_widget import SubmissionFormWidget
        for widg in obj.app.table_widget.formwidget.findChildren(SubmissionFormWidget):
            # logger.debug(widg)
            widg.setParent(None)
        pyd = self.to_pydantic(backup=True)
        form = pyd.to_form(parent=obj)
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
            self.set_attribute(key='comment', value=comment)
            # logger.debug(self.comment)
            self.save(original=False)

    def add_equipment(self, obj):
        """
        Creates widget for adding equipment to this submission

        Args:
            obj (_type_): parent widget
        """
        from frontend.widgets.equipment_usage import EquipmentUsage
        dlg = EquipmentUsage(parent=obj, submission=self)
        if dlg.exec():
            equipment = dlg.parse_form()
            # logger.debug(f"We've got equipment: {equipment}")
            for equip in equipment:
                # logger.debug(f"Processing: {equip}")
                _, assoc = equip.toSQL(submission=self)
                # logger.debug(f"Appending SubmissionEquipmentAssociation: {assoc}")
                assoc.save()
                if equip.tips:
                    logger.debug("We have tips in this equipment")
                    for tips in equip.tips:
                        tassoc = tips.to_sql(submission=self)
                        tassoc.save()

        else:
            pass

    def backup(self, obj=None, fname: Path | None = None, full_backup: bool = False):
        """
        Exports xlsx and yml info files for this instance.

        Args:
            obj (_type_, optional): _description_. Defaults to None.
            fname (Path | None, optional): Filename of xlsx file. Defaults to None.
            full_backup (bool, optional): Whether or not to make yaml file. Defaults to False.
        """
        # logger.debug("Hello from backup.")
        pyd = self.to_pydantic(backup=True)
        if fname is None:
            from frontend.widgets.functions import select_save_file
            fname = select_save_file(default_name=pyd.construct_filename(), extension="xlsx", obj=obj)
        # logger.debug(fname.name)
        if fname.name == "":
            # logger.debug(f"export cancelled.")
            return
        if full_backup:
            backup = self.to_dict(full_data=True)
            try:
                with open(self.__backup_path__.joinpath(fname.with_suffix(".yml")), "w") as f:
                    yaml.dump(backup, f)
            except KeyError as e:
                logger.error(f"Problem saving yml backup file: {e}")
        writer = pyd.to_writer()
        writer.xl.save(filename=fname.with_suffix(".xlsx"))

# Below are the custom submission types

class BacterialCulture(BasicSubmission):
    """
    derivative submission type from BasicSubmission
    """
    id = Column(INTEGER, ForeignKey('_basicsubmission.id'), primary_key=True)
    controls = relationship("Control", back_populates="submission",
                            uselist=True)  #: A control sample added to submission
    __mapper_args__ = dict(polymorphic_identity="Bacterial Culture",
                           polymorphic_load="inline",
                           inherit_condition=(id == BasicSubmission.id))

    def to_dict(self, full_data: bool = False, backup: bool = False, report: bool = False) -> dict:
        """
        Extends parent class method to add controls to dict

        Returns:
            dict: dictionary used in submissions summary
        """
        output = super().to_dict(full_data=full_data, backup=backup, report=report)
        if report:
            return output
        if full_data:
            output['controls'] = [item.to_sub_dict() for item in self.controls]
        return output

    @classmethod
    def get_regex(cls) -> str:
        """
        Retrieves string for regex construction.

        Returns:
            str: string for regex construction
        """
        return "(?P<Bacterial_Culture>RSL(?:-|_)?BC(?:-|_)?20\d{2}-?\d{2}-?\d{2}(?:(_|-)?\d?([^_0123456789\sA-QS-Z]|$)?R?\d?)?)"

    @classmethod
    def filename_template(cls):
        """
        extends parent
        """
        template = super().filename_template()
        template += "_{{ submitting_lab }}_{{ submitter_plate_num }}"
        return template

    @classmethod
    def finalize_parse(cls, input_dict: dict, xl: pd.ExcelFile | None = None, info_map: dict | None = None) -> dict:
        """
        Extends parent. Currently finds control sample and adds to reagents.

        Args:
            input_dict (dict): _description_
            xl (pd.ExcelFile | None, optional): _description_. Defaults to None.
            info_map (dict | None, optional): _description_. Defaults to None.
            plate_map (dict | None, optional): _description_. Defaults to None.

        Returns:
            dict: _description_
        """
        from . import ControlType
        input_dict = super().finalize_parse(input_dict, xl, info_map)
        # build regex for all control types that have targets
        regex = ControlType.build_positive_regex()
        # search samples for match
        for sample in input_dict['samples']:
            matched = regex.match(sample['submitter_id'])
            if bool(matched):
                # logger.debug(f"Control match found: {sample['submitter_id']}")
                new_lot = matched.group()
                try:
                    pos_control_reg = \
                    [reg for reg in input_dict['reagents'] if reg['role'] == "Bacterial-Positive Control"][0]
                except IndexError:
                    logger.error(f"No positive control reagent listed")
                    return input_dict
                pos_control_reg['lot'] = new_lot
                pos_control_reg['missing'] = False
        return input_dict

    @classmethod
    def custom_sample_autofill_row(cls, sample, worksheet: Worksheet) -> int:
        """
        Extends parent
        """
        # logger.debug(f"Checking {sample.well}")
        # logger.debug(f"here's the worksheet: {worksheet}")
        row = super().custom_sample_autofill_row(sample, worksheet)
        df = pd.DataFrame(list(worksheet.values))
        # logger.debug(f"Here's the dataframe: {df}")
        idx = df[df[0] == sample.well]
        if idx.empty:
            new = f"{sample.well[0]}{sample.well[1:].zfill(2)}"
            logger.debug(f"Checking: {new}")
            idx = df[df[0] == new]
        # logger.debug(f"Here is the row: {idx}")
        row = idx.index.to_list()[0]
        return row + 1


class Wastewater(BasicSubmission):
    """
    derivative submission type from BasicSubmission
    """
    id = Column(INTEGER, ForeignKey('_basicsubmission.id'), primary_key=True)
    ext_technician = Column(String(64))  #: Name of technician doing extraction
    pcr_technician = Column(String(64))  #: Name of technician doing pcr
    pcr_info = Column(JSON)  #: unstructured output from pcr table logger or user(Artic)

    __mapper_args__ = __mapper_args__ = dict(polymorphic_identity="Wastewater",
                                             polymorphic_load="inline",
                                             inherit_condition=(id == BasicSubmission.id))

    def to_dict(self, full_data: bool = False, backup: bool = False, report: bool = False) -> dict:
        """
        Extends parent class method to add controls to dict

        Returns:
            dict: dictionary used in submissions summary
        """
        output = super().to_dict(full_data=full_data, backup=backup, report=report)
        if report:
            return output
        try:
            output['pcr_info'] = self.pcr_info
        except TypeError as e:
            pass
        if self.ext_technician is None or self.ext_technician == "None":
            output['ext_technician'] = self.technician
        else:
            output["ext_technician"] = self.ext_technician
        if self.pcr_technician is None or self.pcr_technician == "None":
            output["pcr_technician"] = self.technician
        else:
            output['pcr_technician'] = self.pcr_technician
        return output

    @classmethod
    def custom_info_parser(cls, input_dict: dict, xl: Workbook | None = None) -> dict:
        """
        Update submission dictionary with type specific information. Extends parent

        Args:
            input_dict (dict): Input sample dictionary

        Returns:
            dict: Updated sample dictionary
        """
        input_dict = super().custom_info_parser(input_dict)
        if xl != None:
            input_dict['csv'] = xl["Copy to import file"]
        return input_dict

    @classmethod
    def parse_pcr(cls, xl: Workbook, rsl_plate_num: str) -> list:
        """
        Parse specific to wastewater samples.
        """
        samples = super().parse_pcr(xl=xl, rsl_plate_num=rsl_plate_num)
        # logger.debug(f'Samples from parent pcr parser: {pformat(samples)}')
        output = []
        for sample in samples:
            # NOTE: remove '-{target}' from controls
            sample['sample'] = re.sub('-N\\d$', '', sample['sample'])
            # NOTE: if sample is already in output skip
            if sample['sample'] in [item['sample'] for item in output]:
                continue
            # NOTE: Set ct values
            sample[f"ct_{sample['target'].lower()}"] = sample['ct'] if isinstance(sample['ct'], float) else 0.0
            # NOTE: Set assessment
            sample[f"{sample['target'].lower()}_status"] = sample['assessment']
            # NOTE: Get sample having other target
            other_targets = [s for s in samples if re.sub('-N\\d$', '', s['sample']) == sample['sample']]
            for s in other_targets:
                sample[f"ct_{s['target'].lower()}"] = s['ct'] if isinstance(s['ct'], float) else 0.0
                sample[f"{s['target'].lower()}_status"] = s['assessment']
            try:
                del sample['ct']
            except KeyError:
                pass
            try:
                del sample['assessment']
            except KeyError:
                pass
            output.append(sample)
        return output

    @classmethod
    def enforce_name(cls, instr: str, data: dict | None = {}) -> str:
        """
        Extends parent
        """
        try:
            # Deal with PCR file.
            instr = re.sub(r"PCR(-|_)", "", instr)
        except (AttributeError, TypeError) as e:
            logger.error(f"Problem using regex: {e}")
        outstr = super().enforce_name(instr=instr, data=data)
        return outstr

    @classmethod
    def get_regex(cls) -> str:
        """
        Retrieves string for regex construction

        Returns:
            str: String for regex construction
        """
        return "(?P<Wastewater>RSL(?:-|_)?WW(?:-|_)?20\d{2}-?\d{2}-?\d{2}(?:(_|-)?\d?([^_0123456789\sA-QS-Z]|$)?R?\d?)?)"

    @classmethod
    def adjust_autofill_samples(cls, samples: List[Any]) -> List[Any]:
        """
        Extends parent
        """
        samples = super().adjust_autofill_samples(samples)
        samples = [item for item in samples if not item.submitter_id.startswith("EN")]
        return samples

    @classmethod
    def custom_sample_autofill_row(cls, sample, worksheet: Worksheet) -> int:
        """
        Extends parent
        """
        # logger.debug(f"Checking {sample.well}")
        # logger.debug(f"here's the worksheet: {worksheet}")
        row = super().custom_sample_autofill_row(sample, worksheet)
        df = pd.DataFrame(list(worksheet.values))
        # logger.debug(f"Here's the dataframe: {df}")
        idx = df[df[1] == sample.sample_location]
        # logger.debug(f"Here is the row: {idx}")
        row = idx.index.to_list()[0]
        return row + 1

    def custom_context_events(self) -> dict:
        events = super().custom_context_events()
        events['Link PCR'] = self.link_pcr
        return events

    def link_pcr(self, obj):
        from backend.excel import PCRParser
        from frontend.widgets import select_open_file
        fname = select_open_file(obj=obj, file_extension="xlsx")
        parser = PCRParser(filepath=fname)
        self.set_attribute("pcr_info", parser.pcr)
        self.save(original=False)
        # logger.debug(f"Got {len(parser.samples)} samples to update!")
        # logger.debug(f"Parser samples: {parser.samples}")
        for sample in self.samples:
            # logger.debug(f"Running update on: {sample}")
            try:
                sample_dict = [item for item in parser.samples if item['sample'] == sample.rsl_number][0]
            except IndexError:
                continue
            self.update_subsampassoc(sample=sample, input_dict=sample_dict)
        # self.report.add_result(Result(msg=f"We added PCR info to {sub.rsl_plate_num}.", status='Information'))


class WastewaterArtic(BasicSubmission):
    """
    derivative submission type for artic wastewater
    """
    id = Column(INTEGER, ForeignKey('_basicsubmission.id'), primary_key=True)
    artic_technician = Column(String(64))  #: Name of technician performing artic
    dna_core_submission_number = Column(String(64))  #: Number used by core as id
    pcr_info = Column(JSON)  #: unstructured output from pcr table logger or user(Artic)
    gel_image = Column(String(64))  #: file name of gel image in zip file
    gel_info = Column(JSON)  #: unstructured data from gel.
    gel_controls = Column(JSON)  #: locations of controls on the gel
    source_plates = Column(JSON)  #: wastewater plates that samples come from
    artic_date = Column(TIMESTAMP)  #: Date Artic Performed
    ngs_date = Column(TIMESTAMP)  #: Date submission received
    gel_date = Column(TIMESTAMP)  #: Date submission received
    gel_barcode = Column(String(16))

    __mapper_args__ = dict(polymorphic_identity="Wastewater Artic",
                           polymorphic_load="inline",
                           inherit_condition=(id == BasicSubmission.id))

    def to_dict(self, full_data: bool = False, backup: bool = False, report: bool = False) -> dict:
        """
        Extends parent class method to add controls to dict

        Returns:
            dict: dictionary used in submissions summary
        """
        output = super().to_dict(full_data=full_data, backup=backup, report=report)
        if self.artic_technician in [None, "None"]:
            output['artic_technician'] = self.technician
        else:
            output['artic_technician'] = self.artic_technician
        if report:
            return output
        output['gel_info'] = self.gel_info
        output['gel_image'] = self.gel_image
        output['dna_core_submission_number'] = self.dna_core_submission_number
        output['source_plates'] = self.source_plates
        output['artic_date'] = self.artic_date or self.submitted_date
        output['ngs_date'] = self.ngs_date or self.submitted_date
        output['gel_date'] = self.gel_date or self.submitted_date
        output['gel_barcode'] = self.gel_barcode
        return output

    @classmethod
    def custom_info_parser(cls, input_dict: dict, xl: Workbook | None = None) -> dict:
        """
        Update submission dictionary with type specific information

        Args:
            input_dict (dict): Input sample dictionary
            xl (pd.ExcelFile): original xl workbook, used for child classes mostly

        Returns:
            dict: Updated sample dictionary
        """
        input_dict = super().custom_info_parser(input_dict)
        # workbook = load_workbook(xl.io, data_only=True)
        ws = xl['Egel results']
        data = [ws.cell(row=ii, column=jj) for jj in range(15, 27) for ii in range(10, 18)]
        data = [cell for cell in data if cell.value is not None and "NTC" in cell.value]
        input_dict['gel_controls'] = [
            dict(sample_id=cell.value, location=f"{row_map[cell.row - 9]}{str(cell.column - 14).zfill(2)}") for cell in
            data]
        ws = xl['First Strand List']
        data = [dict(plate=ws.cell(row=ii, column=3).value, starting_sample=ws.cell(row=ii, column=4).value) for ii in
                range(8, 11)]
        for datum in data:
            if datum['plate'] in ["None", None, ""]:
                continue
            else:
                from backend.validators import RSLNamer
                datum['plate'] = RSLNamer(filename=datum['plate'], sub_type="Wastewater").parsed_name
        input_dict['source_plates'] = data
        return input_dict

    @classmethod
    def enforce_name(cls, instr: str, data: dict = {}) -> str:
        """
        Extends parent
        """
        try:
            # NOTE: Deal with PCR file.
            instr = re.sub(r"Artic", "", instr, flags=re.IGNORECASE)
        except (AttributeError, TypeError) as e:
            logger.error(f"Problem using regex: {e}")
        # logger.debug(f"Before RSL addition: {instr}")
        try:
            instr = instr.replace("-", "")
        except AttributeError:
            instr = date.today().strftime("%Y%m%d")
        instr = re.sub(r"^(\d{6})", f"RSL-AR-\\1", instr)
        # logger.debug(f"name coming out of Artic namer: {instr}")
        outstr = super().enforce_name(instr=instr, data=data)
        return outstr

    @classmethod
    def parse_samples(cls, input_dict: dict) -> dict:
        """
        Update sample dictionary with type specific information. Extends parent.

        Args:
            input_dict (dict): Input sample dictionary

        Returns:
            dict: Updated sample dictionary
        """
        input_dict = super().parse_samples(input_dict)
        input_dict['sample_type'] = "Wastewater Sample"
        # Because generate_sample_object needs the submitter_id and the artic has the "({origin well})"
        # at the end, this has to be done here. No moving to sqlalchemy object :(
        input_dict['submitter_id'] = re.sub(r"\s\(.+\)\s?$", "", str(input_dict['submitter_id'])).strip()
        try:
            input_dict['ww_processing_num'] = input_dict['sample_name_(lims)']
            del input_dict['sample_name_(lims)']
        except KeyError:
            logger.error(f"Unable to set ww_processing_num for sample {input_dict['submitter_id']}")
        try:
            input_dict['ww_full_sample_id'] = input_dict['sample_name_(ww)']
            del input_dict['sample_name_(ww)']
        except KeyError:
            logger.error(f"Unable to set ww_processing_num for sample {input_dict['submitter_id']}")
        year = str(date.today().year)[-2:]
        # if "ENC" in input_dict['submitter_id']:
        if re.search(rf"^{year}-(ENC)", input_dict['submitter_id']):
            input_dict['rsl_number'] = cls.en_adapter(input_str=input_dict['submitter_id'])
        if re.search(rf"^{year}-(RSL)", input_dict['submitter_id']):
            input_dict['rsl_number'] = cls.pbs_adapter(input_str=input_dict['submitter_id'])
        return input_dict

    @classmethod
    def en_adapter(cls, input_str: str) -> str:
        """
        Stopgap solution because WW names their ENs different

        Args:
            input_str (str): input name

        Returns:
            str: output name
        """
        # logger.debug(f"input string raw: {input_str}")
        # Remove letters.
        processed = input_str.replace("RSL", "")
        processed = re.sub(r"\(.*\)$", "", processed).strip()
        processed = re.sub(r"[A-QS-Z]+\d*", "", processed)
        # Remove trailing '-' if any
        processed = processed.strip("-")
        # logger.debug(f"Processed after stripping letters: {processed}")
        try:
            en_num = re.search(r"\-\d{1}$", processed).group()
            processed = rreplace(processed, en_num, "")
        except AttributeError:
            en_num = "1"
        en_num = en_num.strip("-")
        # logger.debug(f"Processed after en_num: {processed}")
        try:
            plate_num = re.search(r"\-\d{1}R?\d?$", processed).group()
            processed = rreplace(processed, plate_num, "")
        except AttributeError:
            plate_num = "1"
        plate_num = plate_num.strip("-")
        # logger.debug(f"Processed after plate-num: {processed}")
        day = re.search(r"\d{2}$", processed).group()
        processed = rreplace(processed, day, "")
        # logger.debug(f"Processed after day: {processed}")
        month = re.search(r"\d{2}$", processed).group()
        processed = rreplace(processed, month, "")
        processed = processed.replace("--", "")
        # logger.debug(f"Processed after month: {processed}")
        year = re.search(r'^(?:\d{2})?\d{2}', processed).group()
        year = f"20{year}"
        final_en_name = f"EN{en_num}-{year}{month}{day}"
        # logger.debug(f"Final EN name: {final_en_name}")
        return final_en_name

    @classmethod
    def pbs_adapter(cls, input_str):
        """
                Stopgap solution because WW names their ENs different

                Args:
                    input_str (str): input name

                Returns:
                    str: output name
                """
        # logger.debug(f"input string raw: {input_str}")
        # Remove letters.
        processed = input_str.replace("RSL", "")
        processed = re.sub(r"\(.*\)$", "", processed).strip()
        processed = re.sub(r"[A-QS-Z]+\d*", "", processed)
        # Remove trailing '-' if any
        processed = processed.strip("-")
        # logger.debug(f"Processed after stripping letters: {processed}")
        # try:
        #     en_num = re.search(r"\-\d{1}$", processed).group()
        #     processed = rreplace(processed, en_num, "")
        # except AttributeError:
        #     en_num = "1"
        # en_num = en_num.strip("-")
        # logger.debug(f"Processed after en_num: {processed}")
        try:
            plate_num = re.search(r"\-\d{1}R?\d?$", processed).group()
            processed = rreplace(processed, plate_num, "")
        except AttributeError:
            plate_num = "1"
        plate_num = plate_num.strip("-")
        # logger.debug(f"Plate num: {plate_num}")
        repeat_num = re.search(r"R(?P<repeat>\d)?$", "PBS20240426-2R").groups()[0]
        if repeat_num is None and "R" in plate_num:
            repeat_num = "1"
        plate_num = re.sub(r"R", rf"R{repeat_num}", plate_num)
        # logger.debug(f"Processed after plate-num: {processed}")
        day = re.search(r"\d{2}$", processed).group()
        processed = rreplace(processed, day, "")
        # logger.debug(f"Processed after day: {processed}")
        month = re.search(r"\d{2}$", processed).group()
        processed = rreplace(processed, month, "")
        processed = processed.replace("--", "")
        # logger.debug(f"Processed after month: {processed}")
        year = re.search(r'^(?:\d{2})?\d{2}', processed).group()
        year = f"20{year}"
        final_en_name = f"PBS{year}{month}{day}-{plate_num}"
        # logger.debug(f"Final EN name: {final_en_name}")
        return final_en_name

    @classmethod
    def get_regex(cls) -> str:
        """
        Retrieves string for regex construction

        Returns:
            str: string for regex construction.
        """
        return "(?P<Wastewater_Artic>(\\d{4}-\\d{2}-\\d{2}(?:-|_)(?:\\d_)?artic)|(RSL(?:-|_)?AR(?:-|_)?20\\d{2}-?\\d{2}-?\\d{2}(?:(_|-)\\d?(\\D|$)R?\\d?)?))"

    @classmethod
    def finalize_parse(cls, input_dict: dict, xl: pd.ExcelFile | None = None, info_map: dict | None = None) -> dict:
        """
        Performs any final custom parsing of the excel file. Extends parent

        Args:
            input_dict (dict): Parser product up to this point.
            xl (pd.ExcelFile | None, optional): Excel submission form. Defaults to None.
            info_map (dict | None, optional): Map of information locations from SubmissionType. Defaults to None.
            plate_map (dict | None, optional): Constructed plate map of samples. Defaults to None.

        Returns:
            dict: Updated parser product.
        """
        input_dict = super().finalize_parse(input_dict, xl, info_map)
        # logger.debug(f"Incoming input_dict: {pformat(input_dict)}")
        # TODO: Move to validator?
        for sample in input_dict['samples']:
            # logger.debug(f"Sample: {sample}")
            if re.search(r"^NTC", sample['submitter_id']):
                sample['submitter_id'] = f"{sample['submitter_id']}-WWG-{input_dict['rsl_plate_num']['value']}"
        input_dict['csv'] = xl["hitpicks_csv_to_export"]
        return input_dict

    @classmethod
    def custom_info_writer(cls, input_excel: Workbook, info: dict | None = None, backup: bool = False) -> Workbook:
        """
        Adds custom autofill methods for submission. Extends Parent

        Args:
            input_excel (Workbook): initial workbook.
            info (dict | None, optional): dictionary of additional info. Defaults to None.
            backup (bool, optional): Whether this is part of a backup operation. Defaults to False.

        Returns:
            Workbook: Updated workbook
        """
        input_excel = super().custom_info_writer(input_excel, info, backup)
        logger.debug(f"Info:\n{pformat(info)}")
        check = 'source_plates' in info.keys() and info['source_plates'] is not None
        if check:
            worksheet = input_excel['First Strand List']
            start_row = 8
            for iii, plate in enumerate(info['source_plates']['value']):
                logger.debug(f"Plate: {plate}")
                row = start_row + iii
                try:
                    worksheet.cell(row=row, column=3, value=plate['plate'])
                except TypeError:
                    pass
                try:
                    worksheet.cell(row=row, column=4, value=plate['starting_sample'])
                except TypeError:
                    pass
        check = 'gel_info' in info.keys() and info['gel_info']['value'] is not None
        if check:
            # logger.debug(f"Gel info check passed.")
            if info['gel_info'] != None:
                # logger.debug(f"Gel info not none.")
                worksheet = input_excel['Egel results']
                start_row = 21
                start_column = 15
                for row, ki in enumerate(info['gel_info']['value'], start=1):
                    # logger.debug(f"ki: {ki}")
                    # logger.debug(f"vi: {vi}")
                    row = start_row + row
                    worksheet.cell(row=row, column=start_column, value=ki['name'])
                    for jjj, kj in enumerate(ki['values'], start=1):
                        # logger.debug(f"kj: {kj}")
                        # logger.debug(f"vj: {vj}")
                        column = start_column + 2 + jjj
                        worksheet.cell(row=start_row, column=column, value=kj['name'])
                        # logger.debug(f"Writing {kj['name']} with value {kj['value']} to row {row}, column {column}")
                        try:
                            worksheet.cell(row=row, column=column, value=kj['value'])
                        except AttributeError:
                            logger.error(f"Failed {kj['name']} with value {kj['value']} to row {row}, column {column}")
        check = 'gel_image' in info.keys() and info['gel_image']['value'] is not None
        if check:
            if info['gel_image'] != None:
                worksheet = input_excel['Egel results']
                # logger.debug(f"We got an image: {info['gel_image']}")
                with ZipFile(cls.__directory_path__.joinpath("submission_imgs.zip")) as zipped:
                    z = zipped.extract(info['gel_image']['value'], Path(TemporaryDirectory().name))
                    img = OpenpyxlImage(z)
                    img.height = 400  # insert image height in pixels as float or int (e.g. 305.5)
                    img.width = 600
                    img.anchor = 'B9'
                    worksheet.add_image(img)
        return input_excel

    @classmethod
    def get_details_template(cls, base_dict: dict) -> Tuple[dict, Template]:
        """
        Get the details jinja template for the correct class. Extends parent

        Args:
            base_dict (dict): incoming dictionary of Submission fields

        Returns:
            Tuple[dict, Template]: (Updated dictionary, Template to be rendered)
        """
        base_dict, template = super().get_details_template(base_dict=base_dict)
        base_dict['excluded'] += ['gel_info', 'gel_image', 'headers', "dna_core_submission_number", "source_plates",
                                  "gel_controls"]
        base_dict['DNA Core ID'] = base_dict['dna_core_submission_number']
        check = 'gel_info' in base_dict.keys() and base_dict['gel_info'] != None
        if check:
            headers = [item['name'] for item in base_dict['gel_info'][0]['values']]
            base_dict['headers'] = [''] * (4 - len(headers))
            base_dict['headers'] += headers
            # logger.debug(f"Gel info: {pformat(base_dict['headers'])}")
        check = 'gel_image' in base_dict.keys() and base_dict['gel_image'] != None
        if check:
            with ZipFile(cls.__directory_path__.joinpath("submission_imgs.zip")) as zipped:
                base_dict['gel_image'] = base64.b64encode(zipped.read(base_dict['gel_image'])).decode('utf-8')
        return base_dict, template

    def adjust_to_dict_samples(self, backup: bool = False) -> List[dict]:
        """
        Updates sample dictionaries with custom values

        Args:
            backup (bool, optional): Whether to perform backup. Defaults to False.

        Returns:
            List[dict]: Updated dictionaries
        """
        # logger.debug(f"Hello from {self.__class__.__name__} dictionary sample adjuster.")
        output = []
        # set_plate = None
        for assoc in self.submission_sample_associations:
            dicto = assoc.to_sub_dict()
            # if self.source_plates is None:
            #     output.append(dicto)
            #     continue
            # for item in self.source_plates:
            #     if assoc.sample.id is None:
            #         old_plate = None
            #     else:
            #         old_plate = WastewaterAssociation.query(submission=item['plate'], sample=assoc.sample, limit=1)
            #     if old_plate is not None:
            #         set_plate = old_plate.submission.rsl_plate_num
            #         # logger.debug(f"Dictionary: {pformat(dicto)}")
            #         if dicto['ww_processing_num'].startswith("NTC"):
            #             dicto['well'] = dicto['ww_processing_num']
            #         else:
            #             dicto['well'] = f"{row_map[old_plate.row]}{old_plate.column}"
            #         break
            #     elif dicto['ww_processing_num'].startswith("NTC"):
            #         dicto['well'] = dicto['ww_processing_num']
            # dicto['plate_name'] = set_plate
            # logger.debug(f"Here is our raw sample: {pformat(dicto)}")
            output.append(dicto)
        return output

    def custom_context_events(self) -> dict:
        """
        Creates dictionary of str:function to be passed to context menu. Extends parent

        Returns:
            dict: dictionary of functions
        """
        events = super().custom_context_events()
        events['Gel Box'] = self.gel_box
        return events

    def set_attribute(self, key: str, value):
        super().set_attribute(key=key, value=value)
        if key == 'gel_info':
            if len(self.gel_info) > 3:
                self.gel_info = self.gel_info[-3:]

    def gel_box(self, obj):
        """
        Creates widget to perform gel viewing operations

        Args:
            obj (_type_): parent widget
        """
        from frontend.widgets.gel_checker import GelBox
        from frontend.widgets import select_open_file
        fname = select_open_file(obj=obj, file_extension="jpg")
        dlg = GelBox(parent=obj, img_path=fname, submission=self)
        if dlg.exec():
            self.dna_core_submission_number, self.gel_barcode, img_path, output, comment = dlg.parse_form()
            self.gel_image = img_path.name
            self.gel_info = output
            dt = datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S")
            com = dict(text=comment, name=getuser(), time=dt)
            if com['text'] != None and com['text'] != "":
                if self.comment is not None:
                    self.comment.append(com)
                else:
                    self.comment = [com]
            # logger.debug(pformat(self.gel_info))
            with ZipFile(self.__directory_path__.joinpath("submission_imgs.zip"), 'a') as zipf:
                # Add a file located at the source_path to the destination within the zip
                # file. It will overwrite existing files if the names collide, but it
                # will give a warning
                zipf.write(img_path, self.gel_image)
            self.save()


# Sample Classes

class BasicSample(BaseClass):
    """
    Base of basic sample which polymorphs into BCSample and WWSample
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    submitter_id = Column(String(64), nullable=False, unique=True)  #: identification from submitter
    sample_type = Column(String(32))  #: subtype of sample

    sample_submission_associations = relationship(
        "SubmissionSampleAssociation",
        back_populates="sample",
        cascade="all, delete-orphan",
    )  #: associated submissions

    __mapper_args__ = {
        "polymorphic_identity": "Basic Sample",
        "polymorphic_on": case(

            (sample_type == "Wastewater Sample", "Wastewater Sample"),
            (sample_type == "Wastewater Artic Sample", "Wastewater Sample"),
            (sample_type == "Bacterial Culture Sample", "Bacterial Culture Sample"),

            else_="Basic Sample"
        ),
        "with_polymorphic": "*",
    }

    submissions = association_proxy("sample_submission_associations", "submission")  #: proxy of associated submissions

    @validates('submitter_id')
    def create_id(self, key: str, value: str):
        """
        Creates a random string as a submitter id.

        Args:
            key (str): name of attribute
            value (str): submitter id

        Returns:
            str: new (or unchanged) submitter id
        """
        if value == None:
            return uuid.uuid4().hex.upper()
        else:
            return value

    def __repr__(self) -> str:
        try:
            return f"<{self.sample_type.replace('_', ' ').title().replace(' ', '')}({self.submitter_id})>"
        except AttributeError:
            return f"<Sample({self.submitter_id})"

    @classmethod
    def timestamps(cls) -> List[str]:
        output = [item.name for item in cls.__table__.columns if isinstance(item.type, TIMESTAMP)]
        if issubclass(cls, BasicSample) and not cls.__name__ == "BasicSample":
            output += BasicSample.timestamps()
        return output

    def to_sub_dict(self, full_data: bool = False) -> dict:
        """
        gui friendly dictionary, extends parent method.

        Returns:
            dict: well location and name (sample id, organism) NOTE: keys must sync with WWSample to_sub_dict above
        """
        # logger.debug(f"Converting {self} to dict.")
        # start = time()
        sample = {}
        sample['submitter_id'] = self.submitter_id
        sample['sample_type'] = self.sample_type
        if full_data:
            sample['submissions'] = sorted([item.to_sub_dict() for item in self.sample_submission_associations],
                                           key=itemgetter('submitted_date'))
        # logger.debug(f"Done converting {self} after {time()-start}")
        return sample

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
                                  attrs: dict | None = None) -> BasicSample:
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
                return [item for item in cls.__subclasses__() if
                        item.__mapper_args__['polymorphic_identity'] == polymorphic_identity][0]
            except Exception as e:
                logger.error(f"Could not get polymorph {polymorphic_identity} of {cls} due to {e}")
                model = cls
        else:
            model = cls
        if attrs is None or len(attrs) == 0:
            return model
        if any([not hasattr(cls, attr) for attr in attrs.keys()]):
            # looks for first model that has all included kwargs
            try:
                model = [subclass for subclass in cls.__subclasses__() if
                         all([hasattr(subclass, attr) for attr in attrs.keys()])][0]
            except IndexError as e:
                raise AttributeError(
                    f"Couldn't find existing class/subclass of {cls} with all attributes:\n{pformat(attrs.keys())}")
        logger.info(f"Recruiting model: {model}")
        return model

    @classmethod
    def sql_enforcer(cls, pyd_sample:"PydSample"):
        return pyd_sample

    @classmethod
    def parse_sample(cls, input_dict: dict) -> dict:
        f"""
        Custom sample parser

        Args:
            input_dict (dict): Basic parser results.

        Returns:
            dict: Updated parser results.
        """
        # logger.debug(f"Hello from {cls.__name__} sample parser!")
        return input_dict

    @classmethod
    def get_details_template(cls, base_dict: dict) -> Tuple[dict, Template]:
        """
        Get the details jinja template for the correct class

        Args:
            base_dict (dict): incoming dictionary of Submission fields

        Returns:
            Tuple(dict, Template): (Updated dictionary, Template to be rendered)
        """
        base_dict['excluded'] = ['submissions', 'excluded', 'colour', 'tooltip']
        env = jinja_template_loading()
        temp_name = f"{cls.__name__.lower()}_details.html"
        # logger.debug(f"Returning template: {temp_name}")
        try:
            template = env.get_template(temp_name)
        except TemplateNotFound as e:
            logger.error(f"Couldn't find template {e}")
            template = env.get_template("basicsample_details.html")
        return base_dict, template

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
        # logger.debug(f"Length of kwargs: {len(kwargs)}")
        query: Query = cls.__database_session__.query(model)
        match submitter_id:
            case str():
                # logger.debug(f"Looking up {model} with submitter id: {submitter_id}")
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
            ValueError: Raised if no kwargs are passed to narrow down instances
            ValueError: Raised if unallowed key is given.

        Returns:
            _type_: _description_
        """
        disallowed = ["id"]
        if kwargs == {}:
            raise ValueError("Need to narrow down query or the first available instance will be returned.")
        sanitized_kwargs = {k:v for k,v in kwargs.items() if k not in disallowed}
        instance = cls.query(sample_type=sample_type, limit=1, **kwargs)
        # logger.debug(f"Retrieved instance: {instance}")
        if instance is None:
            used_class = cls.find_polymorphic_subclass(attrs=sanitized_kwargs, polymorphic_identity=sample_type)
            instance = used_class(**sanitized_kwargs)
            instance.sample_type = sample_type
            # logger.debug(f"Creating instance: {instance}")
        return instance

    @classmethod
    def fuzzy_search(cls,
              # submitter_id: str | None = None,
              sample_type: str | BasicSample | None = None,
              # limit: int = 0,
              **kwargs
              ) -> List[BasicSample]:
        match sample_type:
            case str():
                model = cls.find_polymorphic_subclass(polymorphic_identity=sample_type)
            case BasicSample():
                model = sample_type
            case _:
                model = cls.find_polymorphic_subclass(attrs=kwargs)
            # logger.debug(f"Length of kwargs: {len(kwargs)}")
        query: Query = cls.__database_session__.query(model)
        for k, v in kwargs.items():
            search = f"%{v}%"
            try:
                attr = getattr(model, k)
                query = query.filter(attr.like(search))
            except (ArgumentError, AttributeError) as e:
                logger.error(f"Attribute {k} unavailable due to:\n\t{e}\nSkipping.")
        return query.all()

    def delete(self):
        raise AttributeError(f"Delete not implemented for {self.__class__}")

    @classmethod
    def get_searchables(cls):
        return [dict(label="Submitter ID", field="submitter_id")]


    @classmethod
    def samples_to_df(cls, sample_type: str | None | BasicSample = None, **kwargs):
    # def samples_to_df(cls, sample_type:str|None|BasicSample=None, searchables:dict={}):
        logger.debug(f"Checking {sample_type} with type {type(sample_type)}")
        match sample_type:
            case str():
                model = BasicSample.find_polymorphic_subclass(polymorphic_identity=sample_type)
            case _:
                try:
                    check = issubclass(sample_type, BasicSample)
                except TypeError:
                    check = False
                if check:
                    model = sample_type
                else:
                    model = cls
        q_out = model.fuzzy_search(sample_type=sample_type, **kwargs)
        if not isinstance(q_out, list):
            q_out = [q_out]
        try:
            samples = [sample.to_sub_dict() for sample in q_out]
        except TypeError as e:
            logger.error(f"Couldn't find any samples with data: {kwargs}\nDue to {e}")
            return None
        df = pd.DataFrame.from_records(samples)
        # NOTE: Exclude sub information
        for item in ['concentration', 'organism', 'colour', 'tooltip', 'comments', 'samples', 'reagents',
                     'equipment', 'gel_info', 'gel_image', 'dna_core_submission_number', 'gel_controls']:
            try:
                df = df.drop(item, axis=1)
            except:
                logger.warning(f"Couldn't drop '{item}' column from submissionsheet df.")
        return df

    def show_details(self, obj):
        """
        Creates Widget for showing submission details.

        Args:
            obj (_type_): parent widget
        """
        # logger.debug("Hello from details")
        from frontend.widgets.submission_details import SubmissionDetails
        dlg = SubmissionDetails(parent=obj, sub=self)
        if dlg.exec():
            pass

# Below are the custom sample types

class WastewaterSample(BasicSample):
    """
    Derivative wastewater sample
    """
    id = Column(INTEGER, ForeignKey('_basicsample.id'), primary_key=True)
    ww_processing_num = Column(String(64))  #: wastewater processing number
    ww_full_sample_id = Column(String(64))  #: full id given by entrics
    rsl_number = Column(String(64))  #: rsl plate identification number
    collection_date = Column(TIMESTAMP)  #: Date sample collected
    received_date = Column(TIMESTAMP)  #: Date sample received
    notes = Column(String(2000))  #: notes from submission form
    sample_location = Column(String(8))  #: location on 24 well plate
    __mapper_args__ = dict(polymorphic_identity="Wastewater Sample",
                           polymorphic_load="inline",
                           inherit_condition=(id == BasicSample.id))

    @classmethod
    def get_default_info(cls, *args):
        dicto = super().get_default_info(*args)
        match dicto:
            case dict():
                dicto['singles'] += ['ww_processing_num']
                output = {}
                for k, v in dicto.items():
                    if len(args) > 0 and k not in args:
                        # logger.debug(f"Don't want {k}")
                        continue
                    else:
                        output[k] = v
                if len(args) == 1:
                    return output[args[0]]
            case list():
                if "singles" in args:
                    dicto += ['ww_processing_num']
                return dicto
            case _:
                pass

    def to_sub_dict(self, full_data: bool = False) -> dict:
        """
        gui friendly dictionary, extends parent method.

        Returns:
            dict: well location and name (sample id, organism) NOTE: keys must sync with WWSample to_sub_dict above
        """
        sample = super().to_sub_dict(full_data=full_data)
        sample['ww_processing_num'] = self.ww_processing_num
        sample['sample_location'] = self.sample_location
        sample['received_date'] = self.received_date
        sample['collection_date'] = self.collection_date
        return sample

    @classmethod
    def parse_sample(cls, input_dict: dict) -> dict:
        """
        Custom sample parser. Extends parent

        Args:
            input_dict (dict): Basic parser results.

        Returns:
            dict: Updated parser results.
        """
        output_dict = super().parse_sample(input_dict)
        # logger.debug(f"Initial sample dict: {pformat(output_dict)}")
        disallowed = ["", None, "None"]
        try:
            check = output_dict['rsl_number'] in [None, "None"]
        except KeyError:
            check = True
        if check:
            output_dict['rsl_number'] = "RSL-WW-" + output_dict['ww_processing_num']
        if output_dict['ww_full_sample_id'] is not None and output_dict["submitter_id"] in disallowed:
            output_dict["submitter_id"] = output_dict['ww_full_sample_id']
        return output_dict

    def get_previous_ww_submission(self, current_artic_submission: WastewaterArtic):
        try:
            plates = [item['plate'] for item in current_artic_submission.source_plates]
        except TypeError as e:
            logger.error(f"source_plates must not be present")
            plates = [item.rsl_plate_num for item in
                      self.submissions[:self.submissions.index(current_artic_submission)]]
        subs = [sub for sub in self.submissions if sub.rsl_plate_num in plates]
        # logger.debug(f"Submissions: {subs}")
        try:
            return subs[-1]
        except IndexError:
            return None

    @classmethod
    def get_searchables(cls):
        searchables = super().get_searchables()
        for item in ["ww_processing_num", "ww_full_sample_id", "rsl_number"]:
            label = item.strip("ww_").replace("_", " ").replace("rsl", "RSL").title()
            searchables.append(dict(label=label, field=item))
        return searchables


class BacterialCultureSample(BasicSample):
    """
    base of bacterial culture sample
    """
    id = Column(INTEGER, ForeignKey('_basicsample.id'), primary_key=True)
    organism = Column(String(64))  #: bacterial specimen
    concentration = Column(String(16))  #: sample concentration
    control = relationship("Control", back_populates="sample", uselist=False)
    __mapper_args__ = dict(polymorphic_identity="Bacterial Culture Sample",
                           polymorphic_load="inline",
                           inherit_condition=(id == BasicSample.id))

    def to_sub_dict(self, full_data: bool = False) -> dict:
        """
        gui friendly dictionary, extends parent method.

        Returns:
            dict: well location and name (sample id, organism) NOTE: keys must sync with WWSample to_sub_dict above
        """
        # start = time()
        sample = super().to_sub_dict(full_data=full_data)
        sample['name'] = self.submitter_id
        sample['organism'] = self.organism
        sample['concentration'] = self.concentration
        if self.control != None:
            sample['colour'] = [0, 128, 0]
            sample['tooltip'] = f"Control: {self.control.controltype.name} - {self.control.controltype.targets}"
        # logger.debug(f"Done converting to {self} to dict after {time()-start}")
        return sample

# Submission to Sample Associations

class SubmissionSampleAssociation(BaseClass):
    """
    table containing submission/sample associations
    DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
    """

    id = Column(INTEGER, unique=True, nullable=False)  #: id to be used for inheriting purposes
    sample_id = Column(INTEGER, ForeignKey("_basicsample.id"), nullable=False)  #: id of associated sample
    submission_id = Column(INTEGER, ForeignKey("_basicsubmission.id"), primary_key=True)  #: id of associated submission
    row = Column(INTEGER, primary_key=True)  #: row on the 96 well plate
    column = Column(INTEGER, primary_key=True)  #: column on the 96 well plate
    submission_rank = Column(INTEGER, nullable=False, default=0) #: Location in sample list

    # reference to the Submission object
    submission = relationship(BasicSubmission,
                              back_populates="submission_sample_associations")  #: associated submission

    # reference to the Sample object
    sample = relationship(BasicSample, back_populates="sample_submission_associations")  #: associated sample

    base_sub_type = Column(String)  #: string of subtype name

    # Refers to the type of parent.
    # Hooooooo boy, polymorphic association type, now we're getting into the weeds!
    __mapper_args__ = {
        "polymorphic_identity": "Basic Association",
        "polymorphic_on": base_sub_type,
        "with_polymorphic": "*",
    }

    def __init__(self, submission: BasicSubmission = None, sample: BasicSample = None, row: int = 1, column: int = 1,
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
        # logger.debug(f"Looking at kwargs: {pformat(kwargs)}")
        for k,v in kwargs.items():
            try:
                self.__setattr__(k, v)
            except AttributeError:
                logger.error(f"Couldn't set {k} to {v}")
        # logger.debug(f"Using submission sample association id: {self.id}")

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
        # Get sample info
        # logger.debug(f"Running {self.__repr__()}")
        sample = self.sample.to_sub_dict()
        # logger.debug("Sample conversion complete.")
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

    def to_hitpick(self) -> dict | None:
        """
        Outputs a dictionary usable for html plate maps.

        Returns:
            dict: dictionary of sample id, row and column in elution plate
        """
        # Since there is no PCR, negliable result is necessary.
        sample = self.to_sub_dict()
        # logger.debug(f"Sample dict to hitpick: {sample}")
        env = jinja_template_loading()
        template = env.get_template("tooltip.html")
        tooltip_text = template.render(fields=sample)
        try:
            tooltip_text += sample['tooltip']
        except KeyError:
            pass
        sample.update(dict(Name=self.sample.submitter_id[:10], tooltip=tooltip_text))
        return sample

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
        if polymorphic_identity == None:
            output = cls
        else:
            try:
                output = [item for item in cls.__subclasses__() if
                          item.__mapper_args__['polymorphic_identity'] == polymorphic_identity][0]
            except Exception as e:
                logger.error(f"Could not get polymorph {polymorphic_identity} of {cls} due to {e}")
                output = cls
        # logger.debug(f"Using SubmissionSampleAssociation subclass: {output}")
        return output

    @classmethod
    @setup_lookup
    def query(cls,
              submission: BasicSubmission | str | None = None,
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
            submission (models.BasicSubmission | str | None, optional): Submission of interest. Defaults to None.
            sample (models.BasicSample | str | None, optional): Sample of interest. Defaults to None.
            row (int, optional): Row of the sample location on submission plate. Defaults to 0.
            column (int, optional): Column of the sample location on the submission plate. Defaults to 0.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.
            chronologic (bool, optional): Return results in chronologic order. Defaults to False.

        Returns:
            models.SubmissionSampleAssociation|List[models.SubmissionSampleAssociation]: Junction(s) of interest
        """
        query: Query = cls.__database_session__.query(cls)
        match submission:
            case BasicSubmission():
                # logger.debug(f"Lookup SampleSubmissionAssociation with submission BasicSubmission {submission}")
                query = query.filter(cls.submission == submission)
            case str():
                # logger.debug(f"Lookup SampleSubmissionAssociation with submission str {submission}")
                query = query.join(BasicSubmission).filter(BasicSubmission.rsl_plate_num == submission)
            case _:
                pass
        match sample:
            case BasicSample():
                # logger.debug(f"Lookup SampleSubmissionAssociation with sample BasicSample {sample}")
                query = query.filter(cls.sample == sample)
            case str():
                # logger.debug(f"Lookup SampleSubmissionAssociation with sample str {sample}")
                query = query.join(BasicSample).filter(BasicSample.submitter_id == sample)
            case _:
                pass
        if row > 0:
            query = query.filter(cls.row == row)
        if column > 0:
            query = query.filter(cls.column == column)
        match exclude_submission_type:
            case str():
                # logger.debug(f"filter SampleSubmissionAssociation to exclude submission type {exclude_submission_type}")
                query = query.join(BasicSubmission).filter(
                    BasicSubmission.submission_type_name != exclude_submission_type)
            case _:
                pass
        # logger.debug(f"Query count: {query.count()}")
        if reverse and not chronologic:
            query = query.order_by(BasicSubmission.id.desc())
        if chronologic:
            if reverse:
                query = query.order_by(BasicSubmission.submitted_date.desc())
            else:
                query = query.order_by(BasicSubmission.submitted_date)
        return cls.execute_query(query=query, limit=limit, **kwargs)

    @classmethod
    def query_or_create(cls,
                        association_type: str = "Basic Association",
                        submission: BasicSubmission | str | None = None,
                        sample: BasicSample | str | None = None,
                        id:int|None=None,
                        **kwargs) -> SubmissionSampleAssociation:
        """
        Queries for an association, if none exists creates a new one.

        Args:
            association_type (str, optional): Subclass name. Defaults to "Basic Association".
            submission (BasicSubmission | str | None, optional): associated submission. Defaults to None.
            sample (BasicSample | str | None, optional): associated sample. Defaults to None.
            id (int | None, optional): association id. Defaults to None.

       Returns:
            SubmissionSampleAssociation: Queried or new association.
        """
        # logger.debug(f"Attempting create or query with {kwargs}")
        match submission:
            case BasicSubmission():
                pass
            case str():
                submission = BasicSubmission.query(rsl_plate_num=submission)
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
            # sanitized_kwargs = {k:v for k,v in kwargs.items() if k not in ['id']}
            used_cls = cls.find_polymorphic_subclass(polymorphic_identity=association_type)
            instance = used_cls(submission=submission, sample=sample, id=id, **kwargs)
        return instance

    def delete(self):
        raise AttributeError(f"Delete not implemented for {self.__class__}")


class WastewaterAssociation(SubmissionSampleAssociation):
    """
    table containing wastewater specific submission/sample associations
    DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
    """
    id = Column(INTEGER, ForeignKey("_submissionsampleassociation.id"), primary_key=True)
    ct_n1 = Column(FLOAT(2))  #: AKA ct for N1
    ct_n2 = Column(FLOAT(2))  #: AKA ct for N2
    n1_status = Column(String(32))  #: positive or negative for N1
    n2_status = Column(String(32))  #: positive or negative for N2
    pcr_results = Column(JSON)  #: imported PCR status from QuantStudio

    __mapper_args__ = dict(polymorphic_identity="Wastewater Association",
                           polymorphic_load="inline",
                           inherit_condition=(id == SubmissionSampleAssociation.id))

    def to_sub_dict(self) -> dict:
        """
        Returns a sample dictionary updated with instance information. Extends parent

        Returns:
            dict: Updated dictionary with row, column and well updated
        """

        sample = super().to_sub_dict()
        sample['ct'] = f"({self.ct_n1}, {self.ct_n2})"
        try:
            sample['positive'] = any(["positive" in item for item in [self.n1_status, self.n2_status]])
        except (TypeError, AttributeError) as e:
            logger.error(f"Couldn't check positives for {self.sample.rsl_number}. Looks like there isn't PCR data.")
        return sample

    def to_hitpick(self) -> dict | None:
        """
        Outputs a dictionary usable for html plate maps. Extends parent

        Returns:
            dict: dictionary of sample id, row and column in elution plate
        """
        sample = super().to_hitpick()
        try:
            sample[
                'tooltip'] += f"<br>- ct N1: {'{:.2f}'.format(self.ct_n1)} ({self.n1_status})<br>- ct N2: {'{:.2f}'.format(self.ct_n2)} ({self.n2_status})"
        except (TypeError, AttributeError) as e:
            logger.error(f"Couldn't set tooltip for {self.sample.rsl_number}. Looks like there isn't PCR data.")
        return sample

    @classmethod
    def autoincrement_id(cls) -> int:
        """
        Increments the association id automatically. Overrides parent

        Returns:
            int: incremented id
        """
        try:
            parent = [base for base in cls.__bases__ if base.__name__ == "SubmissionSampleAssociation"][0]
            return max([item.id for item in parent.query()]) + 1
        except ValueError as e:
            logger.error(f"Problem incrementing id: {e}")
            return 1


class WastewaterArticAssociation(SubmissionSampleAssociation):
    """
    table containing wastewater artic specific submission/sample associations
    DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
    """
    id = Column(INTEGER, ForeignKey("_submissionsampleassociation.id"), primary_key=True)
    source_plate = Column(String(16))
    source_plate_number = Column(INTEGER)
    source_well = Column(String(8))
    ct = Column(String(8))  #: AKA ct for N1

    __mapper_args__ = dict(polymorphic_identity="Wastewater Artic Association",
                           polymorphic_load="inline",
                           inherit_condition=(id == SubmissionSampleAssociation.id))

    def to_sub_dict(self) -> dict:
        """
        Returns a sample dictionary updated with instance information. Extends parent

        Returns:
            dict: Updated dictionary with row, column and well updated
        """

        sample = super().to_sub_dict()
        sample['ct'] = self.ct
        sample['source_plate'] = self.source_plate
        sample['source_plate_number'] = self.source_plate_number
        sample['source_well'] = self.source_well
        return sample

    @classmethod
    def autoincrement_id(cls) -> int:
        """
        Increments the association id automatically. Overrides parent

        Returns:
            int: incremented id
        """
        try:
            parent = [base for base in cls.__bases__ if base.__name__ == "SubmissionSampleAssociation"][0]
            return max([item.id for item in parent.query()]) + 1
        except ValueError as e:
            logger.error(f"Problem incrementing id: {e}")
            return 1


