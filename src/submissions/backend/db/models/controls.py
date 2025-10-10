# """
# All control related models.
# # NOTE: Can I just replace these controls with the results objects?
# """
# from __future__ import annotations
# from pprint import pformat
# from PyQt6.QtWidgets import QWidget
# from sqlalchemy import Column, String, TIMESTAMP, JSON, INTEGER, ForeignKey, case
# from sqlalchemy.orm import relationship, Query
# import logging, re
# from . import BaseClass
# from tools import setup_lookup, Report, Settings, super_splitter
# from datetime import date, datetime, timedelta
# from typing import List, Literal, Tuple, Generator
# # from re import Pattern
#
# logger = logging.getLogger(f"submissions.{__name__}")
#
#
# class ControlType(BaseClass):
#     """
#     Base class of a control archetype.
#     """
#     id = Column(INTEGER, primary_key=True)  #: primary key
#     name = Column(String(255), unique=True)  #: controltype name (e.g. Irida Control)
#     targets = Column(JSON)  #: organisms checked for
#     control = relationship("Control", back_populates="controltype")  #: control sample created of this type.
#
#     @classmethod
#     @setup_lookup
#     def query(cls,
#               name: str = None,
#               limit: int = 0
#               ) -> ControlType | List[ControlType]:
#         """
#         Lookup control archetypes in the database
#
#         Args:
#             name (str, optional): Name of the desired controltype. Defaults to None.
#             limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.
#
#         Returns:
#             ControlType | List[ControlType]: Single result if the limit = 1, else a list.
#         """
#         query = cls.__database_session__.query(cls)
#         match name:
#             case str():
#                 query = query.filter(cls.name == name)
#                 limit = 1
#             case _:
#                 pass
#         return cls.execute_query(query=query, limit=limit)
#
#     def get_modes(self, mode: Literal['kraken', 'matches', 'contains']) -> List[str]:
#         """
#         Get subtypes associated with this controltype (currently used only for Kraken)
#
#         Args:
#             mode (str): analysis mode submissiontype
#
#         Returns:
#             List[str]: list of subtypes available
#         """
#         if not self.control:
#             return
#         # NOTE: Get first instance since all should have same subtypes
#         # NOTE: Get mode of instance
#         jsoner = getattr(self.control[0], mode)
#         try:
#             # NOTE: Pick genera (all should have same subtypes)
#             genera = list(jsoner.keys())[0]
#         except IndexError:
#             return []
#         # NOTE subtypes now created for all modes, but ignored for all but allowed_for_subtyping later in the ControlsChart
#         subtypes = sorted(list(jsoner[genera].keys()), reverse=True)
#         return subtypes
#
#     # Marked for removal
#     # @property
#     # def control_class(self) -> Control:
#     #     """
#     #     Retrieves the Control class associated with this controltype
#     #
#     #     Returns:
#     #         Control: Associated Control class
#     #     """
#     #     return Control.find_polymorphic_subclass(polymorphic_identity=self.name)
#
#     @classmethod
#     def get_positive_control_types(cls, control_type: str) -> Generator[str, None, None]:
#         """
#         Gets list of Control types if they have targets
#
#         Returns:
#             Generator[str, None, None]: Control types that have targets
#         """
#         ct = cls.query(name=control_type).targets
#         return (k for k, v in ct.items() if v)
#
#     @classmethod
#     def build_positive_regex(cls, control_type: str) -> re.Pattern:
#         """
#         Creates a re.Pattern that will look for positive control types
#
#         Returns:
#             Pattern: Constructed pattern
#         """
#         strings = list(set([super_splitter(item, "-", 0) for item in cls.get_positive_control_types(control_type)]))
#         # NOTE: This will build a string like ^(ATCC49226|MCS)-.*
#         return re.compile(rf"(^{'|^'.join(strings)})-.*", flags=re.IGNORECASE)
#
#
# class Control(BaseClass):
#     """
#     Base class of a control sample.
#     """
#
#     id = Column(INTEGER, primary_key=True)  #: primary key
#     controltype_name = Column(String, ForeignKey("_controltype.name", ondelete="SET NULL",
#                                                  name="fk_BC_subtype_name"))  #: name of joined procedure type
#     controltype = relationship("ControlType", back_populates="control",
#                                foreign_keys=[controltype_name])  #: reference to parent control type
#     name = Column(String(255), unique=True)  #: Sample ID
#     sample_id = Column(String, ForeignKey("_sample.id", ondelete="SET NULL",
#                                                  name="fk_Cont_sample_id"))  #: name of joined procedure type
#     sample = relationship("Sample", back_populates="control")  #: This control's procedure sample
#     submitted_date = Column(TIMESTAMP)  #: Date submitted to Robotics
#     procedure_id = Column(INTEGER, ForeignKey("_procedure.id"))  #: parent procedure id
#     procedure = relationship("Procedure", back_populates="control",
#                               foreign_keys=[procedure_id])  #: parent procedure
#     result = Column(JSON)
#
#     def __repr__(self) -> str:
#         return f"<{self.controltype_name}({self.name})>"
#
#     @classmethod
#     @setup_lookup
#     def query(cls,
#               proceduretype: str | None = None,
#               subtype: str | None = None,
#               start_date: date | datetime | str | int | None = None,
#               end_date: date | datetime | str | int | None = None,
#               name: str | None = None,
#               limit: int = 0, **kwargs
#               ) -> Control | List[Control]:
#         """
#         Lookup control objects in the database based on a number of parameters.
#
#         Args:
#             proceduretype (str | None, optional): Submission type associated with control. Defaults to None.
#             subtype (str | None, optional): Control subtype, eg IridaControl. Defaults to None.
#             start_date (date | str | int | None, optional): Beginning date to search by. Defaults to 2023-01-01 if end_date not None.
#             end_date (date | str | int | None, optional): End date to search by. Defaults to today if start_date not None.
#             name (str | None, optional): Name of control. Defaults to None.
#             limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.
#
#         Returns:
#             Control|List[Control]: Control object of interest.
#         """
#         from backend.db import ProcedureType
#         query: Query = cls.__database_session__.query(cls)
#         match proceduretype:
#             case str():
#                 from backend.db import Procedure
#                 query = query.join(Procedure).join(ProcedureType).filter(ProcedureType.name == proceduretype)
#             case ProcedureType():
#                 from backend import Procedure
#                 query = query.join(Procedure).filter(Procedure.submission_type_name == proceduretype.name)
#             case _:
#                 pass
#                 # NOTE: by control type
#         match subtype:
#             case str():
#                 if cls.__name__ == "Control":
#                     raise ValueError(f"Cannot query base class Control with subtype.")
#                 elif cls.__name__ == "IridaControl":
#                     query = query.filter(cls.subtype == subtype)
#                 else:
#                     try:
#                         query = query.filter(cls.subtype == subtype)
#                     except AttributeError as e:
#                         logger.error(e)
#             case _:
#                 pass
#         # NOTE: by date range
#         if start_date is not None and end_date is None:
#             logger.warning(f"Start date with no end date, using today.")
#             end_date = date.today()
#         if end_date is not None and start_date is None:
#             logger.warning(f"End date with no start date, using 90 days ago.")
#             start_date = date.today() - timedelta(days=90)
#         if start_date is not None:
#             start_date = cls.rectify_query_date(start_date)
#             end_date = cls.rectify_query_date(end_date, eod=True)
#             query = query.filter(cls.submitted_date.between(start_date, end_date))
#         match name:
#             case str():
#                 query = query.filter(cls.name.startswith(name))
#                 limit = 1
#             case _:
#                 pass
#         return cls.execute_query(query=query, limit=limit)
#
#     # Marked for removal
#     # @classmethod
#     # def find_polymorphic_subclass(cls, polymorphic_identity: str | ControlType | None = None,
#     #                               attrs: dict | None = None) -> Control:
#     #     """
#     #     Find subclass based on polymorphic identity or relevant attributes.
#     #
#     #     Args:
#     #         polymorphic_identity (str | None, optional): String representing polymorphic identity. Defaults to None.
#     #         attrs (str | SubmissionType | None, optional): Attributes of the relevant class. Defaults to None.
#     #
#     #     Returns:
#     #         Control: Subclass of interest.
#     #     """
#     #     if isinstance(polymorphic_identity, dict):
#     #         polymorphic_identity = polymorphic_identity['value']
#     #     model = cls
#     #     match polymorphic_identity:
#     #         case str():
#     #             try:
#     #                 model = cls.__mapper__.polymorphic_map[polymorphic_identity].class_
#     #             except Exception as e:
#     #                 logger.error(
#     #                     f"Could not get polymorph {polymorphic_identity} of {cls} due to {e}, falling back to BasicRun")
#     #         case ControlType():
#     #             try:
#     #                 model = cls.__mapper__.polymorphic_map[polymorphic_identity.name].class_
#     #             except Exception as e:
#     #                 logger.error(
#     #                     f"Could not get polymorph {polymorphic_identity} of {cls} due to {e}, falling back to BasicRun")
#     #         case _:
#     #             pass
#     #     # NOTE: if attrs passed in and this cls doesn't have all attributes in attr
#     #     if attrs and any([not hasattr(cls, attr) for attr in attrs.keys()]):
#     #         # NOTE: looks for first model that has all included kwargs
#     #         try:
#     #             model = next(subclass for subclass in cls.__subclasses__() if
#     #                          all([hasattr(subclass, attr) for attr in attrs.keys()]))
#     #         except StopIteration:
#     #             raise AttributeError(
#     #                 f"Couldn't find existing class/subclass of {cls} with all attributes:\n{pformat(attrs.keys())}")
#     #     return model
#
#     # Marked for removal
#     # @classmethod
#     # def make_parent_buttons(cls, parent: QWidget) -> None:
#     #     """
#     #     Super that will make buttons in a CustomFigure. Made to be overridden.
#     #
#     #     Args:
#     #         parent (QWidget): chart holding widget to add buttons to.
#     #
#     #     Returns:
#     #         None: Child methods will return things.
#     #     """
#     #     return None
#
#     # Marked for removal
#     # @classmethod
#     # def make_chart(cls, parent, chart_settings: dict, ctx) -> Tuple[Report, "CustomFigure" | None]:
#     #     """
#     #     Dummy operation to be overridden by child classes.
#     #
#     #     Args:
#     #         parent (QWidget): widget to add chart to.
#     #         chart_settings (dict): settings passed down from chart widget
#     #         ctx (Settings): settings passed down from gui
#     #     """
#     #     return Report(), None
#
#     def delete(self):
#         self.__database_session__.delete(self)
#         self.__database_session__.commit()
