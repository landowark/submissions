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