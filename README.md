## Startup:
1. Open the app using the shortcut in the Submissions folder. For example: L:\\Robotics Laboratory Support\\Submissions\\submissions_v122b.exe - Shortcut.lnk (Version may have changed).
	a. Ignore the large black window of fast scrolling text, it is there for debugging purposes.
	b. The 'Submissions' tab should be open by default.

## Logging in New Run:
*should fit 90% of usage cases*

1. Ensure a properly formatted Submission Excel form has been filled out. 
    a. The program can fill in reagent fields and some other information automatically, but should be checked for accuracy afterwards.
2. Click on 'File' in the menu bar, followed by 'Import Submission' and use the file dialog to locate the form.
3. Click 'Ok'.
4. Most of the fields in the form should be automatically filled in from the form area to the left of the screen.
5. You may need to maximize the app to ensure you can see all the info.
6. Any fields that are not automatically filled in can be filled in manually from the drop down menus.
	a. Any reagent lots not found in the drop downs can be typed in manually.
7. Once you are certain all the information is correct, click 'Submit' at the bottom of the form.
8. Add in any new reagents the app doesn't have in the database.
9. Once the new run shows up at the bottom of the Submissions, everything is fine.
10. In case of any mistakes, the run can be overwritten by a reimport.

## Check existing Run:

1. Details of existing runs can be checked by double clicking on the row of interest in the summary sheet on the right of the 'Submissions' tab.
2. All information available on the run should be available in the resulting text window. This information can be exported by clicking 'Export PDF' at the top.

## Generating a report:

1. Click on 'Reports' -> 'Make Report' in the menu bar.
2. Select the start date and the end date you want for the report. Click 'ok'.
3. Use the file dialog to select a location to save the report.
	a. Both an excel sheet and a pdf should be generated containing summary information for submissions made by each client lab.

## Importing PCR results:

This is meant to import .xslx files created from the Design & Analysis Software
1. Click on 'File' -> 'Import PCR Results'.
2. Use the file dialog to locate the .xlsx file you want to import.
3. Click 'Okay'.
	
## Checking Controls:

1. Controls for bacterial runs are now incorporated directly into the submissions database using webview. (Admittedly this performance is not as good as with a browser, so you will have to triage your data)
2. Click on the "Controls" tab.
3. Range of dates for controls can be selected from the date pickers at the top.
	a. If start date is set after end date, the start date will default back to 3 months before end date.
	b. Recommendation is to use less than 6 month date range keeping in mind that higher data density will affect performance (with kraken being the worst so far)
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

## Hitpicking:
1. Select all submissions you wish to hitpick using "Ctrl + click". All must have PCR results.
2. Right click on the last sample and select "Hitpick" from the contex menu.
3. Select location to save csv file.
