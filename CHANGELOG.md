# 202504.04

- Added html links for equipment/processes/tips.

# 202504.03

- Split Concentration controls on the chart so they are individually selectable.

# 202504.02

- Added cscscience gitlab remote.
- Refined query-by-date to use start/end of day times to improve accuracy.

# 202504.01

- Added in method to backup submissions to xlsx (partly).
- Added in checkbox to use all samples in Concentrations tab (very slow).

# 202503.05

- Created Sample verification before import.
- Shuttered tools.get_config and moved to new inclusive Settings class.
- Added concentrations chart tab.
- Saving report xlsx/pdf now inserts report class name in file name.

# 202503.04

- Kit editor debugging.
- Fixed missing search bar in Edit Reagent.

# 202503.03

- Kit editor pre-release.

# 202501.02

- Fixed bug where Wastewater ENs were not receiving rsl_number and therefore not getting PCR data.

# 202501.01

- Created Client Manager to be run by super users.

# 202412.06

- Switched startup/teardown scripts to importlib/getattr addition to ctx.

# 202412.05

- Switched startup/teardown scripts to decorator registration.

# 202412.04

- Update of wastewater to allow for duplex PCR primers.
- Addition of expiry check after kit integrity check.

## 202412.03

- Automated truncating of object names longer than 64 chars going into _auditlog
- Writer will now blank out the lookup table before writing to ensure removal of extraneous help info.
- Added support for running startup and teardown scripts.
- Created startup script to pull irida controls from secondary database.
- Added ability to not import reagents on first import.

## 202412.02

- Addition of turnaround time tracking
- Merged new Infopane with old ControlsView

## 202411.05

- Can now calculate turnaround time including holidays. 

## 202411.04

- Add reagent from scrape now limits roles to those found in kit to prevent confusion.
- Added audit logs to track changes.
- Added completed_date column to _basicsubmission to track turnaround time.

## 202411.01

- Code clean up.
- Improved flexibility of Irida chart for subtyping.

## 202410.03

- Added code for cataloging of PCR controls.
- Data from control charts now exportable.
- Irida parser updated.

## 202410.02

- Trimmed down html timeline buttons for controls window.
- Improved paginator for submissions table.
- Refactor of Controls to support multiple types. (Note: Irida parser not updated yet.)

## 202410.01

- Reverted details exports from docx back to pdf.
- Large scale speedups for control chart construction.
- Reports are now given their own tab and can be updated in real time. 

## 202409.05

- Replaced some lists with generators to improve speed, added javascript to templates for click events.
- Added in custom field for BasicSubmission which will allow limited new fields to be added to generic submission types.

## 202409.04

- Fixed wastewater sample writing bug.
- Added regex exclusion for KitTypeReagentRole.uses to trim down Bacteria Positive Control lot list.

## 202409.03

- Better navigation and clarity in details panes.
- Upgraded sample search to (semi) realtime search.
- Improved error messaging.

## 202409.02

- Creation of generic submissions using only database is now supported.

## 202408.05

- Improved scraping for gel info of Artic submissions.

## 202408.04

- Fixed false error throw when tips added in xl and from app.

## 202408.03

- Fixed issue backing up database file.

## 202407.05

- Fixed issue with scrolling form potentially altering combobox values.

## 202407.04

- Added support for postgresql databases (auto backup not functional).
- Improved portability and folder obscuring.

## 202407.02

- HTML template for 'About'.
- More flexible custom parsers/writers due to custom info items.
- Vastly increased portability of the reporting functions.

## 202407.01

- Better documentation. 

## 202406.04

- Exported submission details will now be in docx format.
- Adding in tips to Equipment usage.
- New WastewaterArticAssociation will track previously missed sample info.

## 202406.02

- Attached Contact to Submission.
- Renamed ReagentType to ReagentRole to prevent confusion.

## 202405.04

- Improved Webview of submission details.
- Fixed Reagents not being updated on edit.
- Fixed data resorting after submitting new run.

## 202405.03

- Settings can now pull values from the db.
- Improved generic and WW specific PCR parsers.
- Various bug fixes.

## 202405.01

- New Excel writers

## 202404.05

- Addition of default query method using Kwargs.

## 202404.04

- Storing of default values in db rather than hardcoded.
- Removed usage of reportlab. PDF creation handled by PyQt6
- Reconfigured parsers, forms and reports around new default values.
- Fixed 'Missing' and 'Parsed' reagents disconnect in forms.

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
- Added submission editing functionality.

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

- Auto-filling of some empty cells in Excel file.
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
- Fixed error when expiry date stored as int in Excel sheet.

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