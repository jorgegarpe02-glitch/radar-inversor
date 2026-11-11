"""Noticias activas (Google News RSS, gratis) con un termómetro de sentimiento muy simple.

Las búsquedas se filtran para quedarse con noticias de economía y mercados: si buscas «oro» no debe salir el
Balón de Oro, ni con «Santander» el Racing, ni con «Repsol» las motos. Tres piezas:

1. CONSULTAS_ACTIVO: para materias primas, divisas y temas ambiguos se busca por el activo («precio del oro», «onza»,
   «gold price») en vez de por la palabra suelta.
2. Un filtro que puntúa cada titular: suma si viene de un medio financiero o habla de precios, bolsa, resultados…
   y descarta si es deporte, espectáculos, cocina, etc.
3. Modo «empresa» (más permisivo: basta con que no sea ruido) y modo «activo» (estricto: tiene que oler a mercados).
"""
from __future__ import annotations

import email.utils
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

from .cache import con_cache
from .config import UA_WEB

TEMAS = {
    "Petróleo y gas": "petróleo gas OPEP precios",
    "Defensa y aeroespacial": "defensa aeroespacial contratos presupuesto OTAN",
    "Energías renovables": "renovables eólica solar inversión",
    "Semiconductores e IA": "semiconductores chips inteligencia artificial",
    "Bancos centrales y tipos": "BCE Reserva Federal tipos de interés",
    "Aranceles y comercio": "aranceles comercio exterior",
    "Industria y automoción": "industria manufacturera automoción pedidos",
}

TEMAS_EN = {
    "Petróleo y gas": "oil gas OPEC prices",
    "Defensa y aeroespacial": "defense aerospace contracts NATO spending",
    "Energías renovables": "renewable energy wind solar investment",
    "Semiconductores e IA": "semiconductors chips artificial intelligence",
    "Bancos centrales y tipos": "ECB Federal Reserve interest rates",
    "Aranceles y comercio": "tariffs trade",
    "Industria y automoción": "manufacturing automotive orders",
}

POSITIVAS = set(
    """sube suben subida dispara disparan record beneficio beneficios crece crecimiento mejora mejoran contrato
    adjudica adjudicacion dividendo recompra impulsa impulso gana ganancias supera positivo optimismo alcista
    beat beats surge surges soar soars rally rallies gain gains growth upgrade upgraded profit profits strong
    bullish outperform wins win expands boost rise rises jump jumps approval approved buyback dividend""".split()
)
NEGATIVAS = set(
    """cae caen caida desploma hunde hundimiento perdidas perdida recorte recortes despidos ere multa sancion
    sanciones investigacion fraude quiebra huelga retraso retrasos rebaja alerta advierte riesgo bajista
    miss misses plunge plunges fall falls drop drops slump loss losses downgrade downgraded lawsuit probe
    investigation recall cut cuts layoffs weak bearish underperform warning warns bankruptcy default delay
    delays strike fine fined halt ban tariff tariffs sanctions""".split()
)
NEGADORES = {"no", "sin", "not", "never", "nunca"}


def _normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def sentimiento(texto: str) -> float:
    """-1 (muy negativo) a +1 (muy positivo). Método orientativo basado en palabras clave."""
    palabras = re.findall(r"[a-z0-9]+", _normalizar(texto))
    pos = neg = 0
    for i, p in enumerate(palabras):
        invertir = i > 0 and palabras[i - 1] in NEGADORES
        if p in POSITIVAS:
            neg, pos = (neg + 1, pos) if invertir else (neg, pos + 1)
        elif p in NEGATIVAS:
            pos, neg = (pos + 1, neg) if invertir else (pos, neg + 1)
    total = pos + neg
    return 0.0 if total == 0 else (pos - neg) / total


def etiqueta(valor: float) -> str:
    return "🟢" if valor >= 0.25 else "🔴" if valor <= -0.25 else "⚪"


# ----------------------------------------------------------------------------- filtro de noticias financieras
# palabra (sin tildes, minúsculas) → (consulta en español, consulta en inglés)
CONSULTAS_ACTIVO = {
    "oro": ('"precio del oro" OR "onza de oro" OR "oro" cotización OR "oro" lingotes inversores',
            '"gold price" OR "gold prices" OR "spot gold" OR "gold futures" OR bullion'),
    "plata": ('"precio de la plata" OR "onza de plata" OR "plata" cotización metales',
              '"silver price" OR "silver prices" OR "spot silver" OR "silver futures"'),
    "cobre": ('"precio del cobre" OR "cobre" cotización OR "cobre" minería demanda', '"copper price" OR "copper prices" OR "copper futures"'),
    "platino": ('"precio del platino" OR "platino" cotización', '"platinum price" OR "platinum prices"'),
    "paladio": ('"precio del paladio" OR "paladio" cotización', '"palladium price" OR "palladium prices"'),
    "aluminio": ('"precio del aluminio" OR "aluminio" cotización', '"aluminum price" OR "aluminium price"'),
    "niquel": ('"precio del níquel" OR "níquel" cotización', '"nickel price" OR "nickel prices"'),
    "litio": ('"precio del litio" OR "litio" minería baterías', '"lithium price" OR "lithium prices" OR lithium miners'),
    "uranio": ('"precio del uranio" OR "uranio" nuclear demanda', '"uranium price" OR "uranium prices" OR uranium miners'),
    "mineral de hierro": ('"mineral de hierro" precio', '"iron ore price" OR "iron ore prices"'),
    "petroleo": ('"precio del petróleo" OR Brent OR "barril" OPEP', '"oil price" OR "oil prices" OR Brent OR WTI OR OPEC'),
    "petroleo brent": ('Brent "barril" OR "precio del petróleo" OR OPEP', '"Brent crude" OR "oil prices" OR OPEC'),
    "petroleo wti": ('WTI "barril" OR "precio del petróleo"', '"WTI crude" OR "oil prices" OR "crude futures"'),
    "brent": ('Brent "barril" OR "precio del petróleo"', '"Brent crude" OR "oil prices"'),
    "gas": ('"precio del gas" OR "gas natural" TTF OR "gas natural" precio', '"natural gas prices" OR "natural gas futures" OR LNG prices'),
    "gas natural": ('"precio del gas" OR "gas natural" TTF OR "gas natural" precio', '"natural gas prices" OR "natural gas futures" OR "Henry Hub"'),
    "trigo": ('"precio del trigo" OR "trigo" cosecha mercados', '"wheat prices" OR "wheat futures"'),
    "maiz": ('"precio del maíz" OR "maíz" cosecha mercados', '"corn prices" OR "corn futures"'),
    "soja": ('"precio de la soja" OR "soja" cosecha mercados', '"soybean prices" OR "soybean futures"'),
    "cafe": ('"precio del café" OR "café" futuros cosecha', '"coffee prices" OR "coffee futures" OR arabica prices'),
    "cacao": ('"precio del cacao" OR "cacao" futuros cosecha', '"cocoa prices" OR "cocoa futures"'),
    "azucar": ('"precio del azúcar" OR "azúcar" futuros', '"sugar prices" OR "sugar futures"'),
    "algodon": ('"precio del algodón" OR "algodón" futuros', '"cotton prices" OR "cotton futures"'),
    "carbon": ('"precio del carbón" OR "carbón" térmico demanda', '"coal prices" OR "thermal coal"'),
    "bitcoin": ('bitcoin precio OR bitcoin cotización OR bitcoin ETF', 'bitcoin price OR bitcoin ETF'),
    "euro": ('"euro dólar" OR "EUR/USD" OR "tipo de cambio" euro', '"EUR/USD" OR "euro dollar" exchange rate'),
    "dolar": ('"euro dólar" OR "índice dólar" OR "tipo de cambio" dólar', '"dollar index" OR "US dollar" currency markets'),
    "bolsa": ('bolsa hoy Ibex OR "Wall Street" cierre', '"stock market today" OR "Wall Street" stocks'),
    "ibex": ('"Ibex 35"', '"IBEX 35"'), "ibex 35": ('"Ibex 35"', '"IBEX 35"'),
}

# Medios de economía y mercados: un titular suyo cuenta como financiero aunque no use palabras clave
FUENTES_FINANCIERAS = (
    "expansion", "cinco dias", "cincodias", "el economista", "eleconomista", "bolsamania", "estrategias de inversion",
    "invertia", "investing", "capital radio", "capitalradio", "finanzas.com", "la informacion", "el confidencial",
    "vozpopuli", "merca2", "el blog salmon", "fundssociety", "funds society", "rankia", "self bank", "valencia plaza",
    "economia digital", "economiadigital", "negocios", "bloomberg", "reuters", "cnbc", "financial times", "ft.com",
    "wall street journal", "wsj", "marketwatch", "barron", "yahoo finance", "yahoo finanzas", "seeking alpha",
    "motley fool", "kitco", "mining.com", "fxstreet", "fx empire", "fxempire", "dailyfx", "oilprice", "s&p global",
    "argus", "nasdaq", "tipranks", "benzinga", "zacks", "business insider", "the economist", "forbes", "fortune",
    "morningstar", "investopedia", "thestreet", "trading economics", "tradingview", "ig.com", "xtb", "europa press",
    "efe", "bolsa de madrid", "cnmv", "los replicantes", "world gold council", "mining weekly", "energy voice",
    "rigzone", "splash247", "lloyd's list", "tradewinds", "hellenic shipping", "defense news", "breaking defense",
    "infodefensa", "semiconductor", "digitimes", "the information", "techcrunch", "la vanguardia", "el pais", "el mundo",
    "abc", "20minutos", "rtve", "cope", "ser", "onda cero", "la razon", "el espanol", "el periodico", "publico",
)
_FUENTES_GENERALISTAS = {"la vanguardia", "el pais", "el mundo", "abc", "20minutos", "rtve", "cope", "ser", "onda cero",
                         "la razon", "el espanol", "el periodico", "publico", "europa press", "efe", "forbes", "fortune"}

_RE_FINANZAS = re.compile(
    r"\b(precios?|cotiza\w*|bolsas?|mercados?|inversor\w*|inversion\w*|acciones|accionistas?|dividendos?|beneficios?|"
    r"resultados|ingresos|ventas|facturacion|ganancias|perdidas|ebitda|deuda|bonos?|tipos de interes|inflacion|pib|"
    r"bce|fed|reserva federal|banco central|bancos centrales|futuros|onza|barril|maximos?|minimos?|record|rally|"
    r"alcista|bajista|dolar|euro|divisas?|aranceles?|opep|refugio|lingotes?|etf|fondos?|analistas?|objetivo|"
    r"recomendacion|opa|fusion|adquisicion|compra de|contrato|pedido|adjudica\w*|produccion|demanda|oferta|"
    r"exporta\w*|importa\w*|mineria|mineras?|minas?|yacimiento|reservas|cosecha|suministro|ibex|nasdaq|dow jones|"
    r"s&p|wall street|cnmv|sec|trimestre|previsiones|guia|capitalizacion|valoracion|recompra|ampliacion de capital|"
    r"salida a bolsa|quiebra|concurso de acreedores|ere|despidos|inversion|plan estrategico|acuerdo|alianza|lanza|anuncia|"
    r"fabrica|planta|ceo|consejero delegado|banco|banca|negocio|empresa|compania|clientes|chips?|centros? de datos|"
    r"launch\w*|announc\w+|deal|partnership|plant|factory|company|business|bank|customers?|data cent\w+|"
    r"prices?|stocks?|shares?|markets?|investors?|earnings|revenue|profit|sales|dividend|guidance|outlook|forecast|"
    r"futures|ounce|bullion|spot|rally|record high|all-time high|slump|surge|rate cut|rate hike|rates|treasur\w+|yields?|"
    r"inflation|central banks?|tariffs?|opec|haven|etfs?|funds?|analysts?|target|upgrade|downgrade|merger|acquisition|"
    r"takeover|buyback|ipo|contract|order|output|production|demand|supply|exports?|imports?|miners?|mining|mine|"
    r"reserves|harvest|quarter|quarterly|valuation|market cap|bankruptcy|layoffs|trading|traders?|hedge|commodit\w+)\b")

_RE_RUIDO = re.compile(
    r"\b(balon de oro|bota de oro|guante de oro|medallas? de (?:oro|plata|bronce)|oro olimpico|plata olimpica|"
    r"disco de (?:oro|platino)|globos? de oro|oso de oro|leon de oro|concha de (?:oro|plata)|palma de oro|"
    r"bodas de (?:oro|plata)|edad de oro|siglo de oro|epoca dorada|regla de oro|"
    r"corazon de oro|pico de oro|botin de oro|micro de oro|antena de oro|goya|oscar|grammy|emmy|eurovision|"
    r"golden globes?|golden boot|ballon d.?or|gold medal\w*|silver medal\w*|golden boy|golden state|"
    r"futbol|futbolista|liga santander|laliga|champions|europa league|mundial de|eurocopa|copa del rey|gol|goles|"
    r"jugador\w*|entrenador\w*|delantero|portero|fichaje|vestuario|partido de|derbi|clasico|tenis|roland garros|"
    r"wimbledon|nba|baloncesto|euroliga|motogp|moto gp|formula 1|f1|gran premio|ciclismo|vuelta a espana|tour de francia|"
    r"juegos olimpicos|olimpiadas?|atletismo|boxeo|ufc|racing de santander|real madrid|barcelona fc|fc barcelona|"
    r"atletico de madrid|pelicula|serie de|temporada \d|estreno|actor|actriz|cantante|concierto|festival de|album|"
    r"gala|alfombra roja|reality|horoscopo|receta|recetas|loteria|sorteo|euromillones|bonoloto|primitiva|"
    r"football|soccer|premier league|nfl|mlb|nhl|olympics?|tournament|championship game|playoffs?|"
    r"movie|film|actress|singer|concert|album|red carpet|recipe|horoscope|lottery)\b")


# Webs que inundan Google News con traducciones automáticas sin interés para un inversor de aquí
FUENTES_EXCLUIDAS = ("vietnam.vn", "شبكة")


def _es_fuente_financiera(fuente: str) -> int:
    """2 = medio especializado · 1 = generalista (su sección de economía cuenta, pero menos) · 0 = otro."""
    f = _normalizar(fuente)
    if any(x == f or x in f for x in _FUENTES_GENERALISTAS):
        return 1
    return 2 if any(x in f for x in FUENTES_FINANCIERAS) else 0


def relevancia(titulo: str, fuente: str = "") -> int:
    """Cuánto «huele» a economía y mercados un titular. Negativo = ruido (deporte, espectáculos…)."""
    t = _normalizar(titulo)
    puntos = min(len(set(_RE_FINANZAS.findall(t))), 3)
    tipo = _es_fuente_financiera(fuente)
    if tipo == 2:
        puntos += 2
    if _RE_RUIDO.search(t):
        puntos -= 4
    return puntos


def es_financiera(titulo: str, fuente: str = "", estricto: bool = True) -> bool:
    """Estricto (materias primas, temas): tiene que hablar de mercados. Permisivo (empresas): basta con que no sea ruido."""
    r = relevancia(titulo, fuente)
    return r >= 1 if estricto else r >= 0


def consulta_para(texto: str, idioma: str = "es") -> tuple[str, bool]:
    """(consulta que se envía a Google News, ¿aplicar el filtro estricto?)."""
    clave = re.sub(r"\s+", " ", _normalizar(texto)).strip()
    clave = re.sub(r"^(precio|noticias|cotizacion) (del?|de la|de los|de las) ", "", clave)
    if clave in CONSULTAS_ACTIVO:
        return CONSULTAS_ACTIVO[clave][0 if idioma == "es" else 1], True
    return texto, False


def _fecha(texto: str):
    try:
        return email.utils.parsedate_to_datetime(texto).astimezone().replace(tzinfo=None)
    except Exception:
        return None


def _descargar(consulta: str, idioma: str, pais: str, dias: int) -> list[dict]:
    r = requests.get(
        "https://news.google.com/rss/search",
        params={"q": f"{consulta} when:{dias}d", "hl": idioma, "gl": pais, "ceid": f"{pais}:{idioma}"},
        headers=UA_WEB,
        timeout=15,
    )
    r.raise_for_status()
    items = []
    for it in ET.fromstring(r.content).iter("item"):
        titulo = (it.findtext("title") or "").strip()
        fuente = (it.findtext("source") or "").strip()
        if fuente and titulo.endswith(" - " + fuente):
            titulo = titulo[: -len(fuente) - 3]
        if titulo:
            items.append({"titulo": titulo, "fuente": fuente, "fecha": _fecha(it.findtext("pubDate") or ""),
                          "enlace": (it.findtext("link") or "").strip()})
    return items


@con_cache(15 * 60)
def buscar(consulta: str, idioma: str = "es", pais: str = "ES", dias: int = 7, maximo: int = 20,
           modo: str = "auto") -> list[dict]:
    """Titulares recientes de economía y mercados sobre `consulta`.

    modo: «auto» (estricto si es una materia prima o tema ambiguo; permisivo si es una empresa),
    «activo» (siempre estricto), «empresa» (permisivo) o «todo» (sin filtrar, como antes).
    """
    consulta_real, es_activo = consulta_para(consulta, idioma)
    estricto = modo == "activo" or (modo == "auto" and es_activo)
    crudos = _descargar(consulta_real, idioma, pais, dias)
    if modo == "empresa" and len(consulta.split()) <= 3:
        # Segunda búsqueda acotada a bolsa: sube arriba lo financiero de empresas con nombre «de la calle»
        extra = "acciones OR bolsa OR resultados OR beneficio OR dividendo" if idioma == "es" else \
            "stock OR shares OR earnings OR revenue OR analysts"
        try:
            crudos += _descargar(f'"{consulta}" ({extra})', idioma, pais, dias)
        except Exception:  # noqa: BLE001 - la primera búsqueda ya basta
            pass
    vistos, items = set(), []
    for it in crudos:
        clave = _normalizar(it["titulo"])
        if clave in vistos:
            continue
        vistos.add(clave)
        rel = relevancia(it["titulo"], it["fuente"])
        if modo != "todo":
            if rel < (1 if estricto else 0) or any(x in it["fuente"].lower() for x in FUENTES_EXCLUIDAS):
                continue
        s = sentimiento(it["titulo"])
        items.append({**it, "sentimiento": s, "marca": etiqueta(s), "relevancia": rel})
    if modo != "todo" and not estricto:
        # Empresas: los titulares claramente financieros van siempre; los neutros solo si faltan (evita «Santander ciudad»)
        fuertes = [i for i in items if i["relevancia"] >= 1]
        if len(fuertes) >= 8:
            items = fuertes
    items.sort(key=lambda x: x["fecha"] or datetime.min, reverse=True)
    return items[:maximo]


def resumen(items: list[dict]) -> dict:
    if not items:
        return {"n": 0, "media": 0.0, "positivas": 0, "negativas": 0}
    return {
        "n": len(items),
        "media": sum(i["sentimiento"] for i in items) / len(items),
        "positivas": sum(1 for i in items if i["sentimiento"] >= 0.25),
        "negativas": sum(1 for i in items if i["sentimiento"] <= -0.25),
    }
