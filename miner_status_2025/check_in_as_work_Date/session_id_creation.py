import pandas as pd
import duckdb as db


file_path = "miner_all.parquet"  # This file is created by single_miner.py

df = pd.read_parquet(file_path)


query = '''
WITH STEP1 AS (
    SELECT
        ROW_NUMBER() OVER () AS rid,
        miner_id,
        g_session,
        work_day,
        work_month,
        z,
        last_ag,
        last_ug
    FROM df
),
STEP2 AS (
    SELECT
        *,
        CASE
            WHEN z = 0
                 AND LAG(z) OVER (
                        PARTITION BY miner_id, work_day, work_month
                        ORDER BY rid
                 ) = 1
            THEN 1
            ELSE 0
        END AS new_session
    FROM STEP1
),
STEP3 AS (
    SELECT
        *,
        SUM(new_session) OVER (
            PARTITION BY miner_id, work_day, work_month
            ORDER BY rid
        ) AS session_id
    FROM STEP2
)
SELECT *
FROM STEP3
ORDER BY miner_id, work_day, work_month, rid;

'''
print(db.query(query))

#################### Download the dataframe with sessions to parquet ####################

# db.query(query).to_parquet('miner_all_with_sessions.parquet')