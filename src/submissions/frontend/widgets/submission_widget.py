"""
Contains all procedure related frontend functions
"""
from __future__ import annotations
import sys, logging
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QSpinBox, QDoubleSpinBox,
    QComboBox, QDateEdit, QLineEdit, QLabel
)
from PyQt6.QtCore import pyqtSignal, Qt
from .functions import select_open_file, select_save_file
from pathlib import Path
from tools import Report, Alert, main_form_style, report_result, get_application_from_parent
from backend.validators import PydClientSubmission
from backend.db.models import (
    ClientLab, SubmissionType
)
from pprint import pformat
from typing import List, Tuple, TYPE_CHECKING
from datetime import date
from .sample_checker import SampleChecker
if TYPE_CHECKING:
    from backend.db.models import ClientSubmission

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
    update_reagent_fields = ['kittype']

    def __init__(self, parent: QWidget, pyd: PydClientSubmission, disable: list | None = None) -> None:
        super().__init__(parent)
        from backend.db.models import Run
        if disable is None:
            disable = []
        self.app = get_application_from_parent(parent)
        self.pyd = pyd
        # NOTE: pyd contains run up to this point.
        # logger.debug(pformat(self.pyd.__dict__))
        self.missing_info = []
        self.submissiontype = SubmissionType.query(name=self.pyd.submissiontype.get('value'))
        defaults = Run.get_default_info("form_recover", "form_ignore", submissiontype=self.pyd.submissiontype.get('value'))
        self.recover = defaults['form_recover']
        self.ignore = defaults['form_ignore']
        self.layout = QVBoxLayout()
        for k in list(self.pyd.__class__.model_fields.keys()):
            if k in self.ignore:
                logger.warning(f"{k} in form_ignore {self.ignore}, not creating widget")
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
                                            # run_object=Run(), disable=check)
                                            clientsubmission_object=pyd.sql_instance, disable=check)
            if add_widget is not None:
                self.layout.addWidget(add_widget)
            # if k in self.__class__.update_reagent_fields:
            #     add_widget.input.currentTextChanged.connect(self.scrape_reagents)
            #     self.disabler = self.DisableReagents(self)
            #     self.disabler.checkbox.setChecked(True)
            #     self.layout.addWidget(self.disabler)
            #     self.disabler.checkbox.checkStateChanged.connect(self.disable_reagents)
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
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        if key not in self.ignore:
            # match value:
            #     case PydReagent():
            #         if value.name.lower() != "not applicable":
            #             widget = self.ReagentFormWidget(parent=self, reagent=value, extraction_kit=extraction_kit)
            #         else:
            #             widget = None
            #     case _:
            #         widget = self.InfoItem(parent=self, key=key, value=value, submission_type=submission_type,
            #                                clientsubmission_object=clientsubmission_object)
            # if disable:
            #     widget.input.setEnabled(False)
            #     widget.input.setToolTip("Widget disabled to protect database integrity.")
            return self.InfoItem(parent=self, key=key, value=value, submission_type=submission_type,
                                           clientsubmission_object=clientsubmission_object, disable=disable)
        return None

    # @report_result
    # def scrape_reagents(self, *args, **kwargs):  #kittype:str, caller:str|None=None):
    #     """
    #     Extracted scrape reagents function that will procedure when
    #     form 'kittype' widget is updated.

    #     Args:
    #         obj (QMainWindow): updated main application
    #         extraction_kit (str): name of extraction kittype (in 'kittype' widget)

    #     Returns:
    #         Tuple[QMainWindow, dict]: Updated application and result
    #     """
    #     self.extraction_kit = args[0]
    #     report = Report()
    #     # NOTE: Remove previous reagent widgets
    #     try:
    #         old_reagents = self.find_widgets()
    #     except AttributeError:
    #         logger.error(f"Couldn't find old reagents.")
    #         old_reagents = []
    #     for reagent in old_reagents:
    #         if isinstance(reagent, self.ReagentFormWidget) or isinstance(reagent, QPushButton):
    #             reagent.setParent(None)
    #     reagents, integrity_report, missing_reagents = self.pyd.check_kit_integrity(extraction_kit=self.extraction_kit)
    #     expiry_report = self.pyd.check_reagent_expiries(exempt=missing_reagents)
    #     for reagent in reagents:
    #         add_widget = self.ReagentFormWidget(parent=self, reagent=reagent, extraction_kit=self.extraction_kit)
    #         self.layout.addWidget(add_widget)
    #     report.add_result(integrity_report)
    #     report.add_result(expiry_report)
    #     if hasattr(self.pyd, "csv"):
    #         export_csv_btn = QPushButton("Export CSV")
    #         export_csv_btn.setObjectName("export_csv_btn")
    #         self.layout.addWidget(export_csv_btn)
    #         export_csv_btn.clicked.connect(self.export_csv_function)
    #     submit_btn = QPushButton("Submit")
    #     submit_btn.setObjectName("submit_btn")
    #     self.layout.addWidget(submit_btn)
    #     submit_btn.clicked.connect(self.submit_new_sample_function)
    #     self.setLayout(self.layout)
    #     self.disabler.checkbox.setChecked(True)
    #     return report

    def clear_form(self):
        """
        Removes all form widgets
        """
        for item in self.findChildren(QWidget):
            item.setParent(None)

    
    # @report_result
    # def submit_new_sample_function(self, *args) -> Report:
    #     """
    #     Parse forms and add sample to the database.

    #     Args:
    #         obj (QMainWindow): original app window

    #     Returns:
    #         Tuple[QMainWindow, dict]: Collection of new main app window and result dict
    #     """
    #     logger.info(f"\n\nBeginning Submission\n\n")
    #     report = Report()
    #     result = self.parse_form()
    #     report.add_result(result)
    #     base_submission = self.pyd.to_sql()
    #     # NOTE: check output message for issues
    #     if base_submission is None:
    #         return
    #     for reagent in base_submission.reagents:
    #         reagent.update_last_used(kit=base_submission.extraction_kit)
    #     save_output = base_submission.save()
    #     # NOTE: update summary sheet
    #     self.app.table_widget.sub_wid.set_data()
    #     # NOTE: reset form
    #     try:
    #         check = save_output.results == []
    #     except AttributeError:
    #         logger.error(f"No save output, check passes")
    #         check = True
    #     if check:
    #         self.setParent(None)
    #     return report

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
        # reagents = []
        for widget in self.findChildren(QWidget):
            # match widget:
                # case self.ReagentFormWidget():
                #     reagent = widget.parse_form()
                #     if reagent is not None:
                #         reagents.append(reagent)
                #     else:
                #         report.add_result(Alert(msg="Failed integrity check", status="Critical"))
                #         return report
                # case self.InfoItem():
            field, value = widget.parse_form()
            if field is not None:
                info[field] = value
        # self.pyd.reagents = reagents
        for item in self.recover:
            if hasattr(self, item):
                value = getattr(self, item)
                info[item] = value
        for k, v in info.items():
            self.pyd.__setattr__(k, v)
        logger.debug(f"Got info from form: {pformat(self.pyd.__dict__)}")
        report.add_result(report)
        return report

    class InfoItem(QWidget):

        def __init__(self, parent: QWidget, key: str, value: dict, submission_type: str | SubmissionType | None = None,
                     clientsubmission_object: ClientSubmission | None = None, disable: bool = False) -> None:
            super().__init__(parent)
            if isinstance(submission_type, str):
                submission_type = SubmissionType.query(name=submission_type)
            layout = QVBoxLayout()
            self.label = self.ParsedQLabel(key=key, value=value)
            self.input: QWidget = self.set_widget(parent=parent, key=key, value=value, submission_type=submission_type,
                                                  sub_obj=clientsubmission_object)
            self.setObjectName(key)
            try:
                self.missing: bool = value['missing']
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
                       submission_type: str | SubmissionType | None = None,
                       sub_obj: ClientSubmission | None = None) -> QWidget:
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
            from backend.db.models import ClientSubmission
            if isinstance(submission_type, str):
                submission_type = SubmissionType.query(name=submission_type)
            if isinstance(value, dict):
                value = value.get('value', value)
            obj = parent.parent().parent()
            match key:
                case 'clientlab':
                    add_widget = MyQComboBox(scrollWidget=parent)
                    # NOTE: lookup organizations suitable for clientlab (ctx: self.InfoItem.SubmissionFormWidget.SubmissionFormContainer.AddSubForm )
                    labs = [item.name for item in ClientLab.query()]
                    if isinstance(value, dict):
                        value = value['value']
                    if isinstance(value, ClientLab):
                        value = value.name
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
                        categories.insert(0, categories.pop(categories.index(submission_type)))
                    add_widget.addItems(categories)
                    add_widget.setToolTip("Enter procedure category or select from list.")
                case _:
                    
                    field_type = ClientSubmission.determine_field_type(key)
                    match field_type:
                        case "TIMESTAMP":
                            add_widget = MyQDateEdit(calendarPopup=True, scrollWidget=parent)
                            # NOTE: sets submitted date based on date found in excel sheet
                            try:
                                add_widget.setDate(value)
                            # NOTE: if not found, use today
                            except:
                                add_widget.setDate(date.today())
                            add_widget.setToolTip(f"Select date for {key}")
                        case "INTEGER":
                            add_widget = MyQSpinBox(scrollWidget=parent)
                            try:
                                add_widget.setValue(value)
                            except:
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
                            except:
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
                try:
                    check = not value['missing']
                except:
                    check = True
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

    # class ReagentFormWidget(QWidget):

    #     def __init__(self, parent: QWidget, reagent: PydReagent, extraction_kit: str):
    #         super().__init__(parent)
    #         self.parent = parent
    #         self.app = get_application_from_parent(parent)
    #         self.reagent = reagent
    #         self.extraction_kit = extraction_kit
    #         layout = QGridLayout()
    #         self.check = QCheckBox()
    #         self.check.setChecked(True)
    #         self.check.checkStateChanged.connect(self.disable)
    #         layout.addWidget(self.check, 0, 0, 1, 1)
    #         self.label = self.ReagentParsedLabel(reagent=reagent)
    #         layout.addWidget(self.label, 0, 1, 1, 9)
    #         self.lot = self.ReagentLot(scrollWidget=parent, reagent=reagent, extraction_kit=extraction_kit)
    #         layout.addWidget(self.lot, 1, 0, 1, 10)
    #         # NOTE: Remove spacing between reagents
    #         layout.setContentsMargins(0, 0, 0, 0)
    #         self.setLayout(layout)
    #         self.setObjectName(reagent.name)
    #         self.missing = reagent.missing
    #         # NOTE: If changed set self.missing to True and update self.label
    #         self.lot.currentTextChanged.connect(self.updated)

    #     def flip_check(self, checked: bool):
    #         with QSignalBlocker(self.check) as b:
    #             self.check.setChecked(checked)
    #             self.lot.setEnabled(checked)
    #             self.label.setEnabled(checked)

    #     def disable(self):
    #         self.lot.setEnabled(self.check.isChecked())
    #         self.label.setEnabled(self.check.isChecked())
    #         with QSignalBlocker(self.parent.disabler.checkbox) as blocker:
    #             if any([item.lot.isEnabled() for item in self.parent.findChildren(self.__class__)]):
    #                 self.parent.disabler.checkbox.setChecked(True)
    #             else:
    #                 self.parent.disabler.checkbox.setChecked(False)

    #     @report_result
    #     def parse_form(self) -> Tuple[PydReagent | None, Report]:
    #         """
    #         Pulls form info into PydReagent

    #         Returns:
    #             Tuple[PydReagent, dict]: PydReagent and Report(?)
    #         """
    #         report = Report()
    #         if not self.lot.isEnabled():
    #             return None, report
    #         lot = self.lot.currentText()
    #         wanted_reagent, new = Reagent.query_or_create(lot=lot, role=self.reagent.role, expiry=self.reagent.expiry)
    #         # NOTE: if reagent doesn't exist in database, offer to add it (uses App.add_reagent)
    #         if new:
    #             dlg = QuestionAsker(title=f"Add {lot}?",
    #                                 message=f"Couldn't find reagent type {self.reagent.role}: {lot} in the database.\n\nWould you like to add it?")
    #             if dlg.exec():
    #                 wanted_reagent = self.parent.parent().add_reagent(instance=wanted_reagent)
    #                 return wanted_reagent, report
    #             else:
    #                 # NOTE: In this case we will have an empty reagent and the procedure will fail kittype integrity check
    #                 return None, report
    #         else:
    #             # NOTE: Since this now gets passed in directly from the clientsubmissionparser -> pydclientsubmission -> form and the clientsubmissionparser gets the name from the db, it should no longer be necessary to query the db with reagent/kittype, but with rt name directly.
    #             rt = ReagentRole.query(name=self.reagent.role)
    #             if rt is None:
    #                 rt = ReagentRole.query(kittype=self.extraction_kit, reagent=wanted_reagent)
    #             final = PydReagent(name=wanted_reagent.name, lot=wanted_reagent.lot, role=rt.name,
    #                                expiry=wanted_reagent.expiry.date(), missing=False)
    #             return final, report

    #     def updated(self):
    #         """
    #         Set widget status to updated
    #         """
    #         self.missing = True
    #         self.label.updated(self.reagent.role)

    #     class ReagentParsedLabel(QLabel):

    #         def __init__(self, reagent: PydReagent):
    #             super().__init__()
    #             try:
    #                 check = not reagent.missing
    #             except:
    #                 check = False
    #             self.setObjectName(f"{reagent.role}_label")
    #             if check:
    #                 self.setText(f"Parsed {reagent.role}")
    #             else:
    #                 self.setText(f"MISSING {reagent.role}")

    #         def updated(self, reagent_role: str):
    #             """
    #             Marks widget as updated

    #             Args:
    #                 reagent_role (str): _description_
    #             """
    #             self.setText(f"UPDATED {reagent_role}")

    #     class ReagentLot(MyQComboBox):

    #         def __init__(self, scrollWidget, reagent, extraction_kit: str) -> None:
    #             super().__init__(scrollWidget=scrollWidget)
    #             self.setEditable(True)
    #             looked_up_rt = ProcedureTypeReagentRoleAssociation.query(reagentrole=reagent.reagentrole,
    #                                                                proceduretype=extraction_kit)
    #             relevant_reagents = [str(item.lot) for item in looked_up_rt.get_all_relevant_reagents()]
    #             # NOTE: if reagent in sheet is not found insert it into the front of relevant reagents so it shows
    #             if str(reagent.lot) not in relevant_reagents:
    #                 if check_not_nan(reagent.lot):
    #                     relevant_reagents.insert(0, str(reagent.lot))
    #                 else:
    #                     try:
    #                         looked_up_reg = Reagent.query(lot=looked_up_rt.last_used)
    #                     except AttributeError:
    #                         looked_up_reg = None
    #                     if isinstance(looked_up_reg, list):
    #                         looked_up_reg = None
    #                     if looked_up_reg:
    #                         try:
    #                             relevant_reagents.insert(0, relevant_reagents.pop(
    #                                 relevant_reagents.index(looked_up_reg.lot)))
    #                         except ValueError as e:
    #                             logger.error(f"Error reordering relevant reagents: {e}")
    #             else:
    #                 if len(relevant_reagents) > 1:
    #                     idx = relevant_reagents.index(str(reagent.lot))
    #                     moved_reag = relevant_reagents.pop(idx)
    #                     relevant_reagents.insert(0, moved_reag)
    #                 else:
    #                     pass
    #             self.setObjectName(f"lot_{reagent.equipmentrole}")
    #             self.addItems(relevant_reagents)
    #             self.setToolTip(f"Enter lot number for the reagent used for {reagent.equipmentrole}")

    # class DisableReagents(QWidget):

    #     def __init__(self, parent: QWidget):
    #         super().__init__(parent)
    #         self.app = self.parent().parent().parent().parent().parent().parent().parent().parent()
    #         layout = QHBoxLayout()
    #         self.label = QLabel("Import Reagents")
    #         self.checkbox = QCheckBox()
    #         layout.addWidget(self.label)
    #         layout.addWidget(self.checkbox)
    #         self.setLayout(layout)


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
        # reagents = []
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
                logger.debug(f"Setting pyd {item} to {value}")
                value = getattr(self, item)
                info[item] = value
        for k, v in info.items():
            if k == "sample":
                continue
            if isinstance(v, dict):
                v = v.get("value", None)
            logger.debug(f"Setting pyd {k} to {v}")
            self.pyd.__setattr__(k, v)
        # NOTE: run is okay at this point.
        # logger.debug(f"Got pydantic object from form: {pformat(self.pyd.__dict__)}")
        report.add_result(report)
        return report

    # @report_result
    def to_pydantic(self, *args):
        self.parse_form()
        output = self.pyd
        return output

    @report_result
    def create_new_submission(self, *args) -> Report:
        from backend.validators.pydant import PydSample
        from backend.db.models import Sample
        pyd = self.to_pydantic()
        # NOTE: run is empty at this point.
        # logger.debug(f"Got pydantic object from form: {pformat(pyd.__dict__)}")
        # Save samples individually and collect the saved SQL Sample objects.
        # Later, attach these saved Sample objects to the submission SQL object so
        # .save() does not attempt to INSERT duplicate Sample rows (same sample_id).
        saved_samples = []
        for sample in pyd.sample:
            # Normalize PydSample -> SQL Sample object first so we can inspect sample_id safely
            if isinstance(sample, PydSample):
                sample_sql = sample.to_sql()
                if isinstance(sample_sql, tuple):
                    sample_sql = sample_sql[0]
            else:
                sample_sql = sample
            # Defensive checks
            if isinstance(sample_sql, PydSample):
                logger.error("Expected SQL Sample object but got PydSample after to_sql(). Skipping.")
                continue
            if not isinstance(sample_sql, Sample):
                logger.error(f"Unexpected sample object type: {type(sample_sql)}. Skipping.")
                continue

            sid = getattr(sample_sql, 'sample_id', None)
            # If a sample already exists in DB, query it and reuse that instance.
            existing = Sample.query(sample_id=sid)
            if existing:
                # Sample.query may return a single object or a list; normalize to object
                sample_sql = existing[0] if isinstance(existing, list) else existing
            else:
                # Skip samples with missing/blank placeholder IDs
                try:
                    sid_str = str(sid).strip()
                except Exception:
                    sid_str = ""
                if not sid_str or sid_str.lower() in ("", "blank", "na", "n/a"):
                    sample_sql.save()
                # At this point the rank is correct
            saved_samples.append(sample_sql)
        logger.debug(f"Got pydantic run object from form: {pformat(pyd.run[0].__dict__)}")
        # runs = []
        # for run in pyd.run:
        #     run = run.to_sql()
        #     if isinstance(run, tuple):
        #         run = run[0]
        #     runs.append(run)
        pyd.run = []
        sql = pyd.to_sql()
        
        if isinstance(sql, tuple):
            sql = sql[0]
        # sql.run = runs
        # logger.debug(f"Got sqlalchemy run object from form: {pformat(sql.run[0].__dict__)}")
        # Remove any sample info accidentally left in misc_info by pyd.to_sql
        try:
            del sql._misc_info['sample']
        except KeyError:
            pass
        # Clear any pre-built association objects created by pyd.to_sql() so we can
        # re-create clean associations from the saved Sample SQL objects. This avoids
        # carrying over non-serializable _misc_info from pyd objects into the DB.
        try:
            if hasattr(sql, 'clientsubmissionsampleassociation'):
                sql.clientsubmissionsampleassociation = []
        except Exception as e:
            logger.warning(f"Could not clear existing sample associations: {e}")
        try:
            sql.sample = saved_samples
        except Exception as e:
            logger.error(f"Couldn't set samples to {pyd.sample}\ndue to {e}")
        sql.save()
        self.app.table_widget.sub_wid.set_data()
        self.setParent(None)
