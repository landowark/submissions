"""
Handles display of control charts
"""
import re
from datetime import timedelta
from typing import Tuple
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QComboBox, QHBoxLayout,
    QDateEdit, QLabel, QSizePolicy
)
from PyQt6.QtCore import QSignalBlocker
from backend.db import ControlType, Control
from PyQt6.QtCore import QDate, QSize
import logging
from pandas import DataFrame
from tools import Report, Result, get_unique_values_in_df_column, Settings, report_result
# from backend.excel.reports import convert_data_list_to_df
from frontend.visualizations.control_charts import CustomFigure

logger = logging.getLogger(f"submissions.{__name__}")

class ControlsViewer(QWidget):

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.app = self.parent().parent()
        # logger.debug(f"\n\n{self.app}\n\n")
        self.report = Report()
        self.datepicker = ControlsDatePicker()
        self.webengineview = QWebEngineView()
        # set tab2 layout
        self.layout = QVBoxLayout(self)
        self.control_typer = QComboBox()
        # NOTE: fetch types of controls
        con_types = [item.name for item in ControlType.query()]
        self.control_typer.addItems(con_types)
        # NOTE: create custom widget to get types of analysis
        self.mode_typer = QComboBox()
        mode_types = Control.get_modes()
        self.mode_typer.addItems(mode_types)
        # NOTE: create custom widget to get subtypes of analysis
        self.sub_typer = QComboBox()
        self.sub_typer.setEnabled(False)
        # NOTE: add widgets to tab2 layout
        self.layout.addWidget(self.datepicker)
        self.layout.addWidget(self.control_typer)
        self.layout.addWidget(self.mode_typer)
        self.layout.addWidget(self.sub_typer)
        self.layout.addWidget(self.webengineview)
        self.setLayout(self.layout)
        self.controls_getter()
        self.control_typer.currentIndexChanged.connect(self.controls_getter)
        self.mode_typer.currentIndexChanged.connect(self.controls_getter)
        self.datepicker.start_date.dateChanged.connect(self.controls_getter)
        self.datepicker.end_date.dateChanged.connect(self.controls_getter)

    def controls_getter(self):
        """
        Lookup controls from database and send to chartmaker
        """    
        self.controls_getter_function()

    @report_result
    def controls_getter_function(self):
        """
        Get controls based on start/end dates
        """    
        report = Report()
        # NOTE: subtype defaults to disabled  
        try:
            self.sub_typer.disconnect()
        except TypeError:
            pass
        # NOTE: correct start date being more recent than end date and rerun
        if self.datepicker.start_date.date() > self.datepicker.end_date.date():
            logger.warning("Start date after end date is not allowed!")
            threemonthsago = self.datepicker.end_date.date().addDays(-60)
            # NOTE: block signal that will rerun controls getter and set start date
            # Without triggering this function again
            with QSignalBlocker(self.datepicker.start_date) as blocker:
                self.datepicker.start_date.setDate(threemonthsago)
            self.controls_getter()
            self.report.add_result(report)
            return
        # NOTE: convert to python useable date objects
        self.start_date = self.datepicker.start_date.date().toPyDate()
        self.end_date = self.datepicker.end_date.date().toPyDate()
        self.con_type = self.control_typer.currentText()
        self.mode = self.mode_typer.currentText()
        self.sub_typer.clear()
        # NOTE: lookup subtypes
        try:
            sub_types = ControlType.query(name=self.con_type).get_subtypes(mode=self.mode)
        except AttributeError:
            sub_types = []
        if sub_types != []:
            # NOTE: block signal that will rerun controls getter and update sub_typer
            with QSignalBlocker(self.sub_typer) as blocker: 
                self.sub_typer.addItems(sub_types)
            self.sub_typer.setEnabled(True)
            self.sub_typer.currentTextChanged.connect(self.chart_maker)
        else:
            self.sub_typer.clear()
            self.sub_typer.setEnabled(False)
        self.chart_maker()
        return report

    def chart_maker(self):
        """
        Creates plotly charts for webview
        """   
        self.chart_maker_function()     

    @report_result
    def chart_maker_function(self):
        """
        Create html chart for controls reporting

        Args:
            obj (QMainWindow): original app window

        Returns:
            Tuple[QMainWindow, dict]: Collection of new main app window and result dict
        """    
        report = Report()
        # logger.debug(f"Control getter context: \n\tControl type: {self.con_type}\n\tMode: {self.mode}\n\tStart
        # Date: {self.start_date}\n\tEnd Date: {self.end_date}") NOTE: set the subtype for kraken
        if self.sub_typer.currentText() == "":
            self.subtype = None
        else:
            self.subtype = self.sub_typer.currentText()
        # logger.debug(f"Subtype: {self.subtype}")
        # NOTE: query all controls using the type/start and end dates from the gui
        controls = Control.query(control_type=self.con_type, start_date=self.start_date, end_date=self.end_date)
        # NOTE: if no data found from query set fig to none for reporting in webview
        if controls is None:
            fig = None
        else:
            # NOTE: change each control to list of dictionaries
            data = [control.convert_by_mode(mode=self.mode) for control in controls]
            # NOTE: flatten data to one dimensional list
            data = [item for sublist in data for item in sublist]
            # logger.debug(f"Control objects going into df conversion: {type(data)}")
            if not data:
                report.add_result(Result(status="Critical", msg="No data found for controls in given date range."))
                return
            # NOTE send to dataframe creator
            df = self.convert_data_list_to_df(input_df=data)
            if self.subtype is None:
                title = self.mode
            else:
                title = f"{self.mode} - {self.subtype}"
            # NOTE: send dataframe to chart maker
            df, modes = self.prep_df(ctx=self.app.ctx, df=df)
            fig = CustomFigure(df=df, ytitle=title, modes=modes)
        # logger.debug(f"Updating figure...")
        # NOTE: construct html for webview
        html = fig.to_html()
        # logger.debug(f"The length of html code is: {len(html)}")
        self.webengineview.setHtml(html)
        self.webengineview.update()
        # logger.debug("Figure updated... I hope.")
        return report

    def convert_data_list_to_df(self, input_df: list[dict]) -> DataFrame:
        """
        Convert list of control records to dataframe

        Args:
            ctx (dict): settings passed from gui
            input_df (list[dict]): list of dictionaries containing records
            subtype (str | None, optional): sub_type of submission type. Defaults to None.

        Returns:
            DataFrame: dataframe of controls
        """

        df = DataFrame.from_records(input_df)
        safe = ['name', 'submitted_date', 'genus', 'target']
        for column in df.columns:
            if "percent" in column:
                count_col = [item for item in df.columns if "count" in item][0]
                # NOTE: The actual percentage from kraken was off due to exclusion of NaN, recalculating.
                df[column] = 100 * df[count_col] / df.groupby('name')[count_col].transform('sum')
            if column not in safe:
                if self.subtype is not None and column != self.subtype:
                    del df[column]
        # NOTE: move date of sample submitted on same date as previous ahead one.
        df = self.displace_date(df=df)
        # NOTE: ad hoc method to make data labels more accurate.
        df = self.df_column_renamer(df=df)
        return df

    def df_column_renamer(self, df: DataFrame) -> DataFrame:
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

    def displace_date(self, df: DataFrame) -> DataFrame:
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
        previous_dates = []
        for _, item in enumerate(dict_list):
            df, previous_dates = self.check_date(df=df, item=item, previous_dates=previous_dates)
        return df

    def check_date(self, df: DataFrame, item: dict, previous_dates: list) -> Tuple[DataFrame, list]:
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
        previous_dates.append(item['date'])
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
            logger.warning(f"Date check failed, running recursion")
            df, previous_dates = self.check_date(df, item, previous_dates)
            return df, previous_dates

    def prep_df(self, ctx: Settings, df: DataFrame) -> DataFrame:
        """
        Constructs figures based on parsed pandas dataframe.

        Args:
            ctx (Settings): settings passed down from gui
            df (pd.DataFrame): input dataframe
            ytitle (str | None, optional): title for the y-axis. Defaults to None.

        Returns:
            Figure: Plotly figure
        """
        # from backend.excel import drop_reruns_from_df
        # converts starred genera to normal and splits off list of starred
        genera = []
        if df.empty:
            return None
        for item in df['genus'].to_list():
            try:
                if item[-1] == "*":
                    genera.append(item[-1])
                else:
                    genera.append("")
            except IndexError:
                genera.append("")
        df['genus'] = df['genus'].replace({'\*': ''}, regex=True).replace({"NaN": "Unknown"})
        df['genera'] = genera
        # NOTE: remove original runs, using reruns if applicable
        df = self.drop_reruns_from_df(ctx=ctx, df=df)
        # NOTE: sort by and exclude from
        sorts = ['submitted_date', "target", "genus"]
        exclude = ['name', 'genera']
        modes = [item for item in df.columns if item not in sorts and item not in exclude]  # and "_hashes" not in item]
        # NOTE: Set descending for any columns that have "{mode}" in the header.
        ascending = [False if item == "target" else True for item in sorts]
        df = df.sort_values(by=sorts, ascending=ascending)
        # logger.debug(df[df.isna().any(axis=1)])
        # NOTE: actual chart construction is done by
        return df, modes

    def drop_reruns_from_df(self, ctx: Settings, df: DataFrame) -> DataFrame:
        """
        Removes semi-duplicates from dataframe after finding sequencing repeats.

        Args:
            settings (dict): settings passed from gui
            df (DataFrame): initial dataframe

        Returns:
            DataFrame: dataframe with originals removed in favour of repeats.
        """
        if 'rerun_regex' in ctx:
            sample_names = get_unique_values_in_df_column(df, column_name="name")
            rerun_regex = re.compile(fr"{ctx.rerun_regex}")
            for sample in sample_names:
                if rerun_regex.search(sample):
                    first_run = re.sub(rerun_regex, "", sample)
                    df = df.drop(df[df.name == first_run].index)
        return df


class ControlsDatePicker(QWidget):
    """
    custom widget to pick start and end dates for controls graphs
    """    
    def __init__(self) -> None:
        super().__init__()
        self.start_date = QDateEdit(calendarPopup=True)
        # NOTE: start date is two months prior to end date by default
        twomonthsago = QDate.currentDate().addDays(-60)
        self.start_date.setDate(twomonthsago)
        self.end_date = QDateEdit(calendarPopup=True)
        self.end_date.setDate(QDate.currentDate())
        self.layout = QHBoxLayout()
        self.layout.addWidget(QLabel("Start Date"))
        self.layout.addWidget(self.start_date)
        self.layout.addWidget(QLabel("End Date"))
        self.layout.addWidget(self.end_date)
        self.setLayout(self.layout)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(80,20)  
