"""
All control related models.
"""
from __future__ import annotations
from sqlalchemy import Column, String, TIMESTAMP, JSON, INTEGER, ForeignKey
from sqlalchemy.orm import relationship, Query
import logging, re
from operator import itemgetter
from . import BaseClass
from tools import setup_lookup
from datetime import date, datetime
from typing import List, Literal
from dateutil.parser import parse
from re import Pattern

logger = logging.getLogger(f"submissions.{__name__}")


class ControlType(BaseClass):
    """
    Base class of a control archetype.
    """
    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(255), unique=True)  #: controltype name (e.g. MCS)
    targets = Column(JSON)  #: organisms checked for
    instances = relationship("Control", back_populates="controltype")  #: control samples created of this type.

    def __repr__(self) -> str:
        return f"<ControlType({self.name})>"

    @classmethod
    @setup_lookup
    def query(cls,
              name: str = None,
              limit: int = 0
              ) -> ControlType | List[ControlType]:
        """
        Lookup control archetypes in the database

        Args:
            name (str, optional): Name of the desired controltype. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            ControlType | List[ControlType]: Single result if the limit = 1, else a list.
        """
        query = cls.__database_session__.query(cls)
        match name:
            case str():
                query = query.filter(cls.name == name)
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    def get_subtypes(self, mode: Literal['kraken', 'matches', 'contains']) -> List[str]:
        """
        Get subtypes associated with this controltype (currently used only for Kraken)

        Args:
            mode (str): analysis mode sub_type

        Returns:
            List[str]: list of subtypes available
        """
        # NOTE: Get first instance since all should have same subtypes
        # NOTE: Get mode of instance
        jsoner = getattr(self.instances[0], mode)
        # logger.debug(f"JSON out: {jsoner.keys()}")
        try:
            # NOTE: Pick genera (all should have same subtypes)
            genera = list(jsoner.keys())[0]
        except IndexError:
            return []
        # NOTE: remove items that don't have relevant data
        subtypes = [item for item in jsoner[genera] if "_hashes" not in item and "_ratio" not in item]
        return subtypes

    @classmethod
    def get_positive_control_types(cls) -> List[ControlType]:
        """
        Gets list of Control types if they have targets

        Returns:
            List[ControlType]: Control types that have targets
        """
        return [item for item in cls.query() if item.targets]

    @classmethod
    def build_positive_regex(cls) -> Pattern:
        """
        Creates a re.Pattern that will look for positive control types

        Returns:
            Pattern: Constructed pattern
        """
        strings = list(set([item.name.split("-")[0] for item in cls.get_positive_control_types()]))
        return re.compile(rf"(^{'|^'.join(strings)})-.*", flags=re.IGNORECASE)


class Control(BaseClass):
    """
    Base class of a control sample.
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    parent_id = Column(String,
                       ForeignKey("_controltype.id", name="fk_control_parent_id"))  #: primary key of control type
    controltype = relationship("ControlType", back_populates="instances",
                               foreign_keys=[parent_id])  #: reference to parent control type
    name = Column(String(255), unique=True)  #: Sample ID
    submitted_date = Column(TIMESTAMP)  #: Date submitted to Robotics
    contains = Column(JSON)  #: unstructured hashes in contains.tsv for each organism
    matches = Column(JSON)  #: unstructured hashes in matches.tsv for each organism
    kraken = Column(JSON)  #: unstructured output from kraken_report
    submission_id = Column(INTEGER, ForeignKey("_basicsubmission.id"))  #: parent submission id
    submission = relationship("BacterialCulture", back_populates="controls",
                              foreign_keys=[submission_id])  #: parent submission
    refseq_version = Column(String(16))  #: version of refseq used in fastq parsing
    kraken2_version = Column(String(16))  #: version of kraken2 used in fastq parsing
    kraken2_db_version = Column(String(32))  #: folder name of kraken2 db
    sample = relationship("BacterialCultureSample", back_populates="control")  #: This control's submission sample
    sample_id = Column(INTEGER,
                       ForeignKey("_basicsample.id", ondelete="SET NULL", name="cont_BCS_id"))  #: sample id key

    def __repr__(self) -> str:
        return f"<Control({self.name})>"

    def to_sub_dict(self) -> dict:
        """
        Converts object into convenient dictionary for use in submission summary

        Returns:
            dict: output dictionary containing: Name, Type, Targets, Top Kraken results
        """
        # logger.debug("loading json string into dict")
        try:
            kraken = self.kraken
        except TypeError:
            kraken = {}
        # logger.debug("calculating kraken count total to use in percentage")
        kraken_cnt_total = sum([kraken[item]['kraken_count'] for item in kraken])
        # logger.debug("Creating new kraken.")
        new_kraken = [dict(name=item, kraken_count=kraken[item]['kraken_count'],
                           kraken_percent="{0:.0%}".format(kraken[item]['kraken_count'] / kraken_cnt_total),
                           target=item in self.controltype.targets)
                      for item in kraken]
        # logger.debug(f"New kraken before sort: {new_kraken}")
        new_kraken = sorted(new_kraken, key=itemgetter('kraken_count'), reverse=True)
        # logger.debug("setting targets")
        if self.controltype.targets:
            targets = self.controltype.targets
        else:
            targets = ["None"]
        # logger.debug("constructing output dictionary")
        output = {
            "name": self.name,
            "type": self.controltype.name,
            "targets": ", ".join(targets),
            "kraken": new_kraken[0:10]
        }
        return output

    def convert_by_mode(self, mode: Literal['kraken', 'matches', 'contains']) -> List[dict]:
        """
        split this instance into analysis types for controls graphs

        Args:
            mode (str): analysis type, 'contains', etc

        Returns:
            List[dict]: list of records
        """
        output = []
        # logger.debug("load json string for mode (i.e. contains, matches, kraken2)")
        try:
            data = self.__getattribute__(mode)
        except TypeError:
            data = {}
        if data is None:
            data = {}
        # logger.debug(f"Length of data: {len(data)}")
        # logger.debug("dict keys are genera of bacteria, e.g. 'Streptococcus'")
        for genus in data:
            _dict = dict(
                name=self.name,
                submitted_date=self.submitted_date,
                genus=genus,
                target='Target' if genus.strip("*") in self.controltype.targets else "Off-target"
            )
            # logger.debug("get Target or Off-target of genus")
            # logger.debug("set 'contains_hashes', etc for genus")
            for key in data[genus]:
                _dict[key] = data[genus][key]
            output.append(_dict)
        # logger.debug("Have to triage kraken data to keep program from getting overwhelmed")
        if "kraken" in mode:
            output = sorted(output, key=lambda d: d[f"{mode}_count"], reverse=True)[:50]
        return output

    @classmethod
    def get_modes(cls) -> List[str]:
        """
        Get all control modes from database

        Returns:
            List[str]: List of control mode names.
        """
        try:
            # logger.debug("Creating a list of JSON columns in _controls table")
            cols = [item.name for item in list(cls.__table__.columns) if isinstance(item.type, JSON)]
        except AttributeError as e:
            logger.error(f"Failed to get available modes from db: {e}")
            cols = []
        return cols

    @classmethod
    @setup_lookup
    def query(cls,
              control_type: ControlType | str | None = None,
              start_date: date | str | int | None = None,
              end_date: date | str | int | None = None,
              control_name: str | None = None,
              limit: int = 0
              ) -> Control | List[Control]:
        """
        Lookup control objects in the database based on a number of parameters.

        Args:
            control_type (models.ControlType | str | None, optional): Control archetype. Defaults to None.
            start_date (date | str | int | None, optional): Beginning date to search by. Defaults to 2023-01-01 if end_date not None.
            end_date (date | str | int | None, optional): End date to search by. Defaults to today if start_date not None.
            control_name (str | None, optional): Name of control. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            models.Control|List[models.Control]: Control object of interest.
        """
        query: Query = cls.__database_session__.query(cls)
        # NOTE: by control type
        match control_type:
            case ControlType():
                # logger.debug(f"Looking up control by control type: {control_type}")
                query = query.filter(cls.controltype == control_type)
            case str():
                # logger.debug(f"Looking up control by control type: {control_type}")
                query = query.join(ControlType).filter(ControlType.name == control_type)
            case _:
                pass
        # NOTE: by date range
        if start_date is not None and end_date is None:
            logger.warning(f"Start date with no end date, using today.")
            end_date = date.today()
        if end_date is not None and start_date is None:
            logger.warning(f"End date with no start date, using Jan 1, 2023")
            start_date = date(2023, 1, 1)
        if start_date is not None:
            match start_date:
                case date():
                    # logger.debug(f"Lookup control by start date({start_date})")
                    start_date = start_date.strftime("%Y-%m-%d")
                case int():
                    # logger.debug(f"Lookup control by ordinal start date {start_date}")
                    start_date = datetime.fromordinal(
                        datetime(1900, 1, 1).toordinal() + start_date - 2).date().strftime("%Y-%m-%d")
                case _:
                    # logger.debug(f"Lookup control with parsed start date {start_date}")
                    start_date = parse(start_date).strftime("%Y-%m-%d")
            match end_date:
                case date():
                    # logger.debug(f"Lookup control by end date({end_date})")
                    end_date = end_date.strftime("%Y-%m-%d")
                case int():
                    # logger.debug(f"Lookup control by ordinal end date {end_date}")
                    end_date = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + end_date - 2).date().strftime(
                        "%Y-%m-%d")
                case _:
                    # logger.debug(f"Lookup control with parsed end date {end_date}")
                    end_date = parse(end_date).strftime("%Y-%m-%d")
            # logger.debug(f"Looking up BasicSubmissions from start date: {start_date} and end date: {end_date}")
            query = query.filter(cls.submitted_date.between(start_date, end_date))
        match control_name:
            case str():
                # logger.debug(f"Lookup control by name {control_name}")
                query = query.filter(cls.name.startswith(control_name))
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)
