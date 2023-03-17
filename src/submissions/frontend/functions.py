from backend.db.models import *
import logging
from PyQt6.QtWidgets import (
    QMainWindow, QLabel, QToolBar, 
    QTabWidget, QWidget, QVBoxLayout,
    QPushButton, QFileDialog,
    QLineEdit, QMessageBox, QComboBox, QDateEdit, QHBoxLayout,
    QSpinBox, QScrollArea
)


logger = logging.getLogger(f"submissions.{__name__}")

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
        logger.debug(f"Looking at: {item.objectName()}")
        match item:
            case QLineEdit():
                dicto[item.objectName()] = item.text()
            case QComboBox():
                dicto[item.objectName()] = item.currentText()
            case QDateEdit():
                dicto[item.objectName()] = item.date().toPyDate()
            case QSpinBox():
                dicto[item.objectName()] = item.value()
            case ReagentTypeForm():
                reagent = extract_form_info(item) 
                # reagent = {item[0]:item[1] for item in zip(re_labels, re_values)}
                logger.debug(reagent)
                # reagent = {reagent['name:']:{'eol':reagent['extension_of_life_(months):']}}
                reagents[reagent["name"].strip()] = {'eol_ext':int(reagent['eol'])}
        # value for ad hoc check above
    if reagents != {}:
        return dicto, reagents
    return dicto