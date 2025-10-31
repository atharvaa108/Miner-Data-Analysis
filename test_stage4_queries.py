# test_stage4_duckdb_queries.py
# THIS IS THE CRITICAL TEST - Your complex SQL queries

import streamlit as st
import pandas as pd
import duckdb as db
import requests
from io import BytesIO
from datetime import time

st.set_page_config(
    page_title="Stage 4: DuckDB Query Test",
    page_icon="🔍",
    layout="wide"
)

st.title("🔍 Stage 4: DuckDB Query Test")
st.markdown("Testing your complex shift analysis queries")
st.markdown("---")

# Load data
@st.cache_data
def load_data():
    url = "https://huggingface.co/datasets/Atharvaaaaaaaaaa/Data/resolve/main/data.parquet"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return pd.read_parquet(BytesIO(response.content))

st.markdown("### Step 1: Load Data")
with st.spinner("Loading data..."):
    try:
        df = load_data()
        st.success(f"✅ Data loaded: {len(df):,} records")
        st.write(f"Columns: {list(df.columns)}")
    except Exception as e:
        st.error(f"❌ Failed: {e}")
        st.stop()

st.markdown("---")

# Create shift table
st.markdown("### Step 2: Create Shift Reference Table")
try:
    shift_data = {
        'shift_id': [1, 2],
        'start_time': ['08:00:00', '20:00:00'],
        'end_time': ['20:00:00', '08:00:00']
    }
    shift_df = pd.DataFrame(shift_data)
    shift_df['start_time'] = pd.to_datetime(shift_df['start_time'], format='%H:%M:%S').dt.time
    shift_df['end_time'] = pd.to_datetime(shift_df['end_time'], format='%H:%M:%S').dt.time
    
    st.success("✅ Shift table created")
    st.dataframe(shift_df)
except Exception as e:
    st.error(f"❌ Failed: {e}")
    st.stop()

st.markdown("---")

# Register tables with DuckDB
st.markdown("### Step 3: Register Tables in DuckDB")
try:
    db.register('df', df)
    db.register('shift_df', shift_df)
    
    # Test basic query
    test = db.query("SELECT COUNT(*) as count FROM df").df()
    st.success(f"✅ DuckDB registration successful. Total records: {test['count'][0]:,}")
except Exception as e:
    st.error(f"❌ Failed: {e}")
    import traceback
    st.code(traceback.format_exc())
    st.stop()

st.markdown("---")

# Test timezone conversion - THIS IS CRITICAL
st.markdown("### Step 4: Test Timezone Conversion (CRITICAL)")
st.warning("⚠️ This is where many deployments fail!")

try:
    # Try your original query with timezone
    timezone_query = """
    SELECT 
        miner_id,
        ug_session_id,
        (MIN(last_ug) AT TIME ZONE 'UTC') AT TIME ZONE 'America/New_York' AS session_start,
        (MAX(last_ug) AT TIME ZONE 'UTC') AT TIME ZONE 'America/New_York' AS session_end
    FROM df
    GROUP BY miner_id, ug_session_id
    LIMIT 5
    """
    
    result = db.query(timezone_query).df()
    st.success("✅ Timezone conversion works! Your original query will work.")
    st.dataframe(result)
    
except Exception as e:
    st.error(f"❌ Timezone conversion FAILED: {e}")
    st.warning("""
    **This is the problem!** DuckDB timezone operations don't work on Streamlit Cloud.
    
    **Solution:** Use pandas for timezone conversion instead of SQL.
    """)
    
    # Show alternative approach
    st.markdown("#### Alternative: Pandas Timezone Conversion")
    try:
        # Convert timezone in pandas
        df_tz = df.copy()
        df_tz['last_ug'] = pd.to_datetime(df_tz['last_ug'])
        df_tz['last_ug_ny'] = df_tz['last_ug'].dt.tz_localize('UTC').dt.tz_convert('America/New_York')
        
        # Re-register
        db.register('df_tz', df_tz)
        
        # Query without timezone conversion
        simple_query = """
        SELECT 
            miner_id,
            ug_session_id,
            MIN(last_ug_ny) AS session_start,
            MAX(last_ug_ny) AS session_end
        FROM df_tz
        GROUP BY miner_id, ug_session_id
        LIMIT 5
        """
        
        result_alt = db.query(simple_query).df()
        st.success("✅ Alternative method works!")
        st.dataframe(result_alt)
        
        st.info("""
        **USE THIS APPROACH:**
        1. Convert timezone in pandas BEFORE DuckDB
        2. Then use simple MIN/MAX in SQL
        """)
        
    except Exception as e2:
        st.error(f"❌ Alternative also failed: {e2}")
        import traceback
        st.code(traceback.format_exc())

st.markdown("---")

# Test generate_series - THIS IS ALSO CRITICAL
st.markdown("### Step 5: Test Generate Series (Minute Breakdown)")

try:
    # Get one sample session
    sample = db.query("""
        SELECT miner_id, ug_session_id, 
               MIN(last_ug) as start, 
               MAX(last_ug) as end
        FROM df
        GROUP BY miner_id, ug_session_id
        LIMIT 1
    """).df()
    
    st.write("Sample session:", sample)
    
    # Test generate_series
    series_query = """
    WITH base AS (
        SELECT 
            miner_id,
            ug_session_id,
            MIN(last_ug) AS session_start,
            MAX(last_ug) AS session_end
        FROM df
        GROUP BY miner_id, ug_session_id
        LIMIT 1
    )
    SELECT 
        COUNT(*) as minute_count
    FROM (
        SELECT
            unnest(
                generate_series(
                    date_trunc('minute', session_start),
                    date_trunc('minute', session_end),
                    INTERVAL '1 minute'
                )
            ) AS minute_ts
        FROM base
    )
    """
    
    result = db.query(series_query).df()
    st.success("✅ Generate series works!")
    st.write(f"Minutes in sample session: {result['minute_count'][0]}")
    
except Exception as e:
    st.error(f"❌ Generate series failed: {e}")
    st.warning("This is needed for shift overlap calculation")
    import traceback
    st.code(traceback.format_exc())

st.markdown("---")

# Test full query (simplified version)
st.markdown("### Step 6: Test Simplified Full Query")

try:
    # Simplified version without timezone (if timezone failed)
    simple_full_query = """
    WITH base AS (
        SELECT
            miner_id,
            ug_session_id,
            MIN(last_ug) AS session_start,
            MAX(last_ug) AS session_end
        FROM df
        GROUP BY miner_id, ug_session_id
        LIMIT 10
    )
    SELECT
        miner_id,
        ug_session_id,
        session_start,
        session_end,
        EXTRACT(EPOCH FROM (session_end - session_start)) / 3600 AS hours_worked
    FROM base
    ORDER BY miner_id, ug_session_id
    """
    
    result = db.query(simple_full_query).df()
    st.success("✅ Basic query structure works!")
    st.dataframe(result)
    
except Exception as e:
    st.error(f"❌ Query failed: {e}")
    import traceback
    st.code(traceback.format_exc())

st.markdown("---")

# Final verdict
st.markdown("### 🎯 Final Verdict")

st.info("""
**Summary:**
- If Step 4 (timezone) passed → Use your original code ✅
- If Step 4 failed → Use pandas timezone conversion instead ⚠️
- If Step 5 (generate_series) failed → May need alternative approach ⚠️
- If Step 6 passed → Your query logic is sound ✅

**Next:** Move to Stage 5 (Visualizations) if queries work!
""")