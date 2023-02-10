# from datetime import date
from PyQt6.QtWidgets import (
    QLabel, QVBoxLayout, QDialog, 
    QDialogButtonBox, QMessageBox
)
# from PyQt6.QtCore import Qt, QDate, QSize
# from PyQt6.QtGui import QFontMetrics, QAction

# from backend.db import get_all_reagenttype_names, lookup_all_sample_types, create_kit_from_yaml
from jinja2 import Environment, FileSystemLoader
import sys
from pathlib import Path
import logging

logger = logging.getLogger(f"submissions.{__name__}")

if getattr(sys, 'frozen', False):
    loader_path = Path(sys._MEIPASS).joinpath("files", "templates")
else:
    loader_path = Path(__file__).parents[2].joinpath('templates').absolute().__str__()
loader = FileSystemLoader(loader_path)
env = Environment(loader=loader)


class AddReagentQuestion(QDialog):
    """
    dialog to ask about adding a new reagne to db
    """    
    def __init__(self, reagent_type:str, reagent_lot:str) -> QDialog:
        super().__init__()

        self.setWindowTitle(f"Add {reagent_lot}?")

        QBtn = QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.layout = QVBoxLayout()
        message = QLabel(f"Couldn't find reagent type {reagent_type.replace('_', ' ').title().strip('Lot')}: {reagent_lot} in the database.\n\nWould you like to add it?")
        self.layout.addWidget(message)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)


class OverwriteSubQuestion(QDialog):
    """
    dialog to ask about overwriting existing submission
    """    
    def __init__(self, message:str, rsl_plate_num:str) -> QDialog:
        super().__init__()

        self.setWindowTitle(f"Overwrite {rsl_plate_num}?")

        QBtn = QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.layout = QVBoxLayout()
        message = QLabel(message)
        self.layout.addWidget(message)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)


class AlertPop(QMessageBox):

    def __init__(self, message:str, status:str) -> QMessageBox:
        super().__init__()
        icon = getattr(QMessageBox.Icon, status.title())
        self.setIcon(icon)
        # msg.setText("Error")
        self.setInformativeText(message)
        self.setWindowTitle(status.title())

