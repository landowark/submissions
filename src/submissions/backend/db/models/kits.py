from . import Base
from sqlalchemy import Column, String, TIMESTAMP, JSON, INTEGER, ForeignKey, Interval, Table, FLOAT
from sqlalchemy.orm import relationship


reagenttypes_kittypes = Table("_reagentstypes_kittypes", Base.metadata, Column("reagent_types_id", INTEGER, ForeignKey("_reagent_types.id")), Column("kits_id", INTEGER, ForeignKey("_kits.id")))


class KitType(Base):

    __tablename__ = "_kits"

    id = Column(INTEGER, primary_key=True) #: primary key  
    name = Column(String(64), unique=True)
    submissions = relationship("BasicSubmission", back_populates="extraction_kit")
    used_for = Column(JSON)
    cost_per_run = Column(FLOAT(2))
    reagent_types = relationship("ReagentType", back_populates="kits", uselist=True, secondary=reagenttypes_kittypes)
    reagent_types_id = Column(INTEGER, ForeignKey("_reagent_types.id", ondelete='SET NULL', use_alter=True, name="fk_KT_reagentstype_id"))
    
    def __str__(self):
        return self.name
    

class ReagentType(Base):

    __tablename__ = "_reagent_types"

    id = Column(INTEGER, primary_key=True) #: primary key  
    name = Column(String(64))
    kit_id = Column(INTEGER, ForeignKey("_kits.id", ondelete="SET NULL", use_alter=True, name="fk_RT_kits_id"))
    kits = relationship("KitType", back_populates="reagent_types", uselist=True, foreign_keys=[kit_id])
    instances = relationship("Reagent", back_populates="type")
    # instances_id = Column(INTEGER, ForeignKey("_reagents.id", ondelete='SET NULL'))
    eol_ext = Column(Interval())

    def __str__(self):
        return self.name


class Reagent(Base):

    __tablename__ = "_reagents"

    id = Column(INTEGER, primary_key=True) #: primary key
    type = relationship("ReagentType", back_populates="instances")
    type_id = Column(INTEGER, ForeignKey("_reagent_types.id", ondelete='SET NULL', name="fk_reagent_type_id"))
    name = Column(String(64))
    lot = Column(String(64))
    expiry = Column(TIMESTAMP)
    submissions = relationship("BasicSubmission", back_populates="reagents", uselist=True)

    def __str__(self):
        return self.lot

    def to_sub_dict(self):
        try:
            type = self.type.name.replace("_", " ").title()
        except AttributeError:
            type = "Unknown"
        return {
            "type": type,
            "lot": self.lot,
            "expiry": self.expiry.strftime("%Y-%m-%d")
        }

    
    