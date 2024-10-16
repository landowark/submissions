"""
Handles display of control charts
"""
import re
import sys
from datetime import timedelta, date
from pprint import pformat
from typing import Tuple
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QComboBox, QHBoxLayout,
    QDateEdit, QLabel, QSizePolicy, QPushButton, QGridLayout
)
from PyQt6.QtCore import QSignalBlocker
from backend.db import ControlType, IridaControl
from PyQt6.QtCore import QDate, QSize
import logging
from pandas import DataFrame
from tools import Report, Result, get_unique_values_in_df_column, Settings, report_result
from frontend.visualizations import IridaFigure, PCRFigure
from .misc import StartEndDatePicker

logger = logging.getLogger(f"submissions.{__name__}")


class ControlsViewer(QWidget):

    def __init__(self, parent: QWidget, archetype: str) -> None:
        super().__init__(parent)
        logger.debug(f"Incoming Archetype: {archetype}")
        self.archetype = ControlType.query(name=archetype)
        if not self.archetype:
            return
        logger.debug(f"Archetype set as: {self.archetype}")
        self.app = self.parent().parent()
        # logger.debug(f"\n\n{self.app}\n\n")
        self.report = Report()
        self.datepicker = StartEndDatePicker(default_start=-180)
        self.webengineview = QWebEngineView()
        # NOTE: set tab2 layout
        self.layout = QGridLayout(self)
        self.control_sub_typer = QComboBox()
        # NOTE: fetch types of controls
        con_sub_types = [item for item in self.archetype.targets.keys()]
        self.control_sub_typer.addItems(con_sub_types)
        # NOTE: create custom widget to get types of analysis
        self.mode_typer = QComboBox()
        mode_types = IridaControl.get_modes()
        self.mode_typer.addItems(mode_types)
        # NOTE: create custom widget to get subtypes of analysis
        self.mode_sub_typer = QComboBox()
        self.mode_sub_typer.setEnabled(False)
        # NOTE: add widgets to tab2 layout
        self.layout.addWidget(self.datepicker, 0, 0, 1, 2)
        self.save_button = QPushButton("Save Chart", parent=self)
        self.layout.addWidget(self.save_button, 0, 2, 1, 1)
        self.layout.addWidget(self.control_sub_typer, 1, 0, 1, 3)
        self.layout.addWidget(self.mode_typer, 2, 0, 1, 3)
        self.layout.addWidget(self.mode_sub_typer, 3, 0, 1, 3)
        self.archetype.get_instance_class().make_parent_buttons(parent=self)
        self.layout.addWidget(self.webengineview, self.layout.rowCount(), 0, 1, 3)
        self.setLayout(self.layout)
        self.controls_getter_function()
        self.control_sub_typer.currentIndexChanged.connect(self.controls_getter_function)
        self.mode_typer.currentIndexChanged.connect(self.controls_getter_function)
        self.datepicker.start_date.dateChanged.connect(self.controls_getter_function)
        self.datepicker.end_date.dateChanged.connect(self.controls_getter_function)
        self.save_button.pressed.connect(self.save_chart_function)


    def save_chart_function(self):
        self.fig.save_figure(parent=self)

    # def controls_getter(self):
    #     """
    #     Lookup controls from database and send to chartmaker
    #     """
    #     self.controls_getter_function()

    @report_result
    def controls_getter_function(self, *args, **kwargs):
        """
        Get controls based on start/end dates
        """
        report = Report()
        # NOTE: mode_sub_type defaults to disabled
        try:
            self.mode_sub_typer.disconnect()
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
        self.con_sub_type = self.control_sub_typer.currentText()
        self.mode = self.mode_typer.currentText()
        self.mode_sub_typer.clear()
        # NOTE: lookup subtypes
        try:
            sub_types = self.archetype.get_modes(mode=self.mode)
        except AttributeError:
            sub_types = []
        if sub_types:
            # NOTE: block signal that will rerun controls getter and update mode_sub_typer
            with QSignalBlocker(self.mode_sub_typer) as blocker:
                self.mode_sub_typer.addItems(sub_types)
            self.mode_sub_typer.setEnabled(True)
            self.mode_sub_typer.currentTextChanged.connect(self.chart_maker_function)
        else:
            self.mode_sub_typer.clear()
            self.mode_sub_typer.setEnabled(False)
        self.chart_maker_function()
        return report

    def diff_month(self, d1: date, d2: date):
        return abs((d1.year - d2.year) * 12 + d1.month - d2.month)

    @report_result
    def chart_maker_function(self, *args, **kwargs):
        # TODO: Generalize this by moving as much code as possible to IridaControl
        """
        Create html chart for controls reporting

        Args:
            obj (QMainWindow): original app window

        Returns:
            Tuple[QMainWindow, dict]: Collection of new main app window and result dict
        """
        report = Report()
        # logger.debug(f"Control getter context: \n\tControl type: {self.con_sub_type}\n\tMode: {self.mode}\n\tStart \
        #     Date: {self.start_date}\n\tEnd Date: {self.end_date}")
        # NOTE: set the mode_sub_type for kraken
        if self.mode_sub_typer.currentText() == "":
            self.mode_sub_type = None
        else:
            self.mode_sub_type = self.mode_sub_typer.currentText()
        logger.debug(f"Subtype: {self.mode_sub_type}")
        months = self.diff_month(self.start_date, self.end_date)
        # NOTE: query all controls using the type/start and end dates from the gui
        chart_settings = dict(sub_type=self.con_sub_type, start_date=self.start_date, end_date=self.end_date,
                              mode=self.mode,
                              sub_mode=self.mode_sub_type, parent=self, months=months)
        _, self.fig = self.archetype.get_instance_class().make_chart(chart_settings=chart_settings, parent=self, ctx=self.app.ctx)
        # if isinstance(self.fig, IridaFigure):
        #     self.save_button.setEnabled(True)
        # logger.debug(f"Updating figure...")
        # self.fig = fig
        # NOTE: construct html for webview
        html = self.fig.to_html()
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
            mode_sub_type (str | None, optional): sub_type of submission type. Defaults to None.

        Returns:
            DataFrame: dataframe of controls
        """

        df = DataFrame.from_records(input_df)
        safe = ['name', 'submitted_date', 'genus', 'target']
        for column in df.columns:
            if column not in safe:
                if self.mode_sub_type is not None and column != self.mode_sub_type:
                    continue
                else:
                    safe.append(column)
            if "percent" in column:
                # count_col = [item for item in df.columns if "count" in item][0]
                try:
                    count_col = next(item for item in df.columns if "count" in item)
                except StopIteration:
                    continue
                # NOTE: The actual percentage from kraken was off due to exclusion of NaN, recalculating.
                df[column] = 100 * df[count_col] / df.groupby('name')[count_col].transform('sum')
        df = df[[c for c in df.columns if c in safe]]
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
        previous_dates = set()
        # for _, item in enumerate(dict_list):
        for item in dict_list:
            df, previous_dates = self.check_date(df=df, item=item, previous_dates=previous_dates)
        return df

    def check_date(self, df: DataFrame, item: dict, previous_dates: set) -> Tuple[DataFrame, list]:
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
            logger.warning(f"Date check failed, running recursion")
            df, previous_dates = self.check_date(df, item, previous_dates)
            return df, previous_dates

    def prep_df(self, ctx: Settings, df: DataFrame) -> Tuple[DataFrame, list]:
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
            return None
        df['genus'] = df['genus'].replace({'\*': ''}, regex=True).replace({"NaN": "Unknown"})
        df['genera'] = [item[-1] if item and item[-1] == "*" else "" for item in df['genus'].to_list()]
        # NOTE: remove original runs, using reruns if applicable
        df = self.drop_reruns_from_df(ctx=ctx, df=df)
        # NOTE: sort by and exclude from
        sorts = ['submitted_date', "target", "genus"]
        exclude = ['name', 'genera']
        modes = [item for item in df.columns if item not in sorts and item not in exclude]
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
            exclude = [re.sub(rerun_regex, "", sample) for sample in sample_names if rerun_regex.search(sample)]
            df = df[df.name not in exclude]
        return df
