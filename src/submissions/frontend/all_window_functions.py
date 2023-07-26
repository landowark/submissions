'''
functions used by all windows in the application's frontend
'''
from pathlib import Path
import logging
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QFileDialog,
    QLineEdit, QComboBox, QDateEdit, QSpinBox, 
    QDoubleSpinBox
)

logger = logging.getLogger(f"submissions.{__name__}")

def select_open_file(obj:QMainWindow, file_extension:str) -> Path:
    """
    File dialog to select a file to read from

    Args:
        obj (QMainWindow): Original main app window to be parent
        file_extension (str): file extension

    Returns:
        Path: Path of file to be opened
    """    
    # home_dir = str(Path(obj.ctx["directory_path"]))
    home_dir = str(Path(obj.ctx.directory_path))
    fname = Path(QFileDialog.getOpenFileName(obj, 'Open file', home_dir, filter = f"{file_extension}(*.{file_extension})")[0])
    return fname

def select_save_file(obj:QMainWindow, default_name:str, extension:str) -> Path:
    """
    File dialog to select a file to write to

    Args:
        obj (QMainWindow): Original main app window to be parent
        default_name (str): default base file name
        extension (str): file extension

    Returns:
        Path: Path of file to be opened
    """    
    try:
        # home_dir = Path(obj.ctx["directory_path"]).joinpath(default_name).resolve().__str__()
        home_dir = Path(obj.ctx.directory_path).joinpath(default_name).resolve().__str__()
    except FileNotFoundError:
        home_dir = Path.home().resolve().__str__()
    fname = Path(QFileDialog.getSaveFileName(obj, "Save File", home_dir, filter = f"{extension}(*.{extension})")[0])
    return fname

def extract_form_info(object) -> dict:
    """
    retrieves object names and values from form

    Args:
        object (_type_): the form widget

    Returns:
        dict: dictionary of objectName:text items
    """        
    
    from frontend.custom_widgets import ReagentTypeForm
    dicto = {}
    reagents = {}
    logger.debug(f"Object type: {type(object)}")
    # grab all widgets in form
    try:
        all_children = object.layout.parentWidget().findChildren(QWidget)
    except AttributeError:
        all_children = object.layout().parentWidget().findChildren(QWidget)
    for item in all_children:
        logger.debug(f"Looking at: {item.objectName()}: {type(item)}")
        match item:
            case QLineEdit():
                dicto[item.objectName()] = item.text()
            case QComboBox():
                dicto[item.objectName()] = item.currentText()
            case QDateEdit():
                dicto[item.objectName()] = item.date().toPyDate()
            case QSpinBox() | QDoubleSpinBox():
                dicto[item.objectName()] = item.value()
            case ReagentTypeForm():
                reagent = extract_form_info(item) 
                logger.debug(f"Reagent found: {reagent}")
                reagents[reagent["name"].strip()] = {'eol_ext':int(reagent['eol'])}
        # value for ad hoc check above
    if reagents != {}:
        return dicto, reagents
    return dicto
