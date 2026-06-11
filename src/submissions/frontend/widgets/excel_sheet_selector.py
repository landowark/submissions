"""
Widget to select which sheet(s) to import from an Excel file. This is used in the Diomni Results page when importing from Excel, 
and allows the user to select which sheets to import if there are multiple sheets in the file.
"""

from PyQt6.QtWidgets import QVBoxLayout, QLabel, QDialogButtonBox, QDialog, QCheckBox
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet


class ExcelSheetSelector(QDialog):

    def __init__(self, workbook: Workbook, parent=None):
        super().__init__(parent)
        self.workbook = workbook
        self.setWindowTitle("Select Excel Sheet")
        self.setMinimumSize(300, 150)

        layout = QVBoxLayout()
        label = QLabel("Select the sheet to import:")
        layout.addWidget(label)

        for sheet_name in self.workbook.sheetnames:
            checkbox = QCheckBox(sheet_name, parent=self)
            layout.addWidget(checkbox)
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox)
        self.setLayout(layout)

    def get_selected_sheets(self) -> list[Worksheet]:
        selected_sheets = []
        for i in range(self.layout().count()):
            widget = self.layout().itemAt(i).widget()
            if isinstance(widget, QCheckBox) and widget.isChecked():
                sheet = self.workbook[widget.text()]
                selected_sheets.append(sheet)
        return selected_sheets
