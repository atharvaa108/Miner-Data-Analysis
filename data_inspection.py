import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import duckdb
import gdown
import os

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def format_hours(hours):
    """Convert decimal hours to 'Xh Ym' format"""
    if pd.isna(hours):
        return "N/A"
    h = int(hours)
    m = int((hours - h) * 60)
    return f"{h}h {m}m"

def format_hours_short(hours):
    """Convert decimal hours to 'X:YY' format"""
    if pd.isna(hours):
        return "N/A"
    h = int(hours)
    m = int((hours - h) * 60)
    return f"{h}:{m:02d}"

# ============================================================================
# PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="Miner Session Analysis",
    page_icon="⛏️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .main {
        padding: 0rem 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

# ============================================================================
# DATA LOADING - OPTIMIZED
# ============================================================================

@st.cache_resource
def get_duckdb_connection():
    """Create a persistent DuckDB connection"""
    return duckdb.connect()

@st.cache_data(ttl=3600, show_spinner=False)
def download_file():
    """Download file from Google Drive if needed"""
    output = "data.parquet"
    
    if not os.path.exists(output):
        try:
            file_id = "1z4eiH8unaggA3hgQvTdGzHOf5iutd0A-"
            url = f"https://drive.google.com/uc?export=download&id={file_id}"
            gdown.download(url, output, quiet=False)
            return output
        except Exception as e:
            st.error(f"Download failed: {str(e)}")
            return None
    return output

def load_data_lazy():
    """Load parquet file path only - no data in memory"""
    output = download_file()
    if output and os.path.exists(output):
        return output
    return None

# ============================================================================
# DATABASE QUERIES - OPTIMIZED TO WORK DIRECTLY ON FILE
# ============================================================================

@st.cache_data(ttl=1800)
def get_session_stats(parquet_path):
    """Calculate session statistics directly from parquet"""
    conn = get_duckdb_connection()
    query = f'''
    WITH session_stats AS (
        SELECT
            miner_id,
            ug_session_id,
            MIN(shift_id) AS min_shift_id,
            MAX(shift_id) AS max_shift_id,
            EXTRACT(EPOCH FROM (MAX(last_ug) - MIN(last_ug))) / 3600 AS time_diff_hours
        FROM read_parquet('{parquet_path}')
        GROUP BY miner_id, ug_session_id
    )
    SELECT
        COUNT(CASE WHEN min_shift_id = max_shift_id AND time_diff_hours < 12 THEN 1 END) AS case1,
        COUNT(CASE WHEN min_shift_id = max_shift_id AND time_diff_hours > 12 THEN 1 END) AS case2,
        COUNT(CASE WHEN min_shift_id != max_shift_id THEN 1 END) AS case3
    FROM session_stats
    '''
    return conn.execute(query).df()

@st.cache_data(ttl=1800)
def get_per_miner_stats(parquet_path):
    """Get statistics per miner"""
    conn = get_duckdb_connection()
    query = f'''
    WITH session_stats AS (
        SELECT
            miner_id,
            ug_session_id,
            MIN(shift_id) AS min_shift_id,
            MAX(shift_id) AS max_shift_id,
            (MAX(shift_id) - MIN(shift_id) + 1) AS shifts_spanned,
            EXTRACT(EPOCH FROM (MAX(last_ug) - MIN(last_ug))) / 3600 AS time_diff_hours
        FROM read_parquet('{parquet_path}')
        GROUP BY miner_id, ug_session_id
    )
    SELECT
        miner_id,
        COUNT(*) AS total_sessions,
        AVG(time_diff_hours) AS avg_hours,
        MAX(time_diff_hours) AS max_hours,
        MIN(time_diff_hours) AS min_hours,
        AVG(shifts_spanned) AS avg_shifts_spanned,
        MAX(shifts_spanned) AS max_shifts_spanned
    FROM session_stats
    GROUP BY miner_id
    ORDER BY miner_id
    '''
    return conn.execute(query).df()

@st.cache_data(ttl=1800)
def get_miner_details(parquet_path, miner_id):
    """Get detailed session info for a miner"""
    conn = get_duckdb_connection()
    query = f'''
    SELECT
        miner_id,
        ug_session_id,
        MIN(shift_id) AS min_shift_id,
        MAX(shift_id) AS max_shift_id,
        MIN(last_ug) AS work_start,
        MAX(last_ug) AS work_end,
        EXTRACT(EPOCH FROM (MAX(last_ug) - MIN(last_ug))) / 3600 AS time_diff_hours
    FROM read_parquet('{parquet_path}')
    WHERE miner_id = {miner_id}
    GROUP BY miner_id, ug_session_id
    ORDER BY work_start DESC
    '''
    return conn.execute(query).df()

@st.cache_data(ttl=1800)
def get_shift_span_distribution(parquet_path, miner_id=None):
    """Get distribution of shifts spanned"""
    conn = get_duckdb_connection()
    where_clause = f"WHERE miner_id = {miner_id}" if miner_id else ""
    query = f'''
    WITH session_stats AS (
        SELECT
            miner_id,
            ug_session_id,
            (MAX(shift_id) - MIN(shift_id) + 1) AS shifts_spanned
        FROM read_parquet('{parquet_path}')
        {where_clause}
        GROUP BY miner_id, ug_session_id
    )
    SELECT
        shifts_spanned,
        COUNT(*) AS session_count
    FROM session_stats
    GROUP BY shifts_spanned
    ORDER BY shifts_spanned
    '''
    return conn.execute(query).df()

@st.cache_data(ttl=1800)
def get_hourly_distribution(parquet_path):
    """Get distribution of session durations"""
    conn = get_duckdb_connection()
    query = f'''
    WITH session_stats AS (
        SELECT
            EXTRACT(EPOCH FROM (MAX(last_ug) - MIN(last_ug))) / 3600 AS time_diff_hours
        FROM read_parquet('{parquet_path}')
        GROUP BY miner_id, ug_session_id
    )
    SELECT
        FLOOR(time_diff_hours) AS hour_bucket,
        COUNT(*) AS session_count
    FROM session_stats
    WHERE time_diff_hours <= 24
    GROUP BY hour_bucket
    ORDER BY hour_bucket
    '''
    return conn.execute(query).df()

@st.cache_data(ttl=1800)
def get_row_count(parquet_path):
    """Get total row count from parquet"""
    conn = get_duckdb_connection()
    query = f"SELECT COUNT(*) as count FROM read_parquet('{parquet_path}')"
    return conn.execute(query).df()['count'][0]

@st.cache_data(ttl=1800)
def get_miner_ids(parquet_path):
    """Get list of unique miner IDs"""
    conn = get_duckdb_connection()
    query = f"SELECT DISTINCT miner_id FROM read_parquet('{parquet_path}') ORDER BY miner_id"
    return conn.execute(query).df()['miner_id'].tolist()

# ============================================================================
# VISUALIZATION FUNCTIONS
# ============================================================================

def show_overview_dashboard(parquet_path, stats):
    """Display the main overview dashboard"""
    st.header("📈 Session Overview")
    
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    
    total = stats['case1'] + stats['case2'] + stats['case3']
    
    with col1:
        st.metric("Total Sessions", f"{total:,}")
    
    with col2:
        st.metric("Normal Shifts (<12h)", f"{stats['case1']:,}",
                 delta=f"{stats['case1']/total*100:.1f}%")
    
    with col3:
        st.metric("Extended Shifts (>12h)", f"{stats['case2']:,}",
                 delta=f"{stats['case2']/total*100:.1f}%", delta_color="inverse")
    
    with col4:
        st.metric("Multi-Shift Sessions", f"{stats['case3']:,}",
                 delta=f"{stats['case3']/total*100:.1f}%")
    
    st.markdown("---")
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Session Distribution")
        pie_data = pd.DataFrame({
            'Category': ['Same Shift (<12h)', 'Same Shift (>12h)', 'Different Shifts'],
            'Count': [stats['case1'], stats['case2'], stats['case3']]
        })
        
        fig = px.pie(pie_data, values='Count', names='Category',
                    color='Category',
                    color_discrete_map={
                        'Same Shift (<12h)': '#10b981',
                        'Same Shift (>12h)': '#f59e0b',
                        'Different Shifts': '#3b82f6'
                    }, hole=0.4)
        fig.update_traces(textposition='inside', textinfo='percent+label')
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("📈 Session Counts by Category")
        bar_data = pd.DataFrame({
            'Category': ['Same Shift\n(<12h)', 'Same Shift\n(>12h)', 'Different\nShifts'],
            'Count': [stats['case1'], stats['case2'], stats['case3']]
        })
        
        fig = px.bar(bar_data, x='Category', y='Count',
                    color='Category',
                    color_discrete_map={
                        'Same Shift\n(<12h)': '#10b981',
                        'Same Shift\n(>12h)': '#f59e0b',
                        'Different\nShifts': '#3b82f6'
                    }, text='Count')
        fig.update_traces(texttemplate='%{text:,}', textposition='outside')
        fig.update_layout(height=400, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    
    # Duration distribution
    st.markdown("---")
    st.subheader("⏱️ Session Duration Distribution")
    
    duration_df = get_hourly_distribution(parquet_path)
    fig = px.bar(duration_df, x='hour_bucket', y='session_count',
                labels={'hour_bucket': 'Session Duration (hours)', 
                       'session_count': 'Number of Sessions'},
                color='session_count',
                color_continuous_scale='Viridis')
    fig.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

def show_per_miner_analysis(parquet_path):
    """Display per miner analysis"""
    st.header("👤 Per Miner Analysis")
    
    miner_stats_df = get_per_miner_stats(parquet_path)
    miner_ids = get_miner_ids(parquet_path)
    selected_miner = st.selectbox("Select Miner ID", miner_ids, index=0)
    
    if selected_miner:
        miner_stats = miner_stats_df[miner_stats_df['miner_id'] == selected_miner].iloc[0]
        
        # Metrics
        st.subheader(f"📊 Statistics for Miner {selected_miner}")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Sessions", f"{int(miner_stats['total_sessions']):,}")
        
        with col2:
            st.metric("Avg Working Hours", format_hours(miner_stats['avg_hours']))
        
        with col3:
            st.metric("Max Working Hours", format_hours(miner_stats['max_hours']))
        
        with col4:
            st.metric("Max Shifts Spanned", f"{int(miner_stats['max_shifts_spanned'])}")
        
        st.markdown("---")
        
        # Charts
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Shifts Spanned per Session")
            shift_df = get_shift_span_distribution(parquet_path, selected_miner)
            
            fig = px.bar(shift_df, x='shifts_spanned', y='session_count',
                        labels={'shifts_spanned': 'Shifts Spanned', 
                               'session_count': 'Count'},
                        color='session_count',
                        color_continuous_scale='Blues',
                        text='session_count')
            fig.update_traces(texttemplate='%{text}', textposition='outside')
            fig.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("⏱️ Working Hours Distribution")
            miner_details = get_miner_details(parquet_path, selected_miner)
            
            fig = px.histogram(miner_details, x='time_diff_hours', nbins=20,
                             labels={'time_diff_hours': 'Hours'},
                             color_discrete_sequence=['#3b82f6'])
            fig.update_layout(height=400, showlegend=False, bargap=0.1)
            st.plotly_chart(fig, use_container_width=True)
        
        # Detail table
        st.markdown("---")
        st.subheader("📋 Detailed Session Records")
        
        display_df = miner_details.copy()
        display_df['work_start'] = pd.to_datetime(display_df['work_start']).dt.strftime('%Y-%m-%d %H:%M:%S')
        display_df['work_end'] = pd.to_datetime(display_df['work_end']).dt.strftime('%Y-%m-%d %H:%M:%S')
        display_df['duration'] = display_df['time_diff_hours'].apply(format_hours_short)
        display_df['shifts_spanned'] = (display_df['max_shift_id'] - display_df['min_shift_id'] + 1).astype(int)
        
        display_df = display_df[['ug_session_id', 'min_shift_id', 'max_shift_id', 
                                 'shifts_spanned', 'work_start', 'work_end', 'duration']]
        
        st.dataframe(display_df, use_container_width=True, height=400)
        
        # Download
        csv = display_df.to_csv(index=False)
        st.download_button("📥 Download CSV", csv, 
                          f"miner_{selected_miner}_sessions.csv", "text/csv")

def show_shift_span_analysis(parquet_path):
    """Display shift span analysis"""
    st.header("🔄 Shift Span Analysis")
    
    st.info("📊 This view shows how many shifts miners span during sessions")
    
    shift_df = get_shift_span_distribution(parquet_path)
    miner_stats_df = get_per_miner_stats(parquet_path)
    
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    
    total = shift_df['session_count'].sum()
    single = shift_df[shift_df['shifts_spanned'] == 1]['session_count'].sum()
    multi = shift_df[shift_df['shifts_spanned'] > 1]['session_count'].sum()
    max_span = shift_df['shifts_spanned'].max()
    
    with col1:
        st.metric("Total Sessions", f"{total:,}")
    
    with col2:
        st.metric("Single Shift", f"{single:,}", delta=f"{single/total*100:.1f}%")
    
    with col3:
        st.metric("Multi-Shift", f"{multi:,}", delta=f"{multi/total*100:.1f}%")
    
    with col4:
        st.metric("Max Shifts Spanned", f"{int(max_span)}")
    
    st.markdown("---")
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Overall Shift Span Distribution")
        
        fig = px.bar(shift_df, x='shifts_spanned', y='session_count',
                    labels={'shifts_spanned': 'Shifts Spanned', 
                           'session_count': 'Count'},
                    color='session_count',
                    color_continuous_scale='Viridis',
                    text='session_count')
        fig.update_traces(texttemplate='%{text:,}', textposition='outside')
        fig.update_layout(height=400, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("👥 Top 10 Miners by Avg Shifts Spanned")
        
        top10 = miner_stats_df.nlargest(10, 'avg_shifts_spanned')
        
        fig = px.bar(top10, x='miner_id', y='avg_shifts_spanned',
                    labels={'miner_id': 'Miner ID', 
                           'avg_shifts_spanned': 'Avg Shifts'},
                    color='avg_shifts_spanned',
                    color_continuous_scale='Reds',
                    text='avg_shifts_spanned')
        fig.update_traces(texttemplate='%{text:.2f}', textposition='outside')
        fig.update_layout(height=400, showlegend=False)
        fig.update_xaxes(type='category')
        st.plotly_chart(fig, use_container_width=True)
    
    # Table
    st.markdown("---")
    st.subheader("📋 Per Miner Statistics")
    
    display_stats = miner_stats_df.copy()
    display_stats['Avg Hours'] = display_stats['avg_hours'].apply(format_hours_short)
    display_stats['Max Hours'] = display_stats['max_hours'].apply(format_hours_short)
    display_stats['Min Hours'] = display_stats['min_hours'].apply(format_hours_short)
    
    display_stats = display_stats[['miner_id', 'total_sessions', 'Avg Hours', 
                                   'Max Hours', 'Min Hours', 'avg_shifts_spanned', 
                                   'max_shifts_spanned']]
    
    display_stats.columns = ['Miner ID', 'Total Sessions', 'Avg Hours', 
                            'Max Hours', 'Min Hours', 'Avg Shifts Spanned', 
                            'Max Shifts Spanned']
    
    st.dataframe(display_stats, use_container_width=True, height=400)

# ============================================================================
# MAIN APP
# ============================================================================

def main():
    st.title("⛏️ Underground Mining Session Analysis Dashboard")
    st.markdown("---")
    
    # Sidebar
    with st.sidebar:
        st.header("📊 Configuration")
        st.info("📁 Data source: Google Drive")
        
        st.markdown("---")
        st.subheader("🎨 Visualization Options")
        viz_type = st.selectbox(
            "Select Analysis View",
            ["Overview Dashboard", "Per Miner Analysis", "Shift Span Analysis"]
        )
        
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.cache_resource.clear()
            st.rerun()
        
        st.markdown("---")
        st.markdown("### About")
        st.info("""
        **Session Categories:**
        - Case 1: Same shift, <12 hours
        - Case 2: Same shift, >12 hours  
        - Case 3: Different shifts
        """)
    
    # Load data path (not the full data)
    with st.spinner("⏳ Loading data from Google Drive..."):
        parquet_path = load_data_lazy()
    
    if parquet_path is None:
        st.error("⚠️ Failed to load data")
        st.info("""
        **Troubleshooting:**
        1. Check internet connection
        2. Verify Google Drive file is public
        3. Try refreshing the page
        """)
        st.stop()
    
    # Get row count without loading full data
    row_count = get_row_count(parquet_path)
    st.success(f"✅ Loaded {row_count:,} rows")
    
    # Calculate stats
    with st.spinner("Calculating statistics..."):
        stats_df = get_session_stats(parquet_path)
        stats = stats_df.iloc[0]
    
    # Show selected view
    if viz_type == "Overview Dashboard":
        show_overview_dashboard(parquet_path, stats)
    elif viz_type == "Per Miner Analysis":
        show_per_miner_analysis(parquet_path)
    elif viz_type == "Shift Span Analysis":
        show_shift_span_analysis(parquet_path)

if __name__ == "__main__":
    main()