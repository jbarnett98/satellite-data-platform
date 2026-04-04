import streamlit as st
import pandas as pd
import sys
from pathlib import Path
from scripts.config import ENRICHED_DATA_PATH

sys.path.append(str(Path(__file__).resolve().parent.parent / "scripts"))

st.set_page_config(page_title="Satellite Dashboard", layout="wide")

st.title("🛰️ Satellite Analytics Dashboard")

# Load data
df = pd.read_csv(ENRICHED_DATA_PATH)

# Metrics
st.subheader("Overview")

col1, col2 = st.columns(2)

col1.metric("Total Satellites", len(df))
col2.metric("Average Inclination", round(df["inclination"].mean(), 2))

# Table
st.subheader("Satellite Data")

st.dataframe(df)

st.subheader("Orbit Distribution")

orbit_counts = df["orbit_type"].value_counts()

st.bar_chart(orbit_counts)

st.subheader("Filter")

orbit_filter = st.selectbox(
    "Select Orbit Type",
    options=["All", "LEO", "MEO", "GEO"]
)

if orbit_filter != "All":
    df = df[df["orbit_type"] == orbit_filter]

st.dataframe(df)

st.button("Refresh Data")