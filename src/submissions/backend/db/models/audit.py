"""
Audit logging model for database transaction tracking.

Provides the :class:`AuditLog` model and related functionality for tracking
and querying database changes by user and date range.
"""
from __future__ import annotations
from typing import List
from dateutil.parser import parse
from sqlalchemy.orm import declarative_base, DeclarativeMeta, Query
from . import BaseClass, ctx
from sqlalchemy import Column, INTEGER, String, JSON, TIMESTAMP, func
from datetime import date, datetime, timedelta
import logging

logger = logging.getLogger(f"submissions.{__name__}")

# NOTE: Need a seperate base for this.
Base: DeclarativeMeta = declarative_base()

# NOTE: When rebuilding db, change this to baseclass for alembic  
class AuditLog(Base):
    """
    Audit log model for tracking database transactions and changes.
    
    Records all modifications made to the database, including information about
    what was changed, who made the change, and when it occurred. Supports querying
    by date range to retrieve historical transaction data.
    
    :ivar id: Primary key auto-incremented identifier.
    :vartype id: int
    :ivar user: The user who made the database change.
    :vartype user: str
    :ivar time: Timestamp of when the change was made.
    :vartype time: datetime
    :ivar object: Name of the database object that was changed.
    :vartype object: str
    :ivar changes: JSON structure containing the details of what was changed.
    :vartype changes: dict
    """

    __tablename__ = "_auditlog"

    id = Column(INTEGER, primary_key=True, autoincrement=True)  #: primary key
    user = Column(String(64)) #: The user who made the change
    time = Column(TIMESTAMP) #: When the change was made
    object = Column(String(64)) #: What was changed
    changes = Column(JSON) #: List of changes that were made

    def __repr__(self) -> str:
        """
        Return string representation of this audit log entry.
        
        :return: String representation in format ``<object_name: username @ timestamp>``.
        :rtype: str
        """
        return f"<{self.object}: {self.user} @ {self.time}>"

    @classmethod
    def query(cls, start_date: date | str | int | None = None, end_date: date | str | int | None = None) -> List[AuditLog]:
        """
        Search for audit log entries within an optional date range.
        
        Queries the audit log database table and returns all transactions within an optional
        start and end date range. If only one date is provided, sensible defaults are applied.
        Supports multiple input date formats for flexibility.

        :param start_date: Earliest date to search from. Can be:
        
                           - :class:`date` object
                           - :class:`datetime` object
                           - ``int`` (Excel ordinal format)
                           - ``str`` (parsed by dateutil.parser)
                           - ``None`` (defaults to minimum recorded date)
        :type start_date: date | str | int | None
        :param end_date: Latest date to search to (inclusive). Can be:
        
                         - :class:`date` object
                         - :class:`datetime` object
                         - ``int`` (Excel ordinal format)
                         - ``str`` (parsed by dateutil.parser)
                         - ``None`` (defaults to today)
        :type end_date: date | str | int | None
        :return: List of audit log entries matching the date criteria.
        :rtype: list[:class:`AuditLog`]
        
        :raises TypeError: If start_date or end_date are in an unsupported type.
        
        .. note::
           If start_date is provided without end_date, end_date defaults to today.
           If end_date is provided without start_date, start_date defaults to the
           earliest recorded transaction date.
           If both dates are None, returns all audit log entries.
        """
        session = BaseClass.__database_session__
        # session = ctx.database.session()
        query: Query = session.query(cls)
        if start_date is not None and end_date is None:
            logger.warning(f"Start date with no end date, using today.")
            end_date = date.today()
        if end_date is not None and start_date is None:
            logger.warning(f"End date with no start date, using Jan 1, 2023")
            start_date = session.query(cls, func.min(cls.time)).first()[1]
        if start_date is not None:
            match start_date:
                case date():
                    start_date = start_date.strftime("%Y-%m-%d")
                case int():
                    start_date = datetime.fromordinal(
                        datetime(1900, 1, 1).toordinal() + start_date - 2).date().strftime("%Y-%m-%d")
                case str():
                    start_date = parse(start_date).strftime("%Y-%m-%d")
                case _:
                    raise TypeError(f"Unsupported type {type(start_date)} for start_date")
            match end_date:
                case date() | datetime():
                    end_date = end_date + timedelta(days=1)
                    end_date = end_date.strftime("%Y-%m-%d")
                case int():
                    end_date = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + end_date - 2).date() + timedelta(days=1)
                    end_date = end_date.strftime("%Y-%m-%d")
                case str():
                    end_date = parse(end_date) + timedelta(days=1)
                    end_date = end_date.strftime("%Y-%m-%d")
                case _:
                    raise TypeError(f"Unsupported type {type(end_date)} for end_date")
            if start_date == end_date:
                start_date = datetime.strptime(start_date, "%Y-%m-%d").strftime("%Y-%m-%d %H:%M:%S.%f")
                query = query.filter(cls.time == start_date)
            else:
                query = query.filter(cls.time.between(start_date, end_date))
        return query.all()
