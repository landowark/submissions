'''
All models for individual samples.
'''
from . import Base
from sqlalchemy import Column, String, TIMESTAMP, INTEGER, ForeignKey, FLOAT, BOOLEAN, JSON
from sqlalchemy.orm import relationship


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
    well_number = Column(String(8)) #: location on plate
    # The following are fields from the sample tracking excel sheet Ruth put together.
    # I have no idea when they will be implemented or how.
    testing_type = Column(String(64)) 
    site_status = Column(String(64))
    notes = Column(String(2000))
    ct_n1 = Column(FLOAT(2)) #: AKA ct for N1
    ct_n2 = Column(FLOAT(2)) #: AKA ct for N2
    seq_submitted = Column(BOOLEAN())
    ww_seq_run_id = Column(String(64))
    sample_type = Column(String(8))
    pcr_results = Column(JSON)
    

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
            name = f"{self.ww_sample_full_id}\n\t- ct N1: {'{:.2f}'.format(self.ct_n1)}, ct N2: {'{:.2f}'.format(self.ct_n1)}"
        else:
            name = self.ww_sample_full_id
        return {
            "well": self.well_number,
            "name": name,
        }


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
