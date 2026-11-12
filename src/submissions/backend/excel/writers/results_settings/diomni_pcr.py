from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from . import DefaultSettings
from csv import writer as csvwriter
from frontend.widgets.functions import select_save_file
from tools import IndexDirection, convert_row_column_to_well


class DiomniPCRSettings(DefaultSettings):
    """
    Derived from DefaultSettings to write a plate map csv to import into Diomni.

    :cvar label: Button label that shows up in the Procedure creation (Depreciated)
    :type label: str
    """

    label = "Export Diomni Plate"

    def hex_to_rgb(self, hex_string: str) -> str:
        """
        Converts a hex colour string to RGB(RR,GG,BB) format.
        
        :param hex_string: Hex colour code to use. Example: '#007bff' -> 'RGB(0,123,255)'
        :type hex_string: str
        """
        # Remove the '#' prefix if present
        hex_string = hex_string.lstrip('#')
        # Convert hex to integer components
        r, g, b = tuple(int(hex_string[i:i+2], 16) for i in (0, 2, 4))
        return f"RGB({r},{g},{b})"
    
    def rgb_to_hex(self, rgb_string: str) -> str:
        """
        Converts 'RGB(RR,GG,BB)' format to hex string '#RRGGBB'.
        
        :param rgb_string: RGB colour code Example: 'RGB(0,123,255)' -> '#007bff'
        :type rgb_string: str
        """
        # Clean the string and extract numbers
        cleaned = rgb_string.replace('RGB(', '').replace(')', '')
        r, g, b = [int(x.strip()) for x in cleaned.split(',')]
        
        # Return formatted hex string
        return f"#{r:02x}{g:02x}{b:02x}"

    def write_output(self):
        """
        Writes settings to a csv file in diomni format.
        """
        
        filepath = self.render_file_path(file_extension="csv")
        toplines  = [
            ['*All Inputs are case sensitive.  For Example:  FAM is different from Fam', '', '', '', '', '', '', '', '', '', '', ''],
            ['*Do not change column header names and do not delete [Sample Setup]. Minimal columns needed are:  Well and Well Position', '', '', '', '', '', '', '', '', '', '', ''],
            ['*Passive Reference = ROX', '', '', '', '', '', '', '', '', '', '', ''],
            ['[Sample Setup]', '', '', '', '', '', '', '', '', '', '', ''],
            ['Well', 'Well Position', 'Sample Name', 'Biogroup Name', 'Biogroup Color', 'Target Name', 'Task', 'Reporter', 'Quencher', 'Quantity', 'Target Color', 'Comments']
        ]
        samples = []
        for assoc in self.procedure.sample:
            if not assoc.sample:
                continue
            for setting in self.settings:
                output = [
                    self.proceduretype.get_well_index(row=assoc.row, column=assoc.column, direction=IndexDirection.COL),
                    convert_row_column_to_well(assoc.row, assoc.column),
                    assoc.sample,
                    "",
                    "",
                    setting.get("Target Name", ""),
                    "STANDARD" if assoc.is_control == 1 else "UNKNOWN",
                    setting.get("Reporter", "").upper(),
                    "None",
                    "1" if assoc.is_control == 1 else "",
                    setting.get("Target Color", ""),
                    ""
                ]
                samples.append(output)
        with open(filepath, "w", newline='', encoding='utf-8') as f:
            writer = csvwriter(f, delimiter=",")
            writer.writerows(toplines)
            writer.writerows(samples)
            
__all__ = ["DiomniPCRSettings"]