"""Criptomonedas: precios (CoinGecko y Yahoo Finance), ánimo del mercado (alternative.me) y un análisis por reglas.

Una criptomoneda no tiene ventas ni beneficios, así que aquí no hay «valor razonable» que calcular. El análisis responde
a otras preguntas: ¿qué es?, ¿es de las sólidas o de las frágiles?, ¿en qué momento está?, ¿cuánto puede caer?, ¿qué peso
tendría sentido? Todo sale de reglas fijas sobre datos públicos: sin IA y sin coste.
"""
from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd
import requests

from . import datos
from .cache import con_cache

CG = "https://api.coingecko.com/api/v3"
_UA = {"User-Agent": "Mozilla/5.0 (RadarInversor)", "Accept": "application/json"}
FUENTE = "CoinGecko (precios, capitalización y oferta), Yahoo Finance (histórico largo) y alternative.me (índice de miedo y codicia)"

# ----------------------------------------------------------------------------- qué es cada una
TIPOS = {
    "reserva": ("Reserva de valor", "Dinero digital escaso: nadie puede fabricar más de la cuenta. Se compra como «oro digital»."),
    "plataforma": ("Plataforma", "Una red sobre la que otros construyen aplicaciones. La moneda se usa para pagar por usarla."),
    "pagos": ("Pagos", "Pensada para mover dinero rápido y barato."),
    "bolsa": ("Moneda de exchange", "La emite una empresa de compraventa de criptomonedas; depende de que a esa empresa le vaya bien."),
    "defi": ("Finanzas", "Da derecho a participar en una aplicación financiera (préstamos, intercambios, datos…)."),
    "privacidad": ("Privacidad", "Pagos que no se pueden rastrear. Los reguladores las miran con lupa y algunas plataformas las retiran."),
    "meme": ("Moneda de broma", "No tiene ninguna utilidad: su precio depende solo de la moda y de las redes sociales."),
    "ia": ("Inteligencia artificial", "Red que paga por aportar capacidad de cálculo o modelos de IA."),
    "estable": ("Moneda estable", "Está hecha para valer siempre lo mismo (normalmente 1 dólar). No sube: sirve para aparcar dinero, no para invertir."),
    "oro": ("Oro en formato digital", "Cada unidad representa oro físico guardado. Se mueve como el oro, no como una criptomoneda."),
    "copia": ("Copia de otra moneda", "Representa a otra criptomoneda (envuelta o en depósito). Se mueve igual que la original, con un riesgo añadido."),
    "otra": ("Otra", "Proyecto sin una categoría clara en mi lista: trátalo como una apuesta."),
}
TIPO_DE = {
    "bitcoin": "reserva",
    **{k: "plataforma" for k in ("ethereum", "solana", "binancecoin", "cardano", "tron", "avalanche-2", "the-open-network", "sui", "polkadot",
                                 "near", "hedera-hashgraph", "internet-computer", "aptos", "cosmos", "algorand", "ethereum-classic",
                                 "arbitrum", "optimism", "mantle", "polygon-ecosystem-token", "matic-network", "kaspa", "sei-network",
                                 "celestia", "injective-protocol", "stacks", "vechain", "filecoin", "canton-network", "hyperliquid")},
    **{k: "pagos" for k in ("ripple", "stellar", "litecoin", "bitcoin-cash", "dash", "bitcoin-cash-sv")},
    **{k: "bolsa" for k in ("leo-token", "okb", "crypto-com-chain", "whitebit", "kucoin-shares", "bitget-token", "gatechain-token", "mx-token")},
    **{k: "defi" for k in ("chainlink", "uniswap", "aave", "maker", "ondo-finance", "ethena", "lido-dao", "jupiter-exchange-solana",
                           "curve-dao-token", "pancakeswap-token", "quant-network", "the-graph", "pendle", "sky", "raydium", "aster-2")},
    **{k: "privacidad" for k in ("monero", "zcash")},
    **{k: "meme" for k in ("dogecoin", "shiba-inu", "pepe", "bonk", "dogwifcoin", "floki", "official-trump", "pump-fun", "memecore",
                           "fartcoin", "pudgy-penguins", "spx6900", "brett", "world-liberty-financial")},
    **{k: "ia" for k in ("bittensor", "render-token", "fetch-ai", "artificial-superintelligence-alliance", "worldcoin-wld", "akash-network")},
    **{k: "oro" for k in ("tether-gold", "pax-gold")},
    **{k: "defi" for k in ("morpho", "ether-fi", "layerzero", "lighter", "just")},
    **{k: "bolsa" for k in ("nexo", "htx-dao")},
    "blockstack": "plataforma", "figure-heloc": "estable",
}
_PREFIJOS_COPIA = ("wrapped-", "staked-", "coinbase-wrapped", "binance-bridged", "bridged-", "lombard-staked", "renzo-", "kelp-", "rocket-pool-eth",
                   "weth", "wbtc", "mantle-staked", "binance-staked", "jito-staked", "marinade-staked", "liquid-staked", "ether-fi-staked",
                   "binance-peg", "solv-", "jupiter-staked", "cbbtc", "tbtc")
HALVINGS = [date(2012, 11, 28), date(2016, 7, 9), date(2020, 5, 11), date(2024, 4, 20)]


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and np.isnan(x))


def _get(url: str, params: dict | None = None):
    r = requests.get(url, params=params, headers=_UA, timeout=15)
    r.raise_for_status()
    return r.json()


def tipo_de(fila: dict) -> str:
    """Categoría de una moneda. Las estables se detectan también por cómo se comportan (no se mueven)."""
    cid = str(fila.get("id") or "")
    if cid in TIPO_DE:
        return TIPO_DE[cid]
    if any(cid.startswith(p) or cid == p for p in _PREFIJOS_COPIA):
        return "copia"
    c7, c30, c1a = (fila.get(k) for k in ("cambio_7d", "cambio_30d", "cambio_1a"))
    quieta = all(_ok(c) for c in (c7, c30)) and abs(c7) < 0.012 and abs(c30) < 0.025 and (not _ok(c1a) or abs(c1a) < 0.09)
    if quieta or "usd" in cid.split("-") or cid.startswith(("usd", "eur")) or cid.endswith(("-usd", "usd")):
        return "estable"
    return "otra"


# ----------------------------------------------------------------------------- datos
@con_cache(5 * 60)
def mercado(n: int = 100) -> pd.DataFrame:
    """Las `n` mayores criptomonedas con precio en dólares, cambios y oferta. Vacío si CoinGecko no responde."""
    try:
        d = _get(f"{CG}/coins/markets", {"vs_currency": "usd", "order": "market_cap_desc", "per_page": min(n, 250), "page": 1,
                                         "price_change_percentage": "24h,7d,30d,1y"})
    except Exception:  # noqa: BLE001
        return pd.DataFrame()
    filas = []
    for x in d:
        def pct(k):
            v = x.get(k)
            return v / 100 if isinstance(v, (int, float)) else None
        fila = {"id": x.get("id"), "simbolo": str(x.get("symbol") or "").upper(), "nombre": x.get("name"), "puesto": x.get("market_cap_rank"),
                "precio": x.get("current_price"), "cap": x.get("market_cap"), "cap_diluida": x.get("fully_diluted_valuation"),
                "volumen": x.get("total_volume"), "circulante": x.get("circulating_supply"), "oferta_total": x.get("total_supply"),
                "oferta_max": x.get("max_supply"), "maximo": x.get("ath"), "desde_maximo": pct("ath_change_percentage"),
                "fecha_maximo": str(x.get("ath_date") or "")[:10], "fecha_minimo": str(x.get("atl_date") or "")[:10],
                "cambio_24h": pct("price_change_percentage_24h_in_currency"), "cambio_7d": pct("price_change_percentage_7d_in_currency"),
                "cambio_30d": pct("price_change_percentage_30d_in_currency"), "cambio_1a": pct("price_change_percentage_1y_in_currency")}
        fila["tipo"] = tipo_de(fila)
        filas.append(fila)
    return pd.DataFrame(filas)


@con_cache(10 * 60)
def panorama() -> dict:
    """Tamaño total del mercado, peso de bitcoin e índice de miedo y codicia (0 = pánico, 100 = euforia)."""
    r: dict = {}
    try:
        g = _get(f"{CG}/global")["data"]
        r.update(cap_total=g["total_market_cap"].get("usd"), peso_btc=g["market_cap_percentage"].get("btc", 0) / 100,
                 peso_eth=g["market_cap_percentage"].get("eth", 0) / 100, cambio_24h=g.get("market_cap_change_percentage_24h_usd", 0) / 100)
    except Exception:  # noqa: BLE001
        pass
    try:
        f = _get("https://api.alternative.me/fng/", {"limit": 31})["data"]
        r.update(miedo=int(f[0]["value"]), miedo_hace_7=int(f[min(7, len(f) - 1)]["value"]), miedo_hace_30=int(f[-1]["value"]))
    except Exception:  # noqa: BLE001
        pass
    return r


def nombre_miedo(v: int | None) -> str:
    if v is None:
        return "sin dato"
    return ("pánico" if v < 25 else "miedo" if v < 45 else "neutral" if v <= 55 else "codicia" if v <= 75 else "euforia")


@con_cache(30 * 60)
def _historial_cg(cid: str) -> pd.Series:
    d = _get(f"{CG}/coins/{cid}/market_chart", {"vs_currency": "usd", "days": 365, "interval": "daily"})
    s = pd.Series({pd.Timestamp(t, unit="ms").normalize(): p for t, p in d.get("prices", [])}, dtype=float)
    return s[~s.index.duplicated(keep="last")]


def historial(cid: str, simbolo: str, precio: float | None) -> pd.Series:
    """Cierres diarios en dólares. Yahoo da muchos años, pero comparte siglas entre monedas distintas: solo se acepta si su
    último precio coincide con el de CoinGecko. Si no, se usa el último año de CoinGecko."""
    try:
        h = datos.historial(f"{simbolo}-USD", "max")
        if h is not None and len(h) > 200 and _ok(precio) and precio:
            s = h["Close"].dropna()
            if abs(float(s.iloc[-1]) / precio - 1) < 0.08:
                return s
    except Exception:  # noqa: BLE001
        pass
    try:
        return _historial_cg(cid)
    except Exception:  # noqa: BLE001
        return pd.Series(dtype=float)


# ----------------------------------------------------------------------------- cálculos
def _rsi(s: pd.Series, n: int = 14) -> float | None:
    if len(s) < n + 5:
        return None
    d = s.diff().dropna()
    sube = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    baja = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    return 100.0 if baja == 0 else float(100 - 100 / (1 + sube / baja))


def medidas(s: pd.Series, btc: pd.Series | None = None) -> dict:
    """Tendencia, fuerza, volatilidad y caídas a partir de los cierres diarios."""
    r: dict = {"dias": len(s)}
    if len(s) < 30:
        return r
    p = float(s.iloc[-1])
    r["precio"] = p
    for n in (50, 200):
        if len(s) >= n:
            r[f"mm{n}"] = float(s.tail(n).mean())
    if len(s) >= 1400:
        r["mm200s"] = float(s.tail(1400).mean())  # media de 200 semanas: el «suelo» histórico de los grandes ciclos
    r["rsi"] = _rsi(s)
    ren = np.log(s / s.shift(1)).dropna()
    r["vol"] = float(ren.tail(365).std() * np.sqrt(365))
    r["peor_dia"] = float((s / s.shift(1) - 1).min())
    caida = s / s.cummax() - 1
    r["caida_max"] = float(caida.min())
    r["caida_actual"] = float(caida.iloc[-1])
    r["anios"] = (s.index[-1] - s.index[0]).days / 365.25
    # cuántas veces ha caído más de la mitad desde un máximo y se ha recuperado
    hundida, veces = False, 0
    for v in caida:
        if not hundida and v <= -0.5:
            hundida, veces = True, veces + 1
        elif hundida and v > -0.1:
            hundida = False
    r["hundimientos"] = veces
    if len(s) > 95:
        r["cambio_90d"] = float(p / s.iloc[-91] - 1)
        if btc is not None and len(btc) > 95:
            r["vs_btc_90d"] = r["cambio_90d"] - float(btc.iloc[-1] / btc.iloc[-91] - 1)
    if len(s) >= 365 * 3:
        anual = (s / s.shift(365) - 1).dropna()
        r["anios_en_negativo"] = float((anual < 0).mean())
    return r


def ciclo_bitcoin(hoy: date | None = None) -> dict:
    """En qué punto está el ciclo de cuatro años de bitcoin (cada «halving» reduce a la mitad los bitcoins nuevos)."""
    hoy = hoy or date.today()
    pasados = [h for h in HALVINGS if h <= hoy]
    ultimo = pasados[-1]
    meses = (hoy - ultimo).days / 30.44
    proximo = date(ultimo.year + 4, ultimo.month, ultimo.day)
    if meses < 12:
        fase, texto, tono = "inicio", "primer año tras el recorte: históricamente, la parte alcista del ciclo", "verde"
    elif meses < 19:
        fase, texto, tono = "techo", "entre 12 y 18 meses tras el recorte: la zona donde se formaron los máximos de los tres ciclos anteriores", "rojo"
    elif meses < 31:
        fase, texto, tono = "resaca", "segundo-tercer año tras el recorte: en los ciclos anteriores fue el tramo de caídas fuertes", "amarillo"
    else:
        fase, texto, tono = "suelo", ("tercer-cuarto año tras el recorte: en los ciclos anteriores aquí se formaron los suelos, "
                                      "antes del siguiente recorte"), "verde"
    return {"ultimo": ultimo, "proximo": proximo, "meses": meses, "fase": fase, "texto": texto, "tono": tono}


def solidez(f: dict, med: dict) -> dict:
    """0-10: cuánto aguanta. No dice si va a subir; dice si es de las que sobreviven."""
    tipo, puntos, notas = f.get("tipo", "otra"), 0.0, []
    puesto = f.get("puesto") or 999
    p = 3 if puesto <= 2 else 2.5 if puesto <= 10 else 1.5 if puesto <= 30 else 0.8 if puesto <= 100 else 0
    puntos += p
    notas.append((f"Tamaño: puesto {puesto} del mundo", p, 3))
    anios = max(med.get("anios") or 0, _anios_desde(f.get("fecha_minimo")))
    p = 2 if anios >= 8 else 1.5 if anios >= 5 else 0.8 if anios >= 3 else 0
    puntos += p
    notas.append((f"Antigüedad: unos {anios:.0f} años cotizando" if anios >= 1 else "Antigüedad: menos de un año", p, 2))
    liq = (f["volumen"] / f["cap"]) if _ok(f.get("volumen")) and f.get("cap") else None
    p = 0 if liq is None else 1.5 if liq >= 0.015 else 0.8 if liq >= 0.004 else 0
    puntos += p
    notas.append(("Liquidez: " + ("sin dato" if liq is None else f"cada día cambia de manos el {liq * 100:.1f} % de su valor".replace(".", ",")), p, 1.5))
    circ, mx, tot = f.get("circulante"), f.get("oferta_max"), f.get("oferta_total")
    tope = mx or tot
    if mx and circ:
        emitido = circ / mx
        p = 2 if emitido >= 0.9 else 1.3 if emitido >= 0.7 else 0.6 if emitido >= 0.4 else 0
        txt = f"Oferta: tope fijo y ya circula el {emitido * 100:.0f} %"
    elif tope and circ:
        emitido = circ / tope
        p = 1 if emitido >= 0.9 else 0.5 if emitido >= 0.6 else 0
        txt = f"Oferta: sin tope máximo; circula el {emitido * 100:.0f} % de lo creado"
    else:
        emitido, p, txt = None, 0.3, "Oferta: sin tope y sin datos claros de cuánta falta por salir"
    puntos += p
    notas.append((txt, p, 2))
    p = {"reserva": 1.5, "plataforma": 1.0, "pagos": 0.8, "defi": 0.7, "bolsa": 0.5, "ia": 0.4, "privacidad": 0.3, "otra": 0.2, "meme": 0}.get(tipo, 0.2)
    puntos += p
    notas.append((f"Para qué sirve: {TIPOS[tipo][0].lower()}", p, 1.5))
    puntos = round(min(puntos, 10), 1)
    etiqueta = "Alta" if puntos >= 7.5 else "Media" if puntos >= 5 else "Baja" if puntos >= 3 else "Muy baja"
    return {"puntos": puntos, "etiqueta": etiqueta, "notas": notas, "emitido": emitido, "liquidez": liq, "anios": anios}


def _anios_desde(iso: str | None) -> float:
    try:
        return (date.today() - datetime.strptime(str(iso)[:10], "%Y-%m-%d").date()).days / 365.25
    except Exception:  # noqa: BLE001
        return 0.0


def plazos(f: dict, med: dict, sol: dict, pan: dict) -> list[dict]:
    """Veredicto por horizonte: días-semanas, meses y años."""
    filas = []
    # corto: impulso
    pts, por = 0, []
    rsi = med.get("rsi")
    if _ok(med.get("mm50")) and _ok(med.get("precio")):
        arriba = med["precio"] > med["mm50"]
        pts += 1 if arriba else -1
        por.append("por encima de su media de 50 días" if arriba else "por debajo de su media de 50 días")
    if _ok(f.get("cambio_7d")):
        pts += 1 if f["cambio_7d"] > 0.03 else -1 if f["cambio_7d"] < -0.03 else 0
        por.append(f"{f['cambio_7d'] * 100:+.0f} % en 7 días")
    if _ok(rsi):
        if rsi > 75:
            pts -= 1
            por.append(f"muy recalentada (RSI {rsi:.0f})")
        elif rsi < 28:
            por.append(f"muy castigada (RSI {rsi:.0f}): puede rebotar, pero la tendencia manda")
    filas.append(_fila("Corto plazo", "días o semanas", pts, por, 2))
    # medio: tendencia de fondo
    pts, por = 0, []
    if _ok(med.get("mm200")) and _ok(med.get("precio")):
        arriba = med["precio"] > med["mm200"]
        pts += 2 if arriba else -2
        por.append("tendencia de fondo alcista (sobre la media de 200 días)" if arriba else "tendencia de fondo bajista (bajo la media de 200 días)")
        if _ok(med.get("mm50")):
            pts += 1 if med["mm50"] > med["mm200"] else -1
    if _ok(med.get("vs_btc_90d")) and f.get("id") != "bitcoin":
        mejor = med["vs_btc_90d"] > 0
        pts += 1 if mejor else -1
        por.append(f"{'mejor' if mejor else 'peor'} que bitcoin en 3 meses ({med['vs_btc_90d'] * 100:+.0f} puntos)")
    filas.append(_fila("Medio plazo", "de 1 a 6 meses", pts, por, 3))
    # largo: solidez y punto del ciclo
    pts, por = 0, []
    pts += 2 if sol["puntos"] >= 7.5 else 1 if sol["puntos"] >= 5 else -1 if sol["puntos"] >= 3 else -3
    por.append(f"solidez {sol['etiqueta'].lower()} ({sol['puntos']}/10)".replace(".", ","))
    dm = f.get("desde_maximo")
    if _ok(dm) and sol["puntos"] >= 5:
        if dm <= -0.5:
            pts += 1
            por.append(f"un {abs(dm) * 100:.0f} % por debajo de su máximo: las compras hechas tan abajo han sido las buenas en las monedas que sobrevivieron")
        elif dm > -0.12:
            pts -= 1
            por.append("pegada a su máximo histórico: mal sitio para empezar de golpe")
    miedo = pan.get("miedo")
    if miedo is not None:
        if miedo < 25:
            pts += 1
            por.append("el mercado está en pánico, que es cuando se han hecho las mejores compras a largo plazo")
        elif miedo > 75:
            pts -= 1
            por.append("el mercado está eufórico, que es cuando más se ha perdido comprando")
    filas.append(_fila("Largo plazo", "más de 2 años", pts, por, 3))
    return filas


def _fila(plazo: str, cuanto: str, pts: int, por: list[str], umbral: int) -> dict:
    if pts >= umbral:
        color, ver = "verde", "A favor"
    elif pts <= -umbral:
        color, ver = "rojo", "En contra"
    elif pts > 0:
        color, ver = "amarillo", "Algo a favor"
    elif pts < 0:
        color, ver = "amarillo", "Algo en contra"
    else:
        color, ver = "amarillo", "Neutral"
    return {"plazo": plazo, "cuanto": cuanto, "color": color, "veredicto": ver, "porque": "; ".join(por) or "sin datos suficientes", "puntos": pts}


def rangos(f: dict, med: dict) -> dict | None:
    """Rango razonable a 12 meses según lo que se ha movido hasta ahora. NO es una predicción: no supone ni subida ni bajada."""
    vol, p = med.get("vol"), f.get("precio")
    if not (_ok(vol) and _ok(p)):
        return None
    v = min(vol, 1.6)
    peor = med.get("caida_max")
    return {"bajo": p * float(np.exp(-v)), "alto": p * float(np.exp(v)), "vol": vol,
            "desastre": p * (1 + peor) if _ok(peor) and med.get("anios", 0) >= 3 else None, "caida_max": peor}


def riesgos(f: dict, med: dict, sol: dict) -> list[tuple[str, str]]:
    """(gravedad, texto). Gravedad: alto / medio."""
    r, tipo = [], f.get("tipo", "otra")
    vol = med.get("vol")
    if _ok(vol):
        r.append(("alto" if vol > 0.8 else "medio", f"Se mueve muchísimo: una volatilidad anual del {vol * 100:.0f} % (una bolsa normal ronda el 15-20 %). "
                  f"Su peor día cayó un {abs(med.get('peor_dia', 0)) * 100:.0f} %."))
    if _ok(med.get("caida_max")) and med.get("anios", 0) >= 2:
        r.append(("alto" if med["caida_max"] < -0.7 else "medio", f"Ya ha llegado a caer un {abs(med['caida_max']) * 100:.0f} % desde un máximo"
                  + (f", y ha perdido más de la mitad {med['hundimientos']} veces" if med.get("hundimientos", 0) > 1 else "") + ". Puede volver a pasar."))
    if tipo == "meme":
        r.append(("alto", "No tiene utilidad ni ingresos: vale lo que la moda quiera. La mayoría de las monedas de broma acaban perdiendo casi todo."))
    if sol.get("emitido") is not None and sol["emitido"] < 0.7:
        r.append(("alto" if sol["emitido"] < 0.4 else "medio", f"Solo circula el {sol['emitido'] * 100:.0f} % de las monedas: el resto irá saliendo "
                  "al mercado (fundadores, inversores iniciales, recompensas) y eso presiona el precio a la baja."))
    if (f.get("puesto") or 999) > 30:
        r.append(("medio", "Es pequeña: pocas compras o ventas grandes mueven mucho el precio, y los proyectos pequeños desaparecen con frecuencia."))
    if sol.get("liquidez") is not None and sol["liquidez"] < 0.004:
        r.append(("medio", "Se negocia poco: puede costar vender una cantidad grande sin hundir el precio."))
    if sol.get("anios", 0) < 3:
        r.append(("medio", "Lleva poco tiempo: todavía no ha pasado por un mercado bajista completo."))
    if tipo == "bolsa":
        r.append(("medio", "Depende de una sola empresa. Si esa plataforma tiene problemas (como FTX en 2022), la moneda puede quedarse en nada."))
    if tipo == "privacidad":
        r.append(("medio", "Riesgo regulatorio: varias plataformas europeas han dejado de ofrecer monedas de privacidad."))
    if tipo == "copia":
        r.append(("medio", "Además del riesgo de la moneda original, depende de quien custodia o emite la copia."))
    r.append(("medio", "No hay red de seguridad: sin fondo de garantía, y si pierdes las claves o quiebra la plataforma donde la guardas, no se recupera."))
    return r


def recomendacion(f: dict, med: dict, sol: dict, pl: list[dict], pan: dict) -> dict:
    """Qué hacer, con qué peso máximo y de qué forma."""
    tipo, s = f.get("tipo", "otra"), sol["puntos"]
    if tipo == "estable":
        return {"etiqueta": "⚪ NO ES UNA INVERSIÓN", "color": "gris", "peso": None,
                "texto": "Es una moneda estable: está diseñada para no moverse. Sirve para tener el dinero aparcado dentro del mundo cripto, "
                         "pero no va a subir. Su único riesgo relevante es que deje de valer lo que promete (ha pasado: TerraUSD se hundió en 2022).",
                "como": ""}
    if tipo == "oro":
        return {"etiqueta": "⚪ ES ORO, NO CRIPTO", "color": "gris", "peso": None,
                "texto": "Sigue el precio del oro. Si quieres oro, mira su análisis en Mercados → Materias primas; esto solo añade el riesgo "
                         "de que el emisor no tenga el oro que dice.", "como": ""}
    if tipo == "copia":
        return {"etiqueta": "⚪ COPIA DE OTRA MONEDA", "color": "gris", "peso": None,
                "texto": "Se mueve igual que la moneda a la que representa. Analiza la original (bitcoin, ethereum…): la decisión es la misma.", "como": ""}
    largo, medio = pl[2], pl[1]
    peso = "5-10 %" if f.get("id") == "bitcoin" else "3-5 %" if s >= 7.5 else "1-2 %" if s >= 5 else "menos del 1 %"
    como = ("Mejor en compras pequeñas y periódicas (por ejemplo, la misma cantidad cada mes) que todo de golpe: con algo tan volátil, "
            "repartir las compras evita entrar justo en el peor momento.")
    if s < 3 or tipo == "meme" and s < 5:
        return {"etiqueta": "🔴 EVITAR", "color": "rojo", "peso": "nada, o dinero que des por perdido",
                "texto": "Demasiado frágil para considerarla una inversión: " + ("es una moneda de broma" if tipo == "meme" else "es pequeña, joven o con mucha oferta por salir")
                         + f" (solidez {str(s).replace('.', ',')}/10). Esto se parece más a una apuesta que a invertir.", "como": ""}
    if tipo == "meme":
        return {"etiqueta": "🟠 MUY ESPECULATIVA", "color": "amarillo", "peso": "menos del 1 %",
                "texto": "Es una moneda de broma grande y conocida, pero sigue sin tener utilidad: su precio depende de la moda. Puede dar "
                         "subidas enormes en fases de euforia y perder el 80-90 % después.",
                "como": "Si entras, que sea una cantidad que puedas perder entera."}
    if s >= 7.5 and largo["color"] != "rojo" and medio["color"] != "rojo":
        return {"etiqueta": "🟢 ACUMULAR POCO A POCO", "color": "verde", "peso": peso,
                "texto": f"De las más sólidas del mercado (solidez {str(s).replace('.', ',')}/10) y el momento no está en contra. "
                         "Aun así es un activo sin beneficios que lo respalden: su precio depende de que más gente quiera tenerla.", "como": como}
    if s >= 7.5:
        return {"etiqueta": "🟡 SÓLIDA, PERO EN MAL MOMENTO", "color": "amarillo", "peso": peso,
                "texto": f"Es de las sólidas (solidez {str(s).replace('.', ',')}/10), pero la tendencia de fondo es bajista. Para quien invierte a años, "
                         "estas fases son donde se compra barato; para quien necesita el dinero pronto, es mejor esperar a que deje de caer.", "como": como}
    if s >= 5:
        buena = medio["color"] == "verde" or (medio["puntos"] > 0 and largo["puntos"] > 0)
        return {"etiqueta": "🟡 SOLO COMO APUESTA PEQUEÑA", "color": "amarillo", "peso": peso,
                "texto": f"Proyecto establecido pero de segunda fila (solidez {str(s).replace('.', ',')}/10). "
                         + ("La tendencia acompaña, " if buena else "Ahora mismo la tendencia no acompaña, ")
                         + "y este tipo de monedas sube más que bitcoin en las buenas y cae bastante más en las malas.", "como": como}
    return {"etiqueta": "🟠 MUY ESPECULATIVA", "color": "amarillo", "peso": peso,
            "texto": f"Solidez baja ({str(s).replace('.', ',')}/10). Puede multiplicarse o desaparecer; históricamente, la mayoría de las monedas "
                     "de este tamaño no recuperan nunca sus máximos.", "como": "Si entras, que sea una cantidad que puedas perder entera."}


def resumen_llano(f: dict, med: dict, sol: dict, rec: dict, pan: dict, cic: dict) -> str:
    """Tres o cuatro frases sin jerga."""
    tipo = f.get("tipo", "otra")
    fr = [f"**{f['nombre']}** es {_articulo(tipo)} {TIPOS[tipo][0].lower()}. {TIPOS[tipo][1]}"]
    if tipo in ("estable", "oro", "copia"):
        return " ".join(fr + [rec["texto"]])
    dm = f.get("desde_maximo")
    if _ok(dm):
        fr.append(f"Hoy está un {abs(dm) * 100:.0f} % por debajo de su máximo histórico ({f.get('fecha_maximo', '')[:4]})." if dm < -0.03
                  else "Hoy está en máximos históricos.")
    if _ok(med.get("vol")):
        fr.append(f"En un año normal puede subir o bajar un {min(med['vol'], 1.6) * 100:.0f} % sin que haya pasado nada especial.")
    if pan.get("miedo") is not None:
        fr.append(f"El ánimo general del mercado cripto es de **{nombre_miedo(pan['miedo'])}** ({pan['miedo']}/100).")
    fr.append(f"Mi lectura: **{rec['etiqueta'].split(' ', 1)[1].lower()}**" + (f", con un peso máximo orientativo del {rec['peso']} de tus ahorros invertidos."
                                                                             if rec.get("peso") and "%" in rec["peso"] else "."))
    return " ".join(fr)


def _articulo(tipo: str) -> str:
    return {"reserva": "una", "plataforma": "una", "bolsa": "la", "privacidad": "una moneda de", "meme": "una", "ia": "una moneda de",
            "pagos": "una moneda de", "defi": "una moneda de", "otra": "una moneda de categoría"}.get(tipo, "una")


def completo(f: dict, s: pd.Series, btc: pd.Series | None, pan: dict) -> dict:
    """Todo el análisis de una moneda."""
    med = medidas(s, btc)
    sol = solidez(f, med)
    pl = plazos(f, med, sol, pan)
    rec = recomendacion(f, med, sol, pl, pan)
    cic = ciclo_bitcoin()
    return {"medidas": med, "solidez": sol, "plazos": pl, "rangos": rangos(f, med), "riesgos": riesgos(f, med, sol), "recomendacion": rec,
            "ciclo": cic, "resumen": resumen_llano(f, med, sol, rec, pan, cic)}


def lectura_mercado(pan: dict, cic: dict) -> str:
    """Una frase sobre cómo está el mercado cripto en conjunto."""
    partes = []
    if pan.get("miedo") is not None:
        m = pan["miedo"]
        partes.append(f"El ánimo es de **{nombre_miedo(m)}** ({m}/100; hace un mes {pan.get('miedo_hace_30', '—')}). "
                      + ("Históricamente, comprar las monedas sólidas con pánico ha salido bien a varios años vista, aunque puede seguir cayendo antes." if m < 25 else
                         "Hay cautela, sin llegar al pánico." if m < 45 else "Ni miedo ni euforia." if m <= 55 else
                         "Hay optimismo: conviene no perseguir subidas." if m <= 75 else
                         "Hay euforia: es cuando más gente entra y cuando históricamente peor ha salido comprar."))
    if pan.get("peso_btc"):
        b = pan["peso_btc"]
        partes.append(f"Bitcoin es el {b * 100:.0f} % de todo el mercado: "
                      + ("el dinero se refugia en bitcoin y huye de las monedas pequeñas." if b > 0.58 else
                         "reparto normal entre bitcoin y el resto." if b > 0.48 else "el dinero está yendo a monedas pequeñas, señal típica de fases de mucho apetito por el riesgo."))
    partes.append(f"Ciclo de bitcoin: han pasado {cic['meses']:.0f} meses desde el último recorte de emisión ({cic['ultimo'].strftime('%m/%Y')}); "
                  f"estamos en el {cic['texto']}. Ojo: solo hay tres ciclos anteriores, es una pauta y no una ley.")
    return " ".join(partes)
