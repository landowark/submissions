import numpy as np
import logging
import getpass
from PyQt6.QtWidgets import (
    QMainWindow, QLabel, QToolBar, 
    QTabWidget, QWidget, QVBoxLayout,
    QPushButton, QFileDialog,
    QLineEdit, QMessageBox, QComboBox, QDateEdit, QHBoxLayout,
    QSpinBox, QScrollArea
)


logger = logging.getLogger(f"submissions.{__name__}")

def check_not_nan(cell_contents) -> bool:
    try:
        return not np.isnan(cell_contents)
    except TypeError:
        return True
    except Exception as e:
        logger.debug(f"Check encounteded unknown error: {type(e).__name__} - {e}")
        return False


def check_is_power_user(ctx:dict) -> bool:
    try:
        check = getpass.getuser() in ctx['power_users']
    except KeyError as e:
        check = False
    except Exception as e:
        logger.debug(f"Check encounteded unknown error: {type(e).__name__} - {e}")
        check = False
    return check


def create_reagent_list(in_dict:dict) -> list[str]:
    return [item.strip("lot_") for item in in_dict.keys()]


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