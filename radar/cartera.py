"""Simulador de compra para aportaciones pequeñas y efecto sobre tu cartera."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .config import CARPETA
from .escenarios import NOMBRES

RUTA_POSICIONES = CARPETA / "posiciones.json"


def cargar_posiciones() -> pd.DataFrame:
    try:
        datos = json.loads(RUTA_POSICIONES.read_text(encoding="utf-8"))
        df = pd.DataFrame(datos, columns=["ticker", "importe_eur"])
    except (OSError, ValueError):
        df = pd.DataFrame({"ticker": pd.Series(dtype="str"), "importe_eur": pd.Series(dtype="float")})
    df["importe_eur"] = pd.to_numeric(df["importe_eur"], errors="coerce")
    return df


def guardar_posiciones(df: pd.DataFrame) -> None:
    limpio = df.dropna(subset=["ticker", "importe_eur"]).copy()
    limpio["ticker"] = limpio["ticker"].astype(str).str.strip().str.upper()
    limpio = limpio[(limpio["ticker"] != "") & (limpio["importe_eur"] > 0)]
    RUTA_POSICIONES.parent.mkdir(parents=True, exist_ok=True)
    RUTA_POSICIONES.write_text(json.dumps(limpio.to_dict("records")), encoding="utf-8")


def simular_compra(
    importe: float, comision: float, escenarios: dict, precio0: float, cartera_total: float | None = None
) -> pd.DataFrame:
    """Resultado en euros de comprar `importe` hoy, en cada escenario (pesimista P10, mediano P50, optimista P90)."""
    neto = max(importe - comision, 0.0)
    acciones = neto / precio0 if precio0 > 0 else 0.0
    filas = []
    for clave in ("alcista", "mixto", "bajista"):
        e = escenarios[clave]
        fila = {"Escenario": NOMBRES[clave]}
        for etiqueta, q in (("Pesimista (P10)", 10), ("Mediano (P50)", 50), ("Optimista (P90)", 90)):
            fila[etiqueta] = acciones * e["percentiles"][q] - importe
        fila["Probabilidad de pérdida"] = e["prob_perdida"]
        if cartera_total and cartera_total > 0:
            fila["Mediano sobre tu cartera"] = fila["Mediano (P50)"] / cartera_total
        filas.append(fila)
    return pd.DataFrame(filas)


def efecto_en_cartera(posiciones: pd.DataFrame, candidato: str, importe: float, cierres: pd.DataFrame) -> dict | None:
    """Volatilidad de tu cartera antes y después de añadir `importe` del candidato (retornos históricos)."""
    pos = posiciones.dropna().copy()
    pos["ticker"] = pos["ticker"].astype(str).str.upper()
    pesos = pos.groupby("ticker")["importe_eur"].sum()
    pesos = pesos[(pesos > 0) & pesos.index.isin(cierres.columns)]
    if pesos.empty or candidato not in cierres.columns:
        return None
    despues = pesos.copy()
    despues[candidato] = despues.get(candidato, 0.0) + importe
    todos = list(dict.fromkeys(list(pesos.index) + [candidato]))
    ret = np.log(cierres[todos].dropna()).diff().dropna()
    if len(ret) < 120:
        return None

    def vol(p: pd.Series) -> float:
        w = (p.reindex(todos).fillna(0.0) / p.sum()).to_numpy()
        return float(np.sqrt(w @ (ret.cov().to_numpy() * 252) @ w))

    w0 = (pesos / pesos.sum()).reindex(todos).fillna(0.0)
    serie_cartera = ret.mul(w0, axis=1).sum(axis=1)
    return {
        "vol_antes": vol(pesos),
        "vol_despues": vol(despues),
        "correlacion": float(serie_cartera.corr(ret[candidato])),
        "peso_nuevo": importe / (pesos.sum() + importe),
        "dias": len(ret),
    }
