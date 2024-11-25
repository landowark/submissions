'''
Contains miscellaneous widgets for frontend functions
'''
import math
from datetime import date
from PyQt6.QtGui import QPageLayout, QPageSize, QStandardItem, QIcon
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QLabel, QVBoxLayout,
    QLineEdit, QComboBox, QDialog,
    QDialogButtonBox, QDateEdit, QPushButton, QFormLayout, QWidget, QHBoxLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QDate, QSize, QMarginsF
from tools import jinja_template_loading
from backend.db.models import *
import logging
from .pop_ups import AlertPop
from .functions import select_open_file

logger = logging.getLogger(f"submissions.{__name__}")

env = jinja_template_loading()


class AddReagentForm(QDialog):
    """
    dialog to add gather info about new reagent
    """

    def __init__(self, reagent_lot: str | None = None, reagent_role: str | None = None, expiry: date | None = None,
                 reagent_name: str | None = None, kit: str | KitType | None = None) -> None:
        super().__init__()
        if reagent_name is None:
            reagent_name = reagent_role
        self.setWindowTitle("Add Reagent")
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        # NOTE: widget to get lot info
        self.name_input = QComboBox()
        self.name_input.setObjectName("name")
        self.name_input.setEditable(True)
        self.name_input.setCurrentText(reagent_name)
        self.lot_input = QLineEdit()
        self.lot_input.setObjectName("lot")
        self.lot_input.setText(reagent_lot)
        # NOTE: widget to get expiry info
        self.exp_input = QDateEdit(calendarPopup=True)
        self.exp_input.setObjectName('expiry')
        # NOTE: if expiry is not passed in from gui, use today
        if expiry is None:
            self.exp_input.setDate(QDate(1970, 1, 1))
        else:
            try:
                self.exp_input.setDate(expiry)
            except TypeError:
                self.exp_input.setDate(QDate(1970, 1, 1))
        # NOTE: widget to get reagent type info
        self.type_input = QComboBox()
        self.type_input.setObjectName('role')
        if kit:
            match kit:
                case str():
                    kit = KitType.query(name=kit)
                case _:
                    pass
            self.type_input.addItems([item.name for item in ReagentRole.query() if kit in item.kit_types])
        else:
            self.type_input.addItems([item.name for item in ReagentRole.query()])
        # logger.debug(f"Trying to find index of {reagent_type}")
        # NOTE: convert input to user-friendly string?
        try:
            reagent_role = reagent_role.replace("_", " ").title()
        except AttributeError:
            reagent_role = None
        # NOTE: set parsed reagent type to top of list
        index = self.type_input.findText(reagent_role, Qt.MatchFlag.MatchEndsWith)
        if index >= 0:
            self.type_input.setCurrentIndex(index)
        self.layout = QVBoxLayout()
        self.layout.addWidget(QLabel("Name:"))
        self.layout.addWidget(self.name_input)
        self.layout.addWidget(QLabel("Lot:"))
        self.layout.addWidget(self.lot_input)
        self.layout.addWidget(
            QLabel("Expiry:\n(use exact date on reagent.\nEOL will be calculated from kit automatically)"))
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
        return dict(name=self.name_input.currentText().strip(),
                    lot=self.lot_input.text().strip(),
                    expiry=self.exp_input.date().toPyDate(),
                    role=self.type_input.currentText().strip())

    def update_names(self):
        """
        Updates reagent names form field with examples from reagent type
        """
        # logger.debug(self.type_input.currentText())
        self.name_input.clear()
        lookup = Reagent.query(role=self.type_input.currentText())
        self.name_input.addItems(list(set([item.name for item in lookup])))


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
        # logger.debug(f"Current search term: {self.phrase_looker.currentText()}")
        try:
            with open(self.fname, "r") as f:
                for chunk in readInChunks(fileObj=f):
                    total += len(chunk)
                    for line in chunk:
                        if self.phrase_looker.currentText().lower() in line.lower():
                            count += 1
            percent = (count / total) * 100
            msg = f"I found {count} instances of the search phrase out of {total} = {percent:.2f}%."
            status = "Information"
        except AttributeError:
            msg = f"No file was selected."
            status = "Error"
        dlg = AlertPop(message=msg, status=status)
        dlg.exec()


class StartEndDatePicker(QWidget):
    """
    custom widget to pick start and end dates for controls graphs
    """

    def __init__(self, default_start: int) -> None:
        super().__init__()
        self.start_date = QDateEdit(calendarPopup=True)
        # NOTE: start date is two months prior to end date by default
        default_start = QDate.currentDate().addDays(default_start)
        self.start_date.setDate(default_start)
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
        return QSize(80, 20)


def save_pdf(obj: QWebEngineView, filename: Path):
    page_layout = QPageLayout()
    page_layout.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    page_layout.setOrientation(QPageLayout.Orientation.Portrait)
    page_layout.setMargins(QMarginsF(25, 25, 25, 25))
    obj.page().printToPdf(filename.absolute().__str__(), page_layout)


# subclass
class CheckableComboBox(QComboBox):
    # once there is a checkState set, it is rendered
    # here we assume default Unchecked

    def addItem(self, item, header: bool = False):
        super(CheckableComboBox, self).addItem(item)
        item: QStandardItem = self.model().item(self.count() - 1, 0)
        if not header:
            item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            item.setCheckState(Qt.CheckState.Checked)

    def itemChecked(self, index):
        item = self.model().item(index, 0)
        return item.checkState() == Qt.CheckState.Checked

    def changed(self):
        logger.debug("emitting updated")
        self.updated.emit()


class Pagifier(QWidget):

    def __init__(self, page_max:int):
        super().__init__()
        self.page_max = math.ceil(page_max)
        self.page_anchor = 1
        next = QPushButton(parent=self, icon = QIcon.fromTheme(QIcon.ThemeIcon.GoNext))
        next.pressed.connect(self.increment_page)
        previous = QPushButton(parent=self, icon=QIcon.fromTheme(QIcon.ThemeIcon.GoPrevious))
        previous.pressed.connect(self.decrement_page)
        self.current_page = QLineEdit(self)
        self.current_page.setEnabled(False)
        self.update_current_page()
        self.current_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout = QHBoxLayout()
        self.layout.addWidget(previous)
        self.layout.addWidget(self.current_page)
        self.layout.addWidget(next)
        self.setLayout(self.layout)

    def increment_page(self):
        new = self.page_anchor + 1
        if new <= self.page_max:
            self.page_anchor = new
        self.update_current_page()

    def decrement_page(self):
        new = self.page_anchor - 1
        if new >= 1:
            self.page_anchor = new
        self.update_current_page()

    def update_current_page(self):
        self.current_page.setText(f"{self.page_anchor} of {self.page_max}")
