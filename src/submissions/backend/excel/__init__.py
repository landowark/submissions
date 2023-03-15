from pandas import DataFrame
import re


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
    sample_names = get_unique_values_in_df_column(df, column_name="name")
    if 'rerun_regex' in ctx:
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
    else:
        return None
