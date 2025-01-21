"""
Contains miscellaneous widgets for frontend functions
"""
import math
from datetime import date
from PyQt6.QtGui import QStandardItem, QIcon
from PyQt6.QtWidgets import (
    QLabel, QLineEdit, QComboBox, QDateEdit, QPushButton, QWidget,
    QHBoxLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QDate, QSize, QMarginsF
from tools import jinja_template_loading
from backend.db.models import *
import logging

logger = logging.getLogger(f"submissions.{__name__}")

env = jinja_template_loading()


# class AddReagentForm(QDialog):
#     """
#     dialog to add gather info about new reagent (Defunct)
#     """
#
#     def __init__(self, reagent_lot: str | None = None, reagent_role: str | None = None, expiry: date | None = None,
#                  reagent_name: str | None = None, kit: str | KitType | None = None) -> None:
#         super().__init__()
#         if reagent_name is None:
#             reagent_name = reagent_role
#         self.setWindowTitle("Add Reagent")
#         QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
#         self.buttonBox = QDialogButtonBox(QBtn)
#         self.buttonBox.accepted.connect(self.accept)
#         self.buttonBox.rejected.connect(self.reject)
#         # NOTE: widget to get lot info
#         self.name_input = QComboBox()
#         self.name_input.setObjectName("name")
#         self.name_input.setEditable(True)
#         self.name_input.setCurrentText(reagent_name)
#         self.lot_input = QLineEdit()
#         self.lot_input.setObjectName("lot")
#         self.lot_input.setText(reagent_lot)
#         # NOTE: widget to get expiry info
#         self.expiry_input = QDateEdit(calendarPopup=True)
#         self.expiry_input.setObjectName('expiry')
#         # NOTE: if expiry is not passed in from gui, use today
#         if expiry is None:
#             logger.warning(f"Did not receive expiry, setting to 1970, 1, 1")
#             self.expiry_input.setDate(QDate(1970, 1, 1))
#         else:
#             try:
#                 self.expiry_input.setDate(expiry)
#             except TypeError:
#                 self.expiry_input.setDate(QDate(1970, 1, 1))
#         # NOTE: widget to get reagent type info
#         self.role_input = QComboBox()
#         self.role_input.setObjectName('role')
#         if kit:
#             match kit:
#                 case str():
#                     kit = KitType.query(name=kit)
#                 case _:
#                     pass
#             self.role_input.addItems([item.name for item in ReagentRole.query() if kit in item.kit_types])
#         else:
#             self.role_input.addItems([item.name for item in ReagentRole.query()])
#         # NOTE: convert input to user-friendly string?
#         try:
#             reagent_role = reagent_role.replace("_", " ").title()
#         except AttributeError:
#             reagent_role = None
#         # NOTE: set parsed reagent type to top of list
#         index = self.role_input.findText(reagent_role, Qt.MatchFlag.MatchEndsWith)
#         if index >= 0:
#             self.role_input.setCurrentIndex(index)
#         self.layout = QVBoxLayout()
#         self.layout.addWidget(QLabel("Name:"))
#         self.layout.addWidget(self.name_input)
#         self.layout.addWidget(QLabel("Lot:"))
#         self.layout.addWidget(self.lot_input)
#         self.layout.addWidget(
#             QLabel("Expiry:\n(use exact date on reagent.\nEOL will be calculated from kit automatically)")
#         )
#         self.layout.addWidget(self.expiry_input)
#         self.layout.addWidget(QLabel("Type:"))
#         self.layout.addWidget(self.role_input)
#         self.layout.addWidget(self.buttonBox)
#         self.setLayout(self.layout)
#         self.role_input.currentTextChanged.connect(self.update_names)
#
#     def parse_form(self) -> dict:
#         """
#         Converts information in form to dict.
#
#         Returns:
#             dict: Output info
#         """
#         return dict(name=self.name_input.currentText().strip(),
#                     lot=self.lot_input.text().strip(),
#                     expiry=self.expiry_input.date().toPyDate(),
#                     role=self.role_input.currentText().strip())
#
#     def update_names(self):
#         """
#         Updates reagent names form field with examples from reagent type
#         """
#         self.name_input.clear()
#         lookup = Reagent.query(role=self.role_input.currentText())
#         self.name_input.addItems(list(set([item.name for item in lookup])))
#
#
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


# def save_pdf(obj: QWebEngineView, filename: Path):
#     page_layout = QPageLayout()
#     page_layout.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
#     page_layout.setOrientation(QPageLayout.Orientation.Portrait)
#     page_layout.setMargins(QMarginsF(25, 25, 25, 25))
#     obj.page().printToPdf(filename.absolute().__str__(), page_layout)


# NOTE: subclass

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
