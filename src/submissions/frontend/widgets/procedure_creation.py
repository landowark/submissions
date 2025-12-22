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
        logger.debug(f"Procedure: {self.procedure}, ProcedureType: {self.proceduretype.improved_dict}")
        self.setWindowTitle(f"New {self.proceduretype.name} for {self.run.rsl_plate_number}")

        self.plate_map = self.proceduretype.construct_plate_map(sample_dicts=self.procedure.sample)
        self.procedure.update_samples(sample_list=[dict(sample_id=sample.sample_id, index=iii) for iii, sample in
                                                   enumerate(self.procedure.sample, start=1)])
        self.app = get_application_from_parent(parent)
        self.webview = QWebEngineView(parent=self)
        self.webview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.webview.setMinimumSize(1200, 800)
        # self.webview.setMaximumWidth(1200)
        # NOTE: Decide if exporting should be allowed.
        self.layout = QGridLayout()
        # NOTE: button to export a pdf version
        self.layout.addWidget(self.webview, 1, 0, 10, 10)
        self.setLayout(self.layout)
        # self.setFixedWidth(self.webview.width() + 20)
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
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint)

    def set_html(self):
        proceduretype_dict = self.proceduretype.improved_dict_expand_fields([{"reagentrole":[{"reagent":["reagentlot"]}]}, "equipmentrole"])
        # NOTE: Add --New-- as an option for reagents.
        for reagentrole in proceduretype_dict.get("reagentrole", []):
            try:
                check = "--New--" in [v['name'] for v in reagentrole]
            except TypeError:
                try:
                    check = "--New--" in [v.name for v in reagentrole]
                except (TypeError, AttributeError):
                    check = True
            if not check:
                reagentrole.append(dict(name="--New--"))
        # if self.procedure.equipment:
        for equipmentrole in proceduretype_dict.get('equipmentrole', []):
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
        # proceduretype_dict['equipment'] = [sanitize_object_for_json(object) for object in proceduretype_dict['equipment']]
        regex = re.compile(r".*R\d$")
        proceduretype_dict['previous'] = [""] + [item.name for item in self.run.procedure if item.proceduretype == self.proceduretype and not bool(regex.match(item.name))]
        logger.debug(f"Proceduretype dictionary:\n{pformat(proceduretype_dict)}")
        html = render_details_template(
            template_name="procedure_creation",
            js_in=["procedure_form", "grid_drag", "context_menu"],
            proceduretype=proceduretype_dict,
            run=self.run.details_dict(),
            procedure=self.procedure,
            plate_map=self.plate_map,
            edit=self.edit
        )
        # with open("platemap.html", "w") as f:
        #     f.write(html)
        self.webview.setHtml(html)

    @pyqtSlot(str, str, str, str)
    @pyqtSlot(str, str, str, str, bool)
    def update_equipment(self, equipmentrole: str, equipment: str, processversion: str, tips: str, checked: bool=True):
        logger.debug(f"update_equipment: {equipmentrole}, {equipment}, {checked}")
        self.procedure.update_equipment(equipmentrole=equipmentrole, equipment=equipment, processversion=processversion, tips=tips, checked=checked)

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
        logger.debug(f"Start updating samples: {pformat(sample_list)}")
        self.procedure.update_samples(sample_list=sample_list)

    @pyqtSlot(str)
    def log(self, logtext: str):
        logger.debug(logtext)

    @pyqtSlot(str, str, str, str)
    def add_new_reagent(self, reagentrole: str, name: str, lot: str, expiry: str):
        from backend.validators.pydant import PydReagentLot
        expiry = datetime.datetime.strptime(expiry, "%Y-%m-%d")
        logger.debug(f"{reagentrole}, {name}, {lot}, {expiry}")
        pyd = PydReagentLot(reagentrole=reagentrole, name=name, lot=lot, expiry=expiry)
        self.procedure.reagentrole[reagentrole].insert(0, pyd)
        self.set_html()

    @pyqtSlot(str, str)
    @pyqtSlot(str, str, bool)
    def update_reagent(self, reagentrole: str, name_lot_expiry: str, checked:bool=True):
        logger.debug(f"Updating reagent {reagentrole}, {name_lot_expiry}, {checked}")
        try:
            name, lot, expiry = name_lot_expiry.split(" - ")
        except ValueError as e:
            return
        self.procedure.update_reagents(reagentrole=reagentrole, name=name, lot=lot, expiry=expiry, checked=checked)

    @pyqtSlot(str, result=list)
    def get_reagent_names(self, reagentrole_name: str):
        from backend.db.models import ReagentRole
        reagentrole = ReagentRole.query(name=reagentrole_name)
        return [item.name for item in reagentrole.get_reagents(proceduretype=self.procedure.proceduretype)]


    @pyqtSlot(str)
    def remove_element(self, element: str):
        logger.debug(f"Removing element: {element}")
        logger.debug(f"Removing element: {pformat(self)}")


    def return_sql(self, new: bool = False):
        output = self.procedure.to_sql(new=new)
        return output
