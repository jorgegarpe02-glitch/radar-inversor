"""Lo que pasa hoy: estado de las bolsas, último precio y su retraso, mayores movimientos, agenda de resultados
y dividendos, compras y ventas de directivos, comunicados oficiales (SEC) y operaciones corporativas en las noticias."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from . import noticias
from .cache import con_cache
from .config import sec_ua

MADRID = ZoneInfo("Europe/Madrid")

# ----------------------------------------------------------------------------- horarios de bolsa
BOLSAS = {  # nombre: (zona horaria, apertura, cierre, sufijos de Yahoo)
    "Bolsa de Madrid": ("Europe/Madrid", dtime(9, 0), dtime(17, 30), (".MC",)),
    "Fráncfort (Xetra)": ("Europe/Berlin", dtime(9, 0), dtime(17, 30), (".DE",)),
    "París / Ámsterdam": ("Europe/Paris", dtime(9, 0), dtime(17, 30), (".PA", ".AS", ".BR", ".LS", ".MI")),
    "Londres": ("Europe/London", dtime(8, 0), dtime(16, 30), (".L",)),
    "Nueva York": ("America/New_York", dtime(9, 30), dtime(16, 0), ("",)),
    "Tokio": ("Asia/Tokyo", dtime(9, 0), dtime(15, 30), (".T",)),
    "Hong Kong": ("Asia/Hong_Kong", dtime(9, 30), dtime(16, 0), (".HK",)),
}


def estado_bolsas(ahora: datetime | None = None) -> pd.DataFrame:
    """Abierta/cerrada y horario en hora de Madrid. No tiene en cuenta festivos."""
    ahora = ahora or datetime.now(timezone.utc)
    filas = []
    for nombre, (zona, abre, cierra, _) in BOLSAS.items():
        local = ahora.astimezone(ZoneInfo(zona))
        laborable = local.weekday() < 5
        abierta = laborable and abre <= local.time() < cierra
        hoy = local.date()
        a = datetime.combine(hoy, abre, ZoneInfo(zona)).astimezone(MADRID)
        c = datetime.combine(hoy, cierra, ZoneInfo(zona)).astimezone(MADRID)
        filas.append({"Bolsa": nombre, "Estado": "🟢 Abierta" if abierta else "⚪ Cerrada",
                      "Horario (hora de Madrid)": f"{a:%H:%M}–{c:%H:%M}", "abierta": abierta})
    return pd.DataFrame(filas)


def bolsa_de(ticker: str) -> str:
    t = ticker.upper()
    for nombre, (*_, sufijos) in BOLSAS.items():
        for s in sufijos:
            if s and t.endswith(s):
                return nombre
    return "Nueva York" if "." not in t and not t.startswith("^") and "=" not in t else ""


# ----------------------------------------------------------------------------- precios del día
@con_cache(60)
def ultimo_precio(ticker: str) -> dict:
    """Último precio disponible (Yahoo), su hora en Madrid, minutos de retraso y variación del día."""
    tk = yf.Ticker(ticker)
    h = tk.history(period="1d", interval="1m")
    if h.empty:
        h = tk.history(period="5d", interval="5m")
    if h.empty:
        raise ValueError(f"Sin precio para {ticker}")
    ultimo = h.index[-1]
    if ultimo.tzinfo is None:
        ultimo = ultimo.tz_localize("UTC")
    dia = h[h.index.date == h.index[-1].date()]
    previo = None
    try:
        previo = float(tk.fast_info["previous_close"])
    except Exception:  # noqa: BLE001
        d = tk.history(period="5d", interval="1d")
        if len(d) > 1:
            previo = float(d["Close"].iloc[-2])
    precio = float(h["Close"].iloc[-1])
    return {
        "precio": precio, "apertura": float(dia["Open"].iloc[0]), "maximo": float(dia["High"].max()),
        "minimo": float(dia["Low"].min()), "cierre_anterior": previo,
        "var_dia": (precio / previo - 1) if previo else np.nan,
        "hora": ultimo.astimezone(MADRID), "retraso_min": (datetime.now(timezone.utc) - ultimo.astimezone(timezone.utc)).total_seconds() / 60,
    }


def texto_frescura(info: dict, ticker: str) -> str:
    bolsa = bolsa_de(ticker)
    abierta = False
    if bolsa:
        est = estado_bolsas()
        abierta = bool(est.loc[est["Bolsa"] == bolsa, "abierta"].iloc[0])
    hora = info["hora"]
    if abierta:
        return f"Precio de las {hora:%H:%M} (hace {info['retraso_min']:.0f} min) · {bolsa} abierta"
    return f"Último precio: {hora:%d/%m %H:%M} · {bolsa or 'mercado'} cerrada (es el cierre de la última sesión)"


INDICES_HOY = {"IBEX 35": "^IBEX", "Euro Stoxx 50": "^STOXX50E", "DAX": "^GDAXI", "FTSE 100": "^FTSE",
               "S&P 500": "^GSPC", "Nasdaq 100": "^NDX", "Nikkei 225": "^N225", "Brent": "BZ=F", "Oro": "GC=F",
               "EUR/USD": "EURUSD=X", "Bitcoin": "BTC-USD"}


def hoy_en_mercado() -> pd.DataFrame:
    def uno(par):
        nombre, t = par
        try:
            i = ultimo_precio(t)
            return {"Activo": nombre, "Ticker": t, "Precio": i["precio"], "Hoy": i["var_dia"],
                    "Apertura vs cierre anterior": (i["apertura"] / i["cierre_anterior"] - 1) if i["cierre_anterior"] else np.nan,
                    "Hora del dato": i["hora"].strftime("%d/%m %H:%M")}
        except Exception:  # noqa: BLE001
            return None
    with ThreadPoolExecutor(max_workers=6) as ex:
        filas = [f for f in ex.map(uno, INDICES_HOY.items()) if f]
    return pd.DataFrame(filas)


@con_cache(5 * 60)
def movimientos(tickers: tuple) -> pd.DataFrame:
    """Variación de hoy (último precio frente al cierre anterior) de una lista de valores."""
    d = yf.download(list(tickers), period="5d", interval="1d", auto_adjust=False, progress=False, threads=True,
                    group_by="column")
    if d is None or d.empty:
        return pd.DataFrame()
    c, o = d["Close"], d["Open"]
    if isinstance(c, pd.Series):
        c, o = c.to_frame(tickers[0]), o.to_frame(tickers[0])
    filas = []
    for t in c.columns:
        x = c[t].dropna()
        if len(x) < 2:
            continue
        filas.append({"Ticker": t, "Precio": float(x.iloc[-1]), "Hoy": float(x.iloc[-1] / x.iloc[-2] - 1),
                      "Apertura": float(o[t].dropna().iloc[-1]) if o[t].notna().any() else np.nan,
                      "Fecha": x.index[-1].strftime("%d/%m")})
    return pd.DataFrame(filas).sort_values("Hoy", ascending=False).reset_index(drop=True)


# ----------------------------------------------------------------------------- agenda
@con_cache(12 * 3600)
def _calendario(ticker: str) -> dict:
    return yf.Ticker(ticker).calendar or {}


def agenda(tickers: list[str], dias: int = 90) -> pd.DataFrame:
    """Próximos resultados, fechas ex-dividendo y pagos de dividendo."""
    hoy = date.today()

    def uno(t):
        try:
            cal = _calendario(t)
        except Exception:  # noqa: BLE001
            return []
        filas = []
        fechas_res = cal.get("Earnings Date") or []
        for f in (fechas_res if isinstance(fechas_res, list) else [fechas_res])[:1]:
            filas.append({"Ticker": t, "Evento": "📊 Resultados", "Fecha": f,
                          "Detalle": (f"BPA esperado {cal['Earnings Average']:.2f}" if cal.get("Earnings Average") else "")})
        if cal.get("Ex-Dividend Date"):
            filas.append({"Ticker": t, "Evento": "✂️ Ex-dividendo", "Fecha": cal["Ex-Dividend Date"],
                          "Detalle": "Hay que tener la acción el día anterior para cobrarlo"})
        if cal.get("Dividend Date"):
            filas.append({"Ticker": t, "Evento": "💶 Pago de dividendo", "Fecha": cal["Dividend Date"], "Detalle": ""})
        return filas

    with ThreadPoolExecutor(max_workers=6) as ex:
        filas = [f for lista in ex.map(uno, list(dict.fromkeys(tickers))) for f in lista]
    df = pd.DataFrame(filas, columns=["Ticker", "Evento", "Fecha", "Detalle"])
    if df.empty:
        return df
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.date
    df = df.dropna(subset=["Fecha"])
    df["Faltan (días)"] = df["Fecha"].map(lambda f: (f - hoy).days)
    df = df[(df["Faltan (días)"] >= -1) & (df["Faltan (días)"] <= dias)]
    return df.sort_values("Fecha").reset_index(drop=True)


# ----------------------------------------------------------------------------- directivos (insiders)
def _tipo_operacion(texto: str) -> str:
    t = (texto or "").lower()
    if "purchase" in t or "buy" in t:
        return "🟢 Compra"
    if "sale" in t or "sell" in t:
        return "🔴 Venta"
    if "gift" in t:
        return "🎁 Donación"
    if "option" in t or "exercise" in t or "conversion" in t:
        return "Ejercicio de opciones"
    if "award" in t or "grant" in t:
        return "Concesión de acciones"
    return "Otra"


@con_cache(12 * 3600)
def directivos(ticker: str) -> tuple[pd.DataFrame, dict]:
    """Operaciones de directivos y consejeros con acciones de su empresa (Yahoo; sobre todo empresas de EE. UU.)."""
    tk = yf.Ticker(ticker)
    df = tk.insider_transactions
    if df is None or df.empty:
        return pd.DataFrame(), {}
    out = pd.DataFrame({
        "Fecha": pd.to_datetime(df.get("Start Date"), errors="coerce").dt.date,
        "Cargo": df.get("Position", "").fillna("").replace("", "—"),
        "Operación": df.get("Text", "").fillna("").map(_tipo_operacion),
        "Acciones": pd.to_numeric(df.get("Shares"), errors="coerce"),
        "Importe": pd.to_numeric(df.get("Value"), errors="coerce"),
        "Detalle": df.get("Text", "").fillna(""),
    }).sort_values("Fecha", ascending=False).reset_index(drop=True)
    resumen = {}
    ip = tk.insider_purchases
    if ip is not None and not ip.empty:
        col = ip.columns[0]
        tabla = ip.set_index(col)
        def valor(fila, c):
            try:
                return float(tabla.loc[fila, c])
            except Exception:  # noqa: BLE001
                return float("nan")
        resumen = {"compras_acc": valor("Purchases", "Shares"), "compras_n": valor("Purchases", "Trans"),
                   "ventas_acc": valor("Sales", "Shares"), "ventas_n": valor("Sales", "Trans"),
                   "neto_acc": valor("Net Shares Purchased (Sold)", "Shares")}
    seis_meses = out[out["Fecha"] >= (date.today() - timedelta(days=182))]
    resumen["compras_mercado_6m"] = int((seis_meses["Operación"] == "🟢 Compra").sum())
    resumen["ventas_mercado_6m"] = int((seis_meses["Operación"] == "🔴 Venta").sum())
    return out, resumen


# ----------------------------------------------------------------------------- comunicados oficiales (SEC)
FORMULARIOS = {
    "8-K": "Hecho relevante", "6-K": "Hecho relevante (empresa extranjera)", "10-Q": "Resultados trimestrales",
    "10-K": "Informe anual", "20-F": "Informe anual (empresa extranjera)", "4": "Compra/venta de un directivo",
    "144": "Aviso de venta de acciones de un directivo", "SC 13D": "Alguien supera el 5 % con intención de influir",
    "SC 13G": "Alguien supera el 5 % (inversor pasivo)", "SCHEDULE 13D": "Alguien supera el 5 % con intención de influir",
    "SCHEDULE 13G": "Alguien supera el 5 % (inversor pasivo)", "SC TO-T": "OPA lanzada por otra empresa",
    "SC TO-I": "La empresa recompra sus acciones (OPA propia)", "SC 14D9": "Respuesta de la empresa a una OPA",
    "S-4": "Fusión o adquisición pagada con acciones", "425": "Comunicación sobre una fusión",
    "DEFM14A": "Votación de una fusión", "DEF 14A": "Convocatoria de junta", "S-1": "Salida a bolsa / emisión",
    "S-3": "Emisión de acciones o deuda", "424B2": "Emisión de deuda o productos", "SD": "Minerales de conflicto",
}
ITEMS_8K = {"1.01": "acuerdo importante", "1.02": "fin de un acuerdo", "2.01": "compra o venta de activos completada",
            "2.02": "resultados", "2.03": "nueva deuda", "2.05": "reestructuración/despidos", "3.01": "aviso de exclusión de bolsa",
            "4.01": "cambio de auditor", "5.02": "cambios en directivos o consejo", "5.07": "votaciones en junta",
            "7.01": "comunicación al mercado", "8.01": "otros hechos relevantes", "9.01": "estados financieros/anexos"}


@con_cache(30 * 60)
def comunicados_sec(cik: int, maximo: int = 30) -> pd.DataFrame:
    ua = sec_ua()
    if "@" not in ua:
        raise ValueError("La SEC exige identificarse con tu nombre y correo (se guarda solo en tu ordenador).")
    r = requests.get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json",
                     headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}, timeout=30)
    r.raise_for_status()
    rec = r.json()["filings"]["recent"]
    filas = []
    for i in range(min(maximo, len(rec["form"]))):
        forma = rec["form"][i]
        base = forma.replace("/A", "")
        items = rec.get("items", [""] * len(rec["form"]))[i] or ""
        detalle = ", ".join(ITEMS_8K.get(x.strip(), x.strip()) for x in items.split(",") if x.strip()) if base in ("8-K",) else ""
        acc = rec["accessionNumber"][i].replace("-", "")
        momento = pd.to_datetime(rec["acceptanceDateTime"][i], utc=True).tz_convert(MADRID)
        filas.append({"Fecha (Madrid)": momento.strftime("%d/%m/%Y %H:%M"), "Tipo": forma,
                      "Qué es": FORMULARIOS.get(base, base) + (" (corrección)" if forma.endswith("/A") else ""),
                      "Detalle": detalle,
                      "Documento": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{rec['primaryDocument'][i]}"})
    return pd.DataFrame(filas)


# ----------------------------------------------------------------------------- operaciones corporativas en noticias
_CLAVES_OP = {
    "OPA": r"\b(opa|opas|tender offer|takeover bid|oferta p[uú]blica)\b",
    "Fusión": r"\b(fusi[oó]n|fusionar|merger|merge[sd]?)\b",
    "Compra / adquisición": r"\b(adquiri\w*|adquisici[oó]n\w*|compra de|compra el|compra la|acquir\w*|acquisition\w*|buyout|to buy|buys|purchase of)\b",
    "Participación": r"\b(participaci[oó]n|stake|entra en el capital|toma el \d+|hasta el \d+ ?%)\b",
    "Venta / desinversión": r"\b(vende|venta de|desinver\w*|divest\w*|sells|spin[- ]?off|escisi[oó]n)\b",
}


def clasificar_operacion(titulo: str) -> str | None:
    for tipo, patron in _CLAVES_OP.items():
        if re.search(patron, titulo, flags=re.I):
            return tipo
    return None


def operaciones_corporativas(nombre: str | None = None, idioma: str = "es", pais: str = "ES", dias: int = 7) -> list[dict]:
    """Titulares de OPAs, fusiones, compras, participaciones y ventas. Sin nombre: las del mercado en general."""
    if nombre:
        if idioma == "es":
            q = f'"{nombre}" (OPA OR adquisición OR fusión OR compra OR participación OR venta)'
        else:
            q = f'"{nombre}" (acquisition OR merger OR takeover OR stake OR "tender offer" OR divest)'
    else:
        q = ("OPA OR adquisición OR fusión empresa" if idioma == "es"
             else 'acquisition OR merger OR takeover OR "tender offer"')
    items = noticias.buscar(q, idioma, pais, dias, 40)
    salida = []
    for i in items:
        tipo = clasificar_operacion(i["titulo"])
        if tipo:
            salida.append({**i, "operacion": tipo})
    return salida
