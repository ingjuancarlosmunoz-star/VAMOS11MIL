"""
Bodegas potenciales a la redonda.
Lee la base potencial del repositorio (base_potencial.xlsx o base_potencial.csv)
y cuenta cuántas hay a 1 km, 2 km, 3 km... de tu ubicación actual.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st
from streamlit_geolocation import streamlit_geolocation

st.set_page_config(page_title="Bodegas potenciales", page_icon="🏪", layout="wide")

CARPETA = Path(__file__).parent
COLORES = [[27, 158, 119], [217, 95, 2], [117, 112, 179], [231, 41, 138], [102, 166, 30],
           [230, 171, 2], [166, 118, 29], [102, 102, 102], [31, 120, 180], [178, 223, 138]]


@st.cache_data
def cargar_base() -> pd.DataFrame:
    """Busca base_potencial.* en el repo; si no existe, usa el primer CSV/Excel que encuentre."""
    candidatos = sorted(CARPETA.glob("base_potencial.*")) + sorted(
        p for ext in ("*.xlsx", "*.xls", "*.csv") for p in CARPETA.glob(ext)
    )
    if not candidatos:
        raise FileNotFoundError("No encontré la base. Sube 'base_potencial.xlsx' (o .csv) al repositorio.")
    archivo = candidatos[0]
    if archivo.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(archivo)
    else:
        df = pd.read_csv(archivo, sep=None, engine="python", encoding_errors="ignore")

    cols = {str(c).lower().strip(): c for c in df.columns}
    lat_c = next((cols[c] for c in ["lat", "latitud", "latitude", "y", "coord_y"] if c in cols), None)
    lon_c = next((cols[c] for c in ["lon", "lng", "long", "longitud", "longitude", "x", "coord_x"] if c in cols), None)
    if not lat_c or not lon_c:
        raise ValueError(f"La base '{archivo.name}' necesita columnas de latitud y longitud. "
                         f"Columnas encontradas: {list(df.columns)}")
    nom_c = next((cols[c] for c in ["nombre", "name", "razon_social", "razón social", "cliente",
                                    "bodega", "nombre_comercial", "negocio", "subcanal"] if c in cols), None)

    base = pd.DataFrame({
        "nombre": df[nom_c].astype(str) if nom_c else "Bodega",
        "lat": pd.to_numeric(df[lat_c].astype(str).str.replace(",", "."), errors="coerce"),
        "lon": pd.to_numeric(df[lon_c].astype(str).str.replace(",", "."), errors="coerce"),
    })
    base = base.dropna(subset=["lat", "lon"])
    # Corrige coordenadas con el signo cambiado (Perú: latitud y longitud negativas)
    base["lat"] = -base["lat"].abs()
    base["lon"] = -base["lon"].abs()
    # Descarta puntos vacíos o fuera de Perú
    base = base[base["lat"].between(-18.6, 0.1) & base["lon"].between(-81.5, -68.5)]
    return base.reset_index(drop=True)


def distancia_km(lat, lon, lats, lons):
    lat, lon, lats, lons = map(np.radians, (lat, lon, lats, lons))
    a = np.sin((lats - lat) / 2) ** 2 + np.cos(lat) * np.cos(lats) * np.sin((lons - lon) / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.sqrt(a))


# ---------------------------------------------------------------- pantalla
st.title("🏪 Bodegas potenciales a la redonda")

try:
    base = cargar_base()
except Exception as ex:
    st.error(str(ex))
    st.stop()

c1, c2 = st.columns([1, 3])
with c1:
    st.write("📍 Permitir ubicación actual")
    geo = streamlit_geolocation()
with c2:
    radio = st.slider("Radio a la redonda (km)", min_value=1, max_value=10, value=3, step=1)

if not geo or geo.get("latitude") is None:
    st.info("Pulsa el botón 📍 y acepta el permiso de ubicación del navegador.")
    st.stop()

lat, lon = geo["latitude"], geo["longitude"]
base = base.assign(dist=distancia_km(lat, lon, base["lat"].values, base["lon"].values))
cerca = base[base["dist"] <= radio].copy()

# conteo acumulado por km
cols = st.columns(radio)
for k in range(1, radio + 1):
    cols[k - 1].metric(f"A {k} km", int((base["dist"] <= k).sum()))

# ---------------------------------------------------------------- mapa
ang = np.linspace(0, 2 * np.pi, 121)
anillos = [{
    "path": [[lon + (k / (111.32 * np.cos(np.radians(lat)))) * np.cos(a),
              lat + (k / 111.32) * np.sin(a)] for a in ang],
    "color": COLORES[(k - 1) % len(COLORES)],
    "texto": f"{k} km: {int((base['dist'] <= k).sum())} bodegas",
} for k in range(1, radio + 1)]

if len(cerca):
    anillo = np.clip(np.ceil(cerca["dist"]).astype(int), 1, radio)
    cerca["color"] = [COLORES[(k - 1) % len(COLORES)] for k in anillo]
    cerca["texto"] = cerca["nombre"] + " · " + (cerca["dist"] * 1000).round().astype(int).astype(str) + " m"

yo = pd.DataFrame([{"lat": lat, "lon": lon, "texto": "Tú estás aquí"}])
zoom = {1: 14.5, 2: 13.5, 3: 13}.get(radio, 12 if radio <= 5 else 11)

st.pydeck_chart(pdk.Deck(
    layers=[
        pdk.Layer("PathLayer", anillos, get_path="path", get_color="color",
                  width_min_pixels=2, pickable=True),
        pdk.Layer("ScatterplotLayer", cerca, get_position="[lon, lat]", get_fill_color="color",
                  get_radius=25, radius_min_pixels=4, pickable=True),
        pdk.Layer("ScatterplotLayer", yo, get_position="[lon, lat]", get_fill_color=[220, 20, 60],
                  get_line_color=[255, 255, 255], stroked=True, line_width_min_pixels=2,
                  get_radius=40, radius_min_pixels=8, pickable=True),
    ],
    initial_view_state=pdk.ViewState(latitude=lat, longitude=lon, zoom=zoom),
    map_style=None,
    tooltip={"text": "{texto}"},
), height=650)
