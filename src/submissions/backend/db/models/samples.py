from . import Base
from sqlalchemy import Column, String, TIMESTAMP, text, JSON, INTEGER, ForeignKey, FLOAT, BOOLEAN
from sqlalchemy.orm import relationship, relationships


class WWSample(Base):

    __tablename__ = "_ww_samples"

    id = Column(INTEGER, primary_key=True) #: primary key
    ww_processing_num = Column(String(64))
    ww_sample_full_id = Column(String(64), nullable=False)
    rsl_number = Column(String(64))
    rsl_plate = relationship("Wastewater", back_populates="samples")
    rsl_plate_id = Column(INTEGER, ForeignKey("_submissions.id", ondelete="SET NULL", name="fk_WWS_sample_id"))
    collection_date = Column(TIMESTAMP) #: Date submission received
    testing_type = Column(String(64))
    site_status = Column(String(64))
    notes = Column(String(2000))
    ct_n1 = Column(FLOAT(2))
    ct_n2 = Column(FLOAT(2))
    seq_submitted = Column(BOOLEAN())
    ww_seq_run_id = Column(String(64))
    sample_type = Column(String(8))
    well_number = Column(String(8))

    def to_string(self):
        return f"{self.well_number}: {self.ww_sample_full_id}"

    def to_sub_dict(self):
        return {
            "well": self.well_number,
            "name": self.ww_sample_full_id,
        }


class BCSample(Base):

    __tablename__ = "_bc_samples"

    id = Column(INTEGER, primary_key=True) #: primary key
    well_number = Column(String(8))
    sample_id = Column(String(64), nullable=False)
    organism = Column(String(64))
    concentration = Column(String(16))
    rsl_plate_id = Column(INTEGER, ForeignKey("_submissions.id", ondelete="SET NULL", name="fk_BCS_sample_id"))
    rsl_plate = relationship("BacterialCulture", back_populates="samples")

    def to_string(self):
        return f"{self.well_number}: {self.sample_id} - {self.organism}"

    def to_sub_dict(self):
        return {
            "well": self.well_number,
            "name": f"{self.sample_id} - ({self.organism})",
        }
