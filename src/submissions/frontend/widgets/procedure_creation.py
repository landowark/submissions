"""
Main module to construct the procedure form
"""
from __future__ import annotations
import json, sys, logging, re, datetime
from pprint import pformat
from PyQt6.QtCore import pyqtSlot, Qt, QVariant
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QDialog, QGridLayout, QDialogButtonBox
from typing import TYPE_CHECKING, List
if TYPE_CHECKING:
    from backend.validators import PydProcedure, PydEquipment
from frontend.widgets import CustomWebEnginePage
from tools import get_application_from_parent, render_details_template, sanitize_object_for_json, get_index_of_value_in_dict_list

logger = logging.getLogger(f"submissions.{__name__}")


class ProcedureCreation(QDialog):

    def __init__(self, parent, procedure: PydProcedure, edit: bool = False):
        from backend.validators.pydant import PydProcedureType
        super().__init__(parent)
        self.edit = edit
        self.run = procedure.run
        self.procedure = procedure
        self.proceduretype = procedure.proceduretype
        try:
            assert isinstance(self.proceduretype, PydProcedureType)
        except AssertionError:
            sys.exit(str(self.proceduretype))
        self.proceduretype_dict = self.proceduretype.improved_dict_expand_fields([
            {
                "reagentrole":[
                        {"reagent":["reagentlot"]}]
                        
            }, 
            {
                "equipmentrole": [
                        {"equipmentroleequipmentassociation":["equipment", "process"]}]
            }
            
            ])
        # logger.debug(f"ProcedureType: {pformat(self.proceduretype_dict)}")
        # with open("proceduretype.json", "w") as f:
        #     json.dump(sanitize_object_for_json(self.proceduretype_dict), f, indent=4)
        self.setWindowTitle(f"New {self.proceduretype.name} for {self.run.rsl_plate_number}")

        self.plate_map = self.proceduretype.construct_plate_map(sample_dicts=self.procedure.sample)
        logger.debug("Updating samples")
        self.procedure.update_samples(sample_list=[dict(sample_id=sample.sample_id, index=iii) for iii, sample in
                                                   enumerate(self.procedure.sample, start=1)])
        self.app = get_application_from_parent(parent)
        self.webview = QWebEngineView(parent=self)
        self.webview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.webview.setMinimumSize(1200, 800)
        custom_page = CustomWebEnginePage(self.webview)
        self.webview.setPage(custom_page)
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
        # NOTE: Add --New-- as an option for reagents.
        for reagentrole in self.proceduretype_dict.get("reagentrole", []):
            for reagent in reagentrole['reagent']:
                if len(reagent['reagentlot']) < 1:
                    reagent['reagentlot'].append(dict(name="", active=True))
                else:
                    try:
                        reagent['reagentlot'].remove(dict(name="", active=True))
                    except Exception:
                        pass
                try:
                    check = "--New--" in (reagentlot['name'] for reagentlot in reagent['reagentlot'])
                except TypeError:
                    check = True
                if not check:
                    reagent['reagentlot'].append(dict(name="--New--", active=True))
        # if self.procedure.equipment:
        for equipmentrole in self.proceduretype_dict.get('equipmentrole', []):
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
        self.proceduretype_dict['previous'] = [""] + [item.name for item in self.run.procedure if item.proceduretype == self.proceduretype and not bool(regex.match(item.name))]
        # logger.debug(f"Proceduretype equipmentrole dictionary:\n{pformat(self.proceduretype_dict['equipmentrole'])}")
        html = render_details_template(
            template_name="procedure_creation",
            js_in=["procedure_form", "grid_drag", "context_menu"],
            proceduretype=self.proceduretype_dict,
            run=self.run.improved_dict,
            procedure=self.procedure,
            plate_map=self.plate_map,
            edit=self.edit
        )
        # with open("platemap.html", "w") as f:
        #     f.write(html)
        self.webview.setHtml(html)

    @pyqtSlot(str, str, str, QVariant)
    @pyqtSlot(str, str, str, QVariant, bool)
    def update_equipment(self, equipmentrole: str, equipment: str, processversion: str, tips: str, checked: bool=True):
        logger.debug(f"update_equipment: {equipmentrole}, {equipment}, {processversion}, {tips}, {checked}")
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
    def add_new_reagent(self, reagentrole: str, reagent: str, lot: str, expiry: str):
        from backend.validators.pydant import PydReagentLot
        expiry = datetime.datetime.strptime(expiry, "%Y-%m-%d")
        expiry = datetime.datetime.combine(expiry, datetime.datetime.max.time())
        logger.debug(f"{reagentrole}, {reagent}, {lot}, {expiry}")
        pyd = PydReagentLot(reagent=reagent, lot=lot, expiry=expiry, active=True)
        reagentrole_idx, rr_dummy = get_index_of_value_in_dict_list(key="name", value=reagentrole, list_=self.proceduretype_dict['reagentrole'])
        reagent_idx, _ = get_index_of_value_in_dict_list(key="name", value=reagent, list_=rr_dummy['reagent'])
        self.proceduretype_dict['reagentrole'][reagentrole_idx]['reagent'][reagent_idx]['reagentlot'].insert(0, pyd)
        logger.debug(f"Procedure:\n{pformat(self.proceduretype.__dict__)}")
        self.set_html()

    @pyqtSlot(str, str)
    @pyqtSlot(str, str, bool)
    def update_reagent(self, reagentrole: str, name_lot_expiry: str, checked:bool=True):
        logger.debug(f"Updating reagent {reagentrole}, {name_lot_expiry}, {checked}")
        try:
            name, lot = name_lot_expiry.rsplit("-", 1)
        except ValueError as e:
            logger.error(f"Could not split reagent name and lot from: {name_lot_expiry} due to {e}")
            return
        self.procedure.update_reagents(reagentrole=reagentrole, name=name, lot=lot, checked=checked)

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
        output = self.procedure.to_sql()
        if isinstance(output, tuple):
            output = output[0]
        return output
