"""Cadena de suministro: quién vende a quién.

Ninguna fuente gratuita tiene el mapa completo (eso es lo que venden Bloomberg o FactSet). Aquí se combinan tres cosas:

1. Tu tabla de relaciones (editable, se guarda en tu ordenador). Es la que irás completando con lo que descubras.
2. Evidencias del último informe anual en la SEC (10-K / 20-F): frases donde la empresa habla de clientes que
   concentran ventas y de proveedores de fuente única o de los que depende. Solo empresas con informes en la SEC.
3. Empresas similares según Yahoo Finance (competidores/pares).
"""
from __future__ import annotations

import re
import shutil
import warnings
from pathlib import Path

import networkx as nx
import pandas as pd
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from .cache import con_cache
from .config import CARPETA, UA_WEB, sec_ua

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

COLUMNAS = ["origen", "destino", "producto", "fuente", "nota"]  # origen SUMINISTRA A destino
RUTA_RELACIONES = CARPETA / "relaciones.csv"
RUTA_EJEMPLO = Path(__file__).resolve().parent.parent / "datos" / "relaciones_ejemplo.csv"


# ----------------------------------------------------------------------------- tabla propia
def _n(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(texto).lower()).strip()


def _coincide(a: str, b: str) -> bool:
    a, b = _n(a), _n(b)
    if not a or not b:
        return False
    return a == b or (len(a) >= 4 and a in b) or (len(b) >= 4 and b in a)


def cargar_relaciones() -> pd.DataFrame:
    if not RUTA_RELACIONES.exists() and RUTA_EJEMPLO.exists():
        try:
            RUTA_RELACIONES.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(RUTA_EJEMPLO, RUTA_RELACIONES)
        except OSError:
            pass
    ruta = RUTA_RELACIONES if RUTA_RELACIONES.exists() else RUTA_EJEMPLO
    if not ruta.exists():
        return pd.DataFrame(columns=COLUMNAS)
    df = pd.read_csv(ruta, dtype=str).fillna("")
    for c in COLUMNAS:
        if c not in df.columns:
            df[c] = ""
    return df[COLUMNAS]


def guardar_relaciones(df: pd.DataFrame) -> int:
    df = df.copy()
    for c in COLUMNAS:
        if c not in df.columns:
            df[c] = ""
    df = df[COLUMNAS].fillna("").astype(str)
    df = df[(df["origen"].str.strip() != "") & (df["destino"].str.strip() != "")]
    RUTA_RELACIONES.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(RUTA_RELACIONES, index=False)
    return len(df)


def vecinos(df: pd.DataFrame, empresa: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(proveedores de la empresa, clientes de la empresa)."""
    proveedores = df[df["destino"].map(lambda x: _coincide(x, empresa))]
    clientes = df[df["origen"].map(lambda x: _coincide(x, empresa))]
    return proveedores, clientes


def grafo_local(df: pd.DataFrame, empresa: str, profundidad: int = 2):
    """(grafo, niveles, centro). Nivel negativo = aguas arriba (proveedores), positivo = clientes."""
    nombres = set(df["origen"]) | set(df["destino"])
    candidatos = [n for n in nombres if _coincide(n, empresa)]
    if not candidatos:
        return None, {}, None
    G = nx.DiGraph()
    for r in df.itertuples():
        G.add_edge(r.origen, r.destino, producto=r.producto)
    centro = max(candidatos, key=lambda n: G.degree(n))
    nivel = {centro: 0}
    for signo, vecinos_de in ((-1, G.predecessors), (1, G.successors)):
        frontera = [centro]
        for d in range(1, profundidad + 1):
            nueva = []
            for nodo in frontera:
                for v in vecinos_de(nodo):
                    if v not in nivel:
                        nivel[v] = signo * d
                        nueva.append(v)
            frontera = nueva
    return G.subgraph(nivel).copy(), nivel, centro


# ----------------------------------------------------------------------------- SEC EDGAR
class FaltaContactoSEC(ValueError):
    """La SEC exige nombre y correo en la cabecera de cada petición."""


def _sec_get(url: str) -> requests.Response:
    ua = sec_ua()
    if "@" not in ua:
        raise FaltaContactoSEC("La SEC exige identificarse con tu nombre y correo (se guarda solo en tu ordenador).")
    r = requests.get(url, headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}, timeout=40)
    r.raise_for_status()
    return r


@con_cache(7 * 86400)
def tabla_tickers_sec() -> pd.DataFrame:
    datos = _sec_get("https://www.sec.gov/files/company_tickers.json").json()
    return pd.DataFrame(datos).T


def cik_de(ticker: str):
    t = tabla_tickers_sec()
    buscado = ticker.upper().replace(".", "-")
    fila = t[t["ticker"].str.upper() == buscado]
    return int(fila["cik_str"].iloc[0]) if not fila.empty else None


@con_cache(24 * 3600)
def ultimo_informe(cik: int) -> dict:
    """Texto del último 10-K (o 20-F) de la empresa."""
    sub = _sec_get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json").json()
    rec = sub["filings"]["recent"]
    for i, forma in enumerate(rec["form"]):
        if forma in ("10-K", "20-F"):
            acc = rec["accessionNumber"][i].replace("-", "")
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{rec['primaryDocument'][i]}"
            html = _sec_get(url).text
            texto = BeautifulSoup(html, "lxml").get_text(" ")
            return {"texto": re.sub(r"\s+", " ", texto), "fecha": rec["filingDate"][i], "forma": forma, "url": url}
    return {}


_SUFIJOS = r"(?:Inc\.?|Incorporated|Corp\.?|Corporation|Co\.|Company|Ltd\.?|Limited|LLC|plc|PLC|N\.V\.|S\.A\.|AG|GmbH|SE|Holdings)"
_RE_ORG = re.compile(
    r"\b((?:[A-Z][A-Za-z0-9&'\-]*\s+){0,5}[A-Z][A-Za-z0-9&'\-]*\s+" + _SUFIJOS
    + r"(?:,?\s+(?:Ltd\.?|Limited|Inc\.?|LLC|plc))?)(?=[\s,;:)]|$)"
)
_GENERICAS = {"the company", "our company", "this company", "such company", "any company", "the corporation"}
_RE_CLIENTE = re.compile(r"(accounted for|represented|comprised|concentrat)", re.I)
_RE_GEOGRAFIA = re.compile(r"(outside (?:of )?the (?:United States|U\.S\.)|geograph|by region|international)", re.I)
_RE_PORCENTAJE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s?%")
_RE_PROVEEDOR = re.compile(
    r"(sole[- ]source|single[- ]source|sole supplier|single supplier|"
    r"limited number of (?:suppliers|vendors|foundries|manufacturers)|"
    r"(?:rel(?:y|ies)|depend(?:s|ent)?)\s+(?:up)?on\s+(?:[\w.,&'-]+\s+){0,8}?"
    r"(?:to\s+(?:manufacture|produce|fabricate|supply|assemble|provide)|suppliers?|manufacturers?|foundr\w+|vendors?|"
    r"third[- ]part\w+|subcontractors?)|"
    r"(?:manufactured|supplied|produced) by|contract manufactur\w+|foundr(?:y|ies),? (?:such as|including))",
    re.I,
)


def _orgs(frase: str) -> list[str]:
    salida = []
    for m in _RE_ORG.finditer(frase):
        nombre = re.sub(r"^(The|Our|This|These|Such|Any|We|In|For|And|With)\s+", "", m.group(1)).strip()
        if nombre.lower() in _GENERICAS or len(nombre) < 4 or nombre in salida or re.fullmatch(_SUFIJOS, nombre):
            continue
        salida.append(nombre)
    return salida


def extraer_evidencias(texto: str, maximo: int = 60) -> pd.DataFrame:
    """Frases del informe sobre concentración de clientes y dependencia de proveedores."""
    frases = re.split(r"(?<=[.!?])\s+(?=[A-Z])", texto)
    filas = []
    for f in frases:
        if not (40 < len(f) < 700):
            continue
        porcentaje = _RE_PORCENTAJE.search(f)
        if "customer" in f.lower() and _RE_CLIENTE.search(f) and porcentaje:
            if _RE_GEOGRAFIA.search(f):  # reparto por países, no concentración de clientes
                continue
            tipo = "cliente"
        elif _RE_PROVEEDOR.search(f):
            tipo = "proveedor"
        else:
            continue
        filas.append(
            {
                "tipo": tipo,
                "empresas": ", ".join(_orgs(f)),
                "porcentaje": porcentaje.group(1) + "%" if (porcentaje and tipo == "cliente") else "",
                "frase": f.strip(),
            }
        )
    df = pd.DataFrame(filas, columns=["tipo", "empresas", "porcentaje", "frase"])
    if df.empty:
        return df
    clave = df["frase"].map(lambda x: re.sub(r"[^a-z0-9]", "", x.lower())[-110:])  # ignora espacios y encabezados repetidos
    df = df[~clave.duplicated()]
    nombradas = df[df["empresas"] != ""]
    sin_nombre = df[(df["empresas"] == "") & (df["tipo"] == "cliente")].head(10)  # concentración de clientes
    genericas = df[(df["empresas"] == "") & (df["tipo"] == "proveedor")].head(10)
    return pd.concat([nombradas, sin_nombre, genericas]).head(maximo).reset_index(drop=True)


def evidencias_sec(ticker: str) -> tuple[pd.DataFrame, dict]:
    """(evidencias, metadatos). Lanza ValueError si la empresa no está en la SEC."""
    cik = cik_de(ticker)
    if cik is None:
        raise ValueError("Esta empresa no figura en la SEC (solo cubre emisores con informes allí).")
    inf = ultimo_informe(cik)
    if not inf:
        raise ValueError("No encontré un informe anual (10-K/20-F) reciente.")
    return extraer_evidencias(inf["texto"]), {k: inf[k] for k in ("fecha", "forma", "url")}


# ----------------------------------------------------------------------------- similares
@con_cache(24 * 3600)
def similares(ticker: str) -> list[str]:
    """Empresas que Yahoo Finance recomienda como similares/competidoras."""
    r = requests.get(
        f"https://query2.finance.yahoo.com/v6/finance/recommendationsbysymbol/{ticker}",
        headers=UA_WEB,
        timeout=15,
    )
    r.raise_for_status()
    res = r.json().get("finance", {}).get("result") or []
    return [x["symbol"] for x in (res[0].get("recommendedSymbols", []) if res else [])]
