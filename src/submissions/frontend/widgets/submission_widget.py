'''
Contains all submission related frontend functions
'''
import sys
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout,
    QComboBox, QDateEdit, QLineEdit, QLabel
)
from PyQt6.QtCore import pyqtSignal, Qt
from pathlib import Path
from . import select_open_file, select_save_file
import logging, difflib, inspect
from pathlib import Path
from tools import Report, Result, check_not_nan, main_form_style, report_result
from backend.excel.parser import SheetParser
from backend.validators import PydSubmission, PydReagent
from backend.db import (
    KitType, Organization, SubmissionType, Reagent,
    ReagentRole, KitTypeReagentRoleAssociation, BasicSubmission
)
from pprint import pformat
from .pop_ups import QuestionAsker, AlertPop
from .misc import AddReagentForm
from typing import List, Tuple
from datetime import date

logger = logging.getLogger(f"submissions.{__name__}")

class MyQComboBox(QComboBox):
    def __init__(self, scrollWidget=None, *args, **kwargs):
        super(MyQComboBox, self).__init__(*args, **kwargs)
        self.scrollWidget=scrollWidget
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        logger.debug(f"Scrollwidget: {scrollWidget}")

    def wheelEvent(self, *args, **kwargs):
        if self.hasFocus():
            return QComboBox.wheelEvent(self, *args, **kwargs)
        else:
            return self.scrollWidget.wheelEvent(*args, **kwargs)

class MyQDateEdit(QDateEdit):
    def __init__(self, scrollWidget=None, *args, **kwargs):
        super(MyQDateEdit, self).__init__(*args, **kwargs)
        self.scrollWidget=scrollWidget
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, *args, **kwargs):
        if self.hasFocus():
            return QDateEdit.wheelEvent(self, *args, **kwargs)
        else:
            return self.scrollWidget.wheelEvent(*args, **kwargs)


class SubmissionFormContainer(QWidget):
    # A signal carrying a path
    import_drag = pyqtSignal(Path)

    def __init__(self, parent: QWidget) -> None:
        # logger.debug(f"Setting form widget...")
        super().__init__(parent)
        self.app = self.parent().parent()
        # logger.debug(f"App: {self.app}")
        self.report = Report()
        self.setStyleSheet('background-color: light grey;')
        self.setAcceptDrops(True)
        # NOTE: if import_drag is emitted, importSubmission will fire
        self.import_drag.connect(self.importSubmission)

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
        # logger.debug(f"App: {self.app}")
        self.app.last_dir = fname.parent
        self.import_drag.emit(fname)

    @report_result
    def importSubmission(self, fname: Path | None = None):
        """
        import submission from excel sheet into form
        """
        self.app.raise_()
        self.app.activateWindow()
        self.report = Report()
        self.import_submission_function(fname)
        return self.report

    def import_submission_function(self, fname: Path | None = None):
        """
        Import a new submission to the app window

        Args:
            obj (QMainWindow): original app window

        Returns:
            Tuple[QMainWindow, dict|None]: Collection of new main app window and result dict
        """
        logger.info(f"\n\nStarting Import...\n\n")
        report = Report()
        try:
            self.form.setParent(None)
        except AttributeError:
            pass
        # NOTE: initialize samples
        self.samples = []
        self.missing_info = []
        # NOTE: set file dialog
        if isinstance(fname, bool) or fname is None:
            fname = select_open_file(self, file_extension="xlsx")
        # logger.debug(f"Attempting to parse file: {fname}")
        if not fname.exists():
            report.add_result(Result(msg=f"File {fname.__str__()} not found.", status="critical"))
            self.report.add_result(report)
            return
        # NOTE: create sheetparser using excel sheet and context from gui
        try:
            self.prsr = SheetParser(filepath=fname)
        except PermissionError:
            logger.error(f"Couldn't get permission to access file: {fname}")
            return
        except AttributeError:
            self.prsr = SheetParser(filepath=fname)
        # logger.debug(f"Submission dictionary:\n{pformat(self.prsr.sub)}")
        self.pyd = self.prsr.to_pydantic()
        # logger.debug(f"Pydantic result: \n\n{pformat(self.pyd)}\n\n")
        self.form = self.pyd.to_form(parent=self)
        self.layout().addWidget(self.form)
        self.report.add_result(report)
        # logger.debug(f"Outgoing report: {self.report.results}")
        # logger.debug(f"All attributes of submission container:\n{pformat(self.__dict__)}")

    @report_result
    def add_reagent(self, reagent_lot: str | None = None, reagent_role: str | None = None, expiry: date | None = None,
                    name: str | None = None) -> Tuple[PydReagent, Report]:
        """
        Action to create new reagent in DB.

        Args:
            reagent_lot (str | None, optional): Parsed reagent from import form. Defaults to None.
            reagent_role (str | None, optional): Parsed reagent type from import form. Defaults to None.
            expiry (date | None, optional): Parsed reagent expiry data. Defaults to None.
            name (str | None, optional): Parsed reagent name. Defaults to None.

        Returns:
            models.Reagent: the constructed reagent object to add to submission
        """
        report = Report()
        if isinstance(reagent_lot, bool):
            reagent_lot = ""
        # NOTE: create form
        dlg = AddReagentForm(reagent_lot=reagent_lot, reagent_role=reagent_role, expiry=expiry, reagent_name=name)
        if dlg.exec():
            # extract form info
            info = dlg.parse_form()
            # logger.debug(f"Reagent info: {info}")
            # NOTE: create reagent object
            reagent = PydReagent(ctx=self.app.ctx, **info, missing=False)
            # NOTE: send reagent to db
            sqlobj, assoc, result = reagent.toSQL()
            sqlobj.save()
            report.add_result(result)
            # logger.debug(f"Reagent: {reagent}, Report: {report}")
            return reagent, report


class SubmissionFormWidget(QWidget):

    def __init__(self, parent: QWidget, submission: PydSubmission, disable: list | None = None) -> None:
        super().__init__(parent)
        # self.report = Report()
        # logger.debug(f"Disable: {disable}")
        if disable is None:
            disable = []
        self.app = parent.app
        self.pyd = submission
        self.missing_info = []
        st = SubmissionType.query(name=self.pyd.submission_type['value']).get_submission_class()
        defaults = st.get_default_info("form_recover", "form_ignore")
        self.recover = defaults['form_recover']
        self.ignore = defaults['form_ignore']
        # logger.debug(f"Attempting to extend ignore list with {self.pyd.submission_type['value']}")
        self.layout = QVBoxLayout()
        for k in list(self.pyd.model_fields.keys()) + list(self.pyd.model_extra.keys()):
            if k in self.ignore:
                continue
            try:
                # logger.debug(f"Key: {k}, Disable: {disable}")
                check = k in disable
                # logger.debug(f"Check: {check}")
            except TypeError:
                check = False
            try:
                value = self.pyd.__getattribute__(k)
            except AttributeError:
                logger.error(f"Couldn't get attribute from pyd: {k}")
                value = dict(value=None, missing=True)
            add_widget = self.create_widget(key=k, value=value, submission_type=self.pyd.submission_type['value'],
                                            sub_obj=st, disable=check)
            if add_widget is not None:
                self.layout.addWidget(add_widget)
            if k == "extraction_kit":
                add_widget.input.currentTextChanged.connect(self.scrape_reagents)
        self.setStyleSheet(main_form_style)
        self.scrape_reagents(self.pyd.extraction_kit)

    def create_widget(self, key: str, value: dict | PydReagent, submission_type: str | None = None,
                      extraction_kit: str | None = None, sub_obj: BasicSubmission | None = None,
                      disable: bool = False) -> "self.InfoItem":
        """
        Make an InfoItem widget to hold a field

        Args:
            disable ():
            key (str): Name of the field
            value (dict): Value of field
            submission_type (str | None, optional): Submissiontype as str. Defaults to None.

        Returns:
            self.InfoItem: Form widget to hold name:value
        """
        # logger.debug(f"Key: {key}, Disable: {disable}")
        if key not in self.ignore:
            match value:
                case PydReagent():
                    if value.name.lower() != "not applicable":
                        widget = self.ReagentFormWidget(parent=self, reagent=value, extraction_kit=extraction_kit)
                    else:
                        widget = None
                case _:
                    widget = self.InfoItem(parent=self, key=key, value=value, submission_type=submission_type, sub_obj=sub_obj)
            # logger.debug(f"Setting widget enabled to: {not disable}")
            if disable:
                widget.input.setEnabled(False)
                widget.input.setToolTip("Widget disabled to protect database integrity.")
            return widget
        return None

    @report_result
    def scrape_reagents(self, *args, **kwargs):  #extraction_kit:str, caller:str|None=None):
        """
        Extracted scrape reagents function that will run when
        form 'extraction_kit' widget is updated.

        Args:
            obj (QMainWindow): updated main application
            extraction_kit (str): name of extraction kit (in 'extraction_kit' widget)

        Returns:
            Tuple[QMainWindow, dict]: Updated application and result
        """
        extraction_kit = args[0]
        caller = inspect.stack()[1].function.__repr__().replace("'", "")
        # logger.debug(f"Self.reagents: {self.reagents}")
        # logger.debug(f"\n\n{pformat(caller)}\n\n")
        # logger.debug(f"SubmissionType: {self.submission_type}")
        report = Report()
        # logger.debug(f"Extraction kit: {extraction_kit}")
        # NOTE: Remove previous reagent widgets
        try:
            old_reagents = self.find_widgets()
        except AttributeError:
            logger.error(f"Couldn't find old reagents.")
            old_reagents = []
        # logger.debug(f"\n\nAttempting to clear: {old_reagents}\n\n")
        for reagent in old_reagents:
            if isinstance(reagent, self.ReagentFormWidget) or isinstance(reagent, QPushButton):
                reagent.setParent(None)
        reagents, integrity_report = self.pyd.check_kit_integrity(extraction_kit=extraction_kit)
        # logger.debug(f"Missing reagents: {obj.missing_reagents}")
        for reagent in reagents:
            add_widget = self.ReagentFormWidget(parent=self, reagent=reagent, extraction_kit=self.pyd.extraction_kit)
            self.layout.addWidget(add_widget)
        report.add_result(integrity_report)
        # logger.debug(f"Outgoing report: {report.results}")
        if hasattr(self.pyd, "csv"):
            export_csv_btn = QPushButton("Export CSV")
            export_csv_btn.setObjectName("export_csv_btn")
            self.layout.addWidget(export_csv_btn)
            export_csv_btn.clicked.connect(self.export_csv_function)
        submit_btn = QPushButton("Submit")
        submit_btn.setObjectName("submit_btn")
        self.layout.addWidget(submit_btn)
        submit_btn.clicked.connect(self.submit_new_sample_function)
        self.setLayout(self.layout)
        return report

    def clear_form(self):
        """
        Removes all form widgets
        """
        for item in self.findChildren(QWidget):
            item.setParent(None)

    def find_widgets(self, object_name: str | None = None) -> List[QWidget]:
        """
        Gets all widgets filtered by object name

        Args:
            object_name (str | None, optional): name to filter by. Defaults to None.

        Returns:
            List[QWidget]: Widgets matching filter
        """
        query = self.findChildren(QWidget)
        if object_name is not None:
            query = [widget for widget in query if widget.objectName() == object_name]
        return query

    @report_result
    def submit_new_sample_function(self, *args) -> Report:
        """
        Parse forms and add sample to the database.

        Args:
            obj (QMainWindow): original app window

        Returns:
            Tuple[QMainWindow, dict]: Collection of new main app window and result dict
        """
        logger.info(f"\n\nBeginning Submission\n\n")
        report = Report()
        result = self.parse_form()
        report.add_result(result)
        # logger.debug(f"Submission: {pformat(self.pyd)}")
        # logger.debug("Checking kit integrity...")
        _, result = self.pyd.check_kit_integrity()
        report.add_result(result)
        if len(result.results) > 0:
            # self.app.report.add_result(report)
            # self.app.report_result()
            return
        # logger.debug(f"PYD before transformation into SQL:\n\n{self.pyd}\n\n")
        base_submission, result = self.pyd.to_sql()
        # logger.debug(f"SQL object: {pformat(base_submission.__dict__)}")
        # logger.debug(f"Base submission: {base_submission.to_dict()}")
        # NOTE: check output message for issues
        try:
            code = report.results[-1].code
        except IndexError:
            code = 0
        match code:
            # NOTE: code 0: everything is fine.
            case 0:
                pass
            # NOTE: code 1: ask for overwrite
            case 1:
                dlg = QuestionAsker(title=f"Review {base_submission.rsl_plate_num}?", message=result.msg)
                if dlg.exec():
                    # NOTE: Do not add duplicate reagents.
                    pass
                else:
                    self.app.ctx.database_session.rollback()
                    report.add_result(Result(msg="Overwrite cancelled", status="Information"))
                    # self.app.report.add_result(report)
                    # self.app.report_result()
                    return report
            # NOTE: code 2: No RSL plate number given
            case 2:
                report.add_result(result)
                # self.app.report.add_result(report)
                # self.app.report_result()
                return report
            case _:
                pass
        # NOTE: add reagents to submission object
        for reagent in base_submission.reagents:
            # logger.debug(f"Updating: {reagent} with {reagent.lot}")
            reagent.update_last_used(kit=base_submission.extraction_kit)
        # logger.debug(f"Final reagents: {pformat(base_submission.reagents)}")
        base_submission.save()
        # NOTE: update summary sheet
        self.app.table_widget.sub_wid.setData()
        # NOTE: reset form
        self.setParent(None)
        # logger.debug(f"All attributes of obj: {pformat(self.__dict__)}")
        return report

    def export_csv_function(self, fname: Path | None = None):
        """
        Save the submission's csv file.

        Args:
            fname (Path | None, optional): Input filename. Defaults to None.
        """
        if isinstance(fname, bool) or fname is None:
            fname = select_save_file(obj=self, default_name=self.pyd.construct_filename(), extension="csv")
        try:
            self.pyd.export_csv(fname)
        except PermissionError:
            logger.warning(f"Could not get permissions to {fname}. Possibly the request was cancelled.")
        except AttributeError:
            logger.error(f"No csv file found in the submission at this point.")

    def parse_form(self) -> Report:
        """
        Transforms form info into PydSubmission

        Returns:
            Report: Report on status of parse.
        """
        report = Report()
        logger.info(f"Hello from form parser!")
        info = {}
        reagents = []
        for widget in self.findChildren(QWidget):
            # logger.debug(f"Parsed widget of type {type(widget)}")
            match widget:
                case self.ReagentFormWidget():
                    reagent, _ = widget.parse_form()
                    if reagent is not None:
                        reagents.append(reagent)
                case self.InfoItem():
                    field, value = widget.parse_form()
                    if field is not None:
                        info[field] = value
        # logger.debug(f"Info: {pformat(info)}")
        # logger.debug(f"Reagents going into pyd: {pformat(reagents)}")
        self.pyd.reagents = reagents
        # logger.debug(f"Attrs not in info: {[k for k, v in self.__dict__.items() if k not in info.keys()]}")
        for item in self.recover:
            # logger.debug(f"Attempting to recover: {item}")
            if hasattr(self, item):
                value = getattr(self, item)
                # logger.debug(f"Setting {item}")
                info[item] = value
        for k, v in info.items():
            self.pyd.set_attribute(key=k, value=v)
        # NOTE: return submission
        report.add_result(report)
        return report

    class InfoItem(QWidget):

        def __init__(self, parent: QWidget, key: str, value: dict, submission_type: str | None = None,
                     sub_obj: BasicSubmission | None = None) -> None:
            super().__init__(parent)
            layout = QVBoxLayout()
            self.label = self.ParsedQLabel(key=key, value=value)
            self.input: QWidget = self.set_widget(parent=parent, key=key, value=value, submission_type=submission_type,
                                                  sub_obj=sub_obj)
            self.setObjectName(key)
            try:
                self.missing: bool = value['missing']
            except (TypeError, KeyError):
                self.missing: bool = True
            if self.input is not None:
                layout.addWidget(self.label)
                layout.addWidget(self.input)
            layout.setContentsMargins(0, 0, 0, 0)
            self.setLayout(layout)
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
            return self.input.objectName(), dict(value=value, missing=self.missing)

        def set_widget(self, parent: QWidget, key: str, value: dict, submission_type: str | None = None,
                       sub_obj: BasicSubmission | None = None) -> QWidget:
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
            if sub_obj is None:
                sub_obj = SubmissionType.query(name=submission_type).get_submission_class()
            try:
                value = value['value']
            except (TypeError, KeyError):
                pass
            obj = parent.parent().parent()
            logger.debug(f"Object: {obj}")
            logger.debug(f"Parent: {parent.parent()}")
            # logger.debug(f"Creating widget for: {key}")
            match key:
                case 'submitting_lab':
                    add_widget = MyQComboBox(scrollWidget=parent)
                    # lookup organizations suitable for submitting_lab (ctx: self.InfoItem.SubmissionFormWidget.SubmissionFormContainer.AddSubForm )
                    labs = [item.name for item in Organization.query()]
                    # try to set closest match to top of list
                    try:
                        labs = difflib.get_close_matches(value, labs, len(labs), 0)
                    except (TypeError, ValueError):
                        pass
                    # set combobox values to lookedup values
                    add_widget.addItems(labs)
                    add_widget.setToolTip("Select submitting lab.")
                case 'extraction_kit':
                    # if extraction kit not available, all other values fail
                    if not check_not_nan(value):
                        msg = AlertPop(message="Make sure to check your extraction kit in the excel sheet!",
                                       status="warning")
                        msg.exec()
                    # NOTE: create combobox to hold looked up kits
                    add_widget = MyQComboBox(scrollWidget=parent)
                    # NOTE: lookup existing kits by 'submission_type' decided on by sheetparser
                    # logger.debug(f"Looking up kits used for {submission_type}")
                    uses = [item.name for item in KitType.query(used_for=submission_type)]
                    obj.uses = uses
                    # logger.debug(f"Kits received for {submission_type}: {uses}")
                    if check_not_nan(value):
                        # logger.debug(f"The extraction kit in parser was: {value}")
                        uses.insert(0, uses.pop(uses.index(value)))
                        obj.ext_kit = value
                    else:
                        logger.error(f"Couldn't find {obj.prsr.sub['extraction_kit']}")
                        obj.ext_kit = uses[0]
                    add_widget.addItems(uses)
                    add_widget.setToolTip("Select extraction kit.")
                case 'submission_category':
                    add_widget = MyQComboBox(scrollWidget=parent)
                    cats = ['Diagnostic', "Surveillance", "Research"]
                    cats += [item.name for item in SubmissionType.query()]
                    try:
                        cats.insert(0, cats.pop(cats.index(value)))
                    except ValueError:
                        cats.insert(0, cats.pop(cats.index(submission_type)))
                    add_widget.addItems(cats)
                    add_widget.setToolTip("Enter submission category or select from list.")
                case _:
                    if key in sub_obj.timestamps():
                        add_widget = MyQDateEdit(calendarPopup=True, scrollWidget=parent)
                        # NOTE: sets submitted date based on date found in excel sheet
                        try:
                            add_widget.setDate(value)
                        # NOTE: if not found, use today
                        except:
                            add_widget.setDate(date.today())
                        add_widget.setToolTip(f"Select date for {key}")
                    else:
                        # NOTE: anything else gets added in as a line edit
                        add_widget = QLineEdit()
                        # logger.debug(f"Setting widget text to {str(value).replace('_', ' ')}")
                        add_widget.setText(str(value).replace("_", " "))
                        add_widget.setToolTip(f"Enter value for {key}")
            if add_widget is not None:
                add_widget.setObjectName(key)
                add_widget.setParent(parent)
                # add_widget.setStyleSheet(main_form_style)
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

    class ReagentFormWidget(QWidget):

        def __init__(self, parent: QWidget, reagent: PydReagent, extraction_kit: str):
            super().__init__(parent)
            self.app = self.parent().parent().parent().parent().parent().parent().parent().parent()
            self.reagent = reagent
            self.extraction_kit = extraction_kit
            layout = QVBoxLayout()
            self.label = self.ReagentParsedLabel(reagent=reagent)
            layout.addWidget(self.label)
            self.lot = self.ReagentLot(scrollWidget=parent, reagent=reagent, extraction_kit=extraction_kit)
            # self.lot.setStyleSheet(main_form_style)
            layout.addWidget(self.lot)
            # NOTE: Remove spacing between reagents
            layout.setContentsMargins(0, 0, 0, 0)
            self.setLayout(layout)
            self.setObjectName(reagent.name)
            self.missing = reagent.missing
            # NOTE: If changed set self.missing to True and update self.label
            self.lot.currentTextChanged.connect(self.updated)

        def parse_form(self) -> Tuple[PydReagent | None, Report]:
            """
            Pulls form info into PydReagent

            Returns:
                Tuple[PydReagent, dict]: PydReagent and Report(?)
            """
            report = Report()
            lot = self.lot.currentText()
            # logger.debug(f"Using this lot for the reagent {self.reagent}: {lot}")
            wanted_reagent = Reagent.query(lot_number=lot, reagent_role=self.reagent.role)
            # NOTE: if reagent doesn't exist in database, offer to add it (uses App.add_reagent)
            if wanted_reagent is None:
                dlg = QuestionAsker(title=f"Add {lot}?",
                                    message=f"Couldn't find reagent type {self.reagent.role}: {lot} in the database.\n\nWould you like to add it?")
                if dlg.exec():
                    wanted_reagent, _ = self.parent().parent().add_reagent(reagent_lot=lot,
                                                                           reagent_role=self.reagent.role,
                                                                           expiry=self.reagent.expiry,
                                                                           name=self.reagent.name)
                    return wanted_reagent, report
                else:
                    # NOTE: In this case we will have an empty reagent and the submission will fail kit integrity check
                    # logger.debug("Will not add reagent.")
                    report.add_result(Result(msg="Failed integrity check", status="Critical"))
                    return None, report
            else:
                # NOTE: Since this now gets passed in directly from the parser -> pyd -> form and the parser gets the name
                # from the db, it should no longer be necessary to query the db with reagent/kit, but with rt name directly.
                rt = ReagentRole.query(name=self.reagent.role)
                if rt is None:
                    rt = ReagentRole.query(kit_type=self.extraction_kit, reagent=wanted_reagent)
                return PydReagent(name=wanted_reagent.name, lot=wanted_reagent.lot, role=rt.name,
                                  expiry=wanted_reagent.expiry, missing=False), report

        def updated(self):
            """
            Set widget status to updated
            """
            self.missing = True
            self.label.updated(self.reagent.role)

        class ReagentParsedLabel(QLabel):

            def __init__(self, reagent: PydReagent):
                super().__init__()
                try:
                    check = not reagent.missing
                except:
                    check = False
                self.setObjectName(f"{reagent.role}_label")
                if check:
                    self.setText(f"Parsed {reagent.role}")
                else:
                    self.setText(f"MISSING {reagent.role}")

            def updated(self, reagent_role: str):
                """
                Marks widget as updated

                Args:
                    reagent_role (str): _description_
                """
                self.setText(f"UPDATED {reagent_role}")

        class ReagentLot(MyQComboBox):

            def __init__(self, scrollWidget, reagent, extraction_kit: str) -> None:
                super().__init__(scrollWidget=scrollWidget)
                self.setEditable(True)
                # logger.debug(f"Attempting lookup of reagents by type: {reagent.type}")
                # NOTE: below was lookup_reagent_by_type_name_and_kit_name, but I couldn't get it to work.
                lookup = Reagent.query(reagent_role=reagent.role)
                relevant_reagents = [str(item.lot) for item in lookup]
                output_reg = []
                for rel_reagent in relevant_reagents:
                    # NOTE: extract strings from any sets.
                    if isinstance(rel_reagent, set):
                        for thing in rel_reagent:
                            output_reg.append(thing)
                    elif isinstance(rel_reagent, str):
                        output_reg.append(rel_reagent)
                relevant_reagents = output_reg
                # NOTE: if reagent in sheet is not found insert it into the front of relevant reagents so it shows
                # logger.debug(f"Relevant reagents for {reagent.lot}: {relevant_reagents}")
                if str(reagent.lot) not in relevant_reagents:
                    if check_not_nan(reagent.lot):
                        relevant_reagents.insert(0, str(reagent.lot))
                    else:
                        looked_up_rt = KitTypeReagentRoleAssociation.query(reagent_role=reagent.role,
                                                                           kit_type=extraction_kit)
                        try:
                            looked_up_reg = Reagent.query(lot_number=looked_up_rt.last_used)
                        except AttributeError:
                            looked_up_reg = None
                        if isinstance(looked_up_reg, list):
                            looked_up_reg = None
                        # logger.debug(f"Because there was no reagent listed for {reagent.lot}, we will insert the last lot used: {looked_up_reg}")
                        if looked_up_reg is not None:
                            try:
                                relevant_reagents.remove(str(looked_up_reg.lot))
                                relevant_reagents.insert(0, str(looked_up_reg.lot))
                            except ValueError as e:
                                logger.error(f"Error reordering relevant reagents: {e}")
                else:
                    if len(relevant_reagents) > 1:
                        # logger.debug(f"Found {reagent.lot} in relevant reagents: {relevant_reagents}. Moving to front of list.")
                        idx = relevant_reagents.index(str(reagent.lot))
                        # logger.debug(f"The index we got for {reagent.lot} in {relevant_reagents} was {idx}")
                        moved_reag = relevant_reagents.pop(idx)
                        relevant_reagents.insert(0, moved_reag)
                    else:
                        # logger.debug(f"Found {reagent.lot} in relevant reagents: {relevant_reagents}. But no need to move due to short list.")
                        pass
                # logger.debug(f"New relevant reagents: {relevant_reagents}")
                self.setObjectName(f"lot_{reagent.role}")
                self.addItems(relevant_reagents)
                self.setToolTip(f"Enter lot number for the reagent used for {reagent.role}")
                # self.setStyleSheet(main_form_style)



