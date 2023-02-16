
from pandas import DataFrame, concat
from backend.db import models
import json
import logging
from jinja2 import Environment, FileSystemLoader
from datetime import date
import sys
from pathlib import Path

logger = logging.getLogger(f"submissions.{__name__}")

# set path of templates depending on pyinstaller/raw python
if getattr(sys, 'frozen', False):
    loader_path = Path(sys._MEIPASS).joinpath("files", "templates")
else:
    loader_path = Path(__file__).parents[2].joinpath('templates').absolute().__str__()
loader = FileSystemLoader(loader_path)
env = Environment(loader=loader)

logger = logging.getLogger(f"submissions.{__name__}")

def make_report_xlsx(records:list[dict]) -> DataFrame:
    """
    create the dataframe for a report

    Args:
        records (list[dict]): list of dictionaries created from submissions

    Returns:
        DataFrame: output dataframe
    """    
    df = DataFrame.from_records(records)
    # put submissions with the same lab together
    df = df.sort_values("Submitting Lab")
    # aggregate cost and sample count columns
    df2 = df.groupby(["Submitting Lab", "Extraction Kit"]).agg({'Extraction Kit':'count', 'Cost': 'sum', 'Sample Count':'sum'})
    df2 = df2.rename(columns={"Extraction Kit": 'Kit Count'})
    logger.debug(f"Output daftaframe for xlsx: {df2.columns}")
    # apply formating to cost column
    # df2.iloc[:, (df2.columns.get_level_values(1)=='sum') & (df2.columns.get_level_values(0)=='Cost')] = df2.iloc[:, (df2.columns.get_level_values(1)=='sum') & (df2.columns.get_level_values(0)=='Cost')].applymap('${:,.2f}'.format)
    return df2

# def split_row_item(item:str) -> float:
#     return item.split(" ")[-1]


def make_report_html(df:DataFrame, start_date:date, end_date:date) -> str:
    
    """
    generates html from the report dataframe

    Args:
        df (DataFrame): input dataframe generated from 'make_report_xlsx' above
        start_date (date): starting date of the report period
        end_date (date): ending date of the report period

    Returns:
        str: html string
    """    
    old_lab = ""
    output = []
    logger.debug(f"Report DataFrame: {df}")
    for ii, row in enumerate(df.iterrows()):
        # row = [item for item in row]
        logger.debug(f"Row {ii}: {row}")
        lab = row[0][0]
        logger.debug(type(row))
        logger.debug(f"Old lab: {old_lab}, Current lab: {lab}")
        logger.debug(f"Name: {row[0][1]}")
        data = [item for item in row[1]]
        # logger.debug(data)
        # logger.debug(f"Cost: {split_row_item(data[1])}")
        # logger.debug(f"Kit count: {split_row_item(data[0])}")
        # logger.debug(f"Sample Count: {split_row_item(data[2])}")
        kit = dict(name=row[0][1], cost=data[1], plate_count=int(data[0]), sample_count=int(data[2]))
        if lab == old_lab:
            output[-1]['kits'].append(kit)
            output[-1]['total_cost'] += kit['cost']
            output[-1]['total_samples'] += kit['sample_count']
            output[-1]['total_plates'] += kit['plate_count']
        else:
            adder = dict(lab=lab, kits=[kit], total_cost=kit['cost'], total_samples=kit['sample_count'], total_plates=kit['plate_count'])
            output.append(adder)
        old_lab = lab
    logger.debug(output)
    dicto = {'start_date':start_date, 'end_date':end_date, 'labs':output}#, "table":table}
    temp = env.get_template('summary_report.html')
    html = temp.render(input=dicto)
    return html


            


# def split_controls_dictionary(ctx:dict, input_dict) -> list[dict]:
#     # this will be the date in string form
#     dict_name = list(input_dict.keys())[0]
#     # the data associated with the date key
#     sub_dict = input_dict[dict_name]
#     # How many "count", "Percent", etc are in the dictionary
#     data_size = get_dict_size(sub_dict)
#     output = []
#     for ii in range(data_size):
#         new_dict = {}
#         for genus in sub_dict:
#             logger.debug(genus)
#             sub_name = list(sub_dict[genus].keys())[ii]
#             new_dict[genus] = sub_dict[genus][sub_name]
#         output.append({"date":dict_name, "name": sub_name, "data": new_dict})
#     return output
        
        
# def get_dict_size(input:dict):
#     return max(len(input[item]) for item in input)


# def convert_all_controls(ctx:dict, data:list) -> dict:
#     dfs = {}
#     dict_list = [split_controls_dictionary(ctx, datum) for datum in data]
#     dict_list = [item for sublist in dict_list for item in sublist]
#     names = list(set([datum['name'] for datum in dict_list]))
#     for name in names:
        
        
#         # df = DataFrame()
#         # entries = [{item['date']:item['data']} for item in dict_list if item['name']==name]
#         # series_list = []
#         # df = pd.json_normalize(entries)
#         # for entry in entries:
#         #     col_name = list(entry.keys())[0]
#         #     col_dict = entry[col_name]
#         #     series = pd.Series(data=col_dict.values(), index=col_dict.keys(), name=col_name)
#         #     # df[col_name] = series.values
#         #     # logger.debug(df.index)
#         #     series_list.append(series)
#         # df = DataFrame(series_list).T.fillna(0)
#         # logger.debug(df)
#         dfs['name'] = df
#     return dfs

def convert_control_by_mode(ctx:dict, control:models.Control, mode:str) -> list[dict]:
    """
    split control object into analysis types

    Args:
        ctx (dict): settings passed from gui
        control (models.Control): control to be parsed into list
        mode (str): analysis type

    Returns:
        list[dict]: list of records
    """    
    output = []
    data = json.loads(getattr(control, mode))
    for genus in data:
        _dict = {}
        _dict['name'] = control.name
        _dict['submitted_date'] = control.submitted_date
        _dict['genus'] = genus
        _dict['target'] = 'Target' if genus.strip("*") in control.controltype.targets else "Off-target"
        for key in data[genus]:
            _dict[key] = data[genus][key]
        output.append(_dict)
    # logger.debug(output)
    return output


def convert_data_list_to_df(ctx:dict, input:list[dict], subtype:str|None=None) -> DataFrame:
    """
    Convert list of control records to dataframe

    Args:
        ctx (dict): settings passed from gui
        input (list[dict]): list of dictionaries containing records
        subtype (str | None, optional): _description_. Defaults to None.

    Returns:
        DataFrame: _description_
    """    
    df = DataFrame.from_records(input)
    safe = ['name', 'submitted_date', 'genus', 'target']
    # logger.debug(df)
    for column in df.columns:
        if "percent" in column:
            count_col = [item for item in df.columns if "count" in item][0]
            # The actual percentage from kraken was off due to exclusion of NaN, recalculating.
            df[column] = 100 * df[count_col] / df.groupby('submitted_date')[count_col].transform('sum')
        if column not in safe:
            if subtype != None and column != subtype:
                del df[column]
    # logger.debug(df)
    return df

