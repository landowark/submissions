"""
Main module to construct the procedure form
"""
from __future__ import annotations
import sys, logging, datetime
from pprint import pformat
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import pyqtSlot, QVariant, Qt
from typing import TYPE_CHECKING, List
from backend.validators import SourcedField
if TYPE_CHECKING:
    from backend.validators import PydProcedure
from . import DefaultWebDialog
from tools import render_details_template, find_first_matching_dict

logger = logging.getLogger(f"submissions.{__name__}")


class ProcedureCreation(DefaultWebDialog):

    def __init__(self, parent, procedure: PydProcedure, edit: bool = False):
        from backend.validators.pydant import PydProcedureType
        super().__init__(parent)
        self.edit = edit
        self.run = procedure.run
        assert self.run is not None
        self.procedure = procedure
        self.proceduretype = procedure.proceduretype
        self.preprocessing_functions = {i[0]: {"function": i[1], "resultstype": i[2]} for i in self.proceduretype.preprocessing_methods}
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
        self.platemap = self.proceduretype_dict['platemap']
        self.procedure.update_samples(sample_list=[sample for sample in self.constructed_sample_list])
        self.set_html()

    @property
    def constructed_sample_list(self):
        from backend.validators.pydant import PydSample, PydProcedureSampleAssociation
        for iii, sample in enumerate(self.procedure.sample, start=1):
            match sample:
                case PydSample():
                    sample_id = sample.sample_id
                    row = getattr(sample, "row", 0)
                    column = getattr(sample, "column", 0)
                    is_control = getattr(sample, "is_control", 0)
                case PydProcedureSampleAssociation():
                    sample_id = sample.sample
                    row = getattr(sample, "row", 0)
                    column = getattr(sample, "column", 0)
                    is_control = getattr(sample, "is_control", 0)
                case str():
                    sample_id = sample
                    row = 0
                    column = 0
                    is_control = 0
                case dict():
                    sample_id = sample.get("sample_id", f"Unknown Sample {iii}")
                    row = sample.get("row", 0)
                    column = sample.get("column", 0)
                    is_control = sample.get("is_control", 0)
                case _:
                    sample_id = f"Unknown Sample {iii}"
                    row = 0
                    column = 0
                    is_control = 0
            output = dict(sample_id=sample_id, index=iii, row=row, column=column, is_control=is_control)
            yield output

    def set_html(self):
        html = render_details_template(
            template="procedure_creation",
            js_in=["procedure_form", "grid_drag", "context_menu"],
            proceduretype=self.proceduretype_dict,
            run=self.run.improved_dict,
            procedure=self.procedure,
            platemap=self.platemap,
            now = datetime.datetime.now(),
            preprocessing_buttons = [item for item in self.preprocessing_functions.keys()],
            edit=self.edit
        )
        self.webview.setHtml(html)
        
    @pyqtSlot(str, str, str, QVariant)
    @pyqtSlot(str, str, str, QVariant, bool)
    def update_equipment(self, equipmentrole: str, equipment: str, processversion: str, tips: str, checked: bool=True):
        logger.debug(f"Updating equipment with role {equipmentrole}, equipment {equipment}, processversion {processversion}, tips {tips}, checked {checked}")
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
        logger.debug(f"Checkbox toggled: {key} set to {ischecked}")
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
        from backend.db.models import ReagentLot
        logger.debug(f"Adding new reagent with role {reagentrole}, reagent {reagent}, lot {lot}, expiry {expiry}")
        expiry = datetime.datetime.strptime(expiry, "%Y-%m-%d")
        expiry = datetime.datetime.combine(expiry, datetime.datetime.max.time())

        pyd = PydReagentLot(reagent=reagent, lot=lot, expiry=expiry, active=True)

        # If the underlying SQL instance has not been saved yet, ensure a DB row exists.
        if getattr(pyd.sql_instance, "id", None) is None:
            existing_lot = ReagentLot.query(reagent=reagent, lot=lot, limit=1)
            if existing_lot:
                pyd.sql_instance = existing_lot
            else:
                new_lot = ReagentLot(reagent=reagent, lot=lot, expiry=expiry, active=True)
                new_lot.save()
                pyd.sql_instance = new_lot

        reagentrole_idx, rr_dummy = find_first_matching_dict(key="name", value_to_match=reagentrole, list_of_dicts=self.proceduretype_dict['reagentrole'], mode="index")
        reagent_idx, _ = find_first_matching_dict(key="name", value_to_match=reagent, list_of_dicts=rr_dummy['reagent'], mode="index")
        self.proceduretype_dict['reagentrole'][reagentrole_idx]['reagent'][reagent_idx]['reagentlot'].insert(0, pyd)
        self.set_html()

    @pyqtSlot(str, str)
    @pyqtSlot(str, str, bool)
    def update_reagent(self, reagentrole: str, name_lot_expiry: str, checked:bool=True):
        logger.debug(f"Updating reagent with role {reagentrole}, name_lot_expiry {name_lot_expiry}, checked {checked}")
        try:
            name, lot = name_lot_expiry.split(" - ", 1)
        except ValueError as e:
            raise ValueError(f"Could not split reagent name and lot from: {name_lot_expiry} due to {e}")
        self.procedure.update_reagents(reagentrole=reagentrole, name=name, lot=lot, checked=checked)
        # logger.debug(f"Reagent update complete. Current reagents: {pformat(self.procedure.reagentlot)}")

    @pyqtSlot(str, result=list)
    def get_reagent_names(self, reagentrole_name: str):
        from backend.db.models import ReagentRole
        reagentrole = ReagentRole.query(name=reagentrole_name)
        return [item.name for item in reagentrole.get_reagents(proceduretype=self.procedure.proceduretype)]
    
    @pyqtSlot(str)
    def run_preprocess_function(self, function_name):
        over = self.preprocessing_functions.get(function_name, None)
        if over:
            func = over['function']
            resultstype = over['resultstype']
        else:
            raise ValueError(f"Function group for {function_name} not found.")
        self.dlg = func(parent=self.app, resultstype=resultstype, procedure=self.procedure)

    def return_sql(self, new: bool = False):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        logger.debug("Converting procedure to SQL...")
        logger.debug(f"Current procedure state before to_sql: {pformat(self.procedure.__dict__)}")
        try:
            assert self.procedure.run is not None
            output = self.procedure.to_sql()
            if isinstance(output, tuple):
                output = output[0]
            # logger.debug(f"Output from to_sql: {pformat(output.to_pydantic().improved_dict)}")
            # self.run is a PydRun; rsl_plate_number is a SourcedField[str], not a bare str
            expected_plate = self.run.rsl_plate_number
            if isinstance(expected_plate, SourcedField):
                expected_plate = expected_plate.value
            
            assert output.run is not None, "Procedure has no run after to_sql()"
            assert output.run.rsl_plate_number == expected_plate, (
                f"Run mismatch: got {output.run.rsl_plate_number!r}, expected {expected_plate!r}"
            )
        finally:
            QApplication.restoreOverrideCursor()
        return output
