from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout,
    QComboBox, QDateEdit, QLineEdit, QLabel
)
from PyQt6.QtCore import pyqtSignal
from pathlib import Path
from . import select_open_file, select_save_file
import logging, difflib, inspect, json
from pathlib import Path
from tools import Report, Result, check_not_nan
from backend.excel.parser import SheetParser, PCRParser
from backend.validators import PydSubmission, PydReagent
from backend.db import (
    KitType, Organization, SubmissionType, Reagent, 
    ReagentType, KitTypeReagentTypeAssociation, BasicSubmission
)
from pprint import pformat
from .pop_ups import QuestionAsker, AlertPop
from .misc import AddReagentForm
from typing import List, Tuple
from datetime import date

logger = logging.getLogger(f"submissions.{__name__}")

class SubmissionFormContainer(QWidget):

    # A signal carrying a path 
    import_drag = pyqtSignal(Path)

    def __init__(self, parent: QWidget) -> None:
        logger.debug(f"Setting form widget...")
        super().__init__(parent)
        self.app = self.parent().parent()
        self.report = Report()
        self.setAcceptDrops(True)
        # if import_drag is emitted, importSubmission will fire
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
        logger.debug(f"App: {self.app}")
        self.app.last_dir = fname.parent
        self.import_drag.emit(fname)

    def importSubmission(self, fname:Path|None=None):
        """
        import submission from excel sheet into form
        """        
        self.app.raise_()
        self.app.activateWindow()
        self.import_submission_function(fname)
        logger.debug(f"Result from result reporter: {self.report.results}")
        self.app.report.add_result(self.report)
        self.report = Report()
        self.app.result_reporter()

    def import_submission_function(self, fname:Path|None=None):
        """
        Import a new submission to the app window

        Args:
            obj (QMainWindow): original app window

        Returns:
            Tuple[QMainWindow, dict|None]: Collection of new main app window and result dict
        """    
        logger.debug(f"\n\nStarting Import...\n\n")
        report = Report()
        try:
            self.form.setParent(None)
        except AttributeError:
            pass
        # initialize samples
        self.samples = []
        self.missing_info = []
        # set file dialog
        if isinstance(fname, bool) or fname == None:
            fname = select_open_file(self, file_extension="xlsx")
        logger.debug(f"Attempting to parse file: {fname}")
        if not fname.exists():
            report.add_result(Result(msg=f"File {fname.__str__()} not found.", status="critical"))
            self.report.add_result(report)
            return
        # create sheetparser using excel sheet and context from gui
        try:
            self.prsr = SheetParser(filepath=fname)
        except PermissionError:
            logger.error(f"Couldn't get permission to access file: {fname}")
            return
        except AttributeError:
            self.prsr = SheetParser(filepath=fname)
        logger.debug(f"Submission dictionary:\n{pformat(self.prsr.sub)}")
        self.pyd = self.prsr.to_pydantic()
        logger.debug(f"Pydantic result: \n\n{pformat(self.pyd)}\n\n")
        self.form = self.pyd.toForm(parent=self)
        self.layout().addWidget(self.form)
        if self.prsr.sample_result != None:
            report.add_result(msg=self.prsr.sample_result, status="Warning")
        self.report.add_result(report)
        logger.debug(f"Outgoing report: {self.report.results}")
        logger.debug(f"All attributes of submission container:\n{pformat(self.__dict__)}")

    def add_reagent(self, reagent_lot:str|None=None, reagent_type:str|None=None, expiry:date|None=None, name:str|None=None):
        """
        Action to create new reagent in DB.

        Args:
            reagent_lot (str | None, optional): Parsed reagent from import form. Defaults to None.
            reagent_type (str | None, optional): Parsed reagent type from import form. Defaults to None.
            expiry (date | None, optional): Parsed reagent expiry data. Defaults to None.
            name (str | None, optional): Parsed reagent name. Defaults to None.

        Returns:
            models.Reagent: the constructed reagent object to add to submission
        """        
        report = Report()
        if isinstance(reagent_lot, bool):
            reagent_lot = ""
        # create form
        dlg = AddReagentForm(reagent_lot=reagent_lot, reagent_type=reagent_type, expiry=expiry, reagent_name=name)
        if dlg.exec():
            # extract form info
            info = dlg.parse_form()
            logger.debug(f"Reagent info: {info}")
            # create reagent object
            reagent = PydReagent(ctx=self.app.ctx, **info)
            # send reagent to db
            sqlobj, result = reagent.toSQL()
            sqlobj.save()
            report.add_result(result)
            self.app.result_reporter()
            return reagent

class SubmissionFormWidget(QWidget):

    def __init__(self, parent: QWidget, submission:PydSubmission) -> None:
        super().__init__(parent)
        self.report = Report()
        self.app = parent.app
        self.pyd = submission
        # self.input = [{k:v} for k,v in kwargs.items()]
        # self.samples = []
        self.missing_info = []
        self.ignore = ['filepath', 'samples', 'reagents', 'csv', 'ctx', 'comment', 
                       'equipment', 'source_plates', 'id', 'cost', 'extraction_info', 
                       'controls', 'pcr_info', 'gel_info', 'gel_image']
        self.recover = ['filepath', 'samples', 'csv', 'comment', 'equipment']
        self.layout = QVBoxLayout()
        # for k, v in kwargs.items():
        for k in list(self.pyd.model_fields.keys()) + list(self.pyd.model_extra.keys()):
            if k not in self.ignore:
                try:
                    value = self.pyd.__getattribute__(k)
                except AttributeError:
                    logger.error(f"Couldn't get attribute from pyd: {k}")
                    value = dict(value=None, missing=True)
                add_widget = self.create_widget(key=k, value=value, submission_type=self.pyd.submission_type['value'])
                if add_widget != None:
                    self.layout.addWidget(add_widget)
                if k == "extraction_kit":
                    add_widget.input.currentTextChanged.connect(self.scrape_reagents)
            # else:
            # self.__setattr__(k, v)
        # self.scrape_reagents(self.extraction_kit['value'])
        self.scrape_reagents(self.pyd.extraction_kit)
        # extraction kit must be added last so widget order makes sense.
        # self.layout.addWidget(self.create_widget(key="extraction_kit", value=self.extraction_kit, submission_type=self.submission_type))
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
        self.app.report.add_result(self.report)
        self.app.result_reporter()

    def create_widget(self, key:str, value:dict|PydReagent, submission_type:str|None=None, extraction_kit:str|None=None) -> "self.InfoItem":
        """
        Make an InfoItem widget to hold a field

        Args:
            key (str): Name of the field
            value (dict): Value of field
            submission_type (str | None, optional): Submissiontype as str. Defaults to None.

        Returns:
            self.InfoItem: Form widget to hold name:value
        """        
        if key not in self.ignore:
            match value:
                case PydReagent():
                    if value.name.lower() != "not applicable":
                        widget = self.ReagentFormWidget(self, reagent=value, extraction_kit=extraction_kit)
                    else:
                        widget = None
                case _:
                    widget = self.InfoItem(self, key=key, value=value, submission_type=submission_type)
            return widget
        return None
    
    def scrape_reagents(self, *args, **kwargs):#extraction_kit:str, caller:str|None=None):
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
        # self.reagents = []
        # logger.debug(f"Self.reagents: {self.reagents}")
        # logger.debug(f"\n\n{caller}\n\n")
        # logger.debug(f"SubmissionType: {self.submission_type}")
        report = Report()
        logger.debug(f"Extraction kit: {extraction_kit}")
        # Remove previous reagent widgets
        try:
            old_reagents = self.find_widgets()
        except AttributeError:
            logger.error(f"Couldn't find old reagents.")
            old_reagents = []
        # logger.debug(f"\n\nAttempting to clear: {old_reagents}\n\n")
        for reagent in old_reagents:
            if isinstance(reagent, self.ReagentFormWidget) or isinstance(reagent, QPushButton):
                reagent.setParent(None)
        # match caller:
        #     case "import_submission_function":
        #         self.reagents = self.prsr.sub['reagents']
        #     case _:
        # already_have = [reagent for reagent in self.prsr.sub['reagents'] if not reagent.missing]
        # already_have = [reagent for reagent in self.pyd.reagents if not reagent.missing]
        # names = list(set([item.type for item in already_have]))
        # # logger.debug(f"Already have: {already_have}")
        # reagents = [item.to_pydantic() for item in KitType.query(name=extraction_kit).get_reagents(submission_type=self.pyd.submission_type) if item.name not in names]
        # # logger.debug(f"Missing: {reagents}")
        # self.pyd.reagents = already_have + reagents
        # logger.debug(f"Reagents: {self.reagents}")
        # self.kit_integrity_completion_function(extraction_kit=extraction_kit)
        reagents, report = self.pyd.check_kit_integrity(extraction_kit=extraction_kit)
        # logger.debug(f"Missing reagents: {obj.missing_reagents}")
        for reagent in reagents:
            add_widget = self.ReagentFormWidget(parent=self, reagent=reagent, extraction_kit=self.pyd.extraction_kit)
            self.layout.addWidget(add_widget)
        self.report.add_result(report)
        logger.debug(f"Outgoing report: {self.report.results}")

    def kit_integrity_completion_function(self, extraction_kit:str|None=None):
        """
        Compare kit contents to parsed contents and creates widgets.

        Args:
            obj (QMainWindow): The original app window

        Returns:
            Tuple[QMainWindow, dict]: Collection of new main app window and result dict
        """    
        report = Report()
        missing_reagents = []
        # logger.debug(inspect.currentframe().f_back.f_code.co_name)
        # find the widget that contains kit info
        if extraction_kit is None:
            kit_widget = self.find_widgets(object_name="extraction_kit")[0].input
            logger.debug(f"Kit selector: {kit_widget}")
            # get current kit being used
            self.ext_kit = kit_widget.currentText()
        else:
            self.ext_kit = extraction_kit
        for reagent in self.reagents:
            logger.debug(f"Creating widget for {reagent}")
            add_widget = self.ReagentFormWidget(parent=self, reagent=reagent, extraction_kit=self.ext_kit)
            # self.form.layout().addWidget(add_widget)
            self.layout.addWidget(add_widget)
            if reagent.missing:
                missing_reagents.append(reagent)
        logger.debug(f"Checking integrity of {self.ext_kit}")
        # TODO: put check_kit_integrity here instead of what's here?
        # see if there are any missing reagents
        if len(missing_reagents) > 0:
            result = Result(msg=f"""The submission you are importing is missing some reagents expected by the kit.\n\n 
                            It looks like you are missing: {[item.type.upper() for item in missing_reagents]}\n\n 
                            Alternatively, you may have set the wrong extraction kit.\n\nThe program will populate lists using existing reagents. 
                            \n\nPlease make sure you check the lots carefully!""".replace("  ", ""), status="Warning")
            report.add_result(result)
        
        self.report.add_result(report)
        logger.debug(f"Outgoing report: {self.report.results}")
        
    def clear_form(self):
        """
        Removes all form widgets
        """        
        for item in self.findChildren(QWidget):
            item.setParent(None)

    def find_widgets(self, object_name:str|None=None) -> List[QWidget]:
        """
        Gets all widgets filtered by object name

        Args:
            object_name (str | None, optional): name to filter by. Defaults to None.

        Returns:
            List[QWidget]: Widgets matching filter
        """        
        query = self.findChildren(QWidget)
        if object_name != None:
            query = [widget for widget in query if widget.objectName()==object_name]
        return query
    
    def submit_new_sample_function(self) -> QWidget:
        """
        Parse forms and add sample to the database.

        Args:
            obj (QMainWindow): original app window

        Returns:
            Tuple[QMainWindow, dict]: Collection of new main app window and result dict
        """    
        logger.debug(f"\n\nBeginning Submission\n\n")
        report = Report()
        # self.pyd: PydSubmission = self.parse_form()
        result = self.parse_form()
        report.add_result(result)
        logger.debug(f"Submission: {pformat(self.pyd)}")
        logger.debug("Checking kit integrity...")
        _, result = self.pyd.check_kit_integrity()
        report.add_result(result)
        if len(result.results) > 0:
            self.app.report.add_result(report)
            self.app.result_reporter()
            return
        logger.debug(f"PYD before transformation into SQL:\n\n{self.pyd}\n\n")
        base_submission, result = self.pyd.toSQL()
        # logger.debug(f"Base submission: {base_submission.to_dict()}")
        # check output message for issues
        match result.code:
            # code 0: everything is fine.
            case 0:
                self.report.add_result(None)
            # code 1: ask for overwrite
            case 1:
                dlg = QuestionAsker(title=f"Review {base_submission.rsl_plate_num}?", message=result.msg)
                if dlg.exec():
                    # Do not add duplicate reagents.
                    # base_submission.reagents = []
                    result = None
                else:
                    self.app.ctx.database_session.rollback()
                    self.report.add_result(Result(msg="Overwrite cancelled", status="Information"))
                    return
            # code 2: No RSL plate number given
            case 2:
                self.report.add_result(result)
                return
            case _:
                pass
        # add reagents to submission object
        for reagent in base_submission.reagents:
            # logger.debug(f"Updating: {reagent} with {reagent.lot}")
            reagent.update_last_used(kit=base_submission.extraction_kit)
        # logger.debug(f"Here is the final submission: {pformat(base_submission.__dict__)}")
        # logger.debug(f"Parsed reagents: {pformat(base_submission.reagents)}")    
        # logger.debug(f"Sending submission: {base_submission.rsl_plate_num} to database.")
        # logger.debug(f"Samples from pyd: {pformat(self.pyd.samples)}")
        # logger.debug(f"Samples SQL: {pformat([item.__dict__ for item in base_submission.samples])}")
        # logger.debug(f"")
        base_submission.save()
        # update summary sheet
        self.app.table_widget.sub_wid.setData()
        # reset form
        self.setParent(None)
        # logger.debug(f"All attributes of obj: {pformat(self.__dict__)}")
        self.app.report.add_result(report)
        self.app.result_reporter()

    def export_csv_function(self, fname:Path|None=None):
        """
        Save the submission's csv file.

        Args:
            fname (Path | None, optional): Input filename. Defaults to None.
        """        
        self.parse_form()
        if isinstance(fname, bool) or fname == None:
            fname = select_save_file(obj=self, default_name=self.pyd.construct_filename(), extension="csv")
        try:
            self.pyd.csv.to_csv(fname.__str__(), index=False)
        except PermissionError:
            logger.debug(f"Could not get permissions to {fname}. Possibly the request was cancelled.")

    def parse_form(self) -> PydSubmission:
        """
        Transforms form info into PydSubmission

        Returns:
            PydSubmission: Pydantic submission object 
        """        
        report = Report()
        logger.debug(f"Hello from form parser!")
        info = {}
        reagents = []
        for widget in self.findChildren(QWidget):
            # logger.debug(f"Parsed widget of type {type(widget)}")
            match widget:
                case self.ReagentFormWidget():
                    reagent, _ = widget.parse_form()
                    if reagent != None:
                        reagents.append(reagent)
                case self.InfoItem():
                    field, value = widget.parse_form()
                    if field != None:
                        info[field] = value
        logger.debug(f"Info: {pformat(info)}")
        logger.debug(f"Reagents: {pformat(reagents)}")
        self.pyd.reagents = reagents
        # logger.debug(f"Attrs not in info: {[k for k, v in self.__dict__.items() if k not in info.keys()]}")
        for item in self.recover:
            logger.debug(f"Attempting to recover: {item}")
            if hasattr(self, item):
                value = getattr(self, item)
                logger.debug(f"Setting {item}")
                info[item] = value
        # submission = PydSubmission(reagents=reagents, **info)
        for k,v in info.items():
            self.pyd.set_attribute(key=k, value=v)
        # return submission
        self.report.add_result(report)
    
    class InfoItem(QWidget):

        def __init__(self, parent: QWidget, key:str, value:dict, submission_type:str|None=None) -> None:
            super().__init__(parent)
            layout = QVBoxLayout()
            self.label = self.ParsedQLabel(key=key, value=value)
            self.input: QWidget = self.set_widget(parent=self, key=key, value=value, submission_type=submission_type)
            self.setObjectName(key)
            try:
                self.missing:bool = value['missing']
            except (TypeError, KeyError):
                self.missing:bool = True
            if self.input != None:
                layout.addWidget(self.label)
                layout.addWidget(self.input)
            layout.setContentsMargins(0,0,0,0)
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
        
        def set_widget(self, parent: QWidget, key:str, value:dict, submission_type:str|None=None) -> QWidget:
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
            try:
                value = value['value']
            except (TypeError, KeyError):
                pass
            obj = parent.parent().parent()
            logger.debug(f"Creating widget for: {key}")
            match key:
                case 'submitting_lab':
                    add_widget = QComboBox()
                    # lookup organizations suitable for submitting_lab (ctx: self.InfoItem.SubmissionFormWidget.SubmissionFormContainer.AddSubForm )
                    labs = [item.name for item in Organization.query()]
                    # try to set closest match to top of list
                    try:
                        labs = difflib.get_close_matches(value, labs, len(labs), 0)
                    except (TypeError, ValueError):
                        pass
                    # set combobox values to lookedup values
                    add_widget.addItems(labs)
                case 'extraction_kit':
                    # if extraction kit not available, all other values fail
                    if not check_not_nan(value):
                        msg = AlertPop(message="Make sure to check your extraction kit in the excel sheet!", status="warning")
                        msg.exec()
                    # create combobox to hold looked up kits
                    add_widget = QComboBox()
                    # lookup existing kits by 'submission_type' decided on by sheetparser
                    logger.debug(f"Looking up kits used for {submission_type}")
                    uses = [item.name for item in KitType.query(used_for=submission_type)]
                    obj.uses = uses
                    logger.debug(f"Kits received for {submission_type}: {uses}")
                    if check_not_nan(value):
                        logger.debug(f"The extraction kit in parser was: {value}")
                        uses.insert(0, uses.pop(uses.index(value)))
                        obj.ext_kit = value
                    else:
                        logger.error(f"Couldn't find {obj.prsr.sub['extraction_kit']}")
                        obj.ext_kit = uses[0]
                    add_widget.addItems(uses)
                    
                case 'submitted_date':
                    # uses base calendar
                    add_widget = QDateEdit(calendarPopup=True)
                    # sets submitted date based on date found in excel sheet
                    try:
                        add_widget.setDate(value)
                    # if not found, use today
                    except:
                        add_widget.setDate(date.today())
                case 'submission_category':
                    add_widget = QComboBox()
                    cats = ['Diagnostic', "Surveillance", "Research"]
                    cats += [item.name for item in SubmissionType.query()]
                    try:
                        cats.insert(0, cats.pop(cats.index(value)))
                    except ValueError:
                        cats.insert(0, cats.pop(cats.index(submission_type)))
                    add_widget.addItems(cats)
                case _:
                    # anything else gets added in as a line edit
                    add_widget = QLineEdit()
                    logger.debug(f"Setting widget text to {str(value).replace('_', ' ')}")
                    add_widget.setText(str(value).replace("_", " "))
            if add_widget != None:
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

            def __init__(self, key:str, value:dict, title:bool=True, label_name:str|None=None):
                super().__init__()
                try:
                    check = not value['missing']
                except:
                    check = True
                if label_name != None:
                    self.setObjectName(label_name)
                else:
                    self.setObjectName(f"{key}_label")
                if title:
                    output = key.replace('_', ' ').title()
                else:
                    output = key.replace('_', ' ')
                if check:
                    self.setText(f"Parsed {output}")
                else:
                    self.setText(f"MISSING {output}")

            def updated(self, key:str, title:bool=True):
                """
                Mark widget as updated

                Args:
                    key (str): Name of the field
                    title (bool, optional): Use title case. Defaults to True.
                """                
                if title:
                    output = key.replace('_', ' ').title()
                else:
                    output = key.replace('_', ' ')
                self.setText(f"UPDATED {output}")

    class ReagentFormWidget(QWidget):

        def __init__(self, parent:QWidget, reagent:PydReagent, extraction_kit:str):
            super().__init__(parent)
            self.app = self.parent().parent().parent().parent().parent().parent().parent().parent()
            self.reagent = reagent
            self.extraction_kit = extraction_kit
            layout = QVBoxLayout()
            self.label = self.ReagentParsedLabel(reagent=reagent)
            layout.addWidget(self.label)
            self.lot = self.ReagentLot(reagent=reagent, extraction_kit=extraction_kit)
            layout.addWidget(self.lot)
            # Remove spacing between reagents
            layout.setContentsMargins(0,0,0,0)
            self.setLayout(layout)
            self.setObjectName(reagent.name)
            self.missing = reagent.missing
            # If changed set self.missing to True and update self.label
            self.lot.currentTextChanged.connect(self.updated)

        def parse_form(self) -> Tuple[PydReagent, dict]:
            """
            Pulls form info into PydReagent

            Returns:
                Tuple[PydReagent, dict]: PydReagent and Report(?)
            """        
            lot = self.lot.currentText()
            logger.debug(f"Using this lot for the reagent {self.reagent}: {lot}")
            wanted_reagent = Reagent.query(lot_number=lot, reagent_type=self.reagent.type)
            # if reagent doesn't exist in database, offer to add it (uses App.add_reagent)
            if wanted_reagent == None:
                dlg = QuestionAsker(title=f"Add {lot}?", message=f"Couldn't find reagent type {self.reagent.type}: {lot} in the database.\n\nWould you like to add it?")
                if dlg.exec():
                    wanted_reagent = self.parent().parent().add_reagent(reagent_lot=lot, reagent_type=self.reagent.type, expiry=self.reagent.expiry, name=self.reagent.name)
                    return wanted_reagent, None
                else:
                    # In this case we will have an empty reagent and the submission will fail kit integrity check
                    logger.debug("Will not add reagent.")
                    return None, Result(msg="Failed integrity check", status="Critical")
            else:
                # Since this now gets passed in directly from the parser -> pyd -> form and the parser gets the name
                # from the db, it should no longer be necessary to query the db with reagent/kit, but with rt name directly.
                rt = ReagentType.query(name=self.reagent.type)
                if rt == None:
                    rt = ReagentType.query(kit_type=self.extraction_kit, reagent=wanted_reagent)
                return PydReagent(name=wanted_reagent.name, lot=wanted_reagent.lot, type=rt.name, expiry=wanted_reagent.expiry, parsed=not self.missing), None

        def updated(self):
            """
            Set widget status to updated
            """        
            self.missing = True
            self.label.updated(self.reagent.type)

        class ReagentParsedLabel(QLabel):
            
            def __init__(self, reagent:PydReagent):
                super().__init__()
                try:
                    check = not reagent.missing
                except:
                    check = False
                self.setObjectName(f"{reagent.type}_label")
                if check:
                    self.setText(f"Parsed {reagent.type}")
                else:
                    self.setText(f"MISSING {reagent.type}")
            
            def updated(self, reagent_type:str):
                """
                Marks widget as updated

                Args:
                    reagent_type (str): _description_
                """            
                self.setText(f"UPDATED {reagent_type}")

        class ReagentLot(QComboBox):

            def __init__(self, reagent, extraction_kit:str) -> None:
                super().__init__()
                self.setEditable(True)
                logger.debug(f"Attempting lookup of reagents by type: {reagent.type}")
                # below was lookup_reagent_by_type_name_and_kit_name, but I couldn't get it to work.
                lookup = Reagent.query(reagent_type=reagent.type)
                relevant_reagents = [str(item.lot) for item in lookup]
                output_reg = []
                for rel_reagent in relevant_reagents:
                # extract strings from any sets.
                    if isinstance(rel_reagent, set):
                        for thing in rel_reagent:
                            output_reg.append(thing)
                    elif isinstance(rel_reagent, str):
                        output_reg.append(rel_reagent)
                relevant_reagents = output_reg
                # if reagent in sheet is not found insert it into the front of relevant reagents so it shows 
                logger.debug(f"Relevant reagents for {reagent.lot}: {relevant_reagents}")
                if str(reagent.lot) not in relevant_reagents:
                    if check_not_nan(reagent.lot):
                        relevant_reagents.insert(0, str(reagent.lot))
                    else:
                        looked_up_rt = KitTypeReagentTypeAssociation.query(reagent_type=reagent.type, kit_type=extraction_kit)
                        try:
                            looked_up_reg = Reagent.query(lot_number=looked_up_rt.last_used)
                        except AttributeError:
                            looked_up_reg = None
                        if isinstance(looked_up_reg, list):
                            looked_up_reg = None
                        # logger.debug(f"Because there was no reagent listed for {reagent.lot}, we will insert the last lot used: {looked_up_reg}")
                        if looked_up_reg != None:
                            relevant_reagents.remove(str(looked_up_reg.lot))
                            relevant_reagents.insert(0, str(looked_up_reg.lot))
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
                self.setObjectName(f"lot_{reagent.type}")
                self.addItems(relevant_reagents)
