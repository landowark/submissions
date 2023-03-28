# __init__.py

from pathlib import Path

# Version of the realpython-reader package
__project__ = "submissions"
__version__ = "202303.4b"
__author__ = {"name":"Landon Wark", "email":"Landon.Wark@phac-aspc.gc.ca"}
__copyright__ = "2022-2023, Government of Canada"

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
