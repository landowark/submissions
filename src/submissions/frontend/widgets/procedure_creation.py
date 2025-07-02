"""

"""
from __future__ import annotations

import datetime
import os
import sys, logging
from pathlib import Path
from pprint import pformat

from PyQt6.QtCore import pyqtSlot, Qt
from PyQt6.QtGui import QContextMenuEvent, QAction
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QDialog, QGridLayout, QMenu, QDialogButtonBox
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.db.models import Run, Procedure
    from backend.validators import PydProcedure
from tools import jinja_template_loading, get_application_from_parent, render_details_template

logger = logging.getLogger(f"submissions.{__name__}")


class ProcedureCreation(QDialog):

    def __init__(self, parent, procedure: PydProcedure, edit: bool = False):
        super().__init__(parent)
        self.edit = edit
        self.run = procedure.run
        self.procedure = procedure
        self.proceduretype = procedure.proceduretype
        self.setWindowTitle(f"New {self.proceduretype.name} for {self.run.rsl_plate_number}")
        # self.created_procedure = self.proceduretype.construct_dummy_procedure(run=self.run)
        self.procedure.update_kittype_reagentroles(kittype=self.procedure.possible_kits[0])
        # self.created_procedure.samples = self.run.constuct_sample_dicts_for_proceduretype(proceduretype=self.proceduretype)
        # logger.debug(f"Samples to map\n{pformat(self.created_procedure.samples)}")
        self.plate_map = self.proceduretype.construct_plate_map(sample_dicts=self.procedure.sample)
        # logger.debug(f"Plate map: {self.plate_map}")
        # logger.debug(f"Created dummy: {self.created_procedure}")
        self.app = get_application_from_parent(parent)
        self.webview = QWebEngineView(parent=self)
        self.webview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.webview.setMinimumSize(1200, 800)
        self.webview.setMaximumWidth(1200)
        # NOTE: Decide if exporting should be allowed.
        # self.webview.loadFinished.connect(self.activate_export)
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
        from .equipment_usage_2 import EquipmentUsage
        logger.debug(f"Edit: {self.edit}")
        proceduretype_dict = self.proceduretype.details_dict()
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
        html = render_details_template(
            template_name="procedure_creation",
            # css_in=['new_context_menu'],
            js_in=["procedure_form", "grid_drag", "context_menu"],
            proceduretype=proceduretype_dict,
            run=self.run.details_dict(),
            procedure=self.procedure.__dict__,
            plate_map=self.plate_map,
            edit=self.edit
        )
        with open("web.html", "w") as f:
            f.write(html)
        self.webview.setHtml(html)

    @pyqtSlot(str, str)
    def text_changed(self, key: str, new_value: str):
        logger.debug(f"New value for {key}: {new_value}")
        match key:
            case "rsl_plate_num":
                setattr(self.procedure.run, key, new_value)
            case _:
                attribute = getattr(self.procedure, key)
                attribute['value'] = new_value.strip('\"')

    @pyqtSlot(str, bool)
    def check_toggle(self, key: str, ischecked: bool):
        # logger.debug(f"{key} is checked: {ischecked}")
        setattr(self.procedure, key, ischecked)

    @pyqtSlot(str)
    def update_kit(self, kittype):
        self.procedure.update_kittype_reagentroles(kittype=kittype)
        logger.debug({k: v for k, v in self.procedure.__dict__.items() if k != "plate_map"})
        self.set_html()

    @pyqtSlot(list)
    def rearrange_plate(self, sample_list: list):
        self.procedure.update_samples(sample_list=sample_list)

    @pyqtSlot(str)
    def log(self, logtext: str):
        logger.debug(logtext)

    @pyqtSlot(str, str, str, str)
    def add_new_reagent(self, reagentrole: str, name: str, lot: str, expiry: str):
        from backend.validators.pydant import PydReagent
        expiry = datetime.datetime.strptime(expiry, "%Y-%m-%d")
        pyd = PydReagent(reagentrole=reagentrole, name=name, lot=lot, expiry=expiry)
        logger.debug(pyd)
        self.procedure.reagentrole[reagentrole].insert(0, pyd)
        logger.debug(pformat(self.procedure.__dict__))
        self.set_html()

    @pyqtSlot(str, str)
    def update_reagent(self, reagentrole:str, name_lot_expiry:str):
        try:
            name, lot, expiry = name_lot_expiry.split(" - ")
        except ValueError:
            return
        self.procedure.update_reagents(reagentrole=reagentrole, name=name, lot=lot, expiry=expiry)

    def return_sql(self):
        return self.procedure.to_sql()

# class ProcedureWebViewer(QWebEngineView):
#
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#
#     def contextMenuEvent(self, event: QContextMenuEvent):
# self.menu = self.page().createStandardContextMenu()
# self.menu = self.createStandardContextMenu()
# add_sample = QAction("Add Sample")
# self.menu = QMenu()
# self.menu.addAction(add_sample)
# self.menu.popup(event.globalPos())
