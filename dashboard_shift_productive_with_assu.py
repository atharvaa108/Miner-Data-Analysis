import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Page configuration
st.set_page_config(
    page_title="Miner Shift Productivity Dashboard",
    page_icon="⛏️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    [data-testid="stMetric"] {
        background-color: var(--background-color);
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border: 1px solid rgba(128, 128, 128, 0.2);
    }
    </style>
    """, unsafe_allow_html=True)

# ---------------------------
# Load and Process Data Functions
# ---------------------------

@st.cache_data(ttl=3600)
def load_data():
    """Load parquet file from Hugging Face"""
    url = "https://huggingface.co/datasets/Atharvaaaaaaaaaa/Data/resolve/main/data.parquet"
    
    try:
        with st.spinner('Loading data...'):
            df = pd.read_parquet(url)
            
            if df is None or len(df) == 0:
                raise ValueError("DataFrame is empty")
            
            st.success(f"✅ Data loaded! {len(df):,} records")
            return df
                
    except Exception as e:
        st.error(f"❌ Failed to load data: {str(e)}")
        raise

@st.cache_data
def create_shift_table():
    """Create shift definition table"""
    data = {
        'shift_id': [1, 2],
        'start_hour': [8, 20],
        'end_hour': [20, 8]
    }
    return pd.DataFrame(data)

def assign_shift(hour):
    """Assign shift based on hour of day"""
    if 8 <= hour < 20:
        return 1
    else:
        return 2

@st.cache_data
def get_shift_analysis():
    """Process data and calculate shift assignments"""
    df = load_data()
    
    # Convert timestamp to datetime and timezone
    df['last_ug'] = pd.to_datetime(df['last_ug'], utc=True)
    df['last_ug_ny'] = df['last_ug'].dt.tz_convert('America/New_York')
    
    # Calculate session boundaries
    session_stats = df.groupby(['miner_id', 'ug_session_id']).agg({
        'last_ug_ny': ['min', 'max']
    }).reset_index()
    
    session_stats.columns = ['miner_id', 'ug_session_id', 'session_start', 'session_end']
    
    # Calculate hours worked
    session_stats['hours_worked'] = (
        (session_stats['session_end'] - session_stats['session_start']).dt.total_seconds() / 3600
    )
    
    # Create readable format
    session_stats['hours_worked_readable'] = session_stats['hours_worked'].apply(
        lambda h: f"{int(h)}h {int((h % 1) * 60)}m"
    )
    
    # Assign shift based on session start hour
    session_stats['start_hour'] = session_stats['session_start'].dt.hour
    session_stats['assigned_shift_id'] = session_stats['start_hour'].apply(assign_shift)
    
    # Calculate overlap (simplified - using dominant shift)
    session_stats['overlap_hours_with_assigned_shift'] = session_stats['hours_worked']
    session_stats['overlap_readable'] = session_stats['hours_worked_readable']
    
    # Add date/time columns
    session_stats['work_date'] = session_stats['session_start'].dt.date
    session_stats['year'] = session_stats['session_start'].dt.year
    session_stats['month_num'] = session_stats['session_start'].dt.month
    session_stats['month_name'] = session_stats['session_start'].dt.strftime('%b')
    session_stats['month_year'] = session_stats['session_start'].dt.strftime('%b %Y')
    session_stats['sort_key'] = session_stats['session_start'].dt.strftime('%Y-%m')
    session_stats['shift_name'] = session_stats['assigned_shift_id'].map({
        1: 'Shift 1 (Day)', 
        2: 'Shift 2 (Night)'
    })
    
    # Filter to January 2025 onwards
    session_stats = session_stats[session_stats['session_start'] >= '2025-01-01']
    
    if len(session_stats) == 0:
        raise ValueError("No data available for January 2025 onwards")
    
    return session_stats

# ---------------------------
# Page Functions
# ---------------------------

def show_data_insights_page(filtered_df):
    """Display data insights"""
    st.title("📊 Data Insights")
    st.markdown("### Why is Mean Less Than Median?")
    st.markdown("---")
    
    # Calculate statistics
    mean_hours = filtered_df['hours_worked'].mean()
    median_hours = filtered_df['hours_worked'].median()
    skewness = filtered_df['hours_worked'].skew()
    
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
    
    st.success(f"""
    **Key Takeaway:**
    
    The **median ({median_hours:.2f}h)** better represents your typical session length because:
    - It's not affected by the {(short_sessions/total_sessions*100):.1f}% of short sessions
    - 50% of your sessions are above this value, 50% below
    
    **Recommendation:** Use **median** as your primary KPI for session performance.
    """)

def show_assumptions_page(filtered_df):
    """Display methodology"""
    st.title("📖 Assumptions & Methodology")
    st.markdown("---")
    
    st.markdown("#### 🎯 Overview")
    st.info("""
    This dashboard analyzes miner productivity by calculating actual work hours per session and 
    assigning each session to the appropriate shift based on session start time.
    """)
    
    st.markdown("#### ⏰ Shift Definitions")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.success("""
        **🌅 Shift 1 (Day Shift)**
        - Start Time: 08:00:00
        - End Time: 20:00:00
        - Duration: 12 hours
        """)
    
    with col2:
        st.info("""
        **🌙 Shift 2 (Night Shift)**
        - Start Time: 20:00:00
        - End Time: 08:00:00 (next day)
        - Duration: 12 hours
        """)
    
    st.markdown("---")
    
    st.markdown("#### 📊 Statistical Methodology")
    
    st.info(f"""
    **Current Data Statistics:**
    - **Mean**: {filtered_df['hours_worked'].mean():.2f} hours
    - **Median**: {filtered_df['hours_worked'].median():.2f} hours
    - **Skewness**: {filtered_df['hours_worked'].skew():.2f}
    - **Standard Deviation**: {filtered_df['hours_worked'].std():.2f} hours
    """)
    
    st.markdown("---")
    
    st.markdown("#### 📋 Key Assumptions")
    
    st.markdown("""
    **Session Definition:**
    - A session is defined by unique `ug_session_id`
    - Session duration = time between first and last activity
    
    **Shift Assignment:**
    - Assignment based on session start hour
    - Shift 1: 8:00 AM - 8:00 PM
    - Shift 2: 8:00 PM - 8:00 AM
    
    **Data Filtering:**
    - Only data from January 2025 onwards is included
    - All times converted to America/New_York timezone
    """)

def show_dashboard_page():
    """Display main dashboard"""
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
            st.metric("🔢 Total Sessions", f"{len(filtered_df):,}")
        
        with col2:
            st.metric("👷 Active Miners", f"{filtered_df['miner_id'].nunique():,}")
        
        with col3:
            median_hours = filtered_df['hours_worked'].median()
            st.metric("⏱️ Median Hours/Session", f"{median_hours:.2f}")
        
        with col4:
            total_hours = filtered_df['hours_worked'].sum()
            st.metric("⏰ Total Work Hours", f"{total_hours:,.0f}")
        
        with col5:
            max_hours = filtered_df['hours_worked'].max()
            st.metric("🔥 Max Working Hours", f"{max_hours:.2f}")
        
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
        
        # Main visualizations
        tab1, tab2 = st.tabs(["📊 Productivity Trends", "📋 Detailed Analysis"])
        
        with tab1:
            st.markdown("### 📊 Productivity Trends Over Time")
            
            col_left, col_right = st.columns(2)
            
            with col_left:
                fig1 = px.line(
                    monthly_productivity,
                    x='month',
                    y='total_hours',
                    color='shift_id',
                    markers=True,
                    title='🔥 Total Work Hours by Month',
                    labels={'total_hours': 'Total Hours', 'month': 'Month', 'shift_id': 'Shift'}
                )
                fig1.update_layout(template='plotly_dark', height=400)
                st.plotly_chart(fig1, use_container_width=True)
            
            with col_right:
                fig2 = px.line(
                    monthly_productivity,
                    x='month',
                    y='median_hours',
                    color='shift_id',
                    markers=True,
                    title='⚡ Median Hours per Session',
                    labels={'median_hours': 'Median Hours', 'month': 'Month', 'shift_id': 'Shift'}
                )
                fig2.update_layout(template='plotly_dark', height=400)
                st.plotly_chart(fig2, use_container_width=True)
            
            st.markdown("#### 📊 Multi-Metric Analysis")
            
            fig_combined = make_subplots(
                rows=1, cols=2,
                subplot_titles=('Session Count Trend', 'Active Miners Trend')
            )
            
            colors = px.colors.qualitative.Set2
            for idx, shift in enumerate(sorted(monthly_productivity['shift_id'].unique())):
                shift_data = monthly_productivity[monthly_productivity['shift_id'] == shift]
                
                fig_combined.add_trace(
                    go.Bar(
                        x=shift_data['month'],
                        y=shift_data['session_count'],
                        name=f'Shift {int(shift)}',
                        marker_color=colors[idx % len(colors)]
                    ),
                    row=1, col=1
                )
                
                fig_combined.add_trace(
                    go.Scatter(
                        x=shift_data['month'],
                        y=shift_data['unique_miners'],
                        name=f'Shift {int(shift)}',
                        mode='lines+markers',
                        marker_color=colors[idx % len(colors)],
                        showlegend=False
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
                showlegend=True
            )
            
            st.plotly_chart(fig_combined, use_container_width=True)
        
        with tab2:
            st.markdown("### 📋 Detailed Data Analysis")
            
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
            
            csv_filtered = filtered_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Filtered Data",
                data=csv_filtered,
                file_name=f'miner_productivity_{selected_month_display}_{selected_shift}.csv',
                mime='text/csv'
            )

    except Exception as e:
        st.error(f"⚠️ **An error occurred:** {str(e)}")
        with st.expander("🔍 View Error Details"):
            import traceback
            st.code(traceback.format_exc())

# ---------------------------
# Main App
# ---------------------------

def main():
    """Main application"""
    if 'page' not in st.session_state:
        st.session_state.page = 'Dashboard'

    st.title("⛏️ Miner Shift Productivity Dashboard")
    st.markdown("### 📊 Comprehensive Month-wise Shift Analysis")

    # Page selection
    st.sidebar.markdown("---")
    st.sidebar.markdown("## 📄 Navigation")
    page = st.sidebar.radio(
        "Select Page:",
        ["📊 Dashboard", "📖 Assumptions & Methodology", "📊 Data Insights"],
        index=0
    )

    st.markdown("---")

    # Display selected page
    try:
        if page == "📊 Dashboard":
            show_dashboard_page()
        elif page == "📖 Assumptions & Methodology":
            result_df = get_shift_analysis()
            show_assumptions_page(result_df)
        else:
            result_df = get_shift_analysis()
            show_data_insights_page(result_df)
    except Exception as e:
        st.error(f"⚠️ **An error occurred:** {str(e)}")
        with st.expander("🔍 View Full Error Details"):
            import traceback
            st.code(traceback.format_exc())

if __name__ == "__main__":
    main()