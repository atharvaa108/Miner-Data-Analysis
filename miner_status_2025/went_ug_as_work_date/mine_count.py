import pandas as pd

df = pd.read_parquet('miner_all_with_sessions_for_went_ug.parquet')

print(df.groupby('mine_id')['mine_id'].value_counts().reset_index())