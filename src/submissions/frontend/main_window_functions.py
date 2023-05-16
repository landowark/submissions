'''
contains operations used by multiple widgets.
'''
from datetime import date
import difflib
from getpass import getuser
import inspect
from pathlib import Path
import pprint
import re
import yaml
import json
from typing import Tuple
from openpyxl.utils import get_column_letter
from xhtml2pdf import pisa
import pandas as pd
from backend.db.models import *
import logging
from PyQt6.QtWidgets import (
    QMainWindow, QLabel, QWidget, QPushButton, QFileDialog,
    QLineEdit, QMessageBox, QComboBox, QDateEdit
)
from .all_window_functions import extract_form_info, select_open_file, select_save_file
from PyQt6.QtCore import QSignalBlocker
from backend.db.functions import (
    lookup_all_orgs, lookup_kittype_by_use, lookup_kittype_by_name, 
    construct_submission_info, lookup_reagent, store_submission, lookup_submissions_by_date_range, 
    create_kit_from_yaml, create_org_from_yaml, get_control_subtypes, get_all_controls_by_type,
    lookup_all_submissions_by_type, get_all_controls, lookup_submission_by_rsl_num, update_ww_sample
)
from backend.excel.parser import SheetParser, PCRParser
from backend.excel.reports import make_report_html, make_report_xlsx, convert_data_list_to_df
from tools import RSLNamer, check_not_nan, check_kit_integrity
from .custom_widgets.pop_ups import AlertPop, QuestionAsker
from .custom_widgets import ReportDatePicker, ReagentTypeForm
from .custom_widgets.misc import ImportReagent
from .visualizations.control_charts import create_charts, construct_html


logger = logging.getLogger(f"submissions.{__name__}")

def import_submission_function(obj:QMainWindow) -> Tuple[QMainWindow, dict|None]:
    result = None
    # from .custom_widgets.misc import ImportReagent
    # from .custom_widgets.pop_ups import AlertPop
    logger.debug(obj.ctx)
    # initialize samples
    obj.samples = []
    obj.reagents = {}
    # set file dialog
    # home_dir = str(Path(obj.ctx["directory_path"]))
    # fname = Path(QFileDialog.getOpenFileName(obj, 'Open file', home_dir)[0])
    fname = select_open_file(obj, extension="xlsx")
    logger.debug(f"Attempting to parse file: {fname}")
    if not fname.exists():
        result = dict(message=f"File {fname.__str__()} not found.", status="critical")
        return obj, result
    # create sheetparser using excel sheet and context from gui
    try:
        prsr = SheetParser(fname, **obj.ctx)
    except PermissionError:
        logger.error(f"Couldn't get permission to access file: {fname}")
        return
    if prsr.sub['rsl_plate_num'] == None:
        prsr.sub['rsl_plate_num'] = RSLNamer(fname.__str__()).parsed_name
    logger.debug(f"prsr.sub = {prsr.sub}")
    # destroy any widgets from previous imports
    for item in obj.table_widget.formlayout.parentWidget().findChildren(QWidget):
        item.setParent(None)
    # regex to parser out different variable types for decision making
    variable_parser = re.compile(r"""
        # (?x)
        (?P<extraction_kit>^extraction_kit$) |
        (?P<submitted_date>^submitted_date$) |
        (?P<submitting_lab>)^submitting_lab$ |
        (?P<samples>)^samples$ |
        (?P<reagent>^lot_.*$) |
        (?P<csv>^csv$)
    """, re.VERBOSE)
    for item in prsr.sub:
        logger.debug(f"Item: {item}")
        # attempt to match variable name to regex group
        try:
            mo = variable_parser.fullmatch(item).lastgroup
        except AttributeError:
            mo = "other"
        logger.debug(f"Mo: {mo}")
        match mo:
            case 'submitting_lab':
                # create label
                obj.table_widget.formlayout.addWidget(QLabel(item.replace("_", " ").title()))
                logger.debug(f"{item}: {prsr.sub[item]}")
                # create combobox to hold looked up submitting labs
                add_widget = QComboBox()
                labs = [item.__str__() for item in lookup_all_orgs(ctx=obj.ctx)]
                # try to set closest match to top of list
                try:
                    labs = difflib.get_close_matches(prsr.sub[item], labs, len(labs), 0)
                except (TypeError, ValueError):
                    pass
                # set combobox values to lookedup values
                add_widget.addItems(labs)
            case 'extraction_kit':
                # create label
                obj.table_widget.formlayout.addWidget(QLabel(item.replace("_", " ").title()))
                # if extraction kit not available, all other values fail
                if not check_not_nan(prsr.sub[item]):
                    msg = AlertPop(message="Make sure to check your extraction kit in the excel sheet!", status="warning")
                    msg.exec()
                # create combobox to hold looked up kits
                add_widget = QComboBox()
                # lookup existing kits by 'submission_type' decided on by sheetparser
                uses = [item.__str__() for item in lookup_kittype_by_use(ctx=obj.ctx, used_by=prsr.sub['submission_type'])]
                if check_not_nan(prsr.sub[item]):
                    logger.debug(f"The extraction kit in parser was: {prsr.sub[item]}")
                    uses.insert(0, uses.pop(uses.index(prsr.sub[item])))
                    obj.ext_kit = prsr.sub[item]
                else:
                    logger.error(f"Couldn't find prsr.sub[extraction_kit]")
                    obj.ext_kit = uses[0]
                add_widget.addItems(uses)
            case 'submitted_date':
                # create label
                obj.table_widget.formlayout.addWidget(QLabel(item.replace("_", " ").title()))
                # uses base calendar
                add_widget = QDateEdit(calendarPopup=True)
                # sets submitted date based on date found in excel sheet
                try:
                    add_widget.setDate(prsr.sub[item])
                # if not found, use today
                except:
                    add_widget.setDate(date.today())
            case 'reagent':
                # create label
                reg_label = QLabel(item.replace("_", " ").title())
                reg_label.setObjectName(f"lot_{item}_label")
                obj.table_widget.formlayout.addWidget(reg_label)
                # create reagent choice widget
                add_widget = ImportReagent(ctx=obj.ctx, item=item, prsr=prsr)
                obj.reagents[item] = prsr.sub[item]
            case 'samples':
                # hold samples in 'obj' until form submitted
                logger.debug(f"{item}: {prsr.sub[item]}")
                obj.samples = prsr.sub[item]
                add_widget = None
            case 'csv':
                obj.csv = prsr.sub[item]
            case _:
                # anything else gets added in as a line edit
                obj.table_widget.formlayout.addWidget(QLabel(item.replace("_", " ").title()))
                add_widget = QLineEdit()
                logger.debug(f"Setting widget text to {str(prsr.sub[item]).replace('_', ' ')}")
                add_widget.setText(str(prsr.sub[item]).replace("_", " "))
        try:
            add_widget.setObjectName(item)
            logger.debug(f"Widget name set to: {add_widget.objectName()}")
            obj.table_widget.formlayout.addWidget(add_widget)
        except AttributeError as e:
            logger.error(e)
    # compare obj.reagents with expected reagents in kit
    if hasattr(obj, 'ext_kit'):
        obj.kit_integrity_completion()
    logger.debug(f"Imported reagents: {obj.reagents}")
    
    return obj, result

def kit_reload_function(obj:QMainWindow) -> QMainWindow:
    result = None
    for item in obj.table_widget.formlayout.parentWidget().findChildren(QWidget):
        # item.setParent(None)
        if isinstance(item, QLabel):
            if item.text().startswith("Lot"):
                item.setParent(None)
        else:
            logger.debug(f"Type of {item.objectName()} is {type(item)}")
            if item.objectName().startswith("lot_"):
                item.setParent(None)
    obj.kit_integrity_completion_function()
    return obj, result

def kit_integrity_completion_function(obj:QMainWindow) -> QMainWindow:
    result = None
    # from .custom_widgets.misc import ImportReagent
    # from .custom_widgets.pop_ups import AlertPop
    logger.debug(inspect.currentframe().f_back.f_code.co_name)
    kit_widget = obj.table_widget.formlayout.parentWidget().findChild(QComboBox, 'extraction_kit')
    logger.debug(f"Kit selector: {kit_widget}")
    obj.ext_kit = kit_widget.currentText()
    logger.debug(f"Checking integrity of {obj.ext_kit}")
    kit = lookup_kittype_by_name(ctx=obj.ctx, name=obj.ext_kit)
    reagents_to_lookup = [item.replace("lot_", "") for item in obj.reagents]
    logger.debug(f"Reagents for lookup for {kit.name}: {reagents_to_lookup}")
    kit_integrity = check_kit_integrity(kit, reagents_to_lookup)
    if kit_integrity != None:
        # msg = AlertPop(message=kit_integrity['message'], status="critical")
        # msg.exec()
        result = dict(message=kit_integrity['message'], status="Warning")
        for item in kit_integrity['missing']:
            obj.table_widget.formlayout.addWidget(QLabel(f"Lot {item.replace('_', ' ').title()}"))
            add_widget = ImportReagent(ctx=obj.ctx, item=item)
            obj.table_widget.formlayout.addWidget(add_widget)
    submit_btn = QPushButton("Submit")
    submit_btn.setObjectName("lot_submit_btn")
    obj.table_widget.formlayout.addWidget(submit_btn)
    submit_btn.clicked.connect(obj.submit_new_sample)
    return obj, result

def submit_new_sample_function(obj:QMainWindow) -> QMainWindow:
    result = None
    # from .custom_widgets.misc import ImportReagent
    # from .custom_widgets.pop_ups import AlertPop, QuestionAsker
    info = extract_form_info(obj.table_widget.tab1)
    reagents = {k:v for k,v in info.items() if k.startswith("lot_")}
    info = {k:v for k,v in info.items() if not k.startswith("lot_")}
    logger.debug(f"Info: {info}")
    logger.debug(f"Reagents: {reagents}")
    parsed_reagents = []
    # compare reagents in form to reagent database
    for reagent in reagents:
        wanted_reagent = lookup_reagent(ctx=obj.ctx, reagent_lot=reagents[reagent])
        logger.debug(f"Looked up reagent: {wanted_reagent}")
        # if reagent not found offer to add to database
        if wanted_reagent == None:
            r_lot = reagents[reagent]
            dlg = QuestionAsker(title=f"Add {r_lot}?", message=f"Couldn't find reagent type {reagent.replace('_', ' ').title().strip('Lot')}: {r_lot} in the database.\n\nWould you like to add it?")
            if dlg.exec():
                logger.debug(f"checking reagent: {reagent} in obj.reagents. Result: {obj.reagents[reagent]}")
                expiry_date = obj.reagents[reagent]['exp']
                wanted_reagent = obj.add_reagent(reagent_lot=r_lot, reagent_type=reagent.replace("lot_", ""), expiry=expiry_date)
            else:
                # In this case we will have an empty reagent and the submission will fail kit integrity check
                logger.debug("Will not add reagent.")
        if wanted_reagent != None:
            parsed_reagents.append(wanted_reagent)
    # move samples into preliminary submission dict
    info['samples'] = obj.samples
    info['uploaded_by'] = getuser()
    # construct submission object
    logger.debug(f"Here is the info_dict: {pprint.pformat(info)}")
    base_submission, result = construct_submission_info(ctx=obj.ctx, info_dict=info)
    # check output message for issues
    match result['code']:
        # code 1: ask for overwrite
        case 1:
            dlg = QuestionAsker(title=f"Review {base_submission.rsl_plate_num}?", message=result['message'])
            if dlg.exec():
                # Do not add duplicate reagents.
                base_submission.reagents = []
            else:
                return obj, dict(message="Overwrite cancelled", status="Information")
        # code 2: No RSL plate number given
        case 2:
            return obj, dict(message=result['message'], status='critical')
        case _:
            pass
    # add reagents to submission object
    for reagent in parsed_reagents:
        base_submission.reagents.append(reagent)
    logger.debug("Checking kit integrity...")
    kit_integrity = check_kit_integrity(base_submission)
    if kit_integrity != None:
        return obj, dict(message=kit_integrity['message'], status="critical")
    logger.debug(f"Sending submission: {base_submission.rsl_plate_num} to database.")
    result = store_submission(ctx=obj.ctx, base_submission=base_submission)
    # check result of storing for issues
    # update summary sheet
    obj.table_widget.sub_wid.setData()
    # reset form
    for item in obj.table_widget.formlayout.parentWidget().findChildren(QWidget):
        item.setParent(None)
    # print(dir(obj))
    if hasattr(obj, 'csv'):
        dlg = QuestionAsker("Export CSV?", "Would you like to export the csv file?")
        if dlg.exec():
            # home_dir = Path(obj.ctx["directory_path"]).joinpath(f"{base_submission.rsl_plate_num}.csv").resolve().__str__()
            # fname = Path(QFileDialog.getSaveFileName(obj, "Save File", home_dir, filter=".csv")[0])
            fname = select_save_file(obj, f"{base_submission.rsl_plate_num}.csv", extension="csv")
            try:
                obj.csv.to_csv(fname.__str__(), index=False)
            except PermissionError:
                logger.debug(f"Could not get permissions to {fname}. Possibly the request was cancelled.")
    return obj, result

def generate_report_function(obj:QMainWindow) -> QMainWindow:
    # from .custom_widgets import ReportDatePicker
    result = None
    dlg = ReportDatePicker()
    if dlg.exec():
        info = extract_form_info(dlg)
        logger.debug(f"Report info: {info}")
        # find submissions based on date range
        subs = lookup_submissions_by_date_range(ctx=obj.ctx, start_date=info['start_date'], end_date=info['end_date'])
        # convert each object to dict
        records = [item.report_dict() for item in subs]
        # make dataframe from record dictionaries
        df = make_report_xlsx(records=records)
        html = make_report_html(df=df, start_date=info['start_date'], end_date=info['end_date'])
        # setup filedialog to handle save location of report
        home_dir = Path(obj.ctx["directory_path"]).joinpath(f"Submissions_Report_{info['start_date']}-{info['end_date']}.pdf").resolve().__str__()
        fname = Path(QFileDialog.getSaveFileName(obj, "Save File", home_dir, filter=".pdf")[0])
        # logger.debug(f"report output name: {fname}")
        with open(fname, "w+b") as f:
            pisa.CreatePDF(html, dest=f)
        writer = pd.ExcelWriter(fname.with_suffix(".xlsx"), engine='openpyxl')
        df.to_excel(writer, sheet_name="Report") 
        worksheet = writer.sheets['Report']
        for idx, col in enumerate(df):  # loop through all columns
            series = df[col]
            max_len = max((
                series.astype(str).map(len).max(),  # len of largest item
                len(str(series.name))  # len of column name/header
                )) + 20  # adding a little extra space
            try:
                worksheet.column_dimensions[get_column_letter(idx)].width = max_len 
            except ValueError:
                pass
        for cell in worksheet['D']:
            if cell.row > 1:
                cell.style = 'Currency'
        writer.close()
    return obj, result

def add_kit_function(obj:QMainWindow) -> QMainWindow:
    result = None
    # setup file dialog to find yaml flie
    # home_dir = str(Path(obj.ctx["directory_path"]))
    # fname = Path(QFileDialog.getOpenFileName(obj, 'Open file', home_dir, filter = "yml(*.yml)")[0])
    fname = select_open_file(obj, extension="yml")
    assert fname.exists()
    # read yaml file
    try:
        with open(fname.__str__(), "r") as stream:
            try:
                exp = yaml.load(stream, Loader=yaml.Loader)
            except yaml.YAMLError as exc:
                logger.error(f'Error reading yaml file {fname}: {exc}')
                return {}
    except PermissionError:
        return
    # send to kit creator function
    result = create_kit_from_yaml(ctx=obj.ctx, exp=exp)
    # match result['code']:
    #     case 0:
    #         msg = AlertPop(message=result['message'], status='info')
    #     case 1:
    #         msg = AlertPop(message=result['message'], status='critical')
    # msg.exec()
    return obj, result

def add_org_function(obj:QMainWindow) -> QMainWindow:
    result = None
    # setup file dialog to find yaml flie
    # home_dir = str(Path(obj.ctx["directory_path"]))
    # fname = Path(QFileDialog.getOpenFileName(obj, 'Open file', home_dir, filter = "yml(*.yml)")[0])
    fname = select_open_file(obj, extension="yml")
    assert fname.exists()
    # read yaml file
    try:
        with open(fname.__str__(), "r") as stream:
            try:
                org = yaml.load(stream, Loader=yaml.Loader)
            except yaml.YAMLError as exc:
                logger.error(f'Error reading yaml file {fname}: {exc}')
                return obj, dict(message=f"There was a problem reading yaml file {fname.__str__()}", status="critical")
    except PermissionError:
        return obj, result
    # send to kit creator function
    result = create_org_from_yaml(ctx=obj.ctx, org=org)
    # match result['code']:
    #     case 0:
    #         msg = AlertPop(message=result['message'], status='information')
    #     case 1:
    #         msg = AlertPop(message=result['message'], status='critical')
    # msg.exec()
    return obj, result

def controls_getter_function(obj:QMainWindow) -> QMainWindow:
    result = None
    # subtype defaults to disabled  
    try:
        obj.table_widget.sub_typer.disconnect()
    except TypeError:
        pass
    # correct start date being more recent than end date and rerun
    if obj.table_widget.datepicker.start_date.date() > obj.table_widget.datepicker.end_date.date():
        logger.warning("Start date after end date is not allowed!")
        threemonthsago = obj.table_widget.datepicker.end_date.date().addDays(-60)
        # block signal that will rerun controls getter and set start date
        with QSignalBlocker(obj.table_widget.datepicker.start_date) as blocker:
            obj.table_widget.datepicker.start_date.setDate(threemonthsago)
        obj._controls_getter()
        return obj, result
        # convert to python useable date object
    obj.start_date = obj.table_widget.datepicker.start_date.date().toPyDate()
    obj.end_date = obj.table_widget.datepicker.end_date.date().toPyDate()
    obj.con_type = obj.table_widget.control_typer.currentText()
    obj.mode = obj.table_widget.mode_typer.currentText()
    obj.table_widget.sub_typer.clear()
    # lookup subtypes
    sub_types = get_control_subtypes(ctx=obj.ctx, type=obj.con_type, mode=obj.mode)
    if sub_types != []:
        # block signal that will rerun controls getter and update sub_typer
        with QSignalBlocker(obj.table_widget.sub_typer) as blocker: 
            obj.table_widget.sub_typer.addItems(sub_types)
        obj.table_widget.sub_typer.setEnabled(True)
        obj.table_widget.sub_typer.currentTextChanged.connect(obj._chart_maker)
    else:
        obj.table_widget.sub_typer.clear()
        obj.table_widget.sub_typer.setEnabled(False)
    obj._chart_maker()
    return obj, result

def chart_maker_function(obj:QMainWindow) -> QMainWindow:
    result = None
    logger.debug(f"Control getter context: \n\tControl type: {obj.con_type}\n\tMode: {obj.mode}\n\tStart Date: {obj.start_date}\n\tEnd Date: {obj.end_date}")
    if obj.table_widget.sub_typer.currentText() == "":
        obj.subtype = None
    else:
        obj.subtype = obj.table_widget.sub_typer.currentText()
    logger.debug(f"Subtype: {obj.subtype}")
    # query all controls using the type/start and end dates from the gui
    controls = get_all_controls_by_type(ctx=obj.ctx, con_type=obj.con_type, start_date=obj.start_date, end_date=obj.end_date)
    # if no data found from query set fig to none for reporting in webview
    if controls == None:
        fig = None
    else:
        # change each control to list of dicts
        data = [control.convert_by_mode(mode=obj.mode) for control in controls]
        # flatten data to one dimensional list
        data = [item for sublist in data for item in sublist]
        logger.debug(f"Control objects going into df conversion: {data}")
        if data == []:
            return obj, dict(status="Critical", message="No data found for controls in given date range.")
        # send to dataframe creator
        df = convert_data_list_to_df(ctx=obj.ctx, input=data, subtype=obj.subtype)
        if obj.subtype == None:
            title = obj.mode
        else:
            title = f"{obj.mode} - {obj.subtype}"
        # send dataframe to chart maker
        fig = create_charts(ctx=obj.ctx, df=df, ytitle=title)
    logger.debug(f"Updating figure...")
    # construct html for webview
    html = construct_html(figure=fig)
    logger.debug(f"The length of html code is: {len(html)}")
    obj.table_widget.webengineview.setHtml(html)
    obj.table_widget.webengineview.update()
    logger.debug("Figure updated... I hope.")
    return obj, result

def link_controls_function(obj:QMainWindow) -> QMainWindow:
    result = None
    all_bcs = lookup_all_submissions_by_type(obj.ctx, "Bacterial Culture")
    logger.debug(all_bcs)
    all_controls = get_all_controls(obj.ctx)
    ac_list = [control.name for control in all_controls]
    count = 0
    for bcs in all_bcs:
        logger.debug(f"Running for {bcs.rsl_plate_num}")
        logger.debug(f"Here is the current control: {[control.name for control in bcs.controls]}")
        samples = [sample.sample_id for sample in bcs.samples]
        logger.debug(bcs.controls)
        for sample in samples:
            # replace below is a stopgap method because some dingus decided to add spaces in some of the ATCC49... so it looks like "ATCC 49"...
            if " " in sample:
                logger.warning(f"There is not supposed to be a space in the sample name!!!")
                sample = sample.replace(" ", "")
            # if sample not in ac_list:
            if not any([ac.startswith(sample) for ac in ac_list]):
                continue
            else:
                for control in all_controls:
                    diff = difflib.SequenceMatcher(a=sample, b=control.name).ratio()
                    if control.name.startswith(sample):
                        logger.debug(f"Checking {sample} against {control.name}... {diff}")
                        logger.debug(f"Found match:\n\tSample: {sample}\n\tControl: {control.name}\n\tDifference: {diff}")
                        if control in bcs.controls:
                            logger.debug(f"{control.name} already in {bcs.rsl_plate_num}, skipping")
                            continue
                        else:
                            logger.debug(f"Adding {control.name} to {bcs.rsl_plate_num} as control")
                            bcs.controls.append(control)
                            # bcs.control_id.append(control.id)
                            control.submission = bcs
                            control.submission_id = bcs.id
                            obj.ctx["database_session"].add(control)
                            count += 1
        obj.ctx["database_session"].add(bcs)
        logger.debug(f"Here is the new control: {[control.name for control in bcs.controls]}")
    result = dict(message=f"We added {count} controls to bacterial cultures.", status="information")
    logger.debug(result)
    obj.ctx['database_session'].commit()
    # msg = QMessageBox()
    # msg.setText("Controls added")
    # msg.setInformativeText(result)
    # msg.setWindowTitle("Controls added")
    # msg.exec()
    return obj, result

def link_extractions_function(obj:QMainWindow) -> QMainWindow:
    result = None
    # home_dir = str(Path(obj.ctx["directory_path"]))
    # fname = Path(QFileDialog.getOpenFileName(obj, 'Open file', home_dir, filter = "csv(*.csv)")[0])
    fname = select_open_file(obj, extension="csv")
    with open(fname.__str__(), 'r') as f:
        runs = [col.strip().split(",") for col in f.readlines()]
    count = 0
    for run in runs:
        new_run = dict(
                start_time=run[0].strip(), 
                rsl_plate_num=run[1].strip(), 
                sample_count=run[2].strip(), 
                status=run[3].strip(),
                experiment_name=run[4].strip(),
                end_time=run[5].strip()
            )
        for ii in range(6, len(run)):
            new_run[f"column{str(ii-5)}_vol"] = run[ii]
        sub = lookup_submission_by_rsl_num(ctx=obj.ctx, rsl_num=new_run['rsl_plate_num'])
        try:
            logger.debug(f"Found submission: {sub.rsl_plate_num}")
            count += 1
        except AttributeError:
            continue
        if sub.extraction_info != None:
            existing = json.loads(sub.extraction_info)
        else:
            existing = None
        try:
            if json.dumps(new_run) in sub.extraction_info:
                logger.debug(f"Looks like we already have that info.")
                continue
        except TypeError:
            pass
        if existing != None:
            try:
                logger.debug(f"Updating {type(existing)}: {existing} with {type(new_run)}: {new_run}")
                existing.append(new_run)
                logger.debug(f"Setting: {existing}")
                sub.extraction_info = json.dumps(existing)
            except TypeError:
                logger.error(f"Error updating!")
                sub.extraction_info = json.dumps([new_run])
            logger.debug(f"Final ext info for {sub.rsl_plate_num}: {sub.extraction_info}")
        else:
            sub.extraction_info = json.dumps([new_run])        
        obj.ctx['database_session'].add(sub)
        obj.ctx["database_session"].commit()
    result = dict(message=f"We added {count} logs to the database.", status='information') 
    return obj, result

def link_pcr_function(obj:QMainWindow) -> QMainWindow:
    result = None
    # home_dir = str(Path(obj.ctx["directory_path"]))
    # fname = Path(QFileDialog.getOpenFileName(obj, 'Open file', home_dir, filter = "csv(*.csv)")[0])
    fname = select_open_file(obj, extension="csv")
    with open(fname.__str__(), 'r') as f:
        runs = [col.strip().split(",") for col in f.readlines()]
    count = 0
    for run in runs:
        new_run = dict(
                start_time=run[0].strip(), 
                rsl_plate_num=run[1].strip(), 
                biomek_status=run[2].strip(), 
                quant_status=run[3].strip(),
                experiment_name=run[4].strip(),
                end_time=run[5].strip()
            )
        # for ii in range(6, len(run)):
        #     obj[f"column{str(ii-5)}_vol"] = run[ii]
        sub = lookup_submission_by_rsl_num(ctx=obj.ctx, rsl_num=new_run['rsl_plate_num'])
        try:
            logger.debug(f"Found submission: {sub.rsl_plate_num}")
        except AttributeError:
            continue
        if hasattr(sub, 'pcr_info') and sub.pcr_info != None:
            existing = json.loads(sub.pcr_info)
        else:
            existing = None
        try:
            if json.dumps(new_run) in sub.pcr_info:
                logger.debug(f"Looks like we already have that info.")
                continue
            else:
                count += 1
        except TypeError:
            logger.error(f"No json to dump")
        if existing != None:
            try:
                logger.debug(f"Updating {type(existing)}: {existing} with {type(new_run)}: {new_run}")
                existing.append(new_run)
                logger.debug(f"Setting: {existing}")
                sub.pcr_info = json.dumps(existing)
            except TypeError:
                logger.error(f"Error updating!")
                sub.pcr_info = json.dumps([new_run])
            logger.debug(f"Final ext info for {sub.rsl_plate_num}: {sub.pcr_info}")
        else:
            sub.pcr_info = json.dumps([new_run])        
        obj.ctx['database_session'].add(sub)
        obj.ctx["database_session"].commit()
    result = dict(message=f"We added {count} logs to the database.", status='information')
    return obj, result

def import_pcr_results_function(obj:QMainWindow) -> QMainWindow:
    result = None
    # home_dir = str(Path(obj.ctx["directory_path"]))
    # fname = Path(QFileDialog.getOpenFileName(obj, 'Open file', home_dir, filter = "xlsx(*.xlsx)")[0])
    fname = select_open_file(obj, extension="xlsx")
    parser = PCRParser(ctx=obj.ctx, filepath=fname)
    logger.debug(f"Attempting lookup for {parser.plate_num}")
    sub = lookup_submission_by_rsl_num(ctx=obj.ctx, rsl_num=parser.plate_num)
    try:
        logger.debug(f"Found submission: {sub.rsl_plate_num}")
    except AttributeError:
        logger.error(f"Submission of number {parser.plate_num} not found. Attempting rescue of plate repeat.")
        parser.plate_num = "-".join(parser.plate_num.split("-")[:-1])
        sub = lookup_submission_by_rsl_num(ctx=obj.ctx, rsl_num=parser.plate_num)
        try:
            logger.debug(f"Found submission: {sub.rsl_plate_num}")
        except AttributeError:
            logger.error(f"Rescue of {parser.plate_num} failed.")
            return obj, dict(message="Couldn't find a submission with that RSL number.", status="warning")
    # jout = json.dumps(parser.pcr)
    count = 0
    if hasattr(sub, 'pcr_info') and sub.pcr_info != None:
        existing = json.loads(sub.pcr_info)
    else:
        # jout = None
        existing = None
    if existing != None:
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
    obj.ctx['database_session'].add(sub)
    logger.debug(f"Existing {type(sub.pcr_info)}: {sub.pcr_info}")
    logger.debug(f"Inserting {type(json.dumps(parser.pcr))}: {json.dumps(parser.pcr)}")
    obj.ctx["database_session"].commit()
    logger.debug(f"Got {len(parser.samples)} to update!")
    for sample in parser.samples:
        logger.debug(f"Running update on: {sample['sample']}")
        sample['plate_rsl'] = sub.rsl_plate_num
        update_ww_sample(ctx=obj.ctx, sample_obj=sample)
    result = dict(message=f"We added PCR info to {sub.rsl_plate_num}.", status='information')
    return obj, result
    # dlg.exec()    









