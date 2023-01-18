from . import Base
from sqlalchemy import Column, String, TIMESTAMP, text, JSON, INTEGER, ForeignKey, FLOAT, BOOLEAN
from sqlalchemy.orm import relationship, relationships


class Sample(Base):

    __tablename__ = "_ww_samples"

    id = Column(INTEGER, primary_key=True) #: primary key
    ww_processing_num = Column(String(64))
    ww_sample_full_id = Column(String(64))
    rsl_number = Column(String(64))
    rsl_plate = relationship("Wastewater", back_populates="samples")
    collection_date = Column(TIMESTAMP) #: Date submission received
    testing_type = Column(String(64))
    site_status = Column(String(64))
    notes = Column(String(2000))
    ct_n1 = Column(FLOAT(2))
    ct_n2 = Column(FLOAT(2))
    seq_submitted = Column(BOOLEAN())
    ww_seq_run_id = Column(String(64))
    sample_type = Column(String(8))




