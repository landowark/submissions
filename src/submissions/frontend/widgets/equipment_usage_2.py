'''
Creates forms that the user can enter equipment info into.
'''
from pprint import pformat
from PyQt6.QtCore import Qt, QSignalBlocker, pyqtSlot
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QDialog, QComboBox, QCheckBox, QLabel, QWidget, QVBoxLayout, QDialogButtonBox, QGridLayout
)
from backend.db.models import Equipment, Run, Process, Procedure, Tips
from backend.validators.pydant import PydEquipment, PydEquipmentRole, PydTips, PydProcedure
import logging
from typing import Generator

from tools import get_application_from_parent, render_details_template, flatten_list

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
        # self.webview.loadFinished.connect(self.activate_export)
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
        proceduretype_dict['equipment_json'] = flatten_list([item['equipment_json'] for item in proceduretype_dict['equipment']])
        # proceduretype_dict['equipment_json'] = [
        #     {'name': 'Liquid Handler', 'equipment': [
        #         {'name': 'Other', 'asset_number': 'XXX', 'processes': [
        #             {'name': 'Trust Me', 'tips': ['Blah']},
        #             {'name': 'No Me', 'tips': ['Blah', 'Crane']}
        #         ]
        #          },
        #         {'name': 'Biomek', 'asset_number': '5015530', 'processes': [
        #             {'name': 'Sample Addition', 'tips': ['Axygen 20uL']
        #              }
        #         ]
        #          }
        #     ]
        #      }
        # ]
        # if procedure.equipment:
        #     for equipmentrole in proceduretype_dict['equipment']:
        #         # NOTE: Check if procedure equipment is present and move to head of the list if so.
        #         try:
        #             relevant_procedure_item = next((equipment for equipment in procedure.equipment if
        #                                             equipment.equipmentrole == equipmentrole['name']))
        #         except StopIteration:
        #             continue
        #         item_in_er_list = next((equipment for equipment in equipmentrole['equipment'] if
        #                                 equipment['name'] == relevant_procedure_item.name))
        #         equipmentrole['equipment'].insert(0, equipmentrole['equipment'].pop(
        #             equipmentrole['equipment'].index(item_in_er_list)))
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
        logger.debug(pformat(sql.__dict__))
        # import pickle
        # with open("sql.pickle", "wb") as f:
        #     pickle.dump(sql, f)
        # with open("pyd.pickle", "wb") as f:
        #     pickle.dump(self.procedure, f)
        sql.save()
