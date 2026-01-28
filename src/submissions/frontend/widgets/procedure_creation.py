"""
Main module to construct the procedure form
"""
from __future__ import annotations
import json, sys, logging, re, datetime, os
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
            logger.error(str(self.proceduretype))
            return
        self.proceduretype_dict = self.procedure.reorder_proceduretype_by_procedure()
        if isinstance(self.run.rsl_plate_number, dict):
            title = self.run.rsl_plate_number.get("value", "Unknown Run")
        else:
            title = self.run.rsl_plate_number
        self.setWindowTitle(f"New {self.proceduretype.name} for {title}")
        self.plate_map = self.proceduretype.construct_plate_map(sample_dicts=self.procedure.sample)
        self.procedure.update_samples(sample_list=[dict(sample_id=sample.sample_id, index=iii) for iii, sample in
                                                   enumerate(self.procedure.sample, start=1)])
        self.app = get_application_from_parent(parent)
        # Ensure remote debugging is enabled before the WebEngine is initialised.
        # This exposes the remote inspector on localhost:9222 so you can open
        # http://localhost:9222/ in a desktop browser and inspect console/network errors.
        if 'QTWEBENGINE_REMOTE_DEBUGGING' not in os.environ:
            os.environ['QTWEBENGINE_REMOTE_DEBUGGING'] = '9222'
            logger.info('Enabled QTWEBENGINE_REMOTE_DEBUGGING=9222 for remote inspection')

        self.webview = QWebEngineView(parent=self)
        self.webview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.webview.setMinimumSize(1200, 800)
        custom_page = CustomWebEnginePage(self.webview)
        self.webview.setPage(custom_page)
        # Connect a loadFinished handler to capture page load status and HTML for debugging
        # try:
        #     self.webview.loadFinished.connect(self._on_load_finished)
        # except Exception:
        #     # If signal isn't available for some reason, we'll still proceed — console messages will help
        #     logger.debug('Could not connect loadFinished signal')
        # # Connect additional lifecycle signals for better diagnostics
        # try:
        #     self.webview.loadStarted.connect(lambda: logger.info('QWebEngineView loadStarted'))
        # except Exception:
        #     logger.debug('Could not connect loadStarted')
        # try:
        #     self.webview.loadProgress.connect(lambda p: logger.info(f'QWebEngineView loadProgress {p}%'))
        # except Exception:
        #     logger.debug('Could not connect loadProgress')
        # try:
        #     self.webview.urlChanged.connect(lambda u: logger.info(f'QWebEngineView urlChanged: {u.toString()}'))
        # except Exception:
        #     logger.debug('Could not connect urlChanged')
        # # If the underlying QWebEnginePage exposes a renderProcessTerminated signal, connect to it
        # try:
        #     page = self.webview.page()
        #     if hasattr(page, 'renderProcessTerminated'):
        #         def _on_render_terminated(status, code):
        #             logger.error(f'Render process terminated (signal): status={status}, code={code}')
        #         try:
        #             page.renderProcessTerminated.connect(_on_render_terminated)
        #         except Exception:
        #             logger.debug('Could not connect page.renderProcessTerminated')
        # except Exception:
        #     logger.debug('Could not access webview.page() to connect renderProcessTerminated')
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

    # def _on_load_finished(self, ok: bool):
    #     """Handler connected to QWebEngineView.loadFinished to log status and capture HTML for debugging."""
    #     if not ok:
    #         logger.error("QWebEngineView reported loadFinished(False)")
    #     else:
    #         logger.info("QWebEngineView loadFinished(True) — fetching document HTML for debug")

    #     def _got_html(html: str):
    #         if html is None:
    #             logger.debug("runJavaScript returned no HTML")
    #         else:
    #             logger.debug(f"Document HTML length: {len(html)} characters")

    #     try:
    #         # Asynchronously retrieve the outer HTML to confirm content and surface script-clearing behavior
    #         self.webview.page().runJavaScript("document.documentElement.outerHTML", _got_html)
    #     except Exception as e:
    #         logger.exception("Error while running runJavaScript to fetch document HTML: %s", e)

    # @classmethod
    # def reorder_proceduretype_by_procedure(cls, proceduretype_dict: dict, procedure_dict: dict):
    #     for assoc in procedure_dict["procedurereagentlotassociation"]:
    #         reagentrole = assoc['reagentrole']
    #         reagent = assoc['reagent']
    #         reagentlot = assoc['reagentlot']
    #         try:
    #             pt_reagent = next(item['reagent'] for item in proceduretype_dict['reagentrole'] if item['name'] == reagentrole)
    #         except StopIteration:
    #             continue
    #         try:
    #             pt_reagentlots = next(item['reagentlot'] for item in pt_reagent if item['name'] == reagent)
    #         except StopIteration:
    #             continue
    #         rl_index = next((iii for iii, item in enumerate(pt_reagentlots) if item['name'] == reagentlot), 0)
    #         pt_reagentlots.insert(0, pt_reagentlots.pop(rl_index))
    #     for assoc in procedure_dict["procedureequipmentassociation"]:
    #         equipmentrole = assoc['equipmentrole']
    #         equipment = assoc['equipment']
    #         try:
    #             pt_equipment = next(item["equipmentroleequipmentassociation"] for item in proceduretype_dict['equipmentrole'] if item['name'] == equipmentrole)
    #         except StopIteration:
    #             continue
    #         eq_index = next((iii for iii, item in enumerate(pt_equipment) if item['equipment'] == equipment), 0)
    #         pt_equipment.insert(0, pt_equipment.pop(eq_index))
    #     return proceduretype_dict

    def set_html(self):
        # NOTE: Add --New-- as an option for reagents.
        # from backend.db.models import Run
        # for reagentrole in self.proceduretype_dict.get("reagentrole", []):
        #     for reagent in reagentrole['reagent']:
        #         if len(reagent['reagentlot']) < 1:
        #             reagent['reagentlot'].append(dict(name="", active=True))
        #         else:
        #             try:
        #                 reagent['reagentlot'].remove(dict(name="", active=True))
        #             except Exception:
        #                 pass
        #         try:
        #             check = "--New--" in (reagentlot['name'] for reagentlot in reagent['reagentlot'])
        #         except TypeError:
        #             check = True
        #         if not check:
        #             reagent['reagentlot'].append(dict(name="--New--", active=True))
        # regex = re.compile(r".*R\d$")
        # run = Run.query(name=self.run.rsl_plate_number, limit=1)
        # self.proceduretype_dict['previous'] = [""] + [item.name for item in run.procedure if item.proceduretype.name == self.proceduretype.name and not bool(regex.match(item.name))]
        html = render_details_template(
            template="procedure_creation",
            js_in=["procedure_form", "grid_drag", "context_menu"],
            proceduretype=self.proceduretype_dict,
            run=self.run.improved_dict,
            procedure=self.procedure,
            plate_map=self.plate_map,
            now = datetime.datetime.now()
        )
        
        self.webview.setHtml("<h1>TEST</h1><script>console.log('running');</script>")
        with open("created_procedure.html", "w") as f:
            f.write(html)

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
        reagentrole_idx, rr_dummy = get_index_of_value_in_dict_list(key="name", value=reagentrole, list_=self.proceduretype_dict['reagentrole'])
        reagent_idx, _ = get_index_of_value_in_dict_list(key="name", value=reagent, list_=rr_dummy['reagent'])
        self.proceduretype_dict['reagentrole'][reagentrole_idx]['reagent'][reagent_idx]['reagentlot'].insert(0, pyd)
        self.set_html()

    @pyqtSlot(str, str)
    @pyqtSlot(str, str, bool)
    def update_reagent(self, reagentrole: str, name_lot_expiry: str, checked:bool=True):
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

    def return_sql(self, new: bool = False):
        output = self.procedure.to_sql()
        if isinstance(output, tuple):
            output = output[0]
        return output
