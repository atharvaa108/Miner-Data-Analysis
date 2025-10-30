# ==========================================
# STAGE 1: Basic Streamlit Test
# File: test_stage1_basic.py
# Purpose: Verify Streamlit deployment works
# ==========================================

import streamlit as st

st.set_page_config(
    page_title="Stage 1: Basic Test",
    page_icon="✅",
    layout="wide"
)

st.title("✅ Stage 1: Basic Streamlit Test")
st.success("If you see this, Streamlit deployment is working!")

st.markdown("---")

st.markdown("### System Info")
import sys
st.write(f"Python version: {sys.version}")

st.markdown("### Next Steps")
st.info("✅ Stage 1 passed! Move to Stage 2: Import packages")
