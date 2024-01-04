from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QComboBox, QCheckBox, 
                             QLabel, QWidget, QHBoxLayout, 
                             QVBoxLayout, QDialogButtonBox)
from backend.db.models import SubmissionType, Equipment, BasicSubmission
from backend.validators.pydant import PydEquipment, PydEquipmentRole
import logging

logger = logging.getLogger(f"submissions.{__name__}")

class EquipmentUsage(QDialog):

    def __init__(self, parent, submission_type:SubmissionType|str, submission:BasicSubmission) -> QDialog:
        super().__init__(parent)
        self.setWindowTitle("Equipment Checklist")
        self.used_equipment = submission.get_used_equipment()
        logger.debug(f"Existing equipment: {self.used_equipment}")
        if isinstance(submission_type, str):
            self.submission_type = SubmissionType.query(name=submission_type)
        else:
            self.submission_type = submission_type
        # self.static_equipment = submission_type.get_equipment()
        self.opt_equipment = self.submission_type.get_equipment()
        logger.debug(f"EquipmentRoles: {self.opt_equipment}")
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        self.populate_form()

    def populate_form(self):
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        for eq in self.opt_equipment:
            self.layout.addWidget(eq.toForm(parent=self, submission_type=self.submission_type, used=self.used_equipment))
        self.layout.addWidget(self.buttonBox)

    def parse_form(self):
        output = []
        for widget in self.findChildren(QWidget):
            match widget:
                case (EquipmentCheckBox()|RoleComboBox()) :
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

class RoleComboBox(QWidget):

    def __init__(self, parent, role:PydEquipmentRole, submission_type:SubmissionType, used:list) -> None:
        super().__init__(parent)
        self.layout = QHBoxLayout()
        # label = QLabel()
        # label.setText(pool.name)
        self.role = role
        self.check = QCheckBox()
        if role.name in used:
            self.check.setChecked(False)
        else:
            self.check.setChecked(True)
        self.box = QComboBox()
        self.box.setMaximumWidth(125)
        self.box.setMinimumWidth(125)
        self.box.addItems([item.name for item in role.equipment])
        # self.check = QCheckBox()
        # self.layout.addWidget(label)
        self.process = QComboBox()
        self.process.setMaximumWidth(125)
        self.process.setMinimumWidth(125)
        self.process.setEditable(True)
        self.process.addItems(submission_type.get_processes_for_role(equipment_role=role.name))
        self.layout.addWidget(self.check)
        self.layout.addWidget(QLabel(f"{role.name}:"))
        self.layout.addWidget(self.box)
        self.layout.addWidget(self.process)
        # self.layout.addWidget(self.check)
        self.setLayout(self.layout)

    def parse_form(self) -> str|None:
        eq = Equipment.query(name=self.box.currentText())
        if self.check:
            return PydEquipment(name=eq.name, processes=[self.process.currentText()], role=self.role.name, asset_number=eq.asset_number, nickname=eq.nickname)
        else:
            return None
        