'''
Models for the main submission types.
'''
from getpass import getuser
import math
from pprint import pformat
from . import Base
from sqlalchemy import Column, String, TIMESTAMP, INTEGER, ForeignKey, Table, JSON, FLOAT, case
from sqlalchemy.orm import relationship, validates
import logging
import json
from json.decoder import JSONDecodeError
from math import ceil
from sqlalchemy.ext.associationproxy import association_proxy
import uuid
from dateutil.parser import parse
import re
import pandas as pd
from openpyxl import Workbook
from tools import check_not_nan, row_map, Settings
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(f"submissions.{__name__}")

# table containing reagents/submission relationships
reagents_submissions = Table("_reagents_submissions", Base.metadata, Column("reagent_id", INTEGER, ForeignKey("_reagents.id")), Column("submission_id", INTEGER, ForeignKey("_submissions.id")))

class BasicSubmission(Base):
    """
    Concrete of basic submission which polymorphs into BacterialCulture and Wastewater
    """
    __tablename__ = "_submissions"

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
    run_cost = Column(FLOAT(2)) #: total cost of running the plate. Set from constant and mutable kit costs at time of creation.
    uploaded_by = Column(String(32)) #: user name of person who submitted the submission to the database.
    comment = Column(JSON)
    submission_category = Column(String(64))

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
            int: largest column number
        """           
        logger.debug(f"Here's the samples: {self.samples}")
        columns = [assoc.column for assoc in self.submission_sample_associations]
        logger.debug(f"Here are the columns for {self.rsl_plate_num}: {columns}")
        return max(columns)
    
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
            xl (pd.ExcelFile): original xl workbook
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
        logger.debug(f"Called {cls.__name__} sample parser")
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
    def enforce_name(cls, ctx:Settings, instr:str) -> str:
        logger.debug(f"Hello from {cls.__mapper_args__['polymorphic_identity']} Enforcer!")
        logger.debug(f"Attempting enforcement on {instr}")
        return instr

    @classmethod
    def construct_regex(cls):
        rstring =  rf'{"|".join([item.get_regex() for item in cls.__subclasses__()])}'
        regex = re.compile(rstring, flags = re.IGNORECASE | re.VERBOSE)
        return regex
 
    @classmethod
    def find_subclasses(cls, ctx:Settings, attrs:dict|None=None, submission_type:str|None=None):
        if submission_type != None:
            return cls.find_polymorphic_subclass(submission_type)
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
        if polymorphic_identity == None:
            return cls
        else:
            try:
                return [item for item in cls.__subclasses__() if item.__mapper_args__['polymorphic_identity']==polymorphic_identity][0]
            except Exception as e:
                logger.error(f"Could not get polymorph {polymorphic_identity} of {cls} due to {e}")
                return cls

    @classmethod
    def parse_pcr(cls, xl:pd.DataFrame, rsl_number:str) -> list:
        logger.debug(f"Hello from {cls.__mapper_args__['polymorphic_identity']} PCR parser!")
        return []

    def save(self, ctx:Settings):
        self.uploaded_by = getuser()
        ctx.database_session.add(self)
        ctx.database_session.commit()

# Below are the custom submission types

class BacterialCulture(BasicSubmission):
    """
    derivative submission type from BasicSubmission
    """    
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
    def enforce_name(cls, ctx:Settings, instr:str) -> str:
        outstr = super().enforce_name(ctx=ctx, instr=instr)
        def construct(ctx) -> str:
            """
            DEPRECIATED due to slowness. Search for the largest rsl number and increment by 1

            Returns:
                str: new RSL number
            """        
            logger.debug(f"Attempting to construct RSL number from scratch...")
            # directory = Path(self.ctx['directory_path']).joinpath("Bacteria")
            directory = Path(ctx.directory_path).joinpath("Bacteria")
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
            outstr = construct(ctx=ctx)
            # year = datetime.now().year
            # self.parsed_name = f"RSL-{str(year)[-2:]}-0000"
        return re.sub(r"RSL-(\d{2})(\d{4})", r"RSL-\1-\2", outstr, flags=re.IGNORECASE)

    @classmethod
    def get_regex(cls):
        return "(?P<Bacterial_Culture>RSL-?\\d{2}-?\\d{4})"
    
class Wastewater(BasicSubmission):
    """
    derivative submission type from BasicSubmission
    """    
    pcr_info = Column(JSON)
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
    def enforce_name(cls, ctx:Settings, instr:str) -> str:
        outstr = super().enforce_name(ctx=ctx, instr=instr)
        def construct():
            today = datetime.now()
            return f"RSL-WW-{today.year}{str(today.month).zfill(2)}{str(today.day).zfill(2)}"
        if outstr == None:
            outstr = construct()
        try:
            outstr = re.sub(r"PCR(-|_)", "", outstr)
        except AttributeError as e:
            logger.error(f"Problem using regex: {e}")
            outstr = construct()
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
        return "(?P<Wastewater>RSL(?:-|_)?WW(?:-|_)?20\d{2}-?\d{2}-?\d{2}(?:(_|-)\d?(\D|$)R?\d?)?)"
  
class WastewaterArtic(BasicSubmission):
    """
    derivative submission type for artic wastewater
    """    
    __mapper_args__ = {"polymorphic_identity": "Wastewater Artic", "polymorphic_load": "inline"}

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
        input_dict['submitter_id'] = re.sub(r"\s\(.+\)$", "", str(input_dict['submitter_id'])).strip()
        return input_dict
    
    @classmethod
    def enforce_name(cls, ctx:Settings, instr:str) -> str:
        outstr = super().enforce_name(ctx=ctx, instr=instr)
        def construct():
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

class BasicSample(Base):
    """
    Base of basic sample which polymorphs into BCSample and WWSample
    """    

    __tablename__ = "_samples"

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
    def find_subclasses(cls, ctx:Settings, attrs:dict|None=None, rsl_number:str|None=None):
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
        logger.debug(f"Called {cls.__name__} sample parser")
        return input_dict

class WastewaterSample(BasicSample):
    """
    Derivative wastewater sample
    """
    ww_processing_num = Column(String(64)) #: wastewater processing number 
    ww_full_sample_id = Column(String(64))
    rsl_number = Column(String(64)) #: rsl plate identification number
    collection_date = Column(TIMESTAMP) #: Date sample collected
    received_date = Column(TIMESTAMP) #: Date sample received
    notes = Column(String(2000))
    sample_location = Column(String(8)) #: location on 24 well plate
    __mapper_args__ = {"polymorphic_identity": "Wastewater Sample", "polymorphic_load": "inline"}

        
    # @validates("collected-date")
    # def convert_cdate_time(self, key, value):
    #     logger.debug(f"Validating {key}: {value}")
    #     if isinstance(value, Timestamp):
    #         return value.date()
    #     if isinstance(value, str):
    #         return parse(value)
    #     return value
    
    # @validates("rsl_number")
    # def use_submitter_id(self, key, value):
    #     logger.debug(f"Validating {key}: {value}")
    #     return value or self.submitter_id

    # def set_attribute(self, name:str, value):
    #     """
    #     Set an attribute of this object. Extends parent.

    #     Args:
    #         name (str): name of the attribute
    #         value (_type_): value to be set
    #     """        
    #     # Due to the plate map being populated with RSL numbers, we have to do some shuffling. 
    #     match name:
    #         case "submitter_id":
    #             # If submitter_id already has a value, stop
    #             if self.submitter_id != None:
    #                 return
    #             # otherwise also set rsl_number to the same value
    #             else:
    #                 super().set_attribute("rsl_number", value)
    #         case "ww_full_sample_id":
    #             # If value present, set ww_full_sample_id and make this the submitter_id
    #             if value != None:
    #                 super().set_attribute(name, value)
    #                 name = "submitter_id"
    #         case 'collection_date':
    #             # If this is a string use dateutils to parse into date()
    #             if isinstance(value, str):
    #                 logger.debug(f"collection_date {value} is a string. Attempting parse...")
    #                 value = parse(value)
    #         case "rsl_number":
    #             if value == None:
    #                 value = self.submitter_id
    #     super().set_attribute(name, value)

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
        return output_dict

class BacterialCultureSample(BasicSample):
    """
    base of bacterial culture sample
    """
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

class SubmissionSampleAssociation(Base):
    """
    table containing submission/sample associations
    DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
    """    
    __tablename__ = "_submission_sample"
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

class WastewaterAssociation(SubmissionSampleAssociation):
    """
    Derivative custom Wastewater/Submission Association... fancy.
    """    
    ct_n1 = Column(FLOAT(2)) #: AKA ct for N1
    ct_n2 = Column(FLOAT(2)) #: AKA ct for N2
    n1_status = Column(String(32)) #: positive or negative for N1
    n2_status = Column(String(32)) #: positive or negative for N2
    pcr_results = Column(JSON) #: imported PCR status from QuantStudio

    __mapper_args__ = {"polymorphic_identity": "Wastewater Association", "polymorphic_load": "inline"}

