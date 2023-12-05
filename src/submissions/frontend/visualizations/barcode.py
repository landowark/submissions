from reportlab.graphics.barcode import createBarcodeImageInMemory
from reportlab.graphics.shapes import Drawing
from reportlab.lib.units import mm


def make_plate_barcode(text:str, width:int=100, height:int=25) -> Drawing:
    """
    Creates a barcode image for a given str.

    Args:
        text (str): Input string
        width (int, optional): Width (pixels) of image. Defaults to 100.
        height (int, optional): Height (pixels) of image. Defaults to 25.

    Returns:
        Drawing: image object
    """    
    # return createBarcodeDrawing('Code128', value=text, width=200, height=50, humanReadable=True)
    return createBarcodeImageInMemory('Code128', value=text, width=width*mm, height=height*mm, humanReadable=True, format="png")