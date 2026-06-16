"""

"""
from __future__ import annotations
from datetime import datetime
import logging, sys, json
from pprint import pformat
from typing import List, Generator, TYPE_CHECKING
from PyQt6.QtWidgets import (QDialog, QGridLayout, QDialogButtonBox)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import pyqtSlot
from tools import render_details_template, row_keys

if TYPE_CHECKING:
    from backend.db.models import Procedure

logger = logging.getLogger(f"submissions.{__name__}")


class ResultsSampleMatcher(QDialog):

    def __init__(self, parent, results_var_name: str, results: Generator[dict, None, None], samples:List[str],
                 procedure: Procedure, results_type: str):
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
        from backend.db.models import Results
        if ":" in sample:
            sample_id = sample.split(":")[0]
            well = sample.split(":")[1]
            row = row_keys[well[0]]
            column = int(well[1:])
        else:
            row = None
            column = None
        if isinstance(result, str):
            result = result.replace("'", '"')
            try:
                result = json.loads(result)
            except json.JSONDecodeError as e:
                logger.error(f"Could not decode string: {result} due to\n{e}")
                return
        association = next((assoc for assoc in self.procedure.proceduresampleassociation if assoc.sample.sample_id == sample_id and assoc.row==row and assoc.column==column), None)
        date_analyzed = result.pop("date_analyzed", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        if enabled:
            result = Results(sampleprocedureassociation=association, result=result, resultstype=self.results_type, date_analyzed=date_analyzed)
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
        association = next((assoc for assoc in self.procedure.proceduresampleassociation if assoc.sample.sample_id == sample_id and assoc.row==row and assoc.column==column), None)
        try:
            result = next(
                (item for item in self.output if str(item.result[self.results_var_name]) == result_text)
            )
        except StopIteration:
            logger.error(f"Couldn't find association for {result_text}")
            return
        result.sampleprocedureassociation = association


__all__ = ["ResultsSampleMatcher"]