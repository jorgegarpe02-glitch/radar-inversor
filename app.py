"""Radar Inversor · panel local con datos gratuitos.

Arranque:  python lanzar.py   (o doble clic en iniciar.bat / iniciar.command)
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from radar import (actualizador, alertas, cache, cartera, config, conexiones, datos, diario, energia, escenarios, eventos, graficos,
                   materias, mundo, noticias, noticias_ia, senales, suministro, vistas, vistas2, vistas3, vistas4)
from radar import materias as catalogo_materias  # «materias» se reutiliza más abajo como variable

st.set_page_config(page_title="Radar Inversor", page_icon="📡", layout="wide")

RECOMENDACION = {"strong_buy": "Compra fuerte", "buy": "Compra", "hold": "Mantener",
                 "underperform": "Infraponderar", "sell": "Venta"}


# ----------------------------------------------------------------------------- utilidades
def num(x, dec: int = 2) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(x, dec: int = 1, signo: bool = True) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{x * 100:{'+' if signo else ''}.{dec}f}%".replace(".", ",")


def grande(x, moneda: str = "") -> str:
    if not x:
        return "—"
    return f"{num(x / 1e9, 1)} mil M {moneda}".strip() if x >= 1e9 else f"{num(x / 1e6, 0)} M {moneda}".strip()


def esc(texto: str) -> str:
    """Evita que Streamlit interprete $ o [] de un titular como fórmula o enlace."""
    return texto.replace("$", "\\$").replace("[", "(").replace("]", ")")


def seguro(funcion, *args, etiqueta: str = "los datos", **kwargs):
    try:
        return funcion(*args, **kwargs)
    except Exception as e:  # noqa: BLE001 - queremos que la app siga viva sin conexión
        st.warning(f"No pude obtener {etiqueta} ahora mismo ({type(e).__name__}). "
                   "Revisa tu conexión o inténtalo en unos minutos.")
        return None


def titulares(consulta: str, etiqueta: str = "las noticias", modo: str = "auto") -> list[dict]:
    """Titulares de 7 días, solo de economía y mercados. Con la IA activada se leen en inglés y FinBERT valora el tono.

    modo: «empresa» (permisivo: quita deporte, sucesos…), «activo» (estricto: tiene que hablar de mercados) o «auto».
    """
    if usar_ia:
        items = seguro(noticias.buscar, consulta, "en", "US", 7, 20, modo, etiqueta=etiqueta) or []
        try:
            return noticias_ia.aplicar(items)
        except Exception as e:  # noqa: BLE001
            st.caption(f"La IA de noticias falló ({type(e).__name__}); uso palabras clave.")
            return items
    return seguro(noticias.buscar, consulta, leng, pais, 7, 20, modo, etiqueta=etiqueta) or []


def lista_noticias(items: list[dict]) -> None:
    for i in items:
        fecha = i["fecha"].strftime("%d/%m %H:%M") if i["fecha"] else ""
        st.markdown(f"{i['marca']} [{esc(i['titulo'])}]({i['enlace']}) — *{esc(i['fuente'])}* · {fecha}")


@st.fragment(run_every="5m")
def _alertas_fragmento():
    """Revisa las alertas cada 5 minutos mientras el programa está abierto."""
    reglas_act = [r for r in alertas.cargar_reglas() if r.get("activa", True)]
    if not reglas_act:
        st.caption("No tienes alertas. Créalas en 🔔 Alertas.")
        return
    ultima = st.session_state.get("_alertas_ultima")
    if ultima is None or (datetime.now() - ultima).total_seconds() > 270:
        st.session_state["_alertas_ultima"] = datetime.now()
        try:
            for a in alertas.revisar_y_guardar(notificar=True):
                st.toast(f"🔔 {a['mensaje']}")
        except Exception:  # noqa: BLE001
            pass
    st.caption(f"{len(reglas_act)} activas · revisadas a las {st.session_state['_alertas_ultima']:%H:%M}")


# ----------------------------------------------------------------------------- navegación
AREAS = ["🌍 Inicio", "📌 Picks del día", "💡 Ideas", "📈 Mercados", "🏢 Empresa", "🪙 Cripto", "🧺 Cartera", "🔔 Alertas", "📒 Diario", "📘 Guía"]
SUB_MERCADOS = ["🌡️ Hoy", "🖥️ Monitor", "🟩 Mapa de calor", "📊 Macro", "🧮 Buscador", "🔍 Oportunidades", "⛏️ Materias primas", "📅 Agenda",
                "🛢️ Energía y buques"]
SUB_EMPRESA = ["🧠 Análisis", "💼 Negocio", "🏢 Ficha", "🚦 Señales", "🎯 Escenarios", "📰 Noticias", "🕸️ Conexiones", "🔬 Profundizar",
               "💶 Mi compra"]
# Línea de comandos al estilo de un terminal profesional: «NVDA AN», «SAN.MC N», «ORO», «CALOR»…
FUNCIONES = {"AN": "🧠 Análisis", "DES": "🧠 Análisis", "NEG": "💼 Negocio", "FA": "🏢 Ficha", "FICHA": "🏢 Ficha", "GP": "🏢 Ficha",
             "SEN": "🚦 Señales", "ESC": "🎯 Escenarios", "N": "📰 Noticias", "CN": "📰 Noticias", "CON": "🕸️ Conexiones",
             "SPLC": "🕸️ Conexiones", "COMPRA": "💶 Mi compra", "OWN": "🔬 Profundizar", "HDS": "🔬 Profundizar",
             "OPC": "🔬 Profundizar", "OMON": "🔬 Profundizar", "PRO": "🔬 Profundizar"}
COMANDOS = {"CRIPTO": ("🪙 Cripto", None), "CRYPTO": ("🪙 Cripto", None), "BTC": ("🪙 Cripto", None), "BITCOIN": ("🪙 Cripto", None),
            "PICKS": ("📌 Picks del día", None), "RESULTADOS": ("📌 Picks del día", None), "IDEAS": ("💡 Ideas", None), "TOP": ("💡 Ideas", None),
            "MACRO": ("📈 Mercados", "📊 Macro"), "MONITOR": ("📈 Mercados", "🖥️ Monitor"), "BUSCADOR": ("📈 Mercados", "🧮 Buscador"),
            "CARTERA": ("🧺 Cartera", None), "PLAN": ("🧺 Cartera", None), "HOY": ("📈 Mercados", "🌡️ Hoy"), "CALOR": ("📈 Mercados", "🟩 Mapa de calor"), "MAPA": ("🌍 Inicio", None),
            "OPORT": ("📈 Mercados", "🔍 Oportunidades"), "MATERIAS": ("📈 Mercados", "⛏️ Materias primas"),
            "AGENDA": ("📈 Mercados", "📅 Agenda"), "BUQUES": ("📈 Mercados", "🛢️ Energía y buques"), "ALERTAS": ("🔔 Alertas", None),
            "DIARIO": ("📒 Diario", None), "GUIA": ("📘 Guía", None), "AYUDA": ("📘 Guía", None)}
SECCION_DE = {"🌍 Inicio": "🌍 Mapa mundial", "🌡️ Hoy": "🌡️ Mercado", "🏢 Ficha": "🏢 Empresa"}


def abrir_empresa(simbolo: str, destino: str = "🧠 Análisis") -> None:
    """Abre una empresa (por ticker o por nombre) en el área Empresa. Se usa como callback de botones."""
    s = (simbolo or "").strip()
    if not s:
        return
    elegido = s.upper()
    # Solo se da por ticker lo que lo parece sin duda (lleva punto, ^, = o guion: SAN.MC, ^IBEX, GC=F, BTC-EUR).
    # Todo lo demás («accenture», «NVDA», «banco santander») pasa por el buscador, que devuelve primero el ticker exacto si existe.
    if not re.fullmatch(r"[\^A-Za-z0-9]*[.\^=\-][A-Za-z0-9.\-=]*", s):
        try:
            candidatos = datos.buscar(s)
            if candidatos:
                elegido = candidatos[0]["symbol"]
        except Exception:  # noqa: BLE001
            pass
    st.session_state.update(ticker=elegido, area="🏢 Empresa", sub_empresa=destino, centro_mapa=None)


def cerrar_empresa() -> None:
    st.session_state.update(ticker=None, centro_mapa=None)


def ejecutar_comando() -> None:
    """Interpreta lo escrito en la línea de comandos: «NVDA AN», «Repsol N», «CALOR», «ORO»…"""
    texto = (st.session_state.get("comando") or "").strip()
    if not texto:
        return
    st.session_state["comando"] = ""
    partes = texto.split()
    clave = datos._sin_tildes(texto).upper()
    if clave in COMANDOS:
        area_c, sub_c = COMANDOS[clave]
        st.session_state["area"] = area_c
        if sub_c:
            st.session_state["sub_mercados"] = sub_c
        return
    materia = next((m for m in catalogo_materias.MATERIAS if datos._sin_tildes(m.split(" (")[0]) == datos._sin_tildes(texto)), None)
    if materia:
        st.session_state.update(area="📈 Mercados", sub_mercados="⛏️ Materias primas", materia_elegida=materia)
        return
    destino = "🧠 Análisis"
    if len(partes) > 1 and partes[-1].upper() in FUNCIONES:
        destino, partes = FUNCIONES[partes[-1].upper()], partes[:-1]
    abrir_empresa(" ".join(partes), destino)


st.session_state.setdefault("area", "🌍 Inicio")
st.session_state.setdefault("ticker", None)

with st.sidebar:
    st.title("📡 Radar Inversor")
    area = st.radio("Menú", AREAS, key="area")
    sub = None
    if area == "📈 Mercados":
        sub = st.radio("Mercados", SUB_MERCADOS, key="sub_mercados")
    elif area == "🏢 Empresa":
        sub = st.radio("Empresa", SUB_EMPRESA, key="sub_empresa")
    st.text_input("Comando", key="comando", on_change=ejecutar_comando, placeholder="⌨️ Comando: NVDA AN · PICKS · ORO",
                  label_visibility="collapsed",
                  help="Escribe y pulsa Intro. Empresa + función: AN análisis · NEG negocio · FA ficha · SEN señales · ESC escenarios · "
                       "N noticias · CON conexiones · PRO accionistas y opciones. Solos: PICKS, IDEAS, CRIPTO, HOY, MONITOR, CALOR, MACRO, BUSCADOR, CARTERA, MAPA, "
                       "OPORT, MATERIAS, AGENDA, BUQUES, ALERTAS, DIARIO, GUIA, "
                       "o una materia prima (ORO, COBRE…).")
    st.divider()
    st.markdown("**🔎 Buscar una empresa**")
    q_emp = st.text_input("Buscar empresa", key="buscar_empresa", placeholder="Nombre o ticker: Nvidia, Repsol, SAN.MC…",
                          label_visibility="collapsed")
    if q_emp.strip():
        resultados_b = seguro(datos.buscar, q_emp, etiqueta="la búsqueda") or []
        for r in resultados_b[:6]:
            st.button(f"{r['symbol']} · {r['nombre'][:30]}", key=f"bb_{r['symbol']}", on_click=abrir_empresa,
                      args=(r["symbol"],), width="stretch")
        if not resultados_b:
            st.caption("Sin resultados. Revisa cómo está escrito o prueba con el ticker (p. ej. ITX.MC).")
    ticker = st.session_state.get("ticker") or ""
    if ticker:
        st.caption(f"Empresa abierta: **{ticker}**")
        st.button("✕ Cerrar empresa", on_click=cerrar_empresa)
    with st.expander("⚙️ Ajustes"):
        horizonte = st.select_slider("Horizonte de los escenarios", list(escenarios.HORIZONTES), value="1 mes")
        prudencia = st.slider(
            "Prudencia del modelo", 0, 100, 50, 10,
            help="0 % = usa la rentabilidad histórica de la acción tal cual (puede ser demasiado optimista si ha subido mucho). "
                 "100 % = usa solo lo que implica su beta respecto al mercado.") / 100
        ref_ticker = st.text_input("Índice de referencia", datos.referencia_para(ticker) if ticker else "^GSPC",
                                   key=f"ref_{ticker}", help="Se usa para separar mercado alcista y bajista y calcular la beta.")
        idioma = st.selectbox("Idioma de las noticias", ["Español", "Inglés"])
        if noticias_ia.disponible():
            usar_ia = st.toggle("🧠 Valorar titulares con IA (FinBERT)", value=True,
                                help="Lee los titulares en inglés con un modelo entrenado en textos financieros. Funciona en tu ordenador, gratis.")
        else:
            usar_ia = False
            st.caption("🧠 El tono de las noticias se calcula con palabras clave. Puedes activar una IA gratuita que lo lee mejor.")
            if st.button("Instalar IA de noticias (~1 GB, una sola vez)"):
                with st.spinner("Instalando… tarda varios minutos. No cierres la ventana."):
                    ok, log = noticias_ia.instalar()
                if ok:
                    st.success("Instalada. Cierra y vuelve a abrir el programa para activarla.")
                else:
                    st.error("No se pudo instalar. Revisa tu conexión y vuelve a intentarlo.")
                    st.code(log[-1500:])
        if st.button("🗑️ Borrar caché de datos"):
            st.toast(f"Caché borrada ({cache.limpiar()} ficheros).")
        st.divider()
        st.markdown(f"**Versión {actualizador.version_local()}**")
        if actualizador.configuracion().get("repositorio") or actualizador.configuracion().get("url_version"):
            if st.button("🔄 Buscar actualizaciones"):
                info_act = actualizador.comprobar()
                if info_act["error"]:
                    st.warning("No pude consultar si hay versión nueva. Revisa tu conexión.")
                elif info_act["hay_nueva"]:
                    with st.spinner(f"Descargando la versión {info_act['remota']}…"):
                        r_act = actualizador.aplicar()
                    if r_act.get("ok"):
                        if r_act.get("requisitos"):
                            actualizador.instalar_requisitos()
                        st.success(r_act["mensaje"] + " Cierra la ventana negra y vuelve a abrir el programa.")
                    else:
                        st.error(r_act["mensaje"])
                else:
                    st.success("Ya tienes la última versión.")
            st.caption("También se actualiza solo cada vez que lo abres. Tus datos no se tocan.")
        else:
            st.caption("Actualizaciones automáticas sin configurar.")
            repo_act = st.text_input("Repositorio de GitHub", placeholder="usuario/radar-inversor",
                                     help="De dónde descargar las versiones nuevas. Lo rellena quien publica el programa.")
            if st.button("Guardar repositorio") and repo_act.count("/") == 1:
                actualizador.guardar_configuracion(repo_act)
                st.rerun()
    st.markdown("**🔔 Alertas**")
    _alertas_fragmento()
    st.caption("Datos gratuitos: Yahoo Finance, Google News, SEC, FMI, Banco Mundial, GDACS, Wikidata y OpenStreetMap. "
               "Pueden tener retrasos o errores.")

seccion = SECCION_DE.get(sub or area, sub or area)
dias = escenarios.HORIZONTES[horizonte]
leng, pais = ("es", "ES") if idioma == "Español" else ("en", "US")
h, f, ref_h, res, error_escenarios = None, {}, None, None, None
nombre = nombre_corto = moneda = ""
precio = float("nan")

# ----------------------------------------------------------------------------- carga de la empresa (solo en el área Empresa)
if area == "🏢 Empresa":
    if not ticker:
        st.header("🏢 Empresa")
        st.info("Todavía no has abierto ninguna empresa. Búscala aquí o en la barra lateral.")
        q2 = st.text_input("Buscar empresa", placeholder="Nombre o ticker: Nvidia, Repsol, Inditex, SAN.MC…", key="buscar_empresa_main")
        if q2.strip():
            for r in (seguro(datos.buscar, q2, etiqueta="la búsqueda") or [])[:8]:
                st.button(f"📈 {r['symbol']} · {r['nombre']} ({r['mercado']})", key=f"bm_{r['symbol']}",
                          on_click=abrir_empresa, args=(r["symbol"], sub or "🏢 Ficha"))
        st.stop()
    h = seguro(datos.historial, ticker, "5y", etiqueta="el histórico de precios")
    if h is None or h.empty:
        st.error(f"No encontré precios para «{ticker}». Prueba con otro ticker (en España se añade .MC, p. ej. SAN.MC).")
        st.button("✕ Cerrar esta empresa", on_click=cerrar_empresa)
        st.stop()
    f = seguro(datos.ficha, ticker, etiqueta="la ficha de la empresa") or {}
    nombre = f.get("longName") or f.get("shortName") or ticker
    nombre_corto = f.get("shortName") or nombre
    moneda = f.get("currency") or ""
    precio = float(h["Close"].iloc[-1])
    ref_h = seguro(datos.historial, ref_ticker.strip(), "5y", etiqueta=f"el índice de referencia {ref_ticker}")
    if ref_h is not None and not ref_h.empty:
        try:
            res = escenarios.analizar(h["Close"], ref_h["Close"], dias, prudencia)
        except ValueError as e:
            error_escenarios = str(e)
    else:
        error_escenarios = "No pude cargar el índice de referencia."
    st.header(f"{nombre} ({ticker})")
    id_cab = conexiones.entidad(ticker, nombre)
    otros_tk = ()
    if id_cab:
        fila_cab = conexiones.cargar_base()[0]
        fila_cab = fila_cab[fila_cab["id"] == id_cab]
        otros_tk = tuple(t for t in fila_cab.iloc[0]["tickers"].split("|") if t and t.upper() != ticker.upper())
    with st.spinner("Consultando en qué índices cotiza…"):
        try:
            dentro, fallos = datos.indices_de(ticker, otros_tk)
        except Exception:  # noqa: BLE001
            dentro, fallos = [], list(datos.INDICES)
    if dentro:
        st.markdown("**Cotiza en los índices:** " + " ".join(f"`{i}`" for i in dentro))
    elif f.get("quoteType") in (None, "EQUITY") and not fallos:
        st.caption("No forma parte de ninguno de los 19 índices que consulto (S&P 500, Nasdaq-100, IBEX 35, Euro Stoxx 50, DAX, FTSE 100…).")

if area != "🏢 Empresa" and seccion not in ("🌍 Mapa mundial", "🌡️ Mercado", "🔍 Oportunidades"):
    st.header(sub or area)

# ----------------------------------------------------------------------------- MERCADO
if seccion == "🌡️ Mercado":
    st.header("📈 Hoy en el mercado")
    est = eventos.estado_bolsas()
    st.markdown(" · ".join(f"{r['Estado'].split()[0]} **{r['Bolsa']}** ({r['Horario (hora de Madrid)']})" for _, r in est.iterrows()))
    hoy = seguro(eventos.hoy_en_mercado, etiqueta="los datos de hoy")
    if hoy is not None and not hoy.empty:
        cols = st.columns(6)
        for i, fila in hoy.head(6).iterrows():
            cols[i % 6].metric(fila["Activo"], num(fila["Precio"]), f"{fila['Hoy'] * 100:+.2f}%".replace(".", ","),
                               help=f"Dato de las {fila['Hora del dato']} (hora de Madrid)")
        with st.expander("Más: Nikkei, petróleo, oro, euro/dólar, bitcoin y cómo abrió cada uno"):
            st.dataframe(hoy.drop(columns="Ticker"), hide_index=True, width="stretch", column_config={
                "Precio": st.column_config.NumberColumn(format="%.2f"),
                "Hoy": st.column_config.NumberColumn(format="percent"),
                "Apertura vs cierre anterior": st.column_config.NumberColumn("Abrió", format="percent")})
        st.caption("Precios con ~15 minutos de retraso (Yahoo Finance). Si una bolsa está cerrada, ves su cierre de la última sesión.")
    c1, c2 = st.columns([1, 3])
    lista_mov = c1.selectbox("Mayores subidas y bajadas de", ["IBEX 35", "Nasdaq-100", "Dow Jones", "Euro Stoxx 50", "DAX 40", "CAC 40",
                                                             "FTSE 100", "FTSE MIB"])
    try:
        mov = eventos.movimientos(tuple(datos.lista_indice(lista_mov)))
    except Exception:  # noqa: BLE001
        mov = pd.DataFrame()
    if not mov.empty:
        cfg_m = {"Precio": st.column_config.NumberColumn(format="%.2f"), "Hoy": st.column_config.NumberColumn(format="percent"),
                 "Apertura": st.column_config.NumberColumn(format="%.2f")}
        a, b = c2.columns(2)
        a.markdown("**🟢 Más suben**")
        a.dataframe(mov.head(5), hide_index=True, width="stretch", column_config=cfg_m)
        b.markdown("**🔴 Más bajan**" if (mov["Hoy"] < 0).any() else "**🟡 Menos suben** (hoy no baja ninguno)")
        b.dataframe(mov.tail(5).iloc[::-1], hide_index=True, width="stretch", column_config=cfg_m)
    st.subheader("🤝 Compras, fusiones y OPAs (últimos días)")
    ops = (eventos.operaciones_corporativas(None, "es", "ES") if idioma == "Español" else []) + eventos.operaciones_corporativas(None, "en", "US")
    if ops:
        for i in sorted(ops, key=lambda x: x["fecha"] or datetime.min, reverse=True)[:10]:
            hace = f"hace {((datetime.now() - i['fecha']).total_seconds() / 3600):.0f} h" if i["fecha"] else ""
            st.markdown(f"**[{i['operacion']}]** [{esc(i['titulo'])}]({i['enlace']}) — *{esc(i['fuente'])}* · {hace}")
        st.caption("Detectadas automáticamente en titulares de Google News (suelen aparecer con minutos u horas de retraso).")
    st.divider()
    termo = seguro(datos.termometro, etiqueta="el termómetro de mercado")
    if termo is not None and not termo.empty:
        st.info(datos.lectura_regimen(termo))
        cfg = {c: st.column_config.NumberColumn(c, format="%+.2f%%") for c in
               ("1 día %", "1 mes %", "En el año %", "vs media 200d %")}
        cfg["Último"] = st.column_config.NumberColumn("Último", format="%.2f")
        st.dataframe(termo.drop(columns="Símbolo"), hide_index=True, width="stretch", column_config=cfg)
        st.caption("«vs media 200d» indica cuánto cotiza por encima (+) o por debajo (−) de su media de 200 sesiones.")
    st.subheader("Noticias por tema")
    tema = st.selectbox("Tema", list(noticias.TEMAS))
    items = titulares(noticias.TEMAS_EN[tema] if usar_ia else noticias.TEMAS[tema], modo="activo")
    if items:
        r = noticias.resumen(items)
        st.caption(f"{r['n']} titulares · {r['positivas']} positivos · {r['negativas']} negativos (lectura automática orientativa)")
        lista_noticias(items[:15])

# ----------------------------------------------------------------------------- MAPA MUNDIAL
elif seccion == "🌍 Mapa mundial":
    st.markdown("<h2 style='text-align:center;margin:0 0 .4rem 0'>🌍 ¿Qué quieres ver?</h2>", unsafe_allow_html=True)
    st.session_state.setdefault("busqueda_inicio", "")
    busqueda = st.text_input("Buscador", key="busqueda_inicio", label_visibility="collapsed",
                             placeholder="Busca lo que quieras: petroleros, mina de oro, centrales nucleares, GNL, desastres… o una empresa: Nvidia, Repsol")
    ejemplos = ["Petroleros", "Minas de oro", "Minas de cobre", "Centrales nucleares", "Refinerías y GNL", "Desastres naturales"]
    for col, e in zip(st.columns(len(ejemplos)), ejemplos):
        col.button(e, key=f"ej_{e}", on_click=lambda e=e: st.session_state.update(busqueda_inicio=e), width="stretch")
    sugeridas = mundo.interpretar_busqueda(busqueda)
    if busqueda.strip():
        empresas_b = seguro(datos.buscar, busqueda, etiqueta="la búsqueda de empresas") or []
        if sugeridas:
            empresas_b = [r for r in empresas_b if busqueda.strip().lower() in r["nombre"].lower()]
        if empresas_b:
            st.markdown("**📈 Empresas y valores que coinciden** (pincha para abrirlos):")
            for col, r in zip(st.columns(min(len(empresas_b), 4)), empresas_b[:4]):
                col.button(f"{r['symbol']} · {r['nombre'][:32]}", key=f"ini_{r['symbol']}", on_click=abrir_empresa,
                           args=(r["symbol"],), width="stretch")
        elif not sugeridas:
            st.info(f"No he encontrado capas del mapa ni empresas con «{busqueda}». Prueba con «petroleros», «mina de cobre», "
                    "«centrales nucleares», «GNL», «terremotos» o el nombre de una empresa.")
    c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 2, 2])
    capas_sel = c1.multiselect("Capas en el mapa", mundo.CAPAS, default=sugeridas, key=f"capas_{busqueda}",
                               placeholder="Elige capas o usa el buscador")
    color_paises = c2.selectbox("Colorear países por", ["Economía: crecimiento (semáforo)", "Bolsa del país en el año",
                                                        "Inflación", "Paro", "Deuda pública", "Nada"])
    vista = c3.radio("Vista", ["Globo terráqueo", "Mapa plano"], horizontal=True)
    min_mw = c4.select_slider("Centrales: potencia mínima (MW)", [0, 50, 100, 300, 500, 1000], value=300)
    todas_minas = c5.toggle("Minas: incluir todas las registradas", value=False,
                            help="Apagado: solo las grandes minas de la base del programa. Encendido: añade todas las de Wikidata "
                                 "(miles, incluidas pequeñas o históricas).")

    # --- países
    coropleta, eco, fuente_eco, bolsa = None, None, "", None
    with st.spinner("Cargando datos de países…"):
        try:
            eco, fuente_eco = mundo.economia()
        except Exception as e:  # noqa: BLE001
            st.warning(f"No pude cargar los datos económicos ({type(e).__name__}).")
        if color_paises == "Bolsa del país en el año":
            cierres_paises = seguro(datos.cierres, tuple(mundo.ETF_PAIS.values()), "1y", etiqueta="la bolsa por país")
            bolsa = mundo.bolsa_por_pais(cierres_paises) if cierres_paises is not None else None
    if eco is not None and color_paises != "Nada":
        base = eco.merge(bolsa, on="iso3", how="left") if bolsa is not None and not bolsa.empty else eco.assign(bolsa_anio=np.nan)
        if color_paises.startswith("Economía"):
            base = base.assign(valor=base["crecimiento"].map(lambda x: 1 if x >= 2 else -1 if x < 0 else 0))
            base["texto"] = base.apply(lambda r: f"<b>{r['pais']}</b><br>{mundo.semaforo(r['crecimiento'])}: PIB {r['crecimiento']:+.1f}%"
                                       + (f"<br>Inflación {r['inflacion']:.1f}%" if pd.notna(r.get("inflacion")) else "")
                                       + (f"<br>⚠️ {', '.join(mundo.senales_crisis(r))}" if mundo.senales_crisis(r) else ""), axis=1)
            coropleta, modo = base, "semaforo"
        elif color_paises == "Bolsa del país en el año":
            b = base.dropna(subset=["bolsa_anio"])
            coropleta = b.assign(valor=b["bolsa_anio"].clip(-40, 40),
                                 texto=b.apply(lambda r: f"<b>{r['pais']}</b><br>Bolsa en el año: {r['bolsa_anio']:+.1f}% ({r['etf']}, en USD)", axis=1))
            modo = "RdYlGn"
        else:
            col = {"Inflación": "inflacion", "Paro": "paro", "Deuda pública": "deuda"}[color_paises]
            b = base.dropna(subset=[col])
            limite = {"inflacion": 30, "paro": 25, "deuda": 150}[col]
            coropleta = b.assign(valor=b[col].clip(upper=limite),
                                 texto=b.apply(lambda r: f"<b>{r['pais']}</b><br>{color_paises}: {r[col]:.1f}%", axis=1))
            modo = "RdYlGn_r"
    else:
        modo = ""

    # --- capas de puntos
    capas, tablas, avisos_capa = {}, {}, []
    clave = mundo.activos_clave()
    with st.spinner("Cargando capas…"):
        for capa in capas_sel:
            try:
                if capa.startswith("Minas de "):
                    mineral = capa.replace("Minas de ", "")
                    grandes = clave[(clave["tipo"] == "mina") & (clave["subtipo"].str.contains(mineral.rstrip("s")[:5], case=False))]
                    df = grandes.assign(texto=grandes.apply(lambda r: f"<b>{r['nombre']}</b> ({r['pais']})<br>{r['operador']} {r['ticker']}"
                                                            f"<br>{r['detalle']}", axis=1), size=14)
                    if todas_minas:
                        w = mundo.minas_wikidata(mineral)
                        if not w.empty:
                            w = w.assign(texto=w.apply(lambda r: f"{r['nombre']} ({r['pais']})<br>{r['operador']}", axis=1), size=6)
                            df = pd.concat([df, w], ignore_index=True)
                    capas[capa] = df
                    tablas[capa] = df.drop(columns=["texto", "tam", "size"], errors="ignore")
                elif capa.startswith("Centrales: "):
                    comb = mundo.COMBUSTIBLES[capa.replace("Centrales: ", "")]
                    c = mundo.centrales_mundo()
                    c = c[(c["combustible"] == comb) & (c["potencia_mw"] >= min_mw)]
                    capas[capa] = c.assign(tam=c["potencia_mw"], texto=c.apply(
                        lambda r: f"<b>{r['nombre']}</b> ({r['pais']})<br>{r['potencia_mw']:,.0f} MW"
                                  + (f"<br>{r['operador']}" if isinstance(r["operador"], str) else ""), axis=1))
                    tablas[capa] = c.sort_values("potencia_mw", ascending=False)
                elif capa == "Refinerías de petróleo" or capa.startswith("Terminales de GNL"):
                    if capa.startswith("Refinerías"):
                        df = clave[clave["tipo"] == "refineria"]
                    else:
                        df = clave[(clave["tipo"] == "gnl") & (clave["subtipo"] == ("exportación" if "export" in capa else "importación"))]
                    capas[capa] = df.assign(texto=df.apply(lambda r: f"<b>{r['nombre']}</b> ({r['pais']})<br>{r['operador']} {r['ticker']}"
                                                           f"<br>{r['detalle']}", axis=1))
                    tablas[capa] = df
                elif capa == "Petroleros: escalas por puerto":
                    pp = mundo.petroleros_por_puerto(7)
                    if not pp.empty:
                        capas[capa] = pp.assign(tam=pp["petroleros"], texto=pp.apply(
                            lambda r: f"<b>{r['portname']}</b> ({r['country']})<br>{int(r['petroleros'])} escalas de petroleros en 7 días"
                                      f"<br>carga {int(r['exporta'] or 0)} · descarga {int(r['importa'] or 0)} (estim.)<br>hasta {r['ultimo']}", axis=1))
                        tablas[capa] = pp[["portname", "country", "petroleros", "exporta", "importa", "ultimo"]].rename(
                            columns={"portname": "puerto", "country": "país", "petroleros": "escalas de petroleros (7 días)",
                                     "exporta": "carga (estim.)", "importa": "descarga (estim.)", "ultimo": "último dato"})
                elif capa == "Petroleros: tránsito por estrechos":
                    cat = energia.estrechos()
                    pasos = energia.pasos_diarios(tuple(cat["portid"]), 60)
                    res = energia.resumen_estrechos(pasos)
                    m = cat.merge(res, left_on="nombre_es", right_on="Estrecho")
                    capas[capa] = m.assign(tam=m["Petroleros/día"], texto=m.apply(
                        lambda r: f"<b>{r['nombre_es']}</b><br>{r['Petroleros/día']:.1f} petroleros/día"
                                  f" ({r['Petroleros vs 4 sem previas %']:+.0f}% vs 4 semanas previas)<br>{r['Buques/día']:.0f} buques/día", axis=1))
                    tablas[capa] = res
                elif capa == "Alertas: desastres naturales":
                    al = mundo.alertas(30)
                    if not al.empty:
                        capas[capa] = al.assign(color=al["nivel"].map({"Red": "#d00000", "Orange": "#f77f00"}),
                                                texto=al.apply(lambda r: f"<b>{r['tipo']}</b> · alerta {'roja' if r['nivel'] == 'Red' else 'naranja'}"
                                                               f"<br>{r['nombre'][:90]}<br>desde {r['desde']}", axis=1))
                        tablas[capa] = al[["tipo", "nivel", "nombre", "desde", "url"]]
            except Exception as e:  # noqa: BLE001
                avisos_capa.append(f"{capa}: no disponible ahora ({type(e).__name__})")
        rutas = None
        if "Rutas marítimas principales" in capas_sel:
            try:
                rutas = mundo.rutas_maritimas()
            except Exception as e:  # noqa: BLE001
                avisos_capa.append(f"Rutas marítimas: no disponibles ahora ({type(e).__name__})")
    if "ais" in st.session_state and st.session_state["ais"] is not None and not st.session_state["ais"].empty:
        a = st.session_state["ais"]
        capas["Buques en directo"] = a.assign(color=a["categoria"].map({"Petrolero": "#e63946", "Carguero": "#457b9d", "Pasaje": "#2a9d8f"}).fillna("#adb5bd"),
                                              texto=a.apply(lambda r: f"<b>{r['nombre'] or r['mmsi']}</b> · {r['categoria']}<br>{r['velocidad_nudos']} nudos"
                                                            + (f" → {r['destino']}" if r['destino'] else ""), axis=1))
    for a in avisos_capa:
        st.caption("⚠️ " + a)

    centro = st.session_state.get("centro_globo")
    evento = st.plotly_chart(graficos.fig_mundo(capas, coropleta, modo, rutas, vista == "Globo terráqueo", centro),
                             width="stretch", on_select="rerun", selection_mode="points", key="mapa_mundo",
                             config={"scrollZoom": True})
    st.caption("Arrastra para girar el globo y usa la rueda para acercar. Pincha en un país para ver su ficha. "
               + (f"Economía: {fuente_eco}. " if fuente_eco else "")
               + "Ubicaciones aproximadas; los datos de petroleros llevan unos días de retraso.")

    # --- ficha de país
    if eco is not None:
        puntos = evento.selection.points if evento and evento.selection else []
        iso_click = next((p.get("location") for p in puntos if p.get("location")), None)
        nombres = eco.sort_values("pais").set_index("iso3")["pais"]
        opciones = list(nombres.index)
        por_defecto = iso_click or st.session_state.get("pais_ficha") or ("ESP" if "ESP" in opciones else opciones[0])
        iso = st.selectbox("🔎 Ficha de país", opciones, index=opciones.index(por_defecto) if por_defecto in opciones else 0,
                           format_func=lambda i: nombres.get(i, i), key=f"pais_{iso_click}")
        st.session_state["pais_ficha"] = iso
        fila = eco[eco["iso3"] == iso].iloc[0]
        if bolsa is None and iso in mundo.ETF_PAIS:  # solo el ETF de este país
            c_etf = seguro(datos.cierres, (mundo.ETF_PAIS[iso],), "1y", etiqueta="la bolsa del país")
            bolsa = mundo.bolsa_por_pais(c_etf) if c_etf is not None else None
        b = bolsa[bolsa["iso3"] == iso] if bolsa is not None and not bolsa.empty else pd.DataFrame()
        st.subheader(f"{fila['pais']} · {mundo.semaforo(fila['crecimiento'])}")
        m = st.columns(5)
        m[0].metric("Crecimiento del PIB", f"{fila['crecimiento']:+.1f}%".replace(".", ","),
                    (f"{fila['crecimiento'] - fila['crecimiento_previo']:+.1f} pts vs año anterior".replace(".", ",")
                     if pd.notna(fila.get("crecimiento_previo")) else None))
        m[1].metric("Inflación", f"{fila['inflacion']:.1f}%".replace(".", ",") if pd.notna(fila.get("inflacion")) else "—")
        m[2].metric("Paro", f"{fila['paro']:.1f}%".replace(".", ",") if pd.notna(fila.get("paro")) else "—")
        m[3].metric("Deuda pública", f"{fila['deuda']:.0f}% PIB" if pd.notna(fila.get("deuda")) else "—")
        m[4].metric("Bolsa en el año", f"{b['bolsa_anio'].iloc[0]:+.1f}%".replace(".", ",") if not b.empty else "—",
                    f"ETF {b['etf'].iloc[0]} (USD)" if not b.empty else None, delta_color="off")
        crisis = mundo.senales_crisis(fila)
        if crisis:
            st.warning("Señales de crisis: " + ", ".join(crisis) + ".")
        try:
            al = mundo.alertas(30)
            nombre_en = str(fila.get("pais_en") or fila["pais"]).split(",")[0]
            al_pais = al[al["pais"].str.contains(nombre_en, case=False, na=False, regex=False)] if not al.empty else al
            for r in al_pais.itertuples():
                st.markdown(f"🚨 **{r.tipo}** (alerta {'roja' if r.nivel == 'Red' else 'naranja'}) desde {r.desde} · [informe]({r.url})")
        except Exception:  # noqa: BLE001
            pass
        activos_pais = clave[clave["iso3"] == iso]
        if not activos_pais.empty:
            etiqueta_tipo = {"refineria": "refinería", "gnl": "GNL", "mina": "mina"}
            st.markdown("**Infraestructura clave en el país:** " + " · ".join(
                f"{r.nombre} ({etiqueta_tipo.get(r.tipo, r.tipo)}{' de ' + r.subtipo if r.tipo == 'mina' else ''})" for r in activos_pais.itertuples()))
        with st.expander(f"📰 Noticias de la economía de {fila['pais']}"):
            lista_noticias(titulares(f"{fila.get('pais_en') or fila['pais']} economy" if usar_ia else f"economía {fila['pais']}", modo="activo")[:10])

    # --- mercado relacionado
    materias, empresas = mundo.mercado_de(capas_sel)
    if materias or empresas:
        st.subheader("💹 Mercado relacionado con lo que estás viendo")
        if materias:
            cm = seguro(datos.cierres, tuple(materias.values()), "1y", etiqueta="las materias primas")
            if cm is not None and not cm.empty:
                cols = st.columns(len(materias))
                for col, (nom, sim) in zip(cols, materias.items()):
                    if sim in cm and cm[sim].notna().sum() > 22:
                        x = cm[sim].dropna()
                        col.metric(nom, num(float(x.iloc[-1])), f"{(x.iloc[-1] / x.iloc[-22] - 1) * 100:+.1f}% en 1 mes".replace(".", ","))
        if empresas:
            ce = seguro(datos.cierres, tuple(empresas), "1y", etiqueta="las empresas relacionadas")
            if ce is not None and not ce.empty:
                filas_e = []
                for t in empresas:
                    if t in ce and ce[t].notna().sum() > 22:
                        x = ce[t].dropna()
                        previos = x[x.index.year < x.index[-1].year]
                        filas_e.append({"Ticker": t, "Precio": float(x.iloc[-1]), "1 mes": float(x.iloc[-1] / x.iloc[-22] - 1),
                                        "En el año": float(x.iloc[-1] / (previos.iloc[-1] if len(previos) else x.iloc[0]) - 1)})
                st.dataframe(pd.DataFrame(filas_e), hide_index=True, width="stretch", column_config={
                    "Precio": st.column_config.NumberColumn(format="%.2f"),
                    "1 mes": st.column_config.NumberColumn(format="percent"),
                    "En el año": st.column_config.NumberColumn(format="percent")})
                st.caption("Escribe uno de estos tickers en la barra lateral para analizarlo a fondo.")

    # --- tablas
    if tablas:
        with st.expander("📋 Ver los datos de cada capa"):
            for nombre_t, tabla_t in tablas.items():
                st.markdown(f"**{nombre_t}** ({len(tabla_t)})")
                st.dataframe(tabla_t.head(300), hide_index=True, width="stretch")

    # --- buques en directo
    with st.expander("🛰️ Buques en directo (opcional, clave gratuita de aisstream.io)"):
        st.markdown("Muestra la **posición real** de los buques en una zona durante unos segundos, con los petroleros en rojo. "
                    "Necesitas una clave gratuita: entra en **aisstream.io**, regístrate (con tu cuenta de GitHub) y copia tu *API key*. "
                    "Se guarda solo en tu ordenador.")
        clave_guardada = config.leer_clave("aisstream")
        clave_ais = st.text_input("Clave de aisstream.io", value=clave_guardada, type="password")
        zonas_ais = {"Estrecho de Gibraltar": (35.5, -6.5, 36.6, -4.8), "Estrecho de Ormuz": (25.5, 55.5, 27.2, 57.5),
                     "Canal de la Mancha": (49.8, -2.0, 51.5, 2.0), "Estrecho de Malaca / Singapur": (0.8, 102.5, 2.5, 104.5),
                     "Canal de Suez y norte del Mar Rojo": (27.5, 32.0, 31.5, 34.0), "Golfo de México (Texas-Luisiana)": (27.5, -95.5, 30.0, -88.5),
                     "Róterdam y Amberes": (51.2, 3.3, 52.2, 4.6), "Costa de Cataluña y Castellón": (39.8, 0.0, 41.6, 3.3)}
        c1, c2 = st.columns(2)
        zona = c1.selectbox("Zona", list(zonas_ais))
        segundos = c2.select_slider("Escuchar durante (segundos)", [20, 45, 90, 180], value=45)
        if st.button("📡 Ver buques ahora") and clave_ais:
            config.guardar_clave("aisstream", clave_ais)
            with st.spinner(f"Recibiendo posiciones durante {segundos} s…"):
                try:
                    st.session_state["ais"] = mundo.ais_directo(clave_ais, zonas_ais[zona], segundos)
                    z = zonas_ais[zona]
                    st.session_state["centro_globo"] = ((z[0] + z[2]) / 2, (z[1] + z[3]) / 2)
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.warning(f"No pude conectar con aisstream.io: {e}")
        a = st.session_state.get("ais")
        if a is not None:
            if a.empty:
                st.info("No llegó ninguna posición. Prueba más segundos o revisa la clave.")
            else:
                cnt = a["categoria"].value_counts().to_dict()
                st.markdown(f"**{len(a)} buques** recibidos · " + " · ".join(f"{k}: {v}" for k, v in cnt.items()))
                st.caption("El tipo de buque llega en un mensaje aparte cada pocos minutos: con más segundos de escucha se identifican más petroleros.")
                st.dataframe(a.drop(columns=["tipo_ais"]), hide_index=True, width="stretch")
                if st.button("Quitar buques del mapa"):
                    st.session_state["ais"], st.session_state["centro_globo"] = None, None
                    st.rerun()

# ----------------------------------------------------------------------------- ANÁLISIS, NEGOCIO, MAPA DE CALOR
elif seccion == "🧠 Análisis":
    vistas.analisis(ticker, f, h, nombre, ref_h["Close"] if (ref_h is not None and not ref_h.empty) else None, prudencia, (leng, pais))

elif seccion == "💼 Negocio":
    vistas.pantalla_negocio(ticker, f, nombre, abrir_empresa)

elif seccion == "🟩 Mapa de calor":
    vistas.pantalla_calor(abrir_empresa)

elif seccion == "📌 Picks del día":
    vistas3.pantalla_picks(abrir_empresa)

elif seccion == "💡 Ideas":
    vistas3.pantalla_ideas(abrir_empresa)

elif seccion == "🪙 Cripto":
    vistas4.pantalla_cripto()

elif seccion == "📊 Macro":
    vistas2.pantalla_macro()

elif seccion == "🖥️ Monitor":
    vistas2.pantalla_monitor(abrir_empresa)

elif seccion == "🧮 Buscador":
    vistas2.pantalla_buscador(abrir_empresa)

elif seccion == "🧺 Cartera":
    pes_plan, pes_cartera = st.tabs(["📅 Plan mensual", "🧺 Lo que ya tengo"])
    with pes_plan:
        vistas4.pantalla_plan(abrir_empresa)
    with pes_cartera:
        vistas2.pantalla_cartera(abrir_empresa)

elif seccion == "🔬 Profundizar":
    vistas2.pantalla_profundizar(ticker, f, precio)

# ----------------------------------------------------------------------------- EMPRESA
elif seccion == "🏢 Empresa":
    vivo = seguro(eventos.ultimo_precio, ticker, etiqueta="el último precio")
    if vivo:
        precio_vivo, var_vivo = vivo["precio"], vivo["var_dia"]
    else:
        precio_vivo = precio
        var_vivo = precio / float(h["Close"].iloc[-2]) - 1 if len(h) > 1 else 0
    c = st.columns(5)
    c[0].metric("Precio", f"{num(precio_vivo)} {moneda}", f"{var_vivo * 100:+.2f}% hoy".replace(".", ",") if pd.notna(var_vivo) else None)
    c[1].metric("Capitalización", grande(f.get("marketCap"), moneda))
    c[2].metric("PER actual / previsto", f"{num(f.get('trailingPE'), 1)} / {num(f.get('forwardPE'), 1)}")
    c[3].metric("Rentab. por dividendo", pct(f.get("rend_dividendo"), 2, signo=False))
    c[4].metric("Rango 52 semanas", f"{num(f.get('fiftyTwoWeekLow'), 0)} – {num(f.get('fiftyTwoWeekHigh'), 0)}")
    st.plotly_chart(graficos.fig_precio(h), width="stretch")
    st.caption(" · ".join(x for x in (f.get("sector"), f.get("industry"), f.get("country")) if x))
    if vivo:
        st.caption("🕒 " + eventos.texto_frescura(vivo, ticker)
                   + (f" · abrió en {num(vivo['apertura'])} · rango del día {num(vivo['minimo'])}–{num(vivo['maximo'])}" if vivo.get("apertura") else ""))

    st.subheader("Qué está pasando con la empresa")
    ag = seguro(eventos.agenda, [ticker], 120, etiqueta="la agenda")
    if ag is not None and not ag.empty:
        st.markdown("**📅 Próximos eventos:** " + " · ".join(f"{r['Evento']} el {r['Fecha']:%d/%m/%Y} (en {r['Faltan (días)']} días)"
                                                         for _, r in ag.iterrows()))
    with st.expander("🤝 Compras, fusiones, OPAs y ventas en las noticias (7 días)"):
        ops_e = eventos.operaciones_corporativas(nombre_corto, "es", "ES") + eventos.operaciones_corporativas(nombre_corto, "en", "US")
        if ops_e:
            for i in sorted(ops_e, key=lambda x: x["fecha"] or datetime.min, reverse=True)[:12]:
                fecha_txt = f" · {i['fecha']:%d/%m %H:%M}" if i["fecha"] else ""
                st.markdown(f"**[{i['operacion']}]** [{esc(i['titulo'])}]({i['enlace']}) — *{esc(i['fuente'])}*{fecha_txt}")
        else:
            st.caption("No hay titulares de operaciones corporativas sobre esta empresa en los últimos 7 días.")
    with st.expander("👔 Directivos: ¿compran o venden acciones de su empresa?"):
        dirs = seguro(eventos.directivos, ticker, etiqueta="las operaciones de directivos")
        if dirs and not dirs[0].empty:
            tabla_d, res_d = dirs
            m = st.columns(3)
            m[0].metric("Compras en mercado (6 meses)", res_d.get("compras_mercado_6m", 0))
            m[1].metric("Ventas en mercado (6 meses)", res_d.get("ventas_mercado_6m", 0))
            if pd.notna(res_d.get("neto_acc", np.nan)):
                m[2].metric("Saldo neto de acciones (6 meses)", f"{res_d['neto_acc']:+,.0f}".replace(",", "."))
            st.caption("Que un directivo **compre** con su dinero suele leerse como señal de confianza. Las **ventas** son más "
                       "habituales (impuestos, diversificación) y dicen menos. Las concesiones y opciones son parte de su sueldo.")
            st.dataframe(tabla_d.head(40), hide_index=True, width="stretch", column_config={
                "Acciones": st.column_config.NumberColumn(format="%d"), "Importe": st.column_config.NumberColumn(format="%.0f")})
        else:
            st.caption("Sin datos de directivos para este valor (Yahoo los ofrece sobre todo para empresas de EE. UU.).")
    with st.expander("📑 Comunicados oficiales a la SEC (empresas que cotizan en EE. UU.)"):
        if "@" not in config.sec_ua():
            st.caption("Para verlos, guarda tu nombre y correo para la SEC en la sección 🕸️ Conexiones (lo exige la SEC).")
        else:
            cik_e = seguro(suministro.cik_de, ticker, etiqueta="el registro de la SEC")
            if cik_e:
                com = seguro(eventos.comunicados_sec, cik_e, 30, etiqueta="los comunicados de la SEC")
                if com is not None and not com.empty:
                    st.dataframe(com, hide_index=True, width="stretch", column_config={
                        "Documento": st.column_config.LinkColumn("Documento", display_text="abrir")})
                    st.caption("Se publican en cuanto la empresa los presenta. Los más útiles: 8-K (hechos relevantes), "
                               "SC 13D/13G (alguien supera el 5 %), SC TO-T (OPA), S-4/425 (fusiones).")
            else:
                st.caption("Esta empresa no presenta informes en la SEC. Para empresas españolas, los hechos relevantes están en la CNMV (cnmv.es).")

    if fallos:
        st.caption(f"No pude consultar estos índices: {', '.join(fallos)}.")

    st.subheader("Qué esperan los analistas")
    objetivos = {"Objetivo bajo": f.get("targetLowPrice"), "Objetivo medio": f.get("targetMeanPrice"),
                 "Objetivo alto": f.get("targetHighPrice")}
    if any(objetivos.values()):
        cols = st.columns(4)
        for col, (k, v) in zip(cols, objetivos.items()):
            if v:
                col.metric(k, f"{num(v)} {moneda}", f"{(v / precio - 1) * 100:+.1f}% vs hoy".replace(".", ","))
            else:
                col.metric(k, "—")
        cols[3].metric("Consenso", RECOMENDACION.get(f.get("recommendationKey"), "—"),
                       f"{f.get('numberOfAnalystOpinions') or 0} analistas")
    else:
        st.caption("Yahoo no tiene precios objetivo de analistas para este valor.")

    if f.get("longBusinessSummary"):
        with st.expander("Qué hace la empresa"):
            st.write(f["longBusinessSummary"])
    with st.expander("Principales accionistas institucionales"):
        acc = seguro(datos.accionistas, ticker, etiqueta="los accionistas")
        if acc is not None and not acc.empty:
            st.dataframe(acc, hide_index=True, width="stretch")
        else:
            st.caption("Sin datos de accionistas para este valor.")
    ficha_csv = pd.DataFrame({"campo": ["Empresa", "Ticker", "Sector", "Industria", "País", "Precio", "Moneda",
                                        "Capitalización", "Índices"],
                              "valor": [nombre, ticker, f.get("sector"), f.get("industry"), f.get("country"), precio,
                                        moneda, f.get("marketCap"), ", ".join(dentro)]})
    st.download_button("⬇️ Descargar ficha (CSV)", ficha_csv.to_csv(index=False).encode("utf-8"),
                       f"ficha_{ticker}.csv", "text/csv")

# ----------------------------------------------------------------------------- ESCENARIOS
elif seccion == "🎯 Escenarios":
    if res is None:
        st.warning(error_escenarios or "No pude calcular los escenarios.")
    else:
        st.caption(
            f"Referencia: {ref_ticker} · {res['dias_muestra']} días de histórico común · "
            f"{res['pct_dias_alcistas'] * 100:.0f}% de los días fueron de mercado alcista · "
            f"beta {num(res['beta'])} (en días de caída: {num(res['beta_bajista'])})")
        filas = []
        for clave in ("alcista", "mixto", "bajista"):
            e = res["escenarios"][clave]
            p = e["percentiles"]
            filas.append({
                "Escenario": escenarios.NOMBRES[clave],
                "Pesimista (P10)": f"{num(p[10])} ({pct(p[10] / precio - 1)})",
                "Mediano (P50)": f"{num(p[50])} ({pct(p[50] / precio - 1)})",
                "Optimista (P90)": f"{num(p[90])} ({pct(p[90] / precio - 1)})",
                "Prob. de pérdida": pct(e["prob_perdida"], 0, signo=False),
                "Caída máx. típica": pct(e["caida_max_mediana"], 0),
                "Volatilidad anual": pct(e["vol_anual"], 0, signo=False),
            })
        st.subheader(f"Dónde podría estar en {horizonte}")
        st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")
        for aviso in res["avisos"]:
            st.caption("⚠️ " + aviso)
        st.plotly_chart(graficos.fig_abanico(res, {"Objetivo analistas (medio)": f.get("targetMeanPrice")}),
                        width="stretch")
        st.subheader("Prueba de estrés: ¿y si el mercado se desploma?")
        est = escenarios.estres(precio, res["beta"], res["beta_bajista"])
        if not est.empty:
            st.dataframe(est, hide_index=True, width="stretch", column_config={
                "Caída del índice": st.column_config.NumberColumn(format="percent"),
                "Caída estimada de la acción": st.column_config.NumberColumn(format="percent"),
                "Precio estimado": st.column_config.NumberColumn(format="%.2f")})
            st.caption("Aproximación lineal con la beta de días de caída. En crisis reales las correlaciones suelen subir.")
        with st.expander("Cómo leer esto (y qué no es)"):
            st.markdown(
                "- **P10 / P50 / P90**: en 10 de cada 100 caminos simulados el precio acaba por debajo del pesimista, "
                "en 50 por debajo del mediano y en 90 por debajo del optimista.\n"
                "- Los escenarios **alcista/bajista** usan solo días en los que el índice estaba por encima/debajo de su media de "
                "200 sesiones; el **histórico completo** mezcla ambos.\n"
                "- Se basan en lo que ocurrió en el pasado (5 años). **No incluyen resultados, noticias ni cambios de ciclo futuros.**\n"
                "- Con prudencia al 100 % la rentabilidad esperada sale de la beta, no del pasado de la acción.")

# ----------------------------------------------------------------------------- NOTICIAS
elif seccion == "📰 Noticias":
    consulta = st.text_input("Buscar noticias de", conexiones.nombre_corto(nombre_corto).title() if nombre_corto.isupper() else conexiones.nombre_corto(nombre_corto))
    c_n1, c_n2 = st.columns([3, 1])
    c_n1.caption("Solo salen noticias de economía y mercados: se descartan deporte, espectáculos, sucesos… "
                 "(buscar «oro» ya no trae el Balón de Oro).")
    todo = c_n2.toggle("Ver todo sin filtrar", value=False)
    items = titulares(consulta, modo="todo" if todo else "empresa" if conexiones._mismo(consulta, nombre_corto) else "auto")
    if items:
        r = noticias.resumen(items)
        c = st.columns(3)
        c[0].metric("Titulares (7 días)", r["n"])
        c[1].metric("Positivos / negativos", f"{r['positivas']} / {r['negativas']}")
        c[2].metric("Tono medio", f"{r['media']:+.2f}".replace(".", ","))
        st.caption("Tono calculado con IA (FinBERT) sobre titulares en inglés." if usar_ia else
                   "El tono se calcula con palabras clave en el titular: es una pista, no un análisis. Activa la IA en la barra lateral.")
        lista_noticias(items)
    elif items == []:
        st.info("No hay titulares recientes con esa búsqueda.")
    if f.get("industry"):
        with st.expander(f"Sector: {f['industry']}"):
            sector_items = titulares(f["industry"], "las noticias del sector", "activo")
            lista_noticias(sector_items[:10])

# ----------------------------------------------------------------------------- CADENA DE SUMINISTRO
elif seccion == "🕸️ Conexiones":
    st.markdown("A quién le **compra** (proveedores, izquierda) y a quién le **vende** (clientes, derecha). "
                "**Pincha en cualquier empresa** del mapa para ver sus propias conexiones.")
    id_base = conexiones.entidad(ticker, nombre)
    centro_nombre = conexiones.ficha_entidad(id_base)["nombre"] if id_base else conexiones.nombre_corto(nombre_corto)
    c1, c2, c3 = st.columns([2, 1, 1])
    centro_nombre = c1.text_input("Empresa en el centro del mapa", st.session_state.get("centro_mapa") or centro_nombre,
                                  help="Puedes escribir cualquier empresa, también privadas (p. ej. OpenAI) o que no coticen.")
    profundidad = c2.radio("Niveles", [1, 2], horizontal=True, help="2 = también los proveedores de sus proveedores y los clientes de sus clientes.")
    usar_sec = c3.toggle("Añadir hallazgos de informes SEC", value=True)
    extra = []
    clave_sec = conexiones.nombre_corto(centro_nombre).lower()
    if usar_sec and st.session_state.get("menciones", {}).get(clave_sec) is not None:
        extra.append(conexiones.aristas_desde_sec(st.session_state["menciones"][clave_sec], centro_nombre))
    ev_guardado = st.session_state.get("evidencias")
    if usar_sec and ev_guardado and ev_guardado[0] == ticker and conexiones._mismo(centro_nombre, nombre_corto):
        extra.append(conexiones.aristas_desde_informe_propio(ev_guardado[1], centro_nombre))
    rel = conexiones.unificar(suministro.cargar_relaciones(), pd.concat(extra) if extra else None)
    G, niveles, centro = conexiones.grafo(rel, centro_nombre, profundidad)

    if G is not None and G.number_of_edges():
        tickers_nodos = {n: conexiones.ticker_por_nombre(conexiones.real(n)) for n in G.nodes}
        evento = st.plotly_chart(graficos.fig_conexiones(G, niveles, centro, tickers_nodos), width="stretch",
                                 on_select="rerun", selection_mode="points", key=f"mapa_{centro}_{profundidad}")
        puntos = [p for p in (evento.selection.points if evento and evento.selection else []) if p.get("customdata")]
        if puntos and conexiones.real(puntos[0]["customdata"]) != centro:  # pinchar en una empresa la pone en el centro
            st.session_state["centro_mapa"] = conexiones.real(puntos[0]["customdata"])
            st.rerun()
        if not conexiones._mismo(centro, nombre_corto):
            tk_c = tickers_nodos.get(centro, "")
            b1, b2 = st.columns(2)
            b1.button(f"🔎 Analizar {centro} en todo el programa" + (f" ({tk_c})" if tk_c else ""),
                      on_click=abrir_empresa, args=(tk_c or centro,))
            b2.button(f"↩️ Volver a {conexiones.nombre_corto(nombre_corto)}",
                      on_click=lambda: st.session_state.update(centro_mapa=None))
        prov, cli = conexiones.vecinos(rel, centro)
        cfg_rel = {"que": st.column_config.TextColumn("Qué", width="large"), "fuente": "Fuente", "confianza": "Confianza"}
        c1, c2 = st.columns(2)
        c1.markdown(f"**⬅ Le venden a {centro}** ({len(prov)})")
        c1.dataframe(prov[["proveedor", "que", "fuente", "confianza"]].rename(columns={"proveedor": "Proveedor"}),
                     hide_index=True, width="stretch", column_config=cfg_rel)
        c2.markdown(f"**Le compran a {centro} ➡** ({len(cli)})")
        c2.dataframe(cli[["cliente", "que", "fuente", "confianza"]].rename(columns={"cliente": "Cliente"}),
                     hide_index=True, width="stretch", column_config=cfg_rel)
        if len(cli) == 0 or len(prov) == 0:
            lado = "clientes" if len(cli) == 0 else "proveedores"
            st.info(f"No tengo {lado} guardados de {centro}. Suele pasar con empresas que venden sobre todo a particulares "
                    "(Apple, Tesla, Inditex…) o a miles de anunciantes (Meta, Google): no tienen un cliente grande que nombrar "
                    "y por ley solo deben publicar los que superan el 10 % de sus ventas. Prueba **Buscar en informes de otras "
                    "empresas** (abajo) o apúntalos en tu tabla.")
        st.caption("Confianza: **alta** = relación pública y conocida · **media** = informada, conviene verificar · "
                   "**inferida** = deducida automáticamente de un informe (lee la frase) · **tuya** = la añadiste tú.")
    else:
        st.info(f"No tengo conexiones guardadas de «{centro_nombre}». Pulsa abajo **Buscar en informes de otras empresas** "
                "para encontrarlas automáticamente, o añádelas en tu tabla.")
        if st.session_state.get("centro_mapa"):
            st.button("↩️ Volver a la empresa abierta", on_click=lambda: st.session_state.update(centro_mapa=None))

    st.subheader("🔎 Buscar en informes de otras empresas")
    st.caption("Busca en los informes anuales (10-K / 20-F) de los últimos 16 meses de todas las empresas que cotizan en EE. UU. "
               "cuáles nombran a esta empresa, y deduce si son sus clientes, proveedores o competidores leyendo la frase. "
               "Es automático: revisa la frase antes de fiarte. Tarda 30–60 s la primera vez; luego queda guardado una semana.")
    if "@" not in config.sec_ua():
        st.info("La SEC exige identificarse con nombre y correo en cada consulta. Se guarda solo en tu ordenador.")
        contacto = st.text_input("Tu nombre y correo para la SEC", placeholder="Nombre Apellido tu_correo@dominio.com")
        if st.button("Guardar contacto") and "@" in contacto:
            config.guardar_sec_contacto(contacto)
            st.rerun()
    else:
        c1, c2 = st.columns([2, 1])
        termino = c1.text_input("Nombre a buscar en los informes", conexiones.nombre_corto(centro_nombre),
                                help="Usa el nombre con el que suele aparecer escrito (p. ej. «NVIDIA», «Visa», «General Motors»).")
        cuantas = c2.select_slider("Empresas a leer", [10, 15, 25, 40], value=15)
        if st.button(f"🔎 Buscar quién nombra a «{termino}»"):
            with st.spinner("Buscando y leyendo informes…"):
                try:
                    cik_propio = suministro.cik_de(ticker) if conexiones._mismo(termino, nombre_corto) else None
                    m = conexiones.menciones_sec(termino, cik_propio, cuantas)
                    st.session_state.setdefault("menciones", {})[conexiones.nombre_corto(termino).lower()] = m
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.warning(f"No pude completar la búsqueda: {e}")
        m = st.session_state.get("menciones", {}).get(conexiones.nombre_corto(termino).lower())
        if m is not None:
            if m.empty:
                st.info("Ningún informe reciente la nombra.")
            else:
                vista = m.assign(relacion=m["relacion"].map(conexiones.ETIQUETAS))
                st.dataframe(vista[["empresa", "ticker", "relacion", "frases", "frase", "url"]], hide_index=True, width="stretch",
                             column_config={"empresa": "Empresa que la nombra", "relacion": f"Qué es de {termino}",
                                            "frases": st.column_config.NumberColumn("Menciones"),
                                            "frase": st.column_config.TextColumn("Frase más representativa", width="large"),
                                            "url": st.column_config.LinkColumn("Informe", display_text="abrir")})
                st.caption("Los clientes y proveedores encontrados se añaden al mapa con línea de puntos morada.")

    with st.expander("📄 Proveedores que nombra la propia empresa en su informe anual"):
        st.caption("Frases sobre clientes que concentran ventas y proveedores de los que depende. Solo empresas con informes en la SEC.")
        if "@" in config.sec_ua() and st.button("Leer el último 10-K / 20-F"):
            with st.spinner("Descargando y leyendo el informe (20–40 s la primera vez)…"):
                try:
                    ev, meta = suministro.evidencias_sec(ticker)
                    st.session_state["evidencias"] = (ticker, ev, meta)
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.session_state.pop("evidencias", None)
                    st.warning(f"No pude: {e}")
        if ev_guardado and ev_guardado[0] == ticker:
            _, ev, meta = ev_guardado
            st.caption(f"Informe {meta['forma']} del {meta['fecha']} · [ver documento original]({meta['url']})")
            if ev.empty:
                st.info("No encontré frases de concentración de clientes o dependencia de proveedores.")
            else:
                st.dataframe(ev, hide_index=True, width="stretch", column_config={
                    "frase": st.column_config.TextColumn("Frase del informe", width="large")})

    with st.expander("✏️ Mi tabla de relaciones (añade lo que descubras)"):
        st.caption("Cada fila: «origen» le vende a «destino». Se suma al mapa con línea azul. Útil también para prospección.")
        editada = st.data_editor(suministro.cargar_relaciones(), num_rows="dynamic", width="stretch", key="rel_editor")
        c1, c2 = st.columns(2)
        if c1.button("💾 Guardar relaciones"):
            st.success(f"Guardadas {suministro.guardar_relaciones(editada)} relaciones.")
        c2.download_button("⬇️ Descargar CSV", editada.to_csv(index=False).encode("utf-8"), "relaciones.csv", "text/csv")

    pares = seguro(suministro.similares, ticker, etiqueta="las empresas similares") or []
    if pares:
        st.markdown("**Empresas similares (según Yahoo):** " + " · ".join(f"`{p}`" for p in pares))

# ----------------------------------------------------------------------------- ENERGÍA Y BUQUES
elif seccion == "🛢️ Energía y buques":
    sub1, sub2 = st.tabs(["🚢 Tráfico en estrechos y canales", "🏭 Mapa de activos energéticos"])
    with sub1:
        st.caption("Fuente: IMF PortWatch (FMI), estimado con datos AIS de satélite. Se publica con unos días de retraso: "
                   "sirve para ver tendencias semanales, no posiciones en directo.")
        cat = seguro(energia.estrechos, etiqueta="el catálogo de estrechos")
        if cat is not None and not cat.empty:
            base = ["Estrecho de Ormuz", "Canal de Suez", "Bab el-Mandeb (Mar Rojo)", "Estrecho de Malaca",
                    "Canal de Panamá", "Estrecho de Gibraltar"]
            elegidos = st.multiselect("Estrechos y canales", list(cat["nombre_es"]),
                                      default=[x for x in base if x in set(cat["nombre_es"])])
            hist = st.select_slider("Histórico (días)", [90, 180, 365, 730], value=365)
            sel = cat[cat["nombre_es"].isin(elegidos)]
            df = seguro(energia.pasos_diarios, tuple(sel["portid"]), hist, etiqueta="el tráfico marítimo") if len(sel) else None
            if df is not None and not df.empty:
                resumen = energia.resumen_estrechos(df)
                st.dataframe(resumen, hide_index=True, width="stretch", column_config={
                    "Petroleros/día": st.column_config.NumberColumn(format="%.1f"),
                    "Buques/día": st.column_config.NumberColumn(format="%.1f"),
                    "Petroleros vs 4 sem previas %": st.column_config.NumberColumn(format="%+.0f%%"),
                    "Buques vs 4 sem previas %": st.column_config.NumberColumn(format="%+.0f%%")})
                st.plotly_chart(graficos.fig_pasos(df, "n_total", "Buques por día (media 7 días)"), width="stretch")
                st.plotly_chart(graficos.fig_pasos(df, "n_tanker", "Petroleros por día (media 7 días)"), width="stretch")
                ultimos = df.sort_values("fecha").groupby("portid").tail(7).groupby("portid")["n_total"].mean()
                sel_mapa = sel.set_index("portid").join(ultimos.rename("media")).dropna(subset=["lat", "lon", "media"])
                if not sel_mapa.empty:
                    st.plotly_chart(graficos.fig_estrechos_mapa(sel_mapa, sel_mapa["media"], "buques/día"), width="stretch")
                with st.expander("Por qué importa cada paso"):
                    for _, fila in sel.iterrows():
                        if fila["nombre"] in energia.POR_QUE_IMPORTA:
                            st.markdown(f"**{fila['nombre_es']}** — {energia.POR_QUE_IMPORTA[fila['nombre']]}")
    with sub2:
        st.caption("Fuente: OpenStreetMap (colaborativo: puede estar incompleto). La primera consulta de una zona tarda; luego queda en caché.")
        c1, c2, c3 = st.columns(3)
        zona = c1.selectbox("Zona", list(energia.ZONAS))
        capa = c2.selectbox("Qué mostrar", energia.CAPAS)
        fuente = c3.selectbox("Fuente de energía", energia.FUENTES_CENTRAL, disabled=capa != "Centrales eléctricas")
        if st.button("🗺️ Cargar mapa"):
            with st.spinner("Consultando OpenStreetMap…"):
                try:
                    st.session_state["activos"] = (capa, zona, energia.activos(capa, energia.ZONAS[zona], fuente))
                except Exception as e:  # noqa: BLE001
                    st.session_state.pop("activos", None)
                    st.warning(str(e))
        guardado = st.session_state.get("activos")
        if guardado:
            capa_g, zona_g, act = guardado
            if act.empty:
                st.info("Sin resultados en esa zona.")
            else:
                st.markdown(f"**{len(act)} elementos** · {capa_g} · {zona_g}")
                st.plotly_chart(graficos.fig_mapa(act, "fuente" if capa_g == "Centrales eléctricas" else "capa"), width="stretch")
                ops = energia.resumen_operadores(act)
                if not ops.empty:
                    st.markdown("**Quién opera más** (útil para enlazar activos con empresas cotizadas)")
                    st.dataframe(ops, hide_index=True, width="stretch", column_config={
                        "potencia_mw": st.column_config.NumberColumn("Potencia (MW)", format="%.0f")})

# ----------------------------------------------------------------------------- MI COMPRA
elif seccion == "💶 Mi compra":
    st.markdown("Cuánto podrías ganar o perder con una aportación pequeña y cómo encaja en tu cartera.")
    if moneda and moneda != "EUR":
        st.warning(f"Este valor cotiza en {moneda}. Los porcentajes valen igual, pero no incluyen el efecto del tipo de cambio.")
    c1, c2, c3 = st.columns(3)
    importe = c1.number_input("Importe a invertir (€)", 10.0, 1_000_000.0, 50.0, step=10.0)
    comision = c2.number_input("Comisión por operación (€)", 0.0, 100.0, 1.0, step=0.5, help="Compruébala en tu bróker.")
    total = c3.number_input("Valor total de tu cartera (€, opcional)", 0.0, 100_000_000.0, 0.0, step=500.0)
    if res is None:
        st.warning(error_escenarios or "No pude calcular los escenarios.")
    else:
        tabla = cartera.simular_compra(importe, comision, res["escenarios"], precio, total or None)
        cfg = {k: st.column_config.NumberColumn(k, format="%+.2f €") for k in
               ("Pesimista (P10)", "Mediano (P50)", "Optimista (P90)")}
        cfg["Probabilidad de pérdida"] = st.column_config.NumberColumn(format="percent")
        if "Mediano sobre tu cartera" in tabla:
            cfg["Mediano sobre tu cartera"] = st.column_config.NumberColumn(format="percent")
        st.subheader(f"Resultado a {horizonte} de invertir {num(importe)} €")
        st.dataframe(tabla, hide_index=True, width="stretch", column_config=cfg)
        st.caption(f"La comisión de {num(comision)} € ya está descontada del importe invertido y restada del resultado.")

    st.subheader("Mis posiciones")
    st.caption("Importe aproximado que tienes hoy en cada valor (tickers de Yahoo). Se guarda solo en tu ordenador.")
    pos = st.data_editor(cartera.cargar_posiciones(), num_rows="dynamic", width="stretch", key="pos_editor",
                         column_config={"ticker": "Ticker", "importe_eur": st.column_config.NumberColumn("Importe (€)", min_value=0.0, format="%.2f")})
    if st.button("💾 Guardar posiciones"):
        cartera.guardar_posiciones(pos)
        st.success("Posiciones guardadas.")
    validas = pos.dropna()
    if len(validas) and (validas["importe_eur"] > 0).any():
        tickers = tuple(sorted(set(validas["ticker"].astype(str).str.upper()) | {ticker}))
        cierres = seguro(datos.cierres, tickers, "2y", etiqueta="los precios de tu cartera")
        ef = cartera.efecto_en_cartera(pos, ticker, importe, cierres) if cierres is not None else None
        if ef:
            st.subheader("Cómo encaja en tu cartera")
            m = st.columns(4)
            m[0].metric("Volatilidad antes", pct(ef["vol_antes"], 1, signo=False))
            m[1].metric("Volatilidad después", pct(ef["vol_despues"], 1, signo=False),
                        f"{(ef['vol_despues'] - ef['vol_antes']) * 100:+.1f} pts".replace(".", ","), delta_color="inverse")
            m[2].metric("Correlación con tu cartera", num(ef["correlacion"]))
            m[3].metric("Peso de la compra", pct(ef["peso_nuevo"], 1, signo=False))
            st.caption("Cuanto menor la correlación, más diversifica. Cálculo con retornos históricos de 2 años, sin tipo de cambio.")
        elif cierres is not None:
            st.caption("No hay histórico común suficiente para calcular el efecto en la cartera.")

# ----------------------------------------------------------------------------- SEÑALES
elif seccion == "🚦 Señales":
    st.caption("Señales para operaciones cortas (de 1 semana a 6 meses, tú eliges). Miran solo el precio y las noticias, no el valor del "
               "negocio: por eso pueden decir «no entrar» en una empresa que 🧠 Análisis recomienda a más de un año. Son reglas automáticas, "
               "no una garantía ni asesoramiento financiero.")
    rec_largo = (st.session_state.get(f"analisis_{ticker}") or {}).get("an", {}).get("recomendacion")
    vistas3.panel_plazos(h, ref_h["Close"] if (ref_h is not None and not ref_h.empty) else None, prudencia, rec_largo)
    if rec_largo is None:
        st.button("➕ Añadir el veredicto a largo plazo (abre 🧠 Análisis)", on_click=abrir_empresa, args=(ticker, "🧠 Análisis"))
    c1, c2, c3, c4 = st.columns(4)
    importe_op = c1.number_input("Importe por operación (€)", 10.0, 100_000.0, 100.0, 10.0, key="imp_op")
    comision_op = c2.number_input("Comisión por orden (€)", 0.0, 50.0, 1.0, 0.5, key="com_op",
                                  help="Lo que te cobra el bróker en CADA orden (compra y venta se cobran por separado).")
    NOMBRE_DIAS = {5: "1 semana", 10: "2 semanas", 15: "3 semanas", 21: "1 mes", 42: "2 meses", 63: "3 meses", 126: "6 meses"}
    dias_op = c3.select_slider("Horizonte de la operación", list(NOMBRE_DIAS), value=21, format_func=NOMBRE_DIAS.get,
                               help="Cuánto tiempo piensas mantenerla como máximo. A más plazo, el stop y el objetivo se alejan en proporción.")
    perfiles = {"Normal · SL 2 ATR · TP 2:1": (2.0, 2.0), "Ajustado · SL 1,5 ATR · TP 2:1": (1.5, 2.0),
                "Amplio · SL 3 ATR · TP 1,5:1": (3.0, 1.5)}
    perfil = c4.selectbox("Perfil de stop", list(perfiles), help="ATR = lo que se mueve la acción en un día normal.")
    k_sl, rr = perfiles[perfil]
    if dias_op > 21:  # a más plazo, el precio se aleja más por puro ruido: el stop se abre con la raíz del tiempo
        k_sl = k_sl * (dias_op / 21) ** 0.5
    imp_ccy = senales.impuesto_compra(ticker, f.get("marketCap"))
    coste_total = (2 * comision_op + importe_op * imp_ccy) / importe_op
    texto_coste = f"Coste de entrar y salir: {num(2 * comision_op + importe_op * imp_ccy)} € = {pct(coste_total, 1, False)} del importe"
    if imp_ccy:
        texto_coste += " (incluye el 0,2 % del impuesto español sobre transacciones financieras)"
    (st.warning if coste_total >= 0.015 else st.caption)(
        texto_coste + (f". Con importes tan pequeños las comisiones pesan mucho: la acción tiene que subir eso solo para quedarte igual. "
                       f"Para que pesen menos de un 0,5 % harían falta unos {num(2 * comision_op / 0.005, 0)} € por operación."
                       if coste_total >= 0.015 else "."))
    ref_close = ref_h["Close"] if (ref_h is not None and not ref_h.empty) else None
    ind = senales.indicadores(h, ref_close)
    t1, t3 = st.tabs(["📋 Plan para esta acción", "🧪 Prueba histórica"])

    with t1:
        tec = senales.puntuacion_tecnica(ind).iloc[-1]
        if pd.isna(tec):
            st.warning("Hace falta al menos un año de cotización para calcular la señal.")
        else:
            u = ind.iloc[-1]
            noticias_emp = titulares(nombre_corto, "las noticias de la empresa", "empresa")
            r_emp = noticias.resumen(noticias_emp)
            etf = senales.etf_sector(f.get("sector"), f.get("industry"))
            sector_rel = None
            if etf:
                cs = seguro(datos.cierres, (etf, "SPY"), "6mo", etiqueta="el ETF del sector")
                if cs is not None and {etf, "SPY"} <= set(cs.columns) and len(cs.dropna()) > 22:
                    cs = cs.dropna()
                    sector_rel = float(cs[etf].iloc[-1] / cs[etf].iloc[-22] - cs["SPY"].iloc[-1] / cs["SPY"].iloc[-22])
            q_sector = senales.consulta_noticias_sector(f.get("sector"), f.get("industry"), ingles=usar_ia)
            noticias_sec = titulares(q_sector, "las noticias del sector", "activo") if q_sector else []
            r_sec = noticias.resumen(noticias_sec)
            potencial = (f["targetMeanPrice"] / precio - 1) if f.get("targetMeanPrice") else None
            ctx, razones_ctx = senales.puntuacion_contexto(r_emp["media"] if r_emp["n"] else None, r_emp["n"], sector_rel,
                                                           r_sec["media"] if r_sec["n"] >= 3 else None, potencial)
            etiqueta_v, explicacion_v, nota = senales.veredicto(tec, ctx)
            c1, c2, c3 = st.columns([2, 1, 1])
            c1.subheader(etiqueta_v)
            c1.write(explicacion_v)
            c2.metric("Nota global", f"{nota}/100")
            c3.metric("Técnica / contexto", f"{tec:+.0f} / {ctx:+d}", help="Técnica de −6 a +6; contexto (noticias, sector, analistas) de −3 a +3.")
            with st.expander("Por qué (cada factor)", expanded=True):
                for signo, texto in senales.razones_tecnicas(u) + razones_ctx:
                    st.markdown(f"{'✅' if signo > 0 else '⚠️' if signo < 0 else '➖'} {esc(texto)}")
                if etf:
                    st.caption(f"ETF de sector usado como termómetro: {etf} (de EE. UU.; para valores europeos es una aproximación).")

            sl, tp = senales.niveles(precio, float(u["atr"]), float(u["min10"]), k_sl, rr)
            sim = senales.simular_plan(h["Close"], precio, sl, tp, dias_op, importe_op, comision_op, imp_ccy, ref_close, prudencia)
            limite = precio - 0.5 * float(u["atr"])
            st.subheader("Plan de operación")
            m = st.columns(4)
            m[0].metric("Entrada", f"{num(precio)} {moneda}", f"o límite en {num(limite)} (−0,5 ATR)", delta_color="off")
            m[1].metric("Stop loss", f"{num(sl)} {moneda}", f"{(sl / precio - 1) * 100:.1f}%".replace(".", ","))
            m[2].metric("Take profit", f"{num(tp)} {moneda}", f"+{(tp / precio - 1) * 100:.1f}%".replace(".", ","))
            m[3].metric("Resultado esperado", f"{sim['esperado_eur']:+.2f} €".replace(".", ","),
                        help="Media de miles de simulaciones con el SL, el TP, el horizonte y los costes incluidos.")
            m = st.columns(4)
            m[0].metric("Prob. de llegar al TP", pct(sim["prob_tp"], 0, False))
            m[1].metric("Prob. de saltar el SL", pct(sim["prob_sl"], 0, False))
            m[2].metric(f"Si llega al TP ({num(importe_op, 0)} €)", f"{sim['eur_tp']:+.2f} €".replace(".", ","))
            m[3].metric("Si salta el SL", f"{sim['eur_sl']:+.2f} €".replace(".", ","))
            dias_txt = NOMBRE_DIAS[dias_op]
            st.markdown(
                f"**Cómo ejecutarlo en tu bróker:** compra por {num(importe_op, 0)} € (≈ {num((importe_op - comision_op) / precio, 4)} acciones, "
                f"admite fracciones si tu bróker lo permite) → crea una **orden stop loss** de venta a **{num(sl)}** → crea una **orden límite** "
                f"de venta a **{num(tp)}** (si tu bróker no deja tener las dos a la vez, pon el stop y vigila el objetivo) → si en "
                f"**{dias_txt}** no ha tocado ninguna, cierra la posición y apunta el resultado en el 📒 Diario.")
            avisos = []
            if etiqueta_v.startswith("🔴"):
                avisos.append("La señal dice **no entrar**: el plan se muestra solo como referencia.")
            if sim["esperado_eur"] <= 0:
                avisos.append("Con estos costes y esta volatilidad, el resultado esperado es **negativo**.")
            if tp > sim["cierre_p90"]:
                avisos.append(f"El objetivo es ambicioso para {dias_txt}: está por encima del escenario optimista (P90 ≈ {num(sim['cierre_p90'])}).")
            if u["atr_pct"] > 0.04:
                avisos.append(f"Valor muy volátil (se mueve un {u['atr_pct'] * 100:.1f}% al día de media): el stop puede saltar por ruido.")
            for a in avisos:
                st.warning(a)
            st.caption("El stop loss no garantiza el precio: si la acción abre con un hueco por debajo, se vende al primer precio disponible.")

            st.subheader("Rango probable de precio")
            rg = senales.rangos(h["Close"], float(u["atr"]), precio)
            st.dataframe(rg, hide_index=True, width="stretch", column_config={
                **{k: st.column_config.NumberColumn(k, format="%.2f") for k in ("Mínimo probable", "Máximo probable", "Cierre P10", "Cierre P90")},
                "Movimiento típico": st.column_config.NumberColumn(format="percent")})
            st.caption("Mínimo y máximo probable = lo más bajo y lo más alto que suele tocar en ese periodo (mediana de las simulaciones). "
                       "Cierre P10–P90 = entre esos precios termina el periodo 8 de cada 10 veces. Solo volatilidad, sin tendencia.")
            if st.button("📒 Apuntar este plan en el diario"):
                d = diario.cargar()
                fila = {"fecha_entrada": pd.Timestamp.today().date(), "ticker": ticker, "importe_eur": importe_op,
                        "precio_entrada": round(precio, 4), "stop_loss": round(sl, 4), "take_profit": round(tp, 4),
                        "motivo_entrada": f"{etiqueta_v} · nota {nota}", "comisiones_eur": 2 * comision_op + importe_op * imp_ccy}
                diario.guardar(pd.concat([d, pd.DataFrame([fila])], ignore_index=True))
                st.success("Apuntado. Cuando cierres la operación, rellena la fecha y el precio de salida en 📒 Diario.")

    with t3:
        st.caption("Aplica la parte técnica de la señal a los últimos 5 años de ESTE valor, con el mismo SL, TP, horizonte e importe, "
                   "y comisiones incluidas. Las noticias no entran porque no hay histórico gratuito. Si aquí no gana, no la uses en este valor.")
        umbral = st.slider("Entrar cuando la puntuación técnica sea al menos", 1, 6, 3)
        ops = senales.backtest(h, ref_close, umbral, k_sl, rr, dias_op, importe_op, comision_op, imp_ccy)
        base = senales.backtest(h, ref_close, -99, k_sl, rr, dias_op, importe_op, comision_op, imp_ccy)
        gratis = senales.backtest(h, ref_close, umbral, k_sl, rr, dias_op, importe_op, 0.0, 0.0)
        r_s, r_b = senales.resumen_backtest(ops, importe_op), senales.resumen_backtest(base, importe_op)
        r_g = senales.resumen_backtest(gratis, importe_op)
        if not r_s["operaciones"]:
            st.info("Con ese umbral la regla no habría entrado ninguna vez. Bájalo.")
        else:
            filas = []
            for nombre_r, r in (("Con la señal", r_s), ("Entrando a ciegas (mismo SL/TP)", r_b),
                                ("Con la señal si no hubiera comisiones", r_g)):
                filas.append({"Estrategia": nombre_r, "Operaciones": r.get("operaciones", 0), "Acierto": r.get("acierto"),
                              "Media por operación (€)": r.get("media_eur"), "Total (€)": r.get("total_eur"),
                              "Factor de beneficio": r.get("factor_beneficio"), "Peor racha perdedora": r.get("peor_racha"),
                              "Peor caída acumulada (€)": r.get("peor_caida_eur")})
            st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch", column_config={
                "Acierto": st.column_config.NumberColumn(format="percent"),
                "Media por operación (€)": st.column_config.NumberColumn(format="%+.2f €"),
                "Total (€)": st.column_config.NumberColumn(format="%+.2f €"),
                "Factor de beneficio": st.column_config.NumberColumn(format="%.2f"),
                "Peor caída acumulada (€)": st.column_config.NumberColumn(format="%.2f €")})
            if r_s["media_eur"] <= 0:
                st.error("En este valor la señal **no habría ganado dinero** tras comisiones. No la uses aquí o cambia el perfil.")
            elif r_b.get("operaciones") and r_s["media_eur"] <= r_b["media_eur"]:
                st.warning("Habría ganado, pero **no más que entrar a ciegas**: la señal no aporta ventaja en este valor.")
            else:
                st.success("La señal habría ganado y **mejor que entrar a ciegas**. Aun así, el pasado no garantiza el futuro.")
            if r_g.get("operaciones") and r_g["media_eur"] > 0 >= r_s["media_eur"]:
                st.info(f"Sin comisiones la señal habría ganado {r_g['media_eur']:+.2f} € por operación: **son los costes los que la "
                        f"vuelven perdedora**. Sube el importe por operación (prueba con 400-500 €) o busca un bróker más barato.")
            st.caption(f"Salidas: {r_s['por_motivo']} · duración media {r_s['dias_medios']:.0f} sesiones. "
                       "Factor de beneficio = lo ganado ÷ lo perdido (> 1,3 es razonable).")
            curva = pd.DataFrame({"Con la señal": ops.set_index("salida_fecha")["resultado_eur"].cumsum()})
            curva_b = base.set_index("salida_fecha")["resultado_eur"].cumsum().rename("A ciegas")
            st.line_chart(curva.join(curva_b, how="outer").ffill(), y_label="€ acumulados")
            with st.expander("Últimas operaciones simuladas"):
                st.dataframe(ops.tail(25).iloc[::-1], hide_index=True, width="stretch")

# ----------------------------------------------------------------------------- OPORTUNIDADES
elif seccion == "🔍 Oportunidades":
    st.header("🔍 Buscar oportunidades")
    st.caption("Ordena índices enteros por su señal técnica de hoy y comprueba en qué valores ha funcionado la señal en el pasado. "
               "Reglas automáticas: no son una garantía ni asesoramiento financiero.")
    c1, c2, c3, c4 = st.columns(4)
    importe_op = c1.number_input("Importe por operación (€)", 10.0, 100_000.0, 500.0, 10.0, key="imp_opor")
    comision_op = c2.number_input("Comisión por orden (€)", 0.0, 50.0, 1.0, 0.5, key="com_opor")
    dias_op = c3.select_slider("Horizonte máximo", [5, 10, 15, 21], value=21, key="dias_opor",
                               format_func=lambda d: {5: "1 semana", 10: "2 semanas", 15: "3 semanas", 21: "1 mes"}[d])
    perfiles = {"Normal · SL 2 ATR · TP 2:1": (2.0, 2.0), "Ajustado · SL 1,5 ATR · TP 2:1": (1.5, 2.0),
                "Amplio · SL 3 ATR · TP 1,5:1": (3.0, 1.5)}
    perfil = c4.selectbox("Perfil de stop", list(perfiles), key="perfil_opor", help="ATR = lo que se mueve la acción en un día normal.")
    k_sl, rr = perfiles[perfil]
    o1, o2 = st.tabs(["🔍 Escáner de oportunidades", "📊 Comparador (muchos valores)"])
    with o1:
        st.caption("Ordena muchos valores por su puntuación técnica de hoy. Pincha en uno de los mejores para abrir su plan "
                   "completo (noticias, sector, stop loss y take profit).")
        listas = ["IBEX 35", "Nasdaq-100", "Dow Jones", "DAX 40", "CAC 40", "FTSE 100", "S&P 500 (tarda ~1 min)", "Mi lista"]
        c1, c2 = st.columns([1, 2])
        lista = c1.selectbox("Lista", listas)
        propia = c2.text_input("Mi lista (tickers separados por comas)", "SAN.MC, ITX.MC, IBE.MC, REP.MC, NVDA, MSFT, AAPL, LMT, RHM.DE",
                               disabled=lista != "Mi lista")
        if st.button("🔍 Escanear"):
            with st.spinner("Descargando precios y calculando…"):
                try:
                    if lista == "Mi lista":
                        tickers = [x.strip().upper() for x in propia.split(",") if x.strip()]
                    else:
                        tickers = datos.lista_indice(lista.split(" (")[0])
                    ohlc = datos.ohlc_varios(tuple(tickers), "2y")
                    refs = {}
                    for rt in {datos.referencia_para(t) for t in tickers}:
                        hr = datos.historial(rt, "2y")
                        refs[rt] = hr["Close"] if not hr.empty else None
                    st.session_state["escaner"] = (lista, senales.escanear(ohlc, refs, datos.referencia_para), len(tickers))
                except Exception as e:  # noqa: BLE001
                    st.warning(f"No pude completar el escaneo ({type(e).__name__}). Inténtalo de nuevo.")
        if "escaner" in st.session_state:
            nombre_l, tabla, n_t = st.session_state["escaner"]
            st.markdown(f"**{nombre_l}** · {len(tabla)} de {n_t} valores con datos suficientes")
            if not tabla.empty:
                st.dataframe(tabla, hide_index=True, width="stretch", column_config={
                    "Puntuación técnica": st.column_config.ProgressColumn(min_value=-6, max_value=6, format="%+.0f"),
                    "Precio": st.column_config.NumberColumn(format="%.2f"),
                    "Último mes": st.column_config.NumberColumn(format="percent"),
                    "RSI": st.column_config.NumberColumn(format="%.0f"),
                    "Volatilidad diaria": st.column_config.NumberColumn(format="percent"),
                    "vs media 200d": st.column_config.NumberColumn(format="percent"),
                    "Fuerza vs índice (3m)": st.column_config.NumberColumn(format="percent"),
                    "SL": st.column_config.NumberColumn(format="%.2f"), "TP": st.column_config.NumberColumn(format="%.2f")})
                st.caption("≥ +3: técnica favorable · 0 a +2: mixta · negativa: evitar. Prioriza también RSI entre 40 y 60 "
                           "(retroceso) frente a RSI > 70 (ya ha subido mucho).")
                st.markdown("**Abrir el plan de los mejores:**")
                for col, tk_b in zip(st.columns(5), tabla["Ticker"].head(5)):
                    col.button(f"🚦 {tk_b}", key=f"esc_{tk_b}", on_click=abrir_empresa, args=(tk_b, "🚦 Señales"), width="stretch")

    with o2:
        st.caption("Aplica la prueba histórica a muchos valores a la vez (5 años, con tu importe, comisión, horizonte y perfil de stop) "
                   "y compara la señal con entrar a ciegas y con comprar y mantener. Sirve para saber EN QUÉ valores tiene sentido usarla.")
        listas_c = ["IBEX 35", "Dow Jones", "DAX 40", "CAC 40", "Nasdaq-100 (tarda ~1 min)", "FTSE 100 (tarda ~1 min)", "Mi lista"]
        c1, c2, c3 = st.columns([1, 2, 1])
        lista_c = c1.selectbox("Lista", listas_c, key="lista_comp")
        propia_c = c2.text_input("Mi lista (tickers separados por comas)", "NVDA, AAPL, MSFT, LMT, XOM, SAN.MC, ITX.MC, IBE.MC, REP.MC, RHM.DE, SAP.DE, BP.L",
                                 disabled=lista_c != "Mi lista", key="propia_comp")
        umbral_c = c3.slider("Puntuación mínima", 1, 6, 3, key="umbral_comp")
        if st.button("📊 Comparar"):
            with st.spinner("Descargando 5 años de precios y simulando… (puede tardar un minuto)"):
                try:
                    if lista_c == "Mi lista":
                        tks = [x.strip().upper() for x in propia_c.split(",") if x.strip()]
                    else:
                        tks = datos.lista_indice(lista_c.split(" (")[0])
                    ohlc5 = datos.ohlc_varios(tuple(tks), "5y")
                    refs5 = {}
                    for rt in {datos.referencia_para(t) for t in tks}:
                        hr = datos.historial(rt, "5y")
                        refs5[rt] = hr["Close"] if not hr.empty else None
                    tabla_c = senales.comparar(ohlc5, refs5, datos.referencia_para, umbral_c, k_sl, rr, dias_op, importe_op,
                                               comision_op, lambda t: 0.002 if t.upper().endswith(".MC") else 0.0)
                    st.session_state["comparador"] = (lista_c, tabla_c, importe_op, comision_op)
                except Exception as e:  # noqa: BLE001
                    st.warning(f"No pude completar la comparación ({type(e).__name__}). Inténtalo de nuevo.")
        if "comparador" in st.session_state:
            lista_g, tabla_c, imp_g, com_g = st.session_state["comparador"]
            rc = senales.resumen_comparador(tabla_c)
            if rc:
                m = st.columns(4)
                m[0].metric("🟢 Aporta ventaja", f"{rc['aporta']} de {rc['valores']}")
                m[1].metric("🟡 Gana sin aportar", rc["no_aporta"])
                m[2].metric("🔴 Pierde", rc["pierde"])
                m[3].metric("Media por operación", f"{rc['media_senal']:+.2f} €".replace(".", ","),
                            f"a ciegas {rc['media_ciegas']:+.2f} €".replace(".", ","), delta_color="off")
                st.caption(f"{lista_g} · {num(imp_g, 0)} € por operación y {num(com_g)} € por orden. "
                           f"Total de todas las operaciones con señal: {rc['total_senal']:+,.0f} € · "
                           f"comprar y mantener {num(imp_g, 0)} € en cada valor: {rc['total_mantener']:+,.0f} €.")
                st.dataframe(tabla_c, hide_index=True, width="stretch", column_config={
                    "Acierto": st.column_config.NumberColumn(format="percent"),
                    "Señal: media/op (€)": st.column_config.NumberColumn(format="%+.2f €"),
                    "A ciegas: media/op (€)": st.column_config.NumberColumn(format="%+.2f €"),
                    "Señal: total (€)": st.column_config.NumberColumn(format="%+.0f €"),
                    "Comprar y mantener (€)": st.column_config.NumberColumn(format="%+.0f €"),
                    "Factor de beneficio": st.column_config.NumberColumn(format="%.2f")})
                st.caption("🟢 = gana y mejor que entrar a ciegas: son los valores donde la señal parece tener sentido. "
                           "Comprar y mantener sirve de referencia: si en un valor gana mucho más sin hacer nada, el trading no compensa ahí. "
                           "Es el pasado: no garantiza el futuro.")
            else:
                st.info("Ningún valor de la lista tenía histórico suficiente.")

# ----------------------------------------------------------------------------- AGENDA
elif seccion == "📅 Agenda":
    st.markdown("Próximas **presentaciones de resultados** (el día que más se mueve una acción), **fechas ex-dividendo** "
                "y pagos de dividendo de los valores que te interesan.")
    propios = set(cartera.cargar_posiciones()["ticker"].dropna().astype(str).str.upper()) | \
        set(diario.cargar()["ticker"].astype(str).str.upper()) | {ticker}
    propios = {t for t in propios if t and t != "NAN"}
    guardada = config.leer_clave("agenda_lista") or "NVDA, AAPL, MSFT, SAN.MC, IBE.MC, ITX.MC, REP.MC"
    c1, c2, c3 = st.columns([3, 1, 1])
    lista_txt = c1.text_input("Mi lista de seguimiento (tickers separados por comas)", guardada)
    if lista_txt != guardada:
        config.guardar_clave("agenda_lista", lista_txt)
    extra_indice = c2.selectbox("Añadir un índice entero", ["Ninguno", "IBEX 35", "Dow Jones", "DAX 40", "CAC 40"])
    horizonte_ag = c3.select_slider("Próximos", [14, 30, 60, 90], value=60, format_func=lambda d: f"{d} días")
    tks = [x.strip().upper() for x in lista_txt.split(",") if x.strip()] + sorted(propios)
    if extra_indice != "Ninguno":
        tks += seguro(datos.lista_indice, extra_indice, etiqueta="la lista del índice") or []
    with st.spinner(f"Consultando la agenda de {len(set(tks))} valores…"):
        ag = eventos.agenda(tks, horizonte_ag)
    if ag.empty:
        st.info("No hay eventos en ese periodo para estos valores.")
    else:
        ag["Tuyo"] = ag["Ticker"].map(lambda t: "⭐" if t in propios else "")
        st.dataframe(ag[["Fecha", "Faltan (días)", "Ticker", "Tuyo", "Evento", "Detalle"]], hide_index=True, width="stretch",
                     column_config={"Fecha": st.column_config.DateColumn(format="ddd DD/MM/YYYY")})
        st.caption("⭐ = lo tienes en tus posiciones o en el diario. Consejo: si tienes una operación abierta y la empresa presenta "
                   "resultados antes de tu fecha de salida, decide antes si quieres asumir ese salto. Fechas según Yahoo Finance; "
                   "a veces son estimadas y cambian.")
        proximos = ag[(ag["Evento"].str.contains("Resultados")) & (ag["Faltan (días)"] <= 7)]
        for _, r in proximos.iterrows():
            cuando = "hoy" if r["Faltan (días)"] == 0 else "en " + str(r["Faltan (días)"]) + " días"
            st.warning(f"{r['Ticker']} presenta resultados {cuando} ({r['Fecha']:%d/%m}).")

# ----------------------------------------------------------------------------- ALERTAS
elif seccion == "🔔 Alertas":
    st.markdown("Te aviso cuando se cumpla lo que elijas: un precio, una subida o bajada fuerte, una noticia con una palabra, "
                "una OPA o compra relacionada con la empresa, o resultados a la vista. Salen como **notificación de Windows** "
                "y quedan apuntadas abajo.")
    reglas = alertas.cargar_reglas()
    with st.form("nueva_alerta", clear_on_submit=True):
        st.markdown("**➕ Nueva alerta**")
        c1, c2, c3, c4 = st.columns([1, 2, 1, 1])
        t_al = c1.text_input("Ticker", ticker)
        tipo_al = c2.selectbox("Cuando…", list(alertas.TIPOS), format_func=lambda k: alertas.TIPOS[k])
        valor_al = c3.text_input("Valor", help="Precio, % o palabra según el tipo. Para resultados: nº de días.")
        nota_al = c4.text_input("Nombre para noticias", nombre_corto if t_al.upper() == ticker else "",
                                help="Cómo buscar la empresa en las noticias (p. ej. «Repsol»). Si lo dejas vacío uso el ticker.")
        if st.form_submit_button("Crear alerta"):
            try:
                valor = valor_al.strip()
                if tipo_al in ("precio_mayor", "precio_menor", "sube_dia", "baja_dia"):
                    valor = float(valor.replace(",", "."))
                elif tipo_al == "resultados":
                    valor = int(valor or 7)
                reglas.append(alertas.nueva_regla(t_al, tipo_al, valor or None, nota_al))
                alertas.guardar_reglas(reglas)
                st.success("Alerta creada.")
            except ValueError as e:
                st.error(f"No pude crearla: {e}")
    if reglas:
        st.markdown(f"**Tus alertas ({len(reglas)})**")
        for r in list(reglas):
            c1, c2, c3 = st.columns([6, 1, 1])
            c1.markdown(("🟢 " if r.get("activa", True) else "⏸️ ") + alertas.describir(r))
            if c2.button("Pausar" if r.get("activa", True) else "Activar", key=f"pausa_{r['id']}"):
                r["activa"] = not r.get("activa", True)
                alertas.guardar_reglas(reglas)
                st.rerun()
            if c3.button("Borrar", key=f"borra_{r['id']}"):
                alertas.guardar_reglas([x for x in reglas if x["id"] != r["id"]])
                st.rerun()
        c1, c2 = st.columns(2)
        if c1.button("🔄 Revisar ahora"):
            with st.spinner("Revisando…"):
                nuevos = alertas.revisar_y_guardar(notificar=True)
            st.success(f"{len(nuevos)} aviso(s) nuevo(s)." if nuevos else "Nada nuevo por ahora.")
        with c2:
            activa = alertas.tarea_activa()
            st.markdown(f"**Con el programa cerrado:** {'🟢 activado (cada 30 min)' if activa else '⚪ desactivado'}")
            if not activa and st.button("Activar avisos con el programa cerrado"):
                ok, msg = alertas.activar_tarea(30)
                (st.success if ok else st.error)("Activado: revisaré tus alertas cada 30 minutos aunque el programa esté cerrado "
                                                 "(con el ordenador encendido)." if ok else f"No pude activarlo: {msg}")
            if activa and st.button("Desactivar avisos con el programa cerrado"):
                ok, msg = alertas.desactivar_tarea()
                (st.success if ok else st.error)("Desactivado." if ok else msg)
        st.caption("Con el programa abierto reviso tus alertas cada 5 minutos. Cada alerta de precio avisa como mucho una vez al "
                   "día; las de noticias, una vez por titular nuevo.")
    hist = alertas.historial(50)
    if hist:
        st.markdown("**🕓 Últimos avisos**")
        st.dataframe(pd.DataFrame(hist)[["momento", "ticker", "mensaje"]], hide_index=True, width="stretch")

# ----------------------------------------------------------------------------- MATERIAS PRIMAS
elif seccion == "⛏️ Materias primas":
    st.markdown("Precio de las principales materias primas, **qué países las producen** (y cómo va su economía) y qué empresas "
                "cotizadas dependen de ellas.")
    cm = seguro(datos.cierres, tuple(v[0] for v in materias.MATERIAS.values()), "2y", etiqueta="los precios de materias primas")
    if cm is not None and not cm.empty:
        tp = materias.tabla_precios(cm)
        st.dataframe(tp, hide_index=True, width="stretch", column_config={
            "Precio": st.column_config.NumberColumn(format="%.2f"), "1 día": st.column_config.NumberColumn(format="percent"),
            "1 mes": st.column_config.NumberColumn(format="percent"), "En el año": st.column_config.NumberColumn(format="percent")})
        st.caption("Futuros con ~10-15 minutos de retraso (Yahoo Finance). Litio y uranio no tienen futuro gratuito: uso un ETF del sector.")
        por_defecto_mp = st.session_state.pop("materia_elegida", None) or "Cobre"
        elegida = st.selectbox("Ver en detalle", list(materias.MATERIAS), index=list(materias.MATERIAS).index(por_defecto_mp)
                               if por_defecto_mp in materias.MATERIAS else 0)
        t_m, unidad, _, _, empresas_m = materias.MATERIAS[elegida]
        if t_m in cm:
            x = cm[t_m].dropna()
            st.plotly_chart(graficos.fig_precio(pd.DataFrame({"Close": x}), f"{elegida} ({unidad})"), width="stretch")
        eco_m = None
        try:
            eco_m, _ = mundo.economia()
        except Exception:  # noqa: BLE001
            pass
        prod = materias.productores(elegida, eco_m)
        top3, lectura = materias.concentracion(elegida)
        st.markdown(f"**¿Quién la produce?** Los 3 primeros países suman ~{top3:.0f}% del total: {lectura}.")
        c1, c2 = st.columns([3, 2])
        coro = prod.assign(valor=prod["cuota"], texto=prod.apply(
            lambda r: f"<b>{r['pais']}</b><br>~{r['cuota']:.0f}% de la producción mundial"
                      + (f"<br>Economía: PIB {r['crecimiento']:+.1f}%" if pd.notna(r["crecimiento"]) else ""), axis=1))
        c1.plotly_chart(graficos.fig_mundo({}, coro, "YlOrBr", None, False, alto=380), width="stretch", key=f"mapa_mp_{elegida}")
        c2.dataframe(prod.assign(estado=prod["crecimiento"].map(mundo.semaforo))[["pais", "cuota", "crecimiento", "inflacion", "estado"]],
                     hide_index=True, width="stretch", column_config={
                         "pais": "País", "cuota": st.column_config.NumberColumn("Cuota aprox. (%)", format="%.0f"),
                         "crecimiento": st.column_config.NumberColumn("PIB %", format="%+.1f"),
                         "inflacion": st.column_config.NumberColumn("Inflación %", format="%.1f"), "estado": "Economía"})
        c2.caption("Cuotas aproximadas (USGS, IEA, FAO; 2023-2024). Si un gran productor entra en crisis, sufre un desastre o "
                   "sanciones, el precio suele moverse.")
        if empresas_m:
            ce = seguro(datos.cierres, tuple(empresas_m), "1y", etiqueta="las empresas expuestas")
            if ce is not None and not ce.empty:
                filas_e = []
                for t in empresas_m:
                    if t in ce and ce[t].notna().sum() > 22:
                        y = ce[t].dropna()
                        previos = y[y.index.year < y.index[-1].year]
                        filas_e.append({"Empresa / ETF": t, "Precio": float(y.iloc[-1]), "1 mes": float(y.iloc[-1] / y.iloc[-22] - 1),
                                        "En el año": float(y.iloc[-1] / (previos.iloc[-1] if len(previos) else y.iloc[0]) - 1)})
                if filas_e:
                    st.markdown("**Empresas cotizadas expuestas**")
                    st.dataframe(pd.DataFrame(filas_e), hide_index=True, width="stretch", column_config={
                        "Precio": st.column_config.NumberColumn(format="%.2f"),
                        "1 mes": st.column_config.NumberColumn(format="percent"),
                        "En el año": st.column_config.NumberColumn(format="percent")})
        with st.expander(f"📰 Noticias de {elegida.lower()}"):
            consulta_mp = elegida.split(" (")[0]
            noticias_mp = titulares(consulta_mp, f"las noticias de {consulta_mp.lower()}", "activo")
            lista_noticias(noticias_mp[:12])
            if not noticias_mp:
                st.caption("Sin titulares financieros recientes sobre esta materia prima.")

# ----------------------------------------------------------------------------- DIARIO
elif seccion == "📒 Diario":
    st.markdown("Apunta **cada** operación, también las malas. Es la forma más rápida de saber si de verdad ganas dinero y por qué.")
    d = diario.cargar()
    editado = st.data_editor(d, num_rows="dynamic", width="stretch", key="diario_editor", column_config={
        "fecha_entrada": st.column_config.DateColumn("Fecha entrada", format="DD/MM/YYYY"),
        "ticker": "Ticker", "importe_eur": st.column_config.NumberColumn("Importe €", format="%.2f"),
        "precio_entrada": st.column_config.NumberColumn("Precio entrada", format="%.4f"),
        "stop_loss": st.column_config.NumberColumn("Stop loss", format="%.4f"),
        "take_profit": st.column_config.NumberColumn("Take profit", format="%.4f"),
        "motivo_entrada": "Por qué entré", "fecha_salida": st.column_config.DateColumn("Fecha salida", format="DD/MM/YYYY"),
        "precio_salida": st.column_config.NumberColumn("Precio salida", format="%.4f"),
        "comisiones_eur": st.column_config.NumberColumn("Comisiones €", format="%.2f"), "notas": "Qué aprendí"})
    c1, c2 = st.columns(2)
    if c1.button("💾 Guardar diario"):
        st.success(f"Guardadas {diario.guardar(editado)} operaciones.")
    c2.download_button("⬇️ Descargar CSV", editado.to_csv(index=False).encode("utf-8"), "diario_operaciones.csv", "text/csv")
    res_d = diario.resultados(editado)
    e = diario.estadisticas(res_d)
    if e["cerradas"]:
        m = st.columns(5)
        m[0].metric("Cerradas / abiertas", f"{e['cerradas']} / {e['abiertas']}")
        m[1].metric("Acierto", pct(e["acierto"], 0, False))
        m[2].metric("Resultado total", f"{e['total_eur']:+.2f} €".replace(".", ","))
        m[3].metric("Media en R", num(e["media_R"]), help="R = cuántas veces el riesgo asumido ganas o pierdes de media. Por encima de 0,2 R vas bien.")
        m[4].metric("Respeto del stop", pct(e["respeto_sl"], 0, False), help="% de operaciones cerradas sin perder mucho más que el stop.")
        cerr = res_d.dropna(subset=["resultado_eur"]).sort_values("fecha_salida")
        if len(cerr) > 1:
            st.line_chart(cerr.set_index("fecha_salida")["resultado_eur"].cumsum(), y_label="€ acumulados")
        if e["cerradas"] >= 20 and e["total_eur"] < 0:
            st.warning("Tras 20 operaciones vas en negativo. Antes de seguir, revisa en «Qué aprendí» qué se repite en las perdedoras.")
    else:
        st.caption("Cuando tengas operaciones cerradas (con precio de salida) verás aquí tus estadísticas.")

# ----------------------------------------------------------------------------- GUÍA
elif seccion == "📘 Guía":
    ruta_guia = Path(__file__).resolve().parent / "GUIA.md"
    st.markdown(ruta_guia.read_text(encoding="utf-8") if ruta_guia.exists() else "No encuentro GUIA.md junto a la aplicación.")

st.divider()
st.caption("Herramienta informativa basada en datos históricos y fuentes gratuitas. No es asesoramiento financiero; "
           "las simulaciones no predicen el futuro.")
