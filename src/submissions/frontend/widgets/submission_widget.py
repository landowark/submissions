"""
Contains all procedure related frontend functions
"""
from __future__ import annotations
import sys, logging
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QSpinBox, QDoubleSpinBox,
    QComboBox, QDateEdit, QLineEdit, QLabel, QApplication
)
from PyQt6.QtCore import pyqtSignal, Qt
from .functions import select_open_file, select_save_file
from pathlib import Path
from tools import Report, Alert, main_form_style, report_result, get_application_from_parent
from backend.validators import PydClientSubmission, PydSample, SourcedField
from backend.db.models import (
    ClientLab
)
from pprint import pformat
from typing import List, Tuple, TYPE_CHECKING
from datetime import date
from .sample_checker import SampleChecker
if TYPE_CHECKING:
    from backend.db.models import ClientSubmission, SubmissionType

logger = logging.getLogger(f"submissions.{__name__}")


class MyQComboBox(QComboBox):
    """
    Custom combobox that disables wheel events until focussed on.
    """

    def __init__(self, scrollWidget=None, *args, **kwargs):
        super(MyQComboBox, self).__init__(*args, **kwargs)
        self.scrollWidget = scrollWidget
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, *args, **kwargs):
        if self.hasFocus():
            return QComboBox.wheelEvent(self, *args, **kwargs)
        else:
            return self.scrollWidget.wheelEvent(*args, **kwargs)


class MyQDateEdit(QDateEdit):
    """
    Custom date editor that disables wheel events until focussed on.
    """

    def __init__(self, scrollWidget=None, *args, **kwargs):
        super(MyQDateEdit, self).__init__(*args, **kwargs)
        self.scrollWidget = scrollWidget
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, *args, **kwargs):
        if self.hasFocus():
            return QDateEdit.wheelEvent(self, *args, **kwargs)
        else:
            return self.scrollWidget.wheelEvent(*args, **kwargs)


class MyQSpinBox(QSpinBox):

    def __init__(self, scrollWidget=None, *args, **kwargs):
        super(MyQSpinBox, self).__init__(*args, **kwargs)
        self.scrollWidget = scrollWidget
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, *args, **kwargs):
        if self.hasFocus():
            return QDateEdit.wheelEvent(self, *args, **kwargs)
        else:
            return self.scrollWidget.wheelEvent(*args, **kwargs)
        

class MyQDoubleSpinBox(QDoubleSpinBox):

    def __init__(self, scrollWidget=None, *args, **kwargs):
        super(MyQSpinBox, self).__init__(*args, **kwargs)
        self.scrollWidget = scrollWidget
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, *args, **kwargs):
        if self.hasFocus():
            return QDateEdit.wheelEvent(self, *args, **kwargs)
        else:
            return self.scrollWidget.wheelEvent(*args, **kwargs)
        

class SubmissionFormContainer(QWidget):
    # NOTE: A signal carrying a path
    import_drag = pyqtSignal(Path)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.app = self.parent().parent()
        self.setStyleSheet('background-color: light grey;')
        self.setAcceptDrops(True)
        # NOTE: if import_drag is emitted, importSubmission will fire
        self.import_drag.connect(lambda fname: self.import_submission_function(fname=fname))

    def dragEnterEvent(self, event):
        """
        Allow drag if file.
        """
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """
        Sets filename when file dropped
        """
        fname = Path([u.toLocalFile() for u in event.mimeData().urls()][0])
        self.app.last_dir = fname.parent
        self.import_drag.emit(fname)

    @report_result
    def import_submission_function(self, fname: Path | None = None) -> Report:
        """
        Import a new procedure to the app window

        Args:
            obj (QMainWindow): original app window

        Returns:
            Report: Object to give results of import.
        """
        from backend.managers import DefaultClientSubmissionManager
        self.app.raise_()
        self.app.activateWindow()
        logger.info(f"\n\nStarting Import...\n\n")
        report = Report()
        # NOTE: Clear any previous forms.
        try:
            self.form.setParent(None)
        except AttributeError:
            pass
        # NOTE: initialize sample
        self.samples = []
        self.missing_info = []
        # NOTE: set file dialog
        if isinstance(fname, bool) or fname is None:
            fname = select_open_file(self, file_extension="xlsx")
        if not fname:
            report.add_result(Alert(msg=f"File {fname.__str__()} not found.", status="critical"))
            return report
        # NOTE: create sheetparser using excel sheet and context from gui
        self.clientsubmission_manager = DefaultClientSubmissionManager(parent=self, input_object=fname)
        self.pydclientsubmission = self.clientsubmission_manager.to_pydantic()
        # blank samples have no id here.
        checker = SampleChecker(self, "Sample Checker", self.pydclientsubmission.sample)
        if checker.exec():
            try:
                assert isinstance(self.pydclientsubmission, PydClientSubmission)
            except AssertionError as e:
                logger.error(f"Got wrong type for {self.pydclientsubmission}: {type(self.pydclientsubmission)}")
                raise e
            self.form = self.pydclientsubmission.to_form(parent=self)
            self.layout().addWidget(self.form)
        else:
            message = "Submission cancelled."
            logger.warning(message)
            report.add_result(Alert(msg=message, owner=self.__class__.__name__, status="Warning"))
        return report

    
class SubmissionFormWidget(QWidget):
    
    def __init__(self, parent: QWidget, pyd: PydClientSubmission, disable: list | None = None) -> None:
        super().__init__(parent)
        from backend.db.models import Run, SubmissionType
        if disable is None:
            disable = []
        self.app = get_application_from_parent(parent)
        self.pyd = pyd
        # NOTE: pyd contains run up to this point.
        self.missing_info = []
        self.submissiontype = SubmissionType.query(name=self.pyd.submissiontype.get('value'))
        defaults = Run.get_default_info("form_recover", "form_ignore", submissiontype=self.pyd.submissiontype.get('value'))
        self.recover = defaults['form_recover']
        self.ignore = defaults['form_ignore']
        self.layout = QVBoxLayout()
        for k in list(self.pyd.__class__.model_fields.keys()):
            if k in self.ignore:
                # logger.warning(f"{k} in form_ignore {self.ignore}, not creating widget")
                continue
            try:
                check = k in disable
            except TypeError:
                check = False
            try:
                value = self.pyd.__getattribute__(k)
            except AttributeError as e:
                logger.error(f"Couldn't get attribute from pyd: {k} due to {e}")
                try:
                    value = self.pyd.model_extra[k]
                except KeyError:
                    value = dict(value=None, missing=True)
            add_widget = self.create_widget(key=k, value=value, submission_type=self.submissiontype,
                                            clientsubmission_object=pyd.sql_instance, disable=check)
            if add_widget is not None:
                self.layout.addWidget(add_widget)
        self.setStyleSheet(main_form_style)
        self.setLayout(self.layout)

    def disable_reagents(self):
        """
        Disables all ReagentFormWidgets in this form/
        """
        for reagent in self.findChildren(self.ReagentFormWidget):
            reagent.flip_check(self.disabler.checkbox.isChecked())

    def create_widget(self, key: str, value: dict, submission_type: str | SubmissionType | None = None,
                      clientsubmission_object: ClientSubmission | None = None, disable: bool = False) -> SubmissionFormWidget.InfoItem | None:
        """
        Make an InfoItem widget to hold a field

        Args:
            key (str): Name of the field
            value (dict): Value of field
            submission_type (str | None, optional): Submissiontype as str. Defaults to None.

        Returns:
            SubmissionFormWidget.InfoItem: Form widget to hold name:value
        """
        from backend.db.models import SubmissionType
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        if key not in self.ignore:
            return self.InfoItem(parent=self, key=key, value=value, submission_type=submission_type,
                                           clientsubmission_object=clientsubmission_object, disable=disable)
        return None

    def clear_form(self):
        """
        Removes all form widgets
        """
        for item in self.findChildren(QWidget):
            item.setParent(None)

    def export_csv_function(self, fname: Path | None = None):
        """
        Save the procedure's csv file.

        Args:
            fname (Path | None, optional): Input filename. Defaults to None.
        """
        if isinstance(fname, bool) or fname is None:
            fname = select_save_file(obj=self, default_name=self.pyd.export_filename, extension="csv")
        try:
            self.pyd.export_csv(fname)
        except PermissionError:
            logger.warning(f"Could not get permissions to {fname}. Possibly the request was cancelled.")
        except AttributeError:
            logger.error(f"No csv file found in the procedure at this point.")

    def parse_form(self) -> Report:
        """
        Transforms form info into PydSubmission

        Returns:
            Report: Report on status of parse.
        """
        report = Report()
        logger.info(f"Hello from form parser!")
        info = {}
        for widget in self.findChildren(QWidget):
            field, value = widget.parse_form()
            if field is not None:
                info[field] = value
        for item in self.recover:
            if hasattr(self, item):
                value = getattr(self, item)
                info[item] = value
        for k, v in info.items():
            self.pyd.__setattr__(k, v)
        report.add_result(report)
        return report

    class InfoItem(QWidget):

        def __init__(self, parent: QWidget, key: str, value: dict, submission_type: str | SubmissionType | None = None,
                     clientsubmission_object: ClientSubmission | None = None, disable: bool = False) -> None:
            from backend.db.models import SubmissionType
            super().__init__(parent)
            if isinstance(submission_type, str):
                submission_type = SubmissionType.query(name=submission_type)
            layout = QVBoxLayout()
            self.label = self.ParsedQLabel(key=key, value=value)
            self.input: QWidget = self.set_widget(parent=parent, key=key, value=value, submission_type=submission_type,
                                                  sub_obj=clientsubmission_object)
            self.setObjectName(key)
            try:
                self.missing: bool = value.missing
            except (TypeError, KeyError):
                self.missing: bool = True
            try:
                self.location: dict|None = value['location']
            except (TypeError, KeyError):
                self.location: dict|None = None
            if self.input is not None:
                layout.addWidget(self.label)
                layout.addWidget(self.input)
            layout.setContentsMargins(0, 0, 0, 0)
            self.setLayout(layout)
            self.input.setDisabled(disable)
            self.input.setToolTip("Widget disabled to protect database integrity.")
            match self.input:
                case QComboBox():
                    self.input.currentTextChanged.connect(self.update_missing)
                case QDateEdit():
                    self.input.dateChanged.connect(self.update_missing)
                case QLineEdit():
                    self.input.textChanged.connect(self.update_missing)

        def parse_form(self) -> Tuple[str, dict]:
            """
            Pulls info from widget into dict

            Returns:
                Tuple[str, dict]: name of field, {value, missing}
            """
            match self.input:
                case QLineEdit():
                    value = self.input.text()
                case QComboBox():
                    value = self.input.currentText()
                case QDateEdit():
                    value = self.input.date().toPyDate()
                case _:
                    return None, None
            return self.input.objectName(), dict(value=value, missing=self.missing, location=self.location)

        def set_widget(self, parent: QWidget, key: str, value: dict,
                       submission_type: str | SubmissionType | None = None, **kwargs) -> QWidget:
            """
            Creates form widget

            Args:
                parent (QWidget): parent widget
                key (str): name of field
                value (dict): value, and is it missing from scrape
                submission_type (str | None, optional): SubmissionType as str. Defaults to None.

            Returns:
                QWidget: Form object
            """
            from backend.db.models import ClientSubmission, SubmissionType, BaseClass
            if isinstance(submission_type, str):
                submission_type = SubmissionType.query(name=submission_type)
            if isinstance(value, dict):
                value = value.get('value', value)
            elif isinstance(value, SourcedField):
                value = value.value
            if issubclass(value.__class__, BaseClass):
                value = value.name
            match key:
                case 'clientlab':
                    add_widget = MyQComboBox(scrollWidget=parent)
                    # NOTE: lookup organizations suitable for clientlab (ctx: self.InfoItem.SubmissionFormWidget.SubmissionFormContainer.AddSubForm )
                    labs = [item.name for item in ClientLab.query()]
                    try:
                        looked_up_lab = ClientLab.query(name=value, limit=1)
                    except AttributeError:
                        looked_up_lab = None
                    if looked_up_lab:
                        try:
                            labs.remove(str(looked_up_lab.name))
                        except ValueError as e:
                            logger.error(f"Error reordering labs: {e}")
                        labs.insert(0, str(looked_up_lab.name))
                    # NOTE: set combobox values to lookedup values
                    add_widget.addItems(labs)
                    add_widget.setToolTip("Select submitting lab.")
                case 'submission_category':
                    add_widget = MyQComboBox(scrollWidget=parent)
                    categories = ['Diagnostic', "Surveillance", "Research"]
                    categories += [item.name for item in SubmissionType.query()]
                    try:
                        categories.insert(0, categories.pop(categories.index(value)))
                    except ValueError:
                        categories.insert(0, categories.pop(categories.index(submission_type.name)))
                    add_widget.addItems(categories)
                    add_widget.setToolTip("Enter procedure category or select from list.")
                    if value in categories:
                        add_widget.setCurrentIndex(categories.index(value))
                case _:
                    
                    field_type = ClientSubmission.determine_field_type(key)
                    match field_type:
                        case "TIMESTAMP":
                            add_widget = MyQDateEdit(calendarPopup=True, scrollWidget=parent)
                            # NOTE: sets submitted date based on date found in excel sheet
                            try:
                                add_widget.setDate(value)
                            # NOTE: if not found, use today
                            except (ValueError, TypeError):
                                add_widget.setDate(date.today())
                            add_widget.setToolTip(f"Select date for {key}")
                        case "INTEGER":
                            add_widget = MyQSpinBox(scrollWidget=parent)
                            try:
                                add_widget.setValue(value)
                            except (ValueError, TypeError):
                                add_widget.setValue(0)
                            add_widget.setToolTip(f"Set value for {key}")
                        case "RELATIONSHIPSCALAR":
                            add_widget = MyQComboBox(scrollWidget=parent)
                            # NOTE: lookup organizations suitable for clientlab (ctx: self.InfoItem.SubmissionFormWidget.SubmissionFormContainer.AddSubForm )
                            class_ = ClientSubmission.get_relationship_sqlclass(key)
                            labs = [item.name for item in class_.query()]
                            if isinstance(value, dict):
                                value = value['value']
                            if isinstance(value, class_):
                                value = value.name
                            try:
                                looked_up_value = class_.query(name=value, limit=1)
                            except AttributeError:
                                looked_up_value = None
                            if looked_up_value:
                                try:
                                    labs.remove(str(looked_up_value.name))
                                except ValueError as e:
                                    logger.error(f"Error reordering labs: {e}")
                                labs.insert(0, str(looked_up_value.name))
                            # NOTE: set combobox values to lookedup values
                            add_widget.addItems(labs)
                            add_widget.setToolTip(f"Select {key}.")
                        case "Invalid":
                            add_widget = None
                        case _:
                            add_widget = QLineEdit()
                            try:
                                add_widget.setText(value)
                            except (ValueError, TypeError):
                                add_widget.setText("NA")
                            add_widget.setToolTip(f"Set value for {key}")
            if add_widget is not None:
                add_widget.setObjectName(key)
                add_widget.setParent(parent)
            return add_widget

        def update_missing(self):
            """
            Set widget status to updated
            """
            self.missing = True
            self.label.updated(self.objectName())

        class ParsedQLabel(QLabel):

            def __init__(self, key: str, value: dict, title: bool = True, label_name: str | None = None):
                super().__init__()
                check = value.get('missing', True) if isinstance(value, dict) else True
                if label_name is not None:
                    self.setObjectName(label_name)
                else:
                    self.setObjectName(f"{key}_label")
                if title:
                    output = key.replace('_', ' ').title().replace("Rsl", "RSL").replace("Pcr", "PCR")
                else:
                    output = key.replace('_', ' ')
                if check:
                    self.setText(f"Parsed {output}")
                else:
                    self.setText(f"MISSING {output}")

            def updated(self, key: str, title: bool = True):
                """
                Mark widget as updated

                Args:
                    key (str): Name of the field
                    title (bool, optional): Use title case. Defaults to True.
                """
                if title:
                    output = key.replace('_', ' ').title().replace("Rsl", "RSL").replace("Pcr", "PCR")
                else:
                    output = key.replace('_', ' ')
                self.setText(f"UPDATED {output}")


class ClientSubmissionFormWidget(SubmissionFormWidget):

    def __init__(self, parent: QWidget, clientsubmission: PydClientSubmission, samples: List = [],
                 disable: list | None = None) -> None:
        super().__init__(parent, pyd=clientsubmission, disable=disable)
        try:
            self.disabler.setHidden(True)
        except AttributeError:
            pass
        self.sample = samples
        # NOTE: At this point, samples are pydsamples
        start_run_btn = QPushButton("Save")
        self.layout.addWidget(start_run_btn)
        start_run_btn.clicked.connect(self.create_new_submission)
        
    @report_result
    def parse_form(self) -> Report:
        """
        Transforms form info into PydSubmission

        Returns:
            Report: Report on status of parse.
        """
        report = Report()
        logger.info(f"Hello from client procedure form parser!")
        info = {}
        for widget in self.findChildren(QWidget):
            match widget:
                case self.InfoItem():
                    field, value = widget.parse_form()
                case _:
                    continue
            if field is not None:
                info[field] = value
        for item in self.recover:
            if hasattr(self, item):
                value = getattr(self, item)
                info[item] = value
        for k, v in info.items():
            if k == "sample":
                continue
            if isinstance(v, dict):
                v = v.get("value", None)
            self.pyd.__setattr__(k, v)
        # NOTE: run is okay at this point.
        report.add_result(report)
        return report

    def to_pydantic(self, *args):
        self.parse_form()
        output = self.pyd
        output.sample = [item for item in output.sample if PydSample.is_sample_id_valid(item)]
        # No duplicates here
        return output

    @report_result
    def create_new_submission(self, *args) -> Report:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            pyd = self.to_pydantic()
            # As of here, pyd.sample is as it is supposed to be
            logger.debug(f"Pyd.sample: {pformat(pyd.sample)}")
            sql: ClientSubmission = pyd.to_sql()
            if isinstance(sql, tuple):
                sql = sql[0]
            # As of here, sql.sample is empty
            logger.debug(f"SQL.sample: {pformat(sql.sample)}")
            # Remove any sample info accidentally left in misc_info by pyd.to_sql
            try:
                del sql._misc_info['sample']
            except KeyError:
                pass
            # By this point, sample_id is None for some reason.
            # Clear any pre-built association objects created by pyd.to_sql() so we can
            # re-create clean associations from the saved Sample SQL objects. This avoids
            # carrying over non-serializable _misc_info from pyd objects into the DB.
            sql.save()
            # self.app.table_widget.sub_wid.set_data()
            self.app.table_widget.sub_wid.upsert_submission(sql)
        finally:
            QApplication.restoreOverrideCursor()
            self.setParent(None)


__all__ = ["MyQComboBox", "MyQDateEdit", "MyQSpinBox", "MyQDoubleSpinBox", "SubmissionFormContainer", "SubmissionFormWidget", "ClientSubmissionFormWidget"]