"""
Contains widgets specific to the procedure summary and procedure details.
"""

import sys, logging, re
from pprint import pformat

from PyQt6.QtWidgets import QTableView, QMenu, QTreeView, QStyledItemDelegate, QStyle, QStyleOptionViewItem, \
    QHeaderView, QAbstractItemView, QWidget, QTreeWidgetItemIterator
from PyQt6.QtCore import Qt, QAbstractTableModel, QSortFilterProxyModel, pyqtSlot, QModelIndex
from PyQt6.QtGui import QAction, QCursor, QStandardItemModel, QStandardItem, QIcon, QColor, QContextMenuEvent
from typing import Dict, List

from backend import Procedure
from backend.db.models import Run, ClientSubmission
from tools import Report, Result, report_result
from .functions import select_open_file

logger = logging.getLogger(f"procedure.{__name__}")


class pandasModel(QAbstractTableModel):
    """
    pandas model for inserting summary sheet into gui
    NOTE: Copied from Stack Overflow. I have no idea how it actually works.
    """

    def __init__(self, data) -> None:
        QAbstractTableModel.__init__(self)
        self._data = data

    def rowCount(self, parent=None) -> int:
        """
        does what it says

        Args:
            parent (_type_, optional): _description_. Defaults to None.

        Returns:
            int: number of rows in data
        """
        return self._data.shape[0]

    def columnCount(self, parent=None) -> int:
        """
        does what it says

        Args:
            parent (_type_, optional): _description_. Defaults to None.

        Returns:
            int: number of columns in data
        """
        return self._data.shape[1]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole) -> str | None:
        if index.isValid():
            if role == Qt.ItemDataRole.DisplayRole:
                return str(self._data.iloc[index.row(), index.column()])
        return None

    def headerData(self, col, orientation, role):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self._data.columns[col]
        return None


class SubmissionsSheet(QTableView):
    """
    presents procedure summary to user in tab1
    """

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.app = self.parent()
        self.report = Report()
        try:
            page_size = self.app.page_size
        except AttributeError:
            page_size = 250
        self.set_data(page=1, page_size=page_size)
        self.resizeColumnsToContents()
        self.resizeRowsToContents()
        self.setSortingEnabled(True)
        self.doubleClicked.connect(lambda x: Run.query(id=x.sibling(x.row(), 0).data()).show_details(self))
        # NOTE: Have to procedure native query here because mine just returns results?
        self.total_count = Run.__database_session__.query(Run).count()

    def set_data(self, page: int = 1, page_size: int = 250) -> None:
        """
        sets data in model
        """
        # self.data = ClientSubmission.submissions_to_df(page=page, page_size=page_size)
        self.data = Run.submissions_to_df(page=page, page_size=page_size)
        try:
            self.data['Id'] = self.data['Id'].apply(str)
            self.data['Id'] = self.data['Id'].str.zfill(4)
        except KeyError as e:
            logger.error(f"Could not alter id to string due to {e}")
        proxyModel = QSortFilterProxyModel()
        proxyModel.setSourceModel(pandasModel(self.data))
        self.setModel(proxyModel)

    def contextMenuEvent(self, event):
        """
        Creates actions for right click menu events.

        Args:
            event (_type_): the item of interest
        """
        # NOTE: Get current row index
        id = self.selectionModel().currentIndex()
        # NOTE: Convert to data in id column (i.e. column 0)
        id = id.sibling(id.row(), 0).data()
        submission = Run.query(id=id)
        self.menu = QMenu(self)
        self.con_actions = submission.custom_context_events()
        for k in self.con_actions.keys():
            action = QAction(k, self)
            action.triggered.connect(lambda _, action_name=k: self.triggered_action(action_name=action_name))
            self.menu.addAction(action)
        # NOTE: add other required actions
        self.menu.popup(QCursor.pos())

    def triggered_action(self, action_name: str):
        """
        Calls the triggered action from the context menu

        Args:
            action_name (str): name of the action from the menu
        """
        func = self.con_actions[action_name]
        func(obj=self)

    @report_result
    def link_extractions(self):
        """
        Pull extraction logs into the db
        """
        report = Report()
        result = self.link_extractions_function()
        report.add_result(result)
        return report

    def link_extractions_function(self):
        """
        Link extractions from runlogs to imported procedure

        Args:
            obj (QMainWindow): original app window

        Returns:
            Tuple[QMainWindow, dict]: Collection of new main app window and result dict
        """
        report = Report()
        fname = select_open_file(self, file_extension="csv")
        with open(fname.__str__(), 'r') as f:
            # NOTE: split csv on commas
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
            # NOTE: elution columns are item 6 in the comma split list to the end
            for ii in range(6, len(run)):
                new_run[f"column{str(ii - 5)}_vol"] = run[ii]
            # NOTE: Lookup imported procedure
            sub = Run.query(name=new_run['name'])
            # NOTE: If no such procedure exists, move onto the next procedure
            if sub is None:
                continue
            try:
                count += 1
            except AttributeError:
                continue
            sub.set_attribute('extraction_info', new_run)
            sub.save()
        report.add_result(Result(msg=f"We added {count} logs to the database.", status='Information'))
        return report

    @report_result
    def link_pcr(self):
        """
        Pull pcr logs into the db
        """
        report = Report()
        result = self.link_pcr_function()
        report.add_result(result)
        return report

    def link_pcr_function(self):
        """
        Link PCR data from procedure logs to an imported procedure

        Args:
            obj (QMainWindow): original app window

        Returns:
            Tuple[QMainWindow, dict]: Collection of new main app window and result dict
        """
        report = Report()
        fname = select_open_file(self, file_extension="csv")
        with open(fname.__str__(), 'r') as f:
            # NOTE: split csv rows on comma
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
            # NOTE: lookup imported procedure
            sub = Run.query(rsl_number=new_run['name'])
            # NOTE: if imported procedure doesn't exist move on to next procedure
            if sub is None:
                continue
            sub.set_attribute('pcr_info', new_run)
            # NOTE: check if pcr_info already exists
            sub.save()
        report.add_result(Result(msg=f"We added {count} logs to the database.", status='Information'))
        return report


class ClientSubmissionDelegate(QStyledItemDelegate):

    def __init__(self, parent=None):
        super(ClientSubmissionDelegate, self).__init__(parent)
        pixmapi = QStyle.StandardPixmap.SP_ToolBarHorizontalExtensionButton
        icon1 = QWidget().style().standardIcon(pixmapi)
        pixmapi = QStyle.StandardPixmap.SP_ToolBarVerticalExtensionButton
        icon2 = QWidget().style().standardIcon(pixmapi)
        self._plus_icon = icon1
        self._minus_icon = icon2

    def initStyleOption(self, option, index):
        super(ClientSubmissionDelegate, self).initStyleOption(option, index)
        if not index.parent().isValid():
            is_open = bool(option.state & QStyle.StateFlag.State_Open)
            option.features |= QStyleOptionViewItem.ViewItemFeature.HasDecoration
            option.icon = self._minus_icon if is_open else self._plus_icon


class RunDelegate(ClientSubmissionDelegate):
    pass


class SubmissionsTree(QTreeView):
    """
    https://stackoverflow.com/questions/54385437/how-can-i-make-a-table-that-can-collapse-its-rows-into-categories-in-qt
    """

    def __init__(self, model, parent=None):
        super(SubmissionsTree, self).__init__(parent)
        self.total_count = ClientSubmission.__database_session__.query(ClientSubmission).count()
        self.setIndentation(0)
        self.setExpandsOnDoubleClick(False)
        self.clicked.connect(self.on_clicked)
        delegate1 = ClientSubmissionDelegate(self)
        self.setItemDelegateForColumn(0, delegate1)
        self.model = model
        self.setModel(self.model)
        # self.header().setSectionResizeMode(0, QHeaderView.sectionResizeMode(self,0).ResizeToContents)
        self.setSelectionBehavior(QAbstractItemView.selectionBehavior(self).SelectRows)
        # self.setStyleSheet("background-color: #0D1225;")
        self.set_data()
        self.doubleClicked.connect(self.show_details)
        # self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # self.customContextMenuRequested.connect(self.open_menu)

        for ii in range(2):
            self.resizeColumnToContents(ii)

    @pyqtSlot(QModelIndex)
    def on_clicked(self, index):
        if not index.parent().isValid() and index.column() == 0:
            self.setExpanded(index, not self.isExpanded(index))

    def contextMenuEvent(self, event: QContextMenuEvent):
        """
        Creates actions for right click menu events.

        Args:
            event (_type_): the item of interest
        """
        indexes = self.selectedIndexes()

        dicto = next((item.data(1) for item in indexes if item.data(1)))
        query_obj = dicto['item_type'].query(name=dicto['query_str'], limit=1)
        logger.debug(query_obj)

        # NOTE: Convert to data in id column (i.e. column 0)
        # id = id.sibling(id.row(), 0).data()

        # logger.debug(id.model().query_group_object(id.row()))
        # clientsubmission = id.model().query_group_object(id.row())
        self.menu = QMenu(self)
        self.con_actions = query_obj.custom_context_events
        for key in self.con_actions.keys():
            if key.lower() == "add procedure":
                action = QMenu(self.menu)
                action.setTitle("Add Procedure")
                for procedure in query_obj.allowed_procedures:
                    proc_name = procedure.name
                    proc = QAction(proc_name, action)
                    proc.triggered.connect(lambda _, procedure_name=proc_name: self.con_actions['Add Procedure'](obj=self, proceduretype_name=procedure_name))
                    action.addAction(proc)
                    self.menu.addMenu(action)
            else:
                action = QAction(key, self)
                action.triggered.connect(lambda _, action_name=key: self.con_actions[action_name](obj=self))
                self.menu.addAction(action)
        # # NOTE: add other required actions
        self.menu.popup(QCursor.pos())

    def set_data(self, page: int = 1, page_size: int = 250) -> None:
        """
        sets data in model
        """
        self.clear()
        self.data = [item.to_dict(full_data=True) for item in
                     ClientSubmission.query(chronologic=True, page=page, page_size=page_size)]
        logger.debug(f"setting data:\n {pformat(self.data)}")
        # sys.exit()
        root = self.model.invisibleRootItem()
        for submission in self.data:
            group_str = f"{submission['submissiontype']}-{submission['submitter_plate_id']}-{submission['submitted_date']}"
            submission_item = self.model.add_group(parent=root, item_data=dict(
                name=group_str,
                query_str=submission['submitter_plate_id'],
                item_type=ClientSubmission
            ))
            for run in submission['run']:
                # self.model.append_element_to_group(group_item=group_item, element=run)
                run_item = self.model.add_group(parent=submission_item, item_data=dict(
                    name=run['plate_number'],
                    query_str=run['plate_number'],
                    item_type=Run
                ))

                for procedure in run['procedures']:
                    self.model.add_group(parent=run_item, item_data=dict(
                        name=procedure['name'],
                        query_str=procedure['name'],
                        item_type=Procedure
                    ))
        # root = self.model.invisibleRootItem()
        # for submission in self.data:
        #     submission_item = QStandardItem(submission['name'])
        #     root.appendRow(submission_item)
        #     for run in submission['run']:
        #         run_item = QStandardItem(run['name'])
        #         submission_item.appendRow(run_item)
        #         for procedure in run['procedures']:
        #             procedure_item = QStandardItem(procedure['name'])
        #             run_item.appendRow(procedure_item)
        # self._populateTree(self.data, self.model.invisibleRootItem())

    def _populateTree(self, children, parent):
        for child in children:
            logger.debug(child)
            child_item = QStandardItem(child['name'])
            parent.appendRow(child_item)
            if isinstance(children, List):
                self._populateTree(child, child_item)



    def clear(self):
        if self.model != None:
            # self.model.clear()       # works
            self.model.setRowCount(0)  # works

    def show_details(self, sel: QModelIndex):
        id = self.selectionModel().currentIndex()
        # NOTE: Convert to data in id column (i.e. column 0)
        id = id.sibling(id.row(), 1)
        try:
            id = int(id.data())
        except ValueError:
            return
        Run.query(id=id).show_details(self)

    def link_extractions(self):
        pass

    def link_pcr(self):
        pass


class ClientSubmissionRunModel(QStandardItemModel):


    def __init__(self, parent=None):
        super(ClientSubmissionRunModel, self).__init__(parent)
        headers = ["", "id", "Plate Number", "Started Date", "Completed Date", "Signed By"]
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)

    def add_group(self, parent, item_data):
        item_root = QStandardItem()
        item_root.setEditable(False)
        item = QStandardItem(item_data['name'])
        item.setEditable(False)
        i = parent.rowCount()
        for j, it in enumerate((item_root, item)):
            # NOTE: Adding item to invisible root row i, column j (wherever j comes from)
            parent.setChild(i, j, it)
            parent.setEditable(False)
        for j in range(self.columnCount()):
            it = parent.child(i, j)
            if it is None:
                # NOTE: Set invisible root child to empty if it is None.
                it = QStandardItem()
                parent.setChild(i, j, it)
        item_root.setData(dict(item_type=item_data['item_type'], query_str=item_data['query_str']), 1)
        return item_root

    def append_element_to_group(self, group_item, item_data: dict):
        # logger.debug(f"Element: {pformat(element)}")
        j = group_item.rowCount()
        item_icon = QStandardItem()
        item_icon.setEditable(False)
        # item_icon.setBackground(QColor("#0D1225"))
        # item_icon.setData(dict(item_type="Run", query_str=element['plate_number']), 1)
        # group_item.setChild(j, 0, item_icon)
        for i in range(self.columnCount()):
            it = self.horizontalHeaderItem(i)
            try:
                key = it.text().lower().replace(" ", "_")
            except AttributeError:
                key = None
            if not key:
                continue
            value = str(item_data[key])
            item = QStandardItem(value)
            item.setBackground(QColor("#CFE2F3"))
            item.setEditable(False)
            # item_icon.setChild(j, i, item)
            item.setData(dict(item_type=item_data['item_type'], query_str=item_data['query_str']),1)
            group_item.setChild(j, i, item)
        # group_item.setChild(j, 1, QStandardItem("B"))
        return item

    def get_value(self, idx: int, column: int = 1):
        return self.item(idx, column)

    def query_group_object(self, idx: int):
        row_obj = self.get_value(idx)
        logger.debug(row_obj.query_str)
        return self.sql_object.query(name=row_obj.query_str, limit=1)
