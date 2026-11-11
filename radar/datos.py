"""Datos de mercado gratuitos: Yahoo Finance (yfinance) y listas de índices de Wikipedia."""
from __future__ import annotations

import re
from io import StringIO

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from .cache import con_cache
from .config import UA_WEB

TERMOMETRO = {
    "S&P 500": "^GSPC",
    "Nasdaq 100": "^NDX",
    "Euro Stoxx 50": "^STOXX50E",
    "IBEX 35": "^IBEX",
    "FTSE 100": "^FTSE",
    "DAX": "^GDAXI",
    "VIX (miedo)": "^VIX",
    "Petróleo Brent": "BZ=F",
    "Petróleo WTI": "CL=F",
    "Gas natural EE.UU.": "NG=F",
    "Oro": "GC=F",
    "EUR/USD": "EURUSD=X",
    "Bono EE.UU. 10 años": "^TNX",
}

# Índice de referencia según el mercado donde cotiza la acción.
REFERENCIAS = {
    ".MC": "^IBEX",
    ".L": "^FTSE",
    ".DE": "^GDAXI",
    ".PA": "^FCHI",
    ".MI": "FTSEMIB.MI",
    ".AS": "^AEX",
}

# nombre: (url, columnas posibles con el símbolo, sufijo de Yahoo, filas mínimas)
# sufijo "" = bolsa de EE. UU. (tickers sin punto) · "*" = índice de varias bolsas (la tabla ya trae el símbolo completo)
INDICES = {
    "S&P 500": ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", ["Symbol"], "", 400),
    "S&P 100": ("https://en.wikipedia.org/wiki/S%26P_100", ["Symbol"], "", 90),
    # La lista de Nasdaq-100 se lee del JSON público de Nasdaq (Wikipedia ya no trae los tickers en esa página)
    "Nasdaq-100": ("https://api.nasdaq.com/api/quote/list-type/nasdaq100", ["symbol"], "", 90),
    "Dow Jones": ("https://en.wikipedia.org/wiki/List_of_Dow_Jones_Industrial_Average_companies", ["Symbol", "Ticker"], "", 25),
    "S&P 400 (medianas)": ("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", ["Symbol"], "", 350),
    "Euro Stoxx 50": ("https://en.wikipedia.org/wiki/EURO_STOXX_50", ["Ticker"], "*", 45),
    "IBEX 35": ("https://en.wikipedia.org/wiki/IBEX_35", ["Ticker", "Symbol"], ".MC", 30),
    "IBEX Medium Cap": ("https://es.wikipedia.org/wiki/IBEX_Medium_Cap", ["Ticker"], ".MC", 15),
    "FTSE 100": ("https://en.wikipedia.org/wiki/FTSE_100_Index", ["Ticker", "EPIC", "Symbol"], ".L", 90),
    "FTSE 250": ("https://en.wikipedia.org/wiki/FTSE_250_Index", ["Ticker", "EPIC"], ".L", 200),
    "DAX 40": ("https://en.wikipedia.org/wiki/DAX", ["Ticker", "Symbol"], ".DE", 35),
    "MDAX": ("https://en.wikipedia.org/wiki/MDAX", ["Symbol", "Ticker"], ".DE", 40),
    "CAC 40": ("https://en.wikipedia.org/wiki/CAC_40", ["Ticker", "Symbol"], ".PA", 35),
    "FTSE MIB": ("https://en.wikipedia.org/wiki/FTSE_MIB", ["Ticker"], ".MI", 35),
    "AEX": ("https://en.wikipedia.org/wiki/AEX_index", ["Ticker"], ".AS", 20),
    "SMI": ("https://en.wikipedia.org/wiki/Swiss_Market_Index", ["Ticker"], ".SW", 18),
    "OMX Stockholm 30": ("https://en.wikipedia.org/wiki/OMX_Stockholm_30", ["Ticker"], ".ST", 25),
    "PSI (Lisboa)": ("https://en.wikipedia.org/wiki/PSI-20", ["Ticker"], ".LS", 14),
}
# Símbolo de Yahoo del propio índice (para enseñar cómo va hoy)
SIMBOLO_INDICE = {"S&P 500": "^GSPC", "S&P 100": "^OEX", "Nasdaq-100": "^NDX", "Dow Jones": "^DJI", "S&P 400 (medianas)": "^MID",
                  "Euro Stoxx 50": "^STOXX50E", "IBEX 35": "^IBEX", "FTSE 100": "^FTSE", "FTSE 250": "^FTMC", "DAX 40": "^GDAXI",
                  "MDAX": "^MDAXI", "CAC 40": "^FCHI", "FTSE MIB": "FTSEMIB.MI", "AEX": "^AEX", "SMI": "^SSMI",
                  "OMX Stockholm 30": "^OMX", "PSI (Lisboa)": "PSI20.LS"}

CAMPOS_FICHA = [
    "longName", "shortName", "sector", "industry", "country", "currency", "exchange",
    "marketCap", "trailingPE", "forwardPE", "priceToBook", "beta", "dividendRate",
    "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "currentPrice", "regularMarketPrice",
    "previousClose", "targetMeanPrice", "targetMedianPrice", "targetHighPrice",
    "targetLowPrice", "recommendationKey", "numberOfAnalystOpinions", "totalRevenue",
    "profitMargins", "debtToEquity", "fullTimeEmployees", "website", "longBusinessSummary",
    # --- para el análisis fundamental
    "trailingPegRatio", "pegRatio", "enterpriseToEbitda", "enterpriseToRevenue", "enterpriseValue", "ebitda",
    "returnOnEquity", "returnOnAssets", "freeCashflow", "operatingCashflow", "totalDebt", "totalCash",
    "dividendYield", "payoutRatio", "fiveYearAvgDividendYield", "earningsGrowth", "revenueGrowth",
    "earningsQuarterlyGrowth", "grossMargins", "operatingMargins", "ebitdaMargins", "sharesOutstanding",
    "trailingEps", "forwardEps", "bookValue", "heldPercentInsiders", "heldPercentInstitutions", "averageVolume",
    "financialCurrency", "quoteType", "fiftyDayAverage", "twoHundredDayAverage", "shortPercentOfFloat",
    "currentRatio", "quickRatio", "lastDividendValue", "exDividendDate", "priceToSalesTrailing12Months",
]


# ----------------------------------------------------------------------------- búsqueda
# Nombres habituales de empresas españolas → ticker de la Bolsa de Madrid (Yahoo a veces no los devuelve bien)
ALIAS_ES = {
    "inditex": "ITX.MC", "zara": "ITX.MC", "santander": "SAN.MC", "banco santander": "SAN.MC", "bbva": "BBVA.MC",
    "iberdrola": "IBE.MC", "telefonica": "TEF.MC", "movistar": "TEF.MC", "repsol": "REP.MC", "caixabank": "CABK.MC",
    "aena": "AENA.MC", "amadeus": "AMS.MC", "ferrovial": "FER.MC", "cellnex": "CLNX.MC", "naturgy": "NTGY.MC",
    "endesa": "ELE.MC", "acs": "ACS.MC", "grifols": "GRF.MC", "iag": "IAG.MC", "iberia": "IAG.MC", "redeia": "RED.MC",
    "red electrica": "RED.MC", "enagas": "ENG.MC", "mapfre": "MAP.MC", "sabadell": "SAB.MC", "banco sabadell": "SAB.MC",
    "bankinter": "BKT.MC", "unicaja": "UNI.MC", "acciona": "ANA.MC", "acciona energia": "ANE.MC", "acerinox": "ACX.MC",
    "arcelormittal": "MTS.MC", "colonial": "COL.MC", "fluidra": "FDR.MC", "indra": "IDR.MC", "logista": "LOG.MC",
    "merlin": "MRL.MC", "merlin properties": "MRL.MC", "puig": "PUIG.MC", "rovi": "ROVI.MC", "sacyr": "SCYR.MC",
    "solaria": "SLR.MC", "gestamp": "GEST.MC", "talgo": "TLGO.MC", "caf": "CAF.MC", "tecnicas reunidas": "TRE.MC",
    "cie automotive": "CIE.MC", "ebro": "EBRO.MC", "ebro foods": "EBRO.MC", "viscofan": "VIS.MC", "vidrala": "VID.MC",
    "melia": "MEL.MC", "prosegur": "PSG.MC", "faes": "FAE.MC", "almirall": "ALM.MC", "pharmamar": "PHM.MC",
    "ence": "ENC.MC", "atresmedia": "A3M.MC", "mediaset": "MFEB.MC", "neinor": "HOME.MC", "applus": "APPS.MC",
}
_BOLSAS_PRINCIPALES = (".MC", ".DE", ".PA", ".L", ".AS", ".MI", ".SW", ".LS", ".BR", ".CO", ".ST", ".HE", ".OL", ".T",
                       ".HK", ".TO", ".AX", ".KS", ".SS", ".SZ", ".SA", ".IR")


def _sin_tildes(t: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", t.lower()) if not unicodedata.combining(c)).strip()


def _puntuacion(r: dict) -> float:
    """Menor = mejor: bolsas principales primero, mercados secundarios y ETF apalancados al final."""
    s = r["symbol"].upper()
    if r.get("codigo_bolsa") in ("PNK", "OQB", "OQX", "OTC", "OEM", "OGM", "OID") or "OTC" in r.get("mercado", "").upper():
        return 4.0  # mercados extrabursátiles de EE. UU. (poco líquidos)
    if s.endswith(".MC") or ("." not in s and "-" not in s and r["tipo"] == "EQUITY"):
        p = 0.0
    elif s.endswith(_BOLSAS_PRINCIPALES):
        p = 1.0
    elif s.endswith((".T", ".KS", ".HK", ".TW", ".SW", ".ST", ".CO", ".OL", ".HE", ".BR", ".LS", ".VI", ".AX", ".TO")):
        p = 1.5  # bolsa de origen de empresas asiáticas, nórdicas, suizas…
    elif r["tipo"] == "INDEX":
        p = 0.5
    else:
        p = 3.0
    if r["tipo"] == "ETF":
        p += 2.0
    return p


def _en_la_base(texto: str) -> list[dict]:
    """Empresas de la base del programa cuyo nombre o alias encaja con lo escrito (tolera erratas)."""
    import difflib

    from . import conexiones

    q = _sin_tildes(texto).strip()
    if len(q) < 2:
        return []
    empresas, _ = conexiones.cargar_base()
    exactas, empiezan, contienen, nombres = [], [], [], {}
    for fila in empresas.itertuples():
        if not fila.tickers:
            continue
        variantes = [_sin_tildes(x) for x in [fila.nombre, fila.id] + [a for a in fila.alias.split("|") if a]]
        item = {"symbol": fila.tickers.split("|")[0], "nombre": fila.nombre, "mercado": fila.pais, "tipo": "EQUITY", "codigo_bolsa": ""}
        for v in variantes:
            nombres[v] = item
        if q in variantes:
            exactas.append(item)
        elif any(v.startswith(q) or any(pal.startswith(q) for pal in v.split()) for v in variantes):
            empiezan.append(item)
        elif len(q) >= 4 and any(q in v for v in variantes):
            contienen.append(item)
    salida = exactas + empiezan + contienen
    if not salida and len(q) >= 4:  # erratas: «microsft», «acenture», «inditez»
        salida = [nombres[n] for n in difflib.get_close_matches(q, list(nombres), n=3, cutoff=0.78)]
    return salida[:4]


@con_cache(6 * 3600)
def _buscar_yahoo(texto: str) -> list[dict]:
    r = None
    for servidor in ("query2", "query1"):  # si uno de los dos servidores de Yahoo falla, se prueba el otro
        try:
            r = requests.get(f"https://{servidor}.finance.yahoo.com/v1/finance/search",
                             params={"q": texto, "quotesCount": 10, "newsCount": 0}, headers=UA_WEB, timeout=8)
            r.raise_for_status()
            break
        except Exception:  # noqa: BLE001
            r = None
    if r is None:
        raise ConnectionError("El buscador de Yahoo no responde")
    salida = []
    for q in r.json().get("quotes", []):
        if q.get("quoteType") not in ("EQUITY", "ETF", "INDEX"):
            continue
        salida.append({"symbol": q["symbol"], "nombre": q.get("longname") or q.get("shortname") or "",
                       "mercado": q.get("exchDisp") or q.get("exchange") or "", "tipo": q.get("quoteType", ""),
                       "codigo_bolsa": q.get("exchange", "")})
    return sorted(salida, key=_puntuacion)  # orden estable: dentro del mismo nivel respeta la relevancia de Yahoo


def buscar_valores(texto: str) -> list[dict]:
    """Busca empresas/ETF/índices por nombre o ticker.

    Orden: 1) si lo escrito es exactamente un ticker, ese; 2) empresas de la base del programa (con su bolsa principal y
    tolerando erratas); 3) el buscador de Yahoo, con las bolsas principales delante.
    """
    texto = (texto or "").strip()
    if not texto:
        return []
    try:
        yahoo = _buscar_yahoo(texto)
    except Exception:  # noqa: BLE001 - sin conexión con Yahoo aún se puede encontrar en la base
        yahoo = []
    locales = _en_la_base(texto)
    if not yahoo and locales:  # errata: se vuelve a preguntar a Yahoo con el nombre corregido
        try:
            yahoo = _buscar_yahoo(locales[0]["nombre"])
        except Exception:  # noqa: BLE001
            yahoo = []
    exacto = [x for x in yahoo if x["symbol"].upper() == texto.upper()]
    alias = ALIAS_ES.get(_sin_tildes(texto))
    primero = []
    if alias:  # nombres españoles de toda la vida: «bbva» es BBVA.MC, no el ADR de Nueva York
        primero = [{"symbol": alias, "nombre": texto.strip().title() + " (Bolsa de Madrid)", "mercado": "Madrid", "tipo": "EQUITY",
                    "codigo_bolsa": ""}]
    salida, vistos = [], set()
    for x in primero + exacto + locales + yahoo:
        if x["symbol"].upper() not in vistos:
            vistos.add(x["symbol"].upper())
            salida.append(x)
    return salida[:8]


buscar = buscar_valores  # nombre usado en el resto del programa


def referencia_para(ticker: str) -> str:
    """Índice de referencia razonable según el sufijo del ticker."""
    t = ticker.upper()
    for sufijo, indice in REFERENCIAS.items():
        if t.endswith(sufijo):
            return indice
    return "^GSPC"


# ----------------------------------------------------------------------------- precios
@con_cache(15 * 60)
def historial(ticker: str, periodo: str = "5y") -> pd.DataFrame:
    h = yf.Ticker(ticker).history(period=periodo, auto_adjust=True)
    if h is None or h.empty:
        return pd.DataFrame()
    if getattr(h.index, "tz", None) is not None:
        h.index = h.index.tz_localize(None)
    h.index = h.index.normalize()
    return h[["Open", "High", "Low", "Close", "Volume"]]


@con_cache(15 * 60)
def cierres(tickers: tuple, periodo: str = "2y") -> pd.DataFrame:
    """Precios de cierre de varios tickers en una sola tabla."""
    tickers = list(tickers)
    if not tickers:
        return pd.DataFrame()
    d = yf.download(tickers, period=periodo, auto_adjust=True, progress=False, threads=True)
    if d is None or d.empty:
        return pd.DataFrame()
    c = d["Close"]
    if isinstance(c, pd.Series):
        c = c.to_frame(tickers[0])
    if getattr(c.index, "tz", None) is not None:
        c.index = c.index.tz_localize(None)
    return c.dropna(how="all")


@con_cache(30 * 60)
def ohlc_varios(tickers: tuple, periodo: str = "2y") -> dict:
    """Precios OHLC de muchos tickers en una sola descarga: ticker → DataFrame."""
    tickers = list(dict.fromkeys(tickers))
    if not tickers:
        return {}
    d = yf.download(tickers, period=periodo, auto_adjust=True, progress=False, threads=True, group_by="ticker")
    if d is None or d.empty:
        return {}
    if getattr(d.index, "tz", None) is not None:
        d.index = d.index.tz_localize(None)
    salida = {}
    for t in tickers:
        try:
            sub = d[t] if isinstance(d.columns, pd.MultiIndex) else d
        except KeyError:
            continue
        sub = sub[["Open", "High", "Low", "Close"] + (["Volume"] if "Volume" in sub else [])].dropna(subset=["Close"])
        if len(sub):
            salida[t] = sub
    return salida


def lista_indice(nombre: str) -> list[str]:
    return _constituyentes(nombre)


# ----------------------------------------------------------------------------- ficha
@con_cache(3600)
def ficha(ticker: str) -> dict:
    info = yf.Ticker(ticker).info or {}
    f = {k: info.get(k) for k in CAMPOS_FICHA}
    precio = f.get("currentPrice") or f.get("regularMarketPrice")
    f["precio"] = precio
    # Rentabilidad por dividendo calculada por nosotros (Yahoo ha cambiado sus unidades varias veces)
    f["rend_dividendo"] = (f["dividendRate"] / precio) if (f.get("dividendRate") and precio) else None
    return f


@con_cache(24 * 3600)
def accionistas(ticker: str) -> pd.DataFrame:
    """Principales accionistas institucionales (fondos) según Yahoo."""
    df = yf.Ticker(ticker).institutional_holders
    return df if df is not None else pd.DataFrame()


# ----------------------------------------------------------------------------- índices
_RE_BOLSA = re.compile(r"\.(MC|DE|PA|L|MI|AS|BR|LS|SW|F|VI|ST|CO|HE|OL)$")


def _normalizar_simbolo(s, sufijo: str) -> str:
    s = str(s).split(":")[-1]
    s = re.sub(r"\[.*?\]", "", s).strip().upper().replace(" ", "")
    if not s or s == "NAN":
        return ""
    if _RE_BOLSA.search(s):  # Wikipedia ya trae el símbolo completo de Yahoo (SAN.MC, AIR.PA)
        return s
    return s.replace(".", "-") + sufijo  # BT.A → BT-A.L ; BRK.B → BRK-B


@con_cache(7 * 86400)
def _constituyentes(nombre: str) -> list[str]:
    url, columnas, sufijo, min_filas = INDICES[nombre]
    if "api.nasdaq.com" in url:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                                                     "Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*"},
                         timeout=20)
        r.raise_for_status()
        filas = r.json()["data"]["data"]["rows"]
        return sorted({_normalizar_simbolo(x["symbol"], sufijo) for x in filas if x.get("symbol")})
    r = requests.get(url, headers=UA_WEB, timeout=20)
    r.raise_for_status()
    mejor: list[str] = []
    for t in pd.read_html(StringIO(r.text)):
        t.columns = [" ".join(map(str, c)).strip() if isinstance(c, tuple) else str(c) for c in t.columns]
        col = next((c for c in t.columns if c in columnas), None)
        if col is None:
            continue
        simbolos = [s for s in (_normalizar_simbolo(x, sufijo) for x in t[col]) if s]
        if len(simbolos) >= min_filas and len(simbolos) > len(mejor):
            mejor = simbolos
    return sorted(set(mejor))


def _aplica(sufijo: str, t: str) -> bool:
    """¿Tiene sentido buscar el ticker `t` en un índice con ese sufijo?"""
    if sufijo == "":
        return "." not in t  # los tickers de EE. UU. no llevan punto; los extranjeros sí (SAN.MC)
    return "." in t  # Airbus (AIR.PA) está en el CAC 40, el DAX y el Euro Stoxx 50: se miran todos los europeos


def indices_de(ticker: str, otros_tickers: tuple = ()) -> tuple[list[str], list[str]]:
    """(índices en los que cotiza, índices que no se pudieron consultar).

    `otros_tickers`: el mismo valor en otras bolsas (p. ej. ASML y ASML.AS), para no perder índices por el doble listado.
    """
    from concurrent.futures import ThreadPoolExecutor

    candidatos = [t.upper() for t in (ticker, *otros_tickers) if t]
    pendientes = [n for n, (_, _, sufijo, _) in INDICES.items() if any(_aplica(sufijo, t) for t in candidatos)]

    def mirar(nombre):
        try:
            lista = set(_constituyentes(nombre))
        except Exception:  # noqa: BLE001
            return nombre, None
        return nombre, any(t in lista for t in candidatos)

    dentro, fallos = [], []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for nombre, esta in ex.map(mirar, pendientes):
            if esta is None:
                fallos.append(nombre)
            elif esta:
                dentro.append(nombre)
    return dentro, fallos


# ----------------------------------------------------------------------------- mercado
@con_cache(15 * 60)
def termometro() -> pd.DataFrame:
    simbolos = list(TERMOMETRO.values())
    c = yf.download(simbolos, period="1y", auto_adjust=True, progress=False, threads=True)
    if c is None or c.empty:
        return pd.DataFrame()
    c = c["Close"]
    filas = []
    for nombre, s in TERMOMETRO.items():
        if s not in c.columns:
            continue
        x = c[s].dropna()
        if len(x) < 30:
            continue
        ultimo = float(x.iloc[-1])
        anio = x.index[-1].year
        previos = x[x.index.year < anio]
        base_ytd = float(previos.iloc[-1]) if len(previos) else float(x.iloc[0])
        media200 = x.rolling(200).mean().iloc[-1] if len(x) >= 200 else np.nan
        filas.append(
            {
                "Activo": nombre,
                "Símbolo": s,
                "Último": ultimo,
                "1 día %": (ultimo / float(x.iloc[-2]) - 1) * 100,
                "1 mes %": (ultimo / float(x.iloc[-22]) - 1) * 100 if len(x) > 22 else np.nan,
                "En el año %": (ultimo / base_ytd - 1) * 100,
                "vs media 200d %": (ultimo / media200 - 1) * 100 if pd.notna(media200) else np.nan,
            }
        )
    return pd.DataFrame(filas)


def lectura_regimen(t: pd.DataFrame) -> str:
    """Frase corta que resume tendencia y nivel de miedo del mercado."""
    partes = []
    sp = t[t["Símbolo"] == "^GSPC"]
    if not sp.empty and pd.notna(sp["vs media 200d %"].iloc[0]):
        v = float(sp["vs media 200d %"].iloc[0])
        partes.append(
            f"El S&P 500 está un {abs(v):.1f}% {'por encima' if v >= 0 else 'por debajo'} de su media de 200 sesiones "
            f"→ {'tendencia alcista' if v >= 0 else 'tendencia débil o bajista'}."
        )
    vx = t[t["Símbolo"] == "^VIX"]
    if not vx.empty:
        x = float(vx["Último"].iloc[0])
        nivel = "calma" if x < 15 else "normal" if x < 25 else "tensión" if x < 35 else "pánico"
        partes.append(f"El VIX está en {x:.1f} ({nivel}).")
    return " ".join(partes) or "No hay datos suficientes para valorar el régimen de mercado."
