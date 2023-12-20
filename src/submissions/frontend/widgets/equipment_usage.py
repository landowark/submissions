from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QComboBox, QCheckBox, 
                             QLabel, QWidget, QHBoxLayout, 
                             QVBoxLayout, QDialogButtonBox)
from backend.db.models import SubmissionType
from backend.validators.pydant import PydEquipment, PydEquipmentPool

class EquipmentUsage(QDialog):

    def __init__(self, parent, submission_type:SubmissionType|str) -> QDialog:
        super().__init__(parent)
        self.setWindowTitle("Equipment Checklist")
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        # self.static_equipment = submission_type.get_equipment()
        self.opt_equipment = submission_type.get_equipment()
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        self.populate_form()

    def populate_form(self):
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        for eq in self.opt_equipment:
            self.layout.addWidget(eq.toForm(parent=self))
        self.layout.addWidget(self.buttonBox)

    def parse_form(self):
        output = []
        for widget in self.findChildren(QWidget):
            match widget:
                case (EquipmentCheckBox()|PoolComboBox()) :
                    output.append(widget.parse_form())
                case _:
                    pass
        return [item for item in output if item != None]

class EquipmentCheckBox(QWidget):

    def __init__(self, parent, equipment:PydEquipment) -> None:
        super().__init__(parent)
        self.layout = QHBoxLayout()
        self.label = QLabel()
        self.label.setMaximumWidth(125)
        self.label.setMinimumWidth(125)
        self.check = QCheckBox()
        if equipment.static:
            self.check.setChecked(True)
            # self.check.setEnabled(False)
        if equipment.nickname != None:
            text = f"{equipment.name} ({equipment.nickname})"
        else:
            text = equipment.name
        self.setObjectName(equipment.name)
        self.label.setText(text)
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.check)
        self.setLayout(self.layout)

    def parse_form(self) -> str|None:
        if self.check.isChecked():
            return self.objectName()
        else:
            return None

class PoolComboBox(QWidget):

    def __init__(self, parent, pool:PydEquipmentPool) -> None:
        super().__init__(parent)
        self.layout = QHBoxLayout()
        # label = QLabel()
        # label.setText(pool.name)
        self.box = QComboBox()
        self.box.setMaximumWidth(125)
        self.box.setMinimumWidth(125)
        self.box.addItems([item.name for item in pool.equipment])
        self.check = QCheckBox()
        # self.layout.addWidget(label)
        self.layout.addWidget(self.box)
        self.layout.addWidget(self.check)
        self.setLayout(self.layout)

    def parse_form(self) -> str:
        if self.check.isChecked():
            return self.box.currentText()
        else:
            return None
