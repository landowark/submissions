from . import DefaultSettings


class DiomniPCRSettings(DefaultSettings):

    label = "Export Diomni Plate"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)


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



