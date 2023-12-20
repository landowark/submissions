# __init__.py

from pathlib import Path

# Version of the realpython-reader package
__project__ = "submissions"
__version__ = "202312.3b"
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

# Hello Landon, this is your past self here. I'm trying not to screw you over like I usually do, so I will
# set out the workflow I've imagined for creating new submission types.
# First of all, you will need to write new parsing methods in backend.excel.parser to pull information out of the submission form
# for the submission itself as well as for any samples you can pull out of that same workbook.
# The workbooks no longer need a sheet map, but they do need their submission type put in the categories metadata of the client excel template.
# Second, you will have to update the model in backend.db.models.submissions and provide a new polymorph to the BasicSubmission object.
# The BSO should hold the majority of the general info.
# You can also update any of the parsers to pull out any custom info you need, like enforcing RSL plate numbers, scraping PCR results, etc.

# Landon, this is your slightly less past self here. For the most part, Past Landon has not screwed us. I've been able to add in the
# Wastewater Artic with minimal difficulties, except that the parser of the non-standard, user-generated excel sheets required slightly
# more work.

# Landon, this is your even more slightly less past self here. I've overhauled a lot of stuff to make things more flexible, so you should
# hopefully be even less screwed than before... at least with regards to parsers. The addition of kits and such is another story. Putting that
# On the todo list.

'''
Landon, this is 2023-11-07 Landon here in a comment string no less. Really all you should have to do now to add in new experiments is create a new
BasicSubmission derivative with associated SubbmissionType, BasicSample (and maybe SubmissionSampleAssociation if you're feeling lucky), oh, also, 
kits, reagenttypes, reagents... This is sounding less and less impressive as I type it.
'''