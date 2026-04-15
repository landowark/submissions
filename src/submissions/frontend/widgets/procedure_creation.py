"""
Main module to construct the procedure form
"""
from __future__ import annotations
import sys, logging, datetime, os
from pprint import pformat
from PyQt6.QtCore import pyqtSlot, Qt, QVariant
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QDialog, QGridLayout, QDialogButtonBox
from typing import TYPE_CHECKING, List
from . import CustomWebEnginePage
if TYPE_CHECKING:
    from backend.validators import PydProcedure
from frontend.widgets import CustomWebEnginePage
from tools import get_application_from_parent, render_details_template, find_first_matching_dict

logger = logging.getLogger(f"submissions.{__name__}")


class ProcedureCreation(QDialog):

    def __init__(self, parent, procedure: PydProcedure, edit: bool = False):
        from backend.validators.pydant import PydProcedureType, PydProcedureSampleAssociation
        super().__init__(parent)
        if 'QTWEBENGINE_REMOTE_DEBUGGING' not in os.environ:
            os.environ['QTWEBENGINE_REMOTE_DEBUGGING'] = '9222'
            logger.info('Enabled QTWEBENGINE_REMOTE_DEBUGGING=9222 for remote inspection')
        self.edit = edit
        self.run = procedure.run
        self.procedure = procedure
        self.proceduretype = procedure.proceduretype
        try:
            assert isinstance(self.proceduretype, PydProcedureType)
        except AssertionError:
            logger.error(str(self.proceduretype))
            return
        self.proceduretype_dict = self.procedure.reorder_proceduretype_by_procedure()
        if isinstance(self.run.rsl_plate_number, dict):
            title = self.run.rsl_plate_number.get("value", "Unknown Run")
        else:
            title = self.run.rsl_plate_number
        self.setWindowTitle(f"New {self.proceduretype.name} for {title}")
        # sample_dicts = [item.improved_dict for item in self.procedure.sample]
        # self.plate_map = self.proceduretype.construct_plate_map(sample_dicts=self.procedure.sample)
        self.platemap = self.proceduretype_dict['platemap']
        logger.debug(self.platemap)
        self.procedure.update_samples(sample_list=[sample for sample in self.constructed_sample_list])
        self.app = get_application_from_parent(parent)
        # Ensure remote debugging is enabled before the WebEngine is initialised.
        # This exposes the remote inspector on localhost:9222 so you can open
        # http://localhost:9222/ in a desktop browser and inspect console/network errors.
        
        self.webview = QWebEngineView(parent=self)
        self.webview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.webview.setMinimumSize(1200, 800)
        custom_page = CustomWebEnginePage(self.webview)
        self.webview.setPage(custom_page)
        # NOTE: Decide if exporting should be allowed.
        self.layout = QGridLayout()
        # NOTE: button to export a pdf version
        self.layout.addWidget(self.webview, 1, 0, 10, 10)
        self.setLayout(self.layout)
        # NOTE: setup channel
        self.channel = QWebChannel()
        self.channel.registerObject('backend', self)
        self.webview.page().setWebChannel(self.channel)
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout.addWidget(self.buttonBox, 11, 1, 1, 1)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint)
        self.set_html()

    @property
    def constructed_sample_list(self):
        from backend.validators.pydant import PydSample, PydProcedureSampleAssociation
        for iii, sample in enumerate(self.procedure.sample, start=1):
            # logger.debug(f"Constructing sample {iii} from {sample}")
            match sample:
                case PydSample():
                    sample_id = sample.sample_id
                case PydProcedureSampleAssociation():
                    sample_id = sample.sample
                case str():
                    sample_id = sample
                case dict():
                    sample_id = sample.get("sample_id", f"Unknown Sample {iii}")
                case _:
                    sample_id = f"Unknown Sample {iii}"
            yield dict(sample_id=sample_id, index=iii)

    def set_html(self):
        html = render_details_template(
            template="procedure_creation",
            js_in=["procedure_form", "grid_drag", "context_menu"],
            proceduretype=self.proceduretype_dict,
            run=self.run.improved_dict,
            procedure=self.procedure,
            platemap=self.platemap,
            now = datetime.datetime.now()
        )
        self.webview.setHtml(html)
        

    @pyqtSlot(str, str, str, QVariant)
    @pyqtSlot(str, str, str, QVariant, bool)
    def update_equipment(self, equipmentrole: str, equipment: str, processversion: str, tips: str, checked: bool=True):
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

    @pyqtSlot(list)
    def rearrange_plate(self, sample_list: List[dict]):
        self.procedure.update_samples(sample_list=sample_list)

    @pyqtSlot(str)
    def log(self, logtext: str):
        logger.debug(logtext)

    @pyqtSlot(str, str, str, str)
    def add_new_reagent(self, reagentrole: str, reagent: str, lot: str, expiry: str):
        from backend.validators.pydant import PydReagentLot
        expiry = datetime.datetime.strptime(expiry, "%Y-%m-%d")
        expiry = datetime.datetime.combine(expiry, datetime.datetime.max.time())
        pyd = PydReagentLot(reagent=reagent, lot=lot, expiry=expiry, active=True)
        reagentrole_idx, rr_dummy = find_first_matching_dict(key="name", value_to_match=reagentrole, list_of_dicts=self.proceduretype_dict['reagentrole'], mode="index")
        reagent_idx, _ = find_first_matching_dict(key="name", value_to_match=reagent, list_of_dicts=rr_dummy['reagent'], mode="index")
        self.proceduretype_dict['reagentrole'][reagentrole_idx]['reagent'][reagent_idx]['reagentlot'].insert(0, pyd)
        self.set_html()

    @pyqtSlot(str, str)
    @pyqtSlot(str, str, bool)
    def update_reagent(self, reagentrole: str, name_lot_expiry: str, checked:bool=True):
        try:
            name, lot = name_lot_expiry.split(" - ", 1)
        except ValueError as e:
            logger.error(f"Could not split reagent name and lot from: {name_lot_expiry} due to {e}")
            return
        self.procedure.update_reagents(reagentrole=reagentrole, name=name, lot=lot, checked=checked)

    @pyqtSlot(str, result=list)
    def get_reagent_names(self, reagentrole_name: str):
        from backend.db.models import ReagentRole
        reagentrole = ReagentRole.query(name=reagentrole_name)
        return [item.name for item in reagentrole.get_reagents(proceduretype=self.procedure.proceduretype)]

    def return_sql(self, new: bool = False):
        output = self.procedure.to_sql()
        if isinstance(output, tuple):
            output = output[0]
        return output
