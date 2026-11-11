"""Energía y transporte marítimo con fuentes abiertas.

- Tráfico diario de buques por estrechos y canales: IMF PortWatch (FMI), estimado con datos AIS. Sin clave.
  Se publica con unos días de retraso: sirve para ver tendencias semanales, no posiciones en directo.
- Activos energéticos (centrales, refinerías, pozos): OpenStreetMap vía Overpass. Sin clave.
"""
from __future__ import annotations

import re
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests

from .cache import con_cache
from .config import UA_OVERPASS, UA_WEB

PW_BASE = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
PW_DIARIO = f"{PW_BASE}/Daily_Chokepoints_Data/FeatureServer/0/query"
PW_ESTRECHOS = f"{PW_BASE}/PortWatch_chokepoints_database/FeatureServer/0/query"

NOMBRES_ES = {
    "Strait of Hormuz": "Estrecho de Ormuz",
    "Suez Canal": "Canal de Suez",
    "Bab el-Mandeb Strait": "Bab el-Mandeb (Mar Rojo)",
    "Panama Canal": "Canal de Panamá",
    "Malacca Strait": "Estrecho de Malaca",
    "Gibraltar Strait": "Estrecho de Gibraltar",
    "Bosporus Strait": "Bósforo",
    "Dover Strait": "Paso de Calais (Dover)",
    "Cape of Good Hope": "Cabo de Buena Esperanza",
    "Taiwan Strait": "Estrecho de Taiwán",
    "Oresund Strait": "Øresund",
    "Kerch Strait": "Estrecho de Kerch",
    "Lombok Strait": "Estrecho de Lombok",
    "Sunda Strait": "Estrecho de la Sonda",
    "Luzon Strait": "Estrecho de Luzón",
    "Korea Strait": "Estrecho de Corea",
}

POR_QUE_IMPORTA = {
    "Strait of Hormuz": "Salida marítima del crudo y el GNL del Golfo Pérsico. Sensible a petroleras, refinerías y precio del crudo.",
    "Suez Canal": "Ruta Asia–Europa para contenedores y energía. Si cae el tráfico, suben fletes y plazos.",
    "Bab el-Mandeb Strait": "Puerta sur del Mar Rojo: si se desvía, los buques rodean África (más coste y días).",
    "Panama Canal": "Contenedores, GNL/GLP y graneles agrícolas entre el Atlántico y el Pacífico.",
    "Malacca Strait": "Principal paso del crudo y las manufacturas hacia el este de Asia.",
    "Gibraltar Strait": "Entrada y salida del Mediterráneo: termómetro del comercio Europa–Asia–África.",
    "Bosporus Strait": "Crudo y cereales del Mar Negro.",
    "Dover Strait": "Tráfico del norte de Europa (puertos de Róterdam, Amberes, Hamburgo).",
    "Cape of Good Hope": "Ruta alternativa a Suez: sube cuando hay problemas en Mar Rojo.",
    "Taiwan Strait": "Cadena de la electrónica y los semiconductores de Asia oriental.",
}


# ----------------------------------------------------------------------------- PortWatch
def _consulta_pw(url: str, params: dict) -> list[dict]:
    r = requests.get(url, params={**params, "f": "json"}, headers=UA_WEB, timeout=40)
    r.raise_for_status()
    datos = r.json()
    if "error" in datos:
        raise RuntimeError(str(datos["error"]))
    return datos.get("features", [])


@con_cache(30 * 86400)
def estrechos() -> pd.DataFrame:
    """Catálogo de estrechos/canales con su posición (lat, lon)."""
    feats = _consulta_pw(
        PW_ESTRECHOS,
        {"where": "1=1", "outFields": "portid,portname", "returnGeometry": "true", "outSR": "4326", "resultRecordCount": 200},
    )
    filas = [
        {"portid": f["attributes"]["portid"], "nombre": f["attributes"]["portname"],
         "lon": f.get("geometry", {}).get("x"), "lat": f.get("geometry", {}).get("y")}
        for f in feats
    ]
    df = pd.DataFrame(filas).drop_duplicates("portid")
    df["nombre_es"] = df["nombre"].map(lambda x: NOMBRES_ES.get(x, x))
    return df.sort_values("nombre_es").reset_index(drop=True)


@con_cache(6 * 3600)
def pasos_diarios(portids: tuple, dias: int = 365) -> pd.DataFrame:
    """Buques por día en cada estrecho: totales, petroleros, carga seca, contenedores..."""
    desde = (date.today() - timedelta(days=dias)).isoformat()
    ids = ",".join(f"'{p}'" for p in portids)
    filas, offset = [], 0
    while True:
        feats = _consulta_pw(
            PW_DIARIO,
            {
                "where": f"portid IN ({ids}) AND date >= DATE '{desde}'",
                "outFields": "date,portid,portname,n_tanker,n_cargo,n_container,n_dry_bulk,n_total,capacity_tanker",
                "orderByFields": "date ASC",
                "returnGeometry": "false",
                "resultOffset": offset,
                "resultRecordCount": 1000,
            },
        )
        filas += [f["attributes"] for f in feats]
        if len(feats) < 1000:
            break
        offset += 1000
    df = pd.DataFrame(filas)
    if df.empty:
        return df
    df["fecha"] = pd.to_datetime(df["date"])
    df["estrecho"] = df["portname"].map(lambda x: NOMBRES_ES.get(x, x))
    return df.drop(columns="date")


def resumen_estrechos(df: pd.DataFrame) -> pd.DataFrame:
    """Media de la última semana frente a las 4 semanas anteriores, por estrecho."""
    filas = []
    for nombre, g in df.sort_values("fecha").groupby("estrecho"):
        if len(g) < 14:
            continue
        reciente, previo = g.tail(7), g.iloc[-35:-7]

        def var(col):
            base = previo[col].mean()
            return (reciente[col].mean() / base - 1) * 100 if base and base > 0 else np.nan

        filas.append(
            {
                "Estrecho": nombre,
                "Último dato": g["fecha"].max().date().isoformat(),
                "Petroleros/día": reciente["n_tanker"].mean(),
                "Petroleros vs 4 sem previas %": var("n_tanker"),
                "Buques/día": reciente["n_total"].mean(),
                "Buques vs 4 sem previas %": var("n_total"),
            }
        )
    return pd.DataFrame(filas).sort_values("Buques/día", ascending=False).reset_index(drop=True)


# ----------------------------------------------------------------------------- OpenStreetMap
ZONAS = {
    "España y Portugal": (36.0, -9.6, 43.9, 3.4),
    "Reino Unido e Irlanda": (49.8, -10.7, 60.9, 2.0),
    "Mar del Norte": (51.0, -4.0, 62.0, 10.0),
    "Alemania y Benelux": (47.2, 2.5, 55.1, 15.1),
    "Golfo Pérsico": (22.5, 47.0, 31.0, 58.0),
    "Texas y Golfo de México": (25.0, -98.5, 31.0, -88.0),
}
CAPAS = ["Centrales eléctricas", "Refinerías", "Pozos y plataformas de petróleo/gas"]
FUENTES_CENTRAL = ["(todas)", "gas", "coal", "nuclear", "hydro", "solar", "wind", "oil", "biomass"]
MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def consulta_overpass(capa: str, bbox: tuple, fuente: str | None = None, limite: int = 3000) -> str:
    s, w, n, e = bbox
    caja = f"({s},{w},{n},{e})"
    if capa == "Centrales eléctricas":
        filtro = '["power"="plant"]' + (f'["plant:source"~"{fuente}"]' if fuente and fuente != "(todas)" else "")
        cuerpo = f"nwr{filtro}{caja};"
    elif capa == "Refinerías":
        cuerpo = f'nwr["industrial"="refinery"]{caja};'
    else:
        cuerpo = f'nwr["man_made"="petroleum_well"]{caja};\n  nwr["man_made"="offshore_platform"]{caja};'
    return f"[out:json][timeout:90];\n(\n  {cuerpo}\n);\nout center tags {limite};"


def _mw(valor) -> float:
    """Convierte etiquetas OSM tipo '1.2 GW' o '350 MW' a MW (sin unidad = vatios, como manda OSM)."""
    if not valor:
        return np.nan
    m = re.match(r"\s*([\d.,]+)\s*([kKmMgG]?[wW])?", str(valor))
    if not m:
        return np.nan
    num = m.group(1)
    num = num.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", num) else num.replace(",", ".")
    try:
        x = float(num)
    except ValueError:
        return np.nan
    unidad = (m.group(2) or "W").lower()
    return x * {"w": 1e-6, "kw": 1e-3, "mw": 1.0, "gw": 1e3}.get(unidad, 1e-6)


def parsear_overpass(datos: dict, capa: str) -> pd.DataFrame:
    filas = []
    for el in datos.get("elements", []):
        lat = el.get("lat", el.get("center", {}).get("lat"))
        lon = el.get("lon", el.get("center", {}).get("lon"))
        if lat is None or lon is None:
            continue
        t = el.get("tags", {})
        filas.append(
            {
                "capa": capa,
                "nombre": t.get("name", "(sin nombre)"),
                "operador": t.get("operator", t.get("owner", "")),
                "fuente": t.get("plant:source", t.get("product", t.get("man_made", ""))),
                "potencia_mw": _mw(t.get("plant:output:electricity")),
                "lat": lat,
                "lon": lon,
            }
        )
    return pd.DataFrame(filas)


@con_cache(7 * 86400)
def activos(capa: str, bbox: tuple, fuente: str | None = None) -> pd.DataFrame:
    """Activos energéticos de OpenStreetMap en una zona. Prueba varios servidores públicos."""
    consulta = consulta_overpass(capa, bbox, fuente)
    ultimo_error = None
    for intento in range(3):
        for url in MIRRORS:
            try:
                r = requests.post(url, data={"data": consulta}, headers=UA_OVERPASS, timeout=110)
                if r.status_code != 200:
                    ultimo_error = f"{url} respondió {r.status_code}"
                    continue
                datos = r.json()
                if "runtime error" in str(datos.get("remark", "")):
                    ultimo_error = "la consulta tardó demasiado: prueba con una zona más pequeña o filtra por fuente"
                    continue
                return parsear_overpass(datos, capa)
            except (requests.RequestException, ValueError) as e:
                ultimo_error = f"{url}: {type(e).__name__}"
        time.sleep(5 * (intento + 1))  # los servidores públicos piden espera creciente
    raise RuntimeError(f"OpenStreetMap no respondió ({ultimo_error}). Inténtalo de nuevo en unos minutos.")


def resumen_operadores(df: pd.DataFrame, top: int = 15) -> pd.DataFrame:
    """Quién opera más instalaciones/potencia en la zona (útil para enlazar activos con empresas cotizadas)."""
    if df.empty:
        return df
    g = df[df["operador"].str.strip() != ""].groupby("operador")
    out = g.agg(instalaciones=("nombre", "count"), potencia_mw=("potencia_mw", "sum")).reset_index()
    return out.sort_values(["potencia_mw", "instalaciones"], ascending=False).head(top).reset_index(drop=True)
