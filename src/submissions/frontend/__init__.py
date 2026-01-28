"""
Constructs main application.
"""
from .widgets import (
    pandasModel,
    App,
    Concentrations,
    ControlsViewer,
    DateTypePicker,
    EquipmentUsage, RoleComboBox,
    select_open_file, select_save_file, save_pdf,
    GelBox, ControlsForm,
    InfoPane,
    StartEndDatePicker, CheckableComboBox, Pagifier,
    SearchBox, SearchResults, FieldSearch,
    QuestionAsker, AlertPop, HTMLPop, ObjectSelector,
    ProcedureCreation,
    SampleChecker,
    SubmissionDetails, SubmissionComment,
    SubmissionsTree, ClientSubmissionRunModel,
    MyQComboBox, MyQDateEdit, SubmissionFormContainer, SubmissionFormWidget, ClientSubmissionFormWidget,
    Summary,
    TurnaroundMaker
)
from .visualizations import (
    CustomFigure,
    IridaFigure,
    PCRFigure,
    ConcentrationsChart,
    TurnaroundChart
)
