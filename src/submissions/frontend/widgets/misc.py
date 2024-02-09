'''
Contains miscellaneous widgets for frontend functions
'''
from datetime import date
from PyQt6.QtWidgets import (
    QLabel, QVBoxLayout,
    QLineEdit, QComboBox, QDialog, 
    QDialogButtonBox, QDateEdit, QPushButton, QFormLayout
)
from PyQt6.QtCore import Qt, QDate
from tools import jinja_template_loading, Settings
from backend.db.models import *
import logging
from .pop_ups import AlertPop
from .functions import select_open_file
from tools import Settings

logger = logging.getLogger(f"submissions.{__name__}")

env = jinja_template_loading()

class AddReagentForm(QDialog):
    """
    dialog to add gather info about new reagent
    """    
    def __init__(self, reagent_lot:str|None=None, reagent_type:str|None=None, expiry:date|None=None, reagent_name:str|None=None) -> None:
        super().__init__()
        if reagent_lot == None:
            reagent_lot = reagent_type

        self.setWindowTitle("Add Reagent")

        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        # widget to get lot info
        self.name_input = QComboBox()
        self.name_input.setObjectName("name")
        self.name_input.setEditable(True)
        self.name_input.setCurrentText(reagent_name)
        self.lot_input = QLineEdit()
        self.lot_input.setObjectName("lot")
        self.lot_input.setText(reagent_lot)
        # widget to get expiry info
        self.exp_input = QDateEdit(calendarPopup=True)
        self.exp_input.setObjectName('expiry')
        # if expiry is not passed in from gui, use today
        if expiry == None:
            self.exp_input.setDate(QDate.currentDate())
        else:
            self.exp_input.setDate(expiry)
        # widget to get reagent type info
        self.type_input = QComboBox()
        self.type_input.setObjectName('type')
        self.type_input.addItems([item.name for item in ReagentType.query()])
        logger.debug(f"Trying to find index of {reagent_type}")
        # convert input to user friendly string?
        try:
            reagent_type = reagent_type.replace("_", " ").title()
        except AttributeError:
            reagent_type = None
        # set parsed reagent type to top of list
        index = self.type_input.findText(reagent_type, Qt.MatchFlag.MatchEndsWith)
        if index >= 0:
            self.type_input.setCurrentIndex(index)
        self.layout = QVBoxLayout()
        self.layout.addWidget(QLabel("Name:"))
        self.layout.addWidget(self.name_input)
        self.layout.addWidget(QLabel("Lot:"))
        self.layout.addWidget(self.lot_input)
        self.layout.addWidget(QLabel("Expiry:\n(use exact date on reagent.\nEOL will be calculated from kit automatically)"))
        self.layout.addWidget(self.exp_input)
        self.layout.addWidget(QLabel("Type:"))
        self.layout.addWidget(self.type_input)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)
        self.type_input.currentTextChanged.connect(self.update_names)

    def parse_form(self) -> dict:
        """
        Converts information in form to dict.

        Returns:
            dict: Output info
        """        
        return dict(name=self.name_input.currentText(), 
                    lot=self.lot_input.text(), 
                    expiry=self.exp_input.date().toPyDate(),
                    type=self.type_input.currentText())

    def update_names(self):
        """
        Updates reagent names form field with examples from reagent type
        """        
        logger.debug(self.type_input.currentText())
        self.name_input.clear()
        lookup = Reagent.query(reagent_type=self.type_input.currentText())
        self.name_input.addItems(list(set([item.name for item in lookup])))

class ReportDatePicker(QDialog):
    """
    custom dialog to ask for report start/stop dates
    """    
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Select Report Date Range")
        # make confirm/reject buttons
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        # widgets to ask for dates 
        self.start_date = QDateEdit(calendarPopup=True)
        self.start_date.setObjectName("start_date")
        self.start_date.setDate(QDate.currentDate())
        self.end_date = QDateEdit(calendarPopup=True)
        self.end_date.setObjectName("end_date")
        self.end_date.setDate(QDate.currentDate())
        self.layout = QVBoxLayout()
        self.layout.addWidget(QLabel("Start Date"))
        self.layout.addWidget(self.start_date)
        self.layout.addWidget(QLabel("End Date"))
        self.layout.addWidget(self.end_date)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)

    def parse_form(self) -> dict:
        """
        Converts information in this object to a dict

        Returns:
            dict: output dict.
        """        
        return dict(start_date=self.start_date.date().toPyDate(), end_date = self.end_date.date().toPyDate())

class FirstStrandSalvage(QDialog):

    def __init__(self, ctx:Settings, submitter_id:str, rsl_plate_num:str|None=None) -> None:
        super().__init__()
        if rsl_plate_num == None:
            rsl_plate_num = ""
        self.setWindowTitle("Add Reagent")

        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.submitter_id_input = QLineEdit()
        self.submitter_id_input.setText(submitter_id)
        self.rsl_plate_num = QLineEdit()
        self.rsl_plate_num.setText(rsl_plate_num)
        self.row_letter = QComboBox()
        self.row_letter.addItems(['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'])
        self.row_letter.setEditable(False)
        self.column_number = QComboBox()
        self.column_number.addItems(['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12'])
        self.column_number.setEditable(False)
        self.layout = QFormLayout()
        self.layout.addRow(self.tr("&Sample Number:"), self.submitter_id_input)
        self.layout.addRow(self.tr("&Plate Number:"), self.rsl_plate_num)
        self.layout.addRow(self.tr("&Source Row:"), self.row_letter)
        self.layout.addRow(self.tr("&Source Column:"), self.column_number)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)

    def parse_form(self) -> dict:
        """
        Pulls first strand info from form.

        Returns:
            dict: Output info
        """              
        return dict(plate=self.rsl_plate_num.text(), submitter_id=self.submitter_id_input.text(), well=f"{self.row_letter.currentText()}{self.column_number.currentText()}")

class LogParser(QDialog):

    def __init__(self, parent):
        super().__init__(parent)
        self.app = self.parent()
        self.filebutton = QPushButton(self)
        self.filebutton.setText("Import File")
        self.phrase_looker = QComboBox(self)
        self.phrase_looker.setEditable(True)
        self.btn = QPushButton(self)
        self.btn.setText("Search")
        self.layout = QFormLayout(self)
        self.layout.addRow(self.tr("&File:"), self.filebutton)
        self.layout.addRow(self.tr("&Search Term:"), self.phrase_looker)
        self.layout.addRow(self.btn)
        self.filebutton.clicked.connect(self.filelookup)
        self.btn.clicked.connect(self.runsearch)
        self.setMinimumWidth(400)


    def filelookup(self):
        """
        Select file to search
        """        
        self.fname = select_open_file(self, "tabular")

    def runsearch(self):
        """
        Gets total/percent occurences of string in tabular file.
        """        
        count: int = 0
        total: int = 0
        logger.debug(f"Current search term: {self.phrase_looker.currentText()}")
        try:
            with open(self.fname, "r") as f:
                for chunk in readInChunks(fileObj=f):
                    total += len(chunk)
                    for line in chunk:
                        if self.phrase_looker.currentText().lower() in line.lower():
                            count += 1
            percent = (count/total)*100
            msg = f"I found {count} instances of the search phrase out of {total} = {percent:.2f}%."
            status = "Information"
        except AttributeError:
            msg = f"No file was selected."
            status = "Error"
        dlg = AlertPop(message=msg, status=status)
        dlg.exec()

