from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea,
    QGridLayout, QPushButton, QLabel,
    QLineEdit, QSpinBox
)
from sqlalchemy.orm.attributes import InstrumentedAttribute
from backend.db import SubmissionType, BasicSubmission
import logging
from tools import Report
from .functions import select_open_file

logger = logging.getLogger(f"submissions.{__name__}")


class SubmissionTypeAdder(QWidget):

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.report = Report()
        self.app = parent.parent()
        self.template_path = ""
        main_box = QVBoxLayout(self)
        scroll = QScrollArea(self)
        main_box.addWidget(scroll)
        scroll.setWidgetResizable(True)    
        scrollContent = QWidget(scroll)
        self.grid = QGridLayout()
        scrollContent.setLayout(self.grid)
        # NOTE: insert submit button at top
        self.submit_btn = QPushButton("Submit")
        self.grid.addWidget(self.submit_btn,0,0,1,1)
        self.grid.addWidget(QLabel("Submission Type Name:"),2,0)
        # NOTE: widget to get kit name
        self.st_name = QLineEdit()
        self.st_name.setObjectName("submission_type_name")
        self.grid.addWidget(self.st_name,2,1,1,2)
        self.grid.addWidget(QLabel("Template File"),3,0)
        template_selector = QPushButton("Select")
        self.grid.addWidget(template_selector,3,1)
        self.template_label = QLabel("None")
        self.grid.addWidget(self.template_label,3,2)
        # NOTE: widget to get uses of kit
        exclude = ['id', 'submitting_lab_id', 'extraction_kit_id', 'reagents_id', 'extraction_info', 'pcr_info', 'run_cost']
        self.columns = {key:value for key, value in BasicSubmission.__dict__.items() if isinstance(value, InstrumentedAttribute)}
        self.columns = {key:value for key, value in self.columns.items() if hasattr(value, "type") and key not in exclude}
        for iii, key in enumerate(self.columns):
            idx = iii + 4
            self.grid.addWidget(InfoWidget(parent=self, key=key), idx,0,1,3)
        scroll.setWidget(scrollContent)
        self.submit_btn.clicked.connect(self.submit)
        template_selector.clicked.connect(self.get_template_path)

    def submit(self):
        """
        Create SubmissionType and send to db
        """        
        info = self.parse_form()
        ST = SubmissionType(name=self.st_name.text(), info_map=info)
        try:
            with open(self.template_path, "rb") as f:
                ST.template_file = f.read()
        except FileNotFoundError:
            logger.error(f"Could not find template file: {self.template_path}")
        ST.save(ctx=self.app.ctx)

    def parse_form(self) -> dict:
        """
        Pulls info from form

        Returns:
            dict: information from form
        """        
        widgets = [widget for widget in self.findChildren(QWidget) if isinstance(widget, InfoWidget)]
        return {widget.objectName():widget.parse_form() for widget in widgets}
    
    def get_template_path(self):
        """
        Sets path for loading a submission form template
        """        
        self.template_path = select_open_file(obj=self, file_extension="xlsx")
        self.template_label.setText(self.template_path.__str__())


class InfoWidget(QWidget):

    def __init__(self, parent: QWidget, key) -> None:
        super().__init__(parent)
        grid = QGridLayout()
        self.setLayout(grid)
        grid.addWidget(QLabel(key.replace("_", " ").title()),0,0,1,4)
        self.setObjectName(key)
        grid.addWidget(QLabel("Sheet Names (comma seperated):"),1,0)
        self.sheet = QLineEdit()
        self.sheet.setObjectName("sheets")
        grid.addWidget(self.sheet, 1,1,1,3)
        grid.addWidget(QLabel("Row:"),2,0,alignment=Qt.AlignmentFlag.AlignRight)
        self.row = QSpinBox()
        self.row.setObjectName("row")
        grid.addWidget(self.row,2,1)
        grid.addWidget(QLabel("Column:"),2,2,alignment=Qt.AlignmentFlag.AlignRight)
        self.column = QSpinBox()
        self.column.setObjectName("column")
        grid.addWidget(self.column,2,3)

    def parse_form(self) -> dict:
        """
        Pulls info from the Info form.

        Returns:
            dict: sheets, row, column
        """        
        return dict(
            sheets = self.sheet.text().split(","),
            row = self.row.value(),
            column = self.column.value()
        )