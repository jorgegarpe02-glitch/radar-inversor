"""💡 Ideas: las 10 acciones más atractivas de un grupo para comprar con un horizonte de 6 a 12 meses.

Pasa el mismo análisis de 🧠 Análisis a muchas empresas y se queda con las mejores. Para no tardar una eternidad va en dos fases:

1. Criba rápida (una consulta por empresa): descarta lo que a simple vista no interesa (sin potencial según analistas,
   poca rentabilidad, sin crecimiento, mucha deuda) y se queda con unas 24 candidatas.
2. Análisis completo de esas candidatas: calidad, escenarios de precio, riesgos y recomendación, más la tendencia de medio plazo.

El orden final premia la ganancia del escenario base, castiga la pérdida del pesimista y da un extra a la calidad y a que la
tendencia no vaya en contra. Es una lista para empezar a mirar, no una orden de compra.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from . import analisis as an
from . import conexiones, datos, negocio
from . import fundamentales as fu

UNIVERSOS = {
    "España (IBEX 35)": ("IBEX 35",),
    "Europa (Euro Stoxx 50 + IBEX 35)": ("Euro Stoxx 50", "IBEX 35"),
    "EE. UU. grandes (Dow Jones + S&P 100)": ("Dow Jones", "S&P 100"),
    "Tecnología y crecimiento (Nasdaq-100)": ("Nasdaq-100",),
    "Todo lo anterior (tarda varios minutos)": ("IBEX 35", "Euro Stoxx 50", "Dow Jones", "S&P 100", "Nasdaq-100"),
}


def tickers_de(universo: str) -> list[str]:
    salida = []
    for indice in UNIVERSOS[universo]:
        try:
            salida += datos.lista_indice(indice)
        except Exception:  # noqa: BLE001
            pass
    return list(dict.fromkeys(salida))


def _criba(t: str) -> dict:
    try:
        f = datos.ficha(t)
    except Exception:  # noqa: BLE001
        return {}
    p = f.get("precio")
    if not p or f.get("quoteType") not in (None, "EQUITY"):
        return {}
    pot = f["targetMeanPrice"] / p - 1 if f.get("targetMeanPrice") else None
    roe, crec, per_f, deuda = f.get("returnOnEquity"), f.get("revenueGrowth"), f.get("forwardPE"), f.get("debtToEquity")
    nota = 0.0
    if pot is not None:
        nota += 2 * max(min(pot, 0.5), -0.2)
    nota += 1.0 if (roe or 0) >= 0.15 else 0.5 if (roe or 0) >= 0.10 else 0
    nota += 0.6 if (crec or 0) >= 0.08 else 0.3 if (crec or 0) >= 0.03 else -0.3 if (crec is not None and crec < 0) else 0
    nota += 0.5 if (per_f and 0 < per_f < 22) else -0.5 if (per_f and per_f > 45) else 0
    nota -= 0.5 if (deuda or 0) > 250 else 0
    return {"ticker": t, "nombre": f.get("shortName") or t, "nota_criba": nota, "ficha": f}


def _evaluar(c: dict) -> dict | None:
    t, f = c["ticker"], c["ficha"]
    try:
        m = fu.calcular(t, f)
        h = datos.historial(t, "5y")
        id_base = conexiones.entidad(t, f.get("longName") or "")
        ficha_base = conexiones.ficha_entidad(id_base) if id_base else {}
        seg = negocio.segmentos(t, id_base, usar_sec=False)
        nombre = ficha_base.get("nombre") or conexiones.nombre_corto(f.get("longName") or c["nombre"])
        a = an.completo(nombre, m, h, sector=an.sector_yahoo(f.get("sector"), ficha_base.get("sector")), industria=f.get("industry"), seg=seg)
    except Exception:  # noqa: BLE001
        return None
    rec, cal, tec = a["recomendacion"], a["calidad"], a["tecnico"]
    if rec.get("rent_base") is None:
        return None
    medio = "neutral"
    if tec:
        medio = "a favor" if tec.get("tendencia") == "alcista" else "en contra" if tec.get("tendencia") == "bajista" else "neutral"
    puntos = rec["rent_base"] - 0.5 * abs(min(rec.get("rent_pesimista") or 0, 0)) + 0.10 * (cal["media"] - 1)
    puntos += 0.05 if medio == "a favor" else -0.05 if medio == "en contra" else 0
    fuertes = [x["criterio"] for x in cal["criterios"] if x["nota"] == 2]
    graves = [r["titulo"] for r in a["riesgos"]["lista"] if r["severidad"] == 2] or [r["titulo"] for r in a["riesgos"]["lista"][:1]]
    principal = negocio.principal(seg) if seg.get("ejes") else None
    return {"ticker": t, "nombre": nombre, "precio": m.get("precio"), "moneda": m.get("moneda") or "", "titulo": rec["titulo"], "color": rec["color"],
            "rent_base": rec["rent_base"], "rent_pesimista": rec.get("rent_pesimista"), "entrada": rec.get("entrada"), "calidad": cal["etiqueta"],
            "medio": medio, "puntos": puntos, "fuertes": fuertes[:2], "riesgo": graves[0] if graves else "", "per": m.get("per"),
            "per_fwd": m.get("per_fwd"), "dividendo": m.get("div_yield"), "crecimiento": m.get("prev_crec_anio_sig"),
            "sector": an.SECTOR_ES.get(a.get("sector") or "", ""), "principal": principal, "resumen": a["resumen"],
            "estrellas": a["estrellas"]["crecimiento"], "dca": a["dca"]["veredicto"]}


def ranking(universo: str, a_fondo: int = 24, progreso=None) -> dict:
    """{'mejores': [...10], 'analizadas': n, 'cribadas': n, 'universo': n}. `progreso(fracción, texto)` es opcional."""
    tickers = tickers_de(universo)
    avisar = progreso or (lambda *_: None)
    cribadas = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for i, c in enumerate(ex.map(_criba, tickers)):
            if c:
                cribadas.append(c)
            avisar(0.5 * (i + 1) / max(len(tickers), 1), f"Criba rápida: {i + 1} de {len(tickers)} empresas")
    candidatas = sorted(cribadas, key=lambda c: -c["nota_criba"])[:a_fondo]
    evaluadas = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for i, e in enumerate(ex.map(_evaluar, candidatas)):
            if e:
                evaluadas.append(e)
            avisar(0.5 + 0.5 * (i + 1) / max(len(candidatas), 1), f"Análisis a fondo: {i + 1} de {len(candidatas)} candidatas")
    compra = sorted([e for e in evaluadas if e["color"] == "verde"], key=lambda e: -e["puntos"])
    espera = sorted([e for e in evaluadas if e["color"] == "amarillo" and e["titulo"] == "ESPERAR MEJOR PRECIO" and e["rent_base"] > 0.05
                     and e["calidad"] != "Mediocre"],
                    key=lambda e: -e["puntos"])
    mejores = (compra + espera)[:10]
    return {"mejores": mejores, "n_compra": len(compra), "analizadas": len(evaluadas), "cribadas": len(cribadas), "universo": len(tickers),
            "momento": pd.Timestamp.now(), "tabla": evaluadas}
