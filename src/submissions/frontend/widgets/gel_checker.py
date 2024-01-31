# import required modules
# from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import *
# import sys
from PyQt6.QtWidgets import QWidget
import numpy as np
import pyqtgraph as pg
from PyQt6.QtGui import *
from PyQt6.QtCore import *
from PIL import Image
import numpy as np

# Main window class
class GelBox(QDialog):

    def __init__(self, parent, img_path):
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
        # self.show()

    # method for components
    def UiComponents(self):
        # widget = QWidget()
        # setting configuration options
        pg.setConfigOptions(antialias=True)
        # creating image view object
        self.imv = pg.ImageView()
        img = np.array(Image.open(self.img_path).rotate(-90).transpose(Image.FLIP_LEFT_RIGHT))
        self.imv.setImage(img)#, xvals=np.linspace(1., 3., data.shape[0]))
        layout = QGridLayout()
        # setting this layout to the widget
        # widget.setLayout(layout)
        # plot window goes on right side, spanning 3 rows
        layout.addWidget(self.imv, 0, 0,20,20)
        # setting this widget as central widget of the main window
        self.form = ControlsForm(parent=self)
        layout.addWidget(self.form,21,1,1,4)
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox, 21, 5, 1, 1)#, alignment=Qt.AlignmentFlag.AlignTop)
        # self.buttonBox.clicked.connect(self.submit)
        self.setLayout(layout)

    def parse_form(self):
        return self.img_path, self.form.parse_form()
        

class ControlsForm(QWidget):

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.layout = QGridLayout()
        columns = []
        rows = []
        for iii, item in enumerate(["Negative Control Key", "Description", "Results - 65 C",	"Results - 63 C", "Results - Spike"]):
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
        self.setLayout(self.layout)

    def parse_form(self):
        dicto = {}
        for le in self.findChildren(QLineEdit):
            label = [item.strip() for item in le.objectName().split(" : ")]
            if label[0] not in dicto.keys():
                dicto[label[0]] = {}
            dicto[label[0]][label[1]] = le.text()
        return dicto