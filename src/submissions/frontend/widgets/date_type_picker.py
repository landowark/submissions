from PyQt6.QtWidgets import (
    QLabel, QVBoxLayout, QDialog,
    QDialogButtonBox, QMessageBox, QComboBox
)
from .misc import CheckableComboBox, StartEndDatePicker
from backend.db import SubmissionType


class DateTypePicker(QDialog):
    
    def __init__(self, parent):
        super().__init__(parent)
        self.layout = QVBoxLayout()
        self.setFixedWidth(500)
        self.typepicker = CheckableComboBox(parent=self)
        self.typepicker.setEditable(False)
        self.typepicker.addItem("Select", header=True)
        for org in [org.name for org in SubmissionType.query()]:
            self.typepicker.addItem(org)
        self.datepicker = StartEndDatePicker(-180)
        self.layout.addWidget(self.typepicker)
        self.layout.addWidget(self.datepicker)
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)

    def parse_form(self):
        sub_types = [self.typepicker.itemText(i) for i in range(self.typepicker.count()) if self.typepicker.itemChecked(i)]
        start_date = self.datepicker.start_date.date().toPyDate()
        end_date = self.datepicker.end_date.date().toPyDate()
        return dict(submissiontype=sub_types, start_date=start_date, end_date=end_date)


