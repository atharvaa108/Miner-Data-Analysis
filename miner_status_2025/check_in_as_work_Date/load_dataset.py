from datasets import load_dataset

raw_df = load_dataset("Atharvaaaaaaaaaa/miner_status_2025",data_files='miner_status_oct-nov.parquet')

# Access data
df = raw_df['train'].to_pandas() # Shows splits like 'train'
print(df.head())
