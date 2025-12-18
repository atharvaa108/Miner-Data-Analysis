################### Analyzing Miner 300 UG hours by session id ####################


import pandas as pd
from pathlib import Path
import duckdb as db


_root = Path(__file__).resolve().parent

file_path = f"{_root}/miner_all_with_sessions_for_went_ug.parquet"

df = pd.read_parquet(file_path)
df.drop(['work_day','work_month'],axis=1,inplace=True)
print(df.head())

miner = 390

query = f'''
SELECT 
    miner_id,
    EXTRACT(DAY FROM went_ug) AS work_day,
    EXTRACT(MONTH FROM went_ug) AS work_month,
    session_id,
    (
        EXTRACT(HOUR FROM (
            (CAST(MAX(last_ug) AS TIMESTAMP) AT TIME ZONE 'UTC') 
                AT TIME ZONE 'America/New_York'
            -
            (CAST(MIN(last_ug) AS TIMESTAMP) AT TIME ZONE 'UTC') 
                AT TIME ZONE 'America/New_York'
        )))
        +
        (
            EXTRACT(MINUTE FROM (
                (CAST(MAX(last_ug) AS TIMESTAMP) AT TIME ZONE 'UTC') 
                    AT TIME ZONE 'America/New_York'
                -
                (CAST(MIN(last_ug) AS TIMESTAMP) AT TIME ZONE 'UTC') 
                    AT TIME ZONE 'America/New_York'
            )) / 100.0
        )
    AS ug_hours
FROM df
WHERE z = 0 AND mine_id = 1
GROUP BY miner_id,work_day,work_month,session_id
ORDER BY miner_id,work_day,work_month,session_id

'''

print(db.query(query).df()['ug_hours'].describe())
print(db.query(query).df().groupby(['miner_id','work_day','work_month']).agg({'ug_hours':'sum'})['ug_hours'].describe())

db.query(query).df().to_parquet('analysis_data_all_miners.parquet')




"""
At First we drop the check_in as work_Day and work_month. 
Then we consider went_ug as work_day and work_month and calculated the UG hours by considering the

"""

