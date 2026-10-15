
import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from streamlit_folium import folium_static
from folium.plugins import MarkerCluster
import fiona
from shapely.geometry import shape, MultiPolygon

# Set Streamlit page layout
st.set_page_config(layout="wide")

st.markdown(
    '''
    <style>
    .css-18e3th9 { padding-top: 0rem !important; padding-bottom: 0rem !important; }
    .css-1outpf7 { padding: 0rem !important; margin: 0rem !important; }
    </style>
    ''',
    unsafe_allow_html=True
)

# File paths
data_file = "Punjab_Sports_Constituency_Data.xlsx"
shapefile_path = "Punjab_Legislative_Constituency.shp"

# --- Load Constituency Polygons from Shapefile ---
features = []
with fiona.open(shapefile_path) as shapefile:
    for feature in shapefile:
        geom = shape(feature["geometry"])
        if isinstance(geom, MultiPolygon):
            geom = max(geom.geoms, key=lambda g: g.area)
        centroid = geom.centroid
        features.append({
            "AC_NAME": feature["properties"]["AC_NAME"],
            "centroid_x": centroid.x,
            "centroid_y": centroid.y,
            "geometry": geom
        })
gdf = gpd.GeoDataFrame(features, geometry="geometry")

# --- Load and Process the New Excel File ---
df = pd.read_excel(data_file)

# Rename columns to match app expectations
df = df.rename(columns={
    "Name of District": "District",
    "Name of Constituency": "Original_Constituency",
    "Name of Place": "Nursery",
    "AC_Name": "Closest_Match"
})

# Add missing columns if not present
if "Ownership (Dept. / School/ M.C./ Panchayat etc)" not in df.columns:
    df["Ownership (Dept. / School/ M.C./ Panchayat etc)"] = "Unknown"
if "Area / Acre" not in df.columns:
    df["Area / Acre"] = 0

# Rename those columns
df = df.rename(columns={
    "Ownership (Dept. / School/ M.C./ Panchayat etc)": "Ownership",
    "Area / Acre": "Area"
})

# Ensure required columns exist
df = df[["District", "Original_Constituency", "Closest_Match", "Nursery", "Ownership", "Area", "Game", "Lat", "Long"]]

# Convert Lat/Long to numeric and drop invalid rows
df["Latitude"] = pd.to_numeric(df["Lat"], errors="coerce")
df["Longitude"] = pd.to_numeric(df["Long"], errors="coerce")
df = df.dropna(subset=["Latitude", "Longitude"])

# Punjab center fallback
punjab_center = [30.9, 75.85]

# --- Function to Create Map ---
def create_map(df_filtered, gdf_full):
    unique_const = df_filtered["Closest_Match"].unique()
    gdf_filtered = gdf_full[gdf_full["AC_NAME"].isin(unique_const)].copy()

    if len(gdf_filtered) == 0:
        m = folium.Map(location=punjab_center, zoom_start=8, width="100%", height="90vh")
        folium.TileLayer(
            tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
            attr="Google Hybrid",
            name="Google Hybrid",
            overlay=False,
            control=True
        ).add_to(m)
        return m

    if len(gdf_filtered) == 1:
        row = gdf_filtered.iloc[0]
        center = [row["centroid_y"], row["centroid_x"]]
        zoom = 12
    else:
        bounds = gdf_filtered.total_bounds
        center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]
        zoom = 8

    m = folium.Map(location=center, zoom_start=zoom, width="100%", height="90vh")
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        attr="Google Hybrid",
        name="Google Hybrid",
        overlay=False,
        control=True
    ).add_to(m)

    for _, row in gdf_filtered.iterrows():
        folium.GeoJson(
            row["geometry"],
            name=row["AC_NAME"],
            style_function=lambda feature: {
                "fillColor": "transparent",
                "color": "yellow",
                "weight": 1,
                "fillOpacity": 0.5
            }
        ).add_to(m)

    if len(gdf_filtered) == 1:
        folium.Marker(
            location=[gdf_filtered.iloc[0]["centroid_y"], gdf_filtered.iloc[0]["centroid_x"]],
            icon=folium.DivIcon(
                html=f'<div style="font-size: 8pt; color: yellow;">{gdf_filtered.iloc[0]["AC_NAME"]}</div>'
            )
        ).add_to(m)

    sport_icons = {
        'Basketball': 'basketball-ball',
        'Volleyball': 'volleyball-ball',
        'Football': 'futbol',
        'Cricket': 'baseball-ball',
        'Hockey': 'hockey-puck',
    }

    marker_cluster = MarkerCluster().add_to(m)
    for _, row in df_filtered.iterrows():
        sport = row["Game"]
        icon_name = sport_icons.get(sport, "info-sign")
        folium.Marker(
            location=[row["Latitude"], row["Longitude"]],
            popup=(
                f"<b>{row['Nursery']}</b><br>"
                f"{row['Game']}<br>"
                f"{row['Ownership']}<br>"
                f"Area: {row['Area']}"
            ),
            icon=folium.Icon(color="blue", icon=icon_name, prefix="fa")
        ).add_to(marker_cluster)

    return m

# --- Build Streamlit UI ---
st.sidebar.title("Constituency-wise Sports Facilities Map")
st.sidebar.header("Filters")

df["Game"] = df["Game"].fillna("Unknown").astype(str)
all_sports = sorted(df["Game"].unique())
all_constituencies = sorted(df["Closest_Match"].unique())

selected_constituency = st.sidebar.selectbox("Select Constituency", ["All"] + all_constituencies)
selected_sport = st.sidebar.selectbox("Select Sport", ["All"] + all_sports)

df_filtered = df.copy()
if selected_constituency != "All":
    df_filtered = df_filtered[df_filtered["Closest_Match"] == selected_constituency]
if selected_sport != "All":
    df_filtered = df_filtered[df_filtered["Game"] == selected_sport]

m = create_map(df_filtered, gdf)
folium_static(m)
