'''
Models for the main submission types.
'''
import math
from . import Base
from sqlalchemy import Column, String, TIMESTAMP, INTEGER, ForeignKey, Table, JSON, FLOAT, case
from sqlalchemy.orm import relationship, validates
import logging
import json
from json.decoder import JSONDecodeError
from math import ceil
from sqlalchemy.ext.associationproxy import association_proxy
import uuid
from pandas import Timestamp
from dateutil.parser import parse
import re
import pandas as pd
from tools import row_map

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
        "polymorphic_identity": "basic_submission",
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
        "polymorphic_identity": "basic_sample",
        # "polymorphic_on": sample_type,
        "polymorphic_on": case(
            [
                (sample_type == "Wastewater Sample", "Wastewater Sample"),
                (sample_type == "Wastewater Artic Sample", "Wastewater Sample"),
                (sample_type == "Bacterial Culture Sample", "Bacterial Culture Sample"),
            ],
            else_="basic_sample"
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
        return dict(name=self.submitter_id, positive=False, tooltip=tooltip_text)

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

        
    @validates("collected-date")
    def convert_cdate_time(self, key, value):
        logger.debug(f"Validating {key}: {value}")
        if isinstance(value, Timestamp):
            return value.date()
        if isinstance(value, str):
            return parse(value)
        return value
    
    @validates("rsl_number")
    def use_submitter_id(self, key, value):
        logger.debug(f"Validating {key}: {value}")
        return value or self.submitter_id

    def set_attribute(self, name:str, value):
        """
        Set an attribute of this object. Extends parent.

        Args:
            name (str): name of the attribute
            value (_type_): value to be set
        """        
        # Due to the plate map being populated with RSL numbers, we have to do some shuffling. 
        match name:
            case "submitter_id":
                # If submitter_id already has a value, stop
                if self.submitter_id != None:
                    return
                # otherwise also set rsl_number to the same value
                else:
                    super().set_attribute("rsl_number", value)
            case "ww_full_sample_id":
                # If value present, set ww_full_sample_id and make this the submitter_id
                if value != None:
                    super().set_attribute(name, value)
                    name = "submitter_id"
            case 'collection_date':
                # If this is a string use dateutils to parse into date()
                if isinstance(value, str):
                    logger.debug(f"collection_date {value} is a string. Attempting parse...")
                    value = parse(value)
            case "rsl_number":
                if value == None:
                    value = self.submitter_id
        super().set_attribute(name, value)

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
        "polymorphic_identity": "basic_association",
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

class WastewaterAssociation(SubmissionSampleAssociation):
    """
    Derivative custom Wastewater/Submission Association... fancy.
    """    
    ct_n1 = Column(FLOAT(2)) #: AKA ct for N1
    ct_n2 = Column(FLOAT(2)) #: AKA ct for N2
    n1_status = Column(String(32)) #: positive or negative for N1
    n2_status = Column(String(32)) #: positive or negative for N2
    pcr_results = Column(JSON) #: imported PCR status from QuantStudio

    __mapper_args__ = {"polymorphic_identity": "wastewater", "polymorphic_load": "inline"}

