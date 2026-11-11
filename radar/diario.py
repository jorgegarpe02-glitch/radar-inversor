"""Diario de operaciones: apunta cada operación para aprender de tus aciertos y errores."""
from __future__ import annotations

import pandas as pd

from .config import CARPETA

RUTA = CARPETA / "diario.csv"
COLUMNAS = ["fecha_entrada", "ticker", "importe_eur", "precio_entrada", "stop_loss", "take_profit",
            "motivo_entrada", "fecha_salida", "precio_salida", "comisiones_eur", "notas"]
NUMERICAS = ["importe_eur", "precio_entrada", "stop_loss", "take_profit", "precio_salida", "comisiones_eur"]


def cargar() -> pd.DataFrame:
    try:
        df = pd.read_csv(RUTA, dtype=str)
    except (OSError, ValueError):
        df = pd.DataFrame(columns=COLUMNAS)
    for c in COLUMNAS:
        if c not in df.columns:
            df[c] = None
    df = df[COLUMNAS]
    for c in NUMERICAS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ("fecha_entrada", "fecha_salida"):
        df[c] = pd.to_datetime(df[c], errors="coerce").dt.date
    for c in ("ticker", "motivo_entrada", "notas"):
        df[c] = df[c].fillna("").astype(str)
    return df


def guardar(df: pd.DataFrame) -> int:
    df = df.copy()
    df = df[df["ticker"].fillna("").astype(str).str.strip() != ""]
    RUTA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(RUTA, index=False)
    return len(df)


def resultados(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    cerradas = d["precio_salida"].notna() & d["precio_entrada"].gt(0) & d["importe_eur"].gt(0)
    d["resultado_eur"] = (d["importe_eur"] * (d["precio_salida"] / d["precio_entrada"] - 1)
                          - d["comisiones_eur"].fillna(0)).where(cerradas)
    d["resultado_pct"] = (d["resultado_eur"] / d["importe_eur"]).where(cerradas)
    riesgo = (d["precio_entrada"] - d["stop_loss"]) / d["precio_entrada"]
    d["R"] = (d["resultado_pct"] / riesgo).where(cerradas & riesgo.gt(0))
    return d


def estadisticas(d: pd.DataFrame) -> dict:
    c = d.dropna(subset=["resultado_eur"])
    if c.empty:
        return {"cerradas": 0, "abiertas": int(d["precio_salida"].isna().sum())}
    return {
        "cerradas": len(c), "abiertas": int(d["precio_salida"].isna().sum()),
        "acierto": float((c["resultado_eur"] > 0).mean()), "total_eur": float(c["resultado_eur"].sum()),
        "media_eur": float(c["resultado_eur"].mean()),
        "media_R": float(c["R"].mean()) if c["R"].notna().any() else float("nan"),
        "respeto_sl": float((c["precio_salida"] >= c["stop_loss"] * 0.97).mean()) if c["stop_loss"].notna().any() else float("nan"),
    }
