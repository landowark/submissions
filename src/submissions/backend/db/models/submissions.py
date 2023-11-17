'''
Models for the main submission types.
'''
from __future__ import annotations
from getpass import getuser
import math
from pprint import pformat
from . import Reagent, SubmissionType, KitType, Organization
from sqlalchemy import Column, String, TIMESTAMP, INTEGER, ForeignKey, Table, JSON, FLOAT, case
from sqlalchemy.orm import relationship, validates, Query, declared_attr
import logging
import json
from json.decoder import JSONDecodeError
from math import ceil
from sqlalchemy.ext.associationproxy import association_proxy
import uuid
import re
import pandas as pd
from openpyxl import Workbook
from . import Base
from tools import check_not_nan, row_map,  query_return, setup_lookup
from datetime import datetime, date
from typing import List
from dateutil.parser import parse
from dateutil.parser._parser import ParserError
import yaml
from sqlalchemy.exc import OperationalError as AlcOperationalError, IntegrityError as AlcIntegrityError, StatementError
from sqlite3 import OperationalError as SQLOperationalError, IntegrityError as SQLIntegrityError

logger = logging.getLogger(f"submissions.{__name__}")

# table containing reagents/submission relationships
reagents_submissions = Table(
                                "_reagents_submissions", 
                                Base.metadata, 
                                Column("reagent_id", INTEGER, ForeignKey("_reagents.id")), 
                                Column("submission_id", INTEGER, ForeignKey("_submissions.id")),
                                extend_existing = True
                            )

class BasicSubmission(Base):
    """
    Concrete of basic submission which polymorphs into BacterialCulture and Wastewater
    """
    # @declared_attr
    # def __tablename__(cls):
    #     return cls.__name__.lower()
    __tablename__ = "_submissions"
    __table_args__ = {'extend_existing': True} 

    id = Column(INTEGER, primary_key=True) #: primary key   
    rsl_plate_num = Column(String(32), unique=True, nullable=False) #: RSL name (e.g. RSL-22-0012)
    submitter_plate_num = Column(String(127), unique=True) #: The number given to the submission by the submitting lab
    submitted_date = Column(TIMESTAMP) #: Date submission received
    submitting_lab = relationship("Organization", back_populates="submissions") #: client org
    submitting_lab_id = Column(INTEGER, ForeignKey("_organizations.id", ondelete="SET NULL", name="fk_BS_sublab_id")) #: client lab id from _organizations
    sample_count = Column(INTEGER) #: Number of samples in the submission
    extraction_kit = relationship("KitType", back_populates="submissions") #: The extraction kit used
    extraction_kit_id = Column(INTEGER, ForeignKey("_kits.id", ondelete="SET NULL", name="fk_BS_extkit_id"))
    submission_type_name = Column(String, ForeignKey("_submission_types.name", ondelete="SET NULL", name="fk_BS_subtype_name"))
    technician = Column(String(64)) #: initials of processing tech(s)
    # Move this into custom types?
    reagents = relationship("Reagent", back_populates="submissions", secondary=reagents_submissions) #: relationship to reagents
    reagents_id = Column(String, ForeignKey("_reagents.id", ondelete="SET NULL", name="fk_BS_reagents_id")) #: id of used reagents
    extraction_info = Column(JSON) #: unstructured output from the extraction table logger.
    pcr_info = Column(JSON) #: unstructured output from pcr table logger or user(Artic)
    run_cost = Column(FLOAT(2)) #: total cost of running the plate. Set from constant and mutable kit costs at time of creation.
    uploaded_by = Column(String(32)) #: user name of person who submitted the submission to the database.
    comment = Column(JSON) #: user notes
    submission_category = Column(String(64)) #: ["Research", "Diagnostic", "Surveillance"], else defaults to submission_type_name

    submission_sample_associations = relationship(
        "SubmissionSampleAssociation",
        back_populates="submission",
        cascade="all, delete-orphan",
    )
    # association proxy of "user_keyword_associations" collection
    # to "keyword" attribute
    samples = association_proxy("submission_sample_associations", "sample")

    # Allows for subclassing into ex. BacterialCulture, Wastewater, etc.
    __mapper_args__ = {
        "polymorphic_identity": "Basic Submission",
        "polymorphic_on": submission_type_name,
        "with_polymorphic": "*",
    }

    def __repr__(self):
        return f"{self.submission_type}Submission({self.rsl_plate_num})"

    def to_string(self) -> str:
        """
        string presenting basic submission

        Returns:
            str: string representing rsl plate number and submitter plate number
        """        
        return f"{self.rsl_plate_num} - {self.submitter_plate_num}"

    def to_dict(self, full_data:bool=False) -> dict:
        """
        Constructs dictionary used in submissions summary

        Args:
            full_data (bool, optional): indicates if sample dicts to be constructed. Defaults to False.

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
            logger.debug(f"Json error in {self.rsl_plate_num}: {e}")
        # Updated 2023-09 to use the extraction kit to pull reagents.
        if full_data:
            try:
                reagents = [item.to_sub_dict(extraction_kit=self.extraction_kit) for item in self.reagents]
            except Exception as e:
                logger.error(f"We got an error retrieving reagents: {e}")
                reagents = None
            samples = [item.sample.to_sub_dict(submission_rsl=self.rsl_plate_num) for item in self.submission_sample_associations]
        else:
            reagents = None
            samples = None
        try:
            comments = self.comment
        except:
            logger.error(self.comment)
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
            "ext_info": ext_info,
            "comments": comments
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
        logger.debug(f"Came up with association: {assoc}")
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
        logger.debug(f"Here's the samples: {self.samples}")
        columns = set([assoc.column for assoc in self.submission_sample_associations])
        logger.debug(f"Here are the columns for {self.rsl_plate_num}: {columns}")
        return len(columns)
    
    def hitpick_plate(self, plate_number:int|None=None) -> list:
        """
        Returns positve sample locations for plate

        Args:
            plate_number (int | None, optional): Plate id. Defaults to None.

        Returns:
            list: list of htipick dictionaries for each sample
        """        
        output_list = []
        for assoc in self.submission_sample_associations:
            samp = assoc.sample.to_hitpick(submission_rsl=self.rsl_plate_num)
            if samp != None:
                if plate_number != None:
                    samp['plate_number'] = plate_number
                samp['row'] = assoc.row
                samp['column'] = assoc.column
                samp['plate_name'] = self.rsl_plate_num
                output_list.append(samp)
            else:
                continue
        return output_list
    
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
        logger.debug(f"Calling {cls.__name__} info parser.")
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
        # logger.debug(f"Called {cls.__name__} sample parser")
        return input_dict
    
    @classmethod
    def finalize_parse(cls, input_dict:dict, xl:pd.ExcelFile|None=None, info_map:dict|None=None, plate_map:dict|None=None) -> dict:
        return input_dict

    @classmethod
    def custom_autofill(cls, input_excel:Workbook) -> Workbook:
        """
        Adds custom autofill methods for submission

        Args:
            input_excel (Workbook): input workbook

        Returns:
            Workbook: updated workbook
        """        
        return input_excel
    
    @classmethod
    def enforce_name(cls, instr:str, data:dict|None=None) -> str:
        logger.debug(f"Hello from {cls.__mapper_args__['polymorphic_identity']} Enforcer!")
        logger.debug(f"Attempting enforcement on {instr} using data: {pformat(data)}")
        # sys.exit()
        return instr

    @classmethod
    def construct_regex(cls):
        rstring =  rf'{"|".join([item.get_regex() for item in cls.__subclasses__()])}'
        regex = re.compile(rstring, flags = re.IGNORECASE | re.VERBOSE)
        return regex
 
    @classmethod
    def find_subclasses(cls, attrs:dict|None=None, submission_type:str|SubmissionType|None=None):
        match submission_type:
            case str():
                return cls.find_polymorphic_subclass(submission_type)
            case SubmissionType():
                return cls.find_polymorphic_subclass(submission_type.name)
            case _:
                pass
        if len(attrs) == 0 or attrs == None:
            return cls
        if any([not hasattr(cls, attr) for attr in attrs]):
            # looks for first model that has all included kwargs
            try:
                model = [subclass for subclass in cls.__subclasses__() if all([hasattr(subclass, attr) for attr in attrs])][0]
            except IndexError as e:
                raise AttributeError(f"Couldn't find existing class/subclass of {cls} with all attributes:\n{pformat(attrs)}")
        else:
            model = cls
        logger.debug(f"Using model: {model}")
        return model
    
    @classmethod
    def find_polymorphic_subclass(cls, polymorphic_identity:str|None=None):   
        if isinstance(polymorphic_identity, dict):
            polymorphic_identity = polymorphic_identity['value']
        if polymorphic_identity != None:
            try:
                cls = [item for item in cls.__subclasses__() if item.__mapper_args__['polymorphic_identity']==polymorphic_identity][0]
                logger.info(f"Recruiting: {cls}")
            except Exception as e:
                logger.error(f"Could not get polymorph {polymorphic_identity} of {cls} due to {e}")
        return cls

    @classmethod
    def parse_pcr(cls, xl:pd.DataFrame, rsl_number:str) -> list:
        logger.debug(f"Hello from {cls.__mapper_args__['polymorphic_identity']} PCR parser!")
        return []

    def save(self, original:bool=True):
        if original:
            self.uploaded_by = getuser()
        self.metadata.session.add(self)
        self.metadata.session.commit()
        return None
    
    def update(self):
        pass
    
    def delete(self):
        backup = self.to_dict()
        try:
            with open(self.metadata.backup_path.joinpath(f"{self.rsl_plate_num}-backup({date.today().strftime('%Y%m%d')}).yml"), "w") as f:
                yaml.dump(backup, f)
        except KeyError:
            pass
        self.metadata.session.delete(self)
        try:
            self.metadata.session.commit()
        except (SQLIntegrityError, SQLOperationalError, AlcIntegrityError, AlcOperationalError) as e:
            self.metadata.session.rollback()
            raise e

    @classmethod
    @setup_lookup
    def query(cls, 
                submission_type:str|SubmissionType|None=None,
                id:int|str|None=None,
                rsl_number:str|None=None,
                start_date:date|str|int|None=None,
                end_date:date|str|int|None=None,
                reagent:Reagent|str|None=None,
                chronologic:bool=False, limit:int=0, 
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
        logger.debug(f"kwargs coming into query: {kwargs}")
        # NOTE: if you go back to using 'model' change the appropriate cls to model in the query filters
        if submission_type == None:
            model = cls.find_subclasses(attrs=kwargs)
        else:
            if isinstance(submission_type, SubmissionType):
                model = cls.find_subclasses(submission_type=submission_type.name)
            else:
                model = cls.find_subclasses(submission_type=submission_type)
        query: Query = cls.metadata.session.query(model)
        if start_date != None and end_date == None:
            logger.warning(f"Start date with no end date, using today.")
            end_date = date.today()
        if end_date != None and start_date == None:
            logger.warning(f"End date with no start date, using Jan 1, 2023")
            start_date = date(2023, 1, 1)
        if start_date != None:
            match start_date:
                case date():
                    start_date = start_date.strftime("%Y-%m-%d")
                case int():
                    start_date = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + start_date - 2).date().strftime("%Y-%m-%d")
                case _:
                    start_date = parse(start_date).strftime("%Y-%m-%d")
            match end_date:
                case date():
                    end_date = end_date.strftime("%Y-%m-%d")
                case int():
                    end_date = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + end_date - 2).date().strftime("%Y-%m-%d")
                case _:
                    end_date = parse(end_date).strftime("%Y-%m-%d")
            logger.debug(f"Looking up BasicSubmissions from start date: {start_date} and end date: {end_date}")
            query = query.filter(cls.submitted_date.between(start_date, end_date))
        # by reagent (for some reason)
        match reagent:
            case str():
                logger.debug(f"Looking up BasicSubmission with reagent: {reagent}")
                # reagent = Reagent.query(lot_number=reagent)
                # query = query.join(reagents_submissions).filter(reagents_submissions.c.reagent_id==reagent.id)
                query = query.join(cls.reagents).filter(Reagent.lot==reagent)
            case Reagent():
                logger.debug(f"Looking up BasicSubmission with reagent: {reagent}")
                query = query.join(reagents_submissions).filter(reagents_submissions.c.reagent_id==reagent.id)
            case _:
                pass
        # by rsl number (returns only a single value)
        match rsl_number:
            case str():
                query = query.filter(cls.rsl_plate_num==rsl_number)
                logger.debug(f"At this point the query gets: {query.all()}")
                limit = 1
            case _:
                pass
        # by id (returns only a single value)
        match id:
            case int():
                logger.debug(f"Looking up BasicSubmission with id: {id}")
                query = query.filter(cls.id==id)
                limit = 1
            case str():
                logger.debug(f"Looking up BasicSubmission with id: {id}")
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
        return query_return(query=query, limit=limit)

    @classmethod
    def query_or_create(cls, submission_type:str|SubmissionType|None=None, **kwargs) -> BasicSubmission:
        """
        Returns object from db if exists, else, creates new. Due to need for user input, doesn't see much use ATM.

        Args:
            submission_type (str | SubmissionType | None, optional): Submission type to be created. Defaults to None.

        Raises:
            ValueError: _description_
            ValueError: _description_

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
        logger.debug(f"Retrieved instance: {instance}")
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

    @classmethod
    def filename_template(cls):
        return "{{ rsl_plate_num }}"

    def set_attribute(self, key, value):
        match key:
            case "extraction_kit":
                logger.debug(f"Looking up kit {value}")
                # field_value = lookup_kit_types(ctx=self.ctx, name=value)
                field_value = KitType.query(name=value)
                logger.debug(f"Got {field_value} for kit {value}")
            case "submitting_lab":
                logger.debug(f"Looking up organization: {value}")
                # field_value = lookup_organizations(ctx=self.ctx, name=value)
                field_value = Organization.query(name=value)
                logger.debug(f"Got {field_value} for organization {value}")
            case "submitter_plate_num":
                logger.debug(f"Submitter plate id: {value}")
                field_value = value
            case "samples":
                # instance = construct_samples(ctx=ctx, instance=instance, samples=value)
                for sample in value:
                    # logger.debug(f"Parsing {sample} to sql.")
                    sample, _ = sample.toSQL(submission=self)
                    # instance.samples.append(sample)
                return
            case "reagents":
                field_value = [reagent['value'].toSQL()[0] if isinstance(reagent, dict) else reagent.toSQL()[0] for reagent in value]
            case "submission_type":
                # field_value = lookup_submission_type(ctx=self.ctx, name=value)
                field_value = SubmissionType.query(name=value)
            case "sample_count":
                if value == None:
                    field_value = len(self.samples)
                else:
                    field_value = value
            case "ctx" | "csv" | "filepath":
                return
            case _:
                field_value = value
        # insert into field
        try:
            setattr(self, key, field_value)
        except AttributeError:
            logger.error(f"Could not set {self} attribute {key} to {value}")

    def update_subsampassoc(self, sample:BasicSample, input_dict:dict):
        assoc = SubmissionSampleAssociation.query(submission=self, sample=sample, limit=1)
        for k,v in input_dict.items():
            try:
                setattr(assoc, k, v)
            except AttributeError:
                logger.error(f"Can't set {k} to {v}")
        # result = store_object(ctx=ctx, object=assoc)
        result = assoc.save()
        return result

# Below are the custom submission types

class BacterialCulture(BasicSubmission):
    """
    derivative submission type from BasicSubmission
    """    
    # id = Column(INTEGER, ForeignKey('basicsubmission.id'), primary_key=True)
    controls = relationship("Control", back_populates="submission", uselist=True) #: A control sample added to submission
    __mapper_args__ = {"polymorphic_identity": "Bacterial Culture", "polymorphic_load": "inline"}

    def to_dict(self, full_data:bool=False) -> dict:
        """
        Extends parent class method to add controls to dict

        Returns:
            dict: dictionary used in submissions summary
        """        
        output = super().to_dict(full_data=full_data)
        if full_data:
            output['controls'] = [item.to_sub_dict() for item in self.controls]
        return output
    
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
    def custom_autofill(cls, input_excel: Workbook) -> Workbook:
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
        outstr = super().enforce_name(instr=instr, data=data)
        def construct(data:dict|None=None) -> str:
            """
            Create default plate name.

            Returns:
                str: new RSL number
            """        
            logger.debug(f"Attempting to construct RSL number from scratch...")
            # directory = Path(self.ctx['directory_path']).joinpath("Bacteria")
            # directory = Path(ctx.directory_path).joinpath("Bacteria")
            directory = cls.metadata.directory_path.joinpath("Bacteria")
            year = str(datetime.now().year)[-2:]
            if directory.exists():
                logger.debug(f"Year: {year}")
                relevant_rsls = []
                all_xlsx = [item.stem for item in directory.rglob("*.xlsx") if bool(re.search(r"RSL-\d{2}-\d{4}", item.stem)) and year in item.stem[4:6]]
                logger.debug(f"All rsls: {all_xlsx}")
                for item in all_xlsx:
                    try:
                        relevant_rsls.append(re.match(r"RSL-\d{2}-\d{4}", item).group(0))
                    except Exception as e:
                        logger.error(f"Regex error: {e}")
                        continue
                logger.debug(f"Initial xlsx: {relevant_rsls}")
                max_number = max([int(item[-4:]) for item in relevant_rsls])
                logger.debug(f"The largest sample number is: {max_number}")
                return f"RSL-{year}-{str(max_number+1).zfill(4)}"
            else:
                # raise FileNotFoundError(f"Unable to locate the directory: {directory.__str__()}")
                return f"RSL-{year}-0000"
        try:
            outstr = re.sub(r"RSL(\d{2})", r"RSL-\1", outstr, flags=re.IGNORECASE)
        except (AttributeError, TypeError) as e:
            outstr = construct()
            # year = datetime.now().year
            # self.parsed_name = f"RSL-{str(year)[-2:]}-0000"
        return re.sub(r"RSL-(\d{2})(\d{4})", r"RSL-\1-\2", outstr, flags=re.IGNORECASE)

    @classmethod
    def get_regex(cls):
        return "(?P<Bacterial_Culture>RSL-?\\d{2}-?\\d{4})"
    
    @classmethod
    def filename_template(cls):
        template = super().filename_template()
        template += "_{{ submitting_lab }}_{{ submitter_plate_num }}"
        return template
    
class Wastewater(BasicSubmission):
    """
    derivative submission type from BasicSubmission
    """    
    # id = Column(INTEGER, ForeignKey('basicsubmission.id'), primary_key=True)
    ext_technician = Column(String(64))
    pcr_technician = Column(String(64))
    __mapper_args__ = {"polymorphic_identity": "Wastewater", "polymorphic_load": "inline"}

    def to_dict(self, full_data:bool=False) -> dict:
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
        outstr = super().enforce_name(instr=instr, data=data)
        def construct(data:dict|None=None):
            if "submitted_date" in data.keys():
                if data['submitted_date']['value'] != None:
                    today = data['submitted_date']['value']
                else:
                    today = datetime.now()
            else:
                today = re.search(r"\d{4}(_|-)?\d{2}(_|-)?\d{2}", instr)
                try:
                    today = parse(today.group())
                except AttributeError:
                    today = datetime.now()
            return f"RSL-WW-{today.year}{str(today.month).zfill(2)}{str(today.day).zfill(2)}"
        if outstr == None:
            outstr = construct(data)
        try:
            outstr = re.sub(r"PCR(-|_)", "", outstr)
        except AttributeError as e:
            logger.error(f"Problem using regex: {e}")
            outstr = construct(data)
        outstr = outstr.replace("RSLWW", "RSL-WW")
        outstr = re.sub(r"WW(\d{4})", r"WW-\1", outstr, flags=re.IGNORECASE)
        outstr = re.sub(r"(\d{4})-(\d{2})-(\d{2})", r"\1\2\3", outstr)
        logger.debug(f"Coming out of the preliminary parsing, the plate name is {outstr}")
        try:
            plate_number = re.search(r"(?:(-|_)\d)(?!\d)", outstr).group().strip("_").strip("-")
            logger.debug(f"Plate number is: {plate_number}")
        except AttributeError as e:
            plate_number = "1"
        # self.parsed_name = re.sub(r"(\d{8})(-|_\d)?(R\d)?", fr"\1-{plate_number}\3", self.parsed_name)
        outstr = re.sub(r"(\d{8})(-|_)?\d?(R\d?)?", rf"\1-{plate_number}\3", outstr)
        logger.debug(f"After addition of plate number the plate name is: {outstr}")
        try:
            repeat = re.search(r"-\dR(?P<repeat>\d)?", outstr).groupdict()['repeat']
            if repeat == None:
                repeat = "1"
        except AttributeError as e:
            repeat = ""
        return re.sub(r"(-\dR)\d?", rf"\1 {repeat}", outstr).replace(" ", "")

    @classmethod
    def get_regex(cls):
        # return "(?P<Wastewater>RSL(?:-|_)?WW(?:-|_)?20\d{2}-?\d{2}-?\d{2}(?:(_|-)\d?(\D|$)R?\d?)?)"
        # return "(?P<Wastewater>RSL(?:-|_)?WW(?:-|_)?20\d{2}-?\d{2}-?\d{2}(?:(_|-)\d?([^_|\D]|$)R?\d?)?)"
        return "(?P<Wastewater>RSL(?:-|_)?WW(?:-|_)?20\d{2}-?\d{2}-?\d{2}(?:(_|-)?\d?([^_0123456789]|$)R?\d?)?)"
  
class WastewaterArtic(BasicSubmission):
    """
    derivative submission type for artic wastewater
    """    
    # id = Column(INTEGER, ForeignKey('basicsubmission.id'), primary_key=True)
    __mapper_args__ = {"polymorphic_identity": "Wastewater Artic", "polymorphic_load": "inline"}
    artic_technician = Column(String(64))

    def calculate_base_cost(self):
        """
        This method overrides parent method due to multiple output plates from a single submission
        """        
        logger.debug(f"Hello from calculate base cost in WWArtic")
        try:
            cols_count_96 = ceil(int(self.sample_count) / 8)
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
        return input_dict
    
    @classmethod
    def enforce_name(cls, instr:str, data:dict|None=None) -> str:
        outstr = super().enforce_name(instr=instr, data=data)
        def construct(data:dict|None=None):
            today = datetime.now()
            return f"RSL-AR-{today.year}{str(today.month).zfill(2)}{str(today.day).zfill(2)}"
        try:
            outstr = re.sub(r"(\d{4})-(\d{2})-(\d{2})", r"RSL-AR-\1\2\3", outstr, flags=re.IGNORECASE)
        except AttributeError:
            outstr = construct()
        try:
            plate_number = int(re.search(r"_|-\d?_", outstr).group().strip("_").strip("-"))
        except (AttributeError, ValueError) as e:
            plate_number = 1
        return re.sub(r"(_|-\d)?_ARTIC", f"-{plate_number}", outstr)

    @classmethod
    def get_regex(cls):
        return "(?P<Wastewater_Artic>(\\d{4}-\\d{2}-\\d{2}(?:-|_)(?:\\d_)?artic)|(RSL(?:-|_)?AR(?:-|_)?20\\d{2}-?\\d{2}-?\\d{2}(?:(_|-)\\d?(\\D|$)R?\\d?)?))"

    @classmethod
    def finalize_parse(cls, input_dict: dict, xl: pd.ExcelFile | None = None, info_map: dict | None = None, plate_map: dict | None = None) -> dict:
        input_dict = super().finalize_parse(input_dict, xl, info_map, plate_map)
        logger.debug(pformat(input_dict))
        logger.debug(pformat(info_map))
        logger.debug(pformat(plate_map))
        samples = []
        for sample in input_dict['samples']:
            if sample.submitter_id == "NTC1":
                samples.append(dict(sample=sample.submitter_id, destination_row=8, destination_column=2, source_row=0, source_column=0, plate_number='control', plate=None))
                continue
            elif sample.submitter_id == "NTC2":
                samples.append(dict(sample=sample.submitter_id, destination_row=8, destination_column=5, source_row=0, source_column=0, plate_number='control', plate=None))
                continue
            destination_row = sample.row[0]
            destination_column = sample.column[0]
            logger.debug(f"Looking up: {sample.submitter_id} friend.")
            lookup_sample = BasicSample.query(submitter_id=sample.submitter_id)
            lookup_ssa = SubmissionSampleAssociation.query(sample=lookup_sample, exclude_submission_type=cls.__mapper_args__['polymorphic_identity'] , chronologic=True, reverse=True, limit=1)
            try:
                plate = lookup_ssa.submission.rsl_plate_num
                source_row = lookup_ssa.row
                source_column = lookup_ssa.column
            except AttributeError:
                # plate = "Error"
                # source_row = 0
                # source_column = 0
                continue
            samples.append(dict(
                sample=sample.submitter_id,
                destination_column=destination_column, 
                destination_row=destination_row,
                plate=plate,
                source_column=source_column,
                source_row = source_row
                ))
        plates = sorted(list(set([sample['plate'] for sample in samples if sample['plate'] != None])))
        for iii, plate in enumerate(plates):
            for sample in samples:
                if sample['plate'] == plate:
                    sample['plate_number'] = iii + 1
        df = pd.DataFrame.from_records(samples).fillna(value="")
        df.source_row = df.source_row.astype(int)
        df.source_column = df.source_column.astype(int)
        df.sort_values(by=['plate_number', 'source_column', 'source_row'], inplace=True)
        input_dict['csv'] = df
        return input_dict
        
# Sample Classes

class BasicSample(Base):
    """
    Base of basic sample which polymorphs into BCSample and WWSample
    """    

    # @declared_attr
    # def __tablename__(cls):
    #     return cls.__name__.lower()
    __tablename__ = "_samples"
    __table_args__ = {'extend_existing': True} 

    id = Column(INTEGER, primary_key=True) #: primary key
    submitter_id = Column(String(64), nullable=False, unique=True) #: identification from submitter
    sample_type = Column(String(32))

    sample_submission_associations = relationship(
        "SubmissionSampleAssociation",
        back_populates="sample",
        cascade="all, delete-orphan",
    )

    __mapper_args__ = {
        "polymorphic_identity": "Basic Sample",
        # "polymorphic_on": sample_type,
        "polymorphic_on": case(
            [
                (sample_type == "Wastewater Sample", "Wastewater Sample"),
                (sample_type == "Wastewater Artic Sample", "Wastewater Sample"),
                (sample_type == "Bacterial Culture Sample", "Bacterial Culture Sample"),
            ],
            else_="Basic Sample"
         ),
        "with_polymorphic": "*",
    }

    submissions = association_proxy("sample_submission_associations", "submission")

    @validates('submitter_id')
    def create_id(self, key, value):
        # logger.debug(f"validating sample_id of: {value}")
        if value == None:
            return uuid.uuid4().hex.upper()
        else:
            return value
        
    def __repr__(self) -> str:
        return f"<{self.sample_type.replace('_', ' ').title().replace(' ', '')}({self.submitter_id})>"
    
    def set_attribute(self, name, value):
        # logger.debug(f"Setting {name} to {value}")
        try:
            setattr(self, name, value)
        except AttributeError:
            logger.error(f"Attribute {name} not found")
    
    def to_sub_dict(self, submission_rsl:str) -> dict:
        """
        Returns a dictionary of locations.

        Args:
            submission_rsl (str): Submission RSL number.

        Returns:
            dict: 'well' and sample submitter_id as 'name'
        """        
        
        assoc = [item for item in self.sample_submission_associations if item.submission.rsl_plate_num==submission_rsl][0]
        sample = {}
        try:
            sample['well'] = f"{row_map[assoc.row]}{assoc.column}"
        except KeyError as e:
            logger.error(f"Unable to find row {assoc.row} in row_map.")
            sample['well'] = None
        sample['name'] = self.submitter_id
        return sample
    
    def to_hitpick(self, submission_rsl:str|None=None) -> dict|None:
        """
        Outputs a dictionary usable for html plate maps.

        Returns:
            dict: dictionary of sample id, row and column in elution plate
        """        
        # Since there is no PCR, negliable result is necessary.
        assoc = [item for item in self.sample_submission_associations if item.submission.rsl_plate_num==submission_rsl][0]
        tooltip_text =  f"""
                            Sample name: {self.submitter_id}<br>
                            Well: {row_map[assoc.row]}{assoc.column}
                        """
        return dict(name=self.submitter_id[:10], positive=False, tooltip=tooltip_text)

    @classmethod
    def find_subclasses(cls, attrs:dict|None=None, sample_type:str|None=None):
        if sample_type != None:
            return cls.find_polymorphic_subclass(polymorphic_identity=sample_type)
        if len(attrs) == 0 or attrs == None:
            logger.debug(f"No attr, returning {cls}")
            return cls
        if any([not hasattr(cls, attr) for attr in attrs]):
            logger.debug(f"{cls} is missing attrs. searching for better match.")
            # looks for first model that has all included kwargs
            try:
                model = [subclass for subclass in cls.__subclasses__() if all([hasattr(subclass, attr) for attr in attrs])][0]
            except IndexError as e:
                raise AttributeError(f"Couldn't find existing class/subclass of {cls} with all attributes:\n{pformat(attrs)}")
        else:
            logger.debug(f"{cls} has all necessary attributes, returning")
            return cls
        logger.debug(f"Using model: {model}")
        return model
    
    @classmethod
    def find_polymorphic_subclass(cls, polymorphic_identity:str|None=None):   
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
        # logger.debug(f"Called {cls.__name__} sample parser")
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
            ctx (Settings): Settings object passed down from gui
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
        query: Query = cls.metadata.session.query(model)
        match submitter_id:
            case str():
                logger.debug(f"Looking up {model} with submitter id: {submitter_id}")
                query = query.filter(model.submitter_id==submitter_id)
                limit = 1
            case _:
                pass
        # match sample_type:
        #     case str():
        #         logger.debug(f"Looking up {model} with sample type: {sample_type}")
        #         query = query.filter(models.BasicSample.sample_type==sample_type)
        #     case _:
        #         pass
        for k, v in kwargs.items():
            attr = getattr(model, k)
            logger.debug(f"Got attr: {attr}")
            query = query.filter(attr==v)
        if len(kwargs) > 0:
            limit = 1
        return query_return(query=query, limit=limit)
    
    @classmethod
    def query_or_create(cls, sample_type:str, **kwargs):
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
        return instance

#Below are the custom sample types

class WastewaterSample(BasicSample):
    """
    Derivative wastewater sample
    """
    # id = Column(INTEGER, ForeignKey('basicsample.id'), primary_key=True)
    ww_processing_num = Column(String(64)) #: wastewater processing number 
    ww_full_sample_id = Column(String(64))
    rsl_number = Column(String(64)) #: rsl plate identification number
    collection_date = Column(TIMESTAMP) #: Date sample collected
    received_date = Column(TIMESTAMP) #: Date sample received
    notes = Column(String(2000))
    sample_location = Column(String(8)) #: location on 24 well plate
    __mapper_args__ = {"polymorphic_identity": "Wastewater Sample", "polymorphic_load": "inline"}

    def to_hitpick(self, submission_rsl:str) -> dict|None:
        """
        Outputs a dictionary usable for html plate maps. Extends parent method.

        Returns:
            dict: dictionary of sample id, row and column in elution plate
        """       
        sample = super().to_hitpick(submission_rsl=submission_rsl)
        assoc = [item for item in self.sample_submission_associations if item.submission.rsl_plate_num==submission_rsl][0]
        # if either n1 or n2 is positive, include this sample
        try:
            sample['positive'] = any(["positive" in item for item in [assoc.n1_status, assoc.n2_status]])
        except (TypeError, AttributeError) as e:
            logger.error(f"Couldn't check positives for {self.rsl_number}. Looks like there isn't PCR data.")
        try:
            sample['tooltip'] += f"<br>- ct N1: {'{:.2f}'.format(assoc.ct_n1)} ({assoc.n1_status})<br>- ct N2: {'{:.2f}'.format(assoc.ct_n2)} ({assoc.n2_status})"
        except (TypeError, AttributeError) as e:
            logger.error(f"Couldn't set tooltip for {self.rsl_number}. Looks like there isn't PCR data.")
        return sample
    
    def get_recent_ww_submission(self):
        results = [sub for sub in self.submissions if isinstance(sub, Wastewater)]
        if len(results) > 1:
            results = results.sort(key=lambda sub: sub.submitted_date)
        try:
            return results[0]
        except IndexError:
            return None
            
    @classmethod
    def parse_sample(cls, input_dict: dict) -> dict:
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

class BacterialCultureSample(BasicSample):
    """
    base of bacterial culture sample
    """
    # id = Column(INTEGER, ForeignKey('basicsample.id'), primary_key=True)
    organism = Column(String(64)) #: bacterial specimen
    concentration = Column(String(16)) #: sample concentration
    __mapper_args__ = {"polymorphic_identity": "Bacterial Culture Sample", "polymorphic_load": "inline"}

    def to_sub_dict(self, submission_rsl:str) -> dict:
        """
        gui friendly dictionary, extends parent method.

        Returns:
            dict: well location and name (sample id, organism) NOTE: keys must sync with WWSample to_sub_dict above
        """
        sample = super().to_sub_dict(submission_rsl=submission_rsl)
        sample['name'] = f"{self.submitter_id} - ({self.organism})"
        return sample

# Submission to Sample Associations

class SubmissionSampleAssociation(Base):
    """
    table containing submission/sample associations
    DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
    """    

    # @declared_attr
    # def __tablename__(cls):
    #     return cls.__name__.lower()
    __tablename__ = "_submission_sample"
    __table_args__ = {'extend_existing': True} 

    sample_id = Column(INTEGER, ForeignKey("_samples.id"), nullable=False)
    submission_id = Column(INTEGER, ForeignKey("_submissions.id"), primary_key=True)
    row = Column(INTEGER, primary_key=True) #: row on the 96 well plate
    column = Column(INTEGER, primary_key=True) #: column on the 96 well plate

    # reference to the Submission object
    submission = relationship(BasicSubmission, back_populates="submission_sample_associations")

    # reference to the Sample object
    sample = relationship(BasicSample, back_populates="sample_submission_associations")

    base_sub_type = Column(String)
    
    # Refers to the type of parent.
    # Hooooooo boy, polymorphic association type, now we're getting into the weeds!
    __mapper_args__ = {
        "polymorphic_identity": "Basic Association",
        "polymorphic_on": base_sub_type,
        "with_polymorphic": "*",
    }

    def __init__(self, submission:BasicSubmission=None, sample:BasicSample=None, row:int=1, column:int=1):
        self.submission = submission
        self.sample = sample
        self.row = row
        self.column = column

    def __repr__(self) -> str:
        return f"<SubmissionSampleAssociation({self.submission.rsl_plate_num} & {self.sample.submitter_id})"
    
    @classmethod
    def find_polymorphic_subclass(cls, polymorphic_identity:str|None=None):   
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
        query: Query = cls.metadata.session.query(cls)
        match submission:
            case BasicSubmission():
                query = query.filter(cls.submission==submission)
            case str():
                query = query.join(BasicSubmission).filter(BasicSubmission.rsl_plate_num==submission)
            case _:
                pass
        match sample:
            case BasicSample():
                query = query.filter(cls.sample==sample)
            case str():
                query = query.join(BasicSample).filter(BasicSample.submitter_id==sample)
            case _:
                pass
        if row > 0:
            query = query.filter(cls.row==row)
        if column > 0:
            query = query.filter(cls.column==column)
        match exclude_submission_type:
            case str():
                query = query.join(BasicSubmission).filter(BasicSubmission.submission_type_name != exclude_submission_type)
            case _:
                pass
        # logger.debug(f"Query count: {query.count()}")
        if reverse and not chronologic:
            query = query.order_by(BasicSubmission.id.desc())
            # query = query.join(BasicSubmission).order_by(BasicSubmission.id.desc())
            # query.join(BasicSubmission).order_by(cls.submission.id.desc())
        if chronologic:
            if reverse:
                query = query.order_by(BasicSubmission.submitted_date.desc())
                # query = query.join(BasicSubmission).order_by(BasicSubmission.submitted_date.desc())
                # query.join(BasicSubmission).order_by(cls.submission.submitted_date.desc())
            else:
                query = query.order_by(BasicSubmission.submitted_date)
                # query.join(BasicSubmission).order_by(cls.submission.submitted_date)
        # if query.count() == 1:
        #     limit = 1
        return query_return(query=query, limit=limit)
    
    @classmethod
    def query_or_create(cls,
                association_type:str="Basic Association", 
                submission:BasicSubmission|str|None=None,
                sample:BasicSample|str|None=None,
                **kwargs):
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
            instance = used_cls(submission=submission, sample=sample, **kwargs)
        return instance

    def save(self):
        self.metadata.session.add(self)
        self.metadata.session.commit()
        return None

class WastewaterAssociation(SubmissionSampleAssociation):
    """
    Derivative custom Wastewater/Submission Association... fancy.
    """    
    # submission_id = Column(INTEGER, ForeignKey("submissionsampleassociation.submission_id"), primary_key=True)
    # row = Column(INTEGER, ForeignKey("submissionsampleassociation.row"), nullable=False)
    # column = Column(INTEGER, ForeignKey("submissionsampleassociation.column"), primary_key=True)
    ct_n1 = Column(FLOAT(2)) #: AKA ct for N1
    ct_n2 = Column(FLOAT(2)) #: AKA ct for N2
    n1_status = Column(String(32)) #: positive or negative for N1
    n2_status = Column(String(32)) #: positive or negative for N2
    pcr_results = Column(JSON) #: imported PCR status from QuantStudio

    __mapper_args__ = {"polymorphic_identity": "Wastewater Association", "polymorphic_load": "inline"}

