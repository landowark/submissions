from reportlab.graphics.barcode import createBarcodeDrawing, createBarcodeImageInMemory
from reportlab.graphics.shapes import Drawing
from reportlab.lib.units import mm


def make_plate_barcode(text:str) -> Drawing:
    # return createBarcodeDrawing('Code128', value=text, width=200, height=50, humanReadable=True)
    return createBarcodeImageInMemory('Code128', value=text, width=100*mm, height=25*mm, humanReadable=True, format="png")