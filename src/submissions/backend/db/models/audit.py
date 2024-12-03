"""
Contains the audit log class and functions.
"""
from typing import List

from dateutil.parser import parse
from sqlalchemy.orm import declarative_base, DeclarativeMeta, Query
from . import BaseClass
from sqlalchemy import Column, INTEGER, String, JSON, TIMESTAMP, func
from datetime import date, datetime, timedelta
import logging

logger = logging.getLogger(f"submissions.{__name__}")

Base: DeclarativeMeta = declarative_base()

class AuditLog(Base):

    __tablename__ = "_auditlog"

    id = Column(INTEGER, primary_key=True, autoincrement=True)  #: primary key
    user = Column(String(64))
    time = Column(TIMESTAMP)
    object = Column(String(64))
    changes = Column(JSON)

    def __repr__(self):
        return f"<{self.user} @ {self.time}>"

    @classmethod
    def query(cls, start_date: date | str | int | None = None, end_date: date | str | int | None = None) -> List["AuditLog"]:
        """
        Searches for database transactions by date.

        Args:
            start_date (date | str | int | None, Optional): Earliest date sought. Defaults to None
            end_date (date | str | int | None, Optional): Latest date sought. Defaults to None

        Returns:
            List[AuditLog]: List of transactions made to the database.
        """
        session = BaseClass.__database_session__
        query: Query = session.query(cls)
        if start_date is not None and end_date is None:
            logger.warning(f"Start date with no end date, using today.")
            end_date = date.today()
        if end_date is not None and start_date is None:
            logger.warning(f"End date with no start date, using Jan 1, 2023")
            start_date = session.query(cls, func.min(cls.time)).first()[1]
        if start_date is not None:
            # logger.debug(f"Querying with start date: {start_date} and end date: {end_date}")
            match start_date:
                case date():
                    # logger.debug(f"Lookup BasicSubmission by start_date({start_date})")
                    start_date = start_date.strftime("%Y-%m-%d")
                case int():
                    # logger.debug(f"Lookup BasicSubmission by ordinal start_date {start_date}")
                    start_date = datetime.fromordinal(
                        datetime(1900, 1, 1).toordinal() + start_date - 2).date().strftime("%Y-%m-%d")
                case _:
                    # logger.debug(f"Lookup BasicSubmission by parsed str start_date {start_date}")
                    start_date = parse(start_date).strftime("%Y-%m-%d")
            match end_date:
                case date() | datetime():
                    # logger.debug(f"Lookup BasicSubmission by end_date({end_date})")
                    end_date = end_date + timedelta(days=1)
                    end_date = end_date.strftime("%Y-%m-%d")
                case int():
                    # logger.debug(f"Lookup BasicSubmission by ordinal end_date {end_date}")
                    end_date = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + end_date - 2).date() + timedelta(days=1)
                    end_date = end_date.strftime("%Y-%m-%d")
                case _:
                    # logger.debug(f"Lookup BasicSubmission by parsed str end_date {end_date}")
                    end_date = parse(end_date) + timedelta(days=1)
                    end_date = end_date.strftime("%Y-%m-%d")
            # logger.debug(f"Compensating for same date by using time")
            if start_date == end_date:
                start_date = datetime.strptime(start_date, "%Y-%m-%d").strftime("%Y-%m-%d %H:%M:%S.%f")
                query = query.filter(cls.time == start_date)
            else:
                query = query.filter(cls.time.between(start_date, end_date))
        return query.all()
