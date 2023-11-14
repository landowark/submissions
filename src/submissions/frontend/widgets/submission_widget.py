from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout,
    QComboBox, QDateEdit, QLineEdit, QLabel
)
from PyQt6.QtCore import pyqtSignal
from pathlib import Path
from . import select_open_file, select_save_file
import logging
from pathlib import Path
from tools import Report, Result, check_not_nan
from backend.excel.parser import SheetParser, PCRParser
from backend.validators import PydSubmission, PydReagent
from backend.db import (
    check_kit_integrity, update_last_used, KitType, Organization, SubmissionType, Reagent, 
    ReagentType, KitTypeReagentTypeAssociation, BasicSubmission, update_subsampassoc_with_pcr
)
from pprint import pformat
from .pop_ups import QuestionAsker, AlertPop
# from .misc import ReagentFormWidget
from typing import List, Tuple
import difflib
from datetime import date
import inspect
import json


logger = logging.getLogger(f"submissions.{__name__}")

class SubmissionFormContainer(QWidget):

    import_drag = pyqtSignal(Path)

    def __init__(self, parent: QWidget) -> None:
        logger.debug(f"Setting form widget...")
        super().__init__(parent)
        self.app = self.parent().parent#().parent().parent().parent().parent().parent
        self.report = Report()
        # self.parent = parent
        self.setAcceptDrops(True)
        self.import_drag.connect(self.importSubmission)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        fname = Path([u.toLocalFile() for u in event.mimeData().urls()][0])
        
        logger.debug(f"App: {self.app}")
        self.app.last_dir = fname.parent
        self.import_drag.emit(fname)

    def importSubmission(self, fname:Path|None=None):
        """
        import submission from excel sheet into form
        """        
        # from .main_window_functions import import_submission_function
        self.app.raise_()
        self.app.activateWindow()
        self.import_submission_function(fname)
        logger.debug(f"Result from result reporter: {self.report.results}")
        self.app.report.add_result(self.report)
        self.report = Report()
        self.app.result_reporter()

    def scrape_reagents(self, *args, **kwargs):
        # from .main_window_functions import scrape_reagents
        # logger.debug(f"Args: {args}")
        # logger.debug(F"kwargs: {kwargs}")
        print(f"\n\n{inspect.stack()[1].function}\n\n")
        self.scrape_reagents_function(args[0])
        self.kit_integrity_completion()
        self.app.report.add_result(self.report)
        self.report = Report()
        match inspect.stack()[1].function:
            case "import_submission_function":
                pass
            case _:
                self.app.result_reporter()

    # def kit_reload_function(self):
    #     """
    #     Reload the fields in the form

    #     Args:
    #         obj (QMainWindow): original app window

    #     Returns:
    #         Tuple[QMainWindow, dict]: Collection of new main app window and result dict
    #     """    
    #     report = Report()
    #     # for item in obj.table_widget.formlayout.parentWidget().findChildren(QWidget):
    #     logger.debug(f"Attempting to clear {obj.form.find_widgets()}")
    #     for item in self.form.find_widgets():
    #         if isinstance(item, ReagentFormWidget):
    #             item.setParent(None)
    #     self.kit_integrity_completion_function()
    #     self.report.add_result(report)



    def kit_integrity_completion(self):
        """
        Performs check of imported reagents
        NOTE: this will not change self.reagents which should be fine
        since it's only used when looking up 
        """        
        # from .main_window_functions import kit_integrity_completion_function
        self.kit_integrity_completion_function()
        self.app.report.add_result(self.report)
        self.report = Report()
        match inspect.stack()[1].function:
            case "import_submission_function":
                pass
            case _:
                self.app.result_reporter()

    def submit_new_sample(self):
        """
        Attempt to add sample to database when 'submit' button clicked
        """        
        # from .main_window_functions import submit_new_sample_function
        self.submit_new_sample_function()
        self.app.report.add_result(self.report)
        self.report = Report()
        self.app.result_reporter()

    def export_csv(self, fname:Path|None=None):
        # from .main_window_functions import export_csv_function
        self.export_csv_function(fname)

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
        # logger.debug(obj.ctx)
        # initialize samples
        try:
            self.form.setParent(None)
        except AttributeError:
            pass
        self.samples = []
        self.missing_info = []
        # set file dialog
        if isinstance(fname, bool) or fname == None:
            fname = select_open_file(self, file_extension="xlsx")
        logger.debug(f"Attempting to parse file: {fname}")
        if not fname.exists():
            # result = dict(message=f"File {fname.__str__()} not found.", status="critical")
            report.add_result(Result(msg=f"File {fname.__str__()} not found.", status="critical"))
            self.report.add_result(report)
            return
        # create sheetparser using excel sheet and context from gui
        try:
            self.prsr = SheetParser(ctx=self.ctx, filepath=fname)
        except PermissionError:
            logger.error(f"Couldn't get permission to access file: {fname}")
            return
        except AttributeError:
            self.prsr = SheetParser(ctx=self.app.ctx, filepath=fname)
        try:
            logger.debug(f"Submission dictionary:\n{pformat(self.prsr.sub)}")
            self.pyd = self.prsr.to_pydantic()
            logger.debug(f"Pydantic result: \n\n{pformat(self.pyd)}\n\n")
        except Exception as e:
            report.add_result(Result(msg=f"Problem creating pydantic model:\n\n{e}", status="Critical"))
            self.report.add_result(report)
            return
        self.form = self.pyd.toForm(parent=self)
        self.layout().addWidget(self.form)
        kit_widget = self.form.find_widgets(object_name="extraction_kit")[0].input
        logger.debug(f"Kitwidget {kit_widget}")
        self.scrape_reagents(kit_widget.currentText())
        kit_widget.currentTextChanged.connect(self.scrape_reagents)
        # compare obj.reagents with expected reagents in kit
        if self.prsr.sample_result != None:
            report.add_result(msg=self.prsr.sample_result, status="Warning")
        self.report.add_result(report)
        logger.debug(f"Outgoing report: {self.report.results}")
        logger.debug(f"All attributes of submission container:\n{pformat(self.__dict__)}")

    def scrape_reagents_function(self, extraction_kit:str):
        """
        Extracted scrape reagents function that will run when 
        form 'extraction_kit' widget is updated.

        Args:
            obj (QMainWindow): updated main application
            extraction_kit (str): name of extraction kit (in 'extraction_kit' widget)

        Returns:
            Tuple[QMainWindow, dict]: Updated application and result
        """    
        report = Report()
        logger.debug(f"Extraction kit: {extraction_kit}")
        # obj.reagents = []
        # obj.missing_reagents = []
        # Remove previous reagent widgets
        try:
            old_reagents = self.form.find_widgets()
        except AttributeError:
            logger.error(f"Couldn't find old reagents.")
            old_reagents = []
        # logger.debug(f"\n\nAttempting to clear: {old_reagents}\n\n")
        for reagent in old_reagents:
            if isinstance(reagent, ReagentFormWidget) or isinstance(reagent, QPushButton):
                reagent.setParent(None)
        # reagents = obj.prsr.parse_reagents(extraction_kit=extraction_kit)
        # logger.debug(f"Got reagents: {reagents}")
        # for reagent in obj.prsr.sub['reagents']:
        #     # create label
        #     if reagent.parsed:
        #         obj.reagents.append(reagent)
        #     else:
        #         obj.missing_reagents.append(reagent)
        self.form.reagents = self.prsr.sub['reagents']
        # logger.debug(f"Imported reagents: {obj.reagents}")
        # logger.debug(f"Missing reagents: {obj.missing_reagents}")
        self.report.add_result(report)
        logger.debug(f"Outgoing report: {self.report.results}")

    def kit_integrity_completion_function(self):
        """
        Compare kit contents to parsed contents

        Args:
            obj (QMainWindow): The original app window

        Returns:
            Tuple[QMainWindow, dict]: Collection of new main app window and result dict
        """    
        report = Report()
        missing_reagents = []
        # logger.debug(inspect.currentframe().f_back.f_code.co_name)
        # find the widget that contains kit info
        kit_widget = self.form.find_widgets(object_name="extraction_kit")[0].input
        logger.debug(f"Kit selector: {kit_widget}")
        # get current kit being used
        self.ext_kit = kit_widget.currentText()
        # for reagent in obj.pyd.reagents:
        for reagent in self.form.reagents:
            add_widget = ReagentFormWidget(parent=self, reagent=reagent, extraction_kit=self.ext_kit)
            # add_widget.setParent(sub_form_container.form)
            self.form.layout().addWidget(add_widget)
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
        if hasattr(self.pyd, "csv"):
            export_csv_btn = QPushButton("Export CSV")
            export_csv_btn.setObjectName("export_csv_btn")
            self.form.layout().addWidget(export_csv_btn)
            export_csv_btn.clicked.connect(self.export_csv)
        submit_btn = QPushButton("Submit")
        submit_btn.setObjectName("submit_btn")
        self.form.layout().addWidget(submit_btn)
        submit_btn.clicked.connect(self.submit_new_sample)
        self.report.add_result(report)
        logger.debug(f"Outgoing report: {self.report.results}")

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
        self.pyd: PydSubmission = self.form.parse_form()
        logger.debug(f"Submission: {pformat(self.pyd)}")
        logger.debug("Checking kit integrity...")
        result = check_kit_integrity(sub=self.pyd)
        report.add_result(result)
        if len(result.results) > 0:
            self.report.add_result(report)
            return
        base_submission, result = self.pyd.toSQL()
        # check output message for issues
        match result.code:
            # code 0: everything is fine.
            case 0:
                self.report.add_result(None)
            # code 1: ask for overwrite
            case 1:
                dlg = QuestionAsker(title=f"Review {base_submission.rsl_plate_num}?", message=result['message'])
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
            update_last_used(reagent=reagent, kit=base_submission.extraction_kit)
        logger.debug(f"Here is the final submission: {pformat(base_submission.__dict__)}")
        logger.debug(f"Parsed reagents: {pformat(base_submission.reagents)}")    
        logger.debug(f"Sending submission: {base_submission.rsl_plate_num} to database.")
        base_submission.save()
        # update summary sheet
        self.app.table_widget.sub_wid.setData()
        # reset form
        self.form.setParent(None)
        logger.debug(f"All attributes of obj: {pformat(self.__dict__)}")
        wkb = self.pyd.autofill_excel()
        if wkb != None:
            fname = select_save_file(obj=self, default_name=self.pyd.construct_filename(), extension="xlsx")
            try:
                wkb.save(filename=fname.__str__())
            except PermissionError:
                logger.error("Hit a permission error when saving workbook. Cancelled?")
        if hasattr(self.pyd, 'csv'):
            dlg = QuestionAsker("Export CSV?", "Would you like to export the csv file?")
            if dlg.exec():
                fname = select_save_file(self, f"{self.pyd.construct_filename()}.csv", extension="csv")
                try:
                    self.pyd.csv.to_csv(fname.__str__(), index=False)
                except PermissionError:
                    logger.debug(f"Could not get permissions to {fname}. Possibly the request was cancelled.")
        self.report.add_result(report)

    def export_csv_function(self, fname:Path|None=None):
        if isinstance(fname, bool) or fname == None:
            fname = select_save_file(obj=self, default_name=self.pyd.construct_filename(), extension="csv")
        try:
            self.pyd.csv.to_csv(fname.__str__(), index=False)
        except PermissionError:
            logger.debug(f"Could not get permissions to {fname}. Possibly the request was cancelled.")

    def import_pcr_results(self):
        self.import_pcr_results_function()
        self.app.report.add_result(self.report)
        self.report = Report()
        self.app.result_reporter()

    def import_pcr_results_function(self):
        """
        Import Quant-studio PCR data to an imported submission

        Args:
            obj (QMainWindow): original app window

        Returns:
            Tuple[QMainWindow, dict]: Collection of new main app window and result dict
        """    
        report = Report()
        fname = select_open_file(self, file_extension="xlsx")
        parser = PCRParser(filepath=fname)
        logger.debug(f"Attempting lookup for {parser.plate_num}")
        # sub = lookup_submission_by_rsl_num(ctx=obj.ctx, rsl_num=parser.plate_num)
        sub = BasicSubmission.query(rsl_number=parser.plate_num)
        try:
            logger.debug(f"Found submission: {sub.rsl_plate_num}")
        except AttributeError:
            # If no plate is found, may be because this is a repeat. Lop off the '-1' or '-2' and repeat
            logger.error(f"Submission of number {parser.plate_num} not found. Attempting rescue of plate repeat.")
            parser.plate_num = "-".join(parser.plate_num.split("-")[:-1])
            # sub = lookup_submission_by_rsl_num(ctx=obj.ctx, rsl_num=parser.plate_num)
            # sub = lookup_submissions(ctx=obj.ctx, rsl_number=parser.plate_num)
            sub = BasicSubmission.query(rsl_number=parser.plate_num)
            try:
                logger.debug(f"Found submission: {sub.rsl_plate_num}")
            except AttributeError:
                logger.error(f"Rescue of {parser.plate_num} failed.")
                # return obj, dict(message="Couldn't find a submission with that RSL number.", status="warning")
                self.report.add_result(Result(msg="Couldn't find a submission with that RSL number.", status="Warning"))
                return
        # Check if PCR info already exists
        if hasattr(sub, 'pcr_info') and sub.pcr_info != None:
            existing = json.loads(sub.pcr_info)
        else:
            existing = None
        if existing != None:
            # update pcr_info
            try:
                logger.debug(f"Updating {type(existing)}: {existing} with {type(parser.pcr)}: {parser.pcr}")
                if json.dumps(parser.pcr) not in sub.pcr_info:
                    existing.append(parser.pcr)
                logger.debug(f"Setting: {existing}")
                sub.pcr_info = json.dumps(existing)
            except TypeError:
                logger.error(f"Error updating!")
                sub.pcr_info = json.dumps([parser.pcr])
            logger.debug(f"Final pcr info for {sub.rsl_plate_num}: {sub.pcr_info}")
        else:
            sub.pcr_info = json.dumps([parser.pcr])
        # obj.ctx.database_session.add(sub)
        logger.debug(f"Existing {type(sub.pcr_info)}: {sub.pcr_info}")
        logger.debug(f"Inserting {type(json.dumps(parser.pcr))}: {json.dumps(parser.pcr)}")
        sub.save()
        logger.debug(f"Got {len(parser.samples)} samples to update!")
        logger.debug(f"Parser samples: {parser.samples}")
        for sample in sub.samples:
            logger.debug(f"Running update on: {sample}")
            try:
                sample_dict = [item for item in parser.samples if item['sample']==sample.rsl_number][0]
            except IndexError:
                continue
            update_subsampassoc_with_pcr(submission=sub, sample=sample, input_dict=sample_dict)
        self.report.add_result(Result(msg=f"We added PCR info to {sub.rsl_plate_num}.", status='Information'))
        # return obj, result

class SubmissionFormWidget(QWidget):

    def __init__(self, parent: QWidget, **kwargs) -> None:
        super().__init__(parent)
        # self.ignore = [None, "", "qt_spinbox_lineedit", "qt_scrollarea_viewport", "qt_scrollarea_hcontainer",
        #                "qt_scrollarea_vcontainer", "submit_btn"
        #                ]
        self.ignore = ['filepath', 'samples', 'reagents', 'csv', 'ctx']
        layout = QVBoxLayout()
        for k, v in kwargs.items():
            if k not in self.ignore:
                add_widget = self.create_widget(key=k, value=v, submission_type=kwargs['submission_type'])
                if add_widget != None:
                    layout.addWidget(add_widget)
            else:
                setattr(self, k, v)
        
        self.setLayout(layout)

    def create_widget(self, key:str, value:dict, submission_type:str|None=None):
        if key not in self.ignore:
            return self.InfoItem(self, key=key, value=value, submission_type=submission_type)
        return None
        
    def clear_form(self):
        for item in self.findChildren(QWidget):
            item.setParent(None)

    def find_widgets(self, object_name:str|None=None) -> List[QWidget]:
        query = self.findChildren(QWidget)
        if object_name != None:
            query = [widget for widget in query if widget.objectName()==object_name]
        return query
    
    def parse_form(self) -> PydSubmission:
        logger.debug(f"Hello from form parser!")
        info = {}
        reagents = []
        if hasattr(self, 'csv'):
            info['csv'] = self.csv
        for widget in self.findChildren(QWidget):
            # logger.debug(f"Parsed widget of type {type(widget)}")
            match widget:
                case ReagentFormWidget():
                    reagent, _ = widget.parse_form()
                    if reagent != None:
                        reagents.append(reagent)
                case self.InfoItem():
                    field, value = widget.parse_form()
                    if field != None:
                        info[field] = value
        logger.debug(f"Info: {pformat(info)}")
        logger.debug(f"Reagents: {pformat(reagents)}")
        # app = self.parent().parent().parent().parent().parent().parent().parent().parent
        submission = PydSubmission(filepath=self.filepath, reagents=reagents, samples=self.samples, **info)
        return submission
    
    class InfoItem(QWidget):

        def __init__(self, parent: QWidget, key:str, value:dict, submission_type:str|None=None) -> None:
            super().__init__(parent)
            layout = QVBoxLayout()
            self.label = self.ParsedQLabel(key=key, value=value)
            self.input: QWidget = self.set_widget(parent=self, key=key, value=value, submission_type=submission_type['value'])
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
            
        def parse_form(self):
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
                    labs = [item.__str__() for item in Organization.query()]
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
                    uses = [item.__str__() for item in KitType.query(used_for=submission_type)]
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
                    # Run reagent scraper whenever extraction kit is changed.
                    # add_widget.currentTextChanged.connect(obj.scrape_reagents)
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
                    # cats += [item.name for item in lookup_submission_type(ctx=obj.ctx)]
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
                if title:
                    output = key.replace('_', ' ').title()
                else:
                    output = key.replace('_', ' ')
                self.setText(f"UPDATED {output}")

class ReagentFormWidget(QWidget):

    def __init__(self, parent:QWidget, reagent:PydReagent, extraction_kit:str):
        super().__init__(parent)
        # self.setParent(parent)
        self.reagent = reagent
        self.extraction_kit = extraction_kit
        # self.ctx = reagent.ctx
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
        lot = self.lot.currentText()
        # wanted_reagent = lookup_reagents(ctx=self.ctx, lot_number=lot, reagent_type=self.reagent.type)
        wanted_reagent = Reagent.query(lot_number=lot, reagent_type=self.reagent.type)
        # if reagent doesn't exist in database, off to add it (uses App.add_reagent)
        if wanted_reagent == None:
            dlg = QuestionAsker(title=f"Add {lot}?", message=f"Couldn't find reagent type {self.reagent.type}: {lot} in the database.\n\nWould you like to add it?")
            if dlg.exec():
                wanted_reagent = self.parent().parent().parent().parent().parent().parent().parent().parent().parent.add_reagent(reagent_lot=lot, reagent_type=self.reagent.type, expiry=self.reagent.expiry, name=self.reagent.name)
                return wanted_reagent, None
            else:
                # In this case we will have an empty reagent and the submission will fail kit integrity check
                logger.debug("Will not add reagent.")
                return None, Result(msg="Failed integrity check", status="Critical")
        else:
            # Since this now gets passed in directly from the parser -> pyd -> form and the parser gets the name
            # from the db, it should no longer be necessary to query the db with reagent/kit, but with rt name directly.
            # rt = lookup_reagent_types(ctx=self.ctx, name=self.reagent.type)
            # rt = lookup_reagent_types(ctx=self.ctx, kit_type=self.extraction_kit, reagent=wanted_reagent)
            rt = ReagentType.query(name=self.reagent.type)
            if rt == None:
                # rt = lookup_reagent_types(ctx=self.ctx, kit_type=self.extraction_kit, reagent=wanted_reagent)
                rt = ReagentType.query(kit_type=self.extraction_kit, reagent=wanted_reagent)
            return PydReagent(name=wanted_reagent.name, lot=wanted_reagent.lot, type=rt.name, expiry=wanted_reagent.expiry, parsed=not self.missing), None

    def updated(self):
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
            self.setText(f"UPDATED {reagent_type}")

    class ReagentLot(QComboBox):

        def __init__(self, reagent, extraction_kit:str) -> None:
            super().__init__()
            # self.ctx = reagent.ctx
            self.setEditable(True)
            # if reagent.parsed:
            #     pass
            logger.debug(f"Attempting lookup of reagents by type: {reagent.type}")
            # below was lookup_reagent_by_type_name_and_kit_name, but I couldn't get it to work.
            # lookup = lookup_reagents(ctx=self.ctx, reagent_type=reagent.type)
            lookup = Reagent.query(reagent_type=reagent.type)
            relevant_reagents = [item.__str__() for item in lookup]
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
                    # TODO: look up the last used reagent of this type in the database
                    # looked_up_rt = lookup_reagenttype_kittype_association(ctx=self.ctx, reagent_type=reagent.type, kit_type=extraction_kit)
                    looked_up_rt = KitTypeReagentTypeAssociation.query(reagent_type=reagent.type, kit_type=extraction_kit)
                    try:
                        # looked_up_reg = lookup_reagents(ctx=self.ctx, lot_number=looked_up_rt.last_used)
                        looked_up_reg = Reagent.query(lot_number=looked_up_rt.last_used)
                    except AttributeError:
                        looked_up_reg = None
                    logger.debug(f"Because there was no reagent listed for {reagent.lot}, we will insert the last lot used: {looked_up_reg}")
                    if looked_up_reg != None:
                        relevant_reagents.remove(str(looked_up_reg.lot))
                        relevant_reagents.insert(0, str(looked_up_reg.lot))
            else:
                if len(relevant_reagents) > 1:
                    logger.debug(f"Found {reagent.lot} in relevant reagents: {relevant_reagents}. Moving to front of list.")
                    idx = relevant_reagents.index(str(reagent.lot))
                    logger.debug(f"The index we got for {reagent.lot} in {relevant_reagents} was {idx}")
                    moved_reag = relevant_reagents.pop(idx)
                    relevant_reagents.insert(0, moved_reag)
                else:
                    logger.debug(f"Found {reagent.lot} in relevant reagents: {relevant_reagents}. But no need to move due to short list.")
            logger.debug(f"New relevant reagents: {relevant_reagents}")
            self.setObjectName(f"lot_{reagent.type}")
            self.addItems(relevant_reagents)

