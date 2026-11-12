"""Pantalla 🪙 Cripto: precios de las mayores criptomonedas y análisis por reglas de la que elijas."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from . import cripto, plan
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


# ============================================================================= 📅 PLAN MENSUAL
def _eur(x) -> str:
    return "—" if x is None or pd.isna(x) else f"{_miles(x)} €"


def _tabla_reparto(rep: list[dict], con_tengo: bool, clave: str) -> None:
    datos = {"Activo": [r["nombre"] or r["escrito"] for r in rep], "Para qué sirve": [plan.ROLES[r["rol"]][0] for r in rep],
             "Qué hacer": [plan.accion_texto(r) for r in rep]}
    if con_tengo:
        datos["Ya tengo (€)"] = [r.get("tengo") or 0 for r in rep]
    datos.update({"Al mes ahora (€)": [r["euros"] for r in rep], "Al mes sugerido (€)": [r["sugerido"] for r in rep],
                  "Cambio (€)": [r["cambio"] for r in rep], "Por qué": [r["porque"] for r in rep]})
    tabla = pd.DataFrame(datos)

    def color(x):
        return f"color: {VERDE}" if x > 0.5 else f"color: {ROJO}" if x < -0.5 else f"color: {NEUTRO}"

    formato = {"Al mes ahora (€)": "{:.0f}", "Al mes sugerido (€)": "{:.0f}", "Cambio (€)": "{:+.0f}", "Ya tengo (€)": "{:.0f}"}
    st.dataframe(tabla.style.map(color, subset=["Cambio (€)"]).format({k: f for k, f in formato.items() if k in tabla}),
                 hide_index=True, width="stretch", height=min(38 * (len(tabla) + 1) + 4, 760), key=clave,
                 column_config={"Por qué": st.column_config.TextColumn(width="large")})


def _y_si(act: list[dict], perfil: str) -> None:
    """Probar a añadir o quitar un activo sin tocar el plan guardado."""
    st.subheader("🧪 ¿Y si…?")
    st.caption("Prueba a añadir o quitar un activo y mira cómo cambia el análisis. No modifica tu plan guardado.")
    nombres = [a["nombre"] or a["escrito"] for a in act]
    c1, c2, c3, c4 = st.columns([2, 1, 1, 2])
    nuevo = c1.text_input("Añadir (nombre o ticker)", key="ysi_nuevo", placeholder="Ej.: Microsoft, oro, ETH, VWCE.DE")
    eur = c2.number_input("€ al mes", min_value=0, value=50, step=10, key="ysi_eur")
    tengo = c3.number_input("Ya tengo (€)", min_value=0, value=0, step=100, key="ysi_tengo")
    quitar = c4.multiselect("Quitar", nombres, key="ysi_quitar", placeholder="Elige los que quieras quitar")
    if st.button("Probar", key="ysi_probar"):
        if not nuevo.strip() and not quitar:
            st.session_state.pop("ysi_resultado", None)
            st.warning("Escribe un activo para añadir o elige alguno para quitar.")
        else:
            prueba = [a for a, n in zip(act, nombres) if n not in quitar]
            extra = None
            if nuevo.strip() and (eur > 0 or tengo > 0):
                with st.spinner(f"Analizando {nuevo.strip()}…"):
                    extra = plan.evaluar(nuevo.strip())
                extra["euros"], extra["tengo"] = float(eur), float(tengo)
                prueba.append(extra)
            st.session_state["ysi_resultado"] = {"act": prueba, "extra": extra, "quitados": list(quitar)}
    res = st.session_state.get("ysi_resultado")
    if not res:
        return
    prueba, extra = res["act"], res["extra"]
    if not prueba:
        st.warning("Te quedas sin activos: no hay nada que analizar.")
        return
    antes, despues = plan.resumen(act, perfil), plan.resumen(prueba, perfil)
    cambios = ([f"añadiendo **{extra['nombre'] or extra['escrito']}**"] if extra else []) + ([f"quitando **{', '.join(res['quitados'])}**"] if res["quitados"] else [])
    st.markdown("Resultado " + " y ".join(cambios) + ":")
    if extra:
        st.markdown(f"**{extra['nombre'] or extra['escrito']}** → {plan.ROLES[extra['rol']][0]} · {plan.accion_texto(extra)}. {extra['motivo']}")
    orden = {"🔴": 0, "🟡": 1, "🟢": 2}
    a0, a1 = antes["nota"]["etiqueta"], despues["nota"]["etiqueta"]
    veredicto = "mejora" if orden[a1[0]] > orden[a0[0]] else "empeora" if orden[a1[0]] < orden[a0[0]] else "se queda igual"
    m = st.columns(4)
    m[0].metric("Nota", a1, f"antes: {a0.split(' ', 1)[1].lower()} ({veredicto})", delta_color="off")
    m[1].metric("Parte especulativa", f"{despues['especulativo'] * 100:.0f} %", f"{(despues['especulativo'] - antes['especulativo']) * 100:+.0f} puntos",
                delta_color="inverse")
    m[2].metric(f"Sector mayor: {despues['sector'][0]}", f"{despues['sector'][1] * 100:.0f} %",
                f"antes: {antes['sector'][0]} {antes['sector'][1] * 100:.0f} %", delta_color="off")
    m[3].metric("Parte defensiva", f"{despues['defensivo'] * 100:.0f} %", f"{(despues['defensivo'] - antes['defensivo']) * 100:+.0f} puntos")
    t0, t1 = {x["titulo"] for x in antes["flaquezas"]}, {x["titulo"] for x in despues["flaquezas"]}
    arreglados = [x for x in antes["flaquezas"] if x["titulo"] not in t1 and x["grave"] > 0]
    nuevos = [x for x in despues["flaquezas"] if x["titulo"] not in t0]
    if arreglados:
        st.markdown("✅ **Se arregla:** " + "; ".join(x["titulo"] for x in arreglados) + ".")
    if nuevos:
        st.markdown("⚠️ **Aparece:** " + "; ".join(x["titulo"] for x in nuevos) + ".")
    if not arreglados and not nuevos:
        st.markdown("Los puntos débiles no cambian.")
    rep2, sin2 = plan.reparto(prueba, perfil)
    with st.expander("Reparto sugerido con este cambio"):
        _tabla_reparto(rep2, any((r.get("tengo") or 0) > 0 for r in rep2), "ysi_tabla")
        if sin2 >= 1:
            st.caption(f"Quedarían {_eur(sin2)} al mes sin asignar.")
    st.caption("Si te convence, añádelo o quítalo en la tabla de arriba y pulsa «Analizar cartera».")


def pantalla_plan(abrir_empresa) -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    st.caption("Escribe tus activos (de 2 a 20), lo que ya tienes invertido en cada uno y lo que aportas al mes. Te digo para qué sirve cada "
               "pieza, por dónde flaquea el conjunto, qué conviene pausar y cómo repartiría los mismos euros. Admite acciones, fondos y ETF, "
               "criptomonedas y materias primas.")
    perfiles = list(plan.PERFILES)
    perfil = st.radio("¿Cuál es tu perfil de riesgo?", perfiles, index=perfiles.index(plan.cargar_perfil()), horizontal=True, key="plan_perfil",
                      help="Bajo: prefieres no llevarte sustos. Medio: equilibrio. Alto: aceptas caídas fuertes a cambio de más recorrido. "
                           "Cambia cómo se juzga la cartera y qué se recomienda.")
    if perfil != plan.cargar_perfil():
        plan.guardar_perfil(perfil)
    st.caption(f"**Perfil {perfil.lower()}.** {plan.PERFILES[perfil]['frase']}")
    guardado = plan.cargar()
    if guardado.empty:
        guardado = pd.DataFrame({"activo": ["", ""], "euros": [None, None], "tengo": [None, None], "tipo": ["", ""]})
    editado = st.data_editor(guardado, num_rows="dynamic", width="stretch", key="plan_editor", column_config={
        "activo": st.column_config.TextColumn("Activo (nombre o ticker)", help="Ejemplos: Nvidia, ASML, Iberdrola, VWCE.DE, bitcoin, ETH, oro."),
        "euros": st.column_config.NumberColumn("€ al mes", min_value=0, format="%.0f", help="Lo que aportas cada mes. Vacío o 0 si no aportas."),
        "tengo": st.column_config.NumberColumn("Ya tengo (€)", min_value=0, format="%.0f",
                                               help="Lo que vale hoy lo que ya tienes de este activo. Déjalo vacío o en 0 si es una compra nueva."),
        "tipo": st.column_config.SelectboxColumn("Tipo (solo si no lo encuentro)", options=[""] + list(plan.TIPOS_MANUALES),
                                                 help="Para fondos que no están en Yahoo (por ejemplo, los indexados de MyInvestor): "
                                                      "escribe el nombre que quieras y elige aquí qué tipo de fondo es.")})
    c1, c2 = st.columns([1, 4])
    pulsado = c1.button("🔍 Analizar cartera", type="primary", key="plan_analizar")
    c2.caption("Tarda unos segundos por activo la primera vez. Todo se guarda solo en tu ordenador.")
    if pulsado:
        limpio = plan.limpiar(editado)
        plan.guardar(limpio)
        if limpio.empty:
            st.warning("Escribe al menos un activo con lo que aportas al mes o lo que ya tienes.")
            return
        barra = st.progress(0.0, "Analizando…")
        st.session_state["plan_resultado"] = plan.evaluar_todos(limpio, lambda f, txt: barra.progress(min(f, 1.0), txt))
        for k in ("plan_candidatas", "ysi_resultado"):
            st.session_state.pop(k, None)
        barra.empty()
    act = st.session_state.get("plan_resultado")
    if not act:
        st.info("Rellena la tabla y pulsa «Analizar cartera». Con dos activos ya funciona; cuantos más pongas, más completo sale el análisis de conjunto.")
        return

    fl = plan.flaquezas(act, perfil)
    rep, sin_asignar = plan.reparto(act, perfil)
    glob = plan.nota_global(act, fl)
    mensual = sum(a["euros"] for a in act)
    invertido = sum(a.get("tengo") or 0 for a in act)
    con_tengo = invertido > 0
    total = sum(plan.peso_eur(a) for a in act) or 1
    espec = sum(plan.peso_eur(a) for a in act if a["rol"] in plan.ESPECULATIVOS) / total
    c1, c2, c3, c4 = st.columns([2.2, 1, 1, 1])
    icono, _, titulo = glob["etiqueta"].partition(" ")
    c1.markdown(f"<div class='ri-box' style='--c:{_COLOR[glob['color']]};margin:0'><div class='t'>{icono} CARTERA {html(titulo)}</div>"
                f"<div>{html(glob['texto'])} Juzgada con perfil de riesgo {perfil.lower()}.</div></div>", unsafe_allow_html=True)
    c2.metric("Aportas al mes", _eur(mensual), (f"ya invertido: {_eur(invertido)}" if con_tengo else f"{len(act)} activos"), delta_color="off")
    c3.metric("Parte especulativa", f"{espec * 100:.0f} %", f"tu tope: {plan.PERFILES[perfil]['espec'] * 100:.0f} %", delta_color="off",
              help="Empresas que aún no ganan dinero de verdad y criptomonedas.")
    div = plan.renta_dividendos(act)
    c4.metric("Dividendo medio", f"{div * 100:.1f} %".replace(".", ","), help="Rentabilidad por dividendo media de la cartera, ponderada por peso.")
    st.caption("Análisis generado con reglas automáticas sobre datos públicos (sin IA). Es una orientación general: no conoce tu situación "
               "personal ni tus impuestos, y no es asesoramiento financiero."
               + (" Los pesos cuentan lo que ya tienes más un año de aportaciones." if con_tengo else ""))

    # --- reparto
    st.subheader("Cómo repartiría los mismos euros al mes")
    if mensual <= 0:
        st.info("No has puesto aportaciones mensuales: analizo solo lo que ya tienes.")
    else:
        _tabla_reparto(rep, con_tengo, "plan_tabla")
        if sin_asignar >= 1:
            st.warning(f"**Quedan {_eur(sin_asignar)} al mes sin asignar.** Ninguno de tus activos está ahora para comprar más. "
                       "Puedes guardarlos hasta que alguno mejore o destinarlos a lo que le falta a la cartera (más abajo).")
        if any(abs(r["cambio"]) > 0.5 for r in rep):
            orden = sorted(rep, key=lambda r: r["sugerido"])
            nombres = [(r["nombre"] or r["escrito"])[:28] for r in orden]
            fig = go.Figure()
            fig.add_trace(go.Bar(y=nombres, x=[r["euros"] for r in orden], name="Ahora", orientation="h", marker_color=NEUTRO))
            fig.add_trace(go.Bar(y=nombres, x=[r["sugerido"] for r in orden], name="Sugerido", orientation="h", marker_color=AZUL))
            fig.update_layout(barmode="group", height=max(220, 44 * len(orden) + 70), margin=dict(l=10, r=10, t=10, b=10),
                              legend=dict(orientation="h", y=1.06, x=0, traceorder="normal"),
                              xaxis=dict(title="€ al mes", gridcolor="rgba(137,135,129,.2)"), yaxis=dict(title=None))
            st.plotly_chart(fig, width="stretch", key="plan_barras")
        else:
            st.success("No cambiaría el reparto: lo que aportas a cada activo ya es razonable.")
        st.caption("Reglas del reparto: lo que conviene pausar baja a cero (sin vender lo que ya tienes); solo sube lo que el análisis recomienda "
                   "comprar; lo que ya pesa mucho en tu cartera recibe menos; lo especulativo tiene un tope según tu perfil; y los cambios son "
                   "graduales, para no ir detrás de cada movimiento de precio. Revísalo cada dos o tres meses, no cada semana.")

    izq, der = st.columns(2)
    with izq:
        st.subheader("Por dónde flaquea")
        if not fl:
            st.success("No veo puntos débiles relevantes.")
        for x in fl:
            st.markdown(f"{'🔴' if x['grave'] == 2 else '🟡' if x['grave'] == 1 else 'ℹ️'} **{x['titulo']}.** {x['texto']}")
    with der:
        st.subheader("Para qué sirve cada pieza")
        grupos: dict[str, list] = {}
        for a in act:
            grupos.setdefault(a["rol"], []).append(a)
        for rol, lista in sorted(grupos.items(), key=lambda kv: -sum(plan.peso_eur(a) for a in kv[1])):
            peso = sum(plan.peso_eur(a) for a in lista) / total
            st.markdown(f"**{plan.ROLES[rol][0]} · {peso * 100:.0f} %** — " + ", ".join(a["nombre"] or a["escrito"] for a in lista)
                        + f"  \n<span style='opacity:.75;font-size:.85rem'>{html(plan.ROLES[rol][1])}</span>", unsafe_allow_html=True)

    with st.expander("Detalle de cada activo"):
        for a in act:
            st.markdown(f"**{a['nombre'] or a['escrito']}**" + (f" (`{a['ticker']}`)" if a.get("ticker") else "") + f" · {plan.accion_texto(a)}  \n"
                        f"{a['motivo']}" + (f"  \n<span style='opacity:.75;font-size:.85rem'>{html(a['detalle'])}</span>" if a.get("detalle") else ""),
                        unsafe_allow_html=True)
        acciones = [a for a in act if a["clase"] == "accion" and a.get("ticker")]
        if acciones:
            elegido = st.selectbox("Abrir el análisis completo de", [a["ticker"] for a in acciones], key="plan_abrir",
                                   format_func=lambda tk: next(a["nombre"] for a in acciones if a["ticker"] == tk))
            st.button("Abrir en 🏢 Empresa", key="plan_abrir_btn", on_click=abrir_empresa, args=(elegido,))

    # --- qué le falta y qué le sobra
    hue, sob = plan.huecos(act, perfil), plan.sobras(act, perfil)
    izq, der = st.columns(2)
    with izq:
        st.subheader("Qué le falta")
        if not hue:
            st.success(f"Para un perfil {perfil.lower()}, no echo en falta ningún tipo de pieza.")
        for h in hue:
            st.markdown(f"**{h['titulo']}.** {h['texto']}")
    with der:
        st.subheader("Qué le sobra")
        if not sob:
            st.success("No veo piezas repetidas ni que estén de más.")
        for x in sob:
            st.markdown(f"- {x}")
    buscables = [h for h in hue if h["buscar"]]
    if buscables:
        if st.button("🔎 Buscar candidatas que hoy pasan el análisis", key="plan_buscar"):
            ya = {str(a.get("ticker") or "").upper() for a in act}
            with st.spinner("Analizando empresas conocidas de cada tipo…"):
                st.session_state["plan_candidatas"] = {h["rol"]: plan.candidatas(h["rol"], ya) for h in buscables}
        for rol, lista in (st.session_state.get("plan_candidatas") or {}).items():
            st.markdown(f"**Para «{plan.ROLES[rol][0]}»:**")
            if not lista:
                st.caption("Ninguna de las candidatas que reviso está ahora a buen precio. Mira 💡 Ideas para una búsqueda más amplia.")
            for c in lista:
                st.markdown(f"- **{c['nombre']}** (`{c['ticker']}`) · {plan.accion_texto(c)} · {c['detalle']}. {c['motivo']}")
        st.caption("Son empresas grandes y conocidas que reviso con el mismo análisis; no es una lista cerrada ni una orden de compra. "
                   "Puedes probar cualquiera en «¿Y si…?».")

    _y_si(act, perfil)

    # --- fondo indexado, aparte
    st.subheader("Aparte: si quisieras añadir un fondo indexado")
    fc = plan.fondo_complementario(act, perfil)
    st.caption("Esto no forma parte de la nota de arriba, que juzga tus activos tal como son. Es solo por si te planteas añadir un fondo.")
    if fc["ya"]:
        st.markdown(fc["ya"])
    izq, der = st.columns(2)
    with izq:
        st.markdown("**Qué tipo encajaría con lo que tienes**")
        for x in fc["encajan"]:
            st.markdown(f"- {x}")
        if fc["evitar"]:
            st.markdown("**Cuáles te aportarían poco**")
            for x in fc["evitar"]:
                st.markdown(f"- {x}")
    with der:
        st.markdown("**Qué debería tener**")
        for x in fc["requisitos"]:
            st.markdown(f"- {x}")

    # --- proyección
    st.subheader("Si mantienes este plan")
    pr = plan.proyeccion(act)
    st.dataframe(pr.style.format({c: (lambda x: _eur(x)) for c in ("Puesto de tu bolsillo", "Si va mal", "Normal", "Si va bien")}),
                 hide_index=True, width="stretch")
    st.caption("No es una predicción. Uso supuestos prudentes de rentabilidad anual según el tipo de activo (por ejemplo, un fondo mundial: "
               "2 % si va mal, 6 % normal, 9 % si va bien; lo especulativo y las criptomonedas, con un rango mucho más ancho). Sin impuestos ni inflación.")

    with st.expander("📋 Copiar para pedir una segunda opinión a una IA"):
        st.code(plan.texto_para_ia(act, fl, rep, perfil), language="markdown")
