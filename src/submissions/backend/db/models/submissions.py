from . import Base
from sqlalchemy import Column, String, TIMESTAMP, text, JSON, INTEGER, ForeignKey, UniqueConstraint, Table
from sqlalchemy.orm import relationship, relationships
from datetime import datetime as dt

reagents_submissions = Table("_reagents_submissions", Base.metadata, Column("reagent_id", INTEGER, ForeignKey("_reagents.id")), Column("submission_id", INTEGER, ForeignKey("_submissions.id")))

class BasicSubmission(Base):

    # TODO: Figure out if I want seperate tables for different sample types.
    __tablename__ = "_submissions"

    id = Column(INTEGER, primary_key=True) #: primary key   
    rsl_plate_num = Column(String(32), unique=True) #: RSL name (e.g. RSL-22-0012)
    submitter_plate_num = Column(String(127), unique=True) #: The number given to the submission by the submitting lab
    submitted_date = Column(TIMESTAMP) #: Date submission received
    submitting_lab = relationship("Organization", back_populates="submissions") #: client
    submitting_lab_id = Column(INTEGER, ForeignKey("_organizations.id", ondelete="SET NULL"))
    sample_count = Column(INTEGER) #: Number of samples in the submission
    extraction_kit = relationship("KitType", back_populates="submissions") #: The extraction kit used
    extraction_kit_id = Column(INTEGER, ForeignKey("_kits.id", ondelete="SET NULL"))
    submission_type = Column(String(32))
    technician = Column(String(64))
    # Move this into custom types?
    reagents = relationship("Reagent", back_populates="submissions", secondary=reagents_submissions)
    reagents_id = Column(String, ForeignKey("_reagents.id", ondelete="SET NULL", name="fk_BS_reagents_id"))

    __mapper_args__ = {
        "polymorphic_identity": "basic_submission",
        "polymorphic_on": submission_type,
        "with_polymorphic": "*",
    }

    def to_dict(self):
        print(self.submitting_lab)
        try:
            sub_lab = self.submitting_lab.name
        except AttributeError:
            sub_lab = None
        try:
            sub_lab = sub_lab.replace("_", " ").title()
        except AttributeError:
            pass
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
            "Technician": self.technician,
        }
        return output


    def report_dict(self):
        try:
            sub_lab = self.submitting_lab.name
        except AttributeError:
            sub_lab = None
        try:
            sub_lab = sub_lab.replace("_", " ").title()
        except AttributeError:
            pass
        try:
            ext_kit = self.extraction_kit.name
        except AttributeError:
            ext_kit = None
        try:
            cost = self.extraction_kit.cost_per_run
        except AttributeError:
            cost = None
        output = {
            "id": self.id,
            "Plate Number": self.rsl_plate_num,
            "Submission Type": self.submission_type.replace("_", " ").title(),
            "Submitter Plate Number": self.submitter_plate_num,
            "Submitted Date": self.submitted_date.strftime("%Y-%m-%d"),
            "Submitting Lab": sub_lab,
            "Sample Count": self.sample_count,
            "Extraction Kit": ext_kit,
            "Cost": cost
        }
        return output

# Below are the custom submission 

class  BacterialCulture(BasicSubmission):
    control = relationship("Control", back_populates="submissions") #: A control sample added to submission
    control_id = Column(INTEGER, ForeignKey("_control_samples.id", ondelete="SET NULL", name="fk_BC_control_id"))
    __mapper_args__ = {"polymorphic_identity": "bacterial_culture", "polymorphic_load": "inline"}
    

class Wastewater(BasicSubmission):
    samples = relationship("Sample", back_populates="rsl_plate")
    sample_id = Column(String, ForeignKey("_ww_samples.id", ondelete="SET NULL", name="fk_WW_sample_id"))
    __mapper_args__ = {"polymorphic_identity": "wastewater", "polymorphic_load": "inline"}