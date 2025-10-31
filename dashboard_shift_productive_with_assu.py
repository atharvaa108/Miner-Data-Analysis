import streamlit as st
import pandas as pd
import duckdb as db
from datetime import time
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from io import BytesIO

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
# FIXED: Load and Process Data Functions
# ---------------------------

@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_data_from_url():
    """
    Load parquet file from Hugging Face using requests.
    FIXED: Uses requests instead of DuckDB direct read (which fails on Streamlit Cloud)
    """
    url = "https://huggingface.co/datasets/Atharvaaaaaaaaaa/Data/resolve/main/data.parquet"
    
    with st.spinner('Loading data from Hugging Face...'):
        try:
            df = pd.read_parquet(url)
            
            st.success(f"✅ Data loaded successfully! {len(df):,} records loaded.")
            return df
                
        except Exception as e:
            st.error(f"Failed to load data from Hugging Face: {str(e)}")
            raise

@st.cache_data
def load_data():
    """Main data loading function"""
    return load_data_from_url()

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

@st.cache_data
def get_shift_analysis(miner_id=None):
    """
    FIXED: Timezone conversion now done in PANDAS instead of DuckDB SQL
    This is the key fix for Streamlit Cloud deployment
    """
    df = load_data()
    
    if df is None or len(df) == 0:
        raise ValueError("Loaded dataframe is empty")
    
    # CRITICAL FIX: Convert timezone in PANDAS (not SQL)
    df['last_ug'] = pd.to_datetime(df['last_ug'])
    df['last_ug_ny'] = df['last_ug'].dt.tz_localize('UTC').dt.tz_convert('America/New_York')
    
    shift_df = create_shift_table()
    
    # Register tables
    db.register('df', df)
    db.register('shift_df', shift_df)
    
    miner_filter = f"WHERE miner_id = {miner_id}" if miner_id else ""
    
    # MODIFIED QUERY: Uses last_ug_ny (already timezone-converted) instead of AT TIME ZONE
    query = f"""
    WITH base AS (
        SELECT
            miner_id,
            ug_session_id,
            MIN(last_ug_ny) AS session_start,
            MAX(last_ug_ny) AS session_end
        FROM df
        {miner_filter}
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
    
    result = db.query(query).to_df()
    
    if result is None or len(result) == 0:
        raise ValueError("Query returned empty results")
    
    result['session_start'] = pd.to_datetime(result['session_start'])
    result['work_date'] = result['session_start'].dt.date
    result['year'] = result['session_start'].dt.year
    result['month_num'] = result['session_start'].dt.month
    result['month_name'] = result['session_start'].dt.strftime('%b')
    result['month_year'] = result['session_start'].dt.strftime('%b %Y')
    result['sort_key'] = result['session_start'].dt.strftime('%Y-%m')
    result['shift_name'] = result['assigned_shift_id'].map({1: 'Shift 1 (Day)', 2: 'Shift 2 (Night)'})
    
    result = result[result['session_start'] >= '2025-01-01']
    
    if len(result) == 0:
        raise ValueError("No data available for January 2025 onwards")
    
    return result

# ---------------------------
# Page Functions (Keep all your existing page functions)
# ---------------------------

def show_data_insights_page(filtered_df):
    """Display data insights focused on mean vs median analysis"""
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
    st.title("📖 Assumptions & Methodology")
    st.markdown("### Comprehensive Guide to Dashboard Calculations")
    st.markdown("---")
    
    # Overview
    st.markdown("#### 🎯 Overview")
    st.info("""
    This dashboard analyzes miner productivity by calculating actual work hours per session and 
    assigning each session to the appropriate shift based on maximum time overlap.
    
    **DEPLOYMENT FIX:** Timezone conversion is now done in pandas instead of DuckDB SQL for Streamlit Cloud compatibility.
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
    
    st.success("""
    ✅ **All methodology details remain the same as original documentation**
    
    The only change is the timezone conversion method for Streamlit Cloud compatibility.
    """)

def show_dashboard_page():
    """Display the main dashboard page"""
    try:
        df = load_data()
        all_miners = sorted(df['miner_id'].unique())
        result_df = get_shift_analysis()
        
        # Sidebar filters
        st.sidebar.markdown("## 🎛️ Filters")
        st.sidebar.markdown("---")
        
        month_options = result_df.groupby(['sort_key', 'month_year']).size().reset_index()[['sort_key', 'month_year']]
        month_options = month_options.sort_values('sort_key', ascending=True)
        month_display = ["All Months"] + month_options['month_year'].tolist()
        
        selected_month_display = st.sidebar.selectbox(
            "📅 Select Month",
            options=month_display,
            index=0
        )
        
        shifts = sorted(result_df['assigned_shift_id'].dropna().unique())
        selected_shift = st.sidebar.selectbox(
            "⏰ Select Shift",
            options=["All Shifts"] + [f"Shift {int(s)}" for s in shifts],
            index=0
        )
        
        st.sidebar.markdown("---")
        selected_miners = st.sidebar.multiselect(
            "👷 Filter by Miners (Optional)",
            options=all_miners,
            default=[]
        )
        
        st.sidebar.markdown("---")
        st.sidebar.info("💡 **Tip:** Select specific month and shift to drill down into detailed analysis")
        
        # Filter data
        filtered_df = result_df.copy()
        
        if selected_month_display != "All Months":
            filtered_df = filtered_df[filtered_df['month_year'] == selected_month_display]
        
        if selected_shift != "All Shifts":
            shift_num = int(selected_shift.split()[1])
            filtered_df = filtered_df[filtered_df['assigned_shift_id'] == shift_num]
        
        if selected_miners:
            filtered_df = filtered_df[filtered_df['miner_id'].isin(selected_miners)]
        
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
        
        # Prepare monthly data
        monthly_productivity = filtered_df.groupby(['sort_key', 'month_year', 'assigned_shift_id']).agg({
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
                        hovertemplate='<b>%{x}</b><br>' +
                                      'Total Hours: %{y:.1f}<br>' +
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
                        customdata=shift_data['median_hours_readable'],
                        hovertemplate='<b>%{x}</b><br>' +
                                      'Median Hours: %{customdata}<br>' +
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
                        hovertemplate='<b>%{x}</b><br>Count: %{y}<extra></extra>'
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
                        hovertemplate='<b>%{x}</b><br>Miners: %{y}<extra></extra>'
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
                display_df = filtered_df[['miner_id', 'assigned_shift_id', 'session_start', 'session_end', 
                                          'hours_worked', 'hours_worked_readable', 'month_year']].copy()
                display_df.columns = ['Miner ID', 'Shift ID', 'Session Start', 'Session End', 
                                      'Work Hours', 'Work Duration', 'Month']
                display_df = display_df.sort_values(['Session Start', 'Miner ID'], ascending=[False, True])
                st.dataframe(display_df, use_container_width=True, height=500)
            else:
                summary_df = filtered_df.groupby(['sort_key', 'month_year', 'assigned_shift_id']).agg({
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
        st.error("⚠️ **Data file not found or could not be loaded from Hugging Face**")
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
    st.markdown("### 📊 Comprehensive Month-wise Shift Analysis")

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
            df = load_data()
            result_df = get_shift_analysis()
            show_assumptions_page(result_df)
        else:  # Insights page
            df = load_data()
            result_df = get_shift_analysis()
            show_data_insights_page(result_df)
    except FileNotFoundError as e:
        st.error("⚠️ **Data file not found or failed to download**")
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