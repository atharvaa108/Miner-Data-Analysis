import pandas as pd
import duckdb as db
from pathlib import Path

_root = Path(__file__).resolve().parents[1]

file_path = f"{_root}/data/miner_all.parquet"

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
        went_ug,
        last_ug,
        mine_id
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

db.query(query).to_parquet(f'{_root}/went_ug_as_work_date/miner_all_with_sessions_for_went_ug.parquet')

