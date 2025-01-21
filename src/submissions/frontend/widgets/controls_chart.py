"""
Handles display of control charts
"""
from pprint import pformat
from PyQt6.QtWidgets import (
    QWidget, QComboBox, QPushButton
)
from PyQt6.QtCore import QSignalBlocker
from backend import ChartReportMaker
from backend.db import ControlType, IridaControl
import logging
from tools import Report, report_result
from frontend.visualizations import CustomFigure
from .info_tab import InfoPane

logger = logging.getLogger(f"submissions.{__name__}")


class ControlsViewer(InfoPane):

    def __init__(self, parent: QWidget, archetype: str) -> None:
        super().__init__(parent)
        self.archetype = ControlType.query(name=archetype)
        if not self.archetype:
            return
        # NOTE: set tab2 layout
        self.control_sub_typer = QComboBox()
        # NOTE: fetch types of controls
        con_sub_types = [item for item in self.archetype.targets.keys()]
        self.control_sub_typer.addItems(con_sub_types)
        # NOTE: create custom widget to get types of analysis -- disabled by PCR control
        self.mode_typer = QComboBox()
        self.mode_typer.addItems(IridaControl.modes)
        # NOTE: create custom widget to get subtypes of analysis -- disabled by PCR control
        self.mode_sub_typer = QComboBox()
        self.mode_sub_typer.setEnabled(False)
        # NOTE: add widgets to tab2 layout
        self.save_button = QPushButton("Save Chart", parent=self)
        self.layout.addWidget(self.save_button, 0, 2, 1, 1)
        self.export_button = QPushButton("Save Data", parent=self)
        self.layout.addWidget(self.export_button, 0, 3, 1, 1)
        self.layout.addWidget(self.control_sub_typer, 1, 0, 1, 4)
        self.layout.addWidget(self.mode_typer, 2, 0, 1, 4)
        self.layout.addWidget(self.mode_sub_typer, 3, 0, 1, 4)
        self.archetype.instance_class.make_parent_buttons(parent=self)
        self.update_data()
        self.control_sub_typer.currentIndexChanged.connect(self.update_data)
        self.mode_typer.currentIndexChanged.connect(self.update_data)
        self.save_button.pressed.connect(self.save_png)
        self.export_button.pressed.connect(self.save_excel)

    @report_result
    def update_data(self, *args, **kwargs):
        """
        Get controls based on start/end dates
        """
        super().update_data()
        # NOTE: mode_sub_type defaults to disabled
        try:
            self.mode_sub_typer.disconnect()
        except TypeError:
            pass
        self.con_sub_type = self.control_sub_typer.currentText()
        self.mode = self.mode_typer.currentText()
        self.mode_sub_typer.clear()
        # NOTE: lookup subtypes
        try:
            sub_types = self.archetype.get_modes(mode=self.mode)
        except AttributeError:
            sub_types = []
        # NOTE: added in allowed to have subtypes in case additions made in future.
        if sub_types and self.mode.lower() in self.archetype.instance_class.subtyping_allowed:
            # NOTE: block signal that will rerun controls getter and update mode_sub_typer
            with QSignalBlocker(self.mode_sub_typer) as blocker:
                self.mode_sub_typer.addItems(sub_types)
            self.mode_sub_typer.setEnabled(True)
            self.mode_sub_typer.currentTextChanged.connect(self.chart_maker_function)
        else:
            self.mode_sub_typer.clear()
            self.mode_sub_typer.setEnabled(False)
        self.chart_maker_function()

    @report_result
    def chart_maker_function(self, *args, **kwargs):
        """
        Create html chart for controls reporting

        Args:
            obj (QMainWindow): original app window

        Returns:
            Tuple[QMainWindow, dict]: Collection of new main app window and result dict
        """
        report = Report()
        # NOTE: set the mode_sub_type for kraken. Disabled in PCRControl
        if self.mode_sub_typer.currentText() == "":
            self.mode_sub_type = None
        else:
            self.mode_sub_type = self.mode_sub_typer.currentText()
        months = self.diff_month(self.start_date, self.end_date)
        # NOTE: query all controls using the type/start and end dates from the gui
        chart_settings = dict(
            sub_type=self.con_sub_type,
            start_date=self.start_date,
            end_date=self.end_date,
            mode=self.mode,
            sub_mode=self.mode_sub_type,
            parent=self,
            months=months
        )
        self.fig = self.archetype.instance_class.make_chart(chart_settings=chart_settings, parent=self, ctx=self.app.ctx)
        self.report_obj = ChartReportMaker(df=self.fig.df, sheet_name=self.archetype.name)
        if issubclass(self.fig.__class__, CustomFigure):
            self.save_button.setEnabled(True)
        # NOTE: construct html for webview
        # try:
        #     html = self.fig.html
        # except AttributeError:
        #     html = ""
        self.webview.setHtml(self.fig.html)
        self.webview.update()
        return report
