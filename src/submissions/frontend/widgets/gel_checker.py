"""
Gel box for artic quality control
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from PyQt6.QtWidgets import (
    QWidget, QGridLayout, QLabel, QTextEdit, QComboBox
)
from PyQt6.QtGui import QIcon
from PIL.ImageFile import ImageFile
from pyqtgraph import ImageView, setConfigOptions
from numpy import flip as npflip, rot90 as nprot90, array as nparray
from typing import Tuple, List


# Main window class
class GelBox(QWidget):

    def __init__(self, parent, img: ImageFile):
        super().__init__(parent)
        self.img = img
        # NOTE: setting geometry
        # self.setGeometry(50, 50, 1200, 900)
        self.UiComponents()
        # NOTE: showing all the widgets

    # method for components
    def UiComponents(self):
        """
        Create widgets in ui
        """
        # NOTE: setting configuration options
        setConfigOptions(antialias=True)
        # NOTE: creating image view object
        self.imv = ImageView()
        # NOTE: Create image.
        # NOTE: For some reason, ImageView wants to flip the image, so we have to rotate and flip the array first.
        # NOTE: Using the Image.rotate function results in cropped image, so using np.
        img = npflip(nprot90(nparray(self.img), 1), 0)
        self.imv.setImage(img)
        layout = QGridLayout()
        # # NOTE: setting this layout to the widget
        # # NOTE: plot window goes on right side, spanning 3 rows
        layout.addWidget(self.imv, 0, 1, 20, 20)
        # # NOTE: setting this widget as central widget of the main window
        self.setLayout(layout)

    
class ControlsForm(QWidget):

    def __init__(self, parent, control_info: List = None) -> None:
        super().__init__(parent)
        self.layout = QGridLayout()
        columns = []
        rows = []
        try:
            tt_text = "\n".join([f"{item['sample_id']} - CELL {item['well']}" for item in control_info])
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

__all__ = ["GelBox", "ControlsForm"]