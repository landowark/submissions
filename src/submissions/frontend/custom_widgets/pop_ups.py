'''
Contains dialogs for notification and prompting.
'''
from PyQt6.QtWidgets import (
    QLabel, QVBoxLayout, QDialog, 
    QDialogButtonBox, QMessageBox
)
from jinja2 import Environment, FileSystemLoader
import sys
from pathlib import Path
import logging

logger = logging.getLogger(f"submissions.{__name__}")

# determine if pyinstaller launcher is being used
if getattr(sys, 'frozen', False):
    loader_path = Path(sys._MEIPASS).joinpath("files", "templates")
else:
    loader_path = Path(__file__).parents[2].joinpath('templates').absolute().__str__()
loader = FileSystemLoader(loader_path)
env = Environment(loader=loader)


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
        message = QLabel(message)
        self.layout.addWidget(message)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)

class AlertPop(QMessageBox):
    """
    Dialog to show an alert.
    """    
    def __init__(self, message:str, status:str) -> QMessageBox:
        super().__init__()
        # select icon by string
        icon = getattr(QMessageBox.Icon, status.title())
        self.setIcon(icon)
        self.setInformativeText(message)
        self.setWindowTitle(status.title())

