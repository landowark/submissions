"""
Contains widgets specific to the procedure summary and procedure details.
"""
from datetime import date
import sys, logging, asyncio
from operator import itemgetter
from pprint import pformat
from PyQt6.QtWidgets import QMenu, QTreeView, QAbstractItemView
from PyQt6.QtCore import QModelIndex, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QCursor, QStandardItemModel, QStandardItem, QContextMenuEvent
from typing import List, Dict, Any
from tools import datetime, get_application_from_parent

logger = logging.getLogger(f"submissions.{__name__}")


class SubmissionsTree(QTreeView):
    """
    https://stackoverflow.com/questions/54385437/how-can-i-make-a-table-that-can-collapse-its-rows-into-categories-in-qt
    """

    clientsubmissionExpanded = pyqtSignal(QModelIndex)
    runExpanded = pyqtSignal(QModelIndex)

    def __init__(self, model, parent=None):
        super(SubmissionsTree, self).__init__(parent)
        from backend.db.models import ClientSubmission
        self.app = get_application_from_parent(parent)
        self.total_count = ClientSubmission.__database_session__.query(ClientSubmission).count()
        self.setExpandsOnDoubleClick(False)
        self.model: ClientSubmissionRunModel = model
        # header_labels = ["Name", "Submission Type", "Client Lab", "Submitted Date"]
        # self.model.setHorizontalHeaderLabels(header_labels)
        self.setModel(self.model)
        self.setSelectionBehavior(QAbstractItemView.selectionBehavior(self).SelectRows)
        self.set_data()
        self.doubleClicked.connect(self.show_details)
        # self.setStyleSheet("""
        #     QTreeView {
        #         background-color: #f5f5f5;
        #         alternate-background-color: "#cfe2f3";
        #         border: 1px solid #d3d3d3;
        #     }
        #     QTreeView::item {
        #         padding: 5px;
        #         border-bottom: 1px solid #d3d3d3;
        #     }
        #     QTreeView::item:selected {
        #         background-color: #0078d7;
        #         color: white;
        #     }
        # """)

        # NOTE: Enable alternating row colors
        self.setAlternatingRowColors(True)
        self.setIndentation(20)
        self.setItemsExpandable(True)
        self.setSortingEnabled(True)
        # for ii, _ in enumerate(header_labels):
        #     self.resizeColumnToContents(ii)
        self.sortByColumn(3, Qt.SortOrder.DescendingOrder)
        self.expanded.connect(self._route_expansion)

    def _route_expansion(self, index: QModelIndex):
        item_type = index.data(1).get("item_type")
        print(f"Class: {item_type.__name__} at row {index.row()} with parent {index.parent().data()}")
        match item_type.__name__:
            case "ClientSubmission":
                self.clientsubmissionExpanded.emit(index)
            case "Run":
                self.runExpanded.emit(index)
            case _:
                logger.warning(f"Unknown item type expanded: {item_type.__name__}")

    def contextMenuEvent(self, event: QContextMenuEvent):
        """
        Creates actions for right click menu events.

        Args:
            event (_type_): the item of interest
        """
        indexes = self.selectedIndexes()
        dicto = next((item.data(1) for item in indexes if item.data(1)))
        query_obj = dicto['item_type'].query(name=dicto['query_str'], limit=1)
        # NOTE: Convert to data in id column (i.e. column 0)
        self.menu = QMenu(self)
        self.con_actions = query_obj.custom_context_events
        for key in self.con_actions.keys():
            match key.lower():
                case "add procedure":
                    action = QMenu(self.menu)
                    action.setTitle("Add Procedure")
                    for procedure in query_obj.allowed_procedures:
                        proc_name = procedure.name
                        proc = QAction(proc_name, action)
                        proc.triggered.connect(lambda _, procedure_name=proc_name: self.con_actions['Add Procedure'](obj=self, proceduretype_name=procedure_name))
                        action.addAction(proc)
                        self.menu.addMenu(action)
                case "add results":
                    action = QMenu(self.menu)
                    action.setTitle("Add Results")
                    for results in query_obj.proceduretype.allowed_result_methods:
                        res_name = results.get('name', None)
                        if res_name:
                            res = QAction(res_name, action)
                            res.triggered.connect(lambda _, procedure_name=res_name: self.con_actions['Add Results'](obj=self, resultstype_name=procedure_name))
                            action.addAction(res)
                            self.menu.addMenu(action)
                case _:
                    action = QAction(key, self)
                    action.triggered.connect(lambda _, action_name=key: self.con_actions[action_name](obj=self))
                    self.menu.addAction(action)
        # NOTE: add other required actions
        self.menu.popup(QCursor.pos())

    def set_data(self, page: int = 1, page_size: int = 250) -> None:
        """
        sets data in model
        """
        from backend.db.models import Run, ClientSubmission, Procedure
        self.clear()
        subs = [item.to_pydantic().improved_dict
                for item in ClientSubmission.query(chronologic=True, page=page, page_size=page_size)]
        self.data = sorted(subs, key=itemgetter('submitted_date'), reverse=True)
        root = self.model.invisibleRootItem()
        for submission in self.data:
            group_str = f"{submission['submissiontype']}-{submission['submitter_plate_id']}-{submission['submitted_date']}"
            submission_item: QStandardItem = self.model.add_child(parent=root, child=dict(
                name=group_str,
                client=submission['clientlab'],
                date=submission['submitted_date'],
                type=submission['submissiontype'],
                query_str=submission['submitter_plate_id'],
                item_type=ClientSubmission
            ), additions=True)
            asyncio.run(self._process_runs_async(submission['run'], submission_item, Run, Procedure))

    async def _process_runs_async(self, runs: List[Dict[str, Any]], submission_item: QStandardItem, run_type: type, procedure_type: type) -> None:
        """
        Asynchronously process all runs for a submission.
        
        Args:
            runs: List of run dictionaries
            submission_item: The parent QStandardItem for the submission
            run_type: The type of run to process
            procedure_type: The type of procedure to process
        """
        for run in runs:
            run_item = self.model.add_child(parent=submission_item, child=dict(
                name=run['plate_number'],
                query_str=run['plate_number'],
                item_type=run_type
            ))
            await self._process_procedures_async(run['procedure'], run_item, procedure_type)
            await asyncio.sleep(0)  # Allow other tasks to run

    async def _process_procedures_async(self, procedures: List[Any], run_item: QStandardItem, procedure_type: type) -> None:
        """
        Asynchronously process all procedures for a run.
        
        Args:
            procedures: List of procedure dictionaries or names
            run_item: The parent QStandardItem for the run
            procedure_type: The type of procedure to process
        """
        for procedure in procedures:
            procedure_item = self.model.add_child(parent=run_item, child=dict(
                name=procedure['name'] if isinstance(procedure, dict) else procedure,
                query_str=procedure['name'] if isinstance(procedure, dict) else procedure,
                item_type=procedure_type
            ))
            await asyncio.sleep(0)  # Allow other tasks to run


    def _populateTree(self, children, parent):
        for child in children:
            child_item = QStandardItem(child['name'])
            parent.appendRow(child_item)
            if isinstance(children, List):
                self._populateTree(child, child_item)

    def clear(self):
        if self.model != None:
            self.model.setRowCount(0)  # works
            # pass

    def show_details(self, sel: QModelIndex):
        # NOTE: Convert to data in id column (i.e. column 0)
        indexes = self.selectedIndexes()
        dicto = next((item.data(1) for item in indexes if item.data(1)))
        obj = dicto['item_type'].query(name=dicto['query_str'], limit=1)
        obj.show_details(self)


from datetime import date, datetime
from PyQt6.QtCore import Qt, QAbstractItemModel, QModelIndex

class TreeItem:
    def __init__(self, data: dict = None, parent=None):
        self.parent_item = parent
        self.child_items = []
        
        self.data_dict = data or {}
        self.name = self.data_dict.get('name', 'Unknown')
        self.item_type = self.data_dict.get('item_type')
        self.query_str = self.data_dict.get('query_str')
        self.client = self.data_dict.get('client', '')
        self.type_str = self.data_dict.get('type', '')
        
        dt = self.data_dict.get('date', '')
        if isinstance(dt, (date, datetime)):
            self.date_str = dt.strftime("%Y-%m-%d")
        else:
            self.date_str = str(dt)

        # Lazy loading properties
        self.is_loaded = False
        # Procedures are leaf nodes (no children). Submissions & Runs have children.
        from backend.db.models import Procedure
        self.has_children_placeholder = (self.item_type != Procedure)


class ClientSubmissionRunModel(QAbstractItemModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.root_item = TreeItem()
        self.headers = ["Name", "Submission Type", "Client Lab", "Submitted Date"]

    def hasChildren(self, parent=QModelIndex()):
        if not parent.isValid():
            return True
        return parent.internalPointer().has_children_placeholder

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def rowCount(self, parent=QModelIndex()):
        if parent.column() > 0:
            return 0
        parent_item = parent.internalPointer() if parent.isValid() else self.root_item
        return len(parent_item.child_items)

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        parent_item = parent.internalPointer() if parent.isValid() else self.root_item
        child_item = parent_item.child_items[row]
        return self.createIndex(row, column, child_item)

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        child_item = index.internalPointer()
        parent_item = child_item.parent_item
        if parent_item == self.root_item:
            return QModelIndex()
        grandparent = parent_item.parent_item
        row = grandparent.child_items.index(parent_item)
        return self.createIndex(row, 0, parent_item)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = index.internalPointer()
        
        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 0: return item.name
            elif index.column() == 1: return item.type_str
            elif index.column() == 2: return item.client
            elif index.column() == 3: return item.date_str

        # Replaces your original item.setData(..., 1) metadata lookups
        if role == Qt.ItemDataRole.UserRole:
            return {
                'item_type': item.item_type,
                'query_str': item.query_str
            }
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.headers[section]
        return None

    def clear(self):
        self.beginResetModel()
        self.root_item.child_items = []
        self.endResetModel()

    def add_top_level_submissions(self, submissions_list: list):
        """Populates root level submissions efficiently."""
        from backend.db.models import ClientSubmission
        self.beginInsertRows(QModelIndex(), 0, len(submissions_list) - 1)
        for sub in submissions_list:
            group_str = f"{sub['submissiontype']}-{sub['submitter_plate_id']}-{sub['submitted_date']}"
            child_dict = dict(
                name=group_str,
                client=sub['clientlab'],
                date=sub['submitted_date'],
                type=sub['submissiontype'],
                query_str=sub['submitter_plate_id'],
                item_type=ClientSubmission,
                raw_run_data=sub.get('run', []) # Store temporarily for lazy step
            )
            self.root_item.child_items.append(TreeItem(child_dict, self.root_item))
        self.endResetModel()



# class ClientSubmissionRunModel(QStandardItemModel):

#     def __init__(self, parent):
#         super().__init__(parent)

#     def add_child(self, parent: QStandardItem, child:dict, additions:bool=False) -> QStandardItem:
#         # logger.debug(f"Adding child with data: {pformat(child['name'])}")
#         try:
#             item = QStandardItem(child['name'])
#         except Exception as e:
#             logger.error(f"Error creating QStandardItem:{child['name']}")
#             # raise e
#             item = QStandardItem("Unknown")
#         item.setData(dict(item_type=child['item_type'], query_str=child['query_str']), 1)
#         if additions:
#             item_client = QStandardItem(child['client'])
#             if isinstance(child['date'], str):
#                 item_date = QStandardItem(child['date'])
#             elif isinstance(child['date'], (date, datetime)):
#                 item_date = QStandardItem(child['date'].strftime("%Y-%m-%d"))
#             item_type = QStandardItem(child['type'])
#             parent.appendRow([item, item_type, item_client, item_date])
#         else:
#             parent.appendRow([item])
#         item.setEditable(False)
#         return item

#     def edit_item(self):
#         pass
