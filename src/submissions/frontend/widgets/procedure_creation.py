"""

"""
from __future__ import annotations

import os
import sys, logging
from pathlib import Path
from pprint import pformat

from PyQt6.QtCore import pyqtSlot, Qt
from PyQt6.QtGui import QContextMenuEvent, QAction
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QDialog, QGridLayout, QMenu
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.db.models import Run, ProcedureType
from tools import jinja_template_loading, get_application_from_parent, render_details_template
from backend.validators import PydProcedure

logger = logging.getLogger(f"submissions.{__name__}")


class ProcedureCreation(QDialog):

    def __init__(self, parent, run: Run, proceduretype: ProcedureType):
        super().__init__(parent)
        self.run = run
        self.proceduretype = proceduretype
        self.setWindowTitle(f"New {proceduretype.name} for { run.rsl_plate_num }")
        self.created_procedure = self.proceduretype.construct_dummy_procedure(run=self.run)
        self.created_procedure.update_kittype_reagentroles(kittype=self.created_procedure.possible_kits[0])
        self.created_procedure.samples = self.run.constuct_sample_dicts_for_proceduretype(proceduretype=self.proceduretype)
        # logger.debug(f"Samples to map\n{pformat(self.created_procedure.samples)}")
        self.plate_map = self.proceduretype.construct_plate_map(sample_dicts=self.created_procedure.samples)
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

    def set_html(self):
        html = render_details_template(
            template_name="procedure_creation",
            # css_in=['new_context_menu'],
            js_in=["procedure_form", "grid_drag", "context_menu"],
            proceduretype=self.proceduretype.as_dict,
            run=self.run.to_dict(),
            procedure=self.created_procedure.__dict__,
            plate_map=self.plate_map
        )
        with open("procedure.html", "w") as f:
            f.write(html)
        self.webview.setHtml(html)

    @pyqtSlot(str, str)
    def text_changed(self, key: str, new_value: str):
        # logger.debug(f"New value for {key}: {new_value}")
        attribute = getattr(self.created_procedure, key)
        attribute['value'] = new_value

    @pyqtSlot(str, bool)
    def check_toggle(self, key: str, ischecked: bool):
        # logger.debug(f"{key} is checked: {ischecked}")
        setattr(self.created_procedure, key, ischecked)

    @pyqtSlot(str)
    def update_kit(self, kittype):
        self.created_procedure.update_kittype_reagentroles(kittype=kittype)
        logger.debug({k: v for k, v in self.created_procedure.__dict__.items() if k != "plate_map"})
        self.set_html()

    @pyqtSlot(list)
    def rearrange_plate(self, sample_list: list):
        self.created_procedure.update_samples(sample_list=sample_list)

    @pyqtSlot(str)
    def log(self, logtext: str):
        logger.debug(logtext)


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
