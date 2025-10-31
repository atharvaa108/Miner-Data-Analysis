import streamlit as st
import pandas as pd
import duckdb as db
from datetime import time
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import gc

# Page configuration
st.set_page_config(
    page_title="Miner Shift Productivity Dashboard",
    page_icon="⛏️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better aesthetics with dark mode support
st.markdown("""
    <style>
    [data-testid="stMetric"] {
        background-color: var(--background-color);
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border: 1px solid rgba(128, 128, 128, 0.2);
    }
    [data-testid="stMetricValue"] {
        color: var(--text-color) !important;
    }
    h1, h2, h3, h4, h5, h6, .text {
        color: var(--text-color) !important;
    }
    [data-baseweb="select"] {
        background-color: var(--background-color);
    }
    [data-testid="stAppViewContainer"] {
        background-color: var(--background-color);
    }
    .streamlit-expanderHeader {
        color: var(--text-color) !important;
    }
    </style>
    """, unsafe_allow_html=True)

# ---------------------------
# LAZY LOADING FUNCTIONS - MEMORY OPTIMIZED
# ---------------------------

@st.cache_data(ttl=3600, max_entries=1)
def get_miner_list():
    """Fetch only miner IDs without loading full dataset"""
    url = "https://huggingface.co/datasets/Atharvaaaaaaaaaa/Data/resolve/main/data.parquet"
    try:
        # Only read miner_id column
        query = f"""
        SELECT DISTINCT miner_id 
        FROM read_parquet('{url}')
        ORDER BY miner_id
        """
        result = db.query(query).df()
        return result['miner_id'].tolist()
    except Exception as e:
        st.error(f"Failed to load miner list: {str(e)}")
        return []

@st.cache_data(ttl=3600, max_entries=1)
def get_available_months():
    """Fetch available months without loading full dataset"""
    url = "https://huggingface.co/datasets/Atharvaaaaaaaaaa/Data/resolve/main/data.parquet"
    try:
        query = f"""
        SELECT DISTINCT 
            strftime(
                (last_ug AT TIME ZONE 'UTC') AT TIME ZONE 'America/New_York',
                '%Y-%m'
            ) as sort_key,
            strftime(
                (last_ug AT TIME ZONE 'UTC') AT TIME ZONE 'America/New_York',
                '%b %Y'
            ) as month_year
        FROM read_parquet('{url}')
        WHERE (last_ug AT TIME ZONE 'UTC') AT TIME ZONE 'America/New_York' >= '2025-01-01'
        ORDER BY sort_key
        """
        result = db.query(query).df()
        return result
    except Exception as e:
        st.error(f"Failed to load months: {str(e)}")
        return pd.DataFrame()

@st.cache_data
def create_shift_table():
    data = {
        'shift_id': [1, 2],
        'start_time': ['08:00:00', '20:00:00'],
        'end_time': ['20:00:00', '08:00:00']
    }
    shift_df = pd.DataFrame(data)
    shift_df['start_time'] = pd.to_datetime(shift_df['start_time'], format='%H:%M:%S').dt.time
    shift_df['end_time'] = pd.to_datetime(shift_df['end_time'], format='%H:%M:%S').dt.time
    return shift_df

@st.cache_data(max_entries=10)
def get_filtered_shift_analysis(month_filter=None, shift_filter=None, miner_ids=None):
    """
    Load and process ONLY the filtered data needed - TRUE LAZY LOADING
    This prevents loading the entire dataset into memory
    """
    url = "https://huggingface.co/datasets/Atharvaaaaaaaaaa/Data/resolve/main/data.parquet"
    
    # Build WHERE clause for parquet file reading
    where_conditions = ["(last_ug AT TIME ZONE 'UTC') AT TIME ZONE 'America/New_York' >= '2025-01-01'"]
    
    if month_filter and month_filter != "All Months":
        # Extract year and month from display format (e.g., "Jan 2025" -> "2025-01")
        month_map = {
            'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
            'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
            'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
        }
        parts = month_filter.split()
        if len(parts) == 2:
            month_num = month_map.get(parts[0], '01')
            year = parts[1]
            where_conditions.append(f"strftime((last_ug AT TIME ZONE 'UTC') AT TIME ZONE 'America/New_York', '%Y-%m') = '{year}-{month_num}'")
    
    if miner_ids and len(miner_ids) > 0:
        miner_list = ','.join(map(str, miner_ids))
        where_conditions.append(f"miner_id IN ({miner_list})")
    
    where_clause = " AND ".join(where_conditions)
    
    with st.spinner('Loading filtered data...'):
        try:
            # Register shift table
            shift_df = create_shift_table()
            db.register('shift_df', shift_df)
            
            # DuckDB query - reads ONLY filtered data from parquet
            query = f"""
            WITH base AS (
                SELECT
                    miner_id,
                    ug_session_id,
                    (MIN(last_ug) AT TIME ZONE 'UTC') AT TIME ZONE 'America/New_York' AS session_start,
                    (MAX(last_ug) AT TIME ZONE 'UTC') AT TIME ZONE 'America/New_York' AS session_end
                FROM read_parquet('{url}')
                WHERE {where_clause}
                GROUP BY miner_id, ug_session_id
            ),
            
            session_minutes AS (
                SELECT
                    b.miner_id,
                    b.ug_session_id,
                    b.session_start,
                    b.session_end,
                    unnest(
                        generate_series(
                            date_trunc('minute', b.session_start),
                            date_trunc('minute', b.session_end),
                            INTERVAL '1 minute'
                        )
                    ) AS minute_ts
                FROM base b
            ),
            
            minute_shift_assignment AS (
                SELECT
                    sm.miner_id,
                    sm.ug_session_id,
                    sm.session_start,
                    sm.session_end,
                    sm.minute_ts,
                    s.shift_id,
                    CASE 
                        WHEN s.shift_id = 1 THEN
                            CASE WHEN EXTRACT(HOUR FROM sm.minute_ts) >= 8 
                                  AND EXTRACT(HOUR FROM sm.minute_ts) < 20 
                            THEN 1 ELSE 0 END
                        WHEN s.shift_id = 2 THEN
                            CASE WHEN EXTRACT(HOUR FROM sm.minute_ts) >= 20 
                                  OR EXTRACT(HOUR FROM sm.minute_ts) < 8 
                            THEN 1 ELSE 0 END
                    END AS in_shift
                FROM session_minutes sm
                CROSS JOIN shift_df s
            ),
            
            shift_overlap AS (
                SELECT
                    miner_id,
                    ug_session_id,
                    session_start,
                    session_end,
                    shift_id,
                    SUM(in_shift) AS minutes_in_shift
                FROM minute_shift_assignment
                GROUP BY miner_id, ug_session_id, session_start, session_end, shift_id
            ),
            
            best_shift AS (
                SELECT
                    miner_id,
                    ug_session_id,
                    shift_id,
                    minutes_in_shift,
                    ROW_NUMBER() OVER (PARTITION BY miner_id, ug_session_id ORDER BY minutes_in_shift DESC, shift_id) AS rn
                FROM shift_overlap
            ),
            
            session_duration AS (
                SELECT
                    miner_id,
                    ug_session_id,
                    session_start,
                    session_end,
                    EXTRACT(EPOCH FROM (session_end - session_start)) / 60 AS total_minutes
                FROM base
            )
            
            SELECT
                b.miner_id,
                b.ug_session_id,
                b.session_start,
                b.session_end,
                ROUND(sd.total_minutes / 60.0, 2) AS hours_worked,
                CAST(FLOOR(sd.total_minutes / 60) AS INTEGER) || 'h ' || 
                CAST(FLOOR(sd.total_minutes % 60) AS INTEGER) || 'm' AS hours_worked_readable,
                bs.shift_id AS assigned_shift_id,
                ROUND(COALESCE(bs.minutes_in_shift, 0) / 60.0, 2) AS overlap_hours_with_assigned_shift,
                CAST(FLOOR(COALESCE(bs.minutes_in_shift, 0) / 60) AS INTEGER) || 'h ' || 
                CAST(FLOOR(COALESCE(bs.minutes_in_shift, 0) % 60) AS INTEGER) || 'm' AS overlap_readable
            FROM base b
            LEFT JOIN best_shift bs
                ON b.miner_id = bs.miner_id
                AND b.ug_session_id = bs.ug_session_id
                AND bs.rn = 1
            LEFT JOIN session_duration sd
                ON b.miner_id = sd.miner_id
                AND b.ug_session_id = sd.ug_session_id
            ORDER BY b.miner_id, b.ug_session_id;
            """
            
            result = db.query(query).df()
            
            if result is None or len(result) == 0:
                st.warning("No data found for the selected filters")
                return pd.DataFrame()
            
            # Optimize data types
            result['session_start'] = pd.to_datetime(result['session_start'])
            result['session_end'] = pd.to_datetime(result['session_end'])
            result['work_date'] = result['session_start'].dt.date
            result['year'] = result['session_start'].dt.year
            result['month_num'] = result['session_start'].dt.month
            result['month_name'] = result['session_start'].dt.strftime('%b')
            result['month_year'] = result['session_start'].dt.strftime('%b %Y')
            result['sort_key'] = result['session_start'].dt.strftime('%Y-%m')
            result['shift_name'] = result['assigned_shift_id'].map({1: 'Shift 1 (Day)', 2: 'Shift 2 (Night)'})
            
            # Apply shift filter if needed
            if shift_filter and shift_filter != "All Shifts":
                shift_num = int(shift_filter.split()[1])
                result = result[result['assigned_shift_id'] == shift_num]
            
            # Convert to memory-efficient types
            result['month_year'] = result['month_year'].astype('category')
            result['assigned_shift_id'] = result['assigned_shift_id'].astype('int8')
            result['miner_id'] = result['miner_id'].astype('int32')
            
            gc.collect()
            
            return result
                
        except Exception as e:
            st.error(f"Failed to load data: {str(e)}")
            return pd.DataFrame()

# ---------------------------
# Page Functions
# ---------------------------

def show_data_insights_page(filtered_df):
    """Display data insights focused on mean vs median analysis"""
    if filtered_df is None or len(filtered_df) == 0:
        st.warning("⚠️ No data available for the selected filters")
        return
    
    st.title("📊 Data Insights")
    st.markdown("### Why is Mean Less Than Median?")
    st.markdown("---")
    
    # Calculate statistics
    mean_hours = filtered_df['hours_worked'].mean()
    median_hours = filtered_df['hours_worked'].median()
    skewness = filtered_df['hours_worked'].skew()
    std_dev = filtered_df['hours_worked'].std()
    
    # Categorize sessions
    short_sessions = len(filtered_df[filtered_df['hours_worked'] < 5])
    normal_sessions = len(filtered_df[(filtered_df['hours_worked'] >= 5) & (filtered_df['hours_worked'] <= 12)])
    extended_sessions = len(filtered_df[(filtered_df['hours_worked'] > 12) & (filtered_df['hours_worked'] <= 16)])
    anomalous_sessions = len(filtered_df[filtered_df['hours_worked'] > 16])
    total_sessions = len(filtered_df)
    
    # Quick Stats
    st.markdown("#### 📊 Your Data Summary")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Mean", f"{mean_hours:.2f}h")
    with col2:
        st.metric("Median", f"{median_hours:.2f}h")
    with col3:
        st.metric("Difference", f"{abs(median_hours - mean_hours):.2f}h")
    with col4:
        st.metric("Skewness", f"{skewness:.2f}")
    
    st.markdown("---")
    
    # Distribution Chart
    st.markdown("#### 📈 Session Duration Distribution")
    
    col1, col2 = st.columns([2.5, 1])
    
    with col1:
        fig = go.Figure()
        
        fig.add_trace(go.Histogram(
            x=filtered_df['hours_worked'],
            nbinsx=50,
            marker_color='#636EFA',
            opacity=0.7,
            name='Sessions'
        ))
        
        fig.add_vline(x=mean_hours, line_dash="dash", line_color="red", line_width=2,
                     annotation_text=f"Mean: {mean_hours:.2f}h", annotation_position="top")
        fig.add_vline(x=median_hours, line_dash="dash", line_color="green", line_width=2,
                     annotation_text=f"Median: {median_hours:.2f}h", annotation_position="top right")
        
        fig.update_layout(
            xaxis_title="Hours Worked",
            yaxis_title="Number of Sessions",
            template='plotly_dark',
            height=400,
            showlegend=False
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.markdown("**Session Categories:**")
        st.metric("🔴 Short (<5h)", f"{short_sessions:,}", f"{(short_sessions/total_sessions*100):.1f}%")
        st.metric("🟢 Normal (5-12h)", f"{normal_sessions:,}", f"{(normal_sessions/total_sessions*100):.1f}%")
        st.metric("🟡 Extended (12-16h)", f"{extended_sessions:,}", f"{(extended_sessions/total_sessions*100):.1f}%")
        st.metric("🔴 Anomalous (>16h)", f"{anomalous_sessions:,}", f"{(anomalous_sessions/total_sessions*100):.1f}%")
    
    st.markdown("---")
    
    # Explanation
    st.markdown("#### 🔍 Analysis: Why Mean < Median in Your Data")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.info(f"""
        **What Your Data Shows:**
        
        - **Mean = {mean_hours:.2f}h** (average of all sessions)
        - **Median = {median_hours:.2f}h** (middle value)
        - **Gap = {abs(median_hours - mean_hours):.2f}h**
        
        Your mean is **{abs(median_hours - mean_hours):.2f} hours lower** than the median.
        
        **Skewness = {skewness:.2f}** (negative)
        
        This negative skewness means your data has a **left tail** - a concentration of short sessions on the lower end that pulls the average down.
        """)
    
    with col2:
        st.success(f"""
        **The Impact of Short Sessions:**
        
        You have **{short_sessions:,} sessions under 5 hours** ({(short_sessions/total_sessions*100):.1f}% of total).
        
        These short sessions are significantly below the median of {median_hours:.2f}h, creating a "tail" on the left side of the distribution.
        
        **Result:** The mean gets pulled down toward these short values, while the median stays stable at the true center of your data.
        """)
    
    st.markdown("---")
    
    # Recommendation
    st.markdown("#### 💡 What This Means")
    
    st.success(f"""
    **Key Takeaway:**
    
    The **median ({median_hours:.2f}h)** better represents your typical session length because:
    - It's not affected by the {(short_sessions/total_sessions*100):.1f}% of short sessions
    - 50% of your sessions are above this value, 50% below
    - It represents what most miners actually work
    
    The **mean ({mean_hours:.2f}h)** is dragged down by short sessions and underestimates typical productivity.
    
    **Recommendation:** Use **median** as your primary KPI for session performance.
    """)

def show_assumptions_page(filtered_df):
    """Display the Assumptions & Methodology page"""
    if filtered_df is None or len(filtered_df) == 0:
        st.warning("⚠️ No data available for the selected filters")
        return
        
    st.title("📖 Assumptions & Methodology")
    st.markdown("### Comprehensive Guide to Dashboard Calculations")
    st.markdown("---")
    
    # Overview
    st.markdown("#### 🎯 Overview")
    st.info("""
    This dashboard analyzes miner productivity by calculating actual work hours per session and 
    assigning each session to the appropriate shift based on maximum time overlap.
    """)
    
    st.markdown("#### 📊 Data Sources & Derived Columns")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("##### 📥 Source Columns")
        st.markdown("""
        - **`miner_id`**: Unique identifier for each miner
        - **`ug_session_id`**: Unique identifier for each work session
        - **`last_ug`**: Timestamp of each underground activity (UTC timezone)
        """)
    
    with col2:
        st.markdown("##### 📤 Derived Columns")
        st.markdown("""
        - **`session_start`**: Minimum `last_ug` timestamp per session (converted to NY timezone)
        - **`session_end`**: Maximum `last_ug` timestamp per session (converted to NY timezone)
        - **`hours_worked`**: Total duration between session start and end
        - **`assigned_shift_id`**: Shift (1 or 2) assigned based on overlap calculation
        - **`overlap_hours`**: Hours the session overlapped with the assigned shift
        """)
    
    st.markdown("---")
    
    # Statistical Methodology
    st.markdown("#### 📊 Statistical Methodology: Why Median Over Mean")
    
    stat_col1, stat_col2 = st.columns(2)
    
    with stat_col1:
        st.markdown("##### 📉 Distribution Characteristics")
        st.info(f"""
        **Current Data Statistics:**
        - **Mean**: {filtered_df['hours_worked'].mean():.2f} hours
        - **Median**: {filtered_df['hours_worked'].median():.2f} hours
        - **Skewness**: {filtered_df['hours_worked'].skew():.2f}
        - **Standard Deviation**: {filtered_df['hours_worked'].std():.2f} hours
        """)
    
    with stat_col2:
        st.markdown("##### ✅ Why Median is Preferred")
        st.success("""
        **Median Advantages:**
        1. **Outlier Resistant**: Not affected by extreme values
        2. **Representative**: True center of the data
        3. **Skew Handling**: Better for non-normal distributions
        4. **Business Context**: Aligns with actual shift patterns
        """)

def show_dashboard_page():
    """Display the main dashboard page with lazy loading"""
    try:
        # LAZY LOAD: Get only metadata first
        available_months = get_available_months()
        all_miners = get_miner_list()
        
        # Sidebar filters
        st.sidebar.markdown("## 🎛️ Filters")
        st.sidebar.markdown("---")
        
        # Month filter
        if not available_months.empty:
            month_display = ["All Months"] + available_months['month_year'].tolist()
        else:
            month_display = ["All Months"]
        
        selected_month_display = st.sidebar.selectbox(
            "📅 Select Month",
            options=month_display,
            index=0
        )
        
        # Shift filter
        selected_shift = st.sidebar.selectbox(
            "⏰ Select Shift",
            options=["All Shifts", "Shift 1", "Shift 2"],
            index=0
        )
        
        st.sidebar.markdown("---")
        selected_miners = st.sidebar.multiselect(
            "👷 Filter by Miners (Optional)",
            options=all_miners,
            default=[]
        )
        
        st.sidebar.markdown("---")
        st.sidebar.info("💡 **Tip:** Filters are applied before loading data to save memory")
        
        # LAZY LOAD: Load only filtered data
        filtered_df = get_filtered_shift_analysis(
            month_filter=selected_month_display,
            shift_filter=selected_shift,
            miner_ids=selected_miners if selected_miners else None
        )
        
        if filtered_df.empty:
            st.warning("⚠️ No data available for the selected filters")
            return
        
        # Key Metrics
        st.markdown("### 📈 Key Performance Indicators")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("🔢 Total Sessions", f"{len(filtered_df):,}")
        
        with col2:
            st.metric("👷 Active Miners", f"{filtered_df['miner_id'].nunique():,}")
        
        with col3:
            st.metric("⏱️ Median Hours/Session", f"{filtered_df['hours_worked'].median():.2f}")
        
        with col4:
            st.metric("⏰ Total Work Hours", f"{filtered_df['hours_worked'].sum():,.0f}")
        
        with col5:
            st.metric("🔥 Max Working Hours", f"{filtered_df['hours_worked'].max():.2f}")
        
        st.markdown("---")
        
        # Aggregate for charts
        monthly_productivity = filtered_df.groupby(['sort_key', 'month_year', 'assigned_shift_id'], observed=True).agg({
            'hours_worked': ['sum', 'median'],
            'ug_session_id': 'count',
            'miner_id': 'nunique'
        }).reset_index()
        
        monthly_productivity.columns = ['sort_key', 'month', 'shift_id', 'total_hours', 'median_hours', 'session_count', 'unique_miners']
        monthly_productivity = monthly_productivity.sort_values('sort_key', ascending=True)
        monthly_productivity['shift_id'] = monthly_productivity['shift_id'].astype(int)
        
        # Main visualizations
        tab1, tab2 = st.tabs(["📊 Productivity Trends", "📋 Detailed Analysis"])
        
        with tab1:
            st.markdown("### 📊 Productivity Trends Over Time")
            
            col_left, col_right = st.columns(2)
            
            with col_left:
                fig1 = go.Figure()
                colors = px.colors.qualitative.Set2
                
                for idx, shift in enumerate(sorted(monthly_productivity['shift_id'].unique())):
                    shift_data = monthly_productivity[monthly_productivity['shift_id'] == shift]
                    fig1.add_trace(go.Scatter(
                        x=shift_data['month'],
                        y=shift_data['total_hours'],
                        name=f'Shift {int(shift)}',
                        mode='lines+markers',
                        marker=dict(size=10),
                        line=dict(width=3),
                        marker_color=colors[idx % len(colors)]
                    ))
                
                fig1.update_layout(
                    title='🔥 Total Work Hours by Month',
                    xaxis_title='Month',
                    yaxis_title='Total Work Hours',
                    template='plotly_dark',
                    height=400
                )
                
                st.plotly_chart(fig1, use_container_width=True)
            
            with col_right:
                fig2 = go.Figure()
                
                for idx, shift in enumerate(sorted(monthly_productivity['shift_id'].unique())):
                    shift_data = monthly_productivity[monthly_productivity['shift_id'] == shift]
                    fig2.add_trace(go.Scatter(
                        x=shift_data['month'],
                        y=shift_data['median_hours'],
                        name=f'Shift {int(shift)}',
                        mode='lines+markers',
                        marker=dict(size=10),
                        line=dict(width=3, dash='dot'),
                        marker_color=colors[idx % len(colors)]
                    ))
                
                fig2.update_layout(
                    title='⚡ Median Hours per Session',
                    xaxis_title='Month',
                    yaxis_title='Median Hours',
                    template='plotly_dark',
                    height=400
                )
                
                st.plotly_chart(fig2, use_container_width=True)
        
        with tab2:
            st.markdown("### 📋 Detailed Data Analysis")
            
            show_detail = st.checkbox("Show individual records (may load slowly)", value=False)
            
            if show_detail:
                # Limit display
                display_limit = min(5000, len(filtered_df))
                if len(filtered_df) > display_limit:
                    st.warning(f"⚠️ Showing first {display_limit:,} of {len(filtered_df):,} records")
                
                display_df = filtered_df.head(display_limit)[['miner_id', 'assigned_shift_id', 'session_start', 
                                                               'session_end', 'hours_worked', 'hours_worked_readable']].copy()
                display_df.columns = ['Miner ID', 'Shift ID', 'Session Start', 'Session End', 'Work Hours', 'Work Duration']
                st.dataframe(display_df, use_container_width=True, height=400)
            else:
                summary_df = filtered_df.groupby(['month_year', 'assigned_shift_id'], observed=True).agg({
                    'hours_worked': ['sum', 'mean', 'median', 'count'],
                    'miner_id': 'nunique'
                }).reset_index()
                
                summary_df.columns = ['Month', 'Shift ID', 'Total Hours', 'Avg Hours', 'Median Hours', 'Session Count', 'Unique Miners']
                summary_df = summary_df.round(2)
                st.dataframe(summary_df, use_container_width=True, height=400)
            
            st.markdown("---")
            st.markdown("#### 💾 Export Data")
            
            csv_data = filtered_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Filtered Data",
                data=csv_data,
                file_name=f'miner_productivity_{selected_month_display}_{selected_shift}.csv',
                mime='text/csv'
            )

    except Exception as e:
        st.error(f"⚠️ **An error occurred:** {str(e)}")
        with st.expander("🔍 View Error Details"):
            import traceback
            st.code(traceback.format_exc())

# ---------------------------
# Main App Logic
# ---------------------------

def main():
    """Main application logic"""
    if 'page' not in st.session_state:
        st.session_state.page = 'Dashboard'

    st.title("⛏️ Miner Shift Productivity Dashboard")
    st.markdown("### 📊 Memory-Optimized with Lazy Loading")

    # Page navigation
    st.sidebar.markdown("---")
    st.sidebar.markdown("## 📄 Navigation")
    page = st.sidebar.radio(
        "Select Page:",
        ["📊 Dashboard", "📖 Assumptions & Methodology", "📊 Data Insights"],
        index=0 if st.session_state.page == 'Dashboard' else (1 if st.session_state.page == 'Assumptions' else 2)
    )

    if page == "📊 Dashboard":
        st.session_state.page = 'Dashboard'
    elif page == "📖 Assumptions & Methodology":
        st.session_state.page = 'Assumptions'
    else:
        st.session_state.page = 'Insights'

    st.markdown("---")

    # Display pages
    try:
        if st.session_state.page == 'Dashboard':
            show_dashboard_page()
        elif st.session_state.page == 'Assumptions':
            # Load minimal data for assumptions page
            st.sidebar.info("Loading sample data for methodology display...")
            selected_month = "All Months"
            filtered_df = get_filtered_shift_analysis(month_filter=selected_month)
            show_assumptions_page(filtered_df)
        else:  # Insights page
            # Load minimal data for insights
            st.sidebar.info("Loading sample data for insights display...")
            selected_month = "All Months"
            filtered_df = get_filtered_shift_analysis(month_filter=selected_month)
            show_data_insights_page(filtered_df)
    except Exception as e:
        st.error(f"⚠️ **An error occurred:** {str(e)}")
        st.info("Please check the error details below.")
        with st.expander("🔍 View Full Error Details"):
            import traceback
            st.code(traceback.format_exc())

if __name__ == "__main__":
    main()