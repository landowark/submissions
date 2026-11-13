"""
Procedure creation/edit window for the web UI. Replaces frontend.widgets.procedure_creation.ProcedureCreation.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
import json
from datetime import datetime
from pprint import pformat
from typing import Callable, List
import webview
from tools import DictMode, render_details_template, find_first_matching_dict
from .modal import add_buttons
from .window_thread import WindowThread, on_window_thread


def plate_name(run) -> str:
    """
    The run's plate number for the window title, as ProcedureCreation.__init__ works it out.
    """
    from backend.validators import SourcedField
    plate = run.rsl_plate_number
    if isinstance(plate, dict):
        return plate.get("value", "Unknown Run")
    if isinstance(plate, SourcedField):
        return plate.value
    if isinstance(plate, str):
        return plate
    raise TypeError(f"Unrecognised type for run.rsl_plate_number: {type(plate)}")


def constructed_sample_list(procedure):
    """
    Port of ProcedureCreation.constructed_sample_list.
    """
    from backend.validators.pydant import PydSample, PydProcedureSampleAssociation
    for iii, sample in enumerate(procedure.sample, start=1):
        match sample:
            case PydSample():
                sample_id = sample.sample_id
            case PydProcedureSampleAssociation():
                sample_id = sample.sample.sample_id if isinstance(sample.sample, PydSample) else sample.sample
            case str():
                sample_id = sample
            case dict():
                sample_id = sample.get("sample_id", f"Unknown Sample {iii}")
            case _:
                sample_id = f"Unknown Sample {iii}"
        if isinstance(sample, dict):
            row, column, is_control = sample.get("row", 0), sample.get("column", 0), sample.get("is_control", 0)
        elif isinstance(sample, str):
            row, column, is_control = 0, 0, 0
        else:
            row, column, is_control = getattr(sample, "row", 0), getattr(sample, "column", 0), getattr(sample, "is_control", 0)
        yield dict(sample_id=sample_id, index=iii, row=row, column=column, is_control=is_control)


class ProcedureApi(object):
    """
    js_api for one procedure window. Method names match ProcedureCreation's Qt slots.

    Every @on_window_thread method runs on this window's thread; they must not call each other
    (the thread would wait on itself), so shared logic lives in plain _methods.
    """

    def __init__(self, ctx, edit: bool, on_done: Callable[[], None] | None = None):
        self._ctx = ctx
        self._window = None
        self._thread = WindowThread(ctx)
        self._edit = edit
        self._on_done = on_done
        self._procedure = None
        self._run = None
        self._proceduretype_dict = None
        self._platemap = None

    def _load(self, run_id: int | None, proceduretype_name: str | None, procedure_id: int | None) -> tuple[str, str]:
        """
        Builds the PydProcedure (on the window thread) and renders the first page.

        :return: Window title and html.
        """
        from backend.db.models import Run, Procedure
        from backend.validators.pydant import PydProcedureType
        session = self._ctx.database.session()
        if procedure_id is None:
            run = session.get(Run, run_id)
            procedure_type = next(pt for pt in run.allowed_procedures if pt.name == proceduretype_name)
            procedure = procedure_type.construct_dummy_procedure(run=run)
            if not procedure.sample or procedure.run is None:
                raise ValueError(f"Couldn't build a {proceduretype_name} procedure for {run.rsl_plate_number}.")
        else:
            procedure = session.get(Procedure, procedure_id).construct_pyd_procedure_for_creation()
        if not isinstance(procedure.proceduretype, PydProcedureType):
            raise TypeError(f"Unexpected procedure type: {procedure.proceduretype}")
        self._procedure = procedure
        self._run = procedure.run
        self._proceduretype_dict = procedure.reorder_proceduretype_by_procedure()
        self._platemap = self._proceduretype_dict['platemap']
        procedure.update_samples(sample_list=list(constructed_sample_list(procedure)))
        if not all(item.procedure_rank > 0 for item in procedure.sample):
            logger.error("Got some messed up samples here.")
        verb = "Edit" if self._edit else "New"
        return f"{verb} {procedure.proceduretype.name} for {plate_name(self._run)}", self._page()

    def _page(self) -> str:
        html = render_details_template(
            template="procedure_creation",
            js_in=["procedure_form", "grid_drag", "context_menu"],
            proceduretype=self._proceduretype_dict,
            run=self._run.improved_dict,
            procedure=self._procedure,
            platemap=self._platemap,
            now=datetime.now(),
            edit=self._edit,
        )
        return add_buttons(html)

    def _set_text(self, key: str, new_value: str) -> None:
        match key:
            case "rsl_plate_num":
                setattr(self._procedure.run, key, new_value)
            case "repeat_of":
                from backend.db.models import Procedure
                self._procedure.repeat_of = Procedure.query(name=new_value, limit=1)
            case _:
                attribute = getattr(self._procedure, key)
                match attribute:
                    case dict():
                        attribute['value'] = new_value.strip('\"')
                    case _:
                        setattr(self._procedure, key, new_value.strip('\"'))

    def _return_sql(self):
        """
        Port of ProcedureCreation.return_sql, raising instead of returning None.
        """
        from backend.validators import SourcedField
        if not self._procedure.sample:
            raise ValueError("The procedure has no samples.")
        if self._procedure.run is None:
            raise ValueError("The procedure has no run.")
        output = self._procedure.to_sql()
        if isinstance(output, tuple):
            output = output[0]
        expected_plate = self._run.rsl_plate_number
        if isinstance(expected_plate, SourcedField):
            expected_plate = expected_plate.value
        if output.run is None:
            raise ValueError("Procedure has no run after to_sql().")
        if output.run.rsl_plate_number != expected_plate:
            raise ValueError(f"Run mismatch: got {output.run.rsl_plate_number!r}, expected {expected_plate!r}")
        return output

    @on_window_thread
    def update_equipment(self, equipmentrole: str, equipment: str, processversion: str, tips, checked: bool = True) -> None:
        self._procedure.update_equipment(equipmentrole=equipmentrole, equipment=equipment,
                                        processversion=processversion, tips=tips, checked=checked)

    @on_window_thread
    def text_changed(self, key: str, new_value: str) -> None:
        self._set_text(key, new_value)

    @on_window_thread
    def update_date(self, key: str, new_value: str) -> None:
        self._set_text(key, new_value)

    @on_window_thread
    def check_toggle(self, key: str, ischecked: bool) -> None:
        setattr(self._procedure, key, ischecked)

    @on_window_thread
    def rearrange_plate(self, sample_list: List[dict]) -> None:
        logger.debug(pformat(sample_list))
        self._procedure.update_samples(sample_list=sample_list)

    def log(self, logtext: str) -> None:
        logger.debug(logtext)

    @on_window_thread
    def add_new_reagent(self, reagentrole: str, reagent: str, lot: str, expiry: str) -> None:
        from backend.validators.pydant import PydReagentLot
        from backend.db.models import ReagentLot
        expiry = datetime.combine(datetime.strptime(expiry, "%Y-%m-%d"), datetime.max.time())
        pyd = PydReagentLot(reagent=reagent, lot=lot, expiry=expiry, active=True)
        # NOTE: If the underlying SQL instance has not been saved yet, ensure a DB row exists.
        if getattr(pyd.sql_instance, "id", None) is None:
            existing_lot = ReagentLot.query(reagent=reagent, lot=lot, limit=1)
            if existing_lot:
                pyd.sql_instance = existing_lot
                existing_lot.active = True
            else:
                new_lot = ReagentLot(reagent=reagent, lot=lot, expiry=expiry, active=True)
                new_lot.save()
                pyd.sql_instance = new_lot
        reagentrole_idx, rr_dummy = find_first_matching_dict(key="name", value_to_match=reagentrole,
                                                            list_of_dicts=self._proceduretype_dict['reagentrole'],
                                                            mode=DictMode.INDEX)
        reagent_idx, _ = find_first_matching_dict(key="name", value_to_match=reagent,
                                                list_of_dicts=rr_dummy['reagent'], mode=DictMode.POP)
        self._proceduretype_dict['reagentrole'][reagentrole_idx]['reagent'][reagent_idx]['reagentlot'].insert(0, pyd)
        self._window.load_html(self._page())

    @on_window_thread
    def update_reagent(self, reagentrole: str, name_lot_expiry: str | List[str], checked: bool = True) -> None:
        if name_lot_expiry in ("", "--New--"):
            return
        if not isinstance(name_lot_expiry, list):
            name_lot_expiry = [name_lot_expiry]
        multiple = len(name_lot_expiry) > 1
        for item in name_lot_expiry:
            try:
                name, lot = item.split(" - ", 1)
            except ValueError as e:
                logger.exception(f"Could not split reagent name and lot from: {name_lot_expiry} due to {e}")
                continue
            self._procedure.update_reagents(reagentrole=reagentrole, name=name, lot=lot, checked=checked, multiple=multiple)

    @on_window_thread
    def get_reagent_names(self, reagentrole_name: str) -> list:
        from backend.db.models import ReagentRole
        reagentrole = ReagentRole.query(name=reagentrole_name, limit=1)
        if not reagentrole:
            return []
        return [getattr(item, "name", str(item)) for item in reagentrole.get_reagents(proceduretype=self._procedure.proceduretype)]

    @on_window_thread
    def get_reagentlot_names(self, reagentrole_name: str) -> list:
        from backend.db.models import ReagentRole
        role = ReagentRole.query(name=reagentrole_name, limit=1)
        if not role:
            return []
        # NOTE: Normalise proceduretype to the SQL-backed ProcedureType when possible
        proc_type = getattr(self._procedure.proceduretype, "sql_instance", self._procedure.proceduretype)
        assoc = next((item for item in role.reagentroleproceduretypeassociation if item.proceduretype == proc_type), None)
        names: list[str] = []
        for reagent in role.get_reagents(proceduretype=self._procedure.proceduretype):
            for lot in getattr(reagent, 'reagentlot', []):
                # NOTE: Lots may be SQL objects or, in fallback/pydantic cases, simple strings.
                if isinstance(lot, str):
                    names.append(lot)
                    continue
                lot_name = getattr(lot, 'name', None)
                if lot_name is not None and (getattr(lot, 'active', True) or lot_name in self._procedure.used_reagentlots):
                    names.append(lot_name)
        if assoc and getattr(assoc, 'last_used', None) is not None:
            names = assoc.bubble_last_used(reagentlot_list=names)
        return names

    @on_window_thread
    def get_selected_reagent(self, reagentrole_name: str) -> dict:
        assoc = next((a for a in self._procedure.reagentlot
                    if getattr(a.reagentrole, "name", a.reagentrole) == reagentrole_name), None)
        if not assoc:
            return {}
        return {"reagentlot": getattr(assoc.reagentlot, "name", assoc.reagentlot)}

    @on_window_thread
    def get_equipment_names(self, equipmentrole: str) -> list:
        from backend.db.models import EquipmentRole
        role = EquipmentRole.query(name=equipmentrole)
        if not role:
            return []
        return [eq.name for eq in role.equipment]

    @on_window_thread
    def get_processversion_names(self, equipmentrole: str, equipment: str) -> list:
        from backend.db.models import EquipmentRoleEquipmentAssociation
        assoc = EquipmentRoleEquipmentAssociation.query(equipmentrole=equipmentrole, equipment=equipment, limit=1)
        if not assoc:
            return []
        return [pv.name for process in assoc.process for pv in process.processversion if pv.active]

    @on_window_thread
    def get_tipslot_names(self, processversion: str) -> list:
        from backend.db.models import ProcessVersion
        pv = ProcessVersion.query(name=processversion, limit=1)
        if not pv or getattr(pv, "process", None) is None:
            return []
        return [lot.name for tips in pv.process.tips for lot in tips.tipslot if lot.active]

    @on_window_thread
    def get_selected_equipment(self, equipmentrole: str) -> dict:
        eoi = next((e for e in self._procedure.equipment if e.equipmentrole == equipmentrole), None)
        if not eoi:
            return {}
        return {
            "equipment": getattr(eoi.equipment, "name", eoi.equipment),
            "processversion": getattr(eoi.processversion, "name", eoi.processversion),
            "tipslot": [getattr(t, "name", t) for t in (eoi.tipslot or [])],
        }

    def run_preprocess_function(self, function_name: str) -> None:
        # NOTE: Broken in the Qt app too (ProcedureCreation.preprocessing_functions is commented out).
        logger.error(f"Preprocessing from the procedure form isn't available: {function_name}")

    @on_window_thread
    def accept(self) -> None:
        """
        OK: saves the procedure, as Run.add_procedure / Procedure.edit do after exec().
        """
        try:
            sql = self._return_sql()
            if not self._edit and len(sql.sample) != len(self._procedure.sample):
                raise ValueError(f"SQL object sample length {len(sql.sample)} did not equal "
                                f"input sample length {len(self._procedure.sample)}")
            sql.update_last_useds()
            sql.save()
        except Exception as e:
            logger.exception(f"Couldn't save procedure: {e}")
            message = json.dumps(f"Couldn't save procedure: {e}")
            self._window.evaluate_js(f"alert({message}); document.getElementById('modal-ok').disabled = false;")
            return
        self._window.destroy()
        if self._on_done:
            self._on_done()

    def cancel(self) -> None:
        self._window.destroy()  


def open_procedure_window(ctx, run_id: int | None = None, proceduretype_name: str | None = None,
                        procedure_id: int | None = None, on_done: Callable[[], None] | None = None) -> None:
    """
    Opens a procedure window: a new procedure (run_id + proceduretype_name) or an edit (procedure_id).
    """
    api = ProcedureApi(ctx, edit=procedure_id is not None, on_done=on_done)
    try:
        title, html = api._thread.run(api._load, run_id, proceduretype_name, procedure_id)
    except Exception:
        api._thread.close()
        raise
    api._window = webview.create_window(title, html=html, js_api=api, width=1300, height=900)
    api._window.events.closed += api._thread.close