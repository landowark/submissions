from . import Base
from sqlalchemy import Column, String, TIMESTAMP, JSON, INTEGER, ForeignKey
from sqlalchemy.orm import relationship
import logging
from operator import itemgetter
import json

logger = logging.getLogger(f"submissions.{__name__}")

class ControlType(Base):
    """
    Base class of a control archetype.
    """    
    __tablename__ = '_control_types'
    
    id = Column(INTEGER, primary_key=True) #: primary key   
    name = Column(String(255), unique=True) #: controltype name (e.g. MCS)
    targets = Column(JSON) #: organisms checked for
    # instances_id = Column(INTEGER, ForeignKey("_control_samples.id", ondelete="SET NULL", name="fk_ctype_instances_id"))
    instances = relationship("Control", back_populates="controltype") #: control samples created of this type.
    # UniqueConstraint('name', name='uq_controltype_name')


class Control(Base):
    """
    Base class of a control sample.
    """    

    __tablename__ = '_control_samples'
    
    id = Column(INTEGER, primary_key=True) #: primary key
    parent_id = Column(String, ForeignKey("_control_types.id", name="fk_control_parent_id")) #: primary key of control type
    controltype = relationship("ControlType", back_populates="instances", foreign_keys=[parent_id]) #: reference to parent control type
    name = Column(String(255), unique=True) #: Sample ID
    submitted_date = Column(TIMESTAMP) #: Date submitted to Robotics
    contains = Column(JSON) #: unstructured hashes in contains.tsv for each organism
    matches = Column(JSON) #: unstructured hashes in matches.tsv for each organism
    kraken = Column(JSON) #: unstructured output from kraken_report
    # UniqueConstraint('name', name='uq_control_name')
    submission_id = Column(INTEGER, ForeignKey("_submissions.id")) #: parent submission id
    submission = relationship("BacterialCulture", back_populates="controls", foreign_keys=[submission_id]) #: parent submission
    refseq_version = Column(String(16)) #: version of refseq used in fastq parsing
    kraken2_version = Column(String(16)) #: version of kraken2 used in fastq parsing
    kraken2_db_version = Column(String(32)) #: folder name of kraken2 db


    def to_sub_dict(self) -> dict:
        """
        Converts object into convenient dictionary for use in submission summary

        Returns:
            dict: output dictionary containing: Name, Type, Targets, Top Kraken results
        """        
        # load json string into dict
        kraken = json.loads(self.kraken)
        # calculate kraken count total to use in percentage
        kraken_cnt_total = sum([kraken[item]['kraken_count'] for item in kraken])
        new_kraken = []
        for item in kraken:
            # calculate kraken percent (overwrites what's already been scraped)
            kraken_percent = kraken[item]['kraken_count'] / kraken_cnt_total
            new_kraken.append({'name': item, 'kraken_count':kraken[item]['kraken_count'], 'kraken_percent':"{0:.0%}".format(kraken_percent)})
        new_kraken = sorted(new_kraken, key=itemgetter('kraken_count'), reverse=True)
        # set targets
        if self.controltype.targets == []:
            targets = ["None"]
        else:
            targets = self.controltype.targets
        # construct output dictionary
        output = {
            "name" : self.name,
            "type" : self.controltype.name,
            "targets" : ", ".join(targets),
            "kraken" : new_kraken[0:5]
        }
        return output

    def convert_by_mode(self, mode:str) -> list[dict]:
        """
        split control object into analysis types for controls graphs

        Args:
            control (models.Control): control to be parsed into list
            mode (str): analysis type, 'contains', etc

        Returns:
            list[dict]: list of records
        """    
        output = []
        # load json string for mode (i.e. contains, matches, kraken2)
        data = json.loads(getattr(self, mode))
        logger.debug(f"Length of data: {len(data)}")
        # dict keys are genera of bacteria, e.g. 'Streptococcus'
        for genus in data:
            _dict = {}
            _dict['name'] = self.name
            _dict['submitted_date'] = self.submitted_date
            _dict['genus'] = genus
            # get Target or Off-target of genus
            _dict['target'] = 'Target' if genus.strip("*") in self.controltype.targets else "Off-target"
            # set 'contains_hashes', etc for genus, 
            for key in data[genus]:
                _dict[key] = data[genus][key]
            output.append(_dict)
        return output
    
    def create_dummy_data(self, mode:str) -> dict:
        """
        Create non-zero length data to maintain entry of zero length 'contains' (depreciated)

        Args:
            mode (str): analysis type, 'contains', etc

        Returns:
            dict: dictionary of 'Nothing' genus
        """        
        match mode:
            case "contains":
                data = {"Nothing": {"contains_hashes":"0/400", "contains_ratio":0.0}}
            case "matches":
                data = {"Nothing": {"matches_hashes":"0/400", "matches_ratio":0.0}}
            case "kraken":
                data = {"Nothing": {"kraken_percent":0.0, "kraken_count":0}}
            case _:
                data = {}
        return data

