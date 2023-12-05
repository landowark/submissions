from pathlib import Path
import sys
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from tools import check_if_app, jinja_template_loading
import logging

logger = logging.getLogger(f"submissions.{__name__}")

def make_plate_map(sample_list:list) -> Image:
    """
    Makes a pillow image of a plate from hitpicks 

    Args:
        sample_list (list): list of sample dictionaries from the hitpicks

    Returns:
        Image: Image of the 96 well plate with positive samples in red.
    """  
    # If we can't get a plate number, do nothing  
    try:
        plate_num = sample_list[0]['plate_name']
    except IndexError as e:
        logger.error(f"Couldn't get a plate number. Will not make plate.")
        return None
    except TypeError as e:
        logger.error(f"No samples for this plate. Nothing to do.")
        return None
    # Make an 8 row, 12 column, 3 color ints array, filled with white by default
    grid = np.full((8,12,3),255, dtype=np.uint8)
    # Go through samples and change its row/column to red if positive, else blue
    for sample in sample_list:
        logger.debug(f"sample keys: {list(sample.keys())}")
        # set color of square
        if sample['positive']:
            colour = [255,0,0]
        else:
            if 'colour' in sample.keys():
                colour = sample['colour']
            else:
                colour = [0,0,255]
        grid[int(sample['row'])-1][int(sample['column'])-1] = colour
    # Create pixel image from the grid and enlarge
    img = Image.fromarray(grid).resize((1200, 800), resample=Image.NEAREST)
    # create a drawer over the image
    draw = ImageDraw.Draw(img)
    # draw grid over the image
    y_start = 0
    y_end = img.height
    step_size = int(img.width / 12)
    for x in range(0, img.width, step_size):
        line = ((x, y_start), (x, y_end))
        draw.line(line, fill=128)
    x_start = 0
    x_end = img.width
    step_size = int(img.height / 8)
    for y in range(0, img.height, step_size):
        line = ((x_start, y), (x_end, y))
        draw.line(line, fill=128)
    del draw
    old_size = img.size
    new_size = (1300, 900)
    # create a new, larger white image to hold the annotations
    new_img = Image.new("RGB", new_size, "White")
    box = tuple((n - o) // 2 for n, o in zip(new_size, old_size))
    # paste plate map into the new image
    new_img.paste(img, box)
    # create drawer over the new image
    draw = ImageDraw.Draw(new_img)
    if check_if_app():
        font_path = Path(sys._MEIPASS).joinpath("files", "resources")
    else:
        font_path = Path(__file__).parents[2].joinpath('resources').absolute()
        logger.debug(f"Font path: {font_path}")
    font = ImageFont.truetype(font_path.joinpath('arial.ttf').__str__(), 32)
    row_dict = ["A", "B", "C", "D", "E", "F", "G", "H"]
    # write the plate number on the image
    draw.text((100, 850),plate_num,(0,0,0),font=font)
    # write column numbers
    for num in range(1,13):
        x = (num * 100) - 10
        draw.text((x, 0), str(num), (0,0,0),font=font)
    # write row letters
    for num in range(1,9):
        letter = row_dict[num-1]
        y = (num * 100) - 10
        draw.text((10, y), letter, (0,0,0),font=font)
    return new_img

def make_plate_map_html(sample_list:list, plate_rows:int=8, plate_columns=12) -> str:
    """
    Constructs an html based plate map.

    Args:
        sample_list (list): List of submission samples
        plate_rows (int, optional): Number of rows in the plate. Defaults to 8.
        plate_columns (int, optional): Number of columns in the plate. Defaults to 12.

    Returns:
        str: html output string.
    """    
    for sample in sample_list:
        if sample['positive']:
            sample['background_color'] = "#f10f07"
        else:
            if "colour" in sample.keys():
                sample['background_color'] = "#69d84f"
            else:
                sample['background_color'] = "#80cbc4"
    output_samples = []
    for column in range(1, plate_columns+1):
        for row in range(1, plate_rows+1):
            try:
                well = [item for item in sample_list if item['row'] == row and item['column']==column][0]
            except IndexError:
                well = dict(name="", row=row, column=column, background_color="#ffffff")
            output_samples.append(well)
    env = jinja_template_loading()
    template = env.get_template("plate_map.html")
    html = template.render(samples=output_samples, PLATE_ROWS=plate_rows, PLATE_COLUMNS=plate_columns)
    return html

