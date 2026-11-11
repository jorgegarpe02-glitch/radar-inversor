"""Mapa de conexiones: a quién le vende y a quién le compra cualquier empresa.

Combina cuatro fuentes:
1. Base precargada (datos/empresas.csv y datos/relaciones_base.csv): relaciones conocidas públicamente entre ~300 grandes
   empresas (semiconductores, nube e IA, automoción, aeroespacial y defensa, energía, pagos, telecomunicaciones, España).
   Refleja información pública hasta 2026: verifícala antes de decidir.
2. Tu tabla de relaciones (lo que tú vayas añadiendo).
3. El informe anual de la propia empresa en la SEC: proveedores que nombra.
4. Búsqueda inversa en la SEC: qué otras empresas la nombran en SUS informes anuales y en qué papel
   (cliente, proveedor o competidor). Sirve para cualquier empresa que aparezca en informes de empresas cotizadas en EE. UU.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import networkx as nx
import pandas as pd
import requests

from .cache import con_cache
from .config import sec_ua

CARPETA_DATOS = Path(__file__).resolve().parent.parent / "datos"
COLUMNAS = ["proveedor", "cliente", "que", "categoria", "confianza", "fuente", "nota", "finalidad"]
_SUFIJOS_NOMBRE = re.compile(
    r"[,.]?\s+(Inc\.?|Incorporated|Corporation|Corp\.?|Company|Co\.|Holdings?|Group|N\.V\.|NV|S\.A\.|SA|SE|AG|plc|PLC|"
    r"Ltd\.?|Limited|LLC|Platforms|Technologies|Technology|International|Systems)$", re.I)


def _n(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(texto).lower()).strip()


def nombre_corto(nombre: str) -> str:
    """'NVIDIA Corporation' → 'NVIDIA'; 'ASML Holding N.V.' → 'ASML'."""
    n = str(nombre).strip()
    for _ in range(3):
        nuevo = _SUFIJOS_NOMBRE.sub("", n).strip(" ,.")
        if nuevo == n or len(nuevo) < 2:
            break
        n = nuevo
    return n


# ----------------------------------------------------------------------------- base precargada
@lru_cache(maxsize=1)
def cargar_base() -> tuple[pd.DataFrame, pd.DataFrame]:
    empresas = pd.read_csv(CARPETA_DATOS / "empresas.csv", dtype=str).fillna("")
    rel = pd.read_csv(CARPETA_DATOS / "relaciones_base.csv", dtype=str).fillna("")
    return empresas, rel


def entidad(ticker: str = "", nombre: str = "") -> str | None:
    """Id de la base para un ticker o nombre (o None si no está)."""
    empresas, _ = cargar_base()
    t = (ticker or "").upper().strip()
    if t:
        for fila in empresas.itertuples():
            if t in [x.upper() for x in fila.tickers.split("|") if x]:
                return fila.id
    objetivo = _n(nombre_corto(nombre)) if nombre else ""
    if len(objetivo) >= 3:
        for fila in empresas.itertuples():
            candidatos = [fila.nombre] + [a for a in fila.alias.split("|") if a]
            if any(_n(nombre_corto(c)) == objetivo for c in candidatos):
                return fila.id
    return None


def ficha_entidad(id_: str) -> dict:
    empresas, _ = cargar_base()
    fila = empresas[empresas["id"] == id_]
    if fila.empty:
        return {}
    f = fila.iloc[0]
    return {"id": f["id"], "nombre": f["nombre"], "ticker": (f["tickers"].split("|")[0] if f["tickers"] else ""),
            "sector": f["sector"], "pais": f["pais"]}


def ticker_por_nombre(nombre: str) -> str:
    id_ = entidad(nombre=nombre)
    return ficha_entidad(id_).get("ticker", "") if id_ else ""


def relaciones_base() -> pd.DataFrame:
    empresas, rel = cargar_base()
    nombres = dict(zip(empresas["id"], empresas["nombre"]))
    df = pd.DataFrame({
        "proveedor": rel["proveedor"].map(nombres), "cliente": rel["cliente"].map(nombres), "que": rel["que"],
        "categoria": rel["categoria"], "confianza": rel["confianza"], "fuente": "Base precargada", "nota": rel["nota"],
        "finalidad": rel["finalidad"] if "finalidad" in rel else ""})
    return df.dropna(subset=["proveedor", "cliente"])


def unificar(propias: pd.DataFrame | None = None, extra: pd.DataFrame | None = None) -> pd.DataFrame:
    """Une base + tu tabla (origen→destino) + relaciones extra halladas en la SEC, sin duplicados."""
    partes = [relaciones_base()]
    if propias is not None and len(propias):
        p = propias.rename(columns={"origen": "proveedor", "destino": "cliente", "producto": "que"}).copy()
        p["categoria"], p["confianza"] = "", "tuya"
        p["nota"] = p.get("nota", "")
        p["finalidad"] = p.get("finalidad", "")
        p["fuente"] = "Tu tabla"
        partes.append(p[COLUMNAS])
    if extra is not None and len(extra):
        partes.append(extra.reindex(columns=COLUMNAS))
    df = pd.concat(partes, ignore_index=True).fillna("")
    df = df[(df["proveedor"].str.strip() != "") & (df["cliente"].str.strip() != "")]
    # Normaliza nombres a los de la base cuando coinciden (para que tu "Nvidia" y la base "NVIDIA" sean el mismo nodo)
    empresas, _ = cargar_base()
    canon = {}
    for fila in empresas.itertuples():
        for c in [fila.nombre] + [a for a in fila.alias.split("|") if a]:
            canon[_n(nombre_corto(c))] = fila.nombre
    for col in ("proveedor", "cliente"):
        df[col] = df[col].map(lambda x: canon.get(_n(nombre_corto(x)), x))
    clave = df["proveedor"].map(_n) + "→" + df["cliente"].map(_n)
    return df[~clave.duplicated()].reset_index(drop=True)


def _mismo(a: str, b: str) -> bool:
    return _n(nombre_corto(a)) == _n(nombre_corto(b))


DUPLICADO = "\u200b"  # marca invisible para nodos que aparecen a ambos lados


def real(nodo: str) -> str:
    return str(nodo).replace(DUPLICADO, "")


def vecinos(rel: pd.DataFrame, empresa: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(proveedores = a quién le compra, clientes = a quién le vende)."""
    proveedores = rel[rel["cliente"].map(lambda x: _mismo(x, empresa))]
    clientes = rel[rel["proveedor"].map(lambda x: _mismo(x, empresa))]
    return proveedores, clientes


def grafo(rel: pd.DataFrame, empresa: str, profundidad: int = 1, max_por_nivel: int = 40):
    """(grafo, niveles, centro). Nivel negativo = aguas arriba (proveedores); positivo = clientes."""
    G = nx.DiGraph()
    for r in rel.itertuples():
        G.add_edge(r.proveedor, r.cliente, que=r.que, fuente=r.fuente, confianza=r.confianza)
    centro = next((n for n in G.nodes if _mismo(n, empresa)), None)
    if centro is None:
        return None, {}, None
    nivel = {centro: 0}
    for signo, siguientes in ((-1, G.predecessors), (1, G.successors)):
        frontera = [centro]
        for d in range(1, profundidad + 1):
            nueva = []
            for nodo in frontera:
                for v in list(siguientes(nodo)):
                    if sum(1 for x in nivel.values() if x == signo * d) >= max_por_nivel:
                        break
                    if v not in nivel:
                        nivel[v] = signo * d
                        nueva.append(v)
                    elif d == 1 and nivel[v] < 0 and signo == 1:
                        # Empresa que es a la vez proveedor y cliente (p. ej. Alphabet con Apple):
                        # se dibuja también a la derecha con una copia invisible del nombre.
                        copia = v + DUPLICADO
                        G.add_edge(nodo, copia, **G.edges[nodo, v])
                        nivel[copia] = 1
            frontera = nueva
    sub = G.subgraph(nivel).copy()
    # Solo aristas que avanzan en la cadena (evita flechas cruzadas entre nodos del mismo lado)
    for a, b in list(sub.edges):
        if not (nivel[b] - nivel[a] == 1):
            sub.remove_edge(a, b)
    return sub, nivel, centro


# ----------------------------------------------------------------------------- búsqueda inversa en la SEC
# Patrones sobre la frase de OTRA empresa (la que presenta el informe) donde aparece X (la empresa buscada).
_INTRO = r"(?:such as|including|include|includes|like|namely|:)"
_X_LE_VENDE = [  # X es proveedor de quien informa → quien informa es CLIENTE de X
    r"\b(?:manufactur\w+|suppli\w+|provid\w+|produc\w+|purchas\w+|licens\w+|sourc\w+|acquir\w+|bought|obtain\w*|GPUs?|chips?|"
    r"equipment|components?|tools?|hardware|servers?)\s+(?:[\w.&'-]+\s+){0,2}?(?:from|by)\s+(?:[\w.&'-]+\s+){0,2}?{X}",
    r"\b(?:powered by|built on|based on|running on|deploy\w*|utiliz\w*|leverag\w*|integrat\w*|adopt\w*)\s+(?:[\w.&'-]+\s+){0,3}?{X}",
    r"{X}(?:['’]s)?\s+(?:[A-Z0-9][\w\-+]*\s+){0,4}(?:GPUs?|chips?|processors?|accelerators?|servers?|systems?|platforms?|hardware|software|engines?|equipment|tools?|tool|lithography|components?|cloud)\b",
    r"\b(?:suppliers?|vendors?|foundr\w+|contract manufacturers?|sole[- ]source \w+|single[- ]source \w+|providers?|licensors?)\b[^.;]{0,40}" + _INTRO + r"[^.;]{0,120}{X}",
    r"{X}[^.;]{0,40}\b(?:is|are|as|remains|was)\s+(?:our|a|an|the|one of our)\s+(?:\w+\s+){0,3}(?:suppliers?|vendors?|foundry|manufacturer|licensor|provider)\b",
    r"\b(?:rel(?:y|ies|iance|iant)|depend(?:s|ent|ence)?)\s+(?:up)?on\s+(?:[\w.,&'-]+\s+){0,4}?{X}",
    r"\b(?:purchase|purchases|purchased|purchasing|buy|bought|procure\w*|source[sd]?|sourcing|lease|leasing)\b[^.;]{0,60}{X}",
    r"\bagreements?\s+with\s+{X}\b[^.;]{0,80}\b(?:supply|purchase|provide|manufactur|deliver)",
]
_X_LE_COMPRA = [  # X es cliente de quien informa → quien informa es PROVEEDOR de X
    r"\bcustomers?\b[^.;]{0,30}" + _INTRO + r"[^.;]{0,120}{X}",
    r"{X}[^.;]{0,40}\b(?:accounted for|represented|comprised)\s+(?:approximately\s+|about\s+)?\d",
    r"{X}[^.;]{0,30}\b(?:is|was|are|became|remains|as)\s+(?:our|a|an|one of our)\s+(?:\w+\s+){0,3}customers?\b",
    r"\b(?:sales|revenue|revenues)\s+(?:to|from)\s+(?:[\w.,&'-]+\s+){0,3}?{X}",
    r"\b(?:sell|sells|sold|supply|supplies|supplied|provide[sd]?|deliver\w*)\s+(?:[\w.,&'-]+\s+){0,6}?to\s+(?:[\w.,&'-]+\s+){0,2}?{X}",
    r"\breceivables?\b[^.;]{0,200}{X}",
    r"\b(?:largest|major|key|significant|principal|top)\s+(?:\w+\s+){0,2}customers?\b[^.;]{0,120}{X}",
]
_X_COMPITE = [
    r"\bcompet\w*\b[^.;]{0,160}{X}",
    r"{X}[^.;]{0,30}\b(?:is|are)\s+(?:a|an|our|one of our)\s+(?:\w+\s+){0,2}competitors?\b",
]
_RE_LITIGIO = re.compile(r"\b(?:lawsuits?|litigation|plaintiffs?|defendants?|court|settlements?|antitrust|class action|"
                         r"v\.|arbitration|royalt\w+|patents?|exchange program|shares?|stock|director|officer|served as)\b", re.I)
_RE_VEHICULO = re.compile(r"\b(?:Trust|Mortgage|Issuance|Securiti\w*|Master Note|Receivables|Funding|Credit Card|"
                          r"Auto Loan|Lease|Pass[- ]Through|Certificates)\b|^BANK\s+\d{4}|^CD \d{4}", re.I)
ETIQUETAS = {"cliente": "Cliente (le compra)", "proveedor": "Proveedor (le vende)", "competidor": "Competidor",
             "mencion": "Solo mención"}


def _variantes(nombre: str) -> list[str]:
    base = nombre_corto(nombre)
    vs = {base, nombre.strip()}
    return sorted((v for v in vs if len(v) >= 2), key=len, reverse=True)


def clasificar_frase(frase: str, nombre: str) -> str:
    """Papel de la empresa QUE INFORMA respecto a X: 'cliente', 'proveedor', 'competidor' o 'mencion'."""
    x = "(?-i:" + "|".join(re.escape(v) for v in _variantes(nombre)) + r")\b"  # el nombre, sensible a mayúsculas

    def hay(patrones):
        return any(re.search(p.replace("{X}", x), frase, flags=re.I) for p in patrones)

    if _RE_LITIGIO.search(frase):  # pleitos, acuerdos judiciales, etc.: no indican relación comercial
        return "mencion"
    if hay(_X_LE_COMPRA):
        return "proveedor"
    if hay(_X_COMPITE):
        return "competidor"
    if hay(_X_LE_VENDE):
        return "cliente"
    return "mencion"


def frases_con(texto: str, nombre: str, maximo: int = 40) -> list[str]:
    patron = re.compile(r"\b(?:" + "|".join(re.escape(v) for v in _variantes(nombre)) + r")\b")  # sensible a mayúsculas
    salida = []
    for f in re.split(r"(?<=[.!?])\s+(?=[A-Z])", texto):
        if 30 < len(f) < 900 and patron.search(f):
            salida.append(f.strip())
            if len(salida) >= maximo:
                break
    return salida


def resumir_menciones(frases: list[str], nombre: str) -> tuple[str, str, int]:
    """(relación dominante, mejor frase, nº de frases)."""
    if not frases:
        return "mencion", "", 0
    etiquetas = [clasificar_frase(f, nombre) for f in frases]
    peso = {"proveedor": 1.5, "cliente": 1.0, "competidor": 1.2}  # las señales de proveedor son más específicas
    cuenta = {e: etiquetas.count(e) * peso[e] for e in set(etiquetas) if e != "mencion"}
    if cuenta:
        rel = max(cuenta, key=cuenta.get)
        mejor = next(f for f, e in zip(frases, etiquetas) if e == rel)
    else:
        rel, mejor = "mencion", frases[0]
    return rel, mejor, len(frases)


def _efts(nombre: str, desde: int = 0) -> dict:
    ua = sec_ua()
    if "@" not in ua:
        raise ValueError("La SEC exige identificarse con tu nombre y correo (se guarda solo en tu ordenador).")
    hoy = date.today()
    r = requests.get("https://efts.sec.gov/LATEST/search-index",
                     params={"q": f'"{nombre}"', "forms": "10-K,20-F", "dateRange": "custom",
                             "startdt": (hoy - timedelta(days=480)).isoformat(), "enddt": hoy.isoformat(), "from": desde},
                     headers={"User-Agent": ua}, timeout=30)
    r.raise_for_status()
    return r.json()


def _limpiar_nombre_sec(display: str) -> tuple[str, str]:
    """'CoreWeave, Inc.  (CRWV)  (CIK 0001769628)' → ('CoreWeave, Inc.', 'CRWV')."""
    m = re.match(r"\s*(.*?)\s*(?:\(([A-Z0-9.,\- ]+)\))?\s*\(CIK", display)
    if not m:
        return display, ""
    tickers = (m.group(2) or "").split(",")[0].strip()
    return m.group(1).strip(), tickers


@con_cache(7 * 86400)
def menciones_sec(nombre: str, cik_propio: int | None = None, max_empresas: int = 15) -> pd.DataFrame:
    """Empresas que nombran a `nombre` en su último informe anual y qué relación se deduce."""
    from .suministro import ultimo_informe  # import tardío para evitar ciclos

    candidatos = {}
    for desde in (0, 100, 200):
        datos_ = _efts(nombre, desde)
        for h in datos_.get("hits", {}).get("hits", []):
            s = h["_source"]
            if s.get("file_type") not in ("10-K", "20-F") or not s.get("ciks"):
                continue
            cik = int(s["ciks"][0])
            if cik == cik_propio or cik in candidatos:
                continue
            empresa, tk = _limpiar_nombre_sec(s["display_names"][0])
            # Fuera vehículos financieros (titulizaciones, fideicomisos) y filiales de la propia empresa
            if _RE_VEHICULO.search(empresa) or _n(nombre_corto(nombre)) in _n(empresa):
                continue
            candidatos[cik] = {"empresa": empresa, "ticker": tk, "fecha": s.get("file_date", "")}
        if len(candidatos) >= max_empresas or datos_.get("hits", {}).get("total", {}).get("value", 0) <= desde + 100:
            break
    elegidos = list(candidatos.items())[:max_empresas]

    def analizar(par):
        cik, info = par
        try:
            inf = ultimo_informe(cik)
            frases = frases_con(inf.get("texto", ""), nombre)
        except Exception:  # noqa: BLE001
            frases = []
        rel, mejor, n = resumir_menciones(frases, nombre)
        return {**info, "relacion": rel, "frases": n, "frase": mejor,
                "url": inf.get("url", "") if frases else ""}

    with ThreadPoolExecutor(max_workers=4) as ex:
        filas = list(ex.map(analizar, elegidos))
    df = pd.DataFrame(filas, columns=["empresa", "ticker", "relacion", "frases", "frase", "fecha", "url"])
    df = df[df["frases"] > 0].copy()
    orden = {"cliente": 0, "proveedor": 1, "competidor": 2, "mencion": 3}
    df["_o"] = df["relacion"].map(orden)
    return df.sort_values(["_o", "frases"], ascending=[True, False]).drop(columns="_o").reset_index(drop=True)


def aristas_desde_sec(menciones: pd.DataFrame, empresa: str) -> pd.DataFrame:
    """Convierte las menciones de cliente / proveedor en relaciones para el mapa."""
    filas = []
    for r in menciones.itertuples():
        if r.relacion == "cliente":  # la otra empresa le compra a `empresa`
            filas.append({"proveedor": empresa, "cliente": nombre_corto(r.empresa)})
        elif r.relacion == "proveedor":  # la otra empresa le vende a `empresa`
            filas.append({"proveedor": nombre_corto(r.empresa), "cliente": empresa})
        else:
            continue
        filas[-1].update({"que": r.frase[:160] + ("…" if len(r.frase) > 160 else ""), "categoria": "",
                          "confianza": "inferida", "fuente": "Informes SEC (automático)", "nota": r.url})
    return pd.DataFrame(filas, columns=COLUMNAS)


def aristas_desde_informe_propio(evidencias: pd.DataFrame, empresa: str) -> pd.DataFrame:
    """Proveedores que la propia empresa nombra en su informe anual."""
    filas = []
    for r in evidencias.itertuples():
        if r.tipo != "proveedor" or not r.empresas:
            continue
        for nombre in [x.strip() for x in r.empresas.split(",") if x.strip()]:
            if len(nombre_corto(nombre)) < 3 or _mismo(nombre, empresa):
                continue
            filas.append({"proveedor": nombre_corto(nombre), "cliente": empresa, "que": r.frase[:160],
                          "categoria": "", "confianza": "alta", "fuente": "Su informe anual (SEC)", "nota": ""})
    return pd.DataFrame(filas, columns=COLUMNAS)
