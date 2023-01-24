import pandas as pd
from pandas import DataFrame
import numpy as np
from backend.db import models
import json
import logging

logger = logging.getLogger(f"submissions.{__name__}")

def make_report_xlsx(records:list[dict]) -> DataFrame:
    df = DataFrame.from_records(records)
    df = df.sort_values("Submitting Lab")
    # table = df.pivot_table(values="Cost", index=["Submitting Lab", "Extraction Kit"], columns=["Cost", "Sample Count"], aggfunc={'Cost':np.sum,'Sample Count':np.sum})
    df2 = df.groupby(["Submitting Lab", "Extraction Kit"]).agg({'Cost': ['sum', 'count'], 'Sample Count':['sum']})
    # df2['Cost'] = df2['Cost'].map('${:,.2f}'.format)
    logger.debug(df2.columns)
    # df2['Cost']['sum'] = df2['Cost']['sum'].apply('${:,.2f}'.format)
    df2.iloc[:, (df2.columns.get_level_values(1)=='sum') & (df2.columns.get_level_values(0)=='Cost')] = df2.iloc[:, (df2.columns.get_level_values(1)=='sum') & (df2.columns.get_level_values(0)=='Cost')].applymap('${:,.2f}'.format)
    return df2


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

def convert_control_by_mode(ctx:dict, control:models.Control, mode:str):
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
    df = DataFrame.from_records(input)
    safe = ['name', 'submitted_date', 'genus', 'target']
    logger.debug(df)
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
