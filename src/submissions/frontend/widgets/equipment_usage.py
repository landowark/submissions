import sys
from pprint import pformat
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QComboBox, QCheckBox,
                             QLabel, QWidget, QHBoxLayout,
                             QVBoxLayout, QDialogButtonBox, QGridLayout)
from backend.db.models import Equipment, BasicSubmission, Process
from backend.validators.pydant import PydEquipment, PydEquipmentRole, PydTips
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
        # logger.debug(f"Existing equipment: {self.used_equipment}")
        self.opt_equipment = submission.submission_type.get_equipment()
        # logger.debug(f"EquipmentRoles: {self.opt_equipment}")
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
            widg = eq.to_form(parent=self, used=self.used_equipment)
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
        logger.debug(f"parsed output of Equsage form: {pformat(output)}")
        return [item for item in output if item is not None]
    
    class LabelRow(QWidget):

        def __init__(self, parent) -> None:
            super().__init__(parent)
            self.layout = QHBoxLayout()
            self.check = QCheckBox()
            self.layout.addWidget(self.check)
            self.check.stateChanged.connect(self.check_all)
            for item in ["Role", "Equipment", "Process", "Tips"]:
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

class RoleComboBox(QWidget):

    def __init__(self, parent, role:PydEquipmentRole, used:list) -> None:
        super().__init__(parent)
        # self.layout = QHBoxLayout()
        self.layout = QGridLayout()
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
        self.process.setEditable(False)
        self.process.currentTextChanged.connect(self.update_tips)
        # self.tips = QComboBox()
        # self.tips.setMaximumWidth(200)
        # self.tips.setMinimumWidth(200)
        # self.tips.setEditable(True)
        self.layout.addWidget(self.check,0,0)
        label = QLabel(f"{role.name}:")
        label.setMinimumWidth(200)
        label.setMaximumWidth(200)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.layout.addWidget(label,0,1)
        self.layout.addWidget(self.box,0,2)
        self.layout.addWidget(self.process,0,3)
        self.setLayout(self.layout)
        
    def update_processes(self):
        """
        Changes processes when equipment is changed
        """        
        equip = self.box.currentText()
        # logger.debug(f"Updating equipment: {equip}")
        equip2 = [item for item in self.role.equipment if item.name==equip][0]
        # logger.debug(f"Using: {equip2}")
        self.process.clear()
        self.process.addItems([item for item in equip2.processes if item in self.role.processes])

    def update_tips(self):

        process = self.process.currentText()
        logger.debug(f"Checking process: {process}")
        process = Process.query(name=process)
        if process.tip_roles:
            for iii, tip_role in enumerate(process.tip_roles):
                widget = QComboBox()
                tip_choices = [item.name for item in tip_role.instances]
                widget.setEditable(False)
                widget.addItems(tip_choices)
                # logger.debug(f"Tiprole: {tip_role.__dict__}")
                widget.setObjectName(f"tips_{tip_role.name}")
                widget.setMinimumWidth(100)
                widget.setMaximumWidth(100)
                self.layout.addWidget(widget, iii, 4)
        else:
            widget = QLabel("")
            widget.setMinimumWidth(100)
            widget.setMaximumWidth(100)
            self.layout.addWidget(widget,0,4)

    def parse_form(self) -> PydEquipment|None:
        """
        Creates PydEquipment for values in form

        Returns:
            PydEquipment|None: PydEquipment matching form
        """        
        eq = Equipment.query(name=self.box.currentText())
        tips = [PydTips(name=item.currentText(), role=item.objectName().lstrip("tips").lstrip("_")) for item in self.findChildren(QComboBox) if item.objectName().startswith("tips")]
        logger.debug(tips)
        try:
            return PydEquipment(
                name=eq.name,
                processes=[self.process.currentText()],
                role=self.role.name,
                asset_number=eq.asset_number,
                nickname=eq.nickname,
                tips=tips
            )
        except Exception as e:
            logger.error(f"Could create PydEquipment due to: {e}")
        