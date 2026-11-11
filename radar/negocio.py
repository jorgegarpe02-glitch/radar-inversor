"""De dónde viene el dinero de una empresa y a dónde va lo que produce.

Dos fuentes, por orden de fiabilidad:

1. Informe anual en la SEC (10-K / 20-F): las empresas que cotizan en EE. UU. etiquetan sus ingresos por segmento,
   producto y país en un fichero de datos (XBRL). Se lee ese fichero, así que las cifras son las oficiales del último
   ejercicio. Sirve para NVIDIA, Apple, Microsoft… y también para extranjeras con 20-F (ASML, TSMC, Santander, Novo…).
2. Base propia (datos/segmentos.csv): reparto aproximado para las grandes empresas, incluidas las europeas que no
   presentan en la SEC (Inditex, Iberdrola, Repsol, Rheinmetall…). Son porcentajes orientativos de su último ejercicio.

Los clientes con su finalidad («Microsoft compra GPU para los centros de datos de Azure») salen de la base de
relaciones (datos/relaciones_base.csv, columna «finalidad») y de tu propia tabla.
"""
from __future__ import annotations

import itertools
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .cache import con_cache

CARPETA_DATOS = Path(__file__).resolve().parent.parent / "datos"
EJES = {"negocio": "Por línea de negocio", "producto": "Por producto o servicio", "geografia": "Por zona geográfica",
        "cliente": "Por tipo de cliente"}

# ----------------------------------------------------------------------------- base propia
@lru_cache(maxsize=1)
def _segmentos_base() -> pd.DataFrame:
    ruta = CARPETA_DATOS / "segmentos.csv"
    if not ruta.exists():
        return pd.DataFrame(columns=["id", "eje", "segmento", "pct", "descripcion", "ejercicio"])
    df = pd.read_csv(ruta, dtype=str).fillna("")
    df["pct"] = pd.to_numeric(df["pct"], errors="coerce")
    return df


def segmentos_base(id_: str | None) -> dict[str, pd.DataFrame]:
    """eje → tabla (segmento, pct, descripcion, ejercicio) de la base propia."""
    if not id_:
        return {}
    df = _segmentos_base()
    df = df[df["id"] == id_]
    return {eje: g.drop(columns=["id", "eje"]).sort_values("pct", ascending=False).reset_index(drop=True)
            for eje, g in df.groupby("eje", sort=False)}


# ----------------------------------------------------------------------------- SEC (XBRL)
_CONCEPTOS_INGRESOS = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                       "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet", "Revenue",
                       "RevenuesNetOfInterestExpense", "RevenueFromContractsWithCustomers")
_EJE_DE = {"StatementBusinessSegmentsAxis": "negocio", "SegmentsAxis": "negocio", "ProductOrServiceAxis": "producto",
           "ProductsAndServicesAxis": "producto", "StatementGeographicalAxis": "geografia", "GeographicalAreasAxis": "geografia",
           "MajorCustomersAxis": "cliente"}
_IGNORAR_DIM = {"ConsolidationItemsAxis": {"OperatingSegmentsMember", "ReportableSegmentsMember"}}
_PAISES = {"US": "Estados Unidos", "CN": "China", "TW": "Taiwán", "JP": "Japón", "KR": "Corea del Sur", "DE": "Alemania",
           "GB": "Reino Unido", "FR": "Francia", "ES": "España", "IT": "Italia", "NL": "Países Bajos", "IE": "Irlanda",
           "SG": "Singapur", "IN": "India", "BR": "Brasil", "MX": "México", "CA": "Canadá", "AU": "Australia", "CH": "Suiza",
           "HK": "Hong Kong", "IL": "Israel", "SA": "Arabia Saudí", "AE": "Emiratos Árabes", "SE": "Suecia", "DK": "Dinamarca",
           "NO": "Noruega", "BE": "Bélgica", "PL": "Polonia", "TR": "Turquía", "AR": "Argentina", "CL": "Chile", "PT": "Portugal"}
# Solo se traducen nombres completos conocidos: traducir palabra a palabra deja mezclas ilegibles («Server Productos y Nube…»)
_NOMBRES = {
    "data center": "Centros de datos", "gaming": "Videojuegos", "automotive": "Automoción",
    "professional visualization": "Visualización profesional", "compute and networking": "Computación y redes",
    "compute": "Computación", "networking": "Redes", "graphics": "Gráficos", "oem and other": "Fabricantes y otros",
    "other countries": "Otros países", "other": "Otros", "all other": "Otros", "product": "Productos", "products": "Productos",
    "service": "Servicios", "services": "Servicios", "americas": "América", "europe": "Europa",
    "greater china": "China (con Hong Kong y Taiwán)", "china including hong kong": "China (con Hong Kong)", "japan": "Japón",
    "rest of asia pacific": "Resto de Asia-Pacífico", "asia pacific": "Asia-Pacífico",
    "wearables homeand accessories": "Wearables, hogar y accesorios", "i phone": "iPhone", "i pad": "iPad", "mac": "Mac",
    "united states": "Estados Unidos", "non us": "Fuera de EE. UU.", "international": "Internacional",
    "north america": "Norteamérica", "latin america": "Latinoamérica", "emea": "Europa, Oriente Medio y África",
    "europe middle east and africa": "Europa, Oriente Medio y África", "middle east": "Oriente Medio", "africa": "África",
    "cloud": "Nube", "advertising": "Publicidad", "subscription services": "Suscripciones", "hardware": "Hardware",
    "software": "Software", "energy": "Energía", "aeronautics": "Aeronáutica", "space": "Espacio",
    "missiles and fire control": "Misiles y control de fuego", "rotary and mission systems": "Sistemas rotatorios y de misión",
    "us government": "Gobierno de EE. UU.", "commercial": "Comercial", "upstream": "Exploración y producción",
    "downstream": "Refino y comercialización", "chemical": "Química", "chemicals": "Química", "online stores": "Tienda online",
    "physical stores": "Tiendas físicas", "third party seller services": "Servicios a vendedores", "other services": "Otros servicios",
    "amazon web services": "AWS (nube)", "intelligent cloud": "Nube inteligente",
    "productivity and business processes": "Productividad y procesos de negocio", "more personal computing": "Informática personal",
    "server products and cloud services": "Servidores y nube (Azure)", "windows and devices": "Windows y dispositivos",
    "search advertising": "Publicidad en buscador", "linked in corporation": "LinkedIn", "xbox": "Xbox",
    "microsoft three six five commercial products and cloud services": "Microsoft 365 para empresas",
    "microsoft three six five consumer products and cloud services": "Microsoft 365 para particulares",
    "dynamics products and cloud services": "Dynamics", "enterprise and partner services": "Servicios a empresas",
    "wafer": "Obleas (fabricación de chips)", "other products": "Otros productos", "automotive sales": "Venta de coches",
    "energy generation and storage": "Energía y almacenamiento", "services and other": "Servicios y otros",
    "google search other": "Búsqueda de Google", "you tube advertising revenue": "Anuncios en YouTube",
    "google network": "Red de Google", "google cloud": "Google Cloud", "google services": "Servicios de Google",
    "subscriptions platforms and devices revenue": "Suscripciones, plataformas y dispositivos", "other bets": "Otras apuestas",
    "energy generation and storage sales": "Venta de baterías y solar", "automotive regulatory credits": "Créditos regulatorios",
    "automotive leasing": "Alquiler de coches", "energy generation and storage leasing": "Alquiler de energía solar",
    "family of apps": "Aplicaciones (Facebook, Instagram, WhatsApp)", "reality labs": "Reality Labs (gafas y metaverso)",
    "service and field options": "Servicio y mejoras", "metrology and inspection": "Metrología e inspección",
    "taiwan": "Taiwán", "south korea": "Corea del Sur", "germany": "Alemania", "united kingdom": "Reino Unido", "china": "China",
    "rest of world": "Resto del mundo", "rest of the world": "Resto del mundo", "asia": "Asia",
}


def nombre_miembro(miembro: str) -> str:
    """'nvda:DataCenterMember' → 'Centros de datos'; 'country:US' → 'Estados Unidos'. Lo que no conoce lo deja en inglés."""
    prefijo, _, local = miembro.partition(":")
    if prefijo == "country":
        return _PAISES.get(local, local)
    local = re.sub(r"(Segment)?Member$", "", local)
    texto = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", local).strip()
    clave = re.sub(r"\s+", " ", texto.lower().replace(" segment", "").replace(" revenue", "")).strip()
    for c in (clave, texto.lower()):
        if c in _NOMBRES:
            return _NOMBRES[c]
    return texto.replace("Three Six Five", "365").replace("Linked In", "LinkedIn").replace("You Tube", "YouTube") or local


def _dias(inicio: str, fin: str) -> int:
    return (date.fromisoformat(fin) - date.fromisoformat(inicio)).days


def leer_xbrl(contenido: bytes) -> dict:
    """Ingresos del último ejercicio completo por eje (negocio, producto, geografía) a partir de un fichero XBRL."""
    from lxml import etree

    raiz = etree.fromstring(contenido)
    ns = {"x": "http://www.xbrl.org/2003/instance", "d": "http://xbrl.org/2006/xbrldi"}
    contextos = {}
    for c in raiz.findall("x:context", ns):
        ini, fin = c.findtext("x:period/x:startDate", namespaces=ns), c.findtext("x:period/x:endDate", namespaces=ns)
        if not ini or not fin:
            continue
        dims = []
        for m in c.findall(".//d:explicitMember", ns):
            eje, miembro = m.get("dimension", "").split(":")[-1], (m.text or "").strip()
            if miembro.split(":")[-1] in _IGNORAR_DIM.get(eje, ()):
                continue
            dims.append((eje, miembro))
        contextos[c.get("id")] = (ini, fin, dims)
    hechos = []
    for el in raiz:
        if not isinstance(el.tag, str):
            continue
        if etree.QName(el).localname in _CONCEPTOS_INGRESOS and el.get("contextRef") in contextos and (el.text or "").strip():
            ini, fin, dims = contextos[el.get("contextRef")]
            if 340 <= _dias(ini, fin) <= 380:
                try:
                    hechos.append((fin, dims, float(el.text), etree.QName(el).localname))
                except ValueError:
                    pass
    if not hechos:
        return {}
    ultimo = max(h[0] for h in hechos)
    hechos = [h for h in hechos if h[0] == ultimo]
    totales = [h[2] for h in hechos if not h[1]]
    if not totales:
        return {}
    total = max(totales)
    ejes: dict[str, dict[str, float]] = {}
    for _, dims, valor, _ in hechos:
        if len(dims) != 1 or valor <= 0:
            continue
        eje = _EJE_DE.get(dims[0][0])
        if not eje:
            continue
        ejes.setdefault(eje, {})
        ejes[eje][dims[0][1]] = max(valor, ejes[eje].get(dims[0][1], 0))
    salida = {}
    for eje, miembros in ejes.items():
        if len(miembros) < 2:
            continue
        tabla = _jerarquia(miembros, total)
        if not tabla.empty:
            salida[eje] = tabla
    return {"ejercicio_fin": ultimo, "total": total, "ejes": salida} if salida else {}


def _subconjunto(items: list[tuple[str, float]], objetivo: float, tolerancia: float, mas_fino: bool, minimo: int = 2):
    """Subconjunto de `items` que suma `objetivo`. `mas_fino`: el de más miembros; si no, el de menos."""
    items = items[:13]
    tamanos = range(len(items), minimo - 1, -1) if mas_fino else range(minimo, len(items) + 1)
    for k in tamanos:
        for combo in itertools.combinations(items, k):
            if abs(sum(v for _, v in combo) - objetivo) <= tolerancia:
                return list(combo)
    return None


def _jerarquia(miembros: dict[str, float], total: float) -> pd.DataFrame:
    """Reparto de primer nivel (el que suma el total con menos partidas) y, bajo cada partida, su desglose si lo hay.

    Así «Centros de datos» queda arriba con «Computación» y «Redes» debajo, en vez de mezclarse como si fueran iguales.
    """
    items = sorted(miembros.items(), key=lambda kv: -kv[1])

    def particion(candidatos):
        return (_subconjunto(candidatos, total, max(2e-5 * total, 2.0), mas_fino=False)
                or _subconjunto(candidatos, total, 0.006 * total, mas_fino=False))

    primer = particion(items)
    if primer is None:  # no hay un reparto que cuadre: se enseñan todas las partidas tal cual
        return pd.DataFrame([{"segmento": nombre_miembro(n), "valor": v, "pct": 100 * v / total, "nivel": 0} for n, v in items])
    # Si el reparto más grueso es poco informativo (p. ej. «Productos / Servicios») y las demás partidas forman por sí solas
    # otro reparto completo y más detallado que no encaja como desglose del primero, se prefiere el detallado.
    resto_total = [(x, y) for x, y in items if x not in {n for n, _ in primer}]
    segundo = particion(resto_total) if len(resto_total) >= 3 else None
    if segundo and len(segundo) > len(primer):
        encaja = any(_subconjunto([(x, y) for x, y in resto_total if y < v], v, max(2e-5 * v, 2.0), True) for _, v in primer
                     if len([1 for _, y in resto_total if y < v]) >= 2)
        if not encaja:
            primer = segundo
    usados = {n for n, _ in primer}
    filas = []
    for n, v in sorted(primer, key=lambda kv: -kv[1]):
        filas.append({"segmento": nombre_miembro(n), "valor": v, "pct": 100 * v / total, "nivel": 0})
        resto = [(x, y) for x, y in items if x not in usados and y < v]
        hijos = _subconjunto(resto, v, max(2e-5 * v, 2.0), mas_fino=True) if len(resto) >= 2 else None
        for h, vh in sorted(hijos or [], key=lambda kv: -kv[1]):
            usados.add(h)
            filas.append({"segmento": "↳ " + nombre_miembro(h), "valor": vh, "pct": 100 * vh / total, "nivel": 1})
    return pd.DataFrame(filas)


@con_cache(15 * 86400)
def segmentos_sec(cik: int) -> dict:
    """Desglose oficial de ingresos del último informe anual (10-K / 20-F / 40-F)."""
    from .suministro import _sec_get

    sub = _sec_get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json").json()
    rec = sub["filings"]["recent"]
    for i, forma in enumerate(rec["form"]):
        if forma not in ("10-K", "20-F", "40-F"):
            continue
        acc = rec["accessionNumber"][i].replace("-", "")
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/"
        doc = rec["primaryDocument"][i]
        try:
            contenido = _sec_get(base + re.sub(r"\.html?$", "_htm.xml", doc)).content
        except Exception:  # noqa: BLE001 - algunos informes guardan los datos con otro nombre
            indice = _sec_get(base + "index.json").json()
            nombres = [x["name"] for x in indice.get("directory", {}).get("item", [])]
            xml = next((n for n in nombres if n.endswith("_htm.xml")), None) or next(
                (n for n in nombres if n.endswith(".xml") and not re.search(r"_(cal|def|lab|pre)\.xml$|FilingSummary", n)), None)
            if not xml:
                return {}
            contenido = _sec_get(base + xml).content
        r = leer_xbrl(contenido)
        if r:
            r.update(forma=forma, fecha=rec["filingDate"][i], url=base + doc)
        return r
    return {}


def segmentos(ticker: str, id_base: str | None = None, usar_sec: bool = True) -> dict:
    """{'ejes': {eje: tabla}, 'fuente': texto, 'oficial': bool, 'url': …}. Combina SEC (oficial) y base propia."""
    salida = {"ejes": {}, "fuente": "", "oficial": False, "url": "", "ejercicio": ""}
    if usar_sec:
        try:
            from .suministro import cik_de

            cik = cik_de(ticker)
            if cik:
                s = segmentos_sec(cik)
                if s:
                    salida.update(ejes=dict(s["ejes"]), oficial=True, url=s["url"], ejercicio=f"ejercicio cerrado el {s['ejercicio_fin']}",
                                  fuente=f"Informe anual {s['forma']} presentado a la SEC el {s['fecha']} (cifras oficiales)",
                                  total=s["total"])
        except Exception:  # noqa: BLE001 - sin contacto para la SEC o sin conexión: se usa la base propia
            pass
    base = segmentos_base(id_base)
    for eje, tabla in base.items():
        if eje not in salida["ejes"]:
            salida["ejes"][eje] = tabla.assign(aprox=True)
        elif "descripcion" in tabla:
            salida.setdefault("descripciones", {})[eje] = tabla
    if base and not salida["oficial"]:
        salida["fuente"] = "Base del programa (reparto aproximado del último ejercicio: verifícalo en el informe anual)"
        ejercicios = {e for t in base.values() for e in t["ejercicio"] if e}
        salida["ejercicio"] = ", ".join(sorted(ejercicios))
    return salida


_GENERICOS = {"productos", "servicios", "sales and services", "service other", "otros productos", "otros servicios"}
_REGIONES = {"américa", "europa", "japón", "china", "norteamérica", "internacional", "asia-pacífico", "resto de asia-pacífico",
             "china (con hong kong y taiwán)", "estados unidos", "latinoamérica", "europa, oriente medio y áfrica", "asia",
             "fuera de ee. uu.", "resto del mundo"}


def _primer_nivel(t: pd.DataFrame) -> pd.DataFrame:
    return (t[t["nivel"] == 0] if "nivel" in t else t).sort_values("pct", ascending=False)


def _titulares(t: pd.DataFrame) -> pd.DataFrame:
    """Partidas con las que se resume el negocio: las de primer nivel, bajando un nivel cuando son genéricas («Productos»)."""
    if "nivel" not in t:
        return t.sort_values("pct", ascending=False)
    filas, lista = [], t.reset_index(drop=True)
    for i, r in lista.iterrows():
        if r["nivel"] != 0:
            continue
        hijos = []
        for j in range(i + 1, len(lista)):
            if lista.at[j, "nivel"] == 0:
                break
            hijos.append(lista.iloc[j])
        if hijos and str(r["segmento"]).lower() in _GENERICOS:
            filas += [h.copy() for h in hijos]
        else:
            filas.append(r.copy())
    df = pd.DataFrame(filas)
    df["segmento"] = df["segmento"].str.replace("↳ ", "", regex=False)
    return df.sort_values("pct", ascending=False)


def eje_principal(seg: dict) -> str | None:
    """Entre «producto» y «negocio», el desglose que mejor cuenta a qué se dedica (no el que solo reparte por regiones)."""
    candidatos = []
    for i, e in enumerate(("producto", "negocio")):
        t = seg.get("ejes", {}).get(e)
        if t is None or not len(t):
            continue
        tit = _titulares(t)
        nombres = [str(x).lower() for x in tit["segmento"]]
        if sum(n in _REGIONES for n in nombres) >= 0.6 * len(nombres):
            continue  # hay empresas (Apple) cuyos «segmentos» oficiales son regiones
        informativas = sum(n not in _GENERICOS for n in nombres)
        candidatos.append((informativas, -i, e))
    return max(candidatos)[2] if candidatos else None


def principal(seg: dict) -> tuple[str, float] | None:
    """(nombre del negocio que más pesa, % de los ingresos)."""
    eje = eje_principal(seg)
    if not eje:
        return None
    fila = _titulares(seg["ejes"][eje]).iloc[0]
    return str(fila["segmento"]), float(fila["pct"])


def frase_resumen(nombre: str, seg: dict) -> str:
    """«El 90 % de lo que ingresa NVIDIA viene de Centros de datos; después Videojuegos (7 %)…»"""
    eje = eje_principal(seg)
    if not eje:
        return ""
    t = seg["ejes"][eje]
    t0 = _titulares(t)
    p = t0.iloc[0]
    aprox = "En torno al " if (not seg.get("oficial") or "aprox" in t) else "El "
    texto = f"{aprox}{p['pct']:.0f} % de lo que ingresa {nombre} viene de **{p['segmento']}**"
    resto = [f"{r['segmento']} ({r['pct']:.0f} %)" for _, r in t0.iloc[1:4].iterrows() if r["pct"] >= 1]
    if resto:
        texto += "; después " + ", ".join(resto)
    return texto + "."


# ----------------------------------------------------------------------------- clientes con finalidad
def clientes_con_finalidad(rel: pd.DataFrame, empresa: str) -> pd.DataFrame:
    """Quién le compra, qué le compra y para qué lo usa."""
    from .conexiones import _mismo

    if rel is None or rel.empty:
        return pd.DataFrame(columns=["Cliente", "Qué le compra", "Para qué", "Fuente", "Confianza"])
    cli = rel[rel["proveedor"].map(lambda x: _mismo(x, empresa))]
    cli = cli[cli["categoria"].fillna("") != "Accionista"]
    df = pd.DataFrame({"Cliente": cli["cliente"], "Qué le compra": cli["que"],
                       "Para qué": cli["finalidad"] if "finalidad" in cli else "", "Categoría": cli["categoria"],
                       "Fuente": cli["fuente"], "Confianza": cli["confianza"]})
    return df.reset_index(drop=True)


def proveedores_con_finalidad(rel: pd.DataFrame, empresa: str) -> pd.DataFrame:
    from .conexiones import _mismo

    if rel is None or rel.empty:
        return pd.DataFrame(columns=["Proveedor", "Qué le vende", "Para qué", "Fuente", "Confianza"])
    prov = rel[rel["cliente"].map(lambda x: _mismo(x, empresa))]
    prov = prov[prov["categoria"].fillna("") != "Accionista"]
    return pd.DataFrame({"Proveedor": prov["proveedor"], "Qué le vende": prov["que"],
                         "Para qué": prov["finalidad"] if "finalidad" in prov else "", "Categoría": prov["categoria"],
                         "Fuente": prov["fuente"], "Confianza": prov["confianza"]}).reset_index(drop=True)


def por_categoria(clientes: pd.DataFrame) -> pd.DataFrame:
    """Cuántos clientes conocidos hay de cada tipo de producto (para ver a qué se dedica lo que vende)."""
    if clientes.empty or "Categoría" not in clientes:
        return pd.DataFrame()
    g = clientes.groupby("Categoría").agg(Clientes=("Cliente", lambda s: ", ".join(list(s)[:8]) + ("…" if len(s) > 8 else "")),
                                          n=("Cliente", "count")).reset_index()
    return g.sort_values("n", ascending=False)
