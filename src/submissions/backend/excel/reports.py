from pandas import DataFrame
import numpy as np

def make_report_xlsx(records:list[dict]) -> DataFrame:
    df = DataFrame.from_records(records)
    df = df.sort_values("Submitting Lab")
    # table = df.pivot_table(values="Cost", index=["Submitting Lab", "Extraction Kit"], columns=["Cost", "Sample Count"], aggfunc={'Cost':np.sum,'Sample Count':np.sum})
    df2 = df.groupby(["Submitting Lab", "Extraction Kit"]).agg({'Cost': ['sum', 'count'], 'Sample Count':['sum']})
    # df2['Cost'] = df2['Cost'].map('${:,.2f}'.format)
    print(df2.columns)
    # df2['Cost']['sum'] = df2['Cost']['sum'].apply('${:,.2f}'.format)
    df2.iloc[:, (df2.columns.get_level_values(1)=='sum') & (df2.columns.get_level_values(0)=='Cost')] = df2.iloc[:, (df2.columns.get_level_values(1)=='sum') & (df2.columns.get_level_values(0)=='Cost')].applymap('${:,.2f}'.format)
    return df2