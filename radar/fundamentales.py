"""Fundamentales de una empresa calculados a partir de sus cuentas (Yahoo Finance, gratis).

Yahoo publica las cuentas anuales (4-5 años) y trimestrales (5-7 trimestres). Aquí se calculan con ellas los ratios
que usa el análisis: PER, EV/EBITDA, P/FCF, ROE, ROIC, deuda, dividendo, crecimiento, márgenes, recompras, dilución
y el rango histórico de valoración de la propia empresa. Se calculan aquí (en vez de fiarse solo de la ficha de Yahoo)
porque así se sabe de dónde sale cada número y siguen saliendo aunque la ficha de Yahoo falle ese día.

Cada métrica lleva su fuente en `fuentes` para poder citarla.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import yfinance as yf

from .cache import con_cache

F_CUENTAS = "Cuentas publicadas (Yahoo Finance) · cálculo propio"
F_YAHOO = "Yahoo Finance"
F_ANALISTAS = "Consenso de analistas (Yahoo Finance)"


# ----------------------------------------------------------------------------- descarga
@con_cache(12 * 3600)
def estados(ticker: str) -> dict:
    """Cuentas anuales y trimestrales tal como las da Yahoo."""
    t = yf.Ticker(ticker)

    def leer(nombre):
        try:
            df = getattr(t, nombre)
            return df if df is not None else pd.DataFrame()
        except Exception:  # noqa: BLE001
            return pd.DataFrame()

    salida = {k: leer(v) for k, v in {
        "cuenta": "income_stmt", "balance": "balance_sheet", "caja": "cashflow",
        "cuenta_t": "quarterly_income_stmt", "balance_t": "quarterly_balance_sheet", "caja_t": "quarterly_cashflow"}.items()}
    if all(v.empty for v in salida.values()):
        return {}
    return salida


@con_cache(6 * 3600)
def mercado(ticker: str) -> dict:
    """Divisa, acciones, capitalización, dividendos y desdoblamientos (no dependen de la ficha de Yahoo)."""
    t = yf.Ticker(ticker)
    m = {}
    try:
        fi = t.fast_info
        for k_out, k in (("moneda", "currency"), ("precio", "lastPrice"), ("cap", "marketCap"), ("acciones", "shares"),
                         ("tipo", "quoteType")):
            try:
                m[k_out] = fi[k]
            except Exception:  # noqa: BLE001
                m[k_out] = None
    except Exception:  # noqa: BLE001
        pass
    try:
        h = t.history(period="10y", auto_adjust=False)
        if h is not None and not h.empty:
            if getattr(h.index, "tz", None) is not None:
                h.index = h.index.tz_localize(None)
            h.index = h.index.normalize()
            m["precios"] = h["Close"]
            m["dividendos"] = h["Dividends"][h["Dividends"] > 0]
            m["splits"] = h["Stock Splits"][h["Stock Splits"] > 0]
            m["volumen"] = h["Volume"]
    except Exception:  # noqa: BLE001
        pass
    return m


@con_cache(6 * 3600)
def serie_cambio(de: str, a: str) -> pd.Series:
    """Cuántas unidades de `a` vale 1 unidad de `de` (10 años, diario)."""
    h = yf.Ticker(f"{de}{a}=X").history(period="10y")
    if h is None or h.empty:
        return pd.Series(dtype=float)
    if getattr(h.index, "tz", None) is not None:
        h.index = h.index.tz_localize(None)
    return h["Close"].dropna()


@con_cache(12 * 3600)
def estimaciones(ticker: str) -> dict:
    """Previsiones de analistas: BPA de este año y del próximo, y crecimiento esperado. Vacío si Yahoo no las da."""
    t = yf.Ticker(ticker)
    salida = {}
    try:
        e = t.earnings_estimate
        if e is not None and not e.empty:
            for fila, clave in (("0y", "anio"), ("+1y", "anio_sig")):
                if fila in e.index:
                    salida[f"bpa_{clave}"] = _f(e.loc[fila].get("avg"))
                    salida[f"crec_{clave}"] = _f(e.loc[fila].get("growth"))
                    salida[f"n_{clave}"] = _f(e.loc[fila].get("numberOfAnalysts"))
    except Exception:  # noqa: BLE001
        pass
    try:
        r = t.revenue_estimate
        if r is not None and not r.empty and "+1y" in r.index:
            salida["crec_ingresos_sig"] = _f(r.loc["+1y"].get("growth"))
            salida["crec_ingresos_anio"] = _f(r.loc["0y"].get("growth")) if "0y" in r.index else None
    except Exception:  # noqa: BLE001
        pass
    return {k: v for k, v in salida.items() if v is not None}


@con_cache(12 * 3600)
def fechas_resultados(ticker: str) -> pd.DataFrame:
    """Últimas presentaciones de resultados: BPA esperado, publicado y sorpresa."""
    try:
        df = yf.Ticker(ticker).earnings_dates
    except Exception:  # noqa: BLE001
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    return df


# ----------------------------------------------------------------------------- utilidades
def _f(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(x) or math.isinf(x)) else x


def serie(df: pd.DataFrame, *nombres: str) -> pd.Series:
    """Primera fila que exista de `nombres`, ordenada de más antigua a más reciente, sin huecos."""
    if df is None or df.empty:
        return pd.Series(dtype=float)
    for n in nombres:
        if n in df.index:
            s = pd.to_numeric(df.loc[n], errors="coerce").dropna()
            if len(s):
                s.index = pd.to_datetime(s.index)
                return s.sort_index()
    return pd.Series(dtype=float)


def ttm(trimestral: pd.DataFrame, anual: pd.DataFrame, *nombres: str) -> tuple[float | None, str]:
    """Suma de los últimos 4 trimestres si están completos y son más recientes que el último año; si no, último año."""
    q, a = serie(trimestral, *nombres), serie(anual, *nombres)
    if len(q) >= 4:
        ult = q.iloc[-4:]
        completo = (ult.index[-1] - ult.index[0]).days <= 300
        if completo and (not len(a) or ult.index[-1] >= a.index[-1]):
            return float(ult.sum()), f"últimos 12 meses hasta {ult.index[-1]:%m/%Y}"
    if len(a):
        return float(a.iloc[-1]), f"ejercicio cerrado en {a.index[-1]:%m/%Y}"
    return None, ""


def ultimo(trimestral: pd.DataFrame, anual: pd.DataFrame, *nombres: str) -> float | None:
    """Último dato de balance (trimestral si es más reciente)."""
    q, a = serie(trimestral, *nombres), serie(anual, *nombres)
    if len(q) and (not len(a) or q.index[-1] >= a.index[-1]):
        return float(q.iloc[-1])
    return float(a.iloc[-1]) if len(a) else None


def cagr(s: pd.Series) -> float | None:
    """Crecimiento anual compuesto entre el primer y el último dato (solo si ambos son positivos)."""
    s = s.dropna()
    if len(s) < 2:
        return None
    ini, fin = float(s.iloc[0]), float(s.iloc[-1])
    anios = (s.index[-1] - s.index[0]).days / 365.25
    if ini <= 0 or fin <= 0 or anios < 0.9:
        return None
    return (fin / ini) ** (1 / anios) - 1


def _precio_en(precios: pd.Series, fecha) -> float | None:
    if precios is None or precios.empty:
        return None
    p = precios[precios.index <= pd.Timestamp(fecha) + pd.Timedelta(days=3)]
    return float(p.iloc[-1]) if len(p) else None


def _ajuste_splits(fecha, splits: pd.Series | None) -> float:
    """Factor por el que multiplicar unas acciones «de entonces» para ponerlas en base actual."""
    if splits is None or splits.empty:
        return 1.0
    posteriores = splits[splits.index > pd.Timestamp(fecha)]
    return float(posteriores.prod()) if len(posteriores) else 1.0


def acciones_ajustadas(acc: pd.Series, splits: pd.Series | None, acciones_hoy: float | None) -> pd.Series:
    """Acciones de cada ejercicio en base actual.

    Yahoo a veces da las acciones ya ajustadas por desdoblamientos y a veces no: se elige, año a año, la versión
    (con o sin ajuste) que queda más cerca de las acciones actuales.
    """
    if acc.empty:
        return acc
    ref = acciones_hoy or float(acc.iloc[-1])
    salida = {}
    for fecha, v in acc.items():
        con = v * _ajuste_splits(fecha, splits)
        salida[fecha] = con if abs(math.log(con / ref)) < abs(math.log(v / ref)) else v
    return pd.Series(salida)


# ----------------------------------------------------------------------------- cálculo principal
def calcular(ticker: str, ficha: dict | None = None, est: dict | None = None, mer: dict | None = None,
             prev: dict | None = None, cambio: float | None = None) -> dict:
    """Todos los ratios de la empresa. `ficha` (Yahoo) solo se usa como respaldo y para datos de analistas.

    `cambio`: cuántas unidades de la divisa de cotización vale 1 unidad de la divisa de las cuentas (None = misma divisa).
    """
    ficha = ficha or {}
    est = est if est is not None else (estados(ticker) or {})
    mer = mer if mer is not None else (mercado(ticker) or {})
    prev = prev if prev is not None else (estimaciones(ticker) or {})
    vacio = pd.DataFrame()
    cu, ba, ca = est.get("cuenta", vacio), est.get("balance", vacio), est.get("caja", vacio)
    cu_t, ba_t, ca_t = est.get("cuenta_t", vacio), est.get("balance_t", vacio), est.get("caja_t", vacio)
    r: dict = {"ticker": ticker, "avisos": [], "fuentes": {}, "notas": {}}

    # --- divisas: céntimos (peniques en Londres) y cuentas en otra moneda
    moneda = mer.get("moneda") or ficha.get("currency") or ""
    factor_precio = 0.01 if moneda in ("GBp", "GBX", "ZAc", "ILA") else 1.0
    moneda_base = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ILA": "ILS"}.get(moneda, moneda)
    moneda_cuentas = ficha.get("financialCurrency") or moneda_base
    fx, fx_serie = 1.0, None
    if moneda_cuentas and moneda_base and moneda_cuentas != moneda_base:
        if cambio:
            fx = float(cambio)
        else:
            try:
                fx_serie = serie_cambio(moneda_cuentas, moneda_base)
                fx = float(fx_serie.iloc[-1])
            except Exception:  # noqa: BLE001
                fx_serie = None
        if fx_serie is None and not cambio:
            r["avisos"].append(f"Las cuentas están en {moneda_cuentas} y la acción cotiza en {moneda_base}: no pude obtener el "
                               "tipo de cambio, así que los ratios de valoración pueden estar distorsionados.")
    r.update(moneda=moneda, moneda_base=moneda_base, moneda_cuentas=moneda_cuentas, fx=fx, factor_precio=factor_precio)

    precios = mer.get("precios")
    precio = _f(mer.get("precio")) or _f(ficha.get("precio")) or (float(precios.iloc[-1]) if precios is not None and len(precios) else None)
    r["precio"] = precio
    precio_n = precio * factor_precio if precio else None  # precio en la unidad de la divisa (libras, no peniques)

    # --- acciones y capitalización
    acc_hoy = _f(mer.get("acciones")) or _f(ficha.get("sharesOutstanding")) or ultimo(ba_t, ba, "Ordinary Shares Number", "Share Issued")
    cap = _f(mer.get("cap")) or _f(ficha.get("marketCap"))
    if cap and factor_precio != 1.0 and precio_n and acc_hoy and cap > 5 * precio_n * acc_hoy:
        cap *= factor_precio
    if not cap and precio_n and acc_hoy:
        cap = precio_n * acc_hoy
    r.update(acciones=acc_hoy, cap=cap)
    cap_c = cap / fx if cap else None  # capitalización en la divisa de las cuentas

    # --- cuenta de resultados (12 meses)
    ingresos, periodo = ttm(cu_t, cu, "Total Revenue", "Operating Revenue")
    neto, _ = ttm(cu_t, cu, "Net Income Common Stockholders", "Net Income")
    ebitda, _ = ttm(cu_t, cu, "EBITDA", "Normalized EBITDA")
    ebit, _ = ttm(cu_t, cu, "EBIT", "Operating Income")
    bruto, _ = ttm(cu_t, cu, "Gross Profit")
    operativo, _ = ttm(cu_t, cu, "Operating Income", "EBIT")
    bpa, periodo_bpa = ttm(cu_t, cu, "Diluted EPS", "Basic EPS")
    fcf, _ = ttm(ca_t, ca, "Free Cash Flow")
    if fcf is None:
        cfo, _ = ttm(ca_t, ca, "Operating Cash Flow")
        capex, _ = ttm(ca_t, ca, "Capital Expenditure")
        fcf = (cfo + capex) if (cfo is not None and capex is not None) else None
    r.update(ingresos=ingresos, neto=neto, ebitda=ebitda, ebit=ebit, fcf=fcf, bpa=bpa, periodo=periodo or periodo_bpa)
    es_banco = ebitda is None and bruto is None and ingresos is not None
    r["es_financiera"] = es_banco or (ficha.get("sector") in ("Financial Services",))

    # --- balance
    deuda = ultimo(ba_t, ba, "Total Debt")
    caja = ultimo(ba_t, ba, "Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents")
    deuda_neta = (deuda - caja) if (deuda is not None and caja is not None) else ultimo(ba_t, ba, "Net Debt")
    patrimonio = ultimo(ba_t, ba, "Stockholders Equity", "Common Stock Equity")
    capital_inv = ultimo(ba_t, ba, "Invested Capital")
    r.update(deuda=deuda, caja=caja, deuda_neta=deuda_neta, patrimonio=patrimonio)

    # --- valoración
    def pon(clave, valor, fuente, nota=""):
        r[clave] = _f(valor)
        if r[clave] is not None:
            r["fuentes"][clave] = fuente
            if nota:
                r["notas"][clave] = nota

    if neto and neto > 0 and cap_c:
        pon("per", cap_c / neto, F_CUENTAS, f"capitalización ÷ beneficio neto ({periodo})")
    elif bpa and bpa > 0 and precio_n:
        pon("per", precio_n / (bpa * fx), F_CUENTAS, f"precio ÷ beneficio por acción ({periodo_bpa})")
    else:
        pon("per", ficha.get("trailingPE"), F_YAHOO)
    if r.get("per") and _f(ficha.get("trailingPE")) and abs(r["per"] / ficha["trailingPE"] - 1) > 0.25:
        r["avisos"].append(f"El PER calculado con las cuentas ({r['per']:.1f}) difiere del que publica Yahoo "
                           f"({ficha['trailingPE']:.1f}): Yahoo usa el beneficio GAAP de los últimos 4 trimestres y su propio "
                           "recuento de acciones; partidas extraordinarias o cambios de divisa explican la diferencia.")

    bpa_fwd = _f(prev.get("bpa_anio_sig")) or _f(ficha.get("forwardEps"))
    if bpa_fwd and bpa_fwd > 0 and precio_n:
        pon("per_fwd", precio_n / bpa_fwd, F_ANALISTAS,
            "precio ÷ beneficio por acción esperado para el próximo ejercicio")
    else:
        pon("per_fwd", ficha.get("forwardPE"), F_ANALISTAS)
    r["bpa_fwd"] = bpa_fwd if bpa_fwd else ((precio_n / r["per_fwd"]) if (r.get("per_fwd") and precio_n) else None)

    if cap_c and ebitda and ebitda > 0 and deuda_neta is not None and not r["es_financiera"]:
        pon("ev_ebitda", (cap_c + deuda_neta) / ebitda, F_CUENTAS, "(capitalización + deuda neta) ÷ EBITDA de 12 meses")
    elif not r["es_financiera"]:
        pon("ev_ebitda", ficha.get("enterpriseToEbitda"), F_YAHOO)
    if cap_c and fcf and fcf > 0 and not r["es_financiera"]:
        pon("p_fcf", cap_c / fcf, F_CUENTAS, "capitalización ÷ flujo de caja libre de 12 meses")
        pon("fcf_yield", fcf / cap_c, F_CUENTAS)
    if cap_c and patrimonio and patrimonio > 0:
        pon("p_vc", cap_c / patrimonio, F_CUENTAS, "capitalización ÷ patrimonio neto")
    else:
        pon("p_vc", ficha.get("priceToBook"), F_YAHOO)
    if cap_c and ingresos and ingresos > 0:
        pon("p_ventas", cap_c / ingresos, F_CUENTAS)

    # --- rentabilidad
    pat_a = serie(ba, "Stockholders Equity", "Common Stock Equity")
    if neto is not None and patrimonio and patrimonio > 0:
        medio = (patrimonio + float(pat_a.iloc[-2])) / 2 if len(pat_a) >= 2 and pat_a.iloc[-2] > 0 else patrimonio
        pon("roe", neto / medio, F_CUENTAS, "beneficio neto ÷ patrimonio medio")
    else:
        pon("roe", ficha.get("returnOnEquity"), F_YAHOO)
    tasa = serie(cu, "Tax Rate For Calcs")
    tasa_v = float(tasa.iloc[-1]) if len(tasa) and 0 <= tasa.iloc[-1] < 0.6 else 0.25
    if ebit is not None and capital_inv and capital_inv > 0 and not r["es_financiera"]:
        pon("roic", ebit * (1 - tasa_v) / capital_inv, F_CUENTAS, "beneficio operativo después de impuestos ÷ capital invertido")
    if ingresos:
        if bruto is not None:
            pon("margen_bruto", bruto / ingresos, F_CUENTAS)
        if operativo is not None:
            pon("margen_op", operativo / ingresos, F_CUENTAS)
        if neto is not None:
            pon("margen_neto", neto / ingresos, F_CUENTAS)

    # --- deuda
    if deuda_neta is not None and ebitda and ebitda > 0 and not r["es_financiera"]:
        pon("deuda_neta_ebitda", deuda_neta / ebitda, F_CUENTAS, "años de EBITDA necesarios para pagar la deuda neta")
    if deuda is not None and patrimonio and patrimonio > 0 and not r["es_financiera"]:
        pon("deuda_capital", deuda / patrimonio, F_CUENTAS, "deuda total ÷ patrimonio neto")
    intereses, _ = ttm(cu_t, cu, "Interest Expense", "Interest Expense Non Operating")
    if ebit and intereses and intereses > 0 and not r["es_financiera"]:
        pon("cobertura_intereses", ebit / intereses, F_CUENTAS, "beneficio operativo ÷ gastos por intereses")

    # --- dividendo
    div = mer.get("dividendos")
    if div is not None and len(div) and precio:
        hace_un_anio = div.index[-1] - pd.Timedelta(days=350) if (pd.Timestamp.today() - div.index[-1]).days < 400 else pd.Timestamp.today()
        div_12m = float(div[div.index > hace_un_anio].sum())
        r["div_accion"] = div_12m
        if div_12m > 0:
            pon("div_yield", div_12m / precio, "Dividendos pagados (Yahoo Finance) · cálculo propio", "dividendos de los últimos 12 meses ÷ precio")
        por_anio = div.groupby(div.index.year).sum()
        por_anio = por_anio[por_anio.index < pd.Timestamp.today().year]
        r["div_por_anio"] = por_anio.tail(10)
        if len(por_anio) >= 4 and por_anio.iloc[-4] > 0:
            pon("div_crec_3a", (por_anio.iloc[-1] / por_anio.iloc[-4]) ** (1 / 3) - 1, F_CUENTAS)
        r["div_anios_seguidos"] = int((por_anio.tail(10) > 0).sum()) if len(por_anio) else 0
        r["div_recortes"] = int((por_anio.tail(10).pct_change() < -0.10).sum()) if len(por_anio) > 1 else 0
    else:
        r["div_accion"] = 0.0
    if not r.get("div_yield") and _f(ficha.get("rend_dividendo")):
        pon("div_yield", ficha["rend_dividendo"], F_YAHOO)
    div_pagado, _ = ttm(ca_t, ca, "Cash Dividends Paid", "Common Stock Dividend Paid")
    if div_pagado and neto and neto > 0:
        pon("payout", abs(div_pagado) / neto, F_CUENTAS, "dividendos pagados ÷ beneficio neto")
        if fcf and fcf > 0:
            pon("payout_fcf", abs(div_pagado) / fcf, F_CUENTAS, "dividendos pagados ÷ flujo de caja libre")
    else:
        pon("payout", ficha.get("payoutRatio"), F_YAHOO)

    # --- histórico anual
    r["anual"] = _tabla_anual(cu, ba, ca, mer, acc_hoy, fx, factor_precio, cap, precio_n, fx_serie)
    a = r["anual"]
    if not a.empty:
        pon("crec_ingresos_3a", cagr(a["ingresos"].dropna().tail(4)), F_CUENTAS)
        pon("crec_bpa_3a", cagr(a["bpa"].dropna().tail(4)), F_CUENTAS)
        pon("crec_acciones", cagr(a["acciones"].dropna()), F_CUENTAS)
        for clave, col in (("per_hist", "per"), ("ev_ebitda_hist", "ev_ebitda")):
            vals = a[col].dropna()
            vals = vals[(vals > 0) & (vals < 150)]
            extremos = pd.concat([a.get(f"{col}_min", pd.Series(dtype=float)), a.get(f"{col}_max", pd.Series(dtype=float))]).dropna()
            extremos = extremos[(extremos > 0) & (extremos < 200)]
            if len(vals) >= 2:
                r[clave] = {"min": float(extremos.min()) if len(extremos) else float(vals.min()),
                            "mediana": float(vals.median()), "max": float(extremos.max()) if len(extremos) else float(vals.max()),
                            "n": int(len(vals)), "desde": int(vals.index[0].year)}
                r["fuentes"][clave] = "Precios históricos y cuentas anuales (Yahoo Finance) · cálculo propio"

    # --- previsiones y PEG
    for k in ("crec_anio", "crec_anio_sig", "crec_ingresos_sig", "bpa_anio", "bpa_anio_sig"):
        if prev.get(k) is not None:
            r[f"prev_{k}"] = prev[k]
            r["fuentes"][f"prev_{k}"] = F_ANALISTAS
    if r.get("prev_crec_anio_sig") is None and r.get("per_fwd") and r.get("per"):
        r["prev_crec_anio_sig"] = r["per"] / r["per_fwd"] - 1
        r["fuentes"]["prev_crec_anio_sig"] = F_ANALISTAS + " frente al beneficio de los últimos 12 meses"
    peg = _f(ficha.get("trailingPegRatio")) or _f(ficha.get("pegRatio"))
    if peg and peg > 0:
        pon("peg", peg, F_YAHOO, "PER ÷ crecimiento esperado a 5 años (analistas)")
    else:
        g = r.get("prev_crec_anio_sig") or r.get("crec_bpa_3a")
        base = r.get("per_fwd") or r.get("per")
        if g and g > 0.01 and base:
            pon("peg", base / (g * 100), F_CUENTAS,
                "PER ÷ crecimiento del beneficio (" + ("esperado por analistas" if r.get("prev_crec_anio_sig") else "media de los últimos 3 años") + ")")

    # --- analistas
    for k_out, k in (("obj_bajo", "targetLowPrice"), ("obj_medio", "targetMeanPrice"), ("obj_alto", "targetHighPrice"),
                     ("n_analistas", "numberOfAnalystOpinions"), ("beta", "beta")):
        r[k_out] = _f(ficha.get(k))
    r["consenso"] = ficha.get("recommendationKey")

    # --- liquidez
    vol = mer.get("volumen")
    if vol is not None and len(vol) > 20 and precio_n:
        r["volumen_medio_eur"] = float(vol.tail(60).mean()) * precio_n
    if not r.get("periodo"):
        r["avisos"].append("Yahoo no tiene las cuentas de esta empresa: solo puedo dar los datos de mercado.")
    return r


def _tabla_anual(cu, ba, ca, mer, acc_hoy, fx, factor_precio, cap_hoy=None, precio_n=None,
                 fx_serie: pd.Series | None = None) -> pd.DataFrame:
    """Una fila por ejercicio con las magnitudes clave y la valoración a la que cotizaba entonces."""
    cols = {
        "ingresos": serie(cu, "Total Revenue", "Operating Revenue"), "bruto": serie(cu, "Gross Profit"),
        "operativo": serie(cu, "Operating Income", "EBIT"), "ebit": serie(cu, "EBIT", "Operating Income"),
        "ebitda": serie(cu, "EBITDA", "Normalized EBITDA"),
        "neto": serie(cu, "Net Income Common Stockholders", "Net Income"), "bpa_publicado": serie(cu, "Diluted EPS", "Basic EPS"),
        "acciones_dil": serie(cu, "Diluted Average Shares", "Basic Average Shares"),
        "fcf": serie(ca, "Free Cash Flow"), "recompras": serie(ca, "Repurchase Of Capital Stock"),
        "emision": serie(ca, "Issuance Of Capital Stock"),
        "dividendos": serie(ca, "Cash Dividends Paid", "Common Stock Dividend Paid"), "sbc": serie(ca, "Stock Based Compensation"),
        "capex": serie(ca, "Capital Expenditure"), "deuda": serie(ba, "Total Debt"),
        "caja": serie(ba, "Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"),
        "patrimonio": serie(ba, "Stockholders Equity", "Common Stock Equity"), "capital_inv": serie(ba, "Invested Capital"),
        "fondo_comercio": serie(ba, "Goodwill And Other Intangible Assets", "Goodwill"), "activos": serie(ba, "Total Assets"),
        "tasa": serie(cu, "Tax Rate For Calcs"), "id": serie(cu, "Research And Development"),
    }
    a = pd.DataFrame(cols)
    if a.empty or "ingresos" not in a or a["ingresos"].dropna().empty:
        return pd.DataFrame()
    a = a[a["ingresos"].notna()].sort_index()
    a["acciones"] = acciones_ajustadas(a["acciones_dil"].dropna(), mer.get("splits"), acc_hoy).reindex(a.index)
    a["bpa"] = a["neto"] / a["acciones"]  # en base actual (comparable entre años aunque haya habido desdoblamientos)
    a["margen_bruto"] = a["bruto"] / a["ingresos"]
    a["margen_op"] = a["operativo"] / a["ingresos"]
    a["margen_neto"] = a["neto"] / a["ingresos"]
    a["margen_fcf"] = a["fcf"] / a["ingresos"]
    a["deuda_neta"] = a["deuda"] - a["caja"]
    tasa = a["tasa"].where((a["tasa"] >= 0) & (a["tasa"] < 0.6), 0.25).fillna(0.25)
    a["roic"] = a["ebit"] * (1 - tasa) / a["capital_inv"].where(a["capital_inv"] > 0)
    a["roe"] = a["neto"] / a["patrimonio"].where(a["patrimonio"] > 0)
    a["conversion_caja"] = a["fcf"] / a["neto"].where(a["neto"] > 0)
    precios = mer.get("precios")
    for col in ("per", "per_min", "per_max", "ev_ebitda", "ev_ebitda_min", "ev_ebitda_max", "precio_cierre"):
        a[col] = np.nan
    # Escala entre «precio × acciones de las cuentas» y la capitalización real: corrige los ADR que agrupan varias
    # acciones (TSM = 5) y las empresas con varias clases de acciones.
    escala = 1.0
    acc_ult = a["acciones"].dropna()
    if cap_hoy and precio_n and len(acc_ult):
        escala = min(max(cap_hoy / (precio_n * float(acc_ult.iloc[-1])), 0.01), 100.0)
        if 0.85 < escala < 1.18:
            escala = 1.0  # diferencia normal por recompras desde el cierre del ejercicio
    if precios is not None and len(precios):
        for fecha in a.index:
            acc, neto, ebitda, dn = a.at[fecha, "acciones"], a.at[fecha, "neto"], a.at[fecha, "ebitda"], a.at[fecha, "deuda_neta"]
            p = _precio_en(precios, fecha)
            if p is None or pd.isna(acc):
                continue
            tramo = precios[(precios.index > fecha - pd.Timedelta(days=365)) & (precios.index <= fecha)]
            a.at[fecha, "precio_cierre"] = p
            for sufijo, px in (("", p), ("_min", float(tramo.min()) if len(tramo) > 100 else np.nan),
                               ("_max", float(tramo.max()) if len(tramo) > 100 else np.nan)):
                if pd.isna(px):
                    continue
                fx_f = fx
                if fx_serie is not None and len(fx_serie):
                    previos = fx_serie[fx_serie.index <= fecha + pd.Timedelta(days=3)]
                    fx_f = float(previos.iloc[-1]) if len(previos) else fx
                cap = px * factor_precio * acc * escala / fx_f
                if pd.notna(neto) and neto > 0:
                    a.at[fecha, "per" + sufijo] = cap / neto
                if pd.notna(ebitda) and ebitda > 0 and pd.notna(dn):
                    a.at[fecha, "ev_ebitda" + sufijo] = (cap + dn) / ebitda
    return a


# ----------------------------------------------------------------------------- comparables
def resumen_comparable(ticker: str, ficha: dict | None = None, cambio: float | None = None) -> dict:
    """Ratios de una empresa comparable (versión corta de `calcular`)."""
    try:
        r = calcular(ticker, ficha or {}, cambio=cambio)
    except Exception:  # noqa: BLE001
        return {}
    return {k: r.get(k) for k in ("ticker", "per", "per_fwd", "ev_ebitda", "p_fcf", "roe", "roic", "margen_op", "div_yield",
                                  "crec_ingresos_3a", "deuda_neta_ebitda", "cap", "moneda_base", "p_vc")}


def reaccion_resultados(fechas: pd.DataFrame, precios: pd.Series | None, maximo: int = 8) -> pd.DataFrame:
    """Cómo se movió la acción la sesión posterior a cada presentación de resultados."""
    if fechas is None or fechas.empty or precios is None or precios.empty:
        return pd.DataFrame()
    filas = []
    for momento, fila in fechas.iterrows():
        if pd.isna(fila.get("Reported EPS")):
            continue
        dia = pd.Timestamp(momento).normalize()
        antes = precios[precios.index < dia] if momento.hour < 9 else precios[precios.index <= dia]
        despues = precios[precios.index >= dia] if momento.hour < 9 else precios[precios.index > dia]
        if antes.empty or despues.empty:
            continue
        filas.append({"Fecha": dia.date(), "BPA esperado": _f(fila.get("EPS Estimate")), "BPA publicado": _f(fila.get("Reported EPS")),
                      "Sorpresa": (_f(fila.get("Surprise(%)")) or 0) / 100, "Reacción": float(despues.iloc[0] / antes.iloc[-1] - 1)})
        if len(filas) >= maximo:
            break
    return pd.DataFrame(filas)
