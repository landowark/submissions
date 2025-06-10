"""
functions used by all windows in the application's frontend
"""
from pathlib import Path
import logging
from PyQt6.QtCore import QMarginsF
from PyQt6.QtGui import QPageLayout, QPageSize
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QMainWindow, QFileDialog

logger = logging.getLogger(f"submissions.{__name__}")


def select_open_file(obj: QMainWindow, file_extension: str | None = None) -> Path:
    """
    File dialog to select a file to read from

    Args:
        obj (QMainWindow): Original main app window to be parent
        file_extension (str): file extension

    Returns:
        Path: Path of file to be opened
    """
    try:
        home_dir = obj.last_dir.resolve().__str__()
    except FileNotFoundError:
        home_dir = Path.home().resolve().__str__()
    except AttributeError:
        home_dir = obj.app.last_dir.resolve().__str__()
    if file_extension is None:
        fname = Path(QFileDialog.getExistingDirectory(obj, "Open Folder", home_dir))
    else:
        fname = Path(
            QFileDialog.getOpenFileName(obj, 'Open file', home_dir, filter=f"{file_extension}(*.{file_extension})")[0])
        if not fname.exists():
            raise FileNotFoundError(f"File {fname.__str__()} could not be found.")
        if fname.__str__() == ".":
            logger.warning(f"No file selected, cancelling.")
            return
    obj.last_dir = fname.parent
    logger.debug(f"File selected: {fname}")
    return fname


def select_save_file(obj: QMainWindow, default_name: str, extension: str) -> Path:
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
        home_dir = obj.last_dir.joinpath(default_name).resolve().__str__()
    except FileNotFoundError:
        home_dir = Path.home().joinpath(default_name).resolve().__str__()
    except AttributeError:
        home_dir = obj.app.last_dir.joinpath(default_name).resolve().__str__()
    fname = Path(QFileDialog.getSaveFileName(obj, "Save File", home_dir, filter=f"{extension}(*.{extension})")[0])
    obj.last_dir = fname.parent
    return fname


def save_pdf(obj: QWebEngineView, filename: Path):
    """
    Handles printing to PDF

    Args:
        obj (): Parent object
        filename (): Where to save pdf.

    Returns:
        None
    """
    page_layout = QPageLayout()
    page_layout.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    page_layout.setOrientation(QPageLayout.Orientation.Portrait)
    page_layout.setMargins(QMarginsF(25, 25, 25, 25))
    obj.page().printToPdf(filename.absolute().__str__(), page_layout)
