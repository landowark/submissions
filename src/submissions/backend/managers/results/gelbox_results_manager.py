"""
Module for pcr results from Design and Analysis Studio
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from datetime import datetime
from io import BytesIO
from pathlib import Path
from PIL import Image
from backend.validators.pydant import PydProcedure, PydResults
from backend.managers.results import DefaultImageManager
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.db.models import ResultsType


class GelManager(DefaultImageManager):

    resultstype = "Gel Box"

    def __init__(self, procedure: PydProcedure, parent, resultstype: str | ResultsType | None = None,
                input_object: Path | str | Image | None = None, ui=None):
        # NOTE: Set before super().__init__, which runs parse().
        if resultstype:
            self.resultstype = resultstype if isinstance(resultstype, str) else resultstype.name
        self.result = None
        self.image_png = None
        super().__init__(procedure, parent, input_object, ui=ui)

    def parse(self):
        """
        Shows the gel and its controls form; keeps the form values and the image (as PNG) if accepted.
        """
        self.result = self.ui.gel_results(procedure=self.procedure, image=self.input_object, resultstype=self.resultstype)
        if self.result is not None:
            buffer = BytesIO()
            self.input_object.save(buffer, format="PNG")
            self.image_png = buffer.getvalue()

    def procedure_to_pydantic(self) -> PydResults | None:
        """
        Gel results belong to the procedure as a whole. None if the form was cancelled.
        """
        if self.result is None:
            return None
        procedure = self.procedure.name.value if hasattr(self.procedure.name, "value") else self.procedure.name
        return PydResults(resultstype=self.resultstype, result=self.result, image=self.image_png,
                        procedure=procedure, date_analyzed=datetime.now(), is_sample=False)

    def samples_to_pydantic(self):
        yield from ()

# NOTE: add_results looks managers up as f"{results type name without spaces}Manager", i.e. GelBoxManager.
GelBoxManager = GelManager

__all__ = ["GelManager", "GelBoxManager"]