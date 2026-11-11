"""Figuras de Plotly para la interfaz."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

COLORES = {"alcista": "#2a9d8f", "mixto": "#577590", "bajista": "#e76f51"}
NOMBRES = {"alcista": "Mercado alcista", "mixto": "Histórico completo", "bajista": "Mercado bajista"}


def _hex_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def fig_precio(h: pd.DataFrame, titulo: str = "") -> go.Figure:
    c = h["Close"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=h.index, y=c, name="Precio", line=dict(width=2)))
    for ventana, color in ((50, "#f4a261"), (200, "#9b5de5")):
        if len(c) > ventana:
            fig.add_trace(
                go.Scatter(x=h.index, y=c.rolling(ventana).mean(), name=f"Media {ventana}d",
                           line=dict(width=1, dash="dot", color=color))
            )
    fig.update_layout(title=titulo, height=380, margin=dict(l=10, r=10, t=40, b=10), hovermode="x unified",
                      legend=dict(orientation="h", y=-0.15))
    return fig


def fig_abanico(res: dict, objetivos_analistas: dict | None = None) -> go.Figure:
    """Mediana y banda P10–P90 de cada escenario desde hoy hasta el horizonte."""
    dias = res["dias"]
    x = list(range(0, dias + 1))
    fig = go.Figure()
    for clave in ("alcista", "mixto", "bajista"):
        b = res["escenarios"][clave]["bandas"]
        p10 = np.concatenate([[res["precio0"]], b["p10"]])
        p50 = np.concatenate([[res["precio0"]], b["p50"]])
        p90 = np.concatenate([[res["precio0"]], b["p90"]])
        color = COLORES[clave]
        fig.add_trace(go.Scatter(x=x, y=p90, line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=x, y=p10, fill="tonexty", fillcolor=_hex_rgba(color, 0.15),
                                 line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=x, y=p50, name=NOMBRES[clave], line=dict(color=color, width=2.5)))
    fig.add_hline(y=res["precio0"], line_dash="dot", line_color="gray", annotation_text="Precio actual")
    for etiqueta, valor in (objetivos_analistas or {}).items():
        if valor:
            fig.add_hline(y=valor, line_dash="dash", line_color="#adb5bd", annotation_text=etiqueta,
                          annotation_position="top left")
    fig.update_layout(xaxis_title="Días de mercado desde hoy", yaxis_title="Precio", height=430,
                      margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified",
                      legend=dict(orientation="h", y=-0.2))
    return fig


def fig_grafo(G, niveles: dict, centro: str) -> go.Figure:
    """Proveedores a la izquierda, la empresa en el centro, clientes a la derecha."""
    por_nivel: dict[int, list] = {}
    for nodo, n in niveles.items():
        por_nivel.setdefault(n, []).append(nodo)
    pos = {}
    for n, nodos in por_nivel.items():
        for i, nodo in enumerate(sorted(nodos)):
            pos[nodo] = (n, (len(nodos) - 1) / 2 - i)
    fig = go.Figure()
    for a, b, datos in G.edges(data=True):
        fig.add_annotation(x=pos[b][0], y=pos[b][1], ax=pos[a][0], ay=pos[a][1], xref="x", yref="y", axref="x",
                           ayref="y", showarrow=True, arrowhead=3, arrowsize=1.2, arrowwidth=1.2, arrowcolor="#8d99ae",
                           standoff=14, startstandoff=14)
        fig.add_trace(go.Scatter(x=[(pos[a][0] + pos[b][0]) / 2], y=[(pos[a][1] + pos[b][1]) / 2], mode="markers",
                                 marker=dict(size=14, opacity=0), hovertext=datos.get("producto") or "(sin detalle)",
                                 hoverinfo="text", showlegend=False))
    colores = ["#e76f51" if niveles[n] < 0 else "#577590" if niveles[n] == 0 else "#2a9d8f" for n in pos]
    fig.add_trace(go.Scatter(x=[pos[n][0] for n in pos], y=[pos[n][1] for n in pos], mode="markers+text",
                             text=list(pos), textposition="top center",
                             marker=dict(size=[26 if n == centro else 16 for n in pos], color=colores),
                             hoverinfo="text", showlegend=False))
    xs = [p[0] for p in pos.values()]
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10),
                      xaxis=dict(visible=False, range=[min(xs) - 0.8, max(xs) + 0.8]), yaxis=dict(visible=False))
    return fig


COLOR_FUENTE = {"Base precargada": "#8d99ae", "Tu tabla": "#3a86ff", "Su informe anual (SEC)": "#f4a261",
                "Informes SEC (automático)": "#9b5de5"}


def fig_conexiones(G, niveles: dict, centro: str, tickers: dict | None = None) -> go.Figure:
    """Mapa de proveedores (izquierda) → empresa → clientes (derecha). Cada nodo se puede pinchar."""
    tickers = tickers or {}
    por_nivel: dict[int, list] = {}
    for nodo, n in niveles.items():
        por_nivel.setdefault(n, []).append(nodo)
    pos = {}
    for n, nodos in por_nivel.items():
        for i, nodo in enumerate(sorted(nodos, key=str.lower)):
            pos[nodo] = (n * 1.6, (len(nodos) - 1) / 2 - i)
    fig = go.Figure()
    vistos = set()
    for a, b, d in G.edges(data=True):
        fuente = d.get("fuente", "")
        color = COLOR_FUENTE.get(fuente, "#8d99ae")
        fig.add_trace(go.Scatter(x=[pos[a][0], pos[b][0]], y=[pos[a][1], pos[b][1]], mode="lines",
                                 line=dict(color=color, width=1.4, dash="dot" if fuente.startswith("Informes") else "solid"),
                                 hoverinfo="skip", name=fuente, legendgroup=fuente, showlegend=fuente not in vistos))
        vistos.add(fuente)
        fig.add_trace(go.Scatter(x=[(pos[a][0] * 0.35 + pos[b][0] * 0.65)], y=[(pos[a][1] * 0.35 + pos[b][1] * 0.65)],
                                 mode="markers", marker=dict(symbol="triangle-right", size=8, color=color),
                                 hovertext=f"{a} → {b}<br>{(d.get('que') or '')[:120]}<br><i>{fuente}</i>",
                                 hoverinfo="text", showlegend=False))
    nodos = list(pos)
    colores = ["#e76f51" if niveles[n] < 0 else "#264653" if niveles[n] == 0 else "#2a9d8f" for n in nodos]
    etiquetas = [f"{n} ({tickers[n]})" if tickers.get(n) else n for n in nodos]
    fig.add_trace(go.Scatter(
        x=[pos[n][0] for n in nodos], y=[pos[n][1] for n in nodos], mode="markers+text", text=etiquetas,
        textposition=["middle left" if niveles[n] < 0 else "middle right" if niveles[n] > 0 else "top center" for n in nodos],
        customdata=nodos, marker=dict(size=[28 if n == centro else 15 for n in nodos], color=colores,
                                      line=dict(width=1, color="white")),
        hovertext=[f"<b>{n}</b><br>{'Proveedor' if niveles[n] < 0 else 'Cliente' if niveles[n] > 0 else 'Empresa analizada'}"
                   f"<br>Pincha para ver sus conexiones" for n in nodos],
        hoverinfo="text", showlegend=False, name="empresas"))
    alto = max(len(v) for v in por_nivel.values())
    xs = [p[0] for p in pos.values()]
    fig.update_layout(height=max(420, 34 * alto + 80), margin=dict(l=10, r=10, t=30, b=10), clickmode="event+select",
                      xaxis=dict(visible=False, range=[min(xs) - 1.6, max(xs) + 1.6]), yaxis=dict(visible=False),
                      legend=dict(orientation="h", y=1.05, x=0), dragmode=False,
                      annotations=[dict(x=min(xs) if min(xs) < 0 else -1.6, y=(alto - 1) / 2 + 0.9, text="⬅ LE VENDEN (proveedores)",
                                        showarrow=False, font=dict(color="#e76f51")),
                                   dict(x=max(xs) if max(xs) > 0 else 1.6, y=(alto - 1) / 2 + 0.9, text="LE COMPRAN (clientes) ➡",
                                        showarrow=False, font=dict(color="#2a9d8f"))])
    return fig


def fig_mapa(df: pd.DataFrame, color_por: str = "fuente", zoom: float = 4.0) -> go.Figure:
    fig = go.Figure()
    for valor, g in df.groupby(color_por):
        tam = g["potencia_mw"].fillna(0).clip(lower=0)
        tamanos = 7 + 18 * np.sqrt(tam / max(tam.max(), 1)) if tam.max() > 0 else np.full(len(g), 9)
        fig.add_trace(go.Scattermap(lat=g["lat"], lon=g["lon"], mode="markers", name=str(valor or "(n/d)"),
                                    marker=dict(size=tamanos, opacity=0.75),
                                    text=g["nombre"] + "<br>" + g["operador"].fillna("") + "<br>"
                                    + g["potencia_mw"].map(lambda x: f"{x:,.0f} MW" if pd.notna(x) else ""),
                                    hoverinfo="text"))
    fig.update_layout(map=dict(style="open-street-map", center=dict(lat=float(df["lat"].mean()), lon=float(df["lon"].mean())),
                               zoom=zoom), height=520, margin=dict(l=0, r=0, t=0, b=0))
    return fig


def fig_estrechos_mapa(df: pd.DataFrame, valores: pd.Series, titulo: str) -> go.Figure:
    tam = 10 + 30 * (valores / max(valores.max(), 1))
    fig = go.Figure(go.Scattermap(lat=df["lat"], lon=df["lon"], mode="markers+text", text=df["nombre_es"],
                                  textposition="top right", marker=dict(size=tam, color="#e76f51", opacity=0.8),
                                  hovertext=[f"{n}: {v:.0f} {titulo}" for n, v in zip(df["nombre_es"], valores)],
                                  hoverinfo="text"))
    fig.update_layout(map=dict(style="open-street-map", center=dict(lat=20, lon=40), zoom=1.2), height=430,
                      margin=dict(l=0, r=0, t=0, b=0))
    return fig


def fig_pasos(df: pd.DataFrame, columna: str, titulo: str) -> go.Figure:
    fig = go.Figure()
    for nombre, g in df.sort_values("fecha").groupby("estrecho"):
        fig.add_trace(go.Scatter(x=g["fecha"], y=g[columna].rolling(7, min_periods=3).mean(), name=nombre))
    fig.update_layout(title=titulo, height=380, margin=dict(l=10, r=10, t=40, b=10), hovermode="x unified",
                      legend=dict(orientation="h", y=-0.2))
    return fig


# ----------------------------------------------------------------------------- mapa mundial
ESTILO_CAPA = {  # prefijo de capa → (color, símbolo)
    "Minas de oro": ("#b8860b", "diamond"), "Minas de cobre": ("#a0522d", "diamond"), "Minas de hierro": ("#6d6875", "diamond"),
    "Minas de litio": ("#90e0ef", "diamond"), "Minas de uranio": ("#80ed99", "diamond"), "Minas de plata": ("#adb5bd", "diamond"),
    "Minas de carbón": ("#343a40", "diamond"), "Minas de": ("#b5838d", "diamond"),
    "Centrales: nuclear": ("#7b2cbf", "circle"), "Centrales: carbón": ("#495057", "circle"), "Centrales: gas": ("#f77f00", "circle"),
    "Centrales: petróleo": ("#6f1d1b", "circle"), "Centrales: hidroeléctrica": ("#0077b6", "circle"),
    "Centrales: solar": ("#fcbf49", "circle"), "Centrales: eólica": ("#48cae4", "circle"), "Centrales:": ("#8d99ae", "circle"),
    "Refinerías": ("#d62828", "square"), "Terminales de GNL (exportación)": ("#7209b7", "triangle-up"),
    "Terminales de GNL (importación)": ("#b5179e", "triangle-down"), "Petroleros: escalas": ("#023e8a", "circle"),
    "Petroleros: tránsito": ("#e63946", "star"), "Alertas": ("#ff006e", "x"), "Buques en directo": ("#2a9d8f", "circle"),
}


def _estilo(capa: str):
    for prefijo, v in ESTILO_CAPA.items():
        if capa.startswith(prefijo):
            return v
    return ("#8d99ae", "circle")


def fig_mundo(capas: dict, coropleta: pd.DataFrame | None = None, modo_color: str = "", rutas=None,
              globo: bool = True, centro: tuple | None = None, alto: int = 680) -> go.Figure:
    """capas: {nombre: DataFrame con lat, lon, texto y opcional tam}. coropleta: iso3, valor, texto."""
    fig = go.Figure()
    if coropleta is not None and not coropleta.empty:
        if modo_color == "semaforo":
            fig.add_trace(go.Choropleth(
                locations=coropleta["iso3"], z=coropleta["valor"], text=coropleta["texto"], hoverinfo="text",
                colorscale=[[0, "#e63946"], [0.5, "#ffd166"], [1, "#2a9d8f"]], zmin=-1, zmax=1, showscale=False,
                marker_line_color="white", marker_line_width=0.4, name="países"))
        else:
            fig.add_trace(go.Choropleth(
                locations=coropleta["iso3"], z=coropleta["valor"], text=coropleta["texto"], hoverinfo="text",
                colorscale=modo_color or "RdYlGn", reversescale=False, marker_line_color="white", marker_line_width=0.4,
                colorbar=dict(thickness=10, len=0.5, x=0.0, title=""), name="países",
                zmid=0 if (coropleta["valor"].min() < 0 < coropleta["valor"].max()) else None))
    if rutas is not None and rutas[0]:
        fig.add_trace(go.Scattergeo(lat=rutas[0], lon=rutas[1], mode="lines", line=dict(width=0.8, color="#4361ee"),
                                    opacity=0.45, hoverinfo="skip", name="Rutas marítimas principales"))
    for nombre, df in capas.items():
        if df is None or df.empty:
            continue
        color, simbolo = _estilo(nombre)
        if "size" in df:
            tam = df["size"]
        elif "tam" in df and df["tam"].notna().any():
            t = df["tam"].fillna(0).clip(lower=0)
            tam = 5 + 22 * np.sqrt(t / max(t.max(), 1e-9))
        else:
            tam = 8
        fig.add_trace(go.Scattergeo(
            lat=df["lat"], lon=df["lon"], mode="markers", name=f"{nombre} ({len(df)})", text=df["texto"], hoverinfo="text",
            marker=dict(size=tam, color=df["color"] if "color" in df else color, symbol=simbolo, opacity=0.9,
                        line=dict(width=1 if simbolo != "circle" else 0.5, color="#212529" if simbolo != "circle" else "white"))))
    geo = dict(showland=True, landcolor="#2c2c2a", showocean=True, oceancolor="#10202f", showcountries=True,
               countrycolor="#6b6a65", showcoastlines=True, coastlinecolor="#6b6a65", showlakes=False,
               projection_type="orthographic" if globo else "natural earth", bgcolor="rgba(0,0,0,0)")
    if globo:
        lat0, lon0 = centro or (25, 10)
        geo["projection_rotation"] = dict(lat=lat0, lon=lon0)
    elif centro:
        geo["center"] = dict(lat=centro[0], lon=centro[1])
    fig.update_layout(geo=geo, height=alto, margin=dict(l=0, r=0, t=0, b=0), legend=dict(orientation="h", y=-0.02, x=0),
                      uirevision="mapa")
    return fig
