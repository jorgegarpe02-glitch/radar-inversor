"""Pantalla 🪙 Cripto: precios de las mayores criptomonedas y análisis por reglas de la que elijas."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from . import cripto
from .vistas import AMBAR, AZUL, CSS, NEUTRO, ROJO, VERDE, cambio_a_euros, html

_COLOR = {"verde": VERDE, "amarillo": AMBAR, "rojo": ROJO, "gris": NEUTRO}


def _miles(x: float, dec: int = 0) -> str:
    return f"{x:,.{dec}f}".replace(",", "·").replace(".", ",").replace("·", ".")


def _precio(x, simbolo: str = "$") -> str:
    """Precio legible tanto para 73.000 como para 0,0000123."""
    if x is None or pd.isna(x):
        return "—"
    dec = 0 if x >= 1000 else 2 if x >= 1 else 4 if x >= 0.01 else 8
    return f"{_miles(x, dec)} {simbolo}"


def _grande(x) -> str:
    if x is None or pd.isna(x):
        return "—"
    for corte, nombre in ((1e12, "billones"), (1e9, "mil M"), (1e6, "M")):
        if x >= corte:
            return f"{_miles(x / corte, 2 if corte == 1e12 else 1)} {nombre} $"
    return f"{_miles(x)} $"


def _pct(x, signo: bool = True) -> str:
    if x is None or pd.isna(x):
        return "—"
    return (f"{x * 100:+.1f} %" if signo else f"{x * 100:.1f} %").replace(".", ",")


def _grafico(s: pd.Series, nombre: str, periodo: str) -> go.Figure:
    dias = {"3 meses": 92, "1 año": 366, "4 años": 1461, "Todo": len(s)}[periodo]
    v = s.tail(dias)
    fig = go.Figure(go.Scatter(x=v.index, y=v.values, mode="lines", name=nombre, line=dict(color=AZUL, width=2),
                               hovertemplate="%{x|%d/%m/%Y}: %{y:,.4g} $<extra></extra>"))
    for n, color, etiqueta in ((50, AMBAR, "Media 50 días"), (200, NEUTRO, "Media 200 días")):
        if len(s) >= n + 5:
            mm = s.rolling(n).mean().tail(dias)
            fig.add_trace(go.Scatter(x=mm.index, y=mm.values, mode="lines", name=etiqueta, line=dict(color=color, width=1.2, dash="dot"),
                                     hoverinfo="skip"))
    fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=1.08, x=0),
                      yaxis=dict(type="log" if periodo in ("4 años", "Todo") else "linear", title=None, gridcolor="rgba(137,135,129,.2)"),
                      xaxis=dict(title=None, showgrid=False), hovermode="x unified")
    return fig


def pantalla_cripto() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    st.caption("Precios de las 100 mayores criptomonedas y un análisis automático de la que elijas. Una criptomoneda no tiene ventas ni "
               "beneficios, así que aquí no hay «valor razonable»: el análisis mira si es sólida, en qué momento está y cuánto puede caer.")
    with st.spinner("Cargando precios de criptomonedas…"):
        df = cripto.mercado(100)
        pan = cripto.panorama()
    if df.empty:
        st.warning("No he podido cargar los precios (CoinGecko no responde o ha limitado las consultas). Espera un minuto y pulsa «Actualizar».")
        if st.button("🔄 Actualizar", key="cripto_reintentar"):
            st.rerun()
        return
    a_eur = cambio_a_euros("USD")
    cic = cripto.ciclo_bitcoin()

    # --- cómo está el mercado
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Valor de todo el mercado", _grande(pan.get("cap_total")), _pct(pan.get("cambio_24h")) + " hoy" if pan.get("cambio_24h") is not None else None)
    c2.metric("Peso de bitcoin", _pct(pan.get("peso_btc"), False) if pan.get("peso_btc") else "—",
              help="Qué parte de todo el dinero metido en criptomonedas está en bitcoin. Cuando sube, el dinero huye de las monedas pequeñas.")
    c3.metric("Miedo y codicia", f"{pan['miedo']}/100 · {cripto.nombre_miedo(pan['miedo'])}" if pan.get("miedo") is not None else "—",
              f"{pan['miedo'] - pan['miedo_hace_7']:+d} en 7 días" if pan.get("miedo") is not None else None,
              help="Índice de alternative.me. 0 = pánico total, 100 = euforia. Mide volatilidad, volumen, redes sociales y búsquedas.")
    c4.metric("Ciclo de bitcoin", f"{cic['meses']:.0f} meses", f"próximo recorte ≈ {cic['proximo'].strftime('%m/%Y')}", delta_color="off",
              help="Meses desde el último «halving» (cada 4 años se reduce a la mitad la emisión de bitcoins nuevos).")
    st.info(cripto.lectura_mercado(pan, cic))

    # --- tabla de precios
    st.subheader("Precios")
    f1, f2 = st.columns([2, 1])
    ver = f1.radio("Mostrar", ["Las que se pueden analizar", "Todas"], horizontal=True, key="cripto_ver",
                   help="«Las que se pueden analizar» quita las monedas estables (valen siempre 1 dólar), el oro digital y las copias de otras monedas.")
    cuantas = f2.select_slider("Cuántas", [10, 25, 50, 100], value=25, key="cripto_n")
    tabla = df if ver == "Todas" else df[~df["tipo"].isin(["estable", "oro", "copia"])]
    tabla = tabla.head(cuantas)
    vista = pd.DataFrame({
        "#": tabla["puesto"], "Moneda": tabla["nombre"] + " (" + tabla["simbolo"] + ")",
        "Tipo": tabla["tipo"].map(lambda t: cripto.TIPOS[t][0]),
        "Precio ($)": tabla["precio"], "Precio (€)": tabla["precio"] * a_eur if a_eur else None,
        "24 h": tabla["cambio_24h"], "7 días": tabla["cambio_7d"], "30 días": tabla["cambio_30d"], "1 año": tabla["cambio_1a"],
        "Desde su máximo": tabla["desde_maximo"], "Valor total (mil M $)": tabla["cap"] / 1e9})

    def color(v):
        if v is None or pd.isna(v):
            return ""
        return f"color: {VERDE}" if v > 0 else f"color: {ROJO}" if v < 0 else ""

    def fmt_precio(v):
        return "—" if v is None or pd.isna(v) else _precio(v, "").strip()

    cols_pct = ["24 h", "7 días", "30 días", "1 año", "Desde su máximo"]
    estilo = (vista.style.map(color, subset=cols_pct[:4])
              .format({**{c: lambda v: _pct(v) for c in cols_pct}, "Precio ($)": fmt_precio, "Precio (€)": fmt_precio,
                       "Valor total (mil M $)": lambda v: "—" if pd.isna(v) else _miles(v, 1)}))
    st.dataframe(estilo, hide_index=True, width="stretch", height=min(38 * (len(vista) + 1), 520))
    st.caption("Precios en tiempo casi real (CoinGecko, se refrescan cada 5 minutos). Las criptomonedas cotizan 24 horas, fines de semana incluidos.")

    # --- análisis de una
    st.subheader("Análisis de una criptomoneda")
    opciones = df["id"].tolist()
    nombres = {r["id"]: f"{r['nombre']} ({r['simbolo']})" for _, r in df.iterrows()}
    elegida = st.selectbox("Elige o escribe el nombre", opciones, format_func=lambda i: nombres[i], key="cripto_id",
                           help="Puedes escribir para buscar: Bitcoin, Ethereum, Solana, XRP, Dogecoin…")
    f = df[df["id"] == elegida].iloc[0].to_dict()
    with st.spinner(f"Analizando {f['nombre']}…"):
        s = cripto.historial(f["id"], f["simbolo"], f["precio"])
        btc_f = df[df["id"] == "bitcoin"]
        btc = s if elegida == "bitcoin" else (cripto.historial("bitcoin", "BTC", float(btc_f["precio"].iloc[0])) if len(btc_f) else None)
        a = cripto.completo(f, s, btc, pan)
    rec, sol, med = a["recomendacion"], a["solidez"], a["medidas"]

    c1, c2, c3, c4 = st.columns([2.2, 1, 1, 1])
    icono, _, titulo = rec["etiqueta"].partition(" ")
    c1.markdown(f"<div class='ri-box' style='--c:{_COLOR[rec['color']]};margin:0'><div class='t'>{icono} {html(titulo)}</div>"
                f"<div>{html(f['nombre'])} · {_precio(f['precio'])}" + (f" (≈ {_precio(f['precio'] * a_eur, '€')})" if a_eur else "")
                + f" · {html(cripto.TIPOS[f['tipo']][0].lower())}</div></div>", unsafe_allow_html=True)
    c2.metric("Solidez", f"{str(sol['puntos']).replace('.', ',')}/10", sol["etiqueta"], delta_color="off",
              help="Si es de las que aguantan (tamaño, años, liquidez, oferta y utilidad). No dice si va a subir.")
    c3.metric("Desde su máximo", _pct(f.get("desde_maximo")), f"máximo {_precio(f.get('maximo'))}", delta_color="off")
    c4.metric("Peso máximo orientativo", rec["peso"] if rec.get("peso") and "%" in rec["peso"] else "—",
              help="Qué parte de tus ahorros invertidos tendría sentido como mucho. Es una referencia general, no un consejo personal.")
    st.caption("Análisis generado con reglas automáticas sobre datos públicos (no lo escribe una persona ni una IA). No es asesoramiento financiero.")
    st.markdown(f"**En pocas palabras.** {a['resumen']}")
    st.markdown(rec["texto"] + (" " + rec["como"] if rec.get("como") else ""))

    if len(s) > 30:
        periodos = [p for p, d in (("3 meses", 0), ("1 año", 120), ("4 años", 500), ("Todo", 1500)) if len(s) > d]
        periodo = st.radio("Periodo del gráfico", periodos, index=min(1, len(periodos) - 1), horizontal=True, key="cripto_periodo")
        st.plotly_chart(_grafico(s, f["nombre"], periodo), width="stretch", key="cripto_grafico")
        if periodo in ("4 años", "Todo"):
            st.caption("Escala logarítmica: la misma distancia vertical es el mismo porcentaje de subida o bajada.")
    else:
        st.caption("No hay histórico suficiente para dibujar el gráfico de esta moneda.")

    if f["tipo"] in ("estable", "oro", "copia"):
        return

    st.markdown("**Veredicto por plazos**")
    cols = st.columns(3)
    for col, p in zip(cols, a["plazos"]):
        col.markdown(f"<div class='ri-esc' style='--c:{_COLOR[p['color']]}'><div class='s'>{html(p['plazo'])} · {html(p['cuanto'])}</div>"
                     f"<div class='p'>{html(p['veredicto'])}</div><div class='s' style='margin-top:4px'>{html(p['porque'])}</div></div>",
                     unsafe_allow_html=True)

    izq, der = st.columns(2)
    with izq:
        st.markdown(f"**Solidez: {str(sol['puntos']).replace('.', ',')}/10 ({sol['etiqueta'].lower()})**")
        for texto, puntos, maximo in sol["notas"]:
            icono = "🟢" if puntos >= maximo * 0.75 else "🟡" if puntos >= maximo * 0.35 else "🔴"
            st.markdown(f"{icono} {texto} — {str(round(puntos, 1)).replace('.', ',')} de {str(maximo).replace('.', ',')}")
        st.markdown("**Datos**")
        datos = [("Valor total en circulación", _grande(f.get("cap"))),
                 ("Volumen negociado en 24 h", _grande(f.get("volumen"))),
                 ("Monedas en circulación", _miles(f["circulante"]) if f.get("circulante") else "—"),
                 ("Tope máximo de monedas", _miles(f["oferta_max"]) if f.get("oferta_max") else "no tiene"),
                 ("Volatilidad anual", _pct(med.get("vol"), False)),
                 ("Fuerza (RSI 14 días)", f"{med['rsi']:.0f}" if med.get("rsi") is not None else "—"),
                 ("Media de 200 días", _precio(med.get("mm200"))),
                 ("Mayor caída desde un máximo", _pct(med.get("caida_max")))]
        st.dataframe(pd.DataFrame(datos, columns=["Dato", "Valor"]), hide_index=True, width="stretch")
    with der:
        r = a["rangos"]
        if r:
            st.markdown("**Hasta dónde puede moverse en 12 meses**")
            st.markdown(f"- 🟢 Si sale bien: hacia **{_precio(r['alto'])}** ({_pct(r['alto'] / f['precio'] - 1)})\n"
                        f"- 🔴 Si sale mal: hacia **{_precio(r['bajo'])}** ({_pct(r['bajo'] / f['precio'] - 1)})"
                        + (f"\n- ⚫ Si repitiera su peor caída ({_pct(r['caida_max'])}): **{_precio(r['desastre'])}**" if r.get("desastre") else ""))
            st.caption("No es una predicción: es el rango que sale de lo que se ha movido hasta ahora, sin suponer que vaya a subir ni a bajar. "
                       "Aproximadamente dos de cada tres años acaba dentro de ese rango; uno de cada tres, fuera.")
        st.markdown("**Riesgos**")
        for grave, texto in a["riesgos"]:
            st.markdown(f"{'🔴' if grave == 'alto' else '🟡'} {texto}")
        if elegida == "bitcoin" or f["tipo"] != "reserva":
            st.markdown("**Ciclo de bitcoin**")
            st.markdown(f"Han pasado {cic['meses']:.0f} meses desde el último recorte de emisión. Estamos en el {cic['texto']}. "
                        + ("" if elegida == "bitcoin" else "Casi todas las demás monedas siguen a bitcoin, con movimientos más bruscos. ")
                        + "Solo hay tres ciclos anteriores: es una pauta, no una garantía.")
    st.caption(f"Fuentes: {cripto.FUENTE}.")
