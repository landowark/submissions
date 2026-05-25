from . import DefaultSettings
import csv, logging
from frontend.widgets.functions import select_save_file
from tools import row_map

logger = logging.getLogger(f"submissions.{__name__}")

class DiomniPCRSettings(DefaultSettings):

    label = "Export Diomni Plate"

    def hex_to_rgb(self, hex_string):
        """
        Converts a hex color string to RGB(RR,GG,BB) format.
        Example: '#007bff' -> 'RGB(0,123,255)'
        """
        # Remove the '#' prefix if present
        hex_string = hex_string.lstrip('#')
        
        # Convert hex to integer components
        r, g, b = tuple(int(hex_string[i:i+2], 16) for i in (0, 2, 4))
        
        return f"RGB({r},{g},{b})"
    
    def rgb_to_hex(self, rgb_string):
        """
        Converts 'RGB(RR,GG,BB)' format to hex string '#RRGGBB'.
        Example: 'RGB(0,123,255)' -> '#007bff'
        """
        # Clean the string and extract numbers
        cleaned = rgb_string.replace('RGB(', '').replace(')', '')
        r, g, b = [int(x.strip()) for x in cleaned.split(',')]
        
        # Return formatted hex string
        return f"#{r:02x}{g:02x}{b:02x}"

    def write_output(self):
        filepath = select_save_file(obj=self.parent, default_name=self.procedure.name.get("value").replace(":", ""), extension="csv")
        toplines  = [
            ['*All Inputs are case sensitive.  For Example:  FAM is different from Fam', '', '', '', '', '', '', '', '', '', '', ''],
            ['*Do not change column header names and do not delete [Sample Setup]. Minimal columns needed are:  Well and Well Position', '', '', '', '', '', '', '', '', '', '', ''],
            ['*Passive Reference = ROX', '', '', '', '', '', '', '', '', '', '', ''],
            ['[Sample Setup]', '', '', '', '', '', '', '', '', '', '', ''],
            ['Well', 'Well Position', 'Sample Name', 'Biogroup Name', 'Biogroup Color', 'Target Name', 'Task', 'Reporter', 'Quencher', 'Quantity', 'Target Color', 'Comments']
        ]
        samples = []
        for sample in self.procedure.sample:
            for setting in self.settings:
                output = [
                    self.proceduretype.get_well_index(row_idx=sample.row, col_idx=sample.column, direction="col"),
                    f"{row_map[sample.row]}{sample.column}",
                    sample.sample_id,
                    "",
                    "",
                    setting.get("Target Name", ""),
                    "STANDARD" if sample.is_control > 0 else "UNKNOWN",
                    setting.get("Reporter", "").upper(),
                    "None",
                    "1" if sample.is_control == 1 else "",
                    setting.get("Target Color", ""),
                    ""
                ]
                samples.append(output)
        with open(filepath, "w", newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter=",")
            writer.writerows(toplines)
            writer.writerows(samples)
            