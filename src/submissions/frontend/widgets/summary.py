"""
Pane to hold information e.g. cost summary.
"""
from .info_tab import InfoPane
from PyQt6.QtWidgets import QWidget, QLabel, QPushButton
from backend.db import Organization
from backend.excel import ReportMaker
from .misc import CheckableComboBox
import logging

logger = logging.getLogger(f"submissions.{__name__}")


class Summary(InfoPane):

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.save_excel_button = QPushButton("Save Excel", parent=self)
        self.save_excel_button.pressed.connect(self.save_excel)
        self.save_pdf_button = QPushButton("Save PDF", parent=self)
        self.save_pdf_button.pressed.connect(self.save_pdf)
        self.layout.addWidget(self.save_excel_button, 0, 2, 1, 1)
        self.layout.addWidget(self.save_pdf_button, 0, 3, 1, 1)
        self.org_select = CheckableComboBox()
        self.org_select.setEditable(False)
        self.org_select.addItem("Select", header=True)
        for org in [org.name for org in Organization.query()]:
            self.org_select.addItem(org)
        self.org_select.model().itemChanged.connect(self.update_data)
        self.layout.addWidget(QLabel("Client"), 1, 0, 1, 1)
        self.layout.addWidget(self.org_select, 1, 1, 1, 3)
        self.update_data()


    def update_data(self) -> None:
        """
        Sets data in the info pane

        Returns:
            None
        """
        super().update_data()
        orgs = [self.org_select.itemText(i) for i in range(self.org_select.count()) if self.org_select.itemChecked(i)]
        self.report_obj = ReportMaker(start_date=self.start_date, end_date=self.end_date, organizations=orgs)
        self.webview.setHtml(self.report_obj.html)
        if self.report_obj.subs:
            self.save_pdf_button.setEnabled(True)
            self.save_excel_button.setEnabled(True)
        else:
            self.save_pdf_button.setEnabled(False)
            self.save_excel_button.setEnabled(False)
