'''
Models for the main submission types.
'''
import math
from . import Base
from sqlalchemy import Column, String, TIMESTAMP, INTEGER, ForeignKey, Table, JSON, FLOAT, BOOLEAN
from sqlalchemy.orm import relationship, validates
import logging
import json
from json.decoder import JSONDecodeError
from math import ceil
from sqlalchemy.ext.associationproxy import association_proxy
import uuid
from . import Base

logger = logging.getLogger(f"submissions.{__name__}")

# table containing reagents/submission relationships
reagents_submissions = Table("_reagents_submissions", Base.metadata, Column("reagent_id", INTEGER, ForeignKey("_reagents.id")), Column("submission_id", INTEGER, ForeignKey("_submissions.id")))

class BasicSubmission(Base):
    """
    Base of basic submission which polymorphs into BacterialCulture and Wastewater
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
    submission_type = Column(String(32)) #: submission type (should be string in D3 of excel sheet)
    technician = Column(String(64)) #: initials of processing tech(s)
    # Move this into custom types?
    reagents = relationship("Reagent", back_populates="submissions", secondary=reagents_submissions) #: relationship to reagents
    reagents_id = Column(String, ForeignKey("_reagents.id", ondelete="SET NULL", name="fk_BS_reagents_id")) #: id of used reagents
    extraction_info = Column(JSON) #: unstructured output from the extraction table logger.
    run_cost = Column(FLOAT(2)) #: total cost of running the plate. Set from constant and mutable kit costs at time of creation.
    uploaded_by = Column(String(32)) #: user name of person who submitted the submission to the database.
    comment = Column(JSON)

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
        "polymorphic_on": submission_type,
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

    def to_dict(self) -> dict:
        """
        dictionary used in submissions summary

        Returns:
            dict: dictionary used in submissions summary
        """        
        # get lab from nested organization object
        
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
        try:
            reagents = [item.to_sub_dict() for item in self.reagents]
        except Exception as e:
            logger.error(f"We got an error retrieving reagents: {e}")
            reagents = None
        # try:
        #     samples = [item.sample.to_sub_dict(item.__dict__()) for item in self.submission_sample_associations]
        # except Exception as e:
        #     logger.error(f"Problem making list of samples: {e}")
        #     samples = None
        samples = []
        for item in self.submission_sample_associations:
            sample = item.sample.to_sub_dict(submission_rsl=self.rsl_plate_num)
            # try:
            #     sample['well'] = f"{row_map[item.row]}{item.column}"
            # except KeyError as e:
            #     logger.error(f"Unable to find row {item.row} in row_map.")
            #     sample['well'] = None
            samples.append(sample)
        try:
            comments = self.comment
        except:
            logger.error(self.comment)
            comments = None
        output = {
            "id": self.id,
            "Plate Number": self.rsl_plate_num,
            "Submission Type": self.submission_type.replace("_", " ").title(),
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
            "Submission Type": self.submission_type.replace("_", " ").title(),
            "Submitter Plate Number": self.submitter_plate_num,
            "Submitted Date": self.submitted_date.strftime("%Y-%m-%d"),
            "Submitting Lab": sub_lab,
            "Sample Count": self.sample_count,
            "Extraction Kit": ext_kit,
            "Cost": self.run_cost
        }
        return output
    
    def calculate_base_cost(self):
        try:
            # cols_count_96 = ceil(int(self.sample_count) / 8)
            cols_count_96 = self.calculate_column_count()
        except Exception as e:
            logger.error(f"Column count error: {e}")
        # cols_count_24 = ceil(int(self.sample_count) / 3)
        if all(item == 0.0 for item in [self.extraction_kit.constant_cost, self.extraction_kit.mutable_cost_column, self.extraction_kit.mutable_cost_sample]):
            try:
                self.run_cost = self.extraction_kit.cost_per_run
            except Exception as e:
                logger.error(f"Calculation error: {e}")
        else:
            try:
                self.run_cost = self.extraction_kit.constant_cost + (self.extraction_kit.mutable_cost_column * cols_count_96) + (self.extraction_kit.mutable_cost_sample * int(self.sample_count))
            except Exception as e:
                logger.error(f"Calculation error: {e}")

    def calculate_column_count(self):
        logger.debug(f"Here's the samples: {self.samples}")
        # columns = [int(sample.well_number[-2:]) for sample in self.samples]
        columns = [assoc.column for assoc in self.submission_sample_associations]
        logger.debug(f"Here are the columns for {self.rsl_plate_num}: {columns}")
        return max(columns)
    
    def hitpick_plate(self, plate_number:int|None=None) -> list:
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

# Below are the custom submission types

class BacterialCulture(BasicSubmission):
    """
    derivative submission type from BasicSubmission
    """    
    controls = relationship("Control", back_populates="submission", uselist=True) #: A control sample added to submission
    # samples = relationship("BCSample", back_populates="rsl_plate", uselist=True)
    __mapper_args__ = {"polymorphic_identity": "bacterial_culture", "polymorphic_load": "inline"}

    def to_dict(self) -> dict:
        """
        Extends parent class method to add controls to dict

        Returns:
            dict: dictionary used in submissions summary
        """        
        output = super().to_dict()
        output['controls'] = [item.to_sub_dict() for item in self.controls]
        return output   

class Wastewater(BasicSubmission):
    """
    derivative submission type from BasicSubmission
    """    
    # samples = relationship("WWSample", back_populates="rsl_plate", uselist=True)
    pcr_info = Column(JSON)
    # ww_sample_id = Column(String, ForeignKey("_ww_samples.id", ondelete="SET NULL", name="fk_WW_sample_id"))
    __mapper_args__ = {"polymorphic_identity": "wastewater", "polymorphic_load": "inline"}

    def to_dict(self) -> dict:
        """
        Extends parent class method to add controls to dict

        Returns:
            dict: dictionary used in submissions summary
        """        
        output = super().to_dict()
        try:
            output['pcr_info'] = json.loads(self.pcr_info)
        except TypeError as e:
            pass
        return output
    
class WastewaterArtic(BasicSubmission):
    """
    derivative submission type for artic wastewater
    """    
    # samples = relationship("WWSample", back_populates="artic_rsl_plate", uselist=True)
    # Can it use the pcr_info from the wastewater? Cause I can't define pcr_info here due to conflicts with that
    # Not necessary because we don't get any results for this procedure.
    __mapper_args__ = {"polymorphic_identity": "wastewater_artic", "polymorphic_load": "inline"}

    def calculate_base_cost(self):
        """
        This method overrides parent method due to multiple output plates from a single submission
        """        
        logger.debug(f"Hello from calculate base cost in WWArtic")
        try:
            cols_count_96 = ceil(int(self.sample_count) / 8)
        except Exception as e:
            logger.error(f"Column count error: {e}")
        # Since we have multiple output plates per submission form, the constant cost will have to reflect this.
        output_plate_count = math.ceil(int(self.sample_count) / 16)
        logger.debug(f"Looks like we have {output_plate_count} output plates.")
        const_cost = self.extraction_kit.constant_cost * output_plate_count
        try:
            self.run_cost = const_cost + (self.extraction_kit.mutable_cost_column * cols_count_96) + (self.extraction_kit.mutable_cost_sample * int(self.sample_count))
        except Exception as e:
            logger.error(f"Calculation error: {e}")

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
        "polymorphic_on": sample_type,
        "with_polymorphic": "*",
    }

    submissions = association_proxy("sample_submission_associations", "submission")

    @validates('submitter_id')
    def create_id(self, key, value):
        logger.debug(f"validating sample_id of: {value}")
        if value == None:
            return uuid.uuid4().hex.upper()
        else:
            return value
        
    def __repr__(self) -> str:
        return f"{self.sample_type}Sample({self.submitter_id})"
    
    def to_sub_dict(self, submission_rsl:str) -> dict:
        row_map = {1:"A", 2:"B", 3:"C", 4:"D", 5:"E", 6:"F", 7:"G", 8:"H"}
        self.assoc = [item for item in self.sample_submission_associations if item.submission.rsl_plate_num==submission_rsl][0]
        sample = {}
        try:
            sample['well'] = f"{row_map[self.assoc.row]}{self.assoc.column}"
        except KeyError as e:
            logger.error(f"Unable to find row {self.assoc.row} in row_map.")
            sample['well'] = None
        sample['name'] = self.submitter_id
        return sample
    
    def to_hitpick(self, submission_rsl:str) -> dict|None:
        """
        Outputs a dictionary of locations

        Returns:
            dict: dictionary of sample id, row and column in elution plate
        """        
        self.assoc = [item for item in self.sample_submission_associations if item.submission.rsl_plate_num==submission_rsl][0]
        # dictionary to translate row letters into numbers
        # row_dict = dict(A=1, B=2, C=3, D=4, E=5, F=6, G=7, H=8)
        # if either n1 or n2 is positive, include this sample
        # well_row = row_dict[self.well_number[0]]
        # The remaining charagers are the columns
        # well_col = self.well_number[1:]
        return dict(name=self.submitter_id, 
                    # row=well_row, 
                    # col=well_col, 
                    positive=False)

class WastewaterSample(BasicSample):
    """
    Base wastewater sample
    """
    # __tablename__ = "_ww_samples"

    # id = Column(INTEGER, primary_key=True) #: primary key
    ww_processing_num = Column(String(64)) #: wastewater processing number 
    # ww_sample_full_id = Column(String(64), nullable=False, unique=True)
    rsl_number = Column(String(64)) #: rsl plate identification number
    # rsl_plate = relationship("Wastewater", back_populates="samples") #: relationship to parent plate
    # rsl_plate_id = Column(INTEGER, ForeignKey("_submissions.id", ondelete="SET NULL", name="fk_WWS_submission_id"))
    collection_date = Column(TIMESTAMP) #: Date submission received
    # well_number = Column(String(8)) #: location on 96 well plate
    # The following are fields from the sample tracking excel sheet Ruth put together.
    # I have no idea when they will be implemented or how.
    testing_type = Column(String(64)) 
    site_status = Column(String(64))
    notes = Column(String(2000))
    # ct_n1 = Column(FLOAT(2)) #: AKA ct for N1
    # ct_n2 = Column(FLOAT(2)) #: AKA ct for N2
    # n1_status = Column(String(32))
    # n2_status = Column(String(32))
    seq_submitted = Column(BOOLEAN())
    ww_seq_run_id = Column(String(64))
    # sample_type = Column(String(16))
    # pcr_results = Column(JSON)
    well_24 = Column(String(8)) #: location on 24 well plate
    # artic_rsl_plate = relationship("WastewaterArtic", back_populates="samples")
    # artic_well_number = Column(String(8))
    
    __mapper_args__ = {"polymorphic_identity": "wastewater_sample", "polymorphic_load": "inline"}

    # def to_string(self) -> str:
    #     """
    #     string representing sample object

    #     Returns:
    #         str: string representing location and sample id
    #     """        
    #     return f"{self.well_number}: {self.ww_sample_full_id}"

    def to_sub_dict(self, submission_rsl:str) -> dict:
        """
        Gui friendly dictionary. Inherited from BasicSample
        This version will include PCR status.

        Args:
            submission_rsl (str): RSL plate number (passed down from the submission.to_dict() functino)

        Returns:
            dict: Alphanumeric well id and sample name
        """        
        # Get the relevant submission association for this sample
        sample = super().to_sub_dict(submission_rsl=submission_rsl)
        try:
            check = self.assoc.ct_n1 != None and self.assoc.ct_n2 != None
        except AttributeError as e:
            check = False
        if check:
            logger.debug(f"Using well info in name.")
            sample['name'] = f"{self.submitter_id}\n\t- ct N1: {'{:.2f}'.format(self.assoc.ct_n1)} ({self.assoc.n1_status})\n\t- ct N2: {'{:.2f}'.format(self.assoc.ct_n2)} ({self.assoc.n2_status})"
        else:
            logger.error(f"Couldn't get the pcr info")
        return sample
    
    def to_hitpick(self, submission_rsl:str) -> dict|None:
        """
        Outputs a dictionary of locations if sample is positive

        Returns:
            dict: dictionary of sample id, row and column in elution plate
        """       
        sample = super().to_hitpick(submission_rsl=submission_rsl)
        # dictionary to translate row letters into numbers
        # row_dict = dict(A=1, B=2, C=3, D=4, E=5, F=6, G=7, H=8)
        # if either n1 or n2 is positive, include this sample
        try:
            sample['positive'] = any(["positive" in item for item in [self.assoc.n1_status, self.assoc.n2_status]])
        except (TypeError, AttributeError) as e:
            logger.error(f"Couldn't check positives for {self.rsl_number}. Looks like there isn't PCR data.")
            # return None
            # positive = False
        # well_row = row_dict[self.well_number[0]]
        # well_col = self.well_number[1:]
        # if positive:
        #     try:
        #         # The first character of the elution well is the row
        #         well_row = row_dict[self.elution_well[0]]
        #         # The remaining charagers are the columns
        #         well_col = self.elution_well[1:]
        #     except TypeError as e:
        #         logger.error(f"This sample doesn't have elution plate info.")
        #         return None
        return sample
        

class BacterialCultureSample(BasicSample):
    """
    base of bacterial culture sample
    """
    # __tablename__ = "_bc_samples"

    # id = Column(INTEGER, primary_key=True) #: primary key
    # well_number = Column(String(8)) #: location on parent plate
    # sample_id = Column(String(64), nullable=False, unique=True) #: identification from submitter
    organism = Column(String(64)) #: bacterial specimen
    concentration = Column(String(16)) #:
    # sample_type = Column(String(16))
    # rsl_plate_id = Column(INTEGER, ForeignKey("_submissions.id", ondelete="SET NULL", name="fk_BCS_sample_id")) #: id of parent plate
    # rsl_plate = relationship("BacterialCulture", back_populates="samples") #: relationship to parent plate

    __mapper_args__ = {"polymorphic_identity": "bacterial_culture_sample", "polymorphic_load": "inline"}

    # def to_string(self) -> str:
    #     """
    #     string representing object

    #     Returns:
    #         str: string representing well location, sample id and organism
    #     """        
    #     return f"{self.well_number}: {self.sample_id} - {self.organism}"

    def to_sub_dict(self, submission_rsl:str) -> dict:
        """
        gui friendly dictionary

        Returns:
            dict: well location and name (sample id, organism) NOTE: keys must sync with WWSample to_sub_dict above
        """
        sample = super().to_sub_dict(submission_rsl=submission_rsl)
        sample['name'] = f"{self.submitter_id} - ({self.organism})"
        # return {
        #     # "well": self.well_number,
        #     "name": f"{self.submitter_id} - ({self.organism})",
        # }
        return sample

    

class SubmissionSampleAssociation(Base):
    """
    table containing submission/sample associations
    DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
    """    
    __tablename__ = "_submission_sample"
    sample_id = Column(INTEGER, ForeignKey("_samples.id"), primary_key=True)
    submission_id = Column(INTEGER, ForeignKey("_submissions.id"), primary_key=True)
    row = Column(INTEGER)
    column = Column(INTEGER)

    submission = relationship(BasicSubmission, back_populates="submission_sample_associations")

    # reference to the "ReagentType" object
    # sample = relationship("BasicSample")
    sample = relationship(BasicSample, back_populates="sample_submission_associations")

    base_sub_type = Column(String)
    # """Refers to the type of parent."""

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

class WastewaterAssociation(SubmissionSampleAssociation):

    ct_n1 = Column(FLOAT(2)) #: AKA ct for N1
    ct_n2 = Column(FLOAT(2)) #: AKA ct for N2
    n1_status = Column(String(32))
    n2_status = Column(String(32))
    pcr_results = Column(JSON)

    __mapper_args__ = {"polymorphic_identity": "wastewater", "polymorphic_load": "inline"}