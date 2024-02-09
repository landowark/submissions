from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QComboBox, QCheckBox, 
                             QLabel, QWidget, QHBoxLayout, 
                             QVBoxLayout, QDialogButtonBox)
from backend.db.models import Equipment, BasicSubmission
from backend.validators.pydant import PydEquipment, PydEquipmentRole
import logging
from typing import List

logger = logging.getLogger(f"submissions.{__name__}")

class EquipmentUsage(QDialog):

    def __init__(self, parent, submission:BasicSubmission) -> QDialog:
        super().__init__(parent)
        self.submission = submission
        self.setWindowTitle("Equipment Checklist")
        self.used_equipment = self.submission.get_used_equipment()
        self.kit = self.submission.extraction_kit
        logger.debug(f"Existing equipment: {self.used_equipment}")
        self.opt_equipment = submission.submission_type.get_equipment()
        logger.debug(f"EquipmentRoles: {self.opt_equipment}")
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        self.populate_form()

    def populate_form(self):
        """
        Create form widgets
        """        
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        label = self.LabelRow(parent=self)
        self.layout.addWidget(label)
        # logger.debug("Creating widgets for equipment")
        for eq in self.opt_equipment:
            widg = eq.toForm(parent=self, used=self.used_equipment)
            self.layout.addWidget(widg)
            widg.update_processes()
        self.layout.addWidget(self.buttonBox)

    def parse_form(self) -> List[PydEquipment]:
        """
        Pull info from all RoleComboBox widgets

        Returns:
            List[PydEquipment]: All equipment pulled from widgets
        """        
        output = []
        for widget in self.findChildren(QWidget):
            match widget:
                case RoleComboBox() :
                    if widget.check.isChecked():
                        output.append(widget.parse_form())
                case _:
                    pass
        return [item for item in output if item != None]
    
    class LabelRow(QWidget):

        def __init__(self, parent) -> None:
            super().__init__(parent)
            self.layout = QHBoxLayout()
            self.check = QCheckBox()
            self.layout.addWidget(self.check)
            self.check.stateChanged.connect(self.check_all)
            for item in ["Role", "Equipment", "Process"]:
                l = QLabel(item)
                l.setMaximumWidth(200)
                l.setMinimumWidth(200)
                self.layout.addWidget(l)
            self.setLayout(self.layout)

        def check_all(self):
            """
            Toggles all checkboxes in the form
            """            
            for object in self.parent().findChildren(QCheckBox):
                object.setChecked(self.check.isChecked())

# TODO: Figure out how this is working again
class RoleComboBox(QWidget):

    def __init__(self, parent, role:PydEquipmentRole, used:list) -> None:
        super().__init__(parent)
        self.layout = QHBoxLayout()
        self.role = role
        self.check = QCheckBox()
        if role.name in used:
            self.check.setChecked(False)
        else:
            self.check.setChecked(True)
        self.box = QComboBox()
        self.box.setMaximumWidth(200)
        self.box.setMinimumWidth(200)
        self.box.addItems([item.name for item in role.equipment])
        self.box.currentTextChanged.connect(self.update_processes)
        self.process = QComboBox()
        self.process.setMaximumWidth(200)
        self.process.setMinimumWidth(200)
        self.process.setEditable(True)
        self.layout.addWidget(self.check)
        label = QLabel(f"{role.name}:")
        label.setMinimumWidth(200)
        label.setMaximumWidth(200)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.layout.addWidget(label)
        self.layout.addWidget(self.box)
        self.layout.addWidget(self.process)
        self.setLayout(self.layout)
        
    def update_processes(self):
        """
        Changes processes when equipment is changed
        """        
        equip = self.box.currentText()
        logger.debug(f"Updating equipment: {equip}")
        equip2 = [item for item in self.role.equipment if item.name==equip][0]
        logger.debug(f"Using: {equip2}")
        self.process.clear()
        self.process.addItems([item for item in equip2.processes if item in self.role.processes])

    def parse_form(self) -> PydEquipment|None:
        """
        Creates PydEquipment for values in form

        Returns:
            PydEquipment|None: PydEquipment matching form
        """        
        eq = Equipment.query(name=self.box.currentText())
        try:
            return PydEquipment(name=eq.name, processes=[self.process.currentText()], role=self.role.name, asset_number=eq.asset_number, nickname=eq.nickname)
        except Exception as e:
            logger.error(f"Could create PydEquipment due to: {e}")
        