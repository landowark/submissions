"""

"""
from __future__ import annotations

import json
import logging, sys
from pprint import pformat
from typing import List, Generator
from PyQt6.QtWidgets import (QDialog, QGridLayout, QDialogButtonBox)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import pyqtSlot
from tools import render_details_template, row_keys
from backend.db.models import Procedure, ProcedureSampleAssociation, Results

logger = logging.getLogger(f"submissions.{__name__}")

class ResultsSampleMatcher(QDialog):

    def __init__(self, parent, results_var_name: str, results: Generator[dict, None, None], samples:List[str],
                 procedure:Procedure, results_type: str):
        super().__init__(parent=parent)
        self.procedure = procedure
        self.results_type = results_type
        self.results_var_name = results_var_name
        results = [item for item in results]
        html = render_details_template("results_sample_match", results=results, results_var_name=self.results_var_name, samples=samples)
        self.webview = QWebEngineView()
        self.layout = QGridLayout()
        self.setLayout(self.layout)
        self.channel = QWebChannel()
        self.channel.registerObject('backend', self)
        self.webview.setHtml(html)
        self.webview.page().setWebChannel(self.channel)
        self.layout.addWidget(self.webview)
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout.addWidget(self.buttonBox)
        self.output = []

    @pyqtSlot(bool, str, str, str)
    def set_match(self, enabled: bool, sample: str, result_text:str, result: str):
        logger.debug(f"Sample: {sample}")
        if ":" in sample:
            sample_id = sample.split(":")[0]
            well = sample.split(":")[1]
            row = row_keys[well[0]]
            column = int(well[1:])
        else:
            row = None
            column = None
        result = "".join([r for r in result]).replace("\'", "\"")
        try:
            result = json.loads(result)
        except json.decoder.JSONDecoder:
            logger.error("Could not decode json.")
        logger.debug(f"Search: {self.procedure}, {sample_id}, {row}, {column}")
        association = ProcedureSampleAssociation.query(procedure=self.procedure, sample=sample_id, row=row, column=column)
        if enabled:
            result = Results(sampleprocedureassociation=association, result=result, result_type=self.results_type)
            self.output.append(result)
        else:
            try:
                result = next(
                    (item for item in self.output if str(item.result[self.results_var_name]) == result_text)
                )
            except StopIteration:
                logger.error(f"Couldn't find association for {result_text}")
                return
            self.output.remove(result)

    @pyqtSlot(str, str)
    def update_match(self, sample: str, result_text: str):
        if ":" in sample:
            sample_id = sample.split(":")[0]
            well = sample.split(":")[1]
            row = row_keys[well[0]]
            column = int(well[1:])
        else:
            row = None
            column = None
        logger.debug(f"Search: {self.procedure}, {sample_id}, {row}, {column}")
        association = ProcedureSampleAssociation.query(procedure=self.procedure, sample=sample_id, row=row, column=column)
        logger.debug(association)
        try:
            result = next(
                (item for item in self.output if str(item.result[self.results_var_name]) == result_text)
            )
        except StopIteration:
            logger.error(f"Couldn't find association for {result_text}")
            return
        result.sampleprocedureassociation = association
        logger.debug(f"Output: {pformat(self.output)}")
