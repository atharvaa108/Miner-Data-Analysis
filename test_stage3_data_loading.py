# ==========================================
# STAGE 3: Data Loading Test
# File: test_stage3_data_loading.py
# Purpose: Test loading data from Hugging Face URL
# ==========================================

import streamlit as st
import pandas as pd
import duckdb as db

st.set_page_config(
    page_title="Stage 3: Data Loading Test",
    page_icon="📥",
    layout="wide"
)

st.title("📥 Stage 3: Data Loading Test")

url = "https://huggingface.co/datasets/Atharvaaaaaaaaaa/Data/resolve/main/data.parquet"

st.markdown(f"### Testing Data Load from URL")
st.code(url)

st.markdown("---")

# Method 1: DuckDB direct read
st.markdown("#### Method 1: DuckDB Direct Read (Your Current Method)")
with st.spinner("Attempting to load data with DuckDB..."):
    try:
        df = db.read_parquet(url).df()
        st.success(f"✅ Success! Loaded {len(df):,} records")
        st.write(f"Columns: {list(df.columns)}")
        st.write(f"Shape: {df.shape}")
        st.dataframe(df.head())
        
    except Exception as e:
        st.error(f"❌ Failed with DuckDB: {str(e)}")
        st.markdown("**Possible issues:**")
        st.warning("""
        - Network restrictions on Streamlit Cloud
        - DuckDB version compatibility
        - URL access issues
        """)

st.markdown("---")

# Method 2: Pandas read_parquet (Alternative)
st.markdown("#### Method 2: Pandas Direct Read (Alternative)")
with st.spinner("Attempting to load data with Pandas..."):
    try:
        df_pandas = pd.read_parquet(url)
        st.success(f"✅ Success! Loaded {len(df_pandas):,} records")
        st.write(f"Columns: {list(df_pandas.columns)}")
        st.write(f"Shape: {df_pandas.shape}")
        st.dataframe(df_pandas.head())
        
    except Exception as e:
        st.error(f"❌ Failed with Pandas: {str(e)}")

st.markdown("---")

# Method 3: Using requests (Most compatible)
st.markdown("#### Method 3: Using Requests Library (Most Compatible)")
with st.spinner("Attempting to load data with requests..."):
    try:
        import requests
        from io import BytesIO
        
        response = requests.get(url)
        response.raise_for_status()
        df_requests = pd.read_parquet(BytesIO(response.content))
        
        st.success(f"✅ Success! Loaded {len(df_requests):,} records")
        st.write(f"Columns: {list(df_requests.columns)}")
        st.write(f"Shape: {df_requests.shape}")
        st.dataframe(df_requests.head())
        
    except Exception as e:
        st.error(f"❌ Failed with requests: {str(e)}")

st.markdown("---")
st.info("💡 If any method succeeds, use that one in your main app!")