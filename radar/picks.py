"""📌 Picks del día: qué empresas presentan resultados en los próximos días y qué ha pasado otras veces.

No predice si subirá o bajará (nadie puede). Para cada empresa reúne lo que sí se sabe:
- qué beneficio espera el mercado y cuándo se publica,
- cuántas veces batió o falló las previsiones y qué hizo la acción al día siguiente en cada caso,
- cuánto movimiento descuentan hoy las opciones,
- si llega al día de resultados subiendo (buenas noticias ya en el precio) o castigada (listón bajo).

Con eso redacta el «si pasa esto, es probable que pase esto otro» con las frecuencias reales de esa empresa.

Fuentes: calendario de resultados de Nasdaq (EE. UU.) y de Yahoo Finance (Europa); historial y opciones de Yahoo Finance.
"""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pandas as pd
import requests

from . import datos, eventos
from . import fundamentales as fu
from .cache import con_cache

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept": "application/json, text/plain, */*"}
MOMENTO = {"time-pre-market": "antes de abrir la bolsa", "time-after-hours": "tras el cierre", "time-not-supplied": "hora sin confirmar"}


def _numero(texto) -> float | None:
    try:
        t = str(texto).replace("$", "").replace(",", "").strip()
        if t.startswith("(") and t.endswith(")"):
            t = "-" + t[1:-1]
        return float(t)
    except (TypeError, ValueError):
        return None


@con_cache(3 * 3600)
def calendario_eeuu(dia: str) -> list[dict]:
    """Empresas que presentan resultados ese día en EE. UU. (calendario público de Nasdaq)."""
    r = requests.get("https://api.nasdaq.com/api/calendar/earnings", params={"date": dia}, headers=UA, timeout=12)
    r.raise_for_status()
    filas = ((r.json().get("data") or {}).get("rows")) or []
    return [{"ticker": f["symbol"].replace("/", "-"), "nombre": f.get("name", ""), "fecha": dia, "momento": MOMENTO.get(f.get("time"), ""),
             "cap": _numero(f.get("marketCap")), "bpa_esperado": _numero(f.get("epsForecast")), "bpa_hace_un_anio": _numero(f.get("lastYearEPS")),
             "analistas": _numero(f.get("noOfEsts")), "bolsa": "EE. UU."} for f in filas if f.get("symbol")]


def proximos(dias: int = 7, mis_valores: tuple[str, ...] = (), europeos: tuple[str, ...] = (), cap_minima: float = 20e9) -> pd.DataFrame:
    """Presentaciones de resultados de los próximos `dias`: grandes empresas de EE. UU., los índices europeos y tus valores."""
    hoy = date.today()
    fechas = [(hoy + timedelta(days=i)).isoformat() for i in range(dias + 1) if (hoy + timedelta(days=i)).weekday() < 5]
    mios = {t.upper() for t in mis_valores}
    filas = []

    def un_dia(d):
        try:
            return calendario_eeuu(d)
        except Exception:  # noqa: BLE001
            return []

    with ThreadPoolExecutor(max_workers=6) as ex:
        for lista in ex.map(un_dia, fechas):
            filas += [f for f in lista if (f["cap"] or 0) >= cap_minima or f["ticker"].upper() in mios]
    eu = [t for t in dict.fromkeys(list(europeos) + [m for m in mios if "." in m])]
    if eu:
        try:
            ag = eventos.agenda(eu, dias)
            for _, f in ag[ag["Evento"].str.contains("Resultados")].iterrows():
                bpa = None
                if "BPA esperado" in str(f["Detalle"]):
                    bpa = _numero(str(f["Detalle"]).replace("BPA esperado", ""))
                filas.append({"ticker": f["Ticker"], "nombre": "", "fecha": f["Fecha"].isoformat(), "momento": "", "cap": None,
                              "bpa_esperado": bpa, "bpa_hace_un_anio": None, "analistas": None, "bolsa": eventos.bolsa_de(f["Ticker"])})
        except Exception:  # noqa: BLE001
            pass
    df = pd.DataFrame(filas)
    if df.empty:
        return df
    df = df.drop_duplicates(subset=["ticker"]).copy()
    df["mio"] = df["ticker"].str.upper().isin(mios)
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.date
    df["faltan"] = df["fecha"].map(lambda f: (f - hoy).days)
    return df.sort_values(["fecha", "mio", "cap"], ascending=[True, False, False]).reset_index(drop=True)


def _movimiento_opciones(ticker: str, fecha: date, precio: float) -> float | None:
    """Movimiento que descuentan las opciones para el primer vencimiento posterior a los resultados (solo EE. UU.)."""
    if "." in ticker:
        return None
    try:
        import yfinance as yf

        t = yf.Ticker(ticker)
        venc = next((v for v in (t.options or []) if pd.Timestamp(v).date() > fecha), None)
        if not venc:
            return None
        ch = t.option_chain(venc)
        comunes = sorted(set(ch.calls["strike"]) & set(ch.puts["strike"]))
        if not comunes:
            return None
        atm = min(comunes, key=lambda s: abs(s - precio))
        c, p = ch.calls[ch.calls["strike"] == atm].iloc[0], ch.puts[ch.puts["strike"] == atm].iloc[0]

        def medio(f):
            return (f["bid"] + f["ask"]) / 2 if (f["bid"] and f["ask"]) else f["lastPrice"]

        m = (medio(c) + medio(p)) / precio
        return float(m) if 0.005 < m < 0.6 else None
    except Exception:  # noqa: BLE001
        return None


@con_cache(3 * 3600)
def ficha(ticker: str, fecha_iso: str) -> dict:
    """Historial de reacciones a resultados, tendencia con la que llega y movimiento esperado."""
    fecha = date.fromisoformat(fecha_iso)
    mer = fu.mercado(ticker) or {}
    precios = mer.get("precios")
    if precios is None or len(precios) < 60:
        return {}
    precio = float(precios.iloc[-1])
    reac = fu.reaccion_resultados(fu.fechas_resultados(ticker), precios, 12)
    salida = {"ticker": ticker, "precio": precio, "moneda": mer.get("moneda") or "", "reacciones": reac,
              "mes": float(precio / precios.iloc[-22] - 1), "tres_meses": float(precio / precios.iloc[-min(64, len(precios))] - 1),
              "pos52": None, "implicito": _movimiento_opciones(ticker, fecha, precio)}
    anio = precios.tail(252)
    if anio.max() > anio.min():
        salida["pos52"] = float((precio - anio.min()) / (anio.max() - anio.min()))
    if not reac.empty:
        bate, falla = reac[reac["Sorpresa"] > 0], reac[reac["Sorpresa"] <= 0]
        salida.update(n=len(reac), n_bate=len(bate), n_falla=len(falla), media_abs=float(reac["Reacción"].abs().mean()),
                      media=float(reac["Reacción"].mean()), sube=int((reac["Reacción"] > 0).sum()),
                      bate_sube=int((bate["Reacción"] > 0).sum()), bate_media=float(bate["Reacción"].mean()) if len(bate) else None,
                      falla_sube=int((falla["Reacción"] > 0).sum()), falla_media=float(falla["Reacción"].mean()) if len(falla) else None,
                      peor=float(reac["Reacción"].min()), mejor=float(reac["Reacción"].max()))
    return salida


def _p(x, dec=1, signo=True) -> str:
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:{'+' if signo else ''}.{dec}f} %".replace(".", ",")


def lectura(f: dict, fila: dict) -> dict:
    """Convierte los números en frases: qué se espera, «si bate…», «si falla…», y qué tener en cuenta."""
    frases, avisos = [], []
    n = f.get("n", 0)
    esperado = f.get("implicito") or f.get("media_abs")
    if fila.get("bpa_esperado") is not None:
        t = f"El mercado espera un beneficio por acción de **{fila['bpa_esperado']:.2f}**".replace(".", ",")
        if fila.get("bpa_hace_un_anio"):
            crec = fila["bpa_esperado"] / fila["bpa_hace_un_anio"] - 1 if fila["bpa_hace_un_anio"] > 0 else None
            t += f" (hace un año ganó {fila['bpa_hace_un_anio']:.2f}".replace(".", ",") + (f", {_p(crec, 0)}" if crec is not None else "") + ")"
        frases.append(t + ".")
    if f.get("implicito"):
        t = f"Las opciones descuentan un movimiento de **±{_p(f["implicito"], 1, False)}** hasta el primer vencimiento después de los resultados"
        if f.get("media_abs"):
            rel = f["implicito"] / f["media_abs"]
            t += (f", más de lo habitual en esta empresa (±{_p(f['media_abs'], 1, False)}): el mercado está nervioso" if rel > 1.25 else
                  f", menos de lo que suele moverse (±{_p(f['media_abs'], 1, False)}): puede haber sorpresa" if rel < 0.8 else
                  f", en línea con lo que suele moverse (±{_p(f['media_abs'], 1, False)})")
        frases.append(t + ".")
    elif f.get("media_abs"):
        frases.append(f"En sus últimas {n} presentaciones se movió de media un **±{_p(f['media_abs'], 1, False)}** al día siguiente.")
    si_bate = si_falla = None
    if n >= 3:
        nb, nf = f["n_bate"], f["n_falla"]
        if nb:
            si_bate = (f"**Si bate previsiones** (lo hizo {nb} de {n} veces): subió {f['bate_sube']} y bajó {nb - f['bate_sube']}, "
                       f"con una media de {_p(f['bate_media'])}.")
            if nb >= 4 and f["bate_sube"] <= nb / 2:
                si_bate += " Batir no le basta: el listón real está por encima de la cifra oficial y lo que manda son las previsiones que dé para el trimestre siguiente."
            elif nb >= 3 and f["bate_sube"] >= 0.75 * nb:
                si_bate += " Cuando cumple, el mercado suele premiarla."
        if nf:
            si_falla = (f"**Si falla** (pasó {nf} de {n} veces): bajó {nf - f['falla_sube']} y subió {f['falla_sube']}, con una media de {_p(f['falla_media'])}.")
            if nf <= 2:
                si_falla += " Son muy pocos casos para sacar una regla."
        else:
            si_falla = (f"**Si falla**: no ha fallado ninguna de las últimas {n}, así que el mercado no lo espera. "
                        f"Su peor reacción reciente fue {_p(f['peor'])}; un fallo podría ser peor que eso.")
    else:
        avisos.append("Yahoo no tiene suficiente historial de resultados de esta empresa para decir cómo suele reaccionar.")
    mes = f.get("mes")
    if mes is not None:
        if mes > 0.10:
            avisos.append(f"Llega subiendo un {_p(mes, 0, False)} en el último mes: las buenas noticias ya están en el precio y hay más riesgo de "
                          "«comprar con el rumor, vender con la noticia».")
        elif mes < -0.10:
            avisos.append(f"Llega cayendo un {_p(abs(mes), 0, False)} en el último mes: las expectativas están bajas y un resultado simplemente correcto puede bastar para rebotar.")
    if f.get("pos52") is not None and f["pos52"] > 0.92:
        avisos.append("Cotiza pegada a máximos del año: poco margen para decepcionar.")
    # sesgo histórico (solo descriptivo)
    sesgo = "sin datos"
    if n >= 4:
        sesgo = ("favorable" if (f["sube"] >= 0.7 * n and f["media"] > 0.01) else "desfavorable" if (f["sube"] <= 0.35 * n and f["media"] < -0.01)
                 else "sin sesgo claro")
    interes = 0.0
    if esperado:
        interes += min(esperado / 0.03, 3)
    if fila.get("mio"):
        interes += 2
    if fila.get("cap"):
        interes += min(math.log10(max(fila["cap"], 1e9) / 1e9) / 1.5, 2)
    if mes is not None and abs(mes) > 0.10:
        interes += 0.5
    nivel = "alto" if interes >= 4 else "medio" if interes >= 2.5 else "bajo"
    return {"frases": frases, "si_bate": si_bate, "si_falla": si_falla, "avisos": avisos, "sesgo": sesgo, "interes": interes, "nivel": nivel,
            "esperado": esperado}


def universo_europeo() -> tuple[str, ...]:
    """IBEX 35 y Euro Stoxx 50 (lo que se mira para resultados en Europa)."""
    tickers = []
    for indice in ("IBEX 35", "Euro Stoxx 50"):
        try:
            tickers += datos.lista_indice(indice)
        except Exception:  # noqa: BLE001
            pass
    return tuple(dict.fromkeys(tickers))
