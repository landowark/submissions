"""
Contains miscellaneous widgets for frontend functions
"""
import math
from PyQt6.QtGui import QStandardItem, QIcon
from PyQt6.QtWidgets import (
    QLabel, QLineEdit, QComboBox, QDateEdit, QPushButton, QWidget,
    QHBoxLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QDate, QSize
from tools import jinja_template_loading
from backend.db.models import *
import logging

logger = logging.getLogger(f"submissions.{__name__}")

env = jinja_template_loading()


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


class CheckableComboBox(QComboBox):
    # once there is a checkState set, it is rendered
    # here we assume default Unchecked

    def addItem(self, item, header: bool = False, start_checked: bool = True):
        super(CheckableComboBox, self).addItem(item)
        item: QStandardItem = self.model().item(self.count() - 1, 0)
        if not header:
            item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            if start_checked:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)

    def itemChecked(self, index):
        item = self.model().item(index, 0)
        return item.checkState() == Qt.CheckState.Checked

    def changed(self):
        self.updated.emit()

    def get_checked(self):
        checked = [self.itemText(i) for i in range(self.count()) if self.itemChecked(i)]
        return checked


class Pagifier(QWidget):

    def __init__(self, page_max: int):
        super().__init__()
        self.page_max = math.ceil(page_max)
        self.page_anchor = 1
        next = QPushButton(parent=self, icon=QIcon.fromTheme(QIcon.ThemeIcon.GoNext))
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
