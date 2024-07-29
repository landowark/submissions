## Startup:
1. Open the app using the shortcut in the Submissions folder: L:\Robotics Laboratory Support\Submissions\Submissions App.lnk.
   1. Ignore the large black window of fast scrolling text, it is there for debugging purposes.
   2. The 'Submissions' tab should be open by default.
   3. Default settings (config.yml) will be copied to C:\Users\{YOUR USERNAME}\AppData\Local\submissions\config

## Logging in New Run:
*should fit 90% of usage cases*

1. Ensure a properly formatted Submission Excel form has been filled out. 
    a. The program can fill in reagent fields and some other information automatically, but should be checked for accuracy afterwards.
2. Click on 'File' in the menu bar, followed by 'Import Submission' and use the file dialog to locate the form.
   1.  The excel file may also be dragged into the grey area on the left hand side of the screen from Windows File Explorer. If so, skip step 3. 
3. Click 'Ok'.
4. Most of the fields in the form should be automatically filled in from the form area to the left of the screen.
5. You may need to maximize the app to ensure you can see all the info.
6. Any fields that are not automatically filled in can be filled in manually from the drop down menus.
	1. Any reagent lots not found in the drop downs can be typed in manually.
7. Once you are certain all the information is correct, click 'Submit' at the bottom of the form.
8. Add in any new reagents the app doesn't have in the database.
9. Once the new run shows up at the bottom of the Submissions, everything is fine.
10. In case of any mistakes, the run can be overwritten by a reimport.

## Adding Equipment to a Run:

1. Right click on the run in the Submissions Table to access the context menu.
2. Click on “Add Equipment”.
3. Select equipment used for each equipment role from the drop down menu.
   1. Any tips associated with a liquid handler will also be available in a separate drop down menu.
5. Select (or input) the process used on with the equipment.
   1. Equipment that is not necessary may disabled using the check boxes to the left of each entry.

## Importing PCR results (Wastewater only):

This is meant to import .xslx files created from the Design & Analysis Software

1. Click on 'File' -> 'Import PCR Results'.
2. Use the file dialog to locate the .xlsx file you want to import.
3. Click 'Okay'.

## Using the Gel Box (Wastewater Artic only):

1. Right click on the run in the Submissions Table to access the context menu.
2. Click on “Gel Box”.
3.	Choose the .jpg file exported from the Egel reader.
4.	Click “Okay”.
5.	If none exists, eEnter the DNA Core Submission Number and gel barcode at the top of the window.
6.	Use the histogram slide on the right side of the window to adjust the image contrast.
7.	Use the mouse scroll to zoom in on relevant areas of the image.
8.	Enter the control status in the grid at the bottom of the window.
9.	Add any relevant comments.
10.	Click “Okay”.

## Check existing Run:

1. Details of existing runs can be checked by double clicking on the row of interest in the summary sheet on the right of the 'Submissions' tab.
2. All information available on the run should be available in the resulting text window. 
   1. This information can be exported by clicking 'Export DOCX' at the top.

## Signing Off on a run:

1.	Open the “Submission Details” window (see 7.6 above).
2.	Scroll down to bottom of the details window.
3.	If the current user is authorized a button marked “Sign Off” will appear at the bottom of the page. Click it.

## Generating a report:

1. Click on 'Reports' -> 'Make Report' in the menu bar.
2. Select the start date and the end date you want for the report. Click 'ok'.
3. Use the file dialog to select a location to save the report.
	a. Both an excel sheet and a pdf should be generated containing summary information for submissions made by each client lab.

## Exporting a run as an Excel file:

1.	Right click on the run in the Submissions Table to access the context menu.
2.	Select “Export” from the context menu.
3.	Select the folder and input the filename in the “Save File” dialog.
4.	Click “Okay”.
5.	Ensure the resulting Excel workbook contains all the relevant information.

	
## Checking Controls:

1. Controls for bacterial runs are now incorporated directly into the submissions database using webview. (Admittedly this performance is not as good as with a browser, so you will have to triage your data)
2. Click on the "Controls" tab.
3. Range of dates for controls can be selected from the date pickers at the top.
	1. If start date is set after end date, the start date will default back to 3 months before end date.
	2. Recommendation is to use less than 6 month date range keeping in mind that higher data density will affect performance (with kraken being the worst so far)
4. Analysis type and subtype can be set using the drop down menus. (Only kraken has a subtype so far).

## Adding new Kit:

1. Click "Add Kit" tab in the tab bar.
2. Select the Submission type from the drop down menu.
3. Fill in the kit name (required) and other fields (optional).
4. For each reagent type in the kit click the "Add Reagent Type" button.
5. Fill in the name of the reagent type. Alternatively select from already existing types in the drop down.
6. Fill in the reagent location in the excel submission sheet.
	a. For example if the reagent name is in a sheet called "Reagent Info" in row 12, column 1, type "Reagent Info" in the "Excel Location Sheet Name" field. 
	b. Set 12 in the "Name Row" and 1 in the "Name Column".
	c. Repeat 6b for the Lot and the Expiry row and columns.
7. Click the "Submit" button at the top.

## Linking Extraction Logs:

1. Click "Monthly" -> "Link Extraction Logs".
2. Chose the .csv file taken from the extraction table runlogs folder.

## Linking PCR Logs:
1. Click "Monthly" -> "Link PCR Logs".
2. Chose the .csv file taken from the PCR table runlogs folder.

## SETUP:

## Download and Setup:
*Python v3.11 or greater must be installed on your system for this.*

1. Clone or download from github.
2. Enter the downloaded folder.
3. Open a terminal in the folder with the 'src' folder.
4. Create a new virtual environment: ```python -m venv .venv```
5. Activate the virtual environment: (Windows) ```.venv\Scripts\activate.bat```
6. Install dependencies: ```pip install -r requirements.txt```

## Database:
*If using a pre-existing database, skip this.*

1. Copy 'alembic_default.ini' to 'alembic.ini' in the same folder.
2. Open 'alembic.ini' and edit 'sqlalchemy.url' to the desired path of the database.
   1. The path by default is sqlite based. Postgresql support is available.
3. Open a terminal in the folder with the 'src' folder.
4. Run database migration: ```alembic upgrade head```

## First Run:

1. On first run, the application copies src/config.yml to C:\Users\{USERNAME}\AppData\Local\submissions\config
2. If this folder cannot be found, C:\Users\{USERNAME}\Documents\submissions will be used.
   1. If using Postgres, the 'database_path' and other variables will have to be updated manually.
3. Initially, the config variables are set parsing the 'sqlalchemy.url' variable in alembic.ini

## Building Portable Application:
*Download and Setup must have been performed beforehand*

1. Using pyinstaller, an exe can be created.
2. Open a terminal in the folder with the 'src' folder.
3. Activate the virtual environment: (Windows) ```.venv\Scripts\activate.bat```
4. Enter the following command: ```pyinstaller .\submissions.spec --noconfirm```