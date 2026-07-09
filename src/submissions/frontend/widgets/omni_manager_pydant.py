
from PyQt6.QtWidgets import QWidget, QDialog, QVBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from backend.db.models import BaseClass
from . import CustomWebEnginePage
from PyQt6.QtCore import pyqtSlot, QVariant
from tools import render_details_template
from operator import itemgetter


class OmniManager(QDialog):
    """
    Provides a screen for managing all attributes of a database object.
    """
    def __init__(self, parent: QWidget, object_type: type):
        super().__init__(parent)
        self.object_type = object_type
        logger.debug(f"Objecttype: {self.object_type}")
        
        self.pydant = None
        self.webview = QWebEngineView()
        custom_page = CustomWebEnginePage(self.webview)
        self.webview.setPage(custom_page)
        self.layout = QVBoxLayout()
        self.setMinimumWidth(1000)
        self.setLayout(self.layout)
        self.sql_type = BaseClass.find_subclasses(class_name=self.object_type.__name__.replace('Pyd', ''))
        self.setWindowTitle(f"Manage {self.sql_type.__name__}")
        self.layout.addWidget(self.webview)
        self.reset_form()
        self.channel = QWebChannel()
        self.channel.registerObject('backend', self)
        self.webview.page().setWebChannel(self.channel)
        
    def reset_form(self) -> None:
        """
        Resets the form to initial state.

        Returns:
            None
        """
        # addendum = ["", "--New--"]
        object_list = [dict(name="", active=True)] + sorted([dict(name=item.name, active=item.is_active) for item in self.sql_type.query() 
                                                             if item.name != "Default SubmissionType"], key=itemgetter("active"), reverse=True)
        object_name = self.sql_type.__name__
        html = render_details_template("managers/default_manager", js_in=['manager'], object_name=object_name, object_list=object_list)
        self.webview.setHtml(html)
        
    @pyqtSlot(str, result=str)
    def update_selection(self, selection: str) -> None:
        """
        Updates the current selection in the manager.

        Args:
            selection (str): The name of the selected object.

        Returns:
            None
        """
        if selection == "--New--":
            self.pydant = self.object_type()
            self.pydant.new = True
        else:
            try:
                sql_instance = self.object_type._sql_class.query(name=selection, limit=1)
            except AttributeError as e:
                logger.error(f"Couldn't get _sql_object for type {self.object_type}")
            if not sql_instance:
                logger.error(f"Could not find instance with name: {selection}")
                return
            self.pydant = sql_instance.to_pydantic()
            self.pydant.new = False
        html = self.pydant.html_form
        return html
    
    @pyqtSlot(str, str)
    def update_instrumentedattribute(self, field: str, value: str) -> None:
        """
        Updates an InstrumentedAttribute field in the pydantic object.

        Args:
            field (str): The field name to update.
            value (str): The new value for the field.
        """
        logger.debug(f"Updating {field} to {value}")
        self.pydant.update_instrumentedattribute(field, value)
        logger.debug(f"New value for {field}: {getattr(self.pydant, field)}")
        
    @pyqtSlot(str, str, result=str)
    def get_association_form(self, field: str, value: str) -> str:
        """
        Generates an HTML form for association attributes.

        Args:
            field (str): The relationship field name.
            value (str): The selected value for the relationship.
        """
        blank_class = self.pydant.get_association_class(field)
        return blank_class().html_form

    @pyqtSlot(str, str, QVariant)
    def add_relationship(self, field: str, value: str, data: dict | None) -> None:
        """
        Adds a relationship to the pydantic object.

        Args:
            field (str): The relationship field name.
            value (str): The value to add to the relationship.
        """
        self.pydant.add_relationship(field, value, data)
        
    @pyqtSlot(str, str)
    def remove_relationship(self, field: str, value: str) -> None:
        """
        Removes a relationship from the pydantic object.

        Args:
            field (str): The relationship field name.
            value (str): The value to remove from the relationship.
        """
        self.pydant.remove_relationship(field, value)

    @pyqtSlot()
    def submit(self) -> None:
        """
        Submits the current pydantic object to the database.

        Returns:
            None
        """
        logger.debug(f"Pydant object coming in: {pformat(self.pydant.improved_dict)}")
        sql_instance = self.pydant.to_sql()
        if isinstance(sql_instance, tuple):
            sql_instance = sql_instance[0]
        logger.debug(pformat({k:v for k, v in sql_instance.__dict__.items() if not isinstance(v, list) and not isinstance(v, dict)}))
        sql_instance.save()
        self.reset_form()

    @pyqtSlot()
    def save_html(self) -> None:
        """
        Saves the current HTML to a file.

        Args:
            path (str): Path to save the HTML file.

        Returns:
            None
        """
        self.webview.page().toHtml(self.write_html)

    def write_html(self, html: str) -> None:
        """
        Writes HTML to a file.

        Args:
            html (str): HTML content to write.

        Returns:
            None
        """
        ...


__all__ = ["OmniManager"]