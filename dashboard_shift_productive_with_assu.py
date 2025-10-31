import streamlit as st
import pandas as pd
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
# Memory-Efficient Data Loading
# ---------------------------

def assign_shift(hour):
    """Assign shift based on hour of day"""
    if 8 <= hour < 20:
        return 1
    else:
        return 2

@st.cache_data(ttl=3600, max_entries=1)
def load_and_process_data():
    """Load and process data in memory-efficient way"""
    url = "https://huggingface.co/datasets/Atharvaaaaaaaaaa/Data/resolve/main/data.parquet"
    
    try:
        with st.spinner('Loading data (this may take a moment)...'):
            # Read only necessary columns to save memory
            df = pd.read_parquet(
                url,
                columns=['miner_id', 'ug_session_id', 'last_ug']
            )
            
            st.info(f"📥 Loaded {len(df):,} records")
            
            # Process in efficient way
            # Convert timestamp
            df['last_ug'] = pd.to_datetime(df['last_ug'], utc=True)
            df['last_ug'] = df['last_ug'].dt.tz_convert('America/New_York')
            
            # Filter to 2025 only BEFORE aggregation (reduces memory)
            df = df[df['last_ug'] >= '2025-01-01']
            
            st.info(f"📊 Processing {len(df):,} records from 2025...")
            
            # Group and aggregate (this reduces data size significantly)
            session_stats = df.groupby(['miner_id', 'ug_session_id'], as_index=False).agg({
                'last_ug': ['min', 'max']
            })
            
            session_stats.columns = ['miner_id', 'ug_session_id', 'session_start', 'session_end']
            
            # Clear original dataframe from memory
            del df
            gc.collect()
            
            # Calculate hours worked
            session_stats['hours_worked'] = (
                (session_stats['session_end'] - session_stats['session_start']).dt.total_seconds() / 3600
            )
            
            # Remove negative or zero duration sessions
            session_stats = session_stats[session_stats['hours_worked'] > 0]
            
            # Create readable format
            session_stats['hours_worked_readable'] = session_stats['hours_worked'].apply(
                lambda h: f"{int(h)}h {int((h % 1) * 60)}m"
            )
            
            # Assign shift based on session start hour
            session_stats['start_hour'] = session_stats['session_start'].dt.hour
            session_stats['assigned_shift_id'] = session_stats['start_hour'].apply(assign_shift)
            
            # Add date/time columns (only what's needed)
            session_stats['month_year'] = session_stats['session_start'].dt.strftime('%b %Y')
            session_stats['sort_key'] = session_stats['session_start'].dt.strftime('%Y-%m')
            
            # Convert to categorical to save memory
            session_stats['month_year'] = session_stats['month_year'].astype('category')
            session_stats['assigned_shift_id'] = session_stats['assigned_shift_id'].astype('int8')
            session_stats['miner_id'] = session_stats['miner_id'].astype('int32')
            
            # Drop unnecessary columns
            session_stats = session_stats.drop(columns=['start_hour'])
            
            st.success(f"✅ Processed {len(session_stats):,} sessions")
            
            return session_stats
                
    except Exception as e:
        st.error(f"❌ Failed to load data: {str(e)}")
        raise

# ---------------------------
# Page Functions
# ---------------------------

def show_data_insights_page(filtered_df):
    """Display data insights"""
    st.title("📊 Data Insights")
    st.markdown("### Session Duration Analysis")
    st.markdown("---")
    
    # Calculate statistics
    mean_hours = filtered_df['hours_worked'].mean()
    median_hours = filtered_df['hours_worked'].median()
    
    # Categorize sessions
    short_sessions = len(filtered_df[filtered_df['hours_worked'] < 5])
    normal_sessions = len(filtered_df[(filtered_df['hours_worked'] >= 5) & (filtered_df['hours_worked'] <= 12)])
    extended_sessions = len(filtered_df[(filtered_df['hours_worked'] > 12) & (filtered_df['hours_worked'] <= 16)])
    anomalous_sessions = len(filtered_df[filtered_df['hours_worked'] > 16])
    total_sessions = len(filtered_df)
    
    # Quick Stats
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Mean", f"{mean_hours:.2f}h")
    with col2:
        st.metric("Median", f"{median_hours:.2f}h")
    with col3:
        st.metric("Difference", f"{abs(median_hours - mean_hours):.2f}h")
    with col4:
        st.metric("Total Sessions", f"{total_sessions:,}")
    
    st.markdown("---")
    
    # Distribution Chart
    col1, col2 = st.columns([2.5, 1])
    
    with col1:
        fig = go.Figure()
        
        fig.add_trace(go.Histogram(
            x=filtered_df['hours_worked'],
            nbinsx=50,
            marker_color='#636EFA',
            opacity=0.7
        ))
        
        fig.add_vline(x=mean_hours, line_dash="dash", line_color="red", line_width=2,
                     annotation_text=f"Mean: {mean_hours:.2f}h")
        fig.add_vline(x=median_hours, line_dash="dash", line_color="green", line_width=2,
                     annotation_text=f"Median: {median_hours:.2f}h")
        
        fig.update_layout(
            xaxis_title="Hours Worked",
            yaxis_title="Count",
            template='plotly_dark',
            height=400,
            showlegend=False
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.markdown("**Categories:**")
        st.metric("🔴 Short (<5h)", f"{short_sessions:,}", f"{(short_sessions/total_sessions*100):.1f}%")
        st.metric("🟢 Normal (5-12h)", f"{normal_sessions:,}", f"{(normal_sessions/total_sessions*100):.1f}%")
        st.metric("🟡 Extended (12-16h)", f"{extended_sessions:,}", f"{(extended_sessions/total_sessions*100):.1f}%")
        st.metric("🔴 Anomalous (>16h)", f"{anomalous_sessions:,}", f"{(anomalous_sessions/total_sessions*100):.1f}%")

def show_assumptions_page():
    """Display methodology"""
    st.title("📖 Assumptions & Methodology")
    st.markdown("---")
    
    st.markdown("#### 🎯 Overview")
    st.info("""
    This dashboard analyzes miner productivity by calculating work hours per session and 
    assigning each session to a shift based on session start time.
    """)
    
    st.markdown("#### ⏰ Shift Definitions")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.success("""
        **🌅 Shift 1 (Day Shift)**
        - Hours: 08:00 - 20:00
        - Duration: 12 hours
        """)
    
    with col2:
        st.info("""
        **🌙 Shift 2 (Night Shift)**
        - Hours: 20:00 - 08:00
        - Duration: 12 hours
        """)
    
    st.markdown("---")
    
    st.markdown("#### 📋 Key Points")
    
    st.markdown("""
    **Session Calculation:**
    - Session duration = last activity - first activity
    - Assigned to shift based on session start hour
    - All times in America/New_York timezone
    
    **Data:**
    - January 2025 onwards only
    - Excludes sessions with zero duration
    """)

def show_dashboard_page():
    """Display main dashboard"""
    try:
        result_df = load_and_process_data()
        
        # Get unique miners efficiently
        all_miners = sorted(result_df['miner_id'].unique())
        
        # Sidebar filters
        st.sidebar.markdown("## 🎛️ Filters")
        st.sidebar.markdown("---")
        
        # Month filter
        month_options = result_df.groupby(['sort_key', 'month_year']).size().reset_index()[['sort_key', 'month_year']]
        month_options = month_options.sort_values('sort_key', ascending=True)
        month_display = ["All Months"] + month_options['month_year'].tolist()
        
        selected_month = st.sidebar.selectbox("📅 Month", month_display, index=0)
        
        # Shift filter
        selected_shift = st.sidebar.selectbox(
            "⏰ Shift",
            ["All Shifts", "Shift 1", "Shift 2"],
            index=0
        )
        
        # Miner filter
        st.sidebar.markdown("---")
        selected_miners = st.sidebar.multiselect(
            "👷 Miners (Optional)",
            options=all_miners,
            default=[]
        )
        
        # Apply filters
        filtered_df = result_df.copy()
        
        if selected_month != "All Months":
            filtered_df = filtered_df[filtered_df['month_year'] == selected_month]
        
        if selected_shift != "All Shifts":
            shift_num = int(selected_shift.split()[1])
            filtered_df = filtered_df[filtered_df['assigned_shift_id'] == shift_num]
        
        if selected_miners:
            filtered_df = filtered_df[filtered_df['miner_id'].isin(selected_miners)]
        
        # Key Metrics
        st.markdown("### 📈 Key Metrics")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("🔢 Sessions", f"{len(filtered_df):,}")
        
        with col2:
            st.metric("👷 Miners", f"{filtered_df['miner_id'].nunique():,}")
        
        with col3:
            st.metric("⏱️ Median Hours", f"{filtered_df['hours_worked'].median():.2f}")
        
        with col4:
            st.metric("⏰ Total Hours", f"{filtered_df['hours_worked'].sum():,.0f}")
        
        st.markdown("---")
        
        # Aggregate for charts (reduces memory)
        monthly_agg = filtered_df.groupby(['sort_key', 'month_year', 'assigned_shift_id'], observed=True).agg({
            'hours_worked': ['sum', 'median', 'count'],
            'miner_id': 'nunique'
        }).reset_index()
        
        monthly_agg.columns = ['sort_key', 'month', 'shift_id', 'total_hours', 'median_hours', 'session_count', 'unique_miners']
        monthly_agg = monthly_agg.sort_values('sort_key')
        
        # Tabs
        tab1, tab2 = st.tabs(["📊 Charts", "📋 Data"])
        
        with tab1:
            col1, col2 = st.columns(2)
            
            with col1:
                fig1 = px.line(
                    monthly_agg,
                    x='month',
                    y='total_hours',
                    color='shift_id',
                    markers=True,
                    title='Total Work Hours',
                    labels={'total_hours': 'Hours', 'month': 'Month', 'shift_id': 'Shift'}
                )
                fig1.update_layout(template='plotly_dark', height=350)
                st.plotly_chart(fig1, use_container_width=True)
            
            with col2:
                fig2 = px.line(
                    monthly_agg,
                    x='month',
                    y='median_hours',
                    color='shift_id',
                    markers=True,
                    title='Median Hours per Session',
                    labels={'median_hours': 'Hours', 'month': 'Month', 'shift_id': 'Shift'}
                )
                fig2.update_layout(template='plotly_dark', height=350)
                st.plotly_chart(fig2, use_container_width=True)
            
            col3, col4 = st.columns(2)
            
            with col3:
                fig3 = px.bar(
                    monthly_agg,
                    x='month',
                    y='session_count',
                    color='shift_id',
                    title='Session Count',
                    labels={'session_count': 'Sessions', 'month': 'Month', 'shift_id': 'Shift'}
                )
                fig3.update_layout(template='plotly_dark', height=350)
                st.plotly_chart(fig3, use_container_width=True)
            
            with col4:
                fig4 = px.line(
                    monthly_agg,
                    x='month',
                    y='unique_miners',
                    color='shift_id',
                    markers=True,
                    title='Active Miners',
                    labels={'unique_miners': 'Miners', 'month': 'Month', 'shift_id': 'Shift'}
                )
                fig4.update_layout(template='plotly_dark', height=350)
                st.plotly_chart(fig4, use_container_width=True)
        
        with tab2:
            show_detail = st.checkbox("Show individual sessions", value=False)
            
            if show_detail:
                # Show sample if too large
                if len(filtered_df) > 10000:
                    st.warning("⚠️ Showing first 10,000 records only")
                    display_df = filtered_df.head(10000)
                else:
                    display_df = filtered_df
                
                display_df = display_df[['miner_id', 'assigned_shift_id', 'session_start', 'session_end', 
                                          'hours_worked', 'month_year']].copy()
                display_df.columns = ['Miner', 'Shift', 'Start', 'End', 'Hours', 'Month']
                st.dataframe(display_df, use_container_width=True, height=400)
            else:
                st.dataframe(monthly_agg.drop(columns=['sort_key']), use_container_width=True, height=400)
            
            # Export
            st.markdown("---")
            csv = filtered_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Download CSV",
                csv,
                f'miner_data_{selected_month}.csv',
                'text/csv'
            )

    except Exception as e:
        st.error(f"⚠️ Error: {str(e)}")
        with st.expander("🔍 Details"):
            import traceback
            st.code(traceback.format_exc())

# ---------------------------
# Main App
# ---------------------------

def main():
    """Main application"""
    st.title("⛏️ Miner Shift Productivity Dashboard")
    st.markdown("### 📊 Month-wise Shift Analysis")

    # Page selection
    st.sidebar.markdown("---")
    st.sidebar.markdown("## 📄 Pages")
    page = st.sidebar.radio(
        "",
        ["📊 Dashboard", "📖 Methodology", "📊 Insights"]
    )

    st.markdown("---")

    # Display page
    try:
        if page == "📊 Dashboard":
            show_dashboard_page()
        elif page == "📖 Methodology":
            show_assumptions_page()
        else:
            result_df = load_and_process_data()
            show_data_insights_page(result_df)
    except Exception as e:
        st.error(f"⚠️ Error: {str(e)}")
        with st.expander("🔍 Details"):
            import traceback
            st.code(traceback.format_exc())

if __name__ == "__main__":
    main()