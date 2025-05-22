"""
Gel box for artic quality control
"""
from operator import itemgetter
from PyQt6.QtWidgets import (
    QWidget, QDialog, QGridLayout, QLabel, QLineEdit, QDialogButtonBox, QTextEdit, QComboBox
)
import pyqtgraph as pg
from PyQt6.QtGui import QIcon
from PIL import Image
import logging, numpy as np
from pprint import pformat
from typing import Tuple, List
from pathlib import Path
from backend.db.models import Run

logger = logging.getLogger(f"submissions.{__name__}")


# Main window class
class GelBox(QDialog):

    def __init__(self, parent, img_path: str | Path, submission: Run):
        super().__init__(parent)
        # NOTE: setting title
        self.setWindowTitle(f"Gel - {img_path}")
        self.img_path = img_path
        self.submission = submission
        # NOTE: setting geometry
        self.setGeometry(50, 50, 1200, 900)
        # NOTE: icon
        icon = QIcon("skin.png")
        # NOTE: setting icon to the window
        self.setWindowIcon(icon)
        # NOTE: calling method
        self.UiComponents()
        # NOTE: showing all the widgets

    # method for components
    def UiComponents(self):
        """
        Create widgets in ui
        """
        # NOTE: setting configuration options
        pg.setConfigOptions(antialias=True)
        # NOTE: creating image view object
        self.imv = pg.ImageView()
        # NOTE: Create image.
        # NOTE: For some reason, ImageView wants to flip the image, so we have to rotate and flip the array first.
        # NOTE: Using the Image.rotate function results in cropped image, so using np.
        img = np.flip(np.rot90(np.array(Image.open(self.img_path)), 1), 0)
        self.imv.setImage(img)
        layout = QGridLayout()
        layout.addWidget(QLabel("DNA Core Submission Number"), 21, 1)
        self.core_number = QLineEdit()
        self.core_number.setText(self.submission.dna_core_submission_number)
        layout.addWidget(self.core_number, 21, 2)
        layout.addWidget(QLabel("Gel Barcode"), 21, 3)
        self.gel_barcode = QLineEdit()
        self.gel_barcode.setText(self.submission.gel_barcode)
        layout.addWidget(self.gel_barcode, 21, 4)
        # NOTE: setting this layout to the widget
        # NOTE: plot window goes on right side, spanning 3 rows
        layout.addWidget(self.imv, 0, 1, 20, 20)
        # NOTE: setting this widget as central widget of the main window
        try:
            control_info = sorted(self.submission.gel_controls, key=itemgetter('location'))
        except KeyError:
            control_info = None
        self.form = ControlsForm(parent=self, control_info=control_info)
        layout.addWidget(self.form, 22, 1, 1, 4)
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox, 23, 1, 1, 1)
        self.setLayout(layout)

    def parse_form(self) -> Tuple[str, str | Path, list]:
        """
        Get relevant values from self/form

        Returns:
            Tuple[str, str|Path, list]: output values
        """
        dna_core_submission_number = self.core_number.text()
        gel_barcode = self.gel_barcode.text()
        values, comment = self.form.parse_form()
        return dna_core_submission_number, gel_barcode, self.img_path, values, comment


class ControlsForm(QWidget):

    def __init__(self, parent, control_info: List = None) -> None:
        super().__init__(parent)
        self.layout = QGridLayout()
        columns = []
        rows = []
        try:
            tt_text = "\n".join([f"{item['sample_id']} - CELL {item['location']}" for item in control_info])
        except TypeError:
            tt_text = None
        for iii, item in enumerate(
                ["Negative Control Key", "Description", "Results - 65 C", "Results - 63 C", "Results - Spike"]
        ):
            label = QLabel(item)
            self.layout.addWidget(label, 0, iii, 1, 1)
            if iii > 1:
                columns.append(item)
            elif iii == 0:
                if tt_text:
                    label.setStyleSheet("font-weight: bold; color: blue; text-decoration: underline;")
                    label.setToolTip(tt_text)
        for iii, item in enumerate(["RSL-NTC", "ENC-NTC", "NTC"], start=1):
            label = QLabel(item)
            self.layout.addWidget(label, iii, 0, 1, 1)
            rows.append(item)
        for iii, item in enumerate(["Processing Negative (PBS)", "Extraction Negative (Extraction buffers ONLY)",
                                    "Artic no-template control (mastermix ONLY)"], start=1):
            label = QLabel(item)
            self.layout.addWidget(label, iii, 1, 1, 1)
        for iii in range(3):
            for jjj in range(3):
                widge = QComboBox()
                widge.addItems(['Neg', 'Pos'])
                widge.setCurrentIndex(0)
                widge.setEditable(True)
                widge.setObjectName(f"{rows[iii]} : {columns[jjj]}")
                self.layout.addWidget(widge, iii + 1, jjj + 2, 1, 1)
        self.layout.addWidget(QLabel("Comments:"), 0, 5, 1, 1)
        self.comment_field = QTextEdit(self)
        self.comment_field.setFixedHeight(50)
        self.layout.addWidget(self.comment_field, 1, 5, 4, 1)
        self.setLayout(self.layout)

    def parse_form(self) -> Tuple[List[dict], str]:
        """
        Pulls the control statuses from the form.

        Returns:
            List[dict]: output of values
        """
        output = []
        for le in self.findChildren(QComboBox):
            label = [item.strip() for item in le.objectName().split(" : ")]
            dicto = next((item for item in output if item['name'] == label[0]), dict(name=label[0], values=[]))
            dicto['values'].append(dict(name=label[1], value=le.currentText()))
            if label[0] not in [item['name'] for item in output]:
                output.append(dicto)
        return output, self.comment_field.toPlainText()
