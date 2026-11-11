"""Señales de trading a corto plazo (de 1 semana a 1 mes) con plan de entrada, stop loss (SL) y take profit (TP).

Cómo se construye la señal (todo con datos gratuitos):

  Técnica (de -6 a +6)
    · Tendencia: precio frente a su media de 200 sesiones y cruce/pendiente de la media de 50.
    · Impulso: rentabilidad del último mes y fuerza relativa frente a su índice en 3 meses.
    · RSI: premia retrocesos sanos dentro de una tendencia alcista y penaliza la sobrecompra.
    · Mercado: si el índice de referencia está en tendencia alcista o bajista.
  Contexto (de -3 a +3, solo en directo; no existe histórico gratuito de noticias)
    · Tono de las noticias de la empresa (Google News).
    · Sector: fuerza del ETF de su sector frente al S&P 500 y tono de las noticias del sector.
    · Analistas: potencial hasta el precio objetivo medio.

  Plan: SL a ~2 ATR (volatilidad media diaria) por debajo de la entrada, ajustado al mínimo reciente;
        TP a 2 veces el riesgo (relación beneficio/riesgo 2:1). Se calcula con miles de simulaciones la
        probabilidad de tocar antes el TP o el SL dentro del horizonte, y el resultado esperado en euros
        con comisiones e impuestos incluidos.

  Prueba histórica: la parte técnica se aplica día a día a los últimos años del valor para ver si
  habría ganado dinero de verdad, y se compara con entrar a ciegas con el mismo SL/TP.

Nada de esto es una garantía ni asesoramiento: es una forma ordenada de decidir y de limitar pérdidas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .escenarios import _bootstrap

SECTOR_ETF = {
    "Technology": "XLK", "Energy": "XLE", "Industrials": "XLI", "Financial Services": "XLF",
    "Healthcare": "XLV", "Utilities": "XLU", "Basic Materials": "XLB", "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP", "Real Estate": "XLRE", "Communication Services": "XLC",
}
SECTOR_ES = {
    "Technology": "tecnología", "Energy": "energía", "Industrials": "industria", "Financial Services": "banca y finanzas",
    "Healthcare": "salud", "Utilities": "eléctricas y utilities", "Basic Materials": "materias primas",
    "Consumer Cyclical": "consumo cíclico", "Consumer Defensive": "consumo básico", "Real Estate": "inmobiliario",
    "Communication Services": "telecomunicaciones y medios",
}
MAX_TECNICO, MAX_CONTEXTO = 6, 3


def etf_sector(sector: str | None, industria: str | None) -> str | None:
    if industria and "defense" in industria.lower():
        return "ITA"  # aeroespacial y defensa
    return SECTOR_ETF.get(sector or "")


def consulta_noticias_sector(sector: str | None, industria: str | None, ingles: bool = False) -> str | None:
    if ingles:
        return f"{industria or sector} stocks" if (industria or sector) else None
    if industria and "defense" in industria.lower():
        return "industria defensa contratos"
    base = SECTOR_ES.get(sector or "")
    return f"sector {base}" if base else None


# ----------------------------------------------------------------------------- indicadores
def rsi(c: pd.Series, n: int = 14) -> pd.Series:
    d = c.diff()
    sube = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    baja = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    r = 100 - 100 / (1 + sube / baja.replace(0, np.nan))
    return r.fillna(100.0).where(c.notna())


def atr(h: pd.DataFrame, n: int = 14) -> pd.Series:
    previo = h["Close"].shift(1)
    rango = pd.concat([h["High"] - h["Low"], (h["High"] - previo).abs(), (h["Low"] - previo).abs()], axis=1).max(axis=1)
    return rango.ewm(alpha=1 / n, adjust=False).mean()


def indicadores(h: pd.DataFrame, ref: pd.Series | None = None) -> pd.DataFrame:
    """Indicadores diarios. `h` debe tener Open, High, Low, Close (y opcionalmente Volume)."""
    c = h["Close"]
    df = pd.DataFrame(index=h.index)
    df["close"], df["high"], df["low"], df["open"] = c, h["High"], h["Low"], h["Open"]
    df["sma20"], df["sma50"], df["sma200"] = c.rolling(20).mean(), c.rolling(50).mean(), c.rolling(200).mean()
    df["pend50"] = df["sma50"] / df["sma50"].shift(10) - 1
    df["rsi"] = rsi(c)
    df["atr"] = atr(h)
    df["atr_pct"] = df["atr"] / c
    df["ret20"] = c / c.shift(20) - 1
    df["ret60"] = c / c.shift(60) - 1
    df["min10"] = h["Low"].rolling(10).min()
    df["max52"] = c.rolling(252, min_periods=120).max()
    if "Volume" in h:
        df["vol_rel"] = h["Volume"] / h["Volume"].rolling(50).mean()
    if ref is not None and len(ref.dropna()):
        r = ref.reindex(df.index).ffill()
        df["rs60"] = df["ret60"] - (r / r.shift(60) - 1)
        df["ref_alcista"] = (r > r.rolling(200).mean()).where(r.rolling(200).mean().notna())
    else:
        df["rs60"], df["ref_alcista"] = np.nan, np.nan
    return df


def puntuacion_tecnica(ind: pd.DataFrame) -> pd.Series:
    """Puntuación técnica diaria de -6 a +6 (NaN mientras no haya 200 sesiones)."""
    c = ind["close"]
    alcista = c > ind["sma200"]
    tendencia = np.where(alcista, 1, -1) + np.select(
        [(ind["sma50"] > ind["sma200"]) & (ind["pend50"] > 0), (ind["sma50"] < ind["sma200"]) & (ind["pend50"] < 0)],
        [1, -1], 0)
    impulso = np.where(ind["ret20"] > 0, 1, -1) + np.select([ind["rs60"] > 0, ind["rs60"] < 0], [1, -1], 0)
    r = ind["rsi"]
    osc = np.select([r > 75, alcista & (r >= 40) & (r <= 60), alcista & (r > 70)], [-1, 1, -1], 0)
    mercado = np.select([ind["ref_alcista"] == 1, ind["ref_alcista"] == 0], [1, -1], 0)
    total = pd.Series(tendencia + impulso + osc + mercado, index=ind.index, dtype=float)
    return total.where(ind["sma200"].notna() & ind["ret60"].notna())


def razones_tecnicas(ultima: pd.Series) -> list[tuple[int, str]]:
    """Explicación en lenguaje llano de cada componente (signo, texto)."""
    out = []
    c, s50, s200 = ultima["close"], ultima["sma50"], ultima["sma200"]
    if pd.notna(s200):
        if c > s200:
            out.append((1, f"Tendencia de fondo alcista: cotiza un {(c / s200 - 1) * 100:.0f}% por encima de su media de 200 sesiones."))
        else:
            out.append((-1, f"Tendencia de fondo bajista: cotiza un {(1 - c / s200) * 100:.0f}% por debajo de su media de 200 sesiones."))
        if s50 > s200 and ultima["pend50"] > 0:
            out.append((1, "La media de 50 sesiones está por encima de la de 200 y subiendo."))
        elif s50 < s200 and ultima["pend50"] < 0:
            out.append((-1, "La media de 50 sesiones está por debajo de la de 200 y bajando."))
    out.append((1 if ultima["ret20"] > 0 else -1, f"Último mes: {ultima['ret20'] * 100:+.1f}%."))
    if pd.notna(ultima.get("rs60")):
        out.append((1 if ultima["rs60"] > 0 else -1,
                    f"En 3 meses lo hace {abs(ultima['rs60']) * 100:.1f} puntos {'mejor' if ultima['rs60'] > 0 else 'peor'} que su índice."))
    r = ultima["rsi"]
    if r > 75:
        out.append((-1, f"RSI {r:.0f}: sobrecompra fuerte, riesgo de recogida de beneficios. Mejor esperar un retroceso."))
    elif c > s200 and r > 70:
        out.append((-1, f"RSI {r:.0f}: algo sobrecomprada; entrar ahora es perseguir el precio."))
    elif c > s200 and 40 <= r <= 60:
        out.append((1, f"RSI {r:.0f}: retroceso sano dentro de una tendencia alcista (buen punto de entrada)."))
    else:
        out.append((0, f"RSI {r:.0f}: sin señal clara."))
    if ultima.get("ref_alcista") == 1:
        out.append((1, "El mercado (su índice) está en tendencia alcista."))
    elif ultima.get("ref_alcista") == 0:
        out.append((-1, "El mercado (su índice) está en tendencia bajista: las compras salen peor."))
    return out


def puntuacion_contexto(tono_empresa: float | None, n_noticias: int, sector_rel: float | None,
                        tono_sector: float | None, potencial_analistas: float | None) -> tuple[int, list[tuple[int, str]]]:
    """Noticias, sector y analistas: cada uno suma -1, 0 o +1."""
    pts, out = 0, []
    if tono_empresa is not None and n_noticias >= 3:
        s = 1 if tono_empresa > 0.15 else -1 if tono_empresa < -0.15 else 0
        pts += s
        out.append((s, f"Noticias de la empresa (7 días): tono {'positivo' if s > 0 else 'negativo' if s < 0 else 'neutro'} "
                       f"({tono_empresa:+.2f}, {n_noticias} titulares)."))
    s_sec, partes = 0, []
    if sector_rel is not None and np.isfinite(sector_rel):
        s_sec += 1 if sector_rel > 0 else -1
        partes.append(f"su sector va {abs(sector_rel) * 100:.1f} puntos {'mejor' if sector_rel > 0 else 'peor'} que el S&P 500 en un mes")
    if tono_sector is not None:
        s_sec += 1 if tono_sector > 0.15 else -1 if tono_sector < -0.15 else 0
        partes.append(f"tono de noticias del sector {tono_sector:+.2f}")
    if partes:
        s = int(np.sign(s_sec))
        pts += s
        out.append((s, "Sector: " + "; ".join(partes) + "."))
    if potencial_analistas is not None and np.isfinite(potencial_analistas):
        s = 1 if potencial_analistas > 0.15 else -1 if potencial_analistas < 0 else 0
        pts += s
        out.append((s, f"Analistas: el precio objetivo medio está un {potencial_analistas * 100:+.0f}% respecto a hoy."))
    return pts, out


def veredicto(tecnica: float, contexto: int) -> tuple[str, str, int]:
    """(etiqueta, explicación, nota 0-100)."""
    nota = int(round((tecnica + contexto + MAX_TECNICO + MAX_CONTEXTO) / (2 * (MAX_TECNICO + MAX_CONTEXTO)) * 100))
    if tecnica >= 3 and nota >= 65:
        return "🟢 Candidata a compra", "La mayoría de factores acompañan. Si entras, hazlo con el plan de SL y TP.", nota
    if tecnica <= 0 or nota <= 40:
        return "🔴 No entrar", "Los factores juegan en contra. Mejor buscar otra o esperar a que cambie.", nota
    return "🟡 Vigilar", "Señales mixtas. Espera a que mejore (p. ej., retroceso con RSI 40-60 o noticias a favor).", nota


# ----------------------------------------------------------------------------- niveles y costes
def niveles(precio: float, atr_v: float, min10: float | None, k_sl: float = 2.0, rr: float = 2.0) -> tuple[float, float]:
    """(stop loss, take profit). SL a k·ATR, subido al mínimo de 10 sesiones si queda a ≥1 ATR; TP = rr × riesgo."""
    sl = precio - k_sl * atr_v
    if min10 is not None and np.isfinite(min10):
        swing = min10 - 0.25 * atr_v
        if sl < swing <= precio - atr_v:
            sl = swing
    sl = max(sl, precio * 0.01)
    return sl, precio + rr * (precio - sl)


def impuesto_compra(ticker: str, capitalizacion: float | None) -> float:
    """Impuesto español sobre transacciones financieras (0,2 % al comprar empresas españolas de más de 1.000 M€)."""
    return 0.002 if ticker.upper().endswith(".MC") and (capitalizacion or 0) > 1e9 else 0.0


def euros(importe: float, comision: float, impuesto: float, entrada: float, salida: float | np.ndarray):
    """Resultado neto en € de comprar `importe` a `entrada` y vender a `salida` (comisión en compra y venta)."""
    acciones = max(importe - comision - importe * impuesto, 0.0) / entrada
    return acciones * salida - comision - importe


# ----------------------------------------------------------------------------- simulación del plan
def simular_plan(cierres: pd.Series, precio: float, sl: float, tp: float, dias: int, importe: float, comision: float,
                 impuesto: float, ref: pd.Series | None = None, prudencia: float = 0.5, n: int = 5000,
                 semilla: int = 11) -> dict:
    """Probabilidad de tocar TP o SL antes del horizonte y resultado esperado en €."""
    r = np.log(cierres / cierres.shift(1)).dropna().tail(756)  # ~3 años
    mu_hist = float(r.mean())
    mu_prior = 0.0
    if ref is not None:
        rr = np.log(ref / ref.shift(1)).reindex(r.index).dropna()
        comunes = r.reindex(rr.index)
        if len(rr) > 100 and rr.var() > 0:
            mu_prior = float(comunes.cov(rr) / rr.var()) * float(rr.mean())
    mu = (1 - prudencia) * mu_hist + prudencia * mu_prior
    rng = np.random.default_rng(semilla)
    caminos = precio * np.exp(_bootstrap(r.to_numpy() - mu_hist + mu, dias, n, rng))
    toca_tp, toca_sl = caminos >= tp, caminos <= sl
    dia_tp = np.where(toca_tp.any(axis=1), toca_tp.argmax(axis=1), dias + 1)
    dia_sl = np.where(toca_sl.any(axis=1), toca_sl.argmax(axis=1), dias + 1)
    gana = dia_tp < dia_sl
    pierde = dia_sl < dia_tp
    tiempo = ~(gana | pierde)
    salida = np.where(gana, tp, np.where(pierde, sl, caminos[:, -1]))
    resultado = euros(importe, comision, impuesto, precio, salida)
    minimo, maximo = caminos.min(axis=1), caminos.max(axis=1)
    return {
        "prob_tp": float(gana.mean()), "prob_sl": float(pierde.mean()), "prob_tiempo": float(tiempo.mean()),
        "esperado_eur": float(resultado.mean()),
        "eur_tp": float(euros(importe, comision, impuesto, precio, tp)),
        "eur_sl": float(euros(importe, comision, impuesto, precio, sl)),
        "dias_medios_tp": float(dia_tp[gana].mean() + 1) if gana.any() else float("nan"),
        "cierre_p10": float(np.percentile(caminos[:, -1], 10)), "cierre_p50": float(np.median(caminos[:, -1])),
        "cierre_p90": float(np.percentile(caminos[:, -1], 90)),
        "minimo_tipico": float(np.median(minimo)), "maximo_tipico": float(np.median(maximo)),
    }


def rangos(cierres: pd.Series, atr_v: float, precio: float, horizontes=(("1 día", 1), ("1 semana", 5), ("2 semanas", 10),
                                                                         ("1 mes", 21)), n: int = 5000) -> pd.DataFrame:
    """Rango probable de precio en cada horizonte (sin tendencia: solo volatilidad)."""
    r = np.log(cierres / cierres.shift(1)).dropna().tail(756).to_numpy()
    r = r - r.mean()
    rng = np.random.default_rng(5)
    un_dia = precio * np.exp(rng.choice(r, size=n))
    filas = [{"Horizonte": "Un día cualquiera", "Mínimo probable": precio - atr_v / 2, "Máximo probable": precio + atr_v / 2,
              "Cierre P10": float(np.percentile(un_dia, 10)), "Cierre P90": float(np.percentile(un_dia, 90)),
              "Movimiento típico": atr_v / precio}]
    for etiqueta, d in horizontes[1:]:
        caminos = precio * np.exp(_bootstrap(r, d, n, rng, bloque=min(5, d)))
        filas.append({"Horizonte": etiqueta, "Mínimo probable": float(np.median(caminos.min(axis=1))),
                      "Máximo probable": float(np.median(caminos.max(axis=1))),
                      "Cierre P10": float(np.percentile(caminos[:, -1], 10)),
                      "Cierre P90": float(np.percentile(caminos[:, -1], 90)),
                      "Movimiento típico": float(np.std(caminos[:, -1] / precio - 1))})
    return pd.DataFrame(filas)


# ----------------------------------------------------------------------------- prueba histórica
def backtest(h: pd.DataFrame, ref: pd.Series | None, umbral: float = 3, k_sl: float = 2.0, rr: float = 2.0,
             max_dias: int = 21, importe: float = 100.0, comision: float = 1.0, impuesto: float = 0.0) -> pd.DataFrame:
    """Opera la regla técnica día a día. Entra al cierre si puntuación ≥ umbral; sale por SL, TP o tiempo.

    Supuestos prudentes: si un mismo día se tocan SL y TP se cuenta el SL; si abre por debajo del SL se vende a la apertura.
    """
    ind = indicadores(h, ref)
    nota = puntuacion_tecnica(ind)
    o, hi, lo, c = (ind[k].to_numpy() for k in ("open", "high", "low", "close"))
    a, m10, s = ind["atr"].to_numpy(), ind["min10"].to_numpy(), nota.to_numpy()
    fechas = ind.index
    ops, i, n = [], 0, len(ind)
    while i < n - 1:
        if not (np.isfinite(s[i]) and s[i] >= umbral and np.isfinite(a[i])):
            i += 1
            continue
        entrada = c[i]
        sl, tp = niveles(entrada, a[i], m10[i], k_sl, rr)
        salida, motivo, j = None, "tiempo", i
        for j in range(i + 1, min(i + max_dias, n - 1) + 1):
            if lo[j] <= sl:
                salida, motivo = min(o[j], sl), "stop loss"
                break
            if hi[j] >= tp:
                salida, motivo = max(o[j], tp), "take profit"
                break
        if salida is None:
            salida = c[j]
        ops.append({"entrada_fecha": fechas[i], "salida_fecha": fechas[j], "entrada": entrada, "salida": salida,
                    "sl": sl, "tp": tp, "motivo": motivo, "dias": j - i, "nota": s[i],
                    "resultado_eur": euros(importe, comision, impuesto, entrada, salida)})
        i = j + 1
    return pd.DataFrame(ops)


def resumen_backtest(ops: pd.DataFrame, importe: float = 100.0) -> dict:
    if ops.empty:
        return {"operaciones": 0}
    r = ops["resultado_eur"]
    ganancias, perdidas = r[r > 0].sum(), -r[r < 0].sum()
    racha = max_racha = 0
    for x in r:
        racha = racha + 1 if x < 0 else 0
        max_racha = max(max_racha, racha)
    acumulado = r.cumsum()
    return {
        "operaciones": len(ops), "acierto": float((r > 0).mean()), "media_eur": float(r.mean()),
        "total_eur": float(r.sum()), "media_pct": float(r.mean() / importe),
        "factor_beneficio": float(ganancias / perdidas) if perdidas > 0 else float("inf"),
        "peor_racha": int(max_racha), "peor_caida_eur": float((acumulado - acumulado.cummax()).min()),
        "dias_medios": float(ops["dias"].mean()),
        "por_motivo": ops["motivo"].value_counts().to_dict(),
    }


# ----------------------------------------------------------------------------- escáner
def escanear(datos_ohlc: dict, refs: dict, referencia_para) -> pd.DataFrame:
    """Puntuación técnica actual de muchos valores. `datos_ohlc`: ticker → DataFrame OHLC."""
    filas = []
    for t, h in datos_ohlc.items():
        if h is None or len(h.dropna()) < 220:
            continue
        ind = indicadores(h.dropna(), refs.get(referencia_para(t)))
        nota = puntuacion_tecnica(ind).iloc[-1]
        u = ind.iloc[-1]
        if not np.isfinite(nota):
            continue
        sl, tp = niveles(u["close"], u["atr"], u["min10"])
        filas.append({"Ticker": t, "Puntuación técnica": nota, "Precio": u["close"], "Último mes": u["ret20"],
                      "RSI": u["rsi"], "Volatilidad diaria": u["atr_pct"], "vs media 200d": u["close"] / u["sma200"] - 1,
                      "Fuerza vs índice (3m)": u["rs60"], "SL": sl, "TP": tp})
    df = pd.DataFrame(filas)
    if df.empty:
        return df
    return df.sort_values(["Puntuación técnica", "Fuerza vs índice (3m)"], ascending=False).reset_index(drop=True)


# ----------------------------------------------------------------------------- comparador
def comparar(datos_ohlc: dict, refs: dict, referencia_para, umbral: float = 3, k_sl: float = 2.0, rr: float = 2.0,
             max_dias: int = 21, importe: float = 500.0, comision: float = 1.0, impuesto_de=lambda t: 0.0) -> pd.DataFrame:
    """Para cada valor: la señal frente a entrar a ciegas (mismo SL/TP) y frente a comprar y mantener."""
    filas = []
    for t, h in datos_ohlc.items():
        h = h.dropna(subset=["Open", "High", "Low", "Close"]) if h is not None else None
        if h is None or len(h) < 300:
            continue
        ref = refs.get(referencia_para(t))
        imp = impuesto_de(t)
        s = resumen_backtest(backtest(h, ref, umbral, k_sl, rr, max_dias, importe, comision, imp), importe)
        b = resumen_backtest(backtest(h, ref, -99, k_sl, rr, max_dias, importe, comision, imp), importe)
        inicio = h.index[200]  # misma ventana que puede operar la señal (necesita 200 sesiones previas)
        mantener = float(euros(importe, comision, imp, float(h.loc[inicio, "Close"]), float(h["Close"].iloc[-1])))
        anios = max((h.index[-1] - inicio).days / 365.25, 0.1)
        if not s["operaciones"]:
            veredicto_c = "⚪ Sin operaciones"
        elif s["media_eur"] <= 0:
            veredicto_c = "🔴 Pierde"
        elif b.get("operaciones") and s["media_eur"] <= b["media_eur"]:
            veredicto_c = "🟡 Gana, pero no aporta"
        else:
            veredicto_c = "🟢 Aporta ventaja"
        filas.append({
            "Ticker": t, "Veredicto": veredicto_c, "Operaciones": s.get("operaciones", 0), "Acierto": s.get("acierto"),
            "Señal: media/op (€)": s.get("media_eur"), "A ciegas: media/op (€)": b.get("media_eur"),
            "Señal: total (€)": s.get("total_eur", 0.0), "Comprar y mantener (€)": mantener,
            "Años": round(anios, 1), "Factor de beneficio": s.get("factor_beneficio"),
        })
    df = pd.DataFrame(filas)
    if df.empty:
        return df
    orden = {"🟢": 0, "🟡": 1, "🔴": 2, "⚪": 3}
    df["_o"] = df["Veredicto"].str[0].map(orden)
    return df.sort_values(["_o", "Señal: media/op (€)"], ascending=[True, False]).drop(columns="_o").reset_index(drop=True)


def resumen_comparador(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    v = df["Veredicto"].str[0]
    return {"valores": len(df), "aporta": int((v == "🟢").sum()), "no_aporta": int((v == "🟡").sum()),
            "pierde": int((v == "🔴").sum()), "media_senal": float(df["Señal: media/op (€)"].mean()),
            "media_ciegas": float(df["A ciegas: media/op (€)"].mean()),
            "total_senal": float(df["Señal: total (€)"].sum()), "total_mantener": float(df["Comprar y mantener (€)"].sum())}
