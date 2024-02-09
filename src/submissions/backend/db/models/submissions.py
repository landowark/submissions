'''
Models for the main submission types.
'''
from __future__ import annotations
from getpass import getuser
import math, json, logging, uuid, tempfile, re, yaml, base64
from zipfile import ZipFile
from tempfile import TemporaryDirectory
from reportlab.graphics.barcode import createBarcodeImageInMemory
from reportlab.graphics.shapes import Drawing
from reportlab.lib.units import mm
from operator import attrgetter
from pprint import pformat
from . import Reagent, SubmissionType, KitType, Organization
from sqlalchemy import Column, String, TIMESTAMP, INTEGER, ForeignKey, JSON, FLOAT, case
from sqlalchemy.orm import relationship, validates, Query
from json.decoder import JSONDecodeError
from sqlalchemy.ext.associationproxy import association_proxy
import pandas as pd
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.drawing.image import Image as OpenpyxlImage
from . import BaseClass
from tools import check_not_nan, row_map, setup_lookup, jinja_template_loading, rreplace
from datetime import datetime, date
from typing import List, Any, Tuple
from dateutil.parser import parse
from dateutil.parser._parser import ParserError
from sqlalchemy.exc import OperationalError as AlcOperationalError, IntegrityError as AlcIntegrityError, StatementError
from sqlite3 import OperationalError as SQLOperationalError, IntegrityError as SQLIntegrityError
from pathlib import Path
from jinja2.exceptions import TemplateNotFound
from jinja2 import Template


logger = logging.getLogger(f"submissions.{__name__}")

class BasicSubmission(BaseClass):
    """
    Concrete of basic submission which polymorphs into BacterialCulture and Wastewater
    """
    
    id = Column(INTEGER, primary_key=True) #: primary key   
    rsl_plate_num = Column(String(32), unique=True, nullable=False) #: RSL name (e.g. RSL-22-0012)
    submitter_plate_num = Column(String(127), unique=True) #: The number given to the submission by the submitting lab
    submitted_date = Column(TIMESTAMP) #: Date submission received
    submitting_lab = relationship("Organization", back_populates="submissions") #: client org
    submitting_lab_id = Column(INTEGER, ForeignKey("_organization.id", ondelete="SET NULL", name="fk_BS_sublab_id")) #: client lab id from _organizations
    sample_count = Column(INTEGER) #: Number of samples in the submission
    extraction_kit = relationship("KitType", back_populates="submissions") #: The extraction kit used
    extraction_kit_id = Column(INTEGER, ForeignKey("_kittype.id", ondelete="SET NULL", name="fk_BS_extkit_id")) #: id of joined extraction kit
    submission_type_name = Column(String, ForeignKey("_submissiontype.name", ondelete="SET NULL", name="fk_BS_subtype_name")) #: name of joined submission type
    technician = Column(String(64)) #: initials of processing tech(s)
    # Move this into custom types?
    # reagents = relationship("Reagent", back_populates="submissions", secondary=reagents_submissions) #: relationship to reagents
    reagents_id = Column(String, ForeignKey("_reagent.id", ondelete="SET NULL", name="fk_BS_reagents_id")) #: id of used reagents
    extraction_info = Column(JSON) #: unstructured output from the extraction table logger.
    run_cost = Column(FLOAT(2)) #: total cost of running the plate. Set from constant and mutable kit costs at time of creation.
    uploaded_by = Column(String(32)) #: user name of person who submitted the submission to the database.
    comment = Column(JSON) #: user notes
    submission_category = Column(String(64)) #: ["Research", "Diagnostic", "Surveillance", "Validation"], else defaults to submission_type_name

    submission_sample_associations = relationship(
        "SubmissionSampleAssociation",
        back_populates="submission",
        cascade="all, delete-orphan",
    ) #: Relation to SubmissionSampleAssociation
    
    samples = association_proxy("submission_sample_associations", "sample") #: Association proxy to SubmissionSampleAssociation.samples

    submission_reagent_associations = relationship(
        "SubmissionReagentAssociation",
        back_populates="submission",
        cascade="all, delete-orphan",
    ) #: Relation to SubmissionReagentAssociation
    
    reagents = association_proxy("submission_reagent_associations", "reagent") #: Association proxy to SubmissionReagentAssociation.reagent

    submission_equipment_associations = relationship(
        "SubmissionEquipmentAssociation",
        back_populates="submission",
        cascade="all, delete-orphan"
    ) #: Relation to Equipment

    equipment = association_proxy("submission_equipment_associations", "equipment") #: Association proxy to SubmissionEquipmentAssociation.equipment

    # Allows for subclassing into ex. BacterialCulture, Wastewater, etc.
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
        return f"{self.submission_type}Submission({self.rsl_plate_num})"

    def to_dict(self, full_data:bool=False, backup:bool=False) -> dict:
        """
        Constructs dictionary used in submissions summary

        Args:
            full_data (bool, optional): indicates if sample dicts to be constructed. Defaults to False.
            backup (bool, optional): passed to adjust_to_dict_samples. Defaults to False.

        Returns:
            dict: dictionary used in submissions summary and details
        """        
        # get lab from nested organization object
        # logger.debug(f"Converting {self.rsl_plate_num} to dict...")
        try:
            sub_lab = self.submitting_lab.name
        except AttributeError:
            sub_lab = None
        try:
            sub_lab = sub_lab.replace("_", " ").title()
        except AttributeError:
            pass
        # get extraction kit name from nested kit object
        try:
            ext_kit = self.extraction_kit.name
        except AttributeError:
            ext_kit = None
        # load scraped extraction info
        try:
            ext_info = json.loads(self.extraction_info)
        except TypeError:
            ext_info = None
        except JSONDecodeError as e:
            ext_info = None
            logger.error(f"Json error in {self.rsl_plate_num}: {e}")
        # Updated 2023-09 to use the extraction kit to pull reagents.
        if full_data:
            logger.debug(f"Attempting reagents.")
            try:
                reagents = [item.to_sub_dict(extraction_kit=self.extraction_kit) for item in self.submission_reagent_associations]
            except Exception as e:
                logger.error(f"We got an error retrieving reagents: {e}")
                reagents = None
            logger.debug(f"Running samples.")
            samples = self.adjust_to_dict_samples(backup=backup)
            logger.debug("Running equipment")
            try:
                equipment = [item.to_sub_dict() for item in self.submission_equipment_associations]
                if len(equipment) == 0:
                    equipment = None
            except Exception as e:
                logger.error(f"Error setting equipment: {e}")
                equipment = None
        else:
            reagents = None
            samples = None
            equipment = None
        # logger.debug("Getting comments")
        try:
            comments = self.comment
        except Exception as e:
            logger.error(f"Error setting comment: {self.comment}")
            comments = None
        output = {
            "id": self.id,
            "Plate Number": self.rsl_plate_num,
            "Submission Type": self.submission_type_name,
            "Submission Category": self.submission_category,
            "Submitter Plate Number": self.submitter_plate_num,
            "Submitted Date": self.submitted_date.strftime("%Y-%m-%d"),
            "Submitting Lab": sub_lab,
            "Sample Count": self.sample_count,
            "Extraction Kit": ext_kit,
            "Technician": self.technician,
            "Cost": self.run_cost,
            "reagents": reagents,
            "samples": samples,
            "extraction_info": ext_info,
            "comment": comments,
            "equipment": equipment
        }
        return output

    def report_dict(self) -> dict:
        """
        dictionary used in creating reports

        Returns:
            dict: dictionary used in creating reports
        """        
        # get lab name from nested organization object 
        try:
            sub_lab = self.submitting_lab.name
        except AttributeError:
            sub_lab = None
        try:
            sub_lab = sub_lab.replace("_", " ").title()
        except AttributeError:
            pass
        # get extraction kit name from nested kittype object
        try:
            ext_kit = self.extraction_kit.name
        except AttributeError:
            ext_kit = None
        output = {
            "id": self.id,
            "Plate Number": self.rsl_plate_num,
            "Submission Type": self.submission_type_name.replace("_", " ").title(),
            "Submitter Plate Number": self.submitter_plate_num,
            "Submitted Date": self.submitted_date.strftime("%Y-%m-%d"),
            "Submitting Lab": sub_lab,
            "Sample Count": self.sample_count,
            "Extraction Kit": ext_kit,
            "Cost": self.run_cost
        }
        return output
    
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
        assoc = [item for item in self.extraction_kit.kit_submissiontype_associations if item.submission_type == self.submission_type][0]
        # logger.debug(f"Came up with association: {assoc}")
        # If every individual cost is 0 this is probably an old plate.
        if all(item == 0.0 for item in [assoc.constant_cost, assoc.mutable_cost_column, assoc.mutable_cost_sample]):
            try:
                self.run_cost = self.extraction_kit.cost_per_run
            except Exception as e:
                logger.error(f"Calculation error: {e}")
        else:
            try:
                self.run_cost = assoc.constant_cost + (assoc.mutable_cost_column * cols_count_96) + (assoc.mutable_cost_sample * int(self.sample_count))
            except Exception as e:
                logger.error(f"Calculation error: {e}")

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
    
    def hitpick_plate(self) -> list:
        """
        Returns positve sample locations for plate

        Returns:
            list: list of htipick dictionaries for each sample
        """        
        output_list = [assoc.to_hitpick() for assoc in self.submission_sample_associations]
        return output_list

    def make_plate_map(self, plate_rows:int=8, plate_columns=12) -> str:
        """
        Constructs an html based plate map.

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
        for column in range(1, plate_columns+1):
            for row in range(1, plate_rows+1):
                try:
                    well = [item for item in sample_list if item['row'] == row and item['column']==column][0]
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

    def make_plate_barcode(self, width:int=100, height:int=25) -> Drawing:
        """
        Creates a barcode image for this BasicSubmission.

        Args:
            width (int, optional): Width (pixels) of image. Defaults to 100.
            height (int, optional): Height (pixels) of image. Defaults to 25.

        Returns:
            Drawing: image object
        """    
        return createBarcodeImageInMemory('Code128', value=self.rsl_plate_num, width=width*mm, height=height*mm, humanReadable=True, format="png")

    @classmethod
    def submissions_to_df(cls, submission_type:str|None=None, limit:int=0) -> pd.DataFrame:
        """
        Convert all submissions to dataframe

        Args:
            submission_type (str | None, optional): Filter by SubmissionType. Defaults to None.
            limit (int, optional): Maximum number of results to return. Defaults to 0.

        Returns:
            pd.DataFrame: Pandas Dataframe of all relevant submissions
        """        
        logger.debug(f"Querying Type: {submission_type}")
        logger.debug(f"Using limit: {limit}")
        # use lookup function to create list of dicts
        subs = [item.to_dict() for item in cls.query(submission_type=submission_type, limit=limit)]
        logger.debug(f"Got {len(subs)} submissions.")
        df = pd.DataFrame.from_records(subs)
        # Exclude sub information
        for item in ['controls', 'extraction_info', 'pcr_info', 'comment', 'comments', 'samples', 'reagents', 'equipment']:
            try:
                df = df.drop(item, axis=1)
            except:
                logger.warning(f"Couldn't drop '{item}' column from submissionsheet df.")
        return df

    def set_attribute(self, key:str, value):
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
            case "submitter_plate_num":
                # logger.debug(f"Submitter plate id: {value}")
                field_value = value
            case "samples":
                for sample in value:
                    # logger.debug(f"Parsing {sample} to sql.")
                    sample, _ = sample.toSQL(submission=self)
                return
            case "reagents":
                field_value = [reagent['value'].toSQL()[0] if isinstance(reagent, dict) else reagent.toSQL()[0] for reagent in value]
            case "submission_type":
                field_value = SubmissionType.query(name=value)
            case "sample_count":
                if value == None:
                    field_value = len(self.samples)
                else:
                    field_value = value
            case "ctx" | "csv" | "filepath" | "equipment":
                return
            case "comment":
                if value == "" or value == None or value == 'null':
                    field_value = None
                else:
                    field_value = dict(name="submitter", text=value, time=datetime.now())
            case _:
                field_value = value
        # insert into field
        try:
            self.__setattr__(key, field_value)
        except AttributeError:
            logger.error(f"Could not set {self} attribute {key} to {value}")

    def update_subsampassoc(self, sample:BasicSample, input_dict:dict):
        """
        Update a joined submission sample association.

        Args:
            sample (BasicSample): Associated sample.
            input_dict (dict): values to be updated

        Returns:
            Result: _description_
        """        
        assoc = [item for item in self.submission_sample_associations if item.sample==sample][0]
        for k,v in input_dict.items():
            try:
                setattr(assoc, k, v)
            except AttributeError:
                logger.error(f"Can't set {k} to {v}")
        result = assoc.save()
        return result

    def to_pydantic(self, backup:bool=False) -> "PydSubmission":
        """
        Converts this instance into a PydSubmission

        Returns:
            PydSubmission: converted object.
        """        
        from backend.validators import PydSubmission, PydSample, PydReagent, PydEquipment
        dicto = self.to_dict(full_data=True, backup=backup)
        new_dict = {}
        for key, value in dicto.items():
            match key:
                case "reagents":
                    new_dict[key] = [PydReagent(**reagent) for reagent in value]
                case "samples":
                    new_dict[key] = [PydSample(**sample) for sample in dicto['samples']]
                case "equipment":
                    try:
                        new_dict[key] = [PydEquipment(**equipment) for equipment in dicto['equipment']]
                    except TypeError as e:
                        logger.error(f"Possible no equipment error: {e}")
                case "Plate Number":
                    new_dict['rsl_plate_num'] = dict(value=value, missing=True)
                case "Submitter Plate Number":
                    new_dict['submitter_plate_num'] = dict(value=value, missing=True)
                case _:
                    logger.debug(f"Setting dict {key} to {value}")
                    new_dict[key.lower().replace(" ", "_")] = dict(value=value, missing=True)
        new_dict['filepath'] = Path(tempfile.TemporaryFile().name)
        return PydSubmission(**new_dict)

    def save(self, original:bool=True):
        """
        Adds this instance to database and commits.

        Args:
            original (bool, optional): Is this the first save. Defaults to True.
        """        
        if original:
            self.uploaded_by = getuser()
        super().save()

# Polymorphic functions

    @classmethod
    def construct_regex(cls) -> re.Pattern:
        """
        Constructs catchall regex.

        Returns:
            re.Pattern: Regular expression pattern to discriminate between submission types.
        """                
        rstring =  rf'{"|".join([item.get_regex() for item in cls.__subclasses__()])}'
        regex = re.compile(rstring, flags = re.IGNORECASE | re.VERBOSE)
        return regex
 
    @classmethod
    def find_subclasses(cls, attrs:dict|None=None, submission_type:str|SubmissionType|None=None):
        """
        Retrieves subclasses of this class matching patterned

        Args:
            attrs (dict | None, optional): Attributes to look for. Defaults to None.
            submission_type (str | SubmissionType | None, optional): Submission type. Defaults to None.

        Raises:
            AttributeError: Raised if attr given, but not found.

        Returns:
            _type_: Subclass of interest.
        """                
        match submission_type:
            case str():
                return cls.find_polymorphic_subclass(submission_type)
            case SubmissionType():
                return cls.find_polymorphic_subclass(submission_type.name)
            case _:
                pass
        if attrs == None or len(attrs) == 0:
            return cls
        if any([not hasattr(cls, attr) for attr in attrs]):
            # looks for first model that has all included kwargs
            try:
                model = [subclass for subclass in cls.__subclasses__() if all([hasattr(subclass, attr) for attr in attrs])][0]
            except IndexError as e:
                raise AttributeError(f"Couldn't find existing class/subclass of {cls} with all attributes:\n{pformat(attrs)}")
        else:
            model = cls
        logger.info(f"Recruiting model: {model}")
        return model
    
    @classmethod
    def find_polymorphic_subclass(cls, polymorphic_identity:str|None=None):
        """
        Find subclass based on polymorphic identity.

        Args:
            polymorphic_identity (str | None, optional): String representing polymorphic identity. Defaults to None.

        Returns:
            _type_: Subclass of interest.
        """           
        # logger.debug(f"Controlling for dict value")
        if isinstance(polymorphic_identity, dict):
            polymorphic_identity = polymorphic_identity['value']
        if polymorphic_identity != None:
            try:
                cls = [item for item in cls.__subclasses__() if item.__mapper_args__['polymorphic_identity']==polymorphic_identity][0]
                logger.info(f"Recruiting: {cls}")
            except Exception as e:
                logger.error(f"Could not get polymorph {polymorphic_identity} of {cls} due to {e}")
        return cls

# Child class custom functions

    @classmethod
    def custom_platemap(cls, xl:pd.ExcelFile, plate_map:pd.DataFrame) -> pd.DataFrame:
        """
        Stupid stopgap solution to there being an issue with the Bacterial Culture plate map

        Args:
            xl (pd.ExcelFile): original xl workbook, used for child classes mostly
            plate_map (pd.DataFrame): original plate map

        Returns:
            pd.DataFrame: updated plate map.
        """        
        logger.info(f"Calling {cls.__mapper_args__['polymorphic_identity']} plate mapper.")
        return plate_map
    
    @classmethod
    def parse_info(cls, input_dict:dict, xl:pd.ExcelFile|None=None) -> dict:
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
    def parse_samples(cls, input_dict:dict) -> dict:
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
    def finalize_parse(cls, input_dict:dict, xl:pd.ExcelFile|None=None, info_map:dict|None=None, plate_map:dict|None=None) -> dict:
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
    def custom_autofill(cls, input_excel:Workbook, info:dict|None=None, backup:bool=False) -> Workbook:
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
    def enforce_name(cls, instr:str, data:dict|None=None) -> str:
        """
        Custom naming method for this class.

        Args:
            instr (str): Initial name.
            data (dict | None, optional): Additional parameters for name. Defaults to None.

        Returns:
            str: Updated name.
        """        
        logger.info(f"Hello from {cls.__mapper_args__['polymorphic_identity']} Enforcer!")
        return instr

    @classmethod
    def parse_pcr(cls, xl:pd.DataFrame, rsl_number:str) -> list:
        """
        Perform custom parsing of pcr info.

        Args:
            xl (pd.DataFrame): pcr info form
            rsl_number (str): rsl plate num of interest

        Returns:
            list: _description_
        """        
        logger.debug(f"Hello from {cls.__mapper_args__['polymorphic_identity']} PCR parser!")
        return []

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
    def custom_sample_autofill_row(cls, sample, worksheet:Worksheet) -> int:
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
    def adjust_autofill_samples(cls, samples:List[Any]) -> List[Any]:
        logger.info(f"Hello from {cls.__mapper_args__['polymorphic_identity']} sampler")
        return samples
        
    def adjust_to_dict_samples(self, backup:bool=False) -> List[dict]:
        """
        Updates sample dictionaries with custom values

        Args:
            backup (bool, optional): Whether to perform backup. Defaults to False.

        Returns:
            List[dict]: Updated dictionaries
        """        
        logger.debug(f"Hello from {self.__class__.__name__} dictionary sample adjuster.")
        return [item.to_sub_dict() for item in self.submission_sample_associations]   
    
    @classmethod
    def get_details_template(cls, base_dict:dict) -> Tuple[dict, Template]:
        """
        Get the details jinja template for the correct class

        Args:
            base_dict (dict): incoming dictionary of Submission fields

        Returns:
            Tuple(dict, Template): (Updated dictionary, Template to be rendered)
        """        
        base_dict['excluded'] = ['excluded', 'reagents', 'samples', 'controls', 
                                'extraction_info', 'pcr_info', 'comment', 
                                'barcode', 'platemap', 'export_map', 'equipment']
        env = jinja_template_loading()
        temp_name = f"{cls.__name__.lower()}_details.html"
        logger.debug(f"Returning template: {temp_name}")
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
                submission_type:str|SubmissionType|None=None,
                id:int|str|None=None,
                rsl_number:str|None=None,
                start_date:date|str|int|None=None,
                end_date:date|str|int|None=None,
                reagent:Reagent|str|None=None,
                chronologic:bool=False, 
                limit:int=0, 
                **kwargs
                ) -> BasicSubmission | List[BasicSubmission]:
        """
        Lookup submissions based on a number of parameters.

        Args:
            submission_type (str | models.SubmissionType | None, optional): Submission type of interest. Defaults to None.
            id (int | str | None, optional): Submission id in the database (limits results to 1). Defaults to None.
            rsl_number (str | None, optional): Submission name in the database (limits results to 1). Defaults to None.
            start_date (date | str | int | None, optional): Beginning date to search by. Defaults to None.
            end_date (date | str | int | None, optional): Ending date to search by. Defaults to None.
            reagent (models.Reagent | str | None, optional): A reagent used in the submission. Defaults to None.
            chronologic (bool, optional): Return results in chronologic order. Defaults to False.
            limit (int, optional): Maximum number of results to return. Defaults to 0.

        Returns:
            models.BasicSubmission | List[models.BasicSubmission]: Submission(s) of interest
        """    
        
        # NOTE: if you go back to using 'model' change the appropriate cls to model in the query filters
        if submission_type == None:
            # find the subclass containing the relevant attributes
            model = cls.find_subclasses(attrs=kwargs)
        else:
            if isinstance(submission_type, SubmissionType):
                model = cls.find_subclasses(submission_type=submission_type.name)
            else:
                model = cls.find_subclasses(submission_type=submission_type)
        query: Query = cls.__database_session__.query(model)
        if start_date != None and end_date == None:
            logger.warning(f"Start date with no end date, using today.")
            end_date = date.today()
        if end_date != None and start_date == None:
            logger.warning(f"End date with no start date, using Jan 1, 2023")
            start_date = date(2023, 1, 1)
        if start_date != None:
            logger.debug(f"Querying with start date: {start_date} and end date: {end_date}")
            match start_date:
                case date():
                    # logger.debug(f"Lookup BasicSubmission by start_date({start_date})")
                    start_date = start_date.strftime("%Y-%m-%d")
                case int():
                    # logger.debug(f"Lookup BasicSubmission by ordinal start_date {start_date}")
                    start_date = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + start_date - 2).date().strftime("%Y-%m-%d")
                case _:
                    # logger.debug(f"Lookup BasicSubmission by parsed str start_date {start_date}")
                    start_date = parse(start_date).strftime("%Y-%m-%d")
            match end_date:
                case date() | datetime():
                    # logger.debug(f"Lookup BasicSubmission by end_date({end_date})")
                    end_date = end_date.strftime("%Y-%m-%d")
                case int():
                    # logger.debug(f"Lookup BasicSubmission by ordinal end_date {end_date}")
                    end_date = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + end_date - 2).date().strftime("%Y-%m-%d")
                case _:
                    # logger.debug(f"Lookup BasicSubmission by parsed str end_date {end_date}")
                    end_date = parse(end_date).strftime("%Y-%m-%d")
            # logger.debug(f"Looking up BasicSubmissions from start date: {start_date} and end date: {end_date}")
            logger.debug(f"Start date {start_date} == End date {end_date}: {start_date==end_date}")
            # logger.debug(f"Compensating for same date by using time")
            if start_date == end_date:
                start_date = datetime.strptime(start_date, "%Y-%m-%d").strftime("%Y-%m-%d %H:%M:%S.%f")
                query = query.filter(cls.submitted_date==start_date)
            else:
                query = query.filter(cls.submitted_date.between(start_date, end_date))
        # by reagent (for some reason)
        match reagent:
            case str():
                # logger.debug(f"Looking up BasicSubmission with reagent: {reagent}")
                query = query.join(cls.reagents).filter(Reagent.lot==reagent)
            case Reagent():
                # logger.debug(f"Looking up BasicSubmission with reagent: {reagent}")
                query = query.join(reagents_submissions).filter(reagents_submissions.c.reagent_id==reagent.id)
            case _:
                pass
        # by rsl number (returns only a single value)
        match rsl_number:
            case str():
                query = query.filter(cls.rsl_plate_num==rsl_number)
                # logger.debug(f"At this point the query gets: {query.all()}")
                limit = 1
            case _:
                pass
        # by id (returns only a single value)
        match id:
            case int():
                # logger.debug(f"Looking up BasicSubmission with id: {id}")
                query = query.filter(cls.id==id)
                limit = 1
            case str():
                # logger.debug(f"Looking up BasicSubmission with id: {id}")
                query = query.filter(cls.id==int(id))
                limit = 1
            case _:
                pass
        for k, v in kwargs.items():
            attr = getattr(cls, k)
            logger.debug(f"Got attr: {attr}")
            query = query.filter(attr==v)
        if len(kwargs) > 0:
            limit = 1
        if chronologic:
            query.order_by(cls.submitted_date)
        return cls.query_return(query=query, limit=limit)

    @classmethod
    def query_or_create(cls, submission_type:str|SubmissionType|None=None, **kwargs) -> BasicSubmission:
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
                raise ValueError(f"{key} is not allowed as a query argument as it could lead to creation of duplicate objects. Use .query() instead.")
        instance = cls.query(submission_type=submission_type, limit=1, **kwargs)
        # logger.debug(f"Retrieved instance: {instance}")
        if instance == None:
            used_class = cls.find_subclasses(attrs=kwargs, submission_type=submission_type)
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
        names = ["Delete", "Details", "Add Comment", "Add Equipment", "Export"]
        funcs = [self.delete, self.show_details, self.add_comment, self.add_equipment, self.backup]
        dicto = {item[0]:item[1] for item in zip(names, funcs)}
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
        logger.debug("Hello from delete")
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
        logger.debug("Hello from details")
        from frontend.widgets.submission_details import SubmissionDetails
        dlg = SubmissionDetails(parent=obj, sub=self)
        if dlg.exec():
            pass

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
            try:
                # For some reason .append results in new comment being ignored, so have to concatenate lists.
                self.comment = self.comment + comment
            except (AttributeError, TypeError) as e:
                logger.error(f"Hit error ({e}) creating comment")
                self.comment = comment
            logger.debug(self.comment)
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
            logger.debug(f"We've got equipment: {equipment}")
            for equip in equipment:
                logger.debug(f"Processing: {equip}")
                _, assoc = equip.toSQL(submission=self)
                logger.debug(f"Appending SubmissionEquipmentAssociation: {assoc}")
                assoc.save()
        else:
            pass

    def backup(self, obj=None, fname:Path|None=None, full_backup:bool=False):
        """
        Exports xlsx and yml info files for this instance.

        Args:
            obj (_type_, optional): _description_. Defaults to None.
            fname (Path | None, optional): Filename of xlsx file. Defaults to None.
            full_backup (bool, optional): Whether or not to make yaml file. Defaults to False.
        """        
        logger.debug("Hello from backup.")
        pyd = self.to_pydantic(backup=True)
        if fname == None:
            from frontend.widgets.functions import select_save_file
            fname = select_save_file(default_name=pyd.construct_filename(), extension="xlsx", obj=obj)
        logger.debug(fname.name)
        if fname.name == "":
            logger.debug(f"export cancelled.")
            return
        if full_backup:
            backup = self.to_dict(full_data=True)
            try:
                with open(self.__backup_path__.joinpath(fname.with_suffix(".yml")), "w") as f:
                    yaml.dump(backup, f)
            except KeyError as e:
                logger.error(f"Problem saving yml backup file: {e}")
        wb = pyd.autofill_excel()
        wb = pyd.autofill_samples(wb)
        wb = pyd.autofill_equipment(wb)
        wb.save(filename=fname.with_suffix(".xlsx"))

# Below are the custom submission types

class BacterialCulture(BasicSubmission):
    """
    derivative submission type from BasicSubmission
    """    
    id = Column(INTEGER, ForeignKey('_basicsubmission.id'), primary_key=True)
    controls = relationship("Control", back_populates="submission", uselist=True) #: A control sample added to submission
    __mapper_args__ = dict(polymorphic_identity="Bacterial Culture", 
                           polymorphic_load="inline", 
                           inherit_condition=(id == BasicSubmission.id))

    def to_dict(self, full_data:bool=False, backup:bool=False) -> dict:
        """
        Extends parent class method to add controls to dict

        Returns:
            dict: dictionary used in submissions summary
        """        
        output = super().to_dict(full_data=full_data, backup=backup)
        if full_data:
            output['controls'] = [item.to_sub_dict() for item in self.controls]
        return output
    
    @classmethod
    def get_abbreviation(cls) -> str:
        return "BC"

    @classmethod
    def custom_platemap(cls, xl: pd.ExcelFile, plate_map: pd.DataFrame) -> pd.DataFrame:
        """
        Stupid stopgap solution to there being an issue with the Bacterial Culture plate map. Extends parent.

        Args:
            xl (pd.ExcelFile): original xl workbook
            plate_map (pd.DataFrame): original plate map

        Returns:
            pd.DataFrame: updated plate map.
        """        
        plate_map = super().custom_platemap(xl, plate_map)
        num1 = xl.parse("Sample List").iloc[40,1]
        num2 = xl.parse("Sample List").iloc[41,1]
        logger.debug(f"Broken: {plate_map.iloc[5,0]}, {plate_map.iloc[6,0]}")
        logger.debug(f"Replace: {num1}, {num2}")
        if not check_not_nan(plate_map.iloc[5,0]):
            plate_map.iloc[5,0] = num1
        if not check_not_nan(plate_map.iloc[6,0]):
            plate_map.iloc[6,0] = num2
        return plate_map
    
    @classmethod
    def custom_autofill(cls, input_excel: Workbook, info:dict|None=None, backup:bool=False) -> Workbook:
        """
        Stupid stopgap solution to there being an issue with the Bacterial Culture plate map. Extends parent.

        Args:
            input_excel (Workbook): Input openpyxl workbook

        Returns:
            Workbook: Updated openpyxl workbook
        """        
        input_excel = super().custom_autofill(input_excel)
        sheet = input_excel['Plate Map']
        if sheet.cell(12,2).value == None:
            sheet.cell(row=12, column=2, value="=IF(ISBLANK('Sample List'!$B42),\"\",'Sample List'!$B42)")
        if sheet.cell(13,2).value == None:
            sheet.cell(row=13, column=2, value="=IF(ISBLANK('Sample List'!$B43),\"\",'Sample List'!$B43)")
        input_excel["Sample List"].cell(row=15, column=2, value=getuser()[0:2].upper())
        return input_excel

    @classmethod
    def enforce_name(cls, instr:str, data:dict|None=None) -> str:
        """
        Extends parent
        """        
        from backend.validators import RSLNamer
        data['abbreviation'] = cls.get_abbreviation()
        outstr = super().enforce_name(instr=instr, data=data)
        try:
            outstr = re.sub(r"(\d{4})-(\d{2})-(\d{2})", r"\1\2\3", outstr)
            outstr = re.sub(r"BC(\d{6})", r"BC-\1", outstr, flags=re.IGNORECASE)
        except (AttributeError, TypeError) as e:
            outstr = RSLNamer.construct_new_plate_name(data=data)
        return outstr

    @classmethod
    def get_regex(cls) -> str:
        """
        Retrieves string for regex construction.

        Returns:
            str: string for regex construction
        """        
        return "(?P<Bacterial_Culture>RSL(?:-|_)?BC(?:-|_)?20\d{2}-?\d{2}-?\d{2}(?:(_|-)?\d?([^_0123456789\s]|$)?R?\d?)?)"
    
    @classmethod
    def filename_template(cls):
        """
        extends parent
        """        
        template = super().filename_template()
        template += "_{{ submitting_lab }}_{{ submitter_plate_num }}"
        return template
    
    @classmethod
    def parse_info(cls, input_dict: dict, xl: pd.ExcelFile | None = None) -> dict:
        """
        Extends parent
        """        
        input_dict = super().parse_info(input_dict, xl)
        input_dict['submitted_date']['missing'] = True
        return input_dict

    @classmethod
    def custom_sample_autofill_row(cls, sample, worksheet: Worksheet) -> int:
        """
        Extends parent
        """        
        logger.debug(f"Checking {sample.well}")
        logger.debug(f"here's the worksheet: {worksheet}")
        row = super().custom_sample_autofill_row(sample, worksheet)
        df = pd.DataFrame(list(worksheet.values))
        # logger.debug(f"Here's the dataframe: {df}")
        idx = df[df[0]==sample.well]
        if idx.empty:
            new = f"{sample.well[0]}{sample.well[1:].zfill(2)}"
            logger.debug(f"Checking: {new}")
            idx = df[df[0]==new]
        logger.debug(f"Here is the row: {idx}")
        row = idx.index.to_list()[0]
        return row + 1

class Wastewater(BasicSubmission):
    """
    derivative submission type from BasicSubmission
    """    
    id = Column(INTEGER, ForeignKey('_basicsubmission.id'), primary_key=True)
    ext_technician = Column(String(64)) #: Name of technician doing extraction
    pcr_technician = Column(String(64)) #: Name of technician doing pcr
    pcr_info = Column(JSON) #: unstructured output from pcr table logger or user(Artic)

    __mapper_args__ = __mapper_args__ = dict(polymorphic_identity="Wastewater", 
                           polymorphic_load="inline", 
                           inherit_condition=(id == BasicSubmission.id))

    def to_dict(self, full_data:bool=False, backup:bool=False) -> dict:
        """
        Extends parent class method to add controls to dict

        Returns:
            dict: dictionary used in submissions summary
        """        
        output = super().to_dict(full_data=full_data)
        try:
            output['pcr_info'] = json.loads(self.pcr_info)
        except TypeError as e:
            pass
        output['Technician'] = f"Enr: {self.technician}, Ext: {self.ext_technician}, PCR: {self.pcr_technician}"
        
        return output
    
    @classmethod
    def get_abbreviation(cls) -> str:
        return "WW"

    @classmethod
    def parse_info(cls, input_dict:dict, xl:pd.ExcelFile|None=None) -> dict:
        """
        Update submission dictionary with type specific information. Extends parent

        Args:
            input_dict (dict): Input sample dictionary

        Returns:
            dict: Updated sample dictionary
        """        
        input_dict = super().parse_info(input_dict)
        if xl != None:
            input_dict['csv'] = xl.parse("Copy to import file")
        return input_dict
    
    @classmethod
    def parse_pcr(cls, xl: pd.ExcelFile, rsl_number:str) -> list:
        """
        Parse specific to wastewater samples.
        """        
        samples = super().parse_pcr(xl=xl, rsl_number=rsl_number)
        df = xl.parse(sheet_name="Results", dtype=object).fillna("")
        column_names = ["Well", "Well Position", "Omit","Sample","Target","Task"," Reporter","Quencher","Amp Status","Amp Score","Curve Quality","Result Quality Issues","Cq","Cq Confidence","Cq Mean","Cq SD","Auto Threshold","Threshold", "Auto Baseline", "Baseline Start", "Baseline End"]
        samples_df = df.iloc[23:][0:]
        logger.debug(f"Dataframe of PCR results:\n\t{samples_df}")
        samples_df.columns = column_names
        logger.debug(f"Samples columns: {samples_df.columns}")
        well_call_df = xl.parse(sheet_name="Well Call").iloc[24:][0:].iloc[:,-1:]
        try:
            samples_df['Assessment'] = well_call_df.values
        except ValueError:
            logger.error("Well call number doesn't match sample number")
        logger.debug(f"Well call df: {well_call_df}")
        for ii, row in samples_df.iterrows():
            try:
                sample_obj = [sample for sample in samples if sample['sample'] == row[3]][0]    
            except IndexError:
                sample_obj = dict(
                    sample = row['Sample'],
                    plate_rsl = rsl_number,
                )
            logger.debug(f"Got sample obj: {sample_obj}") 
            if isinstance(row['Cq'], float):
                sample_obj[f"ct_{row['Target'].lower()}"] = row['Cq']
            else:
                sample_obj[f"ct_{row['Target'].lower()}"] = 0.0
            try:
                sample_obj[f"{row['Target'].lower()}_status"] = row['Assessment']
            except KeyError:
                logger.error(f"No assessment for {sample_obj['sample']}")
            samples.append(sample_obj)
        return samples
    
    @classmethod
    def enforce_name(cls, instr:str, data:dict|None=None) -> str:
        """
        Extends parent
        """        
        from backend.validators import RSLNamer
        data['abbreviation'] = cls.get_abbreviation()
        outstr = super().enforce_name(instr=instr, data=data)
        try:
            outstr = re.sub(r"PCR(-|_)", "", outstr)
        except AttributeError as e:
            logger.error(f"Problem using regex: {e}")
            outstr = RSLNamer.construct_new_plate_name(instr=outstr)
        outstr = outstr.replace("RSLWW", "RSL-WW")
        outstr = re.sub(r"WW(\d{4})", r"WW-\1", outstr, flags=re.IGNORECASE)
        outstr = re.sub(r"(\d{4})-(\d{2})-(\d{2})", r"\1\2\3", outstr)
        # logger.debug(f"Coming out of the preliminary parsing, the plate name is {outstr}")
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
        return re.sub(r"(-\dR)\d?", rf"\1 {repeat}", outstr).replace(" ", "")

    @classmethod
    def get_regex(cls) -> str:
        """
        Retrieves string for regex construction

        Returns:
            str: String for regex construction
        """        
        return "(?P<Wastewater>RSL(?:-|_)?WW(?:-|_)?20\d{2}-?\d{2}-?\d{2}(?:(_|-)?\d?([^_0123456789\s]|$)?R?\d?)?)"
  
    @classmethod
    def adjust_autofill_samples(cls, samples: List[Any]) -> List[Any]:
        """
        Extends parent
        """
        samples = super().adjust_autofill_samples(samples)
        return [item for item in samples if not item.submitter_id.startswith("EN")]
    
    @classmethod
    def custom_sample_autofill_row(cls, sample, worksheet: Worksheet) -> int:
        """
        Extends parent
        """        
        logger.debug(f"Checking {sample.well}")
        logger.debug(f"here's the worksheet: {worksheet}")
        row = super().custom_sample_autofill_row(sample, worksheet)
        df = pd.DataFrame(list(worksheet.values))
        logger.debug(f"Here's the dataframe: {df}")
        idx = df[df[1]==sample.sample_location]
        logger.debug(f"Here is the row: {idx}")
        row = idx.index.to_list()[0]
        return row + 1

class WastewaterArtic(BasicSubmission):
    """
    derivative submission type for artic wastewater
    """    
    id = Column(INTEGER, ForeignKey('_basicsubmission.id'), primary_key=True)
    artic_technician = Column(String(64)) #: Name of technician performing artic
    dna_core_submission_number = Column(String(64)) #: Number used by core as id
    pcr_info = Column(JSON) #: unstructured output from pcr table logger or user(Artic)
    gel_image = Column(String(64)) #: file name of gel image in zip file
    gel_info = Column(JSON) #: unstructured data from gel.

    __mapper_args__ = dict(polymorphic_identity="Wastewater Artic", 
                           polymorphic_load="inline", 
                           inherit_condition=(id == BasicSubmission.id))

    def calculate_base_cost(self):
        """
        This method overrides parent method due to multiple output plates from a single submission
        """        
        logger.debug(f"Hello from calculate base cost in WWArtic")
        try:
            cols_count_96 = math.ceil(int(self.sample_count) / 8)
        except Exception as e:
            logger.error(f"Column count error: {e}")
        assoc = [item for item in self.extraction_kit.kit_submissiontype_associations if item.submission_type == self.submission_type][0]
        # Since we have multiple output plates per submission form, the constant cost will have to reflect this.
        output_plate_count = math.ceil(int(self.sample_count) / 16)
        logger.debug(f"Looks like we have {output_plate_count} output plates.")
        const_cost = assoc.constant_cost * output_plate_count
        try:
            self.run_cost = const_cost + (assoc.mutable_cost_column * cols_count_96) + (assoc.mutable_cost_sample * int(self.sample_count))
        except Exception as e:
            logger.error(f"Calculation error: {e}")

    def to_dict(self, full_data:bool=False, backup:bool=False) -> dict:
        """
        Extends parent class method to add controls to dict

        Returns:
            dict: dictionary used in submissions summary
        """        
        output = super().to_dict(full_data=full_data)
        output['gel_info'] = self.gel_info
        output['gel_image'] = self.gel_image
        output['dna_core_submission_number'] = self.dna_core_submission_number
        return output

    @classmethod
    def get_abbreviation(cls) -> str:
        return "AR"

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
        if "ENC" in input_dict['submitter_id']:
            input_dict['submitter_id'] = cls.en_adapter(input_str=input_dict['submitter_id'])
        return input_dict
    
    @classmethod
    def en_adapter(cls, input_str:str) -> str:
        """
        Stopgap solution because WW names their ENs different

        Args:
            input_str (str): input name

        Returns:
            str: output name
        """        
        processed = re.sub(r"[A-Z]", "", input_str)
        try:
            en_num = re.search(r"\-\d{1}$", processed).group()
            processed = rreplace(processed, en_num, "")
        except AttributeError:
            en_num = "1"
        en_num = en_num.strip("-")
        # logger.debug(f"Processed after en-num: {processed}")
        try: 
            plate_num = re.search(r"\-\d{1}$", processed).group()
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
        return f"EN{year}{month}{day}-{en_num}"

    @classmethod
    def enforce_name(cls, instr:str|None=None, data:dict|None=None) -> str:
        """
        Extends parent
        """        
        from backend.validators import RSLNamer
        data['abbreviation'] = cls.get_abbreviation()
        outstr = super().enforce_name(instr=instr, data=data)
        try:
            outstr = re.sub(r"(\d{4})-(\d{2})-(\d{2})", r"RSL-AR-\1\2\3", outstr, flags=re.IGNORECASE)
        except (AttributeError, TypeError):
            if instr != None:
                data['rsl_plate_num'] = instr
            # logger.debug(f"Create new plate name from submission parameters")
            outstr = RSLNamer.construct_new_plate_name(data=data)
        try:
            plate_number = int(re.search(r"_|-\d?_", outstr).group().strip("_").strip("-"))
        except (AttributeError, ValueError) as e:
            plate_number = 1
        return re.sub(r"(_|-\d)?_ARTIC", f"-{plate_number}", outstr)

    @classmethod
    def get_regex(cls) -> str:
        """
        Retrieves string for regex construction

        Returns:
            str: string for regex construction.
        """        
        return "(?P<Wastewater_Artic>(\\d{4}-\\d{2}-\\d{2}(?:-|_)(?:\\d_)?artic)|(RSL(?:-|_)?AR(?:-|_)?20\\d{2}-?\\d{2}-?\\d{2}(?:(_|-)\\d?(\\D|$)R?\\d?)?))"

    @classmethod
    def finalize_parse(cls, input_dict: dict, xl: pd.ExcelFile | None = None, info_map: dict | None = None, plate_map: dict | None = None) -> dict:
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
        input_dict = super().finalize_parse(input_dict, xl, info_map, plate_map)
        # logger.debug(pformat(input_dict))
        # logger.debug(pformat(info_map))
        # logger.debug(pformat(plate_map))
        samples = []
        for sample in input_dict['samples']:
            logger.debug(f"Input sample: {pformat(sample.__dict__)}")
            if sample.submitter_id == "NTC1":
                samples.append(dict(sample=sample.submitter_id, destination_row=8, destination_column=2, source_row=0, source_column=0, plate_number='control', plate=None))
                continue
            elif sample.submitter_id == "NTC2":
                samples.append(dict(sample=sample.submitter_id, destination_row=8, destination_column=5, source_row=0, source_column=0, plate_number='control', plate=None))
                continue
            destination_row = sample.row[0]
            destination_column = sample.column[0]
            # logger.debug(f"Looking up: {sample.submitter_id} friend.")
            lookup_sample = BasicSample.query(submitter_id=sample.submitter_id)
            lookup_ssa = SubmissionSampleAssociation.query(sample=lookup_sample, exclude_submission_type=cls.__mapper_args__['polymorphic_identity'] , chronologic=True, reverse=True, limit=1)
            try:
                plate = lookup_ssa.submission.rsl_plate_num
                source_row = lookup_ssa.row
                source_column = lookup_ssa.column
            except AttributeError as e:
                logger.error(f"Problem with lookup: {e}")
                plate = "Error"
                source_row = 0
                source_column = 0
                # continue
            output_sample = dict(
                sample=sample.submitter_id,
                destination_column=destination_column, 
                destination_row=destination_row,
                plate=plate,
                source_column=source_column,
                source_row = source_row
                )
            logger.debug(f"output sample: {pformat(output_sample)}")
            samples.append(output_sample)
        plates = sorted(list(set([sample['plate'] for sample in samples if sample['plate'] != None and sample['plate'] != "Error"])))
        logger.debug(f"Here's what I got for plates: {plates}")
        for iii, plate in enumerate(plates):
            for sample in samples:
                if sample['plate'] == plate:
                    sample['plate_number'] = iii + 1
        df = pd.DataFrame.from_records(samples).fillna(value="")
        try:
            df.source_row = df.source_row.astype(int)
            df.source_column = df.source_column.astype(int)
            df.sort_values(by=['destination_column', 'destination_row'], inplace=True)
        except AttributeError as e:
            logger.error(f"Couldn't construct df due to {e}")
        input_dict['csv'] = df
        return input_dict

    @classmethod
    def custom_autofill(cls, input_excel: Workbook, info: dict | None = None, backup: bool = False) -> Workbook:
        """
        Adds custom autofill methods for submission. Extends Parent

        Args:
            input_excel (Workbook): initial workbook.
            info (dict | None, optional): dictionary of additional info. Defaults to None.
            backup (bool, optional): Whether this is part of a backup operation. Defaults to False.

        Returns:
            Workbook: Updated workbook
        """
        input_excel = super().custom_autofill(input_excel, info, backup)
        worksheet = input_excel["First Strand List"]
        samples = cls.query(rsl_number=info['rsl_plate_num']['value']).submission_sample_associations
        samples = sorted(samples, key=attrgetter('column', 'row'))
        source_plates = []
        first_samples = []
        for sample in samples:
            sample = sample.sample
            try:
                assoc = [item.submission.rsl_plate_num for item in sample.sample_submission_associations if item.submission.submission_type_name=="Wastewater"][-1]
            except IndexError:
                logger.error(f"Association not found for {sample}")
                continue
            if assoc not in source_plates:
                source_plates.append(assoc)
                first_samples.append(sample.ww_processing_num)
        # Pad list to length of 3
        source_plates += ['None'] * (3 - len(source_plates))
        first_samples += [''] * (3 - len(first_samples))
        source_plates = zip(source_plates, first_samples, strict=False)
        for iii, plate in enumerate(source_plates, start=8):
            logger.debug(f"Plate: {plate}")
            for jjj, value in enumerate(plate, start=3):
                worksheet.cell(row=iii, column=jjj, value=value)
        logger.debug(f"Info:\n{pformat(info)}")
        check = 'gel_info' in info.keys() and info['gel_info']['value'] != None
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
                        worksheet.cell(row=row, column=column, value=kj['value'])
        check = 'gel_image' in info.keys() and info['gel_image']['value'] != None
        if check:
            if info['gel_image'] != None:
                worksheet = input_excel['Egel results']
                logger.debug(f"We got an image: {info['gel_image']}")
                with ZipFile(cls.__directory_path__.joinpath("submission_imgs.zip")) as zipped:
                    z = zipped.extract(info['gel_image']['value'], Path(TemporaryDirectory().name))
                    img = OpenpyxlImage(z)
                    img.height = 400 # insert image height in pixels as float or int (e.g. 305.5)
                    img.width = 600
                    img.anchor = 'B9'
                    worksheet.add_image(img)
        return input_excel

    @classmethod
    def get_details_template(cls, base_dict:dict) -> Tuple[dict, Template]:
        """
        Get the details jinja template for the correct class. Extends parent

        Args:
            base_dict (dict): incoming dictionary of Submission fields

        Returns:
            Tuple[dict, Template]: (Updated dictionary, Template to be rendered)
        """        
        base_dict, template = super().get_details_template(base_dict=base_dict)
        base_dict['excluded'] += ['gel_info', 'gel_image', 'headers', "dna_core_submission_number"]
        base_dict['DNA Core ID'] = base_dict['dna_core_submission_number']
        check = 'gel_info' in base_dict.keys() and base_dict['gel_info'] != None
        if check:
            headers = [item['name'] for item in base_dict['gel_info'][0]['values']]
            base_dict['headers'] = [''] * (4 - len(headers))
            base_dict['headers'] += headers
            logger.debug(f"Gel info: {pformat(base_dict['headers'])}")
        check = 'gel_image' in base_dict.keys() and base_dict['gel_image'] != None
        if check:
            with ZipFile(cls.__directory_path__.joinpath("submission_imgs.zip")) as zipped:
                base_dict['gel_image'] = base64.b64encode(zipped.read(base_dict['gel_image'])).decode('utf-8')
        return base_dict, template

    def adjust_to_dict_samples(self, backup:bool=False) -> List[dict]:
        """
        Updates sample dictionaries with custom values

        Args:
            backup (bool, optional): Whether to perform backup. Defaults to False.

        Returns:
            List[dict]: Updated dictionaries
        """       
        logger.debug(f"Hello from {self.__class__.__name__} dictionary sample adjuster.")
        if backup:
            output = []
            for assoc in self.submission_sample_associations:
                dicto = assoc.to_sub_dict()
                old_sub = assoc.sample.get_previous_ww_submission(current_artic_submission=self)
                try:
                    dicto['plate_name'] = old_sub.rsl_plate_num
                except AttributeError:
                    dicto['plate_name'] = ""
                old_assoc = WastewaterAssociation.query(submission=old_sub, sample=assoc.sample, limit=1)
                dicto['well'] = f"{row_map[old_assoc.row]}{old_assoc.column}"
                output.append(dicto)
        else:
            output = super().adjust_to_dict_samples(backup=False)
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
    
    def gel_box(self, obj):
        """
        Creates widget to perform gel viewing operations

        Args:
            obj (_type_): parent widget
        """        
        from frontend.widgets.gel_checker import GelBox
        from frontend.widgets import select_open_file
        fname = select_open_file(obj=obj, file_extension="jpg")
        dlg = GelBox(parent=obj, img_path=fname)
        if dlg.exec():
            self.dna_core_submission_number, img_path, output = dlg.parse_form()
            self.gel_image = img_path.name
            self.gel_info = output
            logger.debug(pformat(self.gel_info))
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

    id = Column(INTEGER, primary_key=True) #: primary key
    submitter_id = Column(String(64), nullable=False, unique=True) #: identification from submitter
    sample_type = Column(String(32)) #: subtype of sample

    sample_submission_associations = relationship(
        "SubmissionSampleAssociation",
        back_populates="sample",
        cascade="all, delete-orphan",
    ) #: associated submissions

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

    submissions = association_proxy("sample_submission_associations", "submission") #: proxy of associated submissions

    @validates('submitter_id')
    def create_id(self, key:str, value:str):
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
    
    def to_sub_dict(self) -> dict:
        """
        gui friendly dictionary, extends parent method.

        Returns:
            dict: well location and name (sample id, organism) NOTE: keys must sync with WWSample to_sub_dict above
        """
        # logger.debug(f"Converting {self} to dict.")
        sample = {}
        sample['submitter_id'] = self.submitter_id
        sample['sample_type'] = self.sample_type
        return sample

    def set_attribute(self, name:str, value):
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
    def find_subclasses(cls, attrs:dict|None=None, sample_type:str|None=None) -> BasicSample:
        """
        Retrieves subclass of BasicSample based on type or possessed attributes.

        Args:
            attrs (dict | None, optional): attributes for query. Defaults to None.
            sample_type (str | None, optional): sample type by name. Defaults to None.

        Raises:
            AttributeError: Raised if class containing all given attributes cannot be found.

        Returns:
            BasicSample: sample type object of interest
        """        
        if sample_type != None:
            return cls.find_polymorphic_subclass(polymorphic_identity=sample_type)
        if len(attrs) == 0 or attrs == None:
            logger.warning(f"No attr, returning {cls}")
            return cls
        if any([not hasattr(cls, attr) for attr in attrs]):
            logger.debug(f"{cls} is missing attrs. searching for better match.")
            # looks for first model that has all included kwargs
            try:
                model = [subclass for subclass in cls.__subclasses__() if all([hasattr(subclass, attr) for attr in attrs])][0]
            except IndexError as e:
                raise AttributeError(f"Couldn't find existing class/subclass of {cls} with all attributes:\n{pformat(attrs)}")
        else:
            # logger.debug(f"{cls} has all necessary attributes, returning")
            return cls
        # logger.debug(f"Using model: {model}")
        return model
    
    @classmethod
    def find_polymorphic_subclass(cls, polymorphic_identity:str|None=None) -> BasicSample:
        """
        Retrieves subclasses of BasicSample based on type name.

        Args:
            polymorphic_identity (str | None, optional): Name of subclass fed to polymorphic identity. Defaults to None.

        Returns:
            BasicSample: Subclass of interest.
        """          
        if isinstance(polymorphic_identity, dict):
            polymorphic_identity = polymorphic_identity['value']
        if polymorphic_identity == None:
            return cls
        else:
            try:
                return [item for item in cls.__subclasses__() if item.__mapper_args__['polymorphic_identity']==polymorphic_identity][0]
            except Exception as e:
                logger.error(f"Could not get polymorph {polymorphic_identity} of {cls} due to {e}")
                return cls

    @classmethod
    def parse_sample(cls, input_dict:dict) -> dict:
        f"""
        Custom sample parser

        Args:
            input_dict (dict): Basic parser results.

        Returns:
            dict: Updated parser results.
        """        
        return input_dict
    
    @classmethod
    @setup_lookup
    def query(cls, 
              submitter_id:str|None=None,
              sample_type:str|None=None,
              limit:int=0,
              **kwargs
              ) -> BasicSample|List[BasicSample]:
        """
        Lookup samples in the database by a number of parameters.

        Args:
            submitter_id (str | None, optional): Name of the sample (limits results to 1). Defaults to None.
            sample_type (str | None, optional): Sample type. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            models.BasicSample|List[models.BasicSample]: Sample(s) of interest.
        """    
        if sample_type == None:
            model = cls.find_subclasses(attrs=kwargs)
        else:
            model = cls.find_subclasses(sample_type=sample_type)
        logger.debug(f"Length of kwargs: {len(kwargs)}")
        # model = models.BasicSample.find_subclasses(ctx=ctx, attrs=kwargs)
        # query: Query = setup_lookup(ctx=ctx, locals=locals()).query(model)
        query: Query = cls.__database_session__.query(model)
        match submitter_id:
            case str():
                # logger.debug(f"Looking up {model} with submitter id: {submitter_id}")
                query = query.filter(model.submitter_id==submitter_id)
                limit = 1
            case _:
                pass
        match sample_type:
            case str():
                logger.warning(f"Looking up samples with sample_type is disabled.")
                # query = query.filter(models.BasicSample.sample_type==sample_type)
            case _:
                pass
        for k, v in kwargs.items():
            attr = getattr(model, k)
            # logger.debug(f"Got attr: {attr}")
            query = query.filter(attr==v)
        if len(kwargs) > 0:
            limit = 1
        return cls.query_return(query=query, limit=limit)
    
    @classmethod
    def query_or_create(cls, sample_type:str|None=None, **kwargs) -> BasicSample:
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
        for key in kwargs.keys():
            if key in disallowed:
                raise ValueError(f"{key} is not allowed as a query argument as it could lead to creation of duplicate objects.")
        instance = cls.query(sample_type=sample_type, limit=1, **kwargs)
        logger.debug(f"Retrieved instance: {instance}")
        if instance == None:
            used_class = cls.find_subclasses(attrs=kwargs, sample_type=sample_type)
            instance = used_class(**kwargs)
            instance.sample_type = sample_type
            logger.debug(f"Creating instance: {instance}")
        return instance

    def delete(self):
        raise AttributeError(f"Delete not implemented for {self.__class__}")

#Below are the custom sample types

class WastewaterSample(BasicSample):
    """
    Derivative wastewater sample
    """
    id = Column(INTEGER, ForeignKey('_basicsample.id'), primary_key=True)
    ww_processing_num = Column(String(64)) #: wastewater processing number 
    ww_full_sample_id = Column(String(64)) #: full id given by entrics
    rsl_number = Column(String(64)) #: rsl plate identification number
    collection_date = Column(TIMESTAMP) #: Date sample collected
    received_date = Column(TIMESTAMP) #: Date sample received
    notes = Column(String(2000)) #: notes from submission form
    sample_location = Column(String(8)) #: location on 24 well plate
    __mapper_args__ = dict(polymorphic_identity="Wastewater Sample", 
                           polymorphic_load="inline", 
                           inherit_condition=(id == BasicSample.id))

    def to_sub_dict(self) -> dict:
        """
        gui friendly dictionary, extends parent method.

        Returns:
            dict: well location and name (sample id, organism) NOTE: keys must sync with WWSample to_sub_dict above
        """
        sample = super().to_sub_dict()
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
        if output_dict['rsl_number'] == None:
            output_dict['rsl_number'] = output_dict['submitter_id']
        if output_dict['ww_full_sample_id'] != None:
            output_dict["submitter_id"] = output_dict['ww_full_sample_id']
        # Ad hoc repair method for WW (or possibly upstream) not formatting some dates properly.
        match output_dict['collection_date']:
            case str():
                try:
                    output_dict['collection_date'] = parse(output_dict['collection_date']).date()
                except ParserError:
                    logger.error(f"Problem parsing collection_date: {output_dict['collection_date']}")
                    output_dict['collection_date'] = date(1,1,1)
            case datetime():
                output_dict['collection_date'] = output_dict['collection_date'].date()
            case date():
                pass
            case _:
                del output_dict['collection_date']
        return output_dict
    
    def get_previous_ww_submission(self, current_artic_submission:WastewaterArtic):
        # assocs = [assoc for assoc in self.sample_submission_associations if assoc.submission.submission_type_name=="Wastewater"]
        subs = self.submissions[:self.submissions.index(current_artic_submission)]
        subs = [sub for sub in subs if sub.submission_type_name=="Wastewater"]
        logger.debug(f"Submissions up to current artic submission: {subs}")
        try:
            return subs[-1]
        except IndexError:
            return None

class BacterialCultureSample(BasicSample):
    """
    base of bacterial culture sample
    """
    id = Column(INTEGER, ForeignKey('_basicsample.id'), primary_key=True)
    organism = Column(String(64)) #: bacterial specimen
    concentration = Column(String(16)) #: sample concentration
    control = relationship("Control", back_populates="sample", uselist=False)
    __mapper_args__ = dict(polymorphic_identity="Bacterial Culture Sample", 
                           polymorphic_load="inline", 
                           inherit_condition=(id == BasicSample.id))

    def to_sub_dict(self) -> dict:
        """
        gui friendly dictionary, extends parent method.

        Returns:
            dict: well location and name (sample id, organism) NOTE: keys must sync with WWSample to_sub_dict above
        """
        sample = super().to_sub_dict()
        sample['name'] = self.submitter_id
        sample['organism'] = self.organism
        sample['concentration'] = self.concentration
        if self.control != None:
            sample['colour'] = [0,128,0]
            sample['tooltip'] = f"Control: {self.control.controltype.name} - {self.control.controltype.targets}"
        return sample

# Submission to Sample Associations

class SubmissionSampleAssociation(BaseClass):
    """
    table containing submission/sample associations
    DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
    """    
    
    id = Column(INTEGER, unique=True, nullable=False) #: id to be used for inheriting purposes
    sample_id = Column(INTEGER, ForeignKey("_basicsample.id"), nullable=False) #: id of associated sample
    submission_id = Column(INTEGER, ForeignKey("_basicsubmission.id"), primary_key=True) #: id of associated submission
    row = Column(INTEGER, primary_key=True) #: row on the 96 well plate
    column = Column(INTEGER, primary_key=True) #: column on the 96 well plate

    # reference to the Submission object
    submission = relationship(BasicSubmission, back_populates="submission_sample_associations") #: associated submission

    # reference to the Sample object
    sample = relationship(BasicSample, back_populates="sample_submission_associations") #: associated sample

    base_sub_type = Column(String) #: string of subtype name
    
    # Refers to the type of parent.
    # Hooooooo boy, polymorphic association type, now we're getting into the weeds!
    __mapper_args__ = {
        "polymorphic_identity": "Basic Association",
        "polymorphic_on": base_sub_type,
        "with_polymorphic": "*",
    }

    def __init__(self, submission:BasicSubmission=None, sample:BasicSample=None, row:int=1, column:int=1, id:int|None=None):
        self.submission = submission
        self.sample = sample
        self.row = row
        self.column = column
        if id != None:
            self.id = id
        else:
            self.id = self.__class__.autoincrement_id()
        logger.debug(f"Using id: {self.id}")

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
        sample['name'] = self.sample.submitter_id
        sample['row'] = self.row
        sample['column'] = self.column
        try:
            sample['well'] = f"{row_map[self.row]}{self.column}"
        except KeyError as e:
            logger.error(f"Unable to find row {self.row} in row_map.")
            sample['well'] = None
        sample['plate_name'] = self.submission.rsl_plate_num
        sample['positive'] = False
        return sample
    
    def to_hitpick(self) -> dict|None:
        """
        Outputs a dictionary usable for html plate maps.

        Returns:
            dict: dictionary of sample id, row and column in elution plate
        """        
        # Since there is no PCR, negliable result is necessary.
        sample = self.to_sub_dict()
        logger.debug(f"Sample dict to hitpick: {sample}")
        env = jinja_template_loading()
        template = env.get_template("tooltip.html")
        tooltip_text = template.render(fields=sample)
        try:
            tooltip_text += sample['tooltip']
        except KeyError:
            pass
        sample.update(dict(name=self.sample.submitter_id[:10], tooltip=tooltip_text))
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
    def find_polymorphic_subclass(cls, polymorphic_identity:str|None=None) -> SubmissionSampleAssociation:   
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
                output = [item for item in cls.__subclasses__() if item.__mapper_args__['polymorphic_identity']==polymorphic_identity][0]
            except Exception as e:
                logger.error(f"Could not get polymorph {polymorphic_identity} of {cls} due to {e}")
                output = cls
        logger.debug(f"Using SubmissionSampleAssociation subclass: {output}")
        return output
            
    @classmethod
    @setup_lookup
    def query(cls, 
              submission:BasicSubmission|str|None=None,
              exclude_submission_type:str|None=None,
              sample:BasicSample|str|None=None,
              row:int=0,
              column:int=0,
              limit:int=0,
              chronologic:bool=False,
              reverse:bool=False,
              ) -> SubmissionSampleAssociation|List[SubmissionSampleAssociation]:
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
                query = query.filter(cls.submission==submission)
            case str():
                # logger.debug(f"Lookup SampleSubmissionAssociation with submission str {submission}")
                query = query.join(BasicSubmission).filter(BasicSubmission.rsl_plate_num==submission)
            case _:
                pass
        match sample:
            case BasicSample():
                # logger.debug(f"Lookup SampleSubmissionAssociation with sample BasicSample {sample}")
                query = query.filter(cls.sample==sample)
            case str():
                # logger.debug(f"Lookup SampleSubmissionAssociation with sample str {sample}")
                query = query.join(BasicSample).filter(BasicSample.submitter_id==sample)
            case _:
                pass
        if row > 0:
            query = query.filter(cls.row==row)
        if column > 0:
            query = query.filter(cls.column==column)
        match exclude_submission_type:
            case str():
                # logger.debug(f"filter SampleSubmissionAssociation to exclude submission type {exclude_submission_type}")
                query = query.join(BasicSubmission).filter(BasicSubmission.submission_type_name != exclude_submission_type)
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
        return cls.query_return(query=query, limit=limit)
    
    @classmethod
    def query_or_create(cls,
                association_type:str="Basic Association", 
                submission:BasicSubmission|str|None=None,
                sample:BasicSample|str|None=None,
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
        logger.debug(f"Attempting create or query with {kwargs}")
        match submission:
            case BasicSubmission():
                pass
            case str():
                submission = BasicSubmission.query(rsl_number=submission)
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
        if instance == None:
            used_cls = cls.find_polymorphic_subclass(polymorphic_identity=association_type)
            instance = used_cls(submission=submission, sample=sample, id=id, **kwargs)
        return instance

    def delete(self):
        raise AttributeError(f"Delete not implemented for {self.__class__}")

class WastewaterAssociation(SubmissionSampleAssociation):
    
    id = Column(INTEGER, ForeignKey("_submissionsampleassociation.id"), primary_key=True)
    ct_n1 = Column(FLOAT(2)) #: AKA ct for N1
    ct_n2 = Column(FLOAT(2)) #: AKA ct for N2
    n1_status = Column(String(32)) #: positive or negative for N1
    n2_status = Column(String(32)) #: positive or negative for N2
    pcr_results = Column(JSON) #: imported PCR status from QuantStudio

    __mapper_args__ = dict(polymorphic_identity="Wastewater Association", 
                           polymorphic_load="inline", 
                           inherit_condition=(id==SubmissionSampleAssociation.id))
    
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
            sample['tooltip'] += f"<br>- ct N1: {'{:.2f}'.format(self.ct_n1)} ({self.n1_status})<br>- ct N2: {'{:.2f}'.format(self.ct_n2)} ({self.n2_status})"
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
            parent = [base for base in cls.__bases__ if base.__name__=="SubmissionSampleAssociation"][0]
            return max([item.id for item in parent.query()]) + 1
        except ValueError as e:
            logger.error(f"Problem incrementing id: {e}")
            return 1
               