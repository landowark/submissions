from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from backend.excel.parsers.results_parsers import DefaultResultsWidgetParser
from PIL.ImageFile import ImageFile
from PyQt6.QtWidgets import QDialogButtonBox, QVBoxLayout
from tools import unc_to_mapped_drive_native

from backend.validators.pydant import PydProcedure

class GelBoxParser(DefaultResultsWidgetParser):
    """
    Widget to display gel images in a GUI dialog. 
    This class extends QDialog to provide a user interface for viewing parsed results data.

    :cvar pyd_name: Name of the Pydantic model associated with this parser.
    :type pyd_name: str
    :ivar procedure: The Pydantic model representing the procedure associated with the gel image.
    :type procedure: PydProcedure
    :ivar img: The gel image to be displayed in the dialog.
    :type img: ImageFile
    :ivar resultstype: The type of results to be parsed. If None, a default value will be used.
    :type resultstype: str | None
    :ivar *args: Additional positional arguments.
    :ivar **kwargs: Additional keyword arguments.
    """

    def __init__(self, procedure: PydProcedure, img: ImageFile, resultstype: str | None=None, *args, **kwargs):
        """
        :param procedure: The Pydantic model representing the procedure associated with the gel image.
        :type procedure: PydProcedure
        :param img: The gel image to be displayed in the dialog.
        :type img: ImageFile
        :param resultstype: The type of results to be parsed. If None, a default value will be used.
        :type resultstype: str | None
        :param *args: Additional positional arguments.
        :param **kwargs: Additional keyword arguments.
        """
        super().__init__(resultstype, *args, **kwargs)
        self.procedure = procedure
        self.img = img
        from frontend.widgets import GelBox, ControlsForm
        self.gel_box = GelBox(parent=self, img=self.img)
        self.controls_form = ControlsForm(parent=self, procedure=procedure, resultstype=resultstype)
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