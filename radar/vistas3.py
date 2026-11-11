"""📌 Picks del día y el veredicto por plazos (corto, medio y largo) que une 🚦 Señales con 🧠 Análisis."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import streamlit as st

from . import analisis as an
from . import cartera, diario, escenarios, picks, senales
from .vistas import AMBAR, AZUL, CSS, NEUTRO, ROJO, VERDE, esc, html, num
from .vistas2 import cargar_vigilancia

_COLOR = {"verde": VERDE, "amarillo": AMBAR, "rojo": ROJO, "gris": NEUTRO}


# ============================================================================= veredicto por plazos
def por_plazos(h: pd.DataFrame, ref_close: pd.Series | None, prudencia: float, rec: dict | None = None) -> list[dict]:
    """Tres respuestas a tres preguntas distintas: ¿entro esta semana?, ¿cómo pinta a 3-6 meses?, ¿la quiero a más de un año?"""
    filas = []
    # --- corto plazo: la misma señal técnica de 🚦 Señales
    try:
        tec = float(senales.puntuacion_tecnica(senales.indicadores(h, ref_close)).iloc[-1])
        etiqueta, _, nota = senales.veredicto(tec, 0)
        color = "verde" if etiqueta.startswith("🟢") else "rojo" if etiqueta.startswith("🔴") else "amarillo"
        texto = {"verde": "El precio acompaña ahora mismo: tendencia e impulso a favor.",
                 "amarillo": "Señales mezcladas: ni a favor ni en contra con claridad.",
                 "rojo": "El precio va en contra ahora mismo (tendencia o impulso bajistas): entrar hoy es ir contra corriente."}[color]
        filas.append({"plazo": "Corto · 1 semana a 1 mes", "pregunta": "¿Es buen momento para entrar ya?", "veredicto": etiqueta.split(" ", 1)[1],
                      "color": color, "porque": f"{texto} Nota técnica {tec:+.0f} sobre ±6.", "donde": "🚦 Señales"})
    except Exception:  # noqa: BLE001
        pass
    # --- medio plazo: tendencia de fondo y lo que dicen las simulaciones a 6 meses
    try:
        c = h["Close"].dropna()
        precio = float(c.iloc[-1])
        m200 = float(c.tail(200).mean())
        m50 = float(c.tail(50).mean())
        e = escenarios.analizar(c, ref_close, 126, prudencia)["escenarios"]["mixto"] if ref_close is not None else None
        mediana = e["percentiles"][50] / precio - 1 if e else None
        prob_perder = e["prob_perdida"] if e else None
        alcista, bajista = precio > m200 and m50 > m200, precio < m200 and m50 < m200
        if alcista and (prob_perder is None or prob_perder < 0.45):
            color, ver = "verde", "A favor"
        elif bajista and (prob_perder is None or prob_perder > 0.40):
            color, ver = "rojo", "En contra"
        else:
            color, ver = "amarillo", "Neutral"
        porque = ("Tendencia de fondo alcista" if alcista else "Tendencia de fondo bajista" if bajista else "Tendencia de fondo sin definir")
        porque += f" (precio {precio / m200 - 1:+.0%} respecto a su media de 200 sesiones)".replace("%", " %")
        if e:
            porque += (f". Según cómo se ha movido históricamente, a 6 meses lo más probable es {mediana:+.0%} y hay un "
                       f"{prob_perder:.0%} de probabilidad de estar en pérdidas").replace("%", " %")
        filas.append({"plazo": "Medio · 3 a 6 meses", "pregunta": "¿Hacia dónde empuja la tendencia?", "veredicto": ver, "color": color,
                      "porque": porque + ".", "donde": "🎯 Escenarios"})
    except Exception:  # noqa: BLE001
        pass
    # --- largo plazo: la recomendación del análisis fundamental
    if rec:
        color = {"verde": "verde", "amarillo": "amarillo", "rojo": "rojo"}[rec["color"]]
        porque = f"Precio {rec['precio_juicio']}"
        if rec.get("rent_base") is not None:
            porque += f"; escenario base {rec['rent_base']:+.0%}".replace("%", " %") + " con dividendos"
        if rec.get("rent_pesimista") is not None:
            porque += f", pesimista {rec['rent_pesimista']:+.0%}".replace("%", " %")
        filas.append({"plazo": "Largo · 12 a 18 meses", "pregunta": "¿Vale más de lo que cuesta?", "veredicto": rec["titulo"].capitalize(),
                      "color": color, "porque": porque + ".", "donde": "🧠 Análisis"})
    return filas


def conclusion_plazos(filas: list[dict]) -> str:
    """Qué hacer cuando los plazos no dicen lo mismo."""
    por = {f["plazo"].split(" ")[0]: f["color"] for f in filas}
    corto, medio, largo = por.get("Corto"), por.get("Medio"), por.get("Largo")
    if largo is None:
        return ("Para saber si merece la pena a más de un año, mira 🧠 Análisis: allí se valora el negocio, no el movimiento del precio.")
    if largo == "verde" and corto == "rojo":
        return ("**No se contradicen: responden a preguntas distintas.** El negocio está a buen precio para tenerlo más de un año, pero ahora mismo "
                "el precio está cayendo. Si vas a largo plazo, la señal de corto solo te dice que no hay prisa: entra **por partes** (por ejemplo, "
                "en 3 o 4 compras repartidas) o espera a que la señal de corto deje de estar en rojo. Si lo que quieres es una operación de días o "
                "semanas, hoy no es el momento.")
    if largo == "verde" and corto in ("verde", "amarillo"):
        return ("Los plazos están alineados o casi: buen precio a largo plazo y el mercado no va en contra. Es la situación más cómoda para entrar"
                + (" de una vez." if corto == "verde" else ", mejor en dos o tres veces."))
    if largo == "rojo" and corto == "verde":
        return ("**Ojo:** el precio sube ahora, pero la empresa está cara o es de poca calidad para tenerla a largo plazo. Solo tiene sentido como "
                "operación corta con stop loss, no como inversión.")
    if largo == "rojo":
        return "A largo plazo no compensa y a corto tampoco acompaña: mejor buscar otra."
    if corto == "verde":
        return ("A largo plazo el precio es justo (sin margen de seguridad), aunque a corto plazo el mercado acompaña. Vale para una operación "
                "corta con stop; para invertir, mejor esperar al precio de entrada que indica 🧠 Análisis.")
    return ("A largo plazo el precio es justo y a corto no hay señal clara: no hay motivo para tener prisa. Apunta el precio de entrada de "
            "🧠 Análisis y pon una alerta.")


def panel_plazos(h: pd.DataFrame, ref_close, prudencia: float, rec: dict | None = None, clave: str = "") -> None:
    filas = por_plazos(h, ref_close, prudencia, rec)
    if not filas:
        return
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown("**Veredicto por plazos**")
    cols = st.columns(len(filas))
    for col, f in zip(cols, filas):
        col.markdown(f"<div class='ri-esc' style='--c:{_COLOR[f['color']]}'><div class='s'>{html(f['plazo'])}</div>"
                     f"<div class='p'>{html(f['veredicto'])}</div><div class='s'><i>{html(f['pregunta'])}</i></div>"
                     f"<div class='s' style='margin-top:4px'>{html(f['porque'])}</div>"
                     f"<div class='s' style='opacity:.6;margin-top:4px'>Detalle en {html(f['donde'])}</div></div>", unsafe_allow_html=True)
    st.info(conclusion_plazos(filas))


# ============================================================================= 📌 PICKS DEL DÍA
def _mis_valores() -> tuple[str, ...]:
    mios = [t for t in cargar_vigilancia() if not any(x in t for x in ("^", "=", "-USD", "-EUR"))]
    try:
        mios += list(cartera.cargar_posiciones()["ticker"].dropna().astype(str))
        d = diario.cargar()
        if "fecha_salida" in d:
            mios += list(d[d["fecha_salida"].isna()]["ticker"].astype(str))
    except Exception:  # noqa: BLE001
        pass
    return tuple(dict.fromkeys(t.upper() for t in mios if t))


def pantalla_picks(abrir_empresa) -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    st.caption("Las empresas que presentan resultados en los próximos días, ordenadas por interés, con lo que ha pasado otras veces: "
               "«si bate previsiones, suele…; si falla, suele…». No predice la dirección: te da las frecuencias reales de cada empresa "
               "para que decidas con datos.")
    c1, c2, c3 = st.columns([1.3, 1.6, 1.4])
    dias = c1.radio("Periodo", [1, 3, 7], index=2, horizontal=True, format_func=lambda d: {1: "Hoy y mañana", 3: "3 días", 7: "7 días"}[d])
    ambito = c2.radio("Qué empresas", ["Grandes + las mías", "Solo las mías"], horizontal=True,
                      help="«Las mías» = tu lista de 🖥️ Monitor, tu 🧺 Cartera y las operaciones abiertas del 📒 Diario.")
    cuantas = c3.slider("Cuántas analizar a fondo", 4, 20, 10, help="Cada una necesita varias consultas; más empresas, más espera la primera vez.")
    mios = _mis_valores()
    with st.spinner("Consultando el calendario de resultados…"):
        try:
            europeos = picks.universo_europeo() if ambito.startswith("Grandes") else ()
            df = picks.proximos(dias, mios, europeos, cap_minima=20e9 if ambito.startswith("Grandes") else 1e15)
        except Exception as e:  # noqa: BLE001
            st.warning(f"No pude cargar el calendario de resultados ({type(e).__name__}). Inténtalo en unos minutos.")
            return
    if df.empty:
        st.info("No hay presentaciones de resultados en ese periodo para las empresas elegidas. Prueba con «7 días» o con «Grandes + las mías».")
        return
    # Se analizan a fondo primero las tuyas y luego las más grandes; el orden final lo da el interés
    candidatos = df.sort_values(["mio", "cap"], ascending=[False, False]).head(cuantas)

    def preparar(fila):
        try:
            f = picks.ficha(fila["ticker"], fila["fecha"].isoformat())
        except Exception:  # noqa: BLE001
            f = {}
        return fila, f, (picks.lectura(f, fila) if f else None)

    with st.spinner(f"Mirando qué hicieron estas {len(candidatos)} empresas en sus últimas presentaciones…"):
        with ThreadPoolExecutor(max_workers=5) as ex:
            preparados = list(ex.map(preparar, [r.to_dict() for _, r in candidatos.iterrows()]))
    preparados = [p for p in preparados if p[2]]
    preparados.sort(key=lambda p: (-p[2]["interes"], p[0]["fecha"]))
    if not preparados:
        st.warning("Yahoo no ha devuelto el historial de estas empresas ahora mismo. Prueba en unos minutos.")
    st.subheader(f"📌 Las {len(preparados)} más interesantes")
    for fila, f, l in preparados:
        cuando = "hoy" if fila["faltan"] == 0 else "mañana" if fila["faltan"] == 1 else f"el {['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'][fila['fecha'].weekday()]} {fila['fecha']:%d/%m}"
        color = {"alto": AMBAR, "medio": AZUL, "bajo": NEUTRO}[l["nivel"]]
        nombre = fila.get("nombre") or fila["ticker"]
        cabecera = (f"<div class='ri-esc' style='--c:{color};height:auto;margin-bottom:6px'><b>{html(fila['ticker'])} · {html(nombre[:45])}</b>"
                    f"{' ⭐ en tus listas' if fila.get('mio') else ''}"
                    f"<div class='s'>Presenta <b>{cuando}</b>{(' ' + html(fila['momento'])) if fila.get('momento') else ''} · {html(fila['bolsa'])} · "
                    f"interés <b>{l['nivel']}</b>"
                    + (f" · movimiento esperado <b>±{l['esperado'] * 100:.1f} %</b>".replace(".", ",") if l.get("esperado") else "")
                    + (f" · sesgo histórico {l['sesgo']}" if l["sesgo"] != "sin datos" else "") + "</div></div>")
        st.markdown(cabecera, unsafe_allow_html=True)
        with st.expander("Qué se espera y qué ha pasado otras veces", expanded=l["nivel"] == "alto" and len(preparados) <= 12):
            for t in l["frases"]:
                st.markdown("- " + esc(t))
            if l["si_bate"]:
                st.markdown("🟢 " + esc(l["si_bate"]))
            if l["si_falla"]:
                st.markdown("🔴 " + esc(l["si_falla"]))
            for a in l["avisos"]:
                st.markdown("🟡 " + esc(a))
            reac = f.get("reacciones")
            if reac is not None and not reac.empty:
                st.dataframe(reac, hide_index=True, width="stretch", height=min(320, 40 + 36 * len(reac)), column_config={
                    "Sorpresa": st.column_config.NumberColumn(format="percent", help="Cuánto batió (+) o falló (−) el beneficio previsto."),
                    "Reacción": st.column_config.NumberColumn("Reacción al día siguiente", format="percent"),
                    "BPA esperado": st.column_config.NumberColumn(format="%.2f"), "BPA publicado": st.column_config.NumberColumn(format="%.2f")})
            st.button(f"🧠 Analizar {fila['ticker']}", key=f"pick_{fila['ticker']}", on_click=abrir_empresa, args=(fila["ticker"],))
    with st.expander(f"📅 Calendario completo del periodo ({len(df)} empresas)"):
        t = df.copy()
        t["Capitalización (mil M)"] = t["cap"] / 1e9
        st.dataframe(t[["fecha", "momento", "ticker", "nombre", "bolsa", "bpa_esperado", "bpa_hace_un_anio", "Capitalización (mil M)", "mio"]].rename(
            columns={"fecha": "Fecha", "momento": "Cuándo", "ticker": "Ticker", "nombre": "Empresa", "bolsa": "Bolsa", "bpa_esperado": "BPA esperado",
                     "bpa_hace_un_anio": "BPA hace un año", "mio": "En tus listas"}), hide_index=True, width="stretch", column_config={
            "Capitalización (mil M)": st.column_config.NumberColumn(format="%.0f"), "BPA esperado": st.column_config.NumberColumn(format="%.2f"),
            "BPA hace un año": st.column_config.NumberColumn(format="%.2f")})
    st.caption("**Cómo leerlo.** «Interés» mide cuánto puede moverse y si la tienes en tus listas, no si conviene comprarla. "
               "«Batir previsiones» no garantiza subir: muchas veces el precio depende de lo que la empresa anuncie para el trimestre siguiente. "
               "Entrar justo antes de resultados es jugarse la operación a una sola noticia; si ya la tienes, decide antes si aguantas un "
               "movimiento del tamaño esperado. Fuentes: calendario de Nasdaq (EE. UU.) y Yahoo Finance (Europa, historial y opciones). "
               "Las fechas pueden cambiar a última hora.")


# ============================================================================= 💡 IDEAS
def pantalla_ideas(abrir_empresa) -> None:
    from . import ideas

    st.markdown(CSS, unsafe_allow_html=True)
    st.subheader("Las 10 más atractivas a 6-12 meses")
    st.caption("El programa pasa su análisis a todas las empresas del grupo que elijas y te enseña las diez que mejor salen: buen precio "
               "frente a lo que puede valer, pérdida acotada si sale mal y negocio de calidad. Es una lista para empezar a mirar, no una orden de compra.")
    c1, c2 = st.columns([3, 1])
    universo = c1.selectbox("Dónde buscar", list(ideas.UNIVERSOS), key="ideas_universo")
    clave = f"ideas_{universo}"
    lanzar = c2.button("🔎 Buscar ideas" if clave not in st.session_state else "🔄 Volver a calcular", width="stretch", type="primary")
    if lanzar:
        barra = st.progress(0.0, "Empezando…")
        try:
            st.session_state[clave] = ideas.ranking(universo, progreso=lambda x, t: barra.progress(min(x, 1.0), t))
        except Exception as e:  # noqa: BLE001
            st.error(f"No pude completar la búsqueda ({type(e).__name__}). Revisa la conexión y vuelve a intentarlo.")
        barra.empty()
    if clave not in st.session_state:
        st.info("Pulsa «Buscar ideas». La primera vez tarda entre 1 y 3 minutos según el grupo (descarga las cuentas de decenas de empresas); "
                "si repites el mismo día va mucho más rápido.")
        return
    r = st.session_state[clave]
    if not r["mejores"]:
        st.warning(f"De {r['universo']} empresas he analizado a fondo {r['analizadas']} y ninguna pasa el listón ahora mismo. "
                   "También es información: el grupo está caro o Yahoo no ha devuelto datos. Prueba con otro grupo.")
        return
    st.caption(f"Calculado el {r['momento']:%d/%m/%Y a las %H:%M} · {r['universo']} empresas en el grupo → {r['cribadas']} con datos → "
               f"{r['analizadas']} analizadas a fondo → {r['n_compra']} con recomendación de compra.")
    if r["n_compra"] < 10:
        st.info(f"Solo {r['n_compra']} empresa(s) salen como compra clara hoy. El resto de la lista son buenas empresas a las que les falta "
                "bajar un poco: llevan su precio de entrada.")
    for i, e in enumerate(r["mejores"], 1):
        color = _COLOR[e["color"]]
        detalle = [f"escenario base <b>{e['rent_base'] * 100:+.0f} %</b>", f"si sale mal <b>{(e['rent_pesimista'] or 0) * 100:+.0f} %</b>",
                   f"calidad <b>{e['calidad'].lower()}</b>", f"tendencia de medio plazo <b>{e['medio']}</b>"]
        if e.get("per_fwd"):
            detalle.append(f"PER previsto {e['per_fwd']:.0f}")
        if e.get("dividendo") and e["dividendo"] > 0.01:
            detalle.append(f"dividendo {e['dividendo'] * 100:.1f} %".replace(".", ","))
        porque = []
        if e.get("principal"):
            porque.append(f"vive sobre todo de «{e['principal'][0]}» ({e['principal'][1]:.0f} %)")
        if e["fuertes"]:
            porque.append("destaca en " + " y ".join(x.lower() for x in e["fuertes"]))
        if e.get("crecimiento") and e["crecimiento"] > 0.05:
            porque.append(f"se espera que el beneficio crezca un {e['crecimiento'] * 100:.0f} %")
        etiqueta = "COMPRAR" if e["color"] == "verde" else f"ESPERAR a {num(e['entrada'], 0 if (e['entrada'] or 0) > 20 else 2)} {e['moneda']}" if e.get("entrada") else e["titulo"]
        st.markdown(
            f"<div class='ri-esc' style='--c:{color};height:auto;margin-bottom:4px'><b>{i}. {html(e['nombre'])} ({html(e['ticker'])})</b> · "
            f"{num(e['precio'], 2)} {html(e['moneda'])} · <b>{html(etiqueta)}</b>{(' · ' + html(e['sector'])) if e['sector'] else ''}"
            f"<div class='s'>{' · '.join(detalle)}</div>"
            + (f"<div class='s'><b>Por qué:</b> {html('; '.join(porque))}.</div>" if porque else "")
            + (f"<div class='s'><b>Lo que puede salir mal:</b> {html(e['riesgo'].lower())}.</div>" if e["riesgo"] else "") + "</div>",
            unsafe_allow_html=True)
        c1, c2 = st.columns([1, 5])
        c1.button("🧠 Ver análisis", key=f"idea_{e['ticker']}", on_click=abrir_empresa, args=(e["ticker"],), width="stretch")
        with c2.expander("En cristiano"):
            st.write(e["resumen"])
    with st.expander(f"Ver todas las analizadas a fondo ({r['analizadas']})"):
        t = pd.DataFrame(r["tabla"]).sort_values("puntos", ascending=False)
        st.dataframe(t[["ticker", "nombre", "titulo", "rent_base", "rent_pesimista", "calidad", "medio", "per_fwd", "dividendo", "sector"]].rename(columns={
            "ticker": "Ticker", "nombre": "Empresa", "titulo": "Recomendación", "rent_base": "Escenario base", "rent_pesimista": "Si sale mal",
            "calidad": "Calidad", "medio": "Tendencia medio plazo", "per_fwd": "PER previsto", "dividendo": "Dividendo", "sector": "Sector"}),
            hide_index=True, width="stretch", column_config={
                **{k: st.column_config.NumberColumn(format="percent") for k in ("Escenario base", "Si sale mal", "Dividendo")},
                "PER previsto": st.column_config.NumberColumn(format="%.1f")})
    st.caption("**Cómo se eligen.** Primero una criba rápida descarta lo que no tiene potencial según analistas, rentabilidad ni crecimiento; "
               "después las candidatas pasan el análisis completo. El orden premia la ganancia del escenario base, resta la mitad de la pérdida "
               "del pesimista y da un extra a la calidad y a que la tendencia no vaya en contra. Los escenarios son a 12-18 meses; la tendencia "
               "de medio plazo indica si el precio acompaña ahora. Diversifica: si las diez son del mismo sector, no compres las diez. "
               + an.AVISO_LEGAL)
