# __init__.py
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from pathlib import Path
from datetime import date
import calendar
import re
import sys

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

def get_version() -> int:
    if not getattr(sys, 'frozen', False):
        dist_folders = Path(__file__).parents[2].joinpath("dist").iterdir()
        current_yyyymm = date.today().strftime('%Y%m')
        max_num = -1
        for path in dist_folders:
            filename = path.name
            # Match files that contain the current year-month substring
            if current_yyyymm in filename:
                # Use regex to find the number before the 'b' at the end (e.g., .1b or .5b)
                match = re.search(r'\.(\d+)b$', filename)
                if match:
                    # Extract the number and compare to find the largest
                    num = int(match.group(1))
                    if num > max_num:
                        max_num = num
        dist_num = max_num + 1 if max_num != -1 else 1
        return f"{year}{str(month).zfill(2)}.{dist_num}b"
    else:
        v = sys.executable
        match = re.search(r"\d{6}\.\w+", v)
        v = match.group(0) if match else ""
        return v.replace("_", " ").upper() if v else "Unknown Version"


# Automatically completes project info for help menu and compiling.
__project__ = "submissions_tng"
__version__ = get_version()
__author__ = {"name": "Landon Wark", "email": "Landon.Wark@phac-aspc.gc.ca"}
__copyright__ = f"2022-{year}, Government of Canada"
__github__ = "https://github.com/landowark/submissions"

project_path = Path(__file__).parents[2].absolute()

