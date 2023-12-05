'''
Contains dialogs for notification and prompting.
'''
from PyQt6.QtWidgets import (
    QLabel, QVBoxLayout, QDialog, 
    QDialogButtonBox, QMessageBox, QComboBox
)
from tools import jinja_template_loading
import logging
from backend.db.models import KitType, SubmissionType
from typing import Literal

logger = logging.getLogger(f"submissions.{__name__}")

env = jinja_template_loading()

class QuestionAsker(QDialog):
    """
    dialog to ask yes/no questions
    """    
    def __init__(self, title:str, message:str) -> QDialog:
        super().__init__()
        self.setWindowTitle(title)
        # set yes/no buttons
        QBtn = QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout = QVBoxLayout()
        # Text for the yes/no question
        self.message = QLabel(message)
        self.layout.addWidget(self.message)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)

class AlertPop(QMessageBox):
    """
    Dialog to show an alert.
    """    
    def __init__(self, message:str, status:Literal['Information', 'Question', 'Warning', 'Critical'], owner:str|None=None) -> QMessageBox:
        super().__init__()
        # select icon by string
        icon = getattr(QMessageBox.Icon, status)
        self.setIcon(icon)
        self.setInformativeText(message)
        self.setWindowTitle(f"{owner} - {status.title()}")

class KitSelector(QDialog):
    """
    dialog to ask yes/no questions
    """    
    def __init__(self, title:str, message:str) -> QDialog:
        super().__init__()
        self.setWindowTitle(title)
        self.widget = QComboBox()
        kits = [item.__str__() for item in KitType.query()]
        self.widget.addItems(kits)
        self.widget.setEditable(False)
        # set yes/no buttons
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout = QVBoxLayout()
        # Text for the yes/no question
        message = QLabel(message)
        self.layout.addWidget(message)
        self.layout.addWidget(self.widget)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)

    def getValues(self):
        return self.widget.currentText()

class SubmissionTypeSelector(QDialog):
    """
    dialog to ask yes/no questions
    """    
    def __init__(self, title:str, message:str) -> QDialog:
        super().__init__()
        self.setWindowTitle(title)
        self.widget = QComboBox()
        # sub_type = [item.name for item in lookup_submission_type(ctx=ctx)]
        sub_type = [item.name for item in SubmissionType.query()]
        self.widget.addItems(sub_type)
        self.widget.setEditable(False)
        # set yes/no buttons
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout = QVBoxLayout()
        # Text for the yes/no question
        message = QLabel(message)
        self.layout.addWidget(message)
        self.layout.addWidget(self.widget)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)

    def parse_form(self):
        return self.widget.currentText()
