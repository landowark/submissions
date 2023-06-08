'''
Models for the main submission types.
'''
from . import Base
from sqlalchemy import Column, String, TIMESTAMP, INTEGER, ForeignKey, Table, JSON, FLOAT
from sqlalchemy.orm import relationship
from datetime import datetime as dt
import logging
import json
from json.decoder import JSONDecodeError
from math import ceil

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

    # Allows for subclassing into ex. BacterialCulture, Wastewater, etc.
    __mapper_args__ = {
        "polymorphic_identity": "basic_submission",
        "polymorphic_on": submission_type,
        "with_polymorphic": "*",
    }

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
        try:
            samples = [item.to_sub_dict() for item in self.samples]
        except:
            samples = None
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
        # logger.debug(f"{self.rsl_plate_num} extraction: {output['Extraction Status']}")
        # logger.debug(f"Output dict: {output}")
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
        # get extraction kit cost from nested kittype object
        # depreciated as it will change kit cost overtime
        # try:
        #     cost = self.extraction_kit.cost_per_run
        # except AttributeError:
        #     cost = None
        
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
            cols_count_96 = ceil(int(self.sample_count) / 8)
        except Exception as e:
            logger.error(f"Column count error: {e}")
        # cols_count_24 = ceil(int(self.sample_count) / 3)
        try:
            self.run_cost = self.extraction_kit.constant_cost + (self.extraction_kit.mutable_cost_column * cols_count_96) + (self.extraction_kit.mutable_cost_sample * int(self.sample_count))
        except Exception as e:
            logger.error(f"Calculation error: {e}")

# Below are the custom submission types

class  BacterialCulture(BasicSubmission):
    """
    derivative submission type from BasicSubmission
    """    
    controls = relationship("Control", back_populates="submission", uselist=True) #: A control sample added to submission
    samples = relationship("BCSample", back_populates="rsl_plate", uselist=True)
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
    

    # def calculate_base_cost(self):
    #     try:
    #         cols_count_96 = ceil(int(self.sample_count) / 8)
    #     except Exception as e:
    #         logger.error(f"Column count error: {e}")
    #     # cols_count_24 = ceil(int(self.sample_count) / 3)
    #     try:
    #         self.run_cost = self.extraction_kit.constant_cost + (self.extraction_kit.mutable_cost_column * cols_count_96) + (self.extraction_kit.mutable_cost_sample * int(self.sample_count))
    #     except Exception as e:
    #         logger.error(f"Calculation error: {e}")
    

class Wastewater(BasicSubmission):
    """
    derivative submission type from BasicSubmission
    """    
    samples = relationship("WWSample", back_populates="rsl_plate", uselist=True)
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
    
    # def calculate_base_cost(self):
    #     try:
    #         cols_count_96 = ceil(int(self.sample_count) / 8) + 1 #: Adding in one column to account for 24 samples + ext negatives
    #     except Exception as e:
    #         logger.error(f"Column count error: {e}")
    #     # cols_count_24 = ceil(int(self.sample_count) / 3)
    #     try:
    #         self.run_cost = self.extraction_kit.constant_cost + (self.extraction_kit.mutable_cost_column * cols_count_96) + (self.extraction_kit.mutable_cost_sample * int(self.sample_count))
    #     except Exception as e:
    #         logger.error(f"Calculation error: {e}")


class WastewaterArtic(BasicSubmission):
    """
    derivative submission type for artic wastewater
    """    
    samples = relationship("WWSample", back_populates="artic_rsl_plate", uselist=True)
    # Can in use the pcr_info from the wastewater? Cause I can't define pcr_info here due to conflicts with that
    __mapper_args__ = {"polymorphic_identity": "wastewater_artic", "polymorphic_load": "inline"}