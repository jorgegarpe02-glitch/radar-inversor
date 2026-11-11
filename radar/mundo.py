"""Mapa mundial: economía por país, alertas, rutas marítimas, petroleros y activos (minas, centrales, refinerías, GNL).

Fuentes gratuitas:
- FMI World Economic Outlook (crecimiento, inflación, paro y deuda; incluye la estimación del año en curso).
  Si el FMI no responde, Banco Mundial (último año disponible).
- ETF de bolsa por país (Yahoo Finance): cómo va su bolsa en el año, en dólares.
- GDACS (ONU / Comisión Europea): terremotos, ciclones, inundaciones, sequías e incendios con alerta naranja o roja.
- FMI PortWatch: rutas marítimas, escalas diarias de petroleros por puerto y tránsitos por estrechos.
- Wikidata: minas por mineral (incluye minas pequeñas o históricas).
- Global Power Plant Database (WRI): ~35.000 centrales eléctricas del mundo (datos de 2021).
- datos/activos_clave.csv: grandes refinerías, terminales de GNL y minas principales (ubicación aproximada).
- aisstream.io (opcional, clave gratuita): posiciones de buques en directo.
"""
from __future__ import annotations

import io
import json
import time
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .cache import con_cache
from .config import UA_WEB

CARPETA_DATOS = Path(__file__).resolve().parent.parent / "datos"
PW = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"

# ----------------------------------------------------------------------------- economía por país
INDICADORES = {  # clave: (código FMI, código Banco Mundial, nombre, unidad)
    "crecimiento": ("NGDP_RPCH", "NY.GDP.MKTP.KD.ZG", "Crecimiento del PIB", "%"),
    "inflacion": ("PCPIPCH", "FP.CPI.TOTL.ZG", "Inflación", "%"),
    "paro": ("LUR", "SL.UEM.TOTL.ZS", "Paro", "%"),
    "deuda": ("GGXWDG_NGDP", "GC.DOD.TOTL.GD.ZS", "Deuda pública", "% del PIB"),
}


def _get_json(url: str, params: dict | None = None, timeout: int = 40):
    r = requests.get(url, params=params, headers={**UA_WEB, "Accept": "application/json"}, timeout=timeout)
    r.raise_for_status()
    return r.json()


@con_cache(7 * 86400)
def _fmi(indicador: str) -> dict:
    """{ISO3: {año: valor}} del FMI DataMapper."""
    return _get_json(f"https://www.imf.org/external/datamapper/api/v1/{indicador}")["values"][indicador]


@con_cache(30 * 86400)
def _fmi_paises() -> dict:
    datos = _get_json("https://www.imf.org/external/datamapper/api/v1/countries")["countries"]
    return {k: v.get("label") for k, v in datos.items() if v.get("label")}


@con_cache(30 * 86400)
def _bm_paises() -> pd.DataFrame:
    """Países (sin agregados regionales) con nombre en español e inglés."""
    en = _get_json("https://api.worldbank.org/v2/country", {"format": "json", "per_page": 400})[1]
    try:
        es = {f["id"]: f["name"] for f in _get_json("https://api.worldbank.org/v2/es/country", {"format": "json", "per_page": 400})[1]}
    except Exception:  # noqa: BLE001
        es = {}
    return pd.DataFrame([{"iso3": f["id"], "pais": es.get(f["id"], f["name"]), "pais_en": f["name"]}
                         for f in en if f["region"]["id"] != "NA"])


@con_cache(7 * 86400)
def _bm(indicador: str) -> pd.DataFrame:
    filas = _get_json(f"https://api.worldbank.org/v2/country/all/indicator/{indicador}",
                      {"format": "json", "mrnev": 1, "per_page": 400})[1] or []
    return pd.DataFrame([{"iso3": f["countryiso3code"], "valor": f["value"], "anio": int(f["date"])}
                         for f in filas if f.get("value") is not None and f.get("countryiso3code")])


def economia(anio: int | None = None) -> tuple[pd.DataFrame, str]:
    """Tabla por país con crecimiento (año en curso y anterior), inflación, paro y deuda. Devuelve (tabla, fuente)."""
    anio = anio or date.today().year
    try:
        nombres = _fmi_paises()
        tabla = pd.DataFrame({"iso3": list(nombres), "pais_en": list(nombres.values())})
        try:
            es = _bm_paises().set_index("iso3")["pais"]
        except Exception:  # noqa: BLE001
            es = pd.Series(dtype=str)
        tabla["pais"] = tabla["iso3"].map(es).fillna(tabla["pais_en"])
        for clave, (cod, _, _, _) in INDICADORES.items():
            serie = _fmi(cod)
            tabla[clave] = tabla["iso3"].map(lambda i: (serie.get(i) or {}).get(str(anio)))
            if clave == "crecimiento":
                tabla["crecimiento_previo"] = tabla["iso3"].map(lambda i: (serie.get(i) or {}).get(str(anio - 1)))
        tabla = tabla.dropna(subset=["crecimiento"])
        if len(tabla) > 100:
            return tabla.reset_index(drop=True), f"FMI, Perspectivas de la Economía Mundial (estimación {anio})"
    except Exception:  # noqa: BLE001 - probamos el Banco Mundial
        pass
    tabla = _bm_paises()
    anios = []
    for clave, (_, cod, _, _) in INDICADORES.items():
        d = _bm(cod)
        tabla = tabla.merge(d.rename(columns={"valor": clave, "anio": f"anio_{clave}"}), on="iso3", how="left")
        anios += list(d["anio"])
    tabla["crecimiento_previo"] = np.nan
    ultimo = max(anios) if anios else anio - 1
    for clave in INDICADORES:  # descarta datos demasiado antiguos (más de 4 años)
        col = f"anio_{clave}"
        if col in tabla:
            tabla.loc[tabla[col] < ultimo - 4, clave] = np.nan
    return tabla.dropna(subset=["crecimiento"]).reset_index(drop=True), f"Banco Mundial (último dato, {ultimo})"


def semaforo(crecimiento: float, verde: float = 2.0, rojo: float = 0.0) -> str:
    if crecimiento is None or pd.isna(crecimiento):
        return "Sin datos"
    return "Creciendo" if crecimiento >= verde else "Contrayéndose" if crecimiento < rojo else "Estancado"


def senales_crisis(fila: pd.Series) -> list[str]:
    out = []
    if pd.notna(fila.get("crecimiento")) and fila["crecimiento"] < 0:
        out.append("recesión")
    if pd.notna(fila.get("inflacion")) and fila["inflacion"] > 15:
        out.append("inflación muy alta")
    if pd.notna(fila.get("paro")) and fila["paro"] > 15:
        out.append("paro muy alto")
    if pd.notna(fila.get("deuda")) and fila["deuda"] > 120:
        out.append("deuda muy alta")
    return out


ETF_PAIS = {
    "USA": "SPY", "CAN": "EWC", "MEX": "EWW", "BRA": "EWZ", "ARG": "ARGT", "CHL": "ECH", "PER": "EPU",
    "GBR": "EWU", "ESP": "EWP", "FRA": "EWQ", "DEU": "EWG", "ITA": "EWI", "NLD": "EWN", "BEL": "EWK", "CHE": "EWL",
    "SWE": "EWD", "NOR": "NORW", "DNK": "EDEN", "FIN": "EFNL", "IRL": "EIRL", "AUT": "EWO", "POL": "EPOL", "GRC": "GREK",
    "TUR": "TUR", "ISR": "EIS", "SAU": "KSA", "ARE": "UAE", "QAT": "QAT", "ZAF": "EZA",
    "CHN": "MCHI", "HKG": "EWH", "TWN": "EWT", "KOR": "EWY", "JPN": "EWJ", "IND": "INDA", "IDN": "EIDO", "MYS": "EWM",
    "THA": "THD", "PHL": "EPHE", "SGP": "EWS", "VNM": "VNM", "AUS": "EWA", "NZL": "ENZL",
}


def bolsa_por_pais(cierres: pd.DataFrame) -> pd.DataFrame:
    """Rentabilidad en el año y en 1 mes del ETF de cada país (en dólares)."""
    filas = []
    for iso, etf in ETF_PAIS.items():
        if etf not in cierres:
            continue
        x = cierres[etf].dropna()
        if len(x) < 30:
            continue
        previos = x[x.index.year < x.index[-1].year]
        base = float(previos.iloc[-1]) if len(previos) else float(x.iloc[0])
        filas.append({"iso3": iso, "etf": etf, "bolsa_anio": (float(x.iloc[-1]) / base - 1) * 100,
                      "bolsa_1m": (float(x.iloc[-1]) / float(x.iloc[-22]) - 1) * 100 if len(x) > 22 else np.nan})
    return pd.DataFrame(filas)


# ----------------------------------------------------------------------------- alertas (GDACS)
TIPOS_GDACS = {"EQ": "Terremoto", "TC": "Ciclón tropical", "FL": "Inundación", "VO": "Volcán", "DR": "Sequía",
               "WF": "Incendio forestal", "TS": "Tsunami"}


@con_cache(3 * 3600)
def alertas(dias: int = 30) -> pd.DataFrame:
    hoy = date.today()
    d = _get_json("https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH",
                  {"eventlist": "EQ;TC;FL;VO;DR;WF", "fromDate": (hoy - timedelta(days=dias)).isoformat(),
                   "toDate": hoy.isoformat(), "alertlevel": "Orange;Red"})
    filas = []
    for f in d.get("features", []):
        p, g = f.get("properties", {}), f.get("geometry", {})
        if g.get("type") != "Point":
            continue
        lon, lat = g["coordinates"][:2]
        filas.append({"tipo": TIPOS_GDACS.get(p.get("eventtype"), p.get("eventtype")), "nivel": p.get("alertlevel"),
                      "nombre": p.get("name", ""), "pais": p.get("country", ""), "desde": (p.get("fromdate") or "")[:10],
                      "lat": lat, "lon": lon, "url": (p.get("url") or {}).get("report", "")})
    return pd.DataFrame(filas)


# ----------------------------------------------------------------------------- transporte marítimo
@con_cache(30 * 86400)
def rutas_maritimas() -> tuple[list, list]:
    """Rutas marítimas principales como listas de lat/lon separadas por None (para dibujar líneas)."""
    d = _get_json(f"{PW}/Global_Shipping_Routes/FeatureServer/15/query",
                  {"where": "1=1", "outFields": "FID", "outSR": 4326, "maxAllowableOffset": 0.25, "f": "json"}, 60)
    lats, lons = [], []
    for f in d.get("features", []):
        for camino in f.get("geometry", {}).get("paths", []):
            for lon, lat in camino:
                lats.append(lat)
                lons.append(lon)
            lats.append(None)
            lons.append(None)
    return lats, lons


@con_cache(30 * 86400)
def puertos() -> pd.DataFrame:
    filas, offset = [], 0
    while True:
        d = _get_json(f"{PW}/PortWatch_ports_database/FeatureServer/0/query",
                      {"where": "1=1", "outFields": "portid,portname,country,ISO3,lat,lon,vessel_count_tanker,industry_top1",
                       "returnGeometry": "false", "resultOffset": offset, "resultRecordCount": 2000, "f": "json"})
        filas += [x["attributes"] for x in d.get("features", [])]
        if not d.get("exceededTransferLimit"):
            break
        offset += 2000
    return pd.DataFrame(filas)


@con_cache(6 * 3600)
def petroleros_por_puerto(dias: int = 7) -> pd.DataFrame:
    """Escalas de petroleros por puerto en los últimos días (estimación del FMI con datos AIS; ~5 días de retraso)."""
    desde = (date.today() - timedelta(days=dias + 6)).isoformat()  # +6 por el retraso de publicación
    estad = json.dumps([{"statisticType": "sum", "onStatisticField": "portcalls_tanker", "outStatisticFieldName": "petroleros"},
                        {"statisticType": "sum", "onStatisticField": "import_tanker", "outStatisticFieldName": "importa"},
                        {"statisticType": "sum", "onStatisticField": "export_tanker", "outStatisticFieldName": "exporta"},
                        {"statisticType": "max", "onStatisticField": "date", "outStatisticFieldName": "ultimo"}])
    filas, offset = [], 0
    while True:
        d = _get_json(f"{PW}/Daily_Ports_Data/FeatureServer/0/query",
                      {"where": f"date >= DATE '{desde}' AND portcalls_tanker > 0", "outStatistics": estad,
                       "groupByFieldsForStatistics": "portid", "orderByFields": "petroleros DESC",
                       "resultOffset": offset, "resultRecordCount": 2000, "f": "json"}, 90)
        filas += [x["attributes"] for x in d.get("features", [])]
        if not d.get("exceededTransferLimit") or offset > 6000:
            break
        offset += 2000
    agg = pd.DataFrame(filas)
    if agg.empty:
        return agg
    return agg.merge(puertos(), on="portid", how="inner").sort_values("petroleros", ascending=False).reset_index(drop=True)


def ais_directo(clave: str, caja: tuple, segundos: int = 45) -> pd.DataFrame:
    """Buques en directo en una zona con aisstream.io (clave gratuita). caja = (lat_min, lon_min, lat_max, lon_max)."""
    import websocket  # websocket-client

    ws = websocket.create_connection("wss://stream.aisstream.io/v0/stream", timeout=15)
    ws.send(json.dumps({"APIKey": clave.strip(), "BoundingBoxes": [[[caja[0], caja[1]], [caja[2], caja[3]]]],
                        "FilterMessageTypes": ["PositionReport", "ShipStaticData"]}))
    posiciones, tipos, destinos = {}, {}, {}
    fin = time.time() + segundos
    ws.settimeout(5)
    try:
        while time.time() < fin:
            try:
                msg = json.loads(ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            if "error" in msg:
                raise ValueError(f"aisstream: {msg['error']}")
            meta, tipo = msg.get("MetaData", {}), msg.get("MessageType")
            mmsi = meta.get("MMSI")
            if not mmsi:
                continue
            if tipo == "PositionReport":
                pr = msg.get("Message", {}).get("PositionReport", {})
                posiciones[mmsi] = {"mmsi": mmsi, "nombre": (meta.get("ShipName") or "").strip(), "lat": meta.get("latitude"),
                                    "lon": meta.get("longitude"), "velocidad_nudos": pr.get("Sog"), "hora": meta.get("time_utc")}
            elif tipo == "ShipStaticData":
                sd = msg.get("Message", {}).get("ShipStaticData", {})
                tipos[mmsi] = sd.get("Type")
                destinos[mmsi] = (sd.get("Destination") or "").strip()
    finally:
        ws.close()
    df = pd.DataFrame(posiciones.values())
    if df.empty:
        return df
    df["tipo_ais"] = df["mmsi"].map(tipos)
    df["destino"] = df["mmsi"].map(destinos).fillna("")
    df["categoria"] = df["tipo_ais"].map(lambda t: "Petrolero" if pd.notna(t) and 80 <= t <= 89 else
                                         "Carguero" if pd.notna(t) and 70 <= t <= 79 else
                                         "Pasaje" if pd.notna(t) and 60 <= t <= 69 else
                                         "Otro" if pd.notna(t) else "Tipo desconocido")
    return df


# ----------------------------------------------------------------------------- activos
MINERALES = {  # nombre: ids de Wikidata del mineral / mena
    "oro": ["Q12528662", "Q897"], "cobre": ["Q63219186", "Q753"], "hierro": ["Q191552"], "litio": ["Q12120060", "Q568"],
    "uranio": ["Q1542864", "Q1098"], "plata": ["Q4417415", "Q1090"], "níquel": ["Q4319652", "Q744"],
    "cobalto": ["Q12110813", "Q740"], "carbón": ["Q24489", "Q156267", "Q732607", "Q48969047"],
    "platino": ["Q141467390", "Q880", "Q1089"], "zinc": ["Q12168819", "Q758"], "plomo": ["Q4410773"],
    "diamantes": ["Q5283"], "estaño": ["Q12135758", "Q1096"], "potasa": ["Q10564271"],
}
COMBUSTIBLES = {"nuclear": "Nuclear", "carbón": "Coal", "gas": "Gas", "petróleo": "Oil", "hidroeléctrica": "Hydro",
                "solar": "Solar", "eólica": "Wind", "geotérmica": "Geothermal", "biomasa": "Biomass"}
CAPAS = (
    [f"Minas de {m}" for m in MINERALES]
    + [f"Centrales: {c}" for c in COMBUSTIBLES]
    + ["Refinerías de petróleo", "Terminales de GNL (exportación)", "Terminales de GNL (importación)",
       "Petroleros: escalas por puerto", "Petroleros: tránsito por estrechos", "Rutas marítimas principales",
       "Alertas: desastres naturales"]
)
_PALABRAS = {  # palabra en el buscador → capas
    "refiner": ["Refinerías de petróleo"], "gnl": ["Terminales de GNL (exportación)", "Terminales de GNL (importación)"],
    "lng": ["Terminales de GNL (exportación)", "Terminales de GNL (importación)"],
    "gas natural": ["Terminales de GNL (exportación)", "Terminales de GNL (importación)", "Centrales: gas"],
    "petroler": ["Petroleros: escalas por puerto", "Petroleros: tránsito por estrechos", "Rutas marítimas principales"],
    "buque": ["Petroleros: escalas por puerto", "Rutas marítimas principales"], "barco": ["Rutas marítimas principales"],
    "ruta": ["Rutas marítimas principales"], "puerto": ["Petroleros: escalas por puerto"],
    "estrecho": ["Petroleros: tránsito por estrechos"], "petróleo": ["Refinerías de petróleo", "Petroleros: escalas por puerto"],
    "crudo": ["Refinerías de petróleo", "Petroleros: escalas por puerto"],
    "nuclear": ["Centrales: nuclear", "Minas de uranio"], "atómica": ["Centrales: nuclear"],
    "desastre": ["Alertas: desastres naturales"], "terremoto": ["Alertas: desastres naturales"],
    "huracán": ["Alertas: desastres naturales"], "ciclón": ["Alertas: desastres naturales"],
    "inundac": ["Alertas: desastres naturales"], "incendio": ["Alertas: desastres naturales"],
    "sequía": ["Alertas: desastres naturales"], "hidroeléctric": ["Centrales: hidroeléctrica"],
    "presa": ["Centrales: hidroeléctrica"], "embalse": ["Centrales: hidroeléctrica"], "solar": ["Centrales: solar"],
    "eólic": ["Centrales: eólica"], "viento": ["Centrales: eólica"], "geotérm": ["Centrales: geotérmica"],
    "biomasa": ["Centrales: biomasa"], "diamante": ["Minas de diamantes"], "paladio": ["Minas de platino"],
}


def _sin_tildes(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t.lower()) if not unicodedata.combining(c))


def interpretar_busqueda(texto: str) -> list[str]:
    """'mina de oro y centrales nucleares' → ['Minas de oro', 'Centrales: nuclear', 'Minas de uranio']."""
    t = _sin_tildes(texto or "")
    capas = []
    solo_centrales = "central" in t and "mina" not in t and "yacimiento" not in t
    for mineral in MINERALES:
        if solo_centrales and mineral in ("carbón", "uranio"):
            continue
        if _sin_tildes(mineral) in t or (mineral == "diamantes" and "diamante" in t):
            capas.append(f"Minas de {mineral}")
    for comb in COMBUSTIBLES:
        if f"central {_sin_tildes(comb)}" in t or f"centrales de {_sin_tildes(comb)}" in t or f"central de {_sin_tildes(comb)}" in t:
            capas.append(f"Centrales: {comb}")
    for palabra, cs in _PALABRAS.items():
        if _sin_tildes(palabra) in t:
            capas += cs
    if ("mina" in t or "miner" in t) and not any(c.startswith("Minas") for c in capas):
        capas += ["Minas de oro", "Minas de cobre", "Minas de litio"]
    if "central" in t and not any(c.startswith("Centrales") for c in capas):
        capas += ["Centrales: nuclear", "Centrales: carbón", "Centrales: gas"]
    return list(dict.fromkeys(capas))


@con_cache(30 * 86400)
def minas_wikidata(mineral: str) -> pd.DataFrame:
    valores = " ".join(f"wd:{q}" for q in MINERALES[mineral])
    consulta = f"""SELECT ?m ?mLabel ?lat ?lon ?paisLabel ?operadorLabel WHERE {{
      VALUES ?p {{ {valores} }}
      ?m wdt:P1056 ?p; p:P625/psv:P625 [ wikibase:geoLatitude ?lat; wikibase:geoLongitude ?lon ].
      FILTER NOT EXISTS {{ ?m wdt:P31 wd:Q42412840 }}
      OPTIONAL {{ ?m wdt:P17 ?pais }} OPTIONAL {{ ?m wdt:P137 ?operador }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "es,en". }} }} LIMIT 5000"""
    r = requests.get("https://query.wikidata.org/sparql", params={"query": consulta},
                     headers={"Accept": "application/sparql-results+json",
                              "User-Agent": "RadarInversor/1.0 (uso personal; radar-inversor local)"}, timeout=90)
    r.raise_for_status()
    filas = []
    for b in r.json()["results"]["bindings"]:
        operador = b.get("operadorLabel", {}).get("value", "")
        filas.append({"nombre": b.get("mLabel", {}).get("value", ""), "lat": float(b["lat"]["value"]),
                      "lon": float(b["lon"]["value"]), "pais": b.get("paisLabel", {}).get("value", ""),
                      "operador": "" if operador.startswith("Q") and operador[1:].isdigit() else operador,
                      "url": b["m"]["value"]})
    df = pd.DataFrame(filas)
    if df.empty:
        return df
    df = df.groupby("url", as_index=False).agg({"nombre": "first", "lat": "first", "lon": "first", "pais": "first",
                                                "operador": lambda s: ", ".join(sorted({x for x in s if x}))})
    return df


URL_CENTRALES = "https://raw.githubusercontent.com/wri/global-power-plant-database/master/output_database/global_power_plant_database.csv"


@con_cache(60 * 86400)
def centrales_mundo() -> pd.DataFrame:
    r = requests.get(URL_CENTRALES, headers=UA_WEB, timeout=120)
    r.raise_for_status()
    df = pd.read_csv(io.BytesIO(r.content), usecols=["country_long", "name", "capacity_mw", "latitude", "longitude",
                                                     "primary_fuel", "commissioning_year", "owner"], low_memory=False)
    return df.rename(columns={"country_long": "pais", "name": "nombre", "capacity_mw": "potencia_mw", "latitude": "lat",
                              "longitude": "lon", "primary_fuel": "combustible", "commissioning_year": "inicio",
                              "owner": "operador"})


PAIS_ISO = {
    "Alemania": "DEU", "Arabia Saudí": "SAU", "Argelia": "DZA", "Australia": "AUS", "Botsuana": "BWA", "Brasil": "BRA",
    "Bélgica": "BEL", "Canadá": "CAN", "Catar": "QAT", "Chile": "CHL", "China": "CHN", "Colombia": "COL",
    "Corea del Sur": "KOR", "EE. UU.": "USA", "Emiratos Árabes Unidos": "ARE", "España": "ESP", "Francia": "FRA",
    "Guinea": "GIN", "India": "IND", "Indonesia": "IDN", "Irán": "IRN", "Italia": "ITA", "Japón": "JPN",
    "Kazajistán": "KAZ", "Kuwait": "KWT", "Malasia": "MYS", "Malí": "MLI", "Mongolia": "MNG", "México": "MEX",
    "Namibia": "NAM", "Nigeria": "NGA", "Noruega": "NOR", "Omán": "OMN", "Panamá": "PAN", "Papúa Nueva Guinea": "PNG",
    "Países Bajos": "NLD", "Perú": "PER", "Polonia": "POL", "Portugal": "PRT", "R. D. del Congo": "COD",
    "Reino Unido": "GBR", "República Dominicana": "DOM", "Rusia": "RUS", "Singapur": "SGP", "Sudáfrica": "ZAF",
    "Suecia": "SWE", "Trinidad y Tobago": "TTO", "Uzbekistán": "UZB", "Venezuela": "VEN",
}


def activos_clave() -> pd.DataFrame:
    df = pd.read_csv(CARPETA_DATOS / "activos_clave.csv", dtype={"ticker": str}).fillna("")
    df["iso3"] = df["pais"].map(PAIS_ISO).fillna("")
    return df


# ----------------------------------------------------------------------------- mercado relacionado
MERCADO = {  # capa (prefijo) → (materias primas, empresas)
    "Minas de oro": ({"Oro": "GC=F"}, ["NEM", "B", "AEM", "GDX"]),
    "Minas de cobre": ({"Cobre": "HG=F"}, ["FCX", "SCCO", "BHP", "TECK", "ATYM.L"]),
    "Minas de hierro": ({}, ["VALE", "RIO", "BHP", "MT.AS"]),
    "Minas de litio": ({}, ["ALB", "SQM", "PLS.AX", "LIT"]),
    "Minas de uranio": ({}, ["CCJ", "KAP.L", "URA"]),
    "Minas de plata": ({"Plata": "SI=F"}, ["PAAS", "FRES.L", "SIL"]),
    "Minas de platino": ({"Platino": "PL=F", "Paladio": "PA=F"}, ["SBSW", "PPLT"]),
    "Minas de carbón": ({}, ["BTU", "GLEN.L", "WHC.AX"]),
    "Minas de níquel": ({}, ["VALE", "GLEN.L", "ERA.PA"]),
    "Minas de cobalto": ({}, ["GLEN.L", "3993.HK"]),
    "Minas de potasa": ({}, ["NTR", "MOS"]),
    "Centrales: nuclear": ({}, ["CEG", "CCJ", "BWXT", "SMR", "URA"]),
    "Centrales: gas": ({"Gas natural EE. UU.": "NG=F", "Gas TTF Europa": "TTF=F"}, ["GEV", "SIE.DE", "ENR.DE"]),
    "Centrales: solar": ({}, ["FSLR", "ENPH", "SLR.MC", "TAN"]),
    "Centrales: eólica": ({}, ["VWS.CO", "ENR.DE", "IBE.MC", "ORSTED.CO"]),
    "Refinerías de petróleo": ({"Brent": "BZ=F", "WTI": "CL=F", "Gasolina": "RB=F"}, ["VLO", "MPC", "PSX", "REP.MC", "RELIANCE.NS"]),
    "Terminales de GNL": ({"Gas TTF Europa": "TTF=F", "Gas natural EE. UU.": "NG=F"}, ["LNG", "VG", "SHEL.L", "ENG.MC"]),
    "Petroleros": ({"Brent": "BZ=F"}, ["FRO", "DHT", "STNG", "TNK", "CMBT"]),
}


def mercado_de(capas: list[str]) -> tuple[dict, list]:
    materias, empresas = {}, []
    for c in capas:
        for prefijo, (m, e) in MERCADO.items():
            if c.startswith(prefijo):
                materias.update(m)
                empresas += [x for x in e if x not in empresas]
    return materias, empresas
