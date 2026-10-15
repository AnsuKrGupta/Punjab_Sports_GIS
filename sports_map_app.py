
import streamlit as st
import pandas as pd
import geopandas as gpd
import json
import branca.colormap as cm
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster, Fullscreen
from shapely.geometry import MultiPolygon

# Set Streamlit page layout
st.set_page_config(layout="wide")

st.markdown(
    '''
    <style>
    /* Let the map fill the whole main area */
    [data-testid="stMainBlockContainer"], .block-container {
        padding: 3rem 0.5rem 0rem 0.5rem !important;
        max-width: 100% !important;
    }
    [data-testid="stCustomComponentV1"], iframe[title="streamlit_folium.st_folium"] {
        width: 100% !important;
        height: calc(100vh - 4.5rem) !important;
    }
    </style>
    ''',
    unsafe_allow_html=True
)

# File paths
data_file = "Punjab_Sports_Constituency_Data.xlsx"
shapefile_path = "Punjab_Legislative_Constituency.shp"
population_file = "Punjab_Constituency_Population.csv"
density_png = "population_density_2020.png"
density_meta = json.load(open("population_density_2020.json"))

# --- Load Constituency Polygons from Shapefile ---
features = []
for _, feature in gpd.read_file(shapefile_path).iterrows():
    geom = feature.geometry
    if isinstance(geom, MultiPolygon):
        geom = max(geom.geoms, key=lambda g: g.area)
    centroid = geom.centroid
    features.append({
        "AC_NO": int(feature["AC_NO"]),
        "AC_NAME": feature["AC_NAME"],
        "centroid_x": centroid.x,
        "centroid_y": centroid.y,
        "geometry": geom
    })
gdf = gpd.GeoDataFrame(features, geometry="geometry", crs="EPSG:4326")

# Estimated population per constituency (WorldPop 2020, 1km, UN-adjusted, summed inside each boundary)
population = pd.read_csv(population_file)
gdf = gdf.merge(population[["AC_NO", "Population_2020_est", "Area_km2", "Density_per_km2"]], on="AC_NO", how="left")

population_breaks = [0, 150000, 200000, 250000, 300000, 400000, 800000]
population_colors = ["#f2f0f7", "#dadaeb", "#bcbddc", "#9e9ac8", "#756bb1", "#54278f"]
population_colormap = cm.StepColormap(
    population_colors,
    index=population_breaks, vmin=0, vmax=800000,
)

# --- Population Layers (toggled from the map's layer control) ---
def add_population_layers(m, gdf_full):
    folium.raster_layers.ImageOverlay(
        image=density_png,
        bounds=density_meta["bounds"],
        name="Population density grid (WorldPop 2020)",
        opacity=0.75,
        interactive=False,
        show=False,
    ).add_to(m)

    layer_data = gdf_full[["AC_NAME", "Population_2020_est", "Area_km2", "Density_per_km2", "geometry"]].copy()
    layer_data["Population"] = layer_data["Population_2020_est"].map("{:,.0f}".format)
    layer_data["Density"] = layer_data["Density_per_km2"].map("{:,.0f} / km²".format)
    layer_data["Area"] = layer_data["Area_km2"].map("{:,.1f} km²".format)
    folium.GeoJson(
        layer_data.drop(columns=["Area_km2", "Density_per_km2"]),
        name="Estimated population by constituency",
        show=False,
        style_function=lambda feature: {
            "fillColor": population_colormap(feature["properties"]["Population_2020_est"]),
            "color": "#ffffff",
            "weight": 0.5,
            "fillOpacity": 0.7,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["AC_NAME", "Population", "Area", "Density"],
            aliases=["Constituency", "Population (est. 2020)", "Area", "Density"],
        ),
    ).add_to(m)

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
if "Coordinate_Fix" not in df.columns:
    df["Coordinate_Fix"] = None
df = df[["District", "Original_Constituency", "Closest_Match", "Nursery", "Ownership", "Area", "Game", "Lat", "Long", "Coordinate_Fix"]]

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
        m = folium.Map(location=punjab_center, zoom_start=8, width="100%", height="100%")
        folium.TileLayer(
            tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
            attr="Google Hybrid",
            name="Google Hybrid",
            overlay=False,
            control=True
        ).add_to(m)
        add_population_layers(m, gdf_full)
        return m

    if len(gdf_filtered) == 1:
        row = gdf_filtered.iloc[0]
        center = [row["centroid_y"], row["centroid_x"]]
        zoom = 12
    else:
        bounds = gdf_filtered.total_bounds
        center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]
        zoom = 8

    m = folium.Map(location=center, zoom_start=zoom, width="100%", height="100%")
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        attr="Google Hybrid",
        name="Google Hybrid",
        overlay=False,
        control=True
    ).add_to(m)
    add_population_layers(m, gdf_full)

    boundaries = folium.FeatureGroup(name="Constituency boundaries").add_to(m)
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
        ).add_to(boundaries)

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

    marker_cluster = MarkerCluster(name="Sports facilities").add_to(m)
    for _, row in df_filtered.iterrows():
        sport = row["Game"]
        icon_name = sport_icons.get(sport, "info-sign")
        fix_note = row["Coordinate_Fix"] if isinstance(row["Coordinate_Fix"], str) else ""
        approximate = fix_note.startswith("Approximate")
        folium.Marker(
            location=[row["Latitude"], row["Longitude"]],
            popup=folium.Popup(
                f"<b>{row['Nursery']}</b><br>"
                f"{row['Game']}<br>"
                f"{row['Ownership']}<br>"
                f"Area: {row['Area']}"
                + (f"<br><i style='color:#b45309'>Location corrected: {fix_note}</i>" if fix_note else ""),
                max_width=300,
            ),
            icon=folium.Icon(color="orange" if approximate else "blue", icon=icon_name, prefix="fa")
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

def legend_html(breaks, colors, fmt):
    rows = "".join(
        f'<div><span style="display:inline-block;width:14px;height:12px;background:{c};margin-right:6px;'
        f'border:1px solid #999"></span>{fmt(lo)}{"+" if i == len(colors) - 1 else " – " + fmt(breaks[i + 1])}</div>'
        for i, (lo, c) in enumerate(zip(breaks, colors))
    )
    return f'<div style="font-size:0.8rem;line-height:1.5">{rows}</div>'

st.sidebar.caption(
    "Blue markers: facility location as recorded. Orange markers: approximate location "
    "(the original coordinates were invalid or missing; click a marker for details)."
)

with st.sidebar.expander("Population layers", expanded=False):
    st.caption(
        "Turn these on from the layers button at the top right of the map. "
        "Source: WorldPop 2020, 1 km grid, UN-adjusted (worldpop.org)."
    )
    st.markdown("**Estimated population by constituency**")
    st.markdown(legend_html(population_breaks, population_colors, lambda v: f"{v / 1000:,.0f}k"), unsafe_allow_html=True)
    st.markdown("**Population density grid** (people per ~1 km² cell)")
    st.markdown(legend_html(density_meta["breaks"], density_meta["colors"], lambda v: f"{v:,}"), unsafe_allow_html=True)
    st.caption(
        "Constituency figures are estimates: the 1 km grid is summed inside each boundary, and some "
        "urban boundaries in the shapefile are offset from the city centres, so city seats may be "
        "undercounted and their neighbours overcounted. The density grid does not depend on the boundaries."
    )

df_filtered = df.copy()
if selected_constituency != "All":
    df_filtered = df_filtered[df_filtered["Closest_Match"] == selected_constituency]
if selected_sport != "All":
    df_filtered = df_filtered[df_filtered["Game"] == selected_sport]

m = create_map(df_filtered, gdf)
Fullscreen(position="topleft").add_to(m)
folium.LayerControl(collapsed=True).add_to(m)
st_folium(m, use_container_width=True, height=800, returned_objects=[])
