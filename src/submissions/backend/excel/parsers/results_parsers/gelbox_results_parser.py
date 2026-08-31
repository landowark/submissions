from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from backend.excel.parsers.results_parsers import DefaultResultsWidgetParser
from PIL.ImageFile import ImageFile
from PyQt6.QtWidgets import QDialogButtonBox, QGridLayout, QVBoxLayout
from tools import unc_to_mapped_drive_native

from backend.validators.pydant import PydProcedure

class GelBoxParser(DefaultResultsWidgetParser):

    def __init__(self, procedure: PydProcedure, img: ImageFile, results_type: str | None=None, *args, **kwargs) -> None:
        super().__init__(results_type, *args, **kwargs)
        self.procedure = procedure
        self.img = img
        from frontend.widgets import GelBox, ControlsForm
        self.gel_box = GelBox(parent=self, img=self.img)
        self.controls_form = ControlsForm(parent=self, procedure=procedure, resultstype=results_type)
        layout = QVBoxLayout()
        layout.addWidget(self.gel_box, stretch=5)
        layout.addWidget(self.controls_form, stretch=1)
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox)
        self.setLayout(layout)
        self.setWindowTitle(unc_to_mapped_drive_native(self.img.filename))


__all__ = ['GelBoxParser']