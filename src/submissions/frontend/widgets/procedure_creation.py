"""
Main module to construct the procedure form
"""
from __future__ import annotations
import sys, logging, re, datetime
from pprint import pformat
from PyQt6.QtCore import pyqtSlot, Qt
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QDialog, QGridLayout, QDialogButtonBox
from typing import TYPE_CHECKING, List
if TYPE_CHECKING:
    from backend.validators import PydProcedure, PydEquipment
from tools import get_application_from_parent, render_details_template, sanitize_object_for_json

logger = logging.getLogger(f"submissions.{__name__}")


class ProcedureCreation(QDialog):

    def __init__(self, parent, procedure: PydProcedure, edit: bool = False):
        super().__init__(parent)
        self.edit = edit
        self.run = procedure.run
        self.procedure = procedure
        self.proceduretype = procedure.proceduretype
        self.setWindowTitle(f"New {self.proceduretype.name} for {self.run.rsl_plate_number}")
        self.plate_map = self.proceduretype.construct_plate_map(sample_dicts=self.procedure.sample)
        self.procedure.update_samples(sample_list=[dict(sample_id=sample.sample_id, index=iii) for iii, sample in
                                                   enumerate(self.procedure.sample, start=1)])
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
        self.set_html()
        self.webview.page().setWebChannel(self.channel)
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout.addWidget(self.buttonBox, 11, 1, 1, 1)


    def set_html(self):
        from .equipment_usage import EquipmentUsage
        proceduretype_dict = self.proceduretype.details_dict()
        # NOTE: Add --New-- as an option for reagents.
        for key, value in self.procedure.reagentrole.items():
            value.append(dict(name="--New--"))
        if self.procedure.equipment:
            for equipmentrole in proceduretype_dict['equipment']:
                # NOTE: Check if procedure equipment is present and move to head of the list if so.
                try:
                    relevant_procedure_item = next((equipment for equipment in self.procedure.equipment if
                                                    equipment.equipmentrole == equipmentrole['name']))
                except StopIteration:
                    continue
                item_in_er_list = next((equipment for equipment in equipmentrole['equipment'] if
                                        equipment['name'] == relevant_procedure_item.name))
                equipmentrole['equipment'].insert(0, equipmentrole['equipment'].pop(
                    equipmentrole['equipment'].index(item_in_er_list)))
        proceduretype_dict['equipment_section'] = EquipmentUsage.construct_html(procedure=self.procedure, child=True)
        proceduretype_dict['equipment'] = [sanitize_object_for_json(object) for object in proceduretype_dict['equipment']]
        self.update_equipment = EquipmentUsage.update_equipment
        regex = re.compile(r".*R\d$")
        proceduretype_dict['previous'] = [""] + [item.name for item in self.run.procedure if item.proceduretype == self.proceduretype and not bool(regex.match(item.name))]
        html = render_details_template(
            template_name="procedure_creation",
            js_in=["procedure_form", "grid_drag", "context_menu"],
            proceduretype=proceduretype_dict,
            run=self.run.details_dict(),
            procedure=self.procedure,
            plate_map=self.plate_map,
            edit=self.edit
        )
        self.webview.setHtml(html)

    @pyqtSlot(str, str, str, str)
    def update_equipment(self, equipmentrole: str, equipment: str, process: str, tips: str):
        from backend.db.models import Equipment, ProcessVersion, TipsLot
        try:
            equipment_of_interest = next(
                (item for item in self.procedure.equipment if item.equipmentrole == equipmentrole))
        except StopIteration:
            equipment_of_interest = None
        equipment = Equipment.query(name=equipment)
        if equipment_of_interest:
            eoi = self.procedure.equipment.pop(self.procedure.equipment.index(equipment_of_interest))
        else:
            eoi: PydEquipment = equipment.to_pydantic(equipmentrole=equipmentrole)
        eoi.name = equipment.name
        eoi.asset_number = equipment.asset_number
        eoi.nickname = equipment.nickname
        process_name, version = process.split("-v")
        process = ProcessVersion.query(name=process_name, version=version, limit=1)
        eoi.process = process
        try:
            tips_manufacturer, tipsref, lot = [item if item != "" else None for item in tips.split("-")]
            tips = TipsLot.query(manufacturer=tips_manufacturer, ref=tipsref, lot=lot)
            eoi.tips = tips
        except ValueError:
            logger.warning(f"No tips info to unpack")
        self.procedure.equipment.append(eoi)

    @pyqtSlot(str, str)
    def text_changed(self, key: str, new_value: str):
        match key:
            case "rsl_plate_num":
                setattr(self.procedure.run, key, new_value)
            case "repeat_of":
                from backend.db.models import Procedure
                parent = Procedure.query(name=new_value, limit=1)
                self.procedure.repeat_of = parent
            case _:
                attribute = getattr(self.procedure, key)
                match attribute:
                    case dict():
                        attribute['value'] = new_value.strip('\"')
                    case _:
                        setattr(self.procedure, key, new_value.strip('\"'))

    @pyqtSlot(str, bool)
    def check_toggle(self, key: str, ischecked: bool):
        setattr(self.procedure, key, ischecked)

    @pyqtSlot(str)
    def update_kit(self, kittype):
        self.procedure.update_kittype_reagentroles(kittype=kittype)
        self.set_html()

    @pyqtSlot(list)
    def rearrange_plate(self, sample_list: List[dict]):
        self.procedure.update_samples(sample_list=sample_list)

    @pyqtSlot(str)
    def log(self, logtext: str):
        logger.debug(logtext)

    @pyqtSlot(str, str, str, str)
    def add_new_reagent(self, reagentrole: str, name: str, lot: str, expiry: str):
        from backend.validators.pydant import PydReagent
        expiry = datetime.datetime.strptime(expiry, "%Y-%m-%d")
        pyd = PydReagent(reagentrole=reagentrole, name=name, lot=lot, expiry=expiry)
        self.procedure.reagentrole[reagentrole].insert(0, pyd)
        self.set_html()

    @pyqtSlot(str, str)
    def update_reagent(self, reagentrole: str, name_lot_expiry: str):
        try:
            name, lot, expiry = name_lot_expiry.split(" - ")
        except ValueError as e:
            return
        self.procedure.update_reagents(reagentrole=reagentrole, name=name, lot=lot, expiry=expiry)

    def return_sql(self, new: bool = False):
        return self.procedure.to_sql(new=new)
