"""Escenarios de precio: simulación por bloques (bootstrap) condicionada al régimen de mercado.

Idea: se separan los días históricos en "mercado alcista" (el índice de referencia cotizaba sobre su media
de 200 sesiones el día anterior) y "mercado bajista". Con los retornos reales de la acción en cada régimen se
generan miles de caminos posibles y se resumen en percentiles:

    P10 = escenario pesimista · P50 = mediano · P90 = optimista

Esto NO es una predicción: es lo que pasaría si el futuro se pareciera estadísticamente al pasado.
El parámetro `prudencia` mezcla la rentabilidad histórica de la acción (que puede ser extraordinaria y no repetirse)
con la rentabilidad que implicaría su beta respecto al mercado.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DIAS_ANIO = 252
HORIZONTES = {"1 semana": 5, "2 semanas": 10, "1 mes": 21, "3 meses": 63, "6 meses": 126, "1 año": 252}
NOMBRES = {"alcista": "Mercado alcista", "mixto": "Histórico completo", "bajista": "Mercado bajista"}


def retornos_log(precios: pd.Series) -> pd.Series:
    return np.log(precios / precios.shift(1)).dropna()


def regimen_diario(ref: pd.Series, ventana: int = 200) -> pd.Series:
    """1.0 alcista / 0.0 bajista, usando el dato del día anterior (sin mirar al futuro)."""
    ma = ref.rolling(ventana).mean()
    reg = (ref > ma).astype(float).where(ma.notna())
    return reg.shift(1)


def preparar(accion: pd.Series, ref: pd.Series) -> pd.DataFrame:
    """Tabla con retornos de la acción (a), del índice (r) y régimen (g) en fechas comunes."""
    d = pd.concat({"a": accion, "r": ref}, axis=1).dropna()
    return pd.concat(
        {"a": retornos_log(d["a"]), "r": retornos_log(d["r"]), "g": regimen_diario(d["r"])}, axis=1, sort=True
    ).dropna()


def betas(d: pd.DataFrame) -> tuple[float, float]:
    """(beta general, beta en días de caída del índice)."""
    var = d["r"].var()
    beta = float(d["a"].cov(d["r"]) / var) if var > 0 else float("nan")
    bajas = d[d["r"] < 0]
    if len(bajas) > 30 and bajas["r"].var() > 0:
        beta_baja = float(bajas["a"].cov(bajas["r"]) / bajas["r"].var())
    else:
        beta_baja = float("nan")
    return beta, beta_baja


def _bootstrap(muestra: np.ndarray, dias: int, n: int, rng: np.random.Generator, bloque: int = 5) -> np.ndarray:
    """Log-retornos acumulados de n caminos, remuestreando bloques de `bloque` días."""
    bloque = max(1, min(bloque, len(muestra)))
    n_bloques = int(np.ceil(dias / bloque))
    inicios = rng.integers(0, len(muestra) - bloque + 1, size=(n, n_bloques))
    idx = inicios[:, :, None] + np.arange(bloque)[None, None, :]
    pasos = muestra[idx].reshape(n, -1)[:, :dias]
    return np.cumsum(pasos, axis=1)


def resumir(caminos_log: np.ndarray, precio0: float) -> dict:
    n, dias = caminos_log.shape
    precios = precio0 * np.exp(caminos_log)
    final = precios[:, -1]
    p = {q: float(np.percentile(final, q)) for q in (5, 10, 25, 50, 75, 90, 95)}
    cola = final[final <= p[5]]
    con_inicio = np.concatenate([np.full((n, 1), precio0), precios], axis=1)
    caida_max = (con_inicio / np.maximum.accumulate(con_inicio, axis=1) - 1).min(axis=1)
    bandas = np.percentile(precios, [10, 50, 90], axis=0)
    return {
        "percentiles": p,
        "prob_perdida": float((final < precio0).mean()),
        "perdida_cola_5": float(cola.mean()) if len(cola) else p[5],
        "caida_max_mediana": float(np.median(caida_max)),
        "caida_max_p10": float(np.percentile(caida_max, 10)),
        "bandas": {"p10": bandas[0], "p50": bandas[1], "p90": bandas[2]},
    }


def analizar(
    accion: pd.Series,
    ref: pd.Series,
    dias: int = 63,
    prudencia: float = 0.5,
    n: int = 4000,
    semilla: int = 7,
) -> dict:
    """Devuelve parámetros y los tres escenarios (alcista, mixto, bajista)."""
    d = preparar(accion.dropna(), ref.dropna())
    if len(d) < 250:
        raise ValueError("Histórico insuficiente: necesito al menos ~1 año de datos comunes con el índice.")
    precio0 = float(accion.dropna().iloc[-1])
    beta, beta_baja = betas(d)
    beta_uso = 1.0 if not np.isfinite(beta) else beta
    rng = np.random.default_rng(semilla)

    res = {
        "precio0": precio0,
        "dias": dias,
        "beta": beta,
        "beta_bajista": beta_baja,
        "pct_dias_alcistas": float((d["g"] == 1.0).mean()),
        "dias_muestra": len(d),
        "avisos": [],
        "escenarios": {},
    }
    for clave, filtro in (("alcista", 1.0), ("mixto", None), ("bajista", 0.0)):
        sub = d if filtro is None else d[d["g"] == filtro]
        if len(sub) < 60:
            res["avisos"].append(
                f"Pocos días en régimen {clave} ({len(sub)}): para ese escenario uso todo el histórico."
            )
            sub = d
        a = sub["a"].to_numpy()
        mu_hist = float(a.mean())
        mu_prior = beta_uso * float(sub["r"].mean())
        mu = (1 - prudencia) * mu_hist + prudencia * mu_prior
        caminos = _bootstrap(a - mu_hist + mu, dias, n, rng)
        res["escenarios"][clave] = {
            **resumir(caminos, precio0),
            "mu_anual": mu * DIAS_ANIO,
            "vol_anual": float(a.std(ddof=1) * np.sqrt(DIAS_ANIO)),
            "dias_muestra": len(sub),
        }
    return res


def estres(precio0: float, beta: float, beta_baja: float, caidas=(-0.05, -0.10, -0.20, -0.30)) -> pd.DataFrame:
    """Impacto aproximado en la acción si el índice cae X% (usa la beta de días de caída si existe)."""
    b = beta_baja if np.isfinite(beta_baja) else beta
    if not np.isfinite(b):
        return pd.DataFrame()
    filas = []
    for c in caidas:
        impacto = max(c * b, -1.0)
        filas.append({"Caída del índice": c, "Caída estimada de la acción": impacto, "Precio estimado": precio0 * (1 + impacto)})
    return pd.DataFrame(filas)
