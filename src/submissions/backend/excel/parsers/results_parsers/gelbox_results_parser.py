from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from backend.excel.parsers.results_parsers import DefaultResultsWidgetParser
from PIL.ImageFile import ImageFile
from PyQt6.QtWidgets import QGridLayout, QVBoxLayout

from backend.validators.pydant import PydProcedure

class GelBoxParser(DefaultResultsWidgetParser):

    def __init__(self, procedure: PydProcedure, img: ImageFile, results_type: str | None, *args, **kwargs) -> None:
        super().__init__(results_type, *args, **kwargs)
        self.procedure = procedure
        self.img = img
        from frontend.widgets import GelBox, ControlsForm
        self.gel_box = GelBox(parent=self, img=img)
        self.controls_form = ControlsForm(parent=self, control_info=[])
        layout = QVBoxLayout()
        layout.addWidget(self.gel_box, 0)
        layout.addWidget(self.controls_form, 1)
        self.setLayout(layout)