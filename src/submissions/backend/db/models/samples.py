'''
All models for individual samples.
'''
from . import Base
from sqlalchemy import Column, String, TIMESTAMP, INTEGER, ForeignKey, FLOAT, BOOLEAN, JSON
from sqlalchemy.orm import relationship
import logging


logger = logging.getLogger(f"submissions.{__name__}")


class WWSample(Base):
    """
    Base wastewater sample
    """
    __tablename__ = "_ww_samples"

    id = Column(INTEGER, primary_key=True) #: primary key
    ww_processing_num = Column(String(64)) #: wastewater processing number 
    ww_sample_full_id = Column(String(64), nullable=False)
    rsl_number = Column(String(64)) #: rsl plate identification number
    rsl_plate = relationship("Wastewater", back_populates="samples") #: relationship to parent plate
    rsl_plate_id = Column(INTEGER, ForeignKey("_submissions.id", ondelete="SET NULL", name="fk_WWS_submission_id"))
    collection_date = Column(TIMESTAMP) #: Date submission received
    well_number = Column(String(8)) #: location on 96 well plate
    # The following are fields from the sample tracking excel sheet Ruth put together.
    # I have no idea when they will be implemented or how.
    testing_type = Column(String(64)) 
    site_status = Column(String(64))
    notes = Column(String(2000))
    ct_n1 = Column(FLOAT(2)) #: AKA ct for N1
    ct_n2 = Column(FLOAT(2)) #: AKA ct for N2
    n1_status = Column(String(32))
    n2_status = Column(String(32))
    seq_submitted = Column(BOOLEAN())
    ww_seq_run_id = Column(String(64))
    sample_type = Column(String(8))
    pcr_results = Column(JSON)
    well_24 = Column(String(8)) #: location on 24 well plate
    artic_rsl_plate = relationship("WastewaterArtic", back_populates="samples")
    artic_well_number = Column(String(8))
    

    def to_string(self) -> str:
        """
        string representing sample object

        Returns:
            str: string representing location and sample id
        """        
        return f"{self.well_number}: {self.ww_sample_full_id}"

    def to_sub_dict(self) -> dict:
        """
        gui friendly dictionary

        Returns:
            dict: well location and id NOTE: keys must sync with BCSample to_sub_dict below
        """
        if self.ct_n1 != None and self.ct_n2 != None:
            # logger.debug(f"Using well info in name.")
            name = f"{self.ww_sample_full_id}\n\t- ct N1: {'{:.2f}'.format(self.ct_n1)} ({self.n1_status})\n\t- ct N2: {'{:.2f}'.format(self.ct_n2)} ({self.n2_status})"
        else:
            # logger.debug(f"NOT using well info in name for: {self.ww_sample_full_id}")
            name = self.ww_sample_full_id
        return {
            "well": self.well_number,
            "name": name,
        }
    
    def to_hitpick(self) -> dict|None:
        """
        Outputs a dictionary of locations if sample is positive

        Returns:
            dict: dictionary of sample id, row and column in elution plate
        """        
        # dictionary to translate row letters into numbers
        row_dict = dict(A=1, B=2, C=3, D=4, E=5, F=6, G=7, H=8)
        # if either n1 or n2 is positive, include this sample
        try:
            positive = any(["positive" in item for item in [self.n1_status, self.n2_status]])
        except TypeError as e:
            logger.error(f"Couldn't check positives for {self.rsl_number}. Looks like there isn't PCR data.")
            return None
        well_row = row_dict[self.well_number[0]]
        well_col = self.well_number[1:]
        # if positive:
        #     try:
        #         # The first character of the elution well is the row
        #         well_row = row_dict[self.elution_well[0]]
        #         # The remaining charagers are the columns
        #         well_col = self.elution_well[1:]
        #     except TypeError as e:
        #         logger.error(f"This sample doesn't have elution plate info.")
        #         return None
        return dict(name=self.ww_sample_full_id, 
                    row=well_row, 
                    col=well_col, 
                    positive=positive)
        # else:
        #     return None


class BCSample(Base):
    """
    base of bacterial culture sample
    """
    __tablename__ = "_bc_samples"

    id = Column(INTEGER, primary_key=True) #: primary key
    well_number = Column(String(8)) #: location on parent plate
    sample_id = Column(String(64), nullable=False) #: identification from submitter
    organism = Column(String(64)) #: bacterial specimen
    concentration = Column(String(16)) #:
    rsl_plate_id = Column(INTEGER, ForeignKey("_submissions.id", ondelete="SET NULL", name="fk_BCS_sample_id")) #: id of parent plate
    rsl_plate = relationship("BacterialCulture", back_populates="samples") #: relationship to parent plate

    def to_string(self) -> str:
        """
        string representing object

        Returns:
            str: string representing well location, sample id and organism
        """        
        return f"{self.well_number}: {self.sample_id} - {self.organism}"

    def to_sub_dict(self) -> dict:
        """
        gui friendly dictionary

        Returns:
            dict: well location and name (sample id, organism) NOTE: keys must sync with WWSample to_sub_dict above
        """
        return {
            "well": self.well_number,
            "name": f"{self.sample_id} - ({self.organism})",
        }

    def to_hitpick(self) -> dict|None:
        """
        Outputs a dictionary of locations

        Returns:
            dict: dictionary of sample id, row and column in elution plate
        """        
        # dictionary to translate row letters into numbers
        row_dict = dict(A=1, B=2, C=3, D=4, E=5, F=6, G=7, H=8)
        # if either n1 or n2 is positive, include this sample
        well_row = row_dict[self.well_number[0]]
        # The remaining charagers are the columns
        well_col = self.well_number[1:]
        return dict(name=self.sample_id, 
                    row=well_row, 
                    col=well_col, 
                    positive=False)
        
# class ArticSample(Base):
#     """
#     base of artic sample
#     """    
#     __tablename__ = "_artic_samples"

#     id = Column(INTEGER, primary_key=True) #: primary key
#     well_number = Column(String(8)) #: location on parent plate
#     rsl_plate = relationship("WastewaterArtic", back_populates="samples") #: relationship to parent plate
#     rsl_plate_id = Column(INTEGER, ForeignKey("_submissions.id", ondelete="SET NULL", name="fk_WWA_submission_id"))
#     ww_sample_full_id = Column(String(64), nullable=False)
#     lims_sample_id = Column(String(64), nullable=False)
#     ct_1 = Column(FLOAT(2)) #: first ct value in column
#     ct_2 = Column(FLOAT(2)) #: second ct value in column

#     def to_string(self) -> str:
#         """
#         string representing sample object

#         Returns:
#             str: string representing location and sample id
#         """        
#         return f"{self.well_number}: {self.ww_sample_full_id}"
    
#     def to_sub_dict(self) -> dict:
#         """
#         gui friendly dictionary

#         Returns:
#             dict: well location and name (sample id, organism) NOTE: keys must sync with WWSample to_sub_dict above
#         """
#         return {
#             "well": self.well_number,
#             "name": self.ww_sample_full_id,
#         }
    
