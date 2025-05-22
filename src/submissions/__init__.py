# __init__.py

from pathlib import Path
from datetime import date
import calendar

year = date.today().year
month = date.today().month
day = date.today().day


def get_week_of_month() -> int:
    """
    Gets the current week number of the month.

    Returns:
        int: 1 if first week of month, etc.
    """
    for ii, week in enumerate(calendar.monthcalendar(date.today().year, date.today().month)):
        if day in week:
            return ii + 1


# Automatically completes project info for help menu and compiling.
__project__ = "procedure"
__version__ = f"{year}{str(month).zfill(2)}.{get_week_of_month()}b"
__author__ = {"name": "Landon Wark", "email": "Landon.Wark@phac-aspc.gc.ca"}
__copyright__ = f"2022-{year}, Government of Canada"
__github__ = "https://github.com/landowark/submissions"

project_path = Path(__file__).parents[2].absolute()


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
