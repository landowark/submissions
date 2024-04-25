## 202404.04

- Storing of default values in db rather than hardcoded.

## 202404.03

- Package updates.
- Bug fixes for JSON updaters.

## 202404.02

- Various bug fixes.
- Move import PCR results to context menu.
- Automated backup of database.
- Added ability to sign off on submission in submission details.

## 202403.03

- Automated version construction.

## 202403.02

- Moved functions out of submission container to submission form
- Added submission editting functionality.

## 202403.01

- Added navigation in submission details to sample details.
- Updated cost calculations.

## 202402.04

- Addition of comments to gel box.

## 202402.01

- Addition of gel box for Artic quality control.

## 202401.04

- Large scale database refactor to increase modularity.

## 202401.01

- Improved tooltips and form regeneration.

## 202312.03

- Enabled creation of new submission types in gui.
- Enabled Equipment addition.

## 202312.02

- Bug fixes for switching kits

## 202312.01

- Control samples info now available in plate map.
- Backups will now create a regenerated xlsx file.
- Report generator now does sums automatically.

## 202311.04

- Added xlsx template files to the database.
- Switched session hand-off to sqlalchemy to abstract parent class.

## 202311.03

- Added in tabular log parser.
- Split main_window_functions into object specific functions.

## 202311.02

- Construct first strand integrated into Artic Import.
- Addition of query_or_create methods for some classes.

## 202311.01

- Kit integrity is now checked before creation of sql object to improve reagent type lookups.

## 202310.03

- Better flexibility with parsers pulling methods from database objects.

## 202310.02

- Improvements to First strand constructor.
- Submission forms can now be dragged and dropped into the form widget.

## 202310.01

- Controls linker is now depreciated.
- Controls will now be directly added to their submissions instead of having to run linker.
- Submission details now has additional html functionality in plate map.
- Added Submission Category to fields.
- Increased robustness of form parsers by adding custom procedures for each.

## 202309.04

- Updated KitAdder to add location info as well.
- Extraction kit can now be updated after import.
- Large scale refactoring to improve efficiency of database functions.

## 202309.03

- Autofill now adds name of reagent instead of type.

## 202309.02

- Massive restructure of app and database to allow better relationships between kits/reagenttypes & submissions/samples.

## 202308.03

- Large restructure of database to allow better relationships between kits/reagenttypes & submissions/samples.

## 202307.04

- Large scale refactor to clean up code.
- Settings now in the form of a pydantic object.
- Individual plate details now in html format.

## 202307.03

- Auto-filling of some empty cells in excel file.
- Better pydantic validations of missing data.

## 202307.02

- Better column counting for cost recovery purposes.
- Improvements to pydantic validations.

## 202307.01

- Fixed bug where date increment of controls not working for multiple same dates.
- Fixed bug by having lookup of reagents by lot *and* reagenttype instead of just lot.
- Added in pydantic to validate submission info.
- Moved parser to metadata based recognition of submission type.

## 202306.03

- Improve WW plate mapping by using layout in submission forms rather than PCR.

## 202306.02

- Addition of bacterial plate maps to details export.
- Change in Artic cost calculation to reflect multiple output plates per submission.

## 202306.01

- Large scale shake up of import and scraper functions.
- Addition of Artic scrapers.

## 202305.05

- Hitpicking now creates source plate map image.
- Hitpick plate map is now included in exported plate results.

## 202305.04

- Added in hitpicking for plates with PCR results
- Fixed error when expiry date stored as int in excel sheet.

## 202305.03

- Added a detailed tab to the cost report.

## 202305.02

- Added rudimentary barcode printing.
- Added ability to comment on submissions.
- Updated kit creation methods to keep pace with new cost calculations.

## 202305.01

- Improved kit cost calculation.

## 202304.04

- Added in discounts for kits based on kit used and submitting client.
- Kraken controls graph now only pulls top 50 results to prevent crashing.
- Improved cost calculations per column in a 96 well plate.

## 202304.01

- Improved function results output to ui.
- Added Well Call Assessment to PCR scraping.

## 202303.05

- Increased robustness of RSL plate number enforcement.
- Added in ability to scrape and include PCR results for wastewater.

## 202303.04

- Added in scraping of logs from the PCR table to add to wastewater submissions.
- Completed partial imports that will add in missing reagents found in the kit indicated by the user.
- Added web documentation to the help menu.

## 202303.03

- Increased robustness by utilizing PyQT6 widget names to pull data from forms instead of previously used label/input zip.
- Above allowed for creation of more helpful prompts.
- Added sorting feature to Submission summary.
- Reagent import dropdowns will now prioritize lot number found in a parsed sheet, moving it to the top of the list.