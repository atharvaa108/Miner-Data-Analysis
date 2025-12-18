################### Analyzing Miner 300 UG hours by session id ####################


import pandas as pd
from pathlib import Path
import duckdb as db


file_path = "miner_all_with_sessions.parquet"

df = pd.read_parquet(file_path)
print(df.head())

query = '''
SELECT 
    miner_id,
    work_day,
    work_month,
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
WHERE z = 0
GROUP BY miner_id,work_day,work_month,session_id
ORDER BY miner_id,work_day,work_month,session_id

'''

print(db.query(query))

#################### Download the dataframe to parquet ####################

#db.query(query).df().to_parquet('all_miners_ug_hours_with_sessions.parquet')


