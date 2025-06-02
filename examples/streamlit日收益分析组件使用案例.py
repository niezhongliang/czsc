import sys
sys.path.append("/Users/niez01/Documents/dev/czsc")

import czsc
import streamlit as st
import pandas as pd
import numpy as np

if __name__ == '__main__':
    st.set_page_config(layout="wide")

    df = pd.DataFrame(
        {"dt": pd.date_range("20210101", periods=1000), "ret": [np.random.uniform(-0.1, 0.1) for _ in range(1000)]}
    )

    czsc.show_daily_return(df)

    czsc.show_monthly_return(df, ret_col="ret")
