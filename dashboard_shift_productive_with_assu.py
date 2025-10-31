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
            name='Sessions',
            hovertemplate='<b>Hours: %{x:.2f}</b><br>Count: %{y}<extra></extra>'
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
            showlegend=False,
            hovermode='closest'
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
    
    # Possible Reasons
    st.markdown("#### 🔎 Possible Reasons for Short Sessions in Your Data")
    
    st.warning(f"""
    **{short_sessions:,} sessions ({(short_sessions/total_sessions*100):.1f}%) are under 5 hours. These could be due to:**
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Operational Reasons:**")
        st.markdown("""
        - Equipment breakdowns
        - Material shortages
        - Scheduled maintenance
        - Safety incidents
        - Medical emergencies
        - Approved early departures
        - Training sessions
        - Shift handovers
        """)
    
    with col2:
        st.markdown("**Data Quality Issues:**")
        st.markdown("""
        - Tracking device failures
        - Signal loss underground
        - Incomplete session logging
        - System errors/reboots
        - Database sync issues
        - Manual entry errors
        - Session fragmentation
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
    
    # Shift Definitions
    st.markdown("#### ⏰ Shift Definitions")
    
    shift_col1, shift_col2 = st.columns(2)
    
    with shift_col1:
        st.success("""
        **🌅 Shift 1 (Day Shift)**
        - Start Time: 08:00:00
        - End Time: 20:00:00
        - Duration: 12 hours
        - Same calendar day
        """)
    
    with shift_col2:
        st.info("""
        **🌙 Shift 2 (Night Shift)**
        - Start Time: 20:00:00
        - End Time: 08:00:00 (next day)
        - Duration: 12 hours
        - Crosses midnight
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
        - **Skewness**: {filtered_df['hours_worked'].skew():.2f} (negative)
        - **Standard Deviation**: {filtered_df['hours_worked'].std():.2f} hours
        
        **What This Tells Us:**
        - **Negative skewness** indicates a left-tailed distribution
        - More sessions are **shorter** than the mean, pulling it down
        - The distribution has a concentration around 8-12 hours with a tail of very short sessions
        """)
    
    with stat_col2:
        st.markdown("##### ✅ Why Median is Preferred")
        st.success("""
        **Median Advantages:**
        1. **Outlier Resistant**: Not affected by extreme values (0.5h or 40h sessions)
        2. **Representative**: 50% of sessions are above, 50% below - true center
        3. **Skew Handling**: Better for non-normal distributions
        4. **Business Context**: Aligns with actual shift completion patterns
        
        **When Mean Would Be Better:**
        - If data were normally distributed (skewness ≈ 0)
        - If outliers were meaningful and should influence the metric
        - If calculating total resource allocation
        """)
    
    st.markdown("---")
    
    # Working Hours Calculation
    st.markdown("#### 🕐 Working Hours Calculation")
    
    with st.expander("📐 **How We Calculate Actual Working Hours**", expanded=True):
        st.markdown("""
        **Step 1: Session Boundary Identification**
        ```sql
        session_start = MIN(last_ug) -- First activity timestamp
        session_end = MAX(last_ug)   -- Last activity timestamp
        ```
        
        **Step 2: Timezone Conversion**
        - All `last_ug` timestamps are converted from UTC to America/New_York timezone
        - This ensures accurate shift assignment based on local time
        
        **Step 3: Duration Calculation**
        ```sql
        total_minutes = EXTRACT(EPOCH FROM (session_end - session_start)) / 60
        hours_worked = total_minutes / 60
        ```
        
        **Step 4: Time Format Display**
        - **Decimal Format**: `5.21` hours
        - **Readable Format**: `5h 12m` (5 hours and 12 minutes)
        
        **Example:**
        - Session Start: `2025-01-18 19:47:41`
        - Session End: `2025-01-19 01:00:04`
        - Working Hours: `5.21` hours or `5h 12m`
        """)
    
    st.markdown("---")
    
    # Data Quality Insights
    st.markdown("#### 🔍 Data Quality & Distribution Analysis")
    
    quality_col1, quality_col2 = st.columns(2)
    
    with quality_col1:
        st.markdown("##### 📊 Session Distribution")
        total = len(filtered_df)
        st.markdown(f"""
        **By Duration Category:**
        - **Very Short (<5h)**: {len(filtered_df[filtered_df['hours_worked'] < 5]):,} sessions ({len(filtered_df[filtered_df['hours_worked'] < 5])/total*100:.1f}%)
        - **Normal (5-12h)**: {len(filtered_df[(filtered_df['hours_worked'] >= 5) & (filtered_df['hours_worked'] <= 12)]):,} sessions ({len(filtered_df[(filtered_df['hours_worked'] >= 5) & (filtered_df['hours_worked'] <= 12)])/total*100:.1f}%)
        - **Extended (12-16h)**: {len(filtered_df[(filtered_df['hours_worked'] > 12) & (filtered_df['hours_worked'] <= 16)]):,} sessions ({len(filtered_df[(filtered_df['hours_worked'] > 12) & (filtered_df['hours_worked'] <= 16)])/total*100:.1f}%)
        - **Anomalous (>16h)**: {len(filtered_df[filtered_df['hours_worked'] > 16]):,} sessions ({len(filtered_df[filtered_df['hours_worked'] > 16])/total*100:.1f}%)
        """)
    
    with quality_col2:
        st.markdown("##### ⚠️ Interpretation")
        st.warning("""
        **Short Sessions Impact:**
        - High percentage of short sessions creates negative skew
        - These pull the mean DOWN below the median
        - Could indicate: incomplete shifts, tracking errors, or legitimate early departures
        
        **Why This Matters:**
        - Using mean would underestimate typical productivity
        - Median better represents "normal" work patterns
        - Management decisions should be based on median performance
        """)
    
    st.markdown("---")
    
    # Key Assumptions
    st.markdown("#### 📋 Key Assumptions")
    
    assumptions_col1, assumptions_col2 = st.columns(2)
    
    with assumptions_col1:
        st.markdown("""
        **Timezone & Time Handling:**
        - All timestamps are converted to America/New_York (EST/EDT)
        - Sessions can span multiple days
        - Midnight crossing is handled automatically for night shifts
        """)
    
    with assumptions_col2:
        st.markdown("""
        **Session Definition:**
        - A session is defined by unique `ug_session_id`
        - Session duration = time between first and last activity
        - Idle time within sessions is included in working hours
        """)
    
    assumptions_col3, assumptions_col4 = st.columns(2)
    
    with assumptions_col3:
        st.markdown("""
        **Shift Assignment:**
        - Shifts are mutually exclusive (no overlap)
        - Assignment based on maximum time overlap
        - Ties are broken by shift_id (lower number wins)
        """)
    
    with assumptions_col4:
        st.markdown("""
        **Data Filtering:**
        - Only data from January 2025 onwards is included
        - Sessions with missing shift assignments are excluded from shift-specific analysis
        - All times are calculated to minute-level precision
        """)
    
    st.markdown("---")
    
    # Data Quality Notes
    st.markdown("#### ⚠️ Data Quality & Limitations")
    
    st.warning("""
    **Please Note:**
    - Sessions spanning multiple shifts are assigned to ONE shift (the one with maximum overlap)
    - Break times and idle periods within sessions are included in working hours
    - The system assumes continuous work between first and last activity timestamp
    - Sessions with less than 1 minute duration may have rounding differences
    - Daylight Saving Time transitions are handled automatically by timezone conversion
    - **Short sessions (<5h)** may indicate incomplete data collection or early departures
    - **Very long sessions (>16h)** should be investigated for potential tracking errors
    """)

def show_dashboard_page():
    """Display the main dashboard page with lazy loading and ALL graphs"""
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
        st.sidebar.info("💡 **Tip:** Filters are applied before loading data to save memory. Hover over charts for detailed comparisons!")
        
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
            st.metric(
                label="🔢 Total Sessions",
                value=f"{len(filtered_df):,}",
                delta=None
            )
        
        with col2:
            st.metric(
                label="👷 Active Miners",
                value=f"{filtered_df['miner_id'].nunique():,}",
                delta=None
            )
        
        with col3:
            median_hours = filtered_df['hours_worked'].median()
            st.metric(
                label="⏱️ Median Hours/Session",
                value=f"{median_hours:.2f}",
                delta=None
            )
        
        with col4:
            total_hours = filtered_df['hours_worked'].sum()
            st.metric(
                label="⏰ Total Work Hours",
                value=f"{total_hours:,.0f}",
                delta=None
            )
        
        with col5:
            max_hours = filtered_df['hours_worked'].max()
            st.metric(
                label="🔥 Max Working Hours",
                value=f"{max_hours:.2f}",
                delta=None
            )
        
        st.markdown("---")
        
        # Prepare monthly data - aggregate to reduce memory
        monthly_productivity = filtered_df.groupby(['sort_key', 'month_year', 'assigned_shift_id'], observed=True).agg({
            'hours_worked': ['sum', 'mean', 'median'],
            'ug_session_id': 'count',
            'miner_id': 'nunique'
        }).reset_index()
        
        monthly_productivity.columns = ['sort_key', 'month', 'shift_id', 'total_hours', 'avg_hours', 'median_hours', 'session_count', 'unique_miners']
        monthly_productivity = monthly_productivity.sort_values('sort_key', ascending=True)
        monthly_productivity['shift_id'] = monthly_productivity['shift_id'].astype(int)
        
        # Readable format for median hours
        monthly_productivity['median_hours_readable'] = monthly_productivity['median_hours'].apply(
            lambda h: (
                (lambda total_min: f"{total_min // 60}h {total_min % 60:02d}m")(int(round(h * 60)))
            )
        )
        
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
                        marker_color=colors[idx % len(colors)],
                        customdata=shift_data[['session_count', 'unique_miners']],
                        hovertemplate='<b>%{x}</b><br>' +
                                      'Total Hours: <b>%{y:,.1f}</b><br>' +
                                      'Sessions: %{customdata[0]:,}<br>' +
                                      'Active Miners: %{customdata[1]:,}<br>' +
                                      '<extra></extra>'
                    ))
                
                fig1.update_layout(
                    title={
                        'text': '🔥 Total Work Hours by Month',
                        'font': {'size': 18, 'color': 'white'}
                    },
                    xaxis_title='Month',
                    yaxis_title='Total Work Hours',
                    hovermode='x unified',
                    template='plotly_dark',
                    height=400,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    ),
                    font=dict(color='white'),
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)'
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
                        marker_color=colors[idx % len(colors)],
                        customdata=shift_data[['median_hours_readable', 'session_count', 'avg_hours']],
                        hovertemplate='<b>%{x}</b><br>' +
                                      'Median Hours: <b>%{customdata[0]}</b><br>' +
                                      'Avg Hours: %{customdata[2]:.2f}<br>' +
                                      'Sessions: %{customdata[1]:,}<br>' +
                                      '<extra></extra>'
                    ))
                
                fig2.update_layout(
                    title={
                        'text': '⚡ Median Hours per Session',
                        'font': {'size': 18, 'color': 'white'}
                    },
                    xaxis_title='Month',
                    yaxis_title='Median Hours',
                    hovermode='x unified',
                    template='plotly_dark',
                    height=400,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    ),
                    font=dict(color='white'),
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)'
                )
                
                st.plotly_chart(fig2, use_container_width=True)
            
            st.markdown("#### 📊 Multi-Metric Analysis")
            
            fig_combined = make_subplots(
                rows=1, cols=2,
                subplot_titles=('Session Count Trend', 'Active Miners Trend'),
                specs=[[{"secondary_y": False}, {"secondary_y": False}]]
            )
            
            for idx, shift in enumerate(sorted(monthly_productivity['shift_id'].unique())):
                shift_data = monthly_productivity[monthly_productivity['shift_id'] == shift]
                
                fig_combined.add_trace(
                    go.Bar(
                        x=shift_data['month'],
                        y=shift_data['session_count'],
                        name=f'Shift {int(shift)}',
                        marker_color=colors[idx % len(colors)],
                        customdata=shift_data[['total_hours', 'median_hours_readable']],
                        hovertemplate='<b>%{x}</b><br>' +
                                      'Session Count: <b>%{y:,}</b><br>' +
                                      'Total Hours: %{customdata[0]:,.1f}<br>' +
                                      'Median: %{customdata[1]}<br>' +
                                      '<extra></extra>'
                    ),
                    row=1, col=1
                )
                
                fig_combined.add_trace(
                    go.Scatter(
                        x=shift_data['month'],
                        y=shift_data['unique_miners'],
                        name=f'Shift {int(shift)}',
                        mode='lines+markers',
                        marker=dict(size=8),
                        line=dict(width=2.5),
                        marker_color=colors[idx % len(colors)],
                        showlegend=False,
                        customdata=shift_data[['session_count', 'total_hours']],
                        hovertemplate='<b>%{x}</b><br>' +
                                      'Active Miners: <b>%{y:,}</b><br>' +
                                      'Sessions: %{customdata[0]:,}<br>' +
                                      'Total Hours: %{customdata[1]:,.1f}<br>' +
                                      '<extra></extra>'
                    ),
                    row=1, col=2
                )
            
            fig_combined.update_xaxes(title_text="Month", row=1, col=1)
            fig_combined.update_xaxes(title_text="Month", row=1, col=2)
            fig_combined.update_yaxes(title_text="Number of Sessions", row=1, col=1)
            fig_combined.update_yaxes(title_text="Number of Miners", row=1, col=2)
            
            fig_combined.update_layout(
                height=450,
                template='plotly_dark',
                hovermode='x unified',
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=-0.2,
                    xanchor="center",
                    x=0.5
                ),
                font=dict(color='white'),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)'
            )
            fig_combined.update_annotations(font=dict(color='white'))
            
            st.plotly_chart(fig_combined, use_container_width=True)
        
        with tab2:
            st.markdown("### 📋 Detailed Data Analysis")
            
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown("#### 📊 Monthly Shift Summary")
            
            with col2:
                show_detail = st.checkbox("Show individual records", value=False)
            
            if show_detail:
                # Limit rows to prevent memory issues
                display_limit = min(10000, len(filtered_df))
                if len(filtered_df) > display_limit:
                    st.warning(f"⚠️ Showing first {display_limit:,} of {len(filtered_df):,} records to prevent memory issues")
                    display_df = filtered_df.head(display_limit)
                else:
                    display_df = filtered_df
                
                display_df = display_df[['miner_id', 'assigned_shift_id', 'session_start', 'session_end', 
                                          'hours_worked', 'hours_worked_readable', 'month_year']].copy()
                display_df.columns = ['Miner ID', 'Shift ID', 'Session Start', 'Session End', 
                                      'Work Hours', 'Work Duration', 'Month']
                display_df = display_df.sort_values(['Session Start', 'Miner ID'], ascending=[False, True])
                st.dataframe(display_df, use_container_width=True, height=500)
            else:
                summary_df = filtered_df.groupby(['sort_key', 'month_year', 'assigned_shift_id'], observed=True).agg({
                    'hours_worked': ['sum', 'mean', 'median', 'std', 'count'],
                    'miner_id': 'nunique'
                }).reset_index()
                
                summary_df.columns = ['sort_key', 'Month', 'Shift ID', 'Total Hours', 'Avg Hours', 
                                     'Median Hours', 'Std Dev', 'Session Count', 'Unique Miners']
                summary_df['Shift ID'] = summary_df['Shift ID'].astype(int)
                summary_df = summary_df.round(2)
                summary_df = summary_df.sort_values('sort_key', ascending=False)
                summary_df = summary_df.drop('sort_key', axis=1)
                
                st.dataframe(summary_df, use_container_width=True, height=500)
            
            st.markdown("---")
            st.markdown("#### 💾 Export Data")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                csv_filtered = filtered_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download Filtered Data",
                    data=csv_filtered,
                    file_name=f'miner_productivity_{selected_month_display}_{selected_shift}.csv',
                    mime='text/csv'
                )
            
            with col2:
                if not show_detail:
                    csv_summary = summary_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Download Summary",
                        data=csv_summary,
                        file_name=f'productivity_summary_{selected_month_display}.csv',
                        mime='text/csv'
                    )

    except FileNotFoundError as e:
        st.error("⚠️ **Data file not found or could not be loaded**")
        st.info("Please ensure the Hugging Face file is publicly accessible.")
        with st.expander("🔍 View Error Details"):
            st.code(str(e))
    except Exception as e:
        st.error(f"⚠️ **An error occurred:** {str(e)}")
        st.info("Please check your data file and query configuration.")
        with st.expander("🔍 View Error Details"):
            st.code(str(e))

# ---------------------------
# Main App Logic with Page Selection
# ---------------------------

def main():
    """Main application logic"""
    # Initialize session state for page navigation
    if 'page' not in st.session_state:
        st.session_state.page = 'Dashboard'

    # Title and description
    st.title("⛏️ Miner Shift Productivity Dashboard")
    st.markdown("### 📊 Memory-Optimized with Lazy Loading")

    # Page selection in sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown("## 📄 Navigation")
    page = st.sidebar.radio(
        "Select Page:",
        ["📊 Dashboard", "📖 Assumptions & Methodology", "📊 Data Insights"],
        index=0 if st.session_state.page == 'Dashboard' else (1 if st.session_state.page == 'Assumptions' else 2)
    )

    # Update session state
    if page == "📊 Dashboard":
        st.session_state.page = 'Dashboard'
    elif page == "📖 Assumptions & Methodology":
        st.session_state.page = 'Assumptions'
    else:
        st.session_state.page = 'Insights'

    st.markdown("---")

    # Display the selected page
    try:
        if st.session_state.page == 'Dashboard':
            show_dashboard_page()
        elif st.session_state.page == 'Assumptions':
            # Load minimal data for assumptions page
            result_df = get_filtered_shift_analysis(month_filter="All Months")
            show_assumptions_page(result_df)
        else:  # Insights page
            # Load minimal data for insights
            result_df = get_filtered_shift_analysis(month_filter="All Months")
            show_data_insights_page(result_df)
    except FileNotFoundError as e:
        st.error("⚠️ **Data file not found or failed to load**")
        st.info("Please check if the Hugging Face file is publicly accessible.")
        st.error(f"Error details: {str(e)}")
    except Exception as e:
        st.error(f"⚠️ **An error occurred:** {str(e)}")
        st.info("Please check the error details below.")
        with st.expander("🔍 View Full Error Details"):
            import traceback
            st.code(traceback.format_exc())

if __name__ == "__main__":
    main()