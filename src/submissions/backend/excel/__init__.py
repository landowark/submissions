
from pandas import DataFrame
import re



def get_unique_values_in_df_column(df: DataFrame, column_name: str) -> list:
    """
    _summary_

    Args:
        df (DataFrame): _description_
        column_name (str): _description_

    Returns:
        list: _description_
    """    
    return sorted(df[column_name].unique())


def drop_reruns_from_df(ctx:dict, df: DataFrame) -> DataFrame:
    """
    Removes semi-duplicates from dataframe after finding sequencing repeats.

    Args:
        settings (dict): settings passed down from click
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
