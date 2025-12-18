import pandas as pd
import duckdb as db
from datasets import load_dataset

# Load the dataset from Hugging Face
raw_df = load_dataset("Atharvaaaaaaaaaa/miner_status_2025",data_files='miner_status_oct-nov.parquet')

# Access data
df = raw_df['train'].to_pandas() # Shows splits like 'train'
print(df.head())


#########################################################################################################
##################  Options If you want a Single miner Data OR the data of all miners  ##################
#########################################################################################################

vars = ['Single Miner', 'All Miners']
print()
option = input(f'Please select the following (1 or 2): {1}. {vars[0]} {2}. {vars[1]} : ')
if option == str(vars.index(f'{vars[0]}') + 1):

    while True:
        op = eval(input('Which miner? : '))
        if isinstance(op,int) and (op in df['miner_id'].unique()):
            miner = op
            single_miner_data = df[df['miner_id'] == miner].loc[:,['miner_id','z','mine_id','g_session','check_in','last_ag','last_ug','went_ug','went_ag','ug_session_time']]
            single_miner_data['work_day'] = pd.to_datetime(single_miner_data['check_in']).dt.day
            single_miner_data['work_month'] = pd.to_datetime(single_miner_data['check_in']).dt.month

            #########################################################################################################
            ##############################  Download the Dataframe in Parquet  ######################################
            #########################################################################################################

            # Convert the dataframe to CSV format
            #single_miner_data.to_csv(f'miner_{miner}.csv',index=False)
            #print(f'Created a CSV file for miner {miner} Successfully🚀')

            break
        else:
            print('Please enter a valid miner id!')
        

else:

    all_miner_data =  df.loc[:,['miner_id','z','mine_id','g_session','check_in','last_ag','last_ug','went_ug','went_ag','ug_session_time']]
    all_miner_data['work_day'] = pd.to_datetime(all_miner_data['check_in']).dt.day
    all_miner_data['work_month'] = pd.to_datetime(all_miner_data['check_in']).dt.month

    bad_miners = [ 48 , 563 , 45 , 420 , 456 , 110 , 525 , 522 , 175,  324 , 488 , 927 , 931 , 300 , 210 , 424  ,479 , 264 , 855, 1515 ,1474 ,1288 ,1195 ,1178 , 213, 1230, 1406, 1055,
                1559, 1445 ,1226 ,1108 ,1174]
    all_miners_excluding_bad_miners = all_miner_data[~all_miner_data['miner_id'].isin(bad_miners)]

    #########################################################################################################
    ##############################  Download the Dataframe in Parquet  ######################################
    #########################################################################################################

    # Convert the dataframe to CSV format
    #all_miners_excluding_bad_miners.to_parquet('miner_all.parquet',index=False) 
    #print('Created a parquet file for all miners Successfully🚀')



    """
        This file will give you either one of two files
            1. miner{miner_you_selected}.csv
            2. miner_all.parquet

        We have excluded bad miners from the dataframe in case of miner_all.parquet.
        Bad miners are the miners whose g_session goes above 10 (worse-to-worse case scenario)

        
    """

