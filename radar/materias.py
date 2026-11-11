"""Materias primas: precios, quién las produce (y cómo va la economía de esos países) y empresas expuestas.

Cuotas de producción: aproximadas, de fuentes públicas (USGS, IEA, FAO, EIA; datos 2023-2024). Sirven para hacerse una
idea de qué países mueven cada mercado, no como cifra exacta.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# nombre: (ticker Yahoo, unidad, categoría, productores [(iso3, % aprox.)], empresas)
MATERIAS = {
    "Petróleo Brent": ("BZ=F", "$/barril", "Energía",
                       [("USA", 20), ("SAU", 11), ("RUS", 11), ("CAN", 6), ("IRQ", 5), ("CHN", 5), ("ARE", 4), ("BRA", 4), ("IRN", 4), ("KWT", 3)],
                       ["XOM", "CVX", "SHEL.L", "BP.L", "TTE.PA", "REP.MC", "2222.SR"]),
    "Petróleo WTI": ("CL=F", "$/barril", "Energía", [("USA", 20), ("SAU", 11), ("RUS", 11), ("CAN", 6)], ["XOM", "CVX", "COP", "OXY"]),
    "Gas natural EE. UU.": ("NG=F", "$/MMBtu", "Energía",
                            [("USA", 25), ("RUS", 15), ("IRN", 6), ("CHN", 6), ("CAN", 5), ("QAT", 4), ("AUS", 4), ("NOR", 3)],
                            ["LNG", "EQT", "XOM", "SHEL.L"]),
    "Gas TTF (Europa)": ("TTF=F", "€/MWh", "Energía", [("NOR", 30), ("USA", 20), ("QAT", 10), ("DZA", 10), ("RUS", 8)],
                         ["EQNR.OL", "ENG.MC", "NTGY.MC", "ENGI.PA"]),
    "Oro": ("GC=F", "$/onza", "Metales preciosos",
            [("CHN", 10), ("RUS", 9), ("AUS", 9), ("CAN", 6), ("USA", 5), ("GHA", 4), ("KAZ", 4), ("MEX", 4), ("UZB", 3), ("PER", 3)],
            ["NEM", "B", "AEM", "GDX"]),
    "Plata": ("SI=F", "$/onza", "Metales preciosos", [("MEX", 24), ("CHN", 13), ("PER", 13), ("BOL", 5), ("CHL", 5), ("POL", 5), ("RUS", 5)],
              ["PAAS", "FRES.L", "SIL"]),
    "Platino": ("PL=F", "$/onza", "Metales preciosos", [("ZAF", 70), ("RUS", 11), ("ZWE", 9), ("CAN", 2), ("USA", 2)], ["SBSW", "PPLT"]),
    "Paladio": ("PA=F", "$/onza", "Metales preciosos", [("RUS", 40), ("ZAF", 35), ("CAN", 8), ("USA", 7), ("ZWE", 6)], ["SBSW", "PALL"]),
    "Cobre": ("HG=F", "$/libra", "Metales industriales",
              [("CHL", 23), ("COD", 13), ("PER", 11), ("CHN", 8), ("USA", 5), ("IDN", 5), ("RUS", 4), ("AUS", 4), ("ZMB", 3), ("MEX", 3)],
              ["FCX", "SCCO", "BHP", "TECK", "ATYM.L"]),
    "Aluminio": ("ALI=F", "$/tonelada", "Metales industriales", [("CHN", 59), ("IND", 6), ("RUS", 5), ("CAN", 4), ("ARE", 4), ("BHR", 2), ("AUS", 2), ("NOR", 2)],
                 ["AA", "NHY.OL", "RIO"]),
    "Litio (ETF LIT)": ("LIT", "$ (ETF)", "Metales de la transición", [("AUS", 37), ("CHL", 24), ("CHN", 18), ("ARG", 5), ("BRA", 3), ("ZWE", 3)],
                        ["ALB", "SQM", "PLS.AX"]),
    "Uranio (ETF URA)": ("URA", "$ (ETF)", "Metales de la transición", [("KAZ", 43), ("CAN", 15), ("NAM", 11), ("AUS", 9), ("UZB", 7), ("RUS", 5), ("NER", 4)],
                         ["CCJ", "KAP.L", "NXE"]),
    "Trigo": ("ZW=F", "centavos $/bushel", "Agrícolas", [("CHN", 17), ("IND", 14), ("RUS", 11), ("USA", 6), ("CAN", 4), ("FRA", 4), ("UKR", 3), ("AUS", 3)],
              ["ADM", "BG"]),
    "Maíz": ("ZC=F", "centavos $/bushel", "Agrícolas", [("USA", 31), ("CHN", 23), ("BRA", 10), ("ARG", 5), ("UKR", 3), ("IND", 3)], ["ADM", "BG", "CTVA"]),
    "Soja": ("ZS=F", "centavos $/bushel", "Agrícolas", [("BRA", 40), ("USA", 28), ("ARG", 12), ("CHN", 5), ("IND", 3)], ["ADM", "BG"]),
    "Café": ("KC=F", "centavos $/libra", "Agrícolas", [("BRA", 35), ("VNM", 17), ("COL", 7), ("IDN", 6), ("ETH", 5), ("HND", 3)], ["SBUX", "NESN.SW"]),
    "Cacao": ("CC=F", "$/tonelada", "Agrícolas", [("CIV", 40), ("GHA", 15), ("ECU", 7), ("CMR", 6), ("NGA", 5), ("IDN", 4), ("BRA", 3)],
              ["HSY", "MDLZ", "BARN.SW"]),
    "Azúcar": ("SB=F", "centavos $/libra", "Agrícolas", [("BRA", 23), ("IND", 19), ("THA", 6), ("CHN", 5), ("USA", 4), ("PAK", 4)], ["EBRO.MC"]),
}


def tabla_precios(cierres: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for nombre, (t, unidad, cat, _, _) in MATERIAS.items():
        if t not in cierres:
            continue
        x = cierres[t].dropna()
        if len(x) < 25:
            continue
        previos = x[x.index.year < x.index[-1].year]
        base = float(previos.iloc[-1]) if len(previos) else float(x.iloc[0])
        filas.append({"Materia prima": nombre, "Categoría": cat, "Precio": float(x.iloc[-1]), "Unidad": unidad,
                      "1 día": float(x.iloc[-1] / x.iloc[-2] - 1), "1 mes": float(x.iloc[-1] / x.iloc[-22] - 1),
                      "En el año": float(x.iloc[-1] / base - 1), "Fecha": x.index[-1].strftime("%d/%m")})
    return pd.DataFrame(filas)


def productores(nombre: str, economia: pd.DataFrame | None = None) -> pd.DataFrame:
    df = pd.DataFrame(MATERIAS[nombre][3], columns=["iso3", "cuota"])
    if economia is not None and not economia.empty:
        df = df.merge(economia[["iso3", "pais", "crecimiento", "inflacion"]], on="iso3", how="left")
    else:
        df["pais"], df["crecimiento"], df["inflacion"] = df["iso3"], np.nan, np.nan
    df["pais"] = df["pais"].fillna(df["iso3"])
    return df


def concentracion(nombre: str) -> tuple[float, str]:
    """Cuota de los 3 primeros productores y lectura del riesgo de suministro."""
    cuotas = sorted((c for _, c in MATERIAS[nombre][3]), reverse=True)
    top3 = float(sum(cuotas[:3]))
    lectura = ("muy concentrada: un problema en un solo país mueve mucho el precio" if top3 >= 60 else
               "bastante concentrada" if top3 >= 40 else "repartida entre muchos países")
    return top3, lectura
