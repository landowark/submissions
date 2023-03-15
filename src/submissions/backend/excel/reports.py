
from pandas import DataFrame
# from backend.db import models
import logging
from jinja2 import Environment, FileSystemLoader
from datetime import date, timedelta
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
    return df2


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
        logger.debug(f"Row {ii}: {row}")
        lab = row[0][0]
        logger.debug(type(row))
        logger.debug(f"Old lab: {old_lab}, Current lab: {lab}")
        logger.debug(f"Name: {row[0][1]}")
        data = [item for item in row[1]]
        kit = dict(name=row[0][1], cost=data[1], plate_count=int(data[0]), sample_count=int(data[2]))
        # if this is the same lab as before add together
        if lab == old_lab:
            output[-1]['kits'].append(kit)
            output[-1]['total_cost'] += kit['cost']
            output[-1]['total_samples'] += kit['sample_count']
            output[-1]['total_plates'] += kit['plate_count']
        # if not the same lab, make a new one
        else:
            adder = dict(lab=lab, kits=[kit], total_cost=kit['cost'], total_samples=kit['sample_count'], total_plates=kit['plate_count'])
            output.append(adder)
        old_lab = lab
    logger.debug(output)
    dicto = {'start_date':start_date, 'end_date':end_date, 'labs':output}#, "table":table}
    temp = env.get_template('summary_report.html')
    html = temp.render(input=dicto)
    return html


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
    # copy = input
    # for item in copy:
    #     item['submitted_date'] = item['submitted_date'].strftime("%Y-%m-%d")
    # with open("controls.json", "w") as f:
    #     f.write(json.dumps(copy))
    # for item in input:
    #     logger.debug(item.keys())
    df = DataFrame.from_records(input)
    df.to_excel("test.xlsx", engine="openpyxl")
    safe = ['name', 'submitted_date', 'genus', 'target']
    # logger.debug(df)
    for column in df.columns:
        if "percent" in column:
            count_col = [item for item in df.columns if "count" in item][0]
            # The actual percentage from kraken was off due to exclusion of NaN, recalculating.
            # df[column] = 100 * df[count_col] / df.groupby('submitted_date')[count_col].transform('sum')
            df[column] = 100 * df[count_col] / df.groupby('name')[count_col].transform('sum')
        if column not in safe:
            if subtype != None and column != subtype:
                del df[column]
    # logger.debug(df)
    # df.sort_values('submitted_date').to_excel("controls.xlsx", engine="openpyxl")
    df = displace_date(df)
    df.sort_values('submitted_date').to_excel("controls.xlsx", engine="openpyxl")
    df = df_column_renamer(df=df)
    return df


def df_column_renamer(df:DataFrame) -> DataFrame:
    """
    Ad hoc function I created to clarify some fields

    Args:
        df (DataFrame): input dataframe

    Returns:
        DataFrame: dataframe with 'clarified' column names
    """  
    df = df[df.columns.drop(list(df.filter(regex='_hashes')))]  
    return df.rename(columns = {
        "contains_ratio":"contains_shared_hashes_ratio",
        "matches_ratio":"matches_shared_hashes_ratio",
        "kraken_count":"kraken2_read_count",
        "kraken_percent":"kraken2_read_percent"
    })


def displace_date(df:DataFrame) -> DataFrame:
    """
    This function serves to split samples that were submitted on the same date by incrementing dates.

    Args:
        df (DataFrame): input dataframe composed of control records

    Returns:
        DataFrame: output dataframe with dates incremented.
    """    
    # dict_list = []
    # for item in df['name'].unique():
    #     dict_list.append(dict(name=item, date=df[df.name == item].iloc[0]['submitted_date']))
    logger.debug(f"Unique items: {df['name'].unique()}")
    # logger.debug(df.to_string())
    # the assumption is that closest names will have closest dates...
    dict_list = [dict(name=item, date=df[df.name == item].iloc[0]['submitted_date']) for item in sorted(df['name'].unique())]
    for ii, item in enumerate(dict_list):
        # if ii > 0:
        try:
            check = item['date'] == dict_list[ii-1]['date']
        except IndexError:
            check = False
        if check:
            logger.debug(f"We found one! Increment date!\n{item['date'] - timedelta(days=1)}")
            mask = df['name'] == item['name']
            # logger.debug(f"We will increment dates in: {df.loc[mask, 'submitted_date']}")
            df.loc[mask, 'submitted_date'] = df.loc[mask, 'submitted_date'].apply(lambda x: x + timedelta(days=1))
            # logger.debug(f"Do these look incremented: {df.loc[mask, 'submitted_date']}")
    return df
                
