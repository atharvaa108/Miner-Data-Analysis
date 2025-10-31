# test_stage3_detailed_debug.py
# Purpose: Detailed debugging for data loading issues

import streamlit as st
import sys
import traceback

st.set_page_config(
    page_title="Stage 3: Detailed Data Loading Debug",
    page_icon="🔍",
    layout="wide"
)

st.title("🔍 Stage 3: Detailed Data Loading Debug")
st.markdown("This will help us find EXACTLY where the error occurs")

url = "https://huggingface.co/datasets/Atharvaaaaaaaaaa/Data/resolve/main/data.parquet"

st.markdown(f"**Testing URL:** `{url}`")
st.markdown("---")

# ==========================================
# TEST 1: Check if requests library works
# ==========================================
st.markdown("### Test 1: Can we import requests?")
try:
    import requests
    st.success("✅ requests library imported successfully")
    st.write(f"Version: {requests.__version__}")
except Exception as e:
    st.error(f"❌ Failed to import requests: {str(e)}")
    st.code(traceback.format_exc())
    st.stop()

st.markdown("---")

# ==========================================
# TEST 2: Can we reach the URL?
# ==========================================
st.markdown("### Test 2: Can we reach the URL?")
try:
    st.info("Attempting to connect to Hugging Face...")
    response = requests.head(url, timeout=10)  # Just check headers first
    st.success(f"✅ URL is reachable! Status code: {response.status_code}")
    st.write("**Response Headers:**")
    st.json(dict(response.headers))
except requests.exceptions.Timeout:
    st.error("❌ Connection timed out - Hugging Face is not responding")
    st.stop()
except requests.exceptions.ConnectionError:
    st.error("❌ Connection error - Cannot reach Hugging Face")
    st.warning("This could be a network restriction on Streamlit Cloud")
    st.stop()
except Exception as e:
    st.error(f"❌ Error checking URL: {str(e)}")
    st.code(traceback.format_exc())
    st.stop()

st.markdown("---")

# ==========================================
# TEST 3: Can we download the file?
# ==========================================
st.markdown("### Test 3: Can we download the file?")
try:
    st.info("Attempting to download parquet file...")
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    
    file_size_mb = len(response.content) / (1024 * 1024)
    st.success(f"✅ File downloaded! Size: {file_size_mb:.2f} MB")
    
    # Check content type
    content_type = response.headers.get('Content-Type', 'unknown')
    st.write(f"**Content Type:** {content_type}")
    
except requests.exceptions.Timeout:
    st.error("❌ Download timed out - file might be too large")
    st.stop()
except requests.exceptions.HTTPError as e:
    st.error(f"❌ HTTP Error: {e}")
    st.stop()
except Exception as e:
    st.error(f"❌ Download failed: {str(e)}")
    st.code(traceback.format_exc())
    st.stop()

st.markdown("---")

# ==========================================
# TEST 4: Can we import pandas and pyarrow?
# ==========================================
st.markdown("### Test 4: Can we import pandas and pyarrow?")
try:
    import pandas as pd
    st.success(f"✅ pandas imported (v{pd.__version__})")
except Exception as e:
    st.error(f"❌ Failed to import pandas: {str(e)}")
    st.stop()

try:
    import pyarrow
    st.success(f"✅ pyarrow imported (v{pyarrow.__version__})")
except Exception as e:
    st.error(f"❌ Failed to import pyarrow: {str(e)}")
    st.warning("pyarrow is required for reading parquet files!")
    st.code("Add 'pyarrow' to your requirements.txt")
    st.stop()

st.markdown("---")

# ==========================================
# TEST 5: Can we read the parquet file?
# ==========================================
st.markdown("### Test 5: Can we read the parquet file?")
try:
    from io import BytesIO
    
    st.info("Converting response to BytesIO...")
    parquet_buffer = BytesIO(response.content)
    st.success("✅ BytesIO object created")
    
    st.info("Attempting to read parquet with pandas...")
    df = pd.read_parquet(parquet_buffer)
    
    st.success(f"✅ SUCCESS! Parquet file read successfully!")
    st.balloons()
    
    # Show data info
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Rows", f"{len(df):,}")
    with col2:
        st.metric("Columns", len(df.columns))
    with col3:
        memory_mb = df.memory_usage(deep=True).sum() / (1024 * 1024)
        st.metric("Memory", f"{memory_mb:.2f} MB")
    
    st.markdown("#### Column Names:")
    st.write(list(df.columns))
    
    st.markdown("#### First 5 Rows:")
    st.dataframe(df.head())
    
    st.markdown("#### Data Types:")
    st.dataframe(pd.DataFrame({
        'Column': df.dtypes.index,
        'Type': df.dtypes.values.astype(str)
    }))
    
except ImportError as e:
    st.error(f"❌ Import error: {str(e)}")
    st.warning("Missing dependency!")
    st.code(traceback.format_exc())
except ValueError as e:
    st.error(f"❌ ValueError - File might not be a valid parquet: {str(e)}")
    st.code(traceback.format_exc())
except Exception as e:
    st.error(f"❌ Failed to read parquet: {str(e)}")
    st.error("**Full error trace:**")
    st.code(traceback.format_exc())
    
    # Additional debugging info
    st.markdown("#### Debug Info:")
    st.write(f"Python version: {sys.version}")
    st.write(f"Response content length: {len(response.content)} bytes")
    st.write(f"Response content type: {response.headers.get('Content-Type')}")
    st.stop()

st.markdown("---")

# ==========================================
# TEST 6: Check specific columns we need
# ==========================================
st.markdown("### Test 6: Check required columns")

required_columns = ['miner_id', 'ug_session_id', 'last_ug']
missing_columns = [col for col in required_columns if col not in df.columns]

if missing_columns:
    st.error(f"❌ Missing required columns: {missing_columns}")
    st.warning("Your main app will fail because these columns are expected!")
else:
    st.success(f"✅ All required columns present: {required_columns}")

st.markdown("---")

# ==========================================
# FINAL SUMMARY
# ==========================================
st.markdown("### 🎉 Final Summary")

if len(missing_columns) == 0:
    st.success("""
    ✅ **ALL TESTS PASSED!**
    
    The data loading method works perfectly. You can now use this code in your main app:
    
    ```python
    @st.cache_data(ttl=3600)
    def load_data_from_url():
        import requests
        from io import BytesIO
        import pandas as pd
        
        url = "https://huggingface.co/datasets/Atharvaaaaaaaaaa/Data/resolve/main/data.parquet"
        
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        df = pd.read_parquet(BytesIO(response.content))
        
        return df
    ```
    """)
else:
    st.warning("""
    ⚠️ Data loads but columns don't match expectations.
    Check your data source or adjust column names in the main app.
    """)

st.markdown("---")
st.info("💡 **Next Step:** If all tests passed, move to Stage 4 (DuckDB queries)")