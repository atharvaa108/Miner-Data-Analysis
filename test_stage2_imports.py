# ==========================================
# STAGE 2: Import Packages Test
# File: test_stage2_imports.py
# Purpose: Verify all required packages can be imported
# ==========================================

import streamlit as st

st.set_page_config(
    page_title="Stage 2: Package Import Test",
    page_icon="📦",
    layout="wide"
)

st.title("📦 Stage 2: Package Import Test")

import sys

# Test each import individually
packages_status = {}

st.markdown("### Testing Package Imports...")

# Test pandas
try:
    import pandas as pd
    packages_status['pandas'] = f"✅ Success (v{pd.__version__})"
except Exception as e:
    packages_status['pandas'] = f"❌ Failed: {str(e)}"

# Test duckdb
try:
    import duckdb as db
    packages_status['duckdb'] = f"✅ Success (v{db.__version__})"
except Exception as e:
    packages_status['duckdb'] = f"❌ Failed: {str(e)}"

# Test plotly
try:
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    packages_status['plotly'] = f"✅ Success"
except Exception as e:
    packages_status['plotly'] = f"❌ Failed: {str(e)}"

# Test datetime
try:
    from datetime import time
    packages_status['datetime'] = "✅ Success"
except Exception as e:
    packages_status['datetime'] = f"❌ Failed: {str(e)}"

# Display results
st.markdown("### Results:")
for package, status in packages_status.items():
    if "✅" in status:
        st.success(f"**{package}**: {status}")
    else:
        st.error(f"**{package}**: {status}")

# Summary
all_passed = all("✅" in status for status in packages_status.values())

st.markdown("---")
if all_passed:
    st.success("✅ All packages imported successfully! Move to Stage 3: Data loading")
else:
    st.error("❌ Some packages failed to import. Check requirements.txt")
    st.info("Make sure your requirements.txt contains:\n\n```\nstreamlit\npandas\nduckdb\nplotly\n```")
