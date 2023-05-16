from reportlab.graphics.barcode import createBarcodeImageInMemory
from reportlab.graphics.shapes import Drawing
from reportlab.lib.units import mm


def make_plate_barcode(text:str, width:int=100, height:int=25) -> Drawing:
    # return createBarcodeDrawing('Code128', value=text, width=200, height=50, humanReadable=True)
    return createBarcodeImageInMemory('Code128', value=text, width=width*mm, height=height*mm, humanReadable=True, format="png")