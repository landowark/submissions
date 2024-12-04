"""
All control related models.
"""
from __future__ import annotations
from pprint import pformat
from PyQt6.QtWidgets import QWidget, QCheckBox, QLabel
from pandas import DataFrame
from sqlalchemy import Column, String, TIMESTAMP, JSON, INTEGER, ForeignKey, case, FLOAT
from sqlalchemy.orm import relationship, Query, validates
import logging, re
from operator import itemgetter
from . import BaseClass
from tools import setup_lookup, report_result, Result, Report, Settings, get_unique_values_in_df_column, super_splitter
from datetime import date, datetime, timedelta
from typing import List, Literal, Tuple, Generator
from dateutil.parser import parse
from re import Pattern


logger = logging.getLogger(f"submissions.{__name__}")


class ControlType(BaseClass):
    """
    Base class of a control archetype.
    """
    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(255), unique=True)  #: controltype name (e.g. Irida Control)
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

    def get_modes(self, mode: Literal['kraken', 'matches', 'contains']) -> List[str]:
        """
        Get subtypes associated with this controltype (currently used only for Kraken)

        Args:
            mode (str): analysis mode sub_type

        Returns:
            List[str]: list of subtypes available
        """
        if not self.instances:
            return
        # NOTE: Get first instance since all should have same subtypes
        # NOTE: Get mode of instance
        jsoner = getattr(self.instances[0], mode)
        try:
            # NOTE: Pick genera (all should have same subtypes)
            genera = list(jsoner.keys())[0]
        except IndexError:
            return []
        # NOTE subtypes now created for all modes, but ignored for all but allowed_for_subtyping later in the ControlsChart
        subtypes = sorted(list(jsoner[genera].keys()), reverse=True)
        return subtypes

    def get_instance_class(self) -> Control:
        """
        Retrieves the Control class associated with this controltype

        Returns:
            Control: Associated Control class
        """        
        return Control.find_polymorphic_subclass(polymorphic_identity=self.name)

    @classmethod
    def get_positive_control_types(cls, control_type: str) -> Generator[str, None, None]:
        """
        Gets list of Control types if they have targets

        Returns:
            Generator[str, None, None]: Control types that have targets
        """
        ct = cls.query(name=control_type).targets
        return (k for k, v in ct.items() if v)

    @classmethod
    def build_positive_regex(cls, control_type:str) -> Pattern:
        """
        Creates a re.Pattern that will look for positive control types

        Returns:
            Pattern: Constructed pattern
        """
        strings = list(set([super_splitter(item, "-", 0) for item in cls.get_positive_control_types(control_type)]))
        return re.compile(rf"(^{'|^'.join(strings)})-.*", flags=re.IGNORECASE)


class Control(BaseClass):
    """
    Base class of a control sample.
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    controltype_name = Column(String, ForeignKey("_controltype.name", ondelete="SET NULL",
                                                 name="fk_BC_subtype_name"))  #: name of joined submission type
    controltype = relationship("ControlType", back_populates="instances",
                               foreign_keys=[controltype_name])  #: reference to parent control type
    name = Column(String(255), unique=True)  #: Sample ID
    submitted_date = Column(TIMESTAMP)  #: Date submitted to Robotics
    submission_id = Column(INTEGER, ForeignKey("_basicsubmission.id"))  #: parent submission id
    submission = relationship("BasicSubmission", back_populates="controls",
                              foreign_keys=[submission_id])  #: parent submission

    __mapper_args__ = {
        "polymorphic_identity": "Basic Control",
        "polymorphic_on": case(
            (controltype_name == "PCR Control", "PCR Control"),
            (controltype_name == "Irida Control", "Irida Control"),
            else_="Basic Control"
        ),
        "with_polymorphic": "*",
    }

    def __repr__(self) -> str:
        return f"<{self.controltype_name}({self.name})>"

    @classmethod
    @setup_lookup
    def query(cls,
              submission_type: str | None = None,
              subtype: str | None = None,
              start_date: date | str | int | None = None,
              end_date: date | str | int | None = None,
              name: str | None = None,
              limit: int = 0, **kwargs
              ) -> Control | List[Control]:
        """
        Lookup control objects in the database based on a number of parameters.

        Args:
            submission_type (str | None, optional): Submission type associated with control. Defaults to None.
            subtype (str | None, optional): Control subtype, eg IridaControl. Defaults to None.
            start_date (date | str | int | None, optional): Beginning date to search by. Defaults to 2023-01-01 if end_date not None.
            end_date (date | str | int | None, optional): End date to search by. Defaults to today if start_date not None.
            name (str | None, optional): Name of control. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            Control|List[Control]: Control object of interest.
        """
        from backend.db import SubmissionType
        query: Query = cls.__database_session__.query(cls)
        match submission_type:
            case str():
                from backend import BasicSubmission, SubmissionType
                # logger.debug(f"Lookup controls by SubmissionType str: {submission_type}")
                query = query.join(BasicSubmission).join(SubmissionType).filter(SubmissionType.name == submission_type)
            case SubmissionType():
                from backend import BasicSubmission
                # logger.debug(f"Lookup controls by SubmissionType: {submission_type}")
                query = query.join(BasicSubmission).filter(BasicSubmission.submission_type_name == submission_type.name)
            case _:
                pass
                # NOTE: by control type
        match subtype:
            case str():
                if cls.__name__ == "Control":
                    raise ValueError(f"Cannot query base class Control with subtype.")
                elif cls.__name__ == "IridaControl":
                    query = query.filter(cls.subtype == subtype)
                else:
                    try:
                        query = query.filter(cls.subtype == subtype)
                    except AttributeError as e:
                        logger.error(e)
            case _:
                pass
        # NOTE: by date range
        if start_date is not None and end_date is None:
            logger.warning(f"Start date with no end date, using today.")
            end_date = date.today()
        if end_date is not None and start_date is None:
            logger.warning(f"End date with no start date, using 90 days ago.")
            start_date = date.today() - timedelta(days=90)
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
        match name:
            case str():
                # logger.debug(f"Lookup control by name {control_name}")
                query = query.filter(cls.name.startswith(name))
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    @classmethod
    def find_polymorphic_subclass(cls, polymorphic_identity: str | ControlType | None = None,
                                  attrs: dict | None = None) -> Control:
        """
        Find subclass based on polymorphic identity or relevant attributes.

        Args:
            polymorphic_identity (str | None, optional): String representing polymorphic identity. Defaults to None.
            attrs (str | SubmissionType | None, optional): Attributes of the relevant class. Defaults to None.

        Returns:
            Control: Subclass of interest.
        """
        if isinstance(polymorphic_identity, dict):
            polymorphic_identity = polymorphic_identity['value']
        model = cls
        match polymorphic_identity:
            case str():
                try:
                    model = cls.__mapper__.polymorphic_map[polymorphic_identity].class_
                except Exception as e:
                    logger.error(
                        f"Could not get polymorph {polymorphic_identity} of {cls} due to {e}, falling back to BasicSubmission")
            case ControlType():
                try:
                    model = cls.__mapper__.polymorphic_map[polymorphic_identity.name].class_
                except Exception as e:
                    logger.error(
                        f"Could not get polymorph {polymorphic_identity} of {cls} due to {e}, falling back to BasicSubmission")
            case _:
                pass
        if attrs and any([not hasattr(cls, attr) for attr in attrs.keys()]):
            # NOTE: looks for first model that has all included kwargs
            try:
                model = next(subclass for subclass in cls.__subclasses__() if
                             all([hasattr(subclass, attr) for attr in attrs.keys()]))
            except StopIteration as e:
                raise AttributeError(
                    f"Couldn't find existing class/subclass of {cls} with all attributes:\n{pformat(attrs.keys())}")
        # logger.info(f"Recruiting model: {model}")
        return model

    @classmethod
    def make_parent_buttons(cls, parent: QWidget) -> None:
        """
        Super that will make buttons in a CustomFigure. Made to be overridden.
        
        Args:
            parent (QWidget): chart holding widget to add buttons to.
        """
        return None

    @classmethod
    def make_chart(cls, parent, chart_settings: dict, ctx) -> Tuple[Report, "CustomFigure" | None]:
        """
        Dummy operation to be overridden by child classes.

        Args:
            chart_settings (dict): settings passed down from chart widget
            ctx (Settings): settings passed down from gui
        """
        return None


class PCRControl(Control):
    """
    Class made to hold info from Design & Analysis software.
    """

    id = Column(INTEGER, ForeignKey('_control.id'), primary_key=True)
    subtype = Column(String(16))  #: PC or NC
    target = Column(String(16))  #: N1, N2, etc.
    ct = Column(FLOAT) #: PCR result
    reagent_lot = Column(String(64), ForeignKey("_reagent.name", ondelete="SET NULL",
                                                name="fk_reagent_lot"))
    reagent = relationship("Reagent", foreign_keys=reagent_lot) #: reagent used for this control

    __mapper_args__ = dict(polymorphic_identity="PCR Control",
                           polymorphic_load="inline",
                           inherit_condition=(id == Control.id))

    def to_sub_dict(self) -> dict:
        """
        Creates dictionary of fields for this object

        Returns:
            dict: Output dict of name, ct, subtype, target, reagent_lot and submitted_date
        """        
        return dict(name=self.name, ct=self.ct, subtype=self.subtype, target=self.target, reagent_lot=self.reagent_lot,
                    submitted_date=self.submitted_date.date())

    @classmethod
    @report_result
    def make_chart(cls, parent, chart_settings: dict, ctx: Settings) -> Tuple[Report, "PCRFigure"]:
        """
        Creates a PCRFigure. Overrides parent

        Args:
            parent (__type__): Widget to contain the chart.
            chart_settings (dict): settings passed down from chart widget
            ctx (Settings): settings passed down from gui. Not used here.

        Returns:
            Tuple[Report, "PCRFigure"]: Report of status and resulting figure.
        """        
        from frontend.visualizations.pcr_charts import PCRFigure
        parent.mode_typer.clear()
        parent.mode_typer.setEnabled(False)
        report = Report()
        # logger.debug(f"Chart settings: {pformat(chart_settings)}")
        controls = cls.query(submission_type=chart_settings['sub_type'], start_date=chart_settings['start_date'],
                             end_date=chart_settings['end_date'])
        data = [control.to_sub_dict() for control in controls]
        df = DataFrame.from_records(data)
        try:
            df = df[df.ct > 0.0]
        except AttributeError:
            df = df
        fig = PCRFigure(df=df, modes=[], settings=chart_settings)
        return report, fig

    def to_pydantic(self):
        from backend.validators import PydPCRControl
        return PydPCRControl(**self.to_sub_dict(), controltype_name=self.controltype_name, submission_id=self.submission_id)


class IridaControl(Control):

    subtyping_allowed = ['kraken']

    id = Column(INTEGER, ForeignKey('_control.id'), primary_key=True)
    contains = Column(JSON)  #: unstructured hashes in contains.tsv for each organism
    matches = Column(JSON)  #: unstructured hashes in matches.tsv for each organism
    kraken = Column(JSON)  #: unstructured output from kraken_report
    subtype = Column(String(16), nullable=False)  #: EN-NOS, MCS-NOS, etc
    refseq_version = Column(String(16))  #: version of refseq used in fastq parsing
    kraken2_version = Column(String(16))  #: version of kraken2 used in fastq parsing
    kraken2_db_version = Column(String(32))  #: folder name of kraken2 db
    sample = relationship("BacterialCultureSample", back_populates="control")  #: This control's submission sample
    sample_id = Column(INTEGER,
                       ForeignKey("_basicsample.id", ondelete="SET NULL", name="cont_BCS_id"))  #: sample id key
    
    __mapper_args__ = dict(polymorphic_identity="Irida Control",
                           polymorphic_load="inline",
                           inherit_condition=(id == Control.id))

    @validates("sub_type")
    def enforce_subtype_literals(self, key: str, value: str) -> str:
        """
        Validates sub_type field with acceptable values

        Args:
            key (str): Field name
            value (str): Field Value

        Raises:
            KeyError: Raised if value is not in the acceptable list.

        Returns:
            str: Validated string.
        """        
        acceptables = ['ATCC49226', 'ATCC49619', 'EN-NOS', "EN-SSTI", "MCS-NOS", "MCS-SSTI", "SN-NOS", "SN-SSTI"]
        if value.upper() not in acceptables:
            raise KeyError(f"Sub-type must be in {acceptables}")
        return value

    def to_sub_dict(self) -> dict:
        """
            Converts object into convenient dictionary for use in submission summary

            Returns:
                dict: output dictionary containing: Name, Type, Targets, Top Kraken results
            """
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
        output = dict(
            name=self.name,
            type=self.controltype.name,
            targets=", ".join(targets),
            kraken=new_kraken[0:10]
        )
        return output

    def convert_by_mode(self, control_sub_type: str, mode: Literal['kraken', 'matches', 'contains'],
                        consolidate: bool = False) -> Generator[dict, None, None]:
        """
        split this instance into analysis types ('kraken', 'matches', 'contains') for controls graphs

        Args:
            consolidate (bool): whether to merge all off-target genera. Defaults to False
            control_sub_type (str): control subtype, 'MCS-NOS', etc.
            mode (Literal['kraken', 'matches', 'contains']): analysis type, 'contains', etc.

        Returns:
            List[dict]: list of records
        """
        # logger.debug("load json string for mode (i.e. contains, matches, kraken2)")
        try:
            data = self.__getattribute__(mode)
        except TypeError:
            data = {}
        if data is None:
            data = {}
        # NOTE: Data truncation and consolidation.
        if "kraken" in mode:
            data = {k: v for k, v in sorted(data.items(), key=lambda d: d[1][f"{mode}_count"], reverse=True)[:50]}
        else:
            if consolidate:
                on_tar = {k: v for k, v in data.items() if k.strip("*") in self.controltype.targets[control_sub_type]}
                # logger.debug(f"Consolidating off-targets to: {self.controltype.targets[control_sub_type]}")
                off_tar = sum(v[f'{mode}_ratio'] for k, v in data.items() if
                              k.strip("*") not in self.controltype.targets[control_sub_type])
                on_tar['Off-target'] = {f"{mode}_ratio": off_tar}
                data = on_tar
        # logger.debug("dict keys are genera of bacteria, e.g. 'Streptococcus'")
        for genus in data:
            _dict = dict(
                name=self.name,
                submitted_date=self.submitted_date,
                genus=genus,
                target='Target' if genus.strip("*") in self.controltype.targets[control_sub_type] else "Off-target"
            )
            # logger.debug("get Target or Off-target of genus")
            for key in data[genus]:
                _dict[key] = data[genus][key]
            yield _dict

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
    def make_parent_buttons(cls, parent: QWidget) -> None:
        """

        Args:
            parent (QWidget): chart holding widget to add buttons to.

        """
        super().make_parent_buttons(parent=parent)
        rows = parent.layout.rowCount()
        # logger.debug(f"Parent rows: {rows}")
        checker = QCheckBox(parent)
        checker.setChecked(True)
        checker.setObjectName("irida_check")
        checker.setToolTip("Pools off-target genera to save time.")
        parent.layout.addWidget(QLabel("Consolidate Off-targets"), rows, 0, 1, 1)
        parent.layout.addWidget(checker, rows, 1, 1, 2)
        checker.checkStateChanged.connect(parent.controls_getter_function)

    @classmethod
    @report_result
    def make_chart(cls, chart_settings: dict, parent, ctx) -> Tuple[Report, "IridaFigure" | None]:
        """
        Creates a IridaFigure. Overrides parent

        Args:
            parent (__type__): Widget to contain the chart.
            chart_settings (dict): settings passed down from chart widget
            ctx (Settings): settings passed down from gui.

        Returns:
            Tuple[Report, "IridaFigure"]: Report of status and resulting figure.
        """        
        from frontend.visualizations import IridaFigure
        try:
            checker = parent.findChild(QCheckBox, name="irida_check")
            if chart_settings['mode'] == "kraken":
                checker.setEnabled(False)
                checker.setChecked(False)
            else:
                checker.setEnabled(True)
            consolidate = checker.isChecked()
        except AttributeError:
            consolidate = False
        report = Report()
        logger.debug(f"settings: {pformat(chart_settings)}")
        controls = cls.query(subtype=chart_settings['sub_type'], start_date=chart_settings['start_date'],
                             end_date=chart_settings['end_date'])
        # logger.debug(f"Controls found: {controls}")
        if not controls:
            report.add_result(Result(status="Critical", msg="No controls found in given date range."))
            return report, None
        # NOTE: change each control to list of dictionaries
        data = [control.convert_by_mode(control_sub_type=chart_settings['sub_type'], mode=chart_settings['mode'],
                                        consolidate=consolidate) for
                control in controls]
        # NOTE: flatten data to one dimensional list
        data = [item for sublist in data for item in sublist]
        # logger.debug(f"Control objects going into df conversion: {pformat(data)}")
        if not data:
            report.add_result(Result(status="Critical", msg="No data found for controls in given date range."))
            return report, None
        df = cls.convert_data_list_to_df(input_df=data, sub_mode=chart_settings['sub_mode'])
        # logger.debug(f"Chart df: \n {df}")
        if chart_settings['sub_mode'] is None:
            title = chart_settings['sub_mode']
        else:
            title = f"{chart_settings['mode']} - {chart_settings['sub_mode']}"
        # NOTE: send dataframe to chart maker
        df, modes = cls.prep_df(ctx=ctx, df=df)
        # logger.debug(f"prepped df: \n {df}")
        fig = IridaFigure(df=df, ytitle=title, modes=modes, parent=parent,
                          settings=chart_settings)
        return report, fig

    @classmethod
    def convert_data_list_to_df(cls, input_df: list[dict], sub_mode) -> DataFrame:
        """
        Convert list of control records to dataframe

        Args:
            input_df (list[dict]): list of dictionaries containing records
            sub_mode (str | None, optional): sub_type of submission type. Defaults to None.

        Returns:
            DataFrame: dataframe of controls
        """
        # logger.debug(f"Subtype: {sub_mode}")
        df = DataFrame.from_records(input_df)
        # logger.debug(f"DF from records: {df}")
        safe = ['name', 'submitted_date', 'genus', 'target']
        for column in df.columns:
            if column not in safe:
                if sub_mode is not None and column != sub_mode:
                    continue
                else:
                    safe.append(column)
            if "percent" in column:
                try:
                    count_col = next(item for item in df.columns if "count" in item)
                except StopIteration:
                    continue
                # NOTE: The actual percentage from kraken was off due to exclusion of NaN, recalculating.
                df[column] = 100 * df[count_col] / df.groupby('name')[count_col].transform('sum')
        df = df[[c for c in df.columns if c in safe]]
        # NOTE: move date of sample submitted on same date as previous ahead one.
        df = cls.displace_date(df=df)
        # NOTE: ad hoc method to make data labels more accurate.
        df = cls.df_column_renamer(df=df)
        return df

    @classmethod
    def df_column_renamer(cls, df: DataFrame) -> DataFrame:
        """
        Ad hoc function I created to clarify some fields

        Args:
            df (DataFrame): input dataframe

        Returns:
            DataFrame: dataframe with 'clarified' column names
        """
        df = df[df.columns.drop(list(df.filter(regex='_hashes')))]
        return df.rename(columns={
            "contains_ratio": "contains_shared_hashes_ratio",
            "matches_ratio": "matches_shared_hashes_ratio",
            "kraken_count": "kraken2_read_count_(top_50)",
            "kraken_percent": "kraken2_read_percent_(top_50)"
        })

    @classmethod
    def displace_date(cls, df: DataFrame) -> DataFrame:
        """
        This function serves to split samples that were submitted on the same date by incrementing dates.
        It will shift the date forward by one day if it is the same day as an existing date in a list.

        Args:
            df (DataFrame): input dataframe composed of control records

        Returns:
            DataFrame: output dataframe with dates incremented.
        """
        # logger.debug(f"Unique items: {df['name'].unique()}")
        # NOTE: get submitted dates for each control
        dict_list = [dict(name=item, date=df[df.name == item].iloc[0]['submitted_date']) for item in
                     sorted(df['name'].unique())]
        previous_dates = set()
        for item in dict_list:
            df, previous_dates = cls.check_date(df=df, item=item, previous_dates=previous_dates)
        return df

    @classmethod
    def check_date(cls, df: DataFrame, item: dict, previous_dates: set) -> Tuple[DataFrame, list]:
        """
        Checks if an items date is already present in df and adjusts df accordingly

        Args:
            df (DataFrame): input dataframe
            item (dict): control for checking
            previous_dates (list): list of dates found in previous controls

        Returns:
            Tuple[DataFrame, list]: Output dataframe and appended list of previous dates
        """
        try:
            check = item['date'] in previous_dates
        except IndexError:
            check = False
        previous_dates.add(item['date'])
        if check:
            # logger.debug(f"We found one! Increment date!\n\t{item['date']} to {item['date'] + timedelta(days=1)}")
            # NOTE: get df locations where name == item name
            mask = df['name'] == item['name']
            # NOTE: increment date in dataframe
            df.loc[mask, 'submitted_date'] = df.loc[mask, 'submitted_date'].apply(lambda x: x + timedelta(days=1))
            item['date'] += timedelta(days=1)
            passed = False
        else:
            passed = True
        # logger.debug(f"\n\tCurrent date: {item['date']}\n\tPrevious dates:{previous_dates}")
        # logger.debug(f"DF: {type(df)}, previous_dates: {type(previous_dates)}")
        # NOTE: if run didn't lead to changed date, return values
        if passed:
            # logger.debug(f"Date check passed, returning.")
            return df, previous_dates
        # NOTE: if date was changed, rerun with new date
        else:
            # logger.warning(f"Date check failed, running recursion")
            df, previous_dates = cls.check_date(df, item, previous_dates)
            return df, previous_dates

    @classmethod
    def prep_df(cls, ctx: Settings, df: DataFrame) -> Tuple[DataFrame | None, list]:
        """
        Constructs figures based on parsed pandas dataframe.

        Args:
            ctx (Settings): settings passed down from gui
            df (pd.DataFrame): input dataframe
            ytitle (str | None, optional): title for the y-axis. Defaults to None.

        Returns:
            Figure: Plotly figure
        """
        # NOTE: converts starred genera to normal and splits off list of starred
        if df.empty:
            return None, []
        df['genus'] = df['genus'].replace({'\*': ''}, regex=True).replace({"NaN": "Unknown"})
        df['genera'] = [item[-1] if item and item[-1] == "*" else "" for item in df['genus'].to_list()]
        # NOTE: remove original runs, using reruns if applicable
        df = cls.drop_reruns_from_df(ctx=ctx, df=df)
        # NOTE: sort by and exclude from
        sorts = ['submitted_date', "target", "genus"]
        exclude = ['name', 'genera']
        # logger.debug(df.columns)
        modes = [item for item in df.columns if item not in sorts and item not in exclude]
        # logger.debug(f"Modes coming out: {modes}")
        # NOTE: Set descending for any columns that have "{mode}" in the header.
        ascending = [False if item == "target" else True for item in sorts]
        df = df.sort_values(by=sorts, ascending=ascending)
        # logger.debug(df[df.isna().any(axis=1)])
        # NOTE: actual chart construction is done by
        return df, modes

    @classmethod
    def drop_reruns_from_df(cls, ctx: Settings, df: DataFrame) -> DataFrame:
        """
        Removes semi-duplicates from dataframe after finding sequencing repeats.

        Args:
            ctx (Settings): settings passed from gui
            df (DataFrame): initial dataframe

        Returns:
            DataFrame: dataframe with originals removed in favour of repeats.
        """
        if 'rerun_regex' in ctx:
            sample_names = get_unique_values_in_df_column(df, column_name="name")
            rerun_regex = re.compile(fr"{ctx.rerun_regex}")
            exclude = [re.sub(rerun_regex, "", sample) for sample in sample_names if rerun_regex.search(sample)]
            df = df[df.name not in exclude]
        return df

    def to_pydantic(self):
        from backend.validators import PydIridaControl
        return PydIridaControl(**self.__dict__)
