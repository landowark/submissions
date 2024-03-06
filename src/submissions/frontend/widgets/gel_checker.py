"""
Gel box for artic quality control
"""
from PyQt6.QtWidgets import (QWidget, QDialog, QGridLayout,
                             QLabel, QLineEdit, QDialogButtonBox,
                             QTextEdit
                             )
import numpy as np
import pyqtgraph as pg
from PyQt6.QtGui import QIcon
from PIL import Image
import numpy as np
import logging
from pprint import pformat
from typing import Tuple, List
from pathlib import Path

logger = logging.getLogger(f"submissions.{__name__}")

# Main window class
class GelBox(QDialog):

    def __init__(self, parent, img_path:str|Path):
        super().__init__(parent)
        # setting title
        self.setWindowTitle("PyQtGraph")
        self.img_path = img_path
        # setting geometry
        self.setGeometry(50, 50, 1200, 900)
        # icon
        icon = QIcon("skin.png")
        # setting icon to the window
        self.setWindowIcon(icon)
        # calling method
        self.UiComponents()
        # showing all the widgets

    # method for components
    def UiComponents(self):
        """
        Create widgets in ui
        """        
        # setting configuration options
        pg.setConfigOptions(antialias=True)
        # creating image view object
        self.imv = pg.ImageView()
        img = np.array(Image.open(self.img_path).rotate(-90).transpose(Image.FLIP_LEFT_RIGHT))
        self.imv.setImage(img, scale=None)#, xvals=np.linspace(1., 3., data.shape[0]))
        
        layout = QGridLayout()
        layout.addWidget(QLabel("DNA Core Submission Number"),0,1)
        self.core_number = QLineEdit()
        layout.addWidget(self.core_number, 0,2)
        # setting this layout to the widget
        # plot window goes on right side, spanning 3 rows
        layout.addWidget(self.imv, 1, 1,20,20)
        # setting this widget as central widget of the main window
        self.form = ControlsForm(parent=self)
        layout.addWidget(self.form,22,1,1,4)
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox, 23, 1, 1, 1)#, alignment=Qt.AlignmentFlag.AlignTop)
        self.setLayout(layout)

    def parse_form(self) -> Tuple[str, str|Path, list]:
        """
        Get relevant values from self/form

        Returns:
            Tuple[str, str|Path, list]: output values
        """        
        dna_core_submission_number = self.core_number.text()
        values, comment = self.form.parse_form()
        return dna_core_submission_number, self.img_path, values, comment
        
class ControlsForm(QWidget):

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.layout = QGridLayout()
        columns = []
        rows = []
        for iii, item in enumerate(["Negative Control Key", "Description", "Results - 65 C", "Results - 63 C", "Results - Spike"]):
            label = QLabel(item)
            self.layout.addWidget(label, 0, iii,1,1)
            if iii > 1:
                columns.append(item)
        for iii, item in enumerate(["RSL-NTC", "ENC-NTC", "NTC"], start=1):
            label = QLabel(item)
            self.layout.addWidget(label, iii, 0, 1, 1)
            rows.append(item)
        for iii, item in enumerate(["Processing Negative (PBS)", "Extraction Negative (Extraction buffers ONLY)", "Artic no-template control (mastermix ONLY)"], start=1):
            label = QLabel(item)
            self.layout.addWidget(label, iii, 1, 1, 1)
        for iii in range(3):
            for jjj in range(3):
                widge = QLineEdit()
                widge.setText("Neg")
                widge.setObjectName(f"{rows[iii]} : {columns[jjj]}")
                self.layout.addWidget(widge, iii+1, jjj+2, 1, 1)
        self.layout.addWidget(QLabel("Comments:"), 0,5,1,1)
        self.comment_field = QTextEdit(self)
        self.comment_field.setFixedHeight(50)
        self.layout.addWidget(self.comment_field, 1,5,4,1)
        
        self.setLayout(self.layout)

    def parse_form(self) -> List[dict]:
        """
        Pulls the controls statuses from the form.

        Returns:
            List[dict]: output of values
        """        
        output = []
        for le in self.findChildren(QLineEdit):
            label = [item.strip() for item in le.objectName().split(" : ")]
            try:
                dicto = [item for item in output if item['name']==label[0]][0]
            except IndexError:
                dicto = dict(name=label[0], values=[])
            dicto['values'].append(dict(name=label[1], value=le.text()))
            if label[0] not in [item['name'] for item in output]:
                output.append(dicto)
        logger.debug(pformat(output))
        return output, self.comment_field.toPlainText()
