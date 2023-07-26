'''
Contains functions for generating summary reports
'''
from pandas import DataFrame
import logging
from datetime import date, timedelta
import re
from typing import Tuple
from tools import jinja_template_loading

logger = logging.getLogger(f"submissions.{__name__}")

env = jinja_template_loading()

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
    df2 = df2.rename(columns={"Extraction Kit": 'Plate Count'})
    logger.debug(f"Output daftaframe for xlsx: {df2.columns}")
    df = df.drop('id', axis=1)
    df = df.sort_values(['Submitting Lab', "Submitted Date"])
    return df, df2


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
    
    df = DataFrame.from_records(input)
    # df.to_excel("test.xlsx", engine="openpyxl")
    safe = ['name', 'submitted_date', 'genus', 'target']
    for column in df.columns:
        if "percent" in column:
            count_col = [item for item in df.columns if "count" in item][0]
            # The actual percentage from kraken was off due to exclusion of NaN, recalculating.
            df[column] = 100 * df[count_col] / df.groupby('name')[count_col].transform('sum')
        if column not in safe:
            if subtype != None and column != subtype:
                del df[column]
    # logger.debug(df)
    # move date of sample submitted on same date as previous ahead one.
    df = displace_date(df)
    # ad hoc method to make data labels more accurate.
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
        "kraken_count":"kraken2_read_count_(top_50)",
        "kraken_percent":"kraken2_read_percent_(top_50)"
    })


def displace_date(df:DataFrame) -> DataFrame:
    """
    This function serves to split samples that were submitted on the same date by incrementing dates.
    It will shift the date forward by one day if it is the same day as an existing date in a list.

    Args:
        df (DataFrame): input dataframe composed of control records

    Returns:
        DataFrame: output dataframe with dates incremented.
    """    
    logger.debug(f"Unique items: {df['name'].unique()}")
    # get submitted dates for each control
    dict_list = [dict(name=item, date=df[df.name == item].iloc[0]['submitted_date']) for item in sorted(df['name'].unique())]
    previous_dates = []
    for _, item in enumerate(dict_list):
        df, previous_dates = check_date(df=df, item=item, previous_dates=previous_dates)
    return df

def check_date(df:DataFrame, item:dict, previous_dates:list) -> Tuple[DataFrame, list]:
    """
    Checks if an items date is already present in df and adjusts df accordingly

    Args:
        df (DataFrame): input dataframe
        item (dict): control for checking
        previous_dates (list): list of dates found in previous controls

    Returns:
        Tuple[DataFrame, list]: Output dataframe and appended list of previous dates
    """    
    try:
        check = item['date'] in previous_dates
    except IndexError:
        check = False
    previous_dates.append(item['date'])
    if check:
        logger.debug(f"We found one! Increment date!\n\t{item['date']} to {item['date'] + timedelta(days=1)}")
        # get df locations where name == item name
        mask = df['name'] == item['name']
        # increment date in dataframe
        df.loc[mask, 'submitted_date'] = df.loc[mask, 'submitted_date'].apply(lambda x: x + timedelta(days=1))
        item['date'] += timedelta(days=1)
        passed = False
    else:
        passed = True
    logger.debug(f"\n\tCurrent date: {item['date']}\n\tPrevious dates:{previous_dates}")
    logger.debug(f"DF: {type(df)}, previous_dates: {type(previous_dates)}")
    # if run didn't lead to changed date, return values
    if passed:
        logger.debug(f"Date check passed, returning.")
        return df, previous_dates
    # if date was changed, rerun with new date
    else:
        logger.warning(f"Date check failed, running recursion")
        df, previous_dates = check_date(df, item, previous_dates)
        return df, previous_dates
                

def get_unique_values_in_df_column(df: DataFrame, column_name: str) -> list:
    """
    get all unique values in a dataframe column by name

    Args:
        df (DataFrame): input dataframe
        column_name (str): name of column of interest

    Returns:
        list: sorted list of unique values
    """    
    return sorted(df[column_name].unique())


def drop_reruns_from_df(ctx:dict, df: DataFrame) -> DataFrame:
    """
    Removes semi-duplicates from dataframe after finding sequencing repeats.

    Args:
        settings (dict): settings passed from gui
        df (DataFrame): initial dataframe

    Returns:
        DataFrame: dataframe with originals removed in favour of repeats.
    """    
    if 'rerun_regex' in ctx:
        sample_names = get_unique_values_in_df_column(df, column_name="name")
        # logger.debug(f"Compiling regex from: {settings['rerun_regex']}")
        rerun_regex = re.compile(fr"{ctx['rerun_regex']}")
        for sample in sample_names:
            # logger.debug(f'Running search on {sample}')
            if rerun_regex.search(sample):
                # logger.debug(f'Match on {sample}')
                first_run = re.sub(rerun_regex, "", sample)
                # logger.debug(f"First run: {first_run}")
                df = df.drop(df[df.name == first_run].index)
    return df
    


def make_hitpicks(input:list) -> DataFrame:
    return DataFrame.from_records(input)