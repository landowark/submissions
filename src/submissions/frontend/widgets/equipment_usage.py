"""
Creates forms that the user can enter equipment info into.
"""
import sys, logging
from pprint import pformat
from typing import Generator
from PyQt6.QtCore import Qt, pyqtSlot, QSignalBlocker
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QDialogButtonBox, QGridLayout, QWidget, QCheckBox, QComboBox, QLabel
)
from backend import Process
from backend.db.models import Equipment
from backend.validators.pydant import PydProcedure, PydEquipmentRole, PydTips, PydEquipment
from tools import get_application_from_parent, render_details_template

logger = logging.getLogger(f"submissions.{__name__}")


class EquipmentUsage(QDialog):

    def __init__(self, parent, procedure: PydProcedure):
        super().__init__(parent)
        self.procedure = procedure
        self.setWindowTitle(f"Equipment Checklist - {procedure.name}")
        self.used_equipment = self.procedure.equipment
        self.kit = self.procedure.kittype
        self.opt_equipment = procedure.proceduretype.get_equipment()
        self.layout = QVBoxLayout()
        self.app = get_application_from_parent(parent)
        self.webview = QWebEngineView(parent=self)
        self.webview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.webview.setMinimumSize(1200, 800)
        self.webview.setMaximumWidth(1200)
        # NOTE: Decide if exporting should be allowed.
        self.layout = QGridLayout()
        # NOTE: button to export a pdf version
        self.layout.addWidget(self.webview, 1, 0, 10, 10)
        self.setLayout(self.layout)
        self.setFixedWidth(self.webview.width() + 20)
        # NOTE: setup channel
        self.channel = QWebChannel()
        self.channel.registerObject('backend', self)
        html = self.construct_html(procedure=procedure)
        self.webview.setHtml(html)
        self.webview.page().setWebChannel(self.channel)
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout.addWidget(self.buttonBox, 11, 1, 1, 1)

    @classmethod
    def construct_html(cls, procedure: PydProcedure, child: bool = False):
        proceduretype = procedure.proceduretype
        proceduretype_dict = proceduretype.details_dict()
        run = procedure.run
        html = render_details_template(
            template_name="support/equipment_usage",
            css_in=[],
            js_in=[],
            proceduretype=proceduretype_dict,
            run=run.details_dict(),
            procedure=procedure.__dict__,
            child=child
        )
        return html

    @pyqtSlot(str, str, str, str)
    def update_equipment(self, equipmentrole: str, equipment: str, process: str, tips: str):
        try:
            equipment_of_interest = next(
                (item for item in self.procedure.equipment if item.equipmentrole == equipmentrole))
        except StopIteration:
            equipment_of_interest = None
        equipment = Equipment.query(name=equipment)
        if equipment_of_interest:
            eoi = self.procedure.equipment.pop(self.procedure.equipment.index(equipment_of_interest))
        else:
            eoi = equipment.to_pydantic(proceduretype=self.procedure.proceduretype)
        eoi.name = equipment.name
        eoi.asset_number = equipment.asset_number
        eoi.nickname = equipment.nickname
        process = next((prcss for prcss in equipment.process if prcss.name == process))
        eoi.process = process.to_pydantic()
        tips = next((tps for tps in equipment.tips if tps.name == tips))
        eoi.tips = tips.to_pydantic()
        self.procedure.equipment.append(eoi)
        logger.debug(f"Updated equipment: {self.procedure.equipment}")

    def save_procedure(self):
        sql, _ = self.procedure.to_sql()
        sql.save()


class RoleComboBox(QWidget):

    def __init__(self, parent, role: PydEquipmentRole, used: Generator) -> None:
        super().__init__(parent)
        self.layout = QGridLayout()
        self.role = role
        self.check = QCheckBox()
        self.check.setChecked(False)
        self.check.stateChanged.connect(self.toggle_checked)
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
        self.layout.addWidget(self.check, 0, 0)
        label = QLabel(f"{role.name}:")
        label.setMinimumWidth(200)
        label.setMaximumWidth(200)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.layout.addWidget(label, 0, 1)
        self.layout.addWidget(self.box, 0, 2)
        self.layout.addWidget(self.process, 0, 3)
        self.setLayout(self.layout)
        self.toggle_checked()

    def update_processes(self):
        """
        Changes process when equipment is changed
        """
        equip = self.box.currentText()
        equip2 = next((item for item in self.role.equipment if item.name == equip), self.role.equipment[0])
        with QSignalBlocker(self.process) as blocker:
            self.process.clear()
        self.process.addItems([item for item in equip2.process if item in self.role.process])

    def update_tips(self):
        """
        Changes what tips are available when process is changed
        """
        process = self.process.currentText().strip()
        process = Process.query(name=process)
        if process.tiprole:
            for iii, tip_role in enumerate(process.tiprole):
                widget = QComboBox()
                tip_choices = [item.name for item in tip_role.tips]
                widget.setEditable(False)
                widget.addItems(tip_choices)
                widget.setObjectName(f"tips_{tip_role.name}")
                widget.setMinimumWidth(200)
                widget.setMaximumWidth(200)
                self.layout.addWidget(widget, iii, 4)
        else:
            widget = QLabel("")
            widget.setMinimumWidth(200)
            widget.setMaximumWidth(200)
            self.layout.addWidget(widget, 0, 4)
        try:
            widget.setEnabled(self.check.isChecked())
        except NameError:
            pass

    def parse_form(self) -> PydEquipment | None:
        """
        Creates PydEquipment for values in form

        Returns:
            PydEquipment|None: PydEquipment matching form
        """
        eq = Equipment.query(name=self.box.currentText())
        tips = [PydTips(name=item.currentText(), tiprole=item.objectName().lstrip("tips").lstrip("_"), lot="") for item in
                self.findChildren(QComboBox) if item.objectName().startswith("tips")]
        try:
            return PydEquipment(
                name=eq.name,
                processes=[self.process.currentText().strip()],
                equipmentrole=self.role.name,
                asset_number=eq.asset_number,
                nickname=eq.nickname,
                tips=tips
            )
        except Exception as e:
            logger.error(f"Could create PydEquipment due to: {e}")

    def toggle_checked(self):
        """
        If this equipment is disabled, the input fields will be disabled.
        """
        for widget in self.findChildren(QWidget):
            match widget:
                case QCheckBox():
                    continue
                case _:
                    widget.setEnabled(self.check.isChecked())
