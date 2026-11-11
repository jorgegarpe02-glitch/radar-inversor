"""Más pantallas de «terminal»: 📊 Macro, 🖥️ Monitor, 🧮 Buscador, 🧺 Cartera, 🔬 Profundizar (accionistas, opciones,
correlaciones), señales en la cadena de suministro y exportación del análisis.

Todo con fuentes gratuitas: Yahoo Finance y, cuando responde, FRED (Reserva Federal de San Luis).
"""
from __future__ import annotations

import io
import math
from concurrent.futures import ThreadPoolExecutor
from io import StringIO

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf

from . import analisis as an
from . import cartera, conexiones, config, datos, diario, negocio, suministro
from .cache import con_cache
from .vistas import AMBAR, AZUL, NEUTRO, ROJO, VERDE, esc, html, num

RUTA_VIGILANCIA = config.CARPETA / "vigilancia.txt"
VIGILANCIA_INICIAL = ["^IBEX", "^GSPC", "^NDX", "NVDA", "MSFT", "SAN.MC", "ITX.MC", "IBE.MC", "REP.MC", "GC=F", "BZ=F", "EURUSD=X", "BTC-EUR"]
NOMBRES_SIMBOLO = {"^IBEX": "IBEX 35", "^GSPC": "S&P 500", "^NDX": "Nasdaq-100", "^DJI": "Dow Jones", "^STOXX50E": "Euro Stoxx 50",
                   "^GDAXI": "DAX 40", "^FTSE": "FTSE 100", "^VIX": "Volatilidad (VIX)", "GC=F": "Oro", "SI=F": "Plata", "BZ=F": "Petróleo Brent",
                   "CL=F": "Petróleo WTI", "HG=F": "Cobre", "NG=F": "Gas natural", "EURUSD=X": "Euro / dólar", "EURGBP=X": "Euro / libra",
                   "BTC-EUR": "Bitcoin (€)", "BTC-USD": "Bitcoin ($)", "ETH-EUR": "Ethereum (€)", "^TNX": "Bono EE. UU. 10 años"}
PAISES_ES = {"United States": "Estados Unidos", "Spain": "España", "Germany": "Alemania", "France": "Francia", "United Kingdom": "Reino Unido",
             "Netherlands": "Países Bajos", "Italy": "Italia", "Switzerland": "Suiza", "Japan": "Japón", "China": "China", "Taiwan": "Taiwán",
             "South Korea": "Corea del Sur", "Ireland": "Irlanda", "Denmark": "Dinamarca", "Sweden": "Suecia", "Canada": "Canadá",
             "Brazil": "Brasil", "Mexico": "México", "India": "India", "Australia": "Australia", "Luxembourg": "Luxemburgo"}


def _pct(x, dec=1, signo=True) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{x * 100:{'+' if signo else ''}.{dec}f} %".replace(".", ",")


# ============================================================================= 📊 MACRO
CURVA_EEUU = {"3 meses": "^IRX", "5 años": "^FVX", "10 años": "^TNX", "30 años": "^TYX"}
DIVISAS = {"Euro / dólar": "EURUSD=X", "Euro / libra": "EURGBP=X", "Euro / yen": "EURJPY=X", "Euro / franco suizo": "EURCHF=X",
           "Dólar / yuan": "USDCNY=X", "Índice dólar": "DX-Y.NYB"}
TERMOMETROS = {"Volatilidad (VIX)": "^VIX", "Oro": "GC=F", "Petróleo Brent": "BZ=F", "Cobre": "HG=F", "Bitcoin (USD)": "BTC-USD",
               "Bonos EE. UU. largo plazo (TLT)": "TLT", "Bonos basura EE. UU. (HYG)": "HYG"}
# id de FRED → (nombre, unidad, qué significa)
FRED = {
    "DGS2": ("Bono EE. UU. a 2 años", "%", "Lo que el mercado espera de los tipos de la Fed en los próximos dos años."),
    "T10Y2Y": ("Curva 10 años − 2 años (EE. UU.)", "puntos", "Negativa = curva invertida, históricamente antesala de recesión."),
    "FEDFUNDS": ("Tipo oficial de la Fed", "%", "El precio del dinero en dólares."),
    "ECBDFR": ("Tipo de depósito del BCE", "%", "El precio del dinero en euros."),
    "CPIAUCSL": ("Inflación EE. UU. (interanual)", "% interanual", "Subida de precios en 12 meses; el objetivo de la Fed es el 2 %."),
    "CP0000EZ19M086NEST": ("Inflación zona euro (interanual)", "% interanual", "Subida de precios en 12 meses; el objetivo del BCE es el 2 %."),
    "UNRATE": ("Paro EE. UU.", "%", "Si sube deprisa, la Fed tiende a bajar tipos."),
    "IRLTLT01ESM156N": ("Bono español a 10 años", "%", "Lo que paga España por financiarse a largo plazo."),
    "IRLTLT01DEM156N": ("Bono alemán a 10 años", "%", "La referencia sin riesgo de la zona euro."),
    "BAMLH0A0HYM2": ("Diferencial de bonos basura (EE. UU.)", "puntos", "Cuánto más pagan las empresas arriesgadas. Si se dispara, el mercado tiene miedo."),
}
_INTERANUAL = {"CPIAUCSL", "CP0000EZ19M086NEST"}


@con_cache(12 * 3600)
def serie_fred(id_: str) -> pd.Series:
    """Serie de FRED (sin clave). Vacía si no responde."""
    inicio = (pd.Timestamp.today() - pd.DateOffset(years=6)).strftime("%Y-%m-%d")
    r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": id_, "cosd": inicio},
                     headers=config.UA_WEB, timeout=8)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text))
    s = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    s.index = pd.to_datetime(df.iloc[:, 0])
    return s.dropna()


def _fred_todas() -> dict[str, pd.Series]:
    # Si FRED no respondió hace poco, no se vuelve a esperar en cada recarga de la pantalla
    fallo = st.session_state.get("fred_fallo")
    if fallo is not None and (pd.Timestamp.now() - fallo).total_seconds() < 600:
        return {}

    def una(id_):
        try:
            s = serie_fred(id_)
            if id_ in _INTERANUAL and len(s) > 13:
                s = (s / s.shift(12) - 1).dropna() * 100
            return id_, s
        except Exception:  # noqa: BLE001
            return id_, pd.Series(dtype=float)

    with ThreadPoolExecutor(max_workers=10) as ex:
        salida = {k: v for k, v in ex.map(una, FRED) if len(v)}
    if not salida:
        st.session_state["fred_fallo"] = pd.Timestamp.now()
    return salida


def _linea(s: pd.Series, titulo: str, sufijo: str = "", cero: bool = False, alto: int = 240) -> go.Figure:
    fig = go.Figure(go.Scatter(x=s.index, y=s.values, mode="lines", line=dict(color=AZUL, width=2),
                               hovertemplate="%{x|%d/%m/%Y}: %{y:,.2f}" + sufijo + "<extra></extra>"))
    if cero:
        fig.add_hline(y=0, line=dict(color=NEUTRO, width=1))
    fig.update_layout(title=titulo, height=alto, margin=dict(l=10, r=10, t=40, b=10), showlegend=False, yaxis=dict(ticksuffix=sufijo))
    return fig


def pantalla_macro() -> None:
    st.caption("El tablero de mandos de la economía: tipos de interés, inflación, divisas y los termómetros del miedo. "
               "Los tipos mandan sobre todo lo demás: cuando suben, las acciones caras y las empresas endeudadas sufren.")
    simbolos = tuple(list(CURVA_EEUU.values()) + list(DIVISAS.values()) + list(TERMOMETROS.values()))
    try:
        cs = datos.cierres(simbolos, "2y").ffill()
    except Exception as e:  # noqa: BLE001
        st.warning(f"No pude cargar los datos de mercado ({type(e).__name__}).")
        return
    fred = _fred_todas()

    # --- curva de tipos
    st.subheader("Curva de tipos de EE. UU.")
    puntos = {k: v for k, v in CURVA_EEUU.items() if v in cs and cs[v].notna().any()}
    if puntos:
        hoy = {k: float(cs[v].dropna().iloc[-1]) for k, v in puntos.items()}
        hace = {k: float(cs[v].dropna().iloc[-min(126, len(cs[v].dropna()))]) for k, v in puntos.items()}
        if "DGS2" in fred:
            hoy = {"3 meses": hoy.get("3 meses"), "2 años": float(fred["DGS2"].iloc[-1]), **{k: v for k, v in hoy.items() if k != "3 meses"}}
            antes2 = fred["DGS2"][fred["DGS2"].index <= fred["DGS2"].index[-1] - pd.Timedelta(days=182)]
            hace = {"3 meses": hace.get("3 meses"), "2 años": float(antes2.iloc[-1]) if len(antes2) else None,
                    **{k: v for k, v in hace.items() if k != "3 meses"}}
        c1, c2 = st.columns([3, 2])
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=list(hoy), y=list(hoy.values()), mode="lines+markers+text", name="Hoy", line=dict(color=AZUL, width=2),
                                 marker=dict(size=9), text=[f"{v:.2f} %".replace(".", ",") if v else "" for v in hoy.values()],
                                 textposition="top center"))
        fig.add_trace(go.Scatter(x=list(hace), y=list(hace.values()), mode="lines+markers", name="Hace 6 meses",
                                 line=dict(color=NEUTRO, width=2, dash="dot"), marker=dict(size=8)))
        fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(ticksuffix=" %"), xaxis=dict(type="category"),
                          legend=dict(orientation="h", y=1.12))
        c1.plotly_chart(fig, width="stretch", key="curva")
        corto, largo = hoy.get("3 meses"), hoy.get("10 años")
        if corto and largo:
            pendiente = largo - corto
            c2.metric("Pendiente 10 años − 3 meses", f"{pendiente:+.2f} puntos".replace(".", ","))
            c2.markdown(("**Curva invertida**: el dinero a corto paga más que a largo. El mercado espera bajadas de tipos y, "
                         "históricamente, ha precedido a recesiones (con muchos meses de retraso y algún falso aviso)." if pendiente < 0 else
                         "**Curva normal**: prestar a largo plazo paga más que a corto. No hay señal de recesión en los bonos."
                         if pendiente > 0.5 else "**Curva plana**: el mercado duda entre crecimiento y frenazo."))
            c2.caption("Fuente: Yahoo Finance (letras a 13 semanas y bonos a 5, 10 y 30 años)" + (" y FRED (2 años)." if "DGS2" in fred else "."))

    # --- indicadores oficiales
    st.subheader("Tipos oficiales, inflación y empleo")
    if fred:
        ids = [i for i in FRED if i in fred and i != "DGS2"]
        if "IRLTLT01ESM156N" in fred and "IRLTLT01DEM156N" in fred:
            prima = (fred["IRLTLT01ESM156N"] - fred["IRLTLT01DEM156N"]).dropna() * 100
            if len(prima):
                st.metric("Prima de riesgo de España", f"{prima.iloc[-1]:.0f} puntos básicos",
                          f"{prima.iloc[-1] - prima.iloc[-min(13, len(prima))]:+.0f} en 12 meses", delta_color="inverse",
                          help="Lo que España paga de más que Alemania por su deuda a 10 años. Dato mensual.")
        cols = st.columns(3)
        for i, id_ in enumerate(ids):
            nombre, unidad, que = FRED[id_]
            s = fred[id_]
            anterior = s[s.index <= s.index[-1] - pd.Timedelta(days=360)]
            with cols[i % 3]:
                st.metric(nombre, f"{s.iloc[-1]:.2f} {unidad.split(' ')[0]}".replace(".", ","),
                          f"{s.iloc[-1] - anterior.iloc[-1]:+.2f} en un año".replace(".", ",") if len(anterior) else None,
                          delta_color="off", help=f"{que} Último dato: {s.index[-1]:%m/%Y}.")
                st.plotly_chart(_linea(s.tail(1500), "", "", cero=id_ == "T10Y2Y", alto=150), width="stretch", key=f"fred_{id_}")
        st.caption("Fuente: FRED (Reserva Federal de San Luis), que recoge datos de la Fed, el BCE, Eurostat y la OCDE. "
                   "Los datos mensuales llegan con uno o dos meses de retraso.")
    else:
        st.info("FRED (la base de datos de la Reserva Federal) no responde ahora mismo, así que no puedo enseñar tipos oficiales, "
                "inflación ni paro. El resto de la pantalla usa Yahoo Finance.")

    # --- divisas y termómetros
    for titulo, grupo, nota in (("Divisas", DIVISAS, "Si inviertes en acciones de EE. UU., un dólar más débil te resta rentabilidad en euros."),
                                ("Termómetros del mercado", TERMOMETROS,
                                 "VIX por encima de 30 = miedo. Oro y bonos largos suben cuando se busca refugio; cobre y bonos basura, cuando hay confianza.")):
        st.subheader(titulo)
        filas = []
        for nombre, sim in grupo.items():
            if sim not in cs or cs[sim].dropna().empty:
                continue
            s = cs[sim].dropna()
            filas.append({"Activo": nombre, "Último": float(s.iloc[-1]), "Hoy": s.iloc[-1] / s.iloc[-2] - 1 if len(s) > 1 else None,
                          "1 mes": s.iloc[-1] / s.iloc[-min(22, len(s))] - 1, "1 año": s.iloc[-1] / s.iloc[-min(253, len(s))] - 1,
                          "Último año": list(s.tail(253).round(4))})
        if filas:
            st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch", column_config={
                "Último": st.column_config.NumberColumn(format="%.4f" if titulo == "Divisas" else "%.2f"),
                **{k: st.column_config.NumberColumn(format="percent") for k in ("Hoy", "1 mes", "1 año")},
                "Último año": st.column_config.LineChartColumn(width="medium")})
            st.caption(nota)
    st.caption("No incluyo calendario de publicaciones económicas: no hay una fuente gratuita fiable. Las fechas de resultados de "
               "empresas están en 📅 Agenda.")


# ============================================================================= 🖥️ MONITOR
def cargar_vigilancia() -> list[str]:
    try:
        lista = [x.strip().upper() for x in RUTA_VIGILANCIA.read_text(encoding="utf-8").splitlines() if x.strip()]
        return lista or list(VIGILANCIA_INICIAL)
    except OSError:
        return list(VIGILANCIA_INICIAL)


def guardar_vigilancia(lista: list[str]) -> None:
    RUTA_VIGILANCIA.parent.mkdir(parents=True, exist_ok=True)
    RUTA_VIGILANCIA.write_text("\n".join(dict.fromkeys(x.strip().upper() for x in lista if x.strip())), encoding="utf-8")


def pantalla_monitor(abrir_empresa) -> None:
    st.caption("Tu lista de seguimiento en una sola pantalla: precio, variación y tendencia de lo que tú elijas "
               "(acciones, índices, materias primas, divisas o criptomonedas).")
    lista = cargar_vigilancia()
    with st.expander("✏️ Cambiar la lista"):
        texto = st.text_area("Un símbolo de Yahoo por línea (o separados por comas)", "\n".join(lista), height=180,
                             help="Ejemplos: NVDA, SAN.MC, ^IBEX (índice), GC=F (oro), EURUSD=X (divisa), BTC-EUR.")
        if st.button("Guardar lista"):
            guardar_vigilancia([x for trozo in texto.splitlines() for x in trozo.split(",")])
            st.rerun()
    try:
        ohlc = datos.ohlc_varios(tuple(lista), "1y")
    except Exception as e:  # noqa: BLE001
        st.warning(f"No pude cargar los precios ({type(e).__name__}).")
        return
    filas = []
    for t in lista:
        df = ohlc.get(t)
        if df is None or df["Close"].dropna().empty:
            filas.append({"Símbolo": t, "Nombre": "sin datos"})
            continue
        c = df["Close"].dropna()
        ficha_base = conexiones.ficha_entidad(conexiones.entidad(t, "")) if conexiones.entidad(t, "") else {}
        maximo, minimo = float(c.max()), float(c.min())
        filas.append({"Símbolo": t, "Nombre": NOMBRES_SIMBOLO.get(t) or ficha_base.get("nombre", ""), "Último": float(c.iloc[-1]),
                      "Hoy": c.iloc[-1] / c.iloc[-2] - 1 if len(c) > 1 else None,
                      "1 semana": c.iloc[-1] / c.iloc[-min(6, len(c))] - 1, "1 mes": c.iloc[-1] / c.iloc[-min(22, len(c))] - 1,
                      "En el año": c.iloc[-1] / c[c.index.year == c.index[-1].year].iloc[0] - 1,
                      "Posición en su rango anual": (c.iloc[-1] - minimo) / (maximo - minimo) if maximo > minimo else 0.5,
                      "Sobre media 200": c.iloc[-1] / c.tail(200).mean() - 1 if len(c) >= 150 else None,
                      "Último año": list(c.round(4))})
    df = pd.DataFrame(filas)
    st.dataframe(df, hide_index=True, width="stretch", height=min(700, 40 + 36 * len(df)), column_config={
        "Último": st.column_config.NumberColumn(format="%.2f"),
        **{k: st.column_config.NumberColumn(format="percent") for k in ("Hoy", "1 semana", "1 mes", "En el año", "Sobre media 200")},
        "Posición en su rango anual": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent",
                                                                       help="0 % = en el mínimo del año · 100 % = en el máximo"),
        "Último año": st.column_config.LineChartColumn(width="medium")})
    acciones = [t for t in lista if not any(x in t for x in ("^", "=", "-USD", "-EUR"))]
    if acciones:
        c1, c2 = st.columns([3, 1])
        elegido = c1.selectbox("Abrir el análisis de", acciones, label_visibility="collapsed")
        c2.button(f"🧠 Analizar {elegido}", on_click=abrir_empresa, args=(elegido,), width="stretch")
    st.caption("Precios de Yahoo Finance con ~15 minutos de retraso. Pulsa «R» para refrescar.")


# ============================================================================= 🧮 BUSCADOR (screener)
def _fila_buscador(t: str) -> dict:
    try:
        f = datos.ficha(t)
    except Exception:  # noqa: BLE001
        return {}
    if not f.get("precio"):
        return {}
    alto, bajo, p = f.get("fiftyTwoWeekHigh"), f.get("fiftyTwoWeekLow"), f["precio"]
    return {"Ticker": t, "Empresa": f.get("shortName") or t, "Sector": an.SECTOR_ES.get(f.get("sector") or "", f.get("sector") or ""),
            "Capitalización (mil M)": (f.get("marketCap") or 0) / 1e9 or None, "PER": f.get("trailingPE"), "PER previsto": f.get("forwardPE"),
            "Dividendo": f.get("rend_dividendo"), "ROE": f.get("returnOnEquity"), "Margen neto": f.get("profitMargins"),
            "Crec. ingresos": f.get("revenueGrowth"), "Crec. beneficio": f.get("earningsGrowth"),
            "Deuda / capital": (f.get("debtToEquity") or 0) / 100 if f.get("debtToEquity") is not None else None,
            "Desde máximo": p / alto - 1 if alto else None,
            "Potencial analistas": f["targetMeanPrice"] / p - 1 if f.get("targetMeanPrice") else None, "Beta": f.get("beta")}


PLANTILLAS = {
    "Sin filtros": {},
    "Calidad a precio razonable": {"per_max": 25, "roe_min": 15, "crec_min": 5},
    "Dividendo alto y sostenible": {"div_min": 4.0, "per_max": 20},
    "Crecimiento": {"crec_min": 15, "roe_min": 10},
    "Castigadas (lejos de máximos)": {"caida_min": 25},
    "Baratas por PER": {"per_max": 12},
}


def pantalla_buscador(abrir_empresa) -> None:
    st.caption("Filtra las acciones de un índice por sus números (PER, dividendo, rentabilidad, crecimiento…). "
               "Es un colador, no una recomendación: lo que salga hay que mirarlo después en 🧠 Análisis.")
    c1, c2 = st.columns([2, 2])
    indice = c1.selectbox("Dónde buscar", ["IBEX 35", "Euro Stoxx 50", "Dow Jones", "DAX 40", "CAC 40", "FTSE MIB", "Nasdaq-100",
                                           "S&P 100", "FTSE 100"], key="busc_indice")
    plantilla = c2.selectbox("Plantilla", list(PLANTILLAS), key="busc_plantilla")
    try:
        tickers = datos.lista_indice(indice)
    except Exception as e:  # noqa: BLE001
        st.warning(f"No pude cargar la lista del índice ({type(e).__name__}).")
        return
    clave = f"buscador_{indice}"
    if clave not in st.session_state:
        barra = st.progress(0.0, f"Leyendo los datos de {len(tickers)} empresas (solo la primera vez; luego va de memoria)…")
        filas = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            for i, fila in enumerate(ex.map(_fila_buscador, tickers)):
                if fila:
                    filas.append(fila)
                barra.progress((i + 1) / len(tickers))
        barra.empty()
        st.session_state[clave] = pd.DataFrame(filas)
    df = st.session_state[clave]
    if df.empty:
        st.warning("Yahoo no ha devuelto datos de estas empresas ahora mismo. Prueba en unos minutos.")
        if st.button("Reintentar"):
            st.session_state.pop(clave, None)
            st.rerun()
        return
    p = PLANTILLAS[plantilla]
    f1, f2, f3, f4, f5 = st.columns(5)
    per_max = f1.number_input("PER máximo", 0, 200, p.get("per_max", 0), help="0 = sin límite")
    div_min = f2.number_input("Dividendo mínimo (%)", 0.0, 15.0, p.get("div_min", 0.0), 0.5)
    roe_min = f3.number_input("ROE mínimo (%)", 0, 100, p.get("roe_min", 0))
    crec_min = f4.number_input("Crecimiento de ingresos mínimo (%)", -50, 200, p.get("crec_min", -50))
    caida_min = f5.number_input("Caída desde máximos, al menos (%)", 0, 90, p.get("caida_min", 0))
    sectores = st.multiselect("Sectores", sorted(x for x in df["Sector"].dropna().unique() if x), placeholder="Todos")
    r = df.copy()
    if per_max:
        r = r[(r["PER"] > 0) & (r["PER"] <= per_max)]
    if div_min:
        r = r[r["Dividendo"] >= div_min / 100]
    if roe_min:
        r = r[r["ROE"] >= roe_min / 100]
    if crec_min > -50:
        r = r[r["Crec. ingresos"] >= crec_min / 100]
    if caida_min:
        r = r[r["Desde máximo"] <= -caida_min / 100]
    if sectores:
        r = r[r["Sector"].isin(sectores)]
    st.markdown(f"**{len(r)} de {len(df)} empresas** pasan el filtro.")
    st.dataframe(r.sort_values("Capitalización (mil M)", ascending=False), hide_index=True, width="stretch", column_config={
        "Capitalización (mil M)": st.column_config.NumberColumn(format="%.1f"),
        **{k: st.column_config.NumberColumn(format="%.1f") for k in ("PER", "PER previsto", "Beta", "Deuda / capital")},
        **{k: st.column_config.NumberColumn(format="percent") for k in ("Dividendo", "ROE", "Margen neto", "Crec. ingresos",
                                                                        "Crec. beneficio", "Desde máximo", "Potencial analistas")}})
    if len(r):
        c1, c2, c3 = st.columns([3, 1, 1])
        elegido = c1.selectbox("Abrir", list(r["Ticker"]), label_visibility="collapsed", key="busc_abrir")
        c2.button(f"🧠 Analizar {elegido}", on_click=abrir_empresa, args=(elegido,), width="stretch")
        c3.download_button("⬇️ Descargar (CSV)", r.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"), f"buscador_{indice}.csv",
                           width="stretch")
    st.caption("Datos de la ficha de Yahoo Finance. El crecimiento es del último trimestre frente al mismo del año anterior. "
               "Un PER bajo o un dividendo alto pueden ser señal de problemas: comprueba siempre los riesgos.")


# ============================================================================= 🧺 CARTERA
def _posiciones() -> pd.DataFrame:
    """Posiciones guardadas en «Mi compra» más las operaciones abiertas del diario."""
    pos = cartera.cargar_posiciones().dropna(subset=["ticker"]).copy()
    try:
        d = diario.cargar()
        abiertas = d[d["fecha_salida"].isna()] if "fecha_salida" in d else d.iloc[0:0]
        extra = abiertas.groupby("ticker")["importe_eur"].sum().reset_index()
        extra = extra[~extra["ticker"].str.upper().isin(set(pos["ticker"].str.upper()))]
        pos = pd.concat([pos, extra], ignore_index=True)
    except Exception:  # noqa: BLE001
        pass
    pos["ticker"] = pos["ticker"].astype(str).str.upper()
    return pos[pos["importe_eur"] > 0]


def _barras_h(serie: pd.Series, titulo: str, clave: str) -> None:
    s = serie.sort_values()
    fig = go.Figure(go.Bar(x=s.values * 100, y=s.index, orientation="h", marker=dict(color=AZUL, line_width=0),
                           text=[f"{v * 100:.0f} %" for v in s.values], textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}: %{x:.1f} % de la cartera<extra></extra>"))
    fig.update_layout(title=titulo, height=max(180, 40 * len(s) + 70), margin=dict(l=10, r=40, t=40, b=10), showlegend=False,
                      xaxis=dict(range=[0, max(100, float(s.max()) * 110)], ticksuffix=" %"), bargap=0.4)
    st.plotly_chart(fig, width="stretch", key=clave)


def pantalla_cartera(abrir_empresa) -> None:
    st.header("🧺 Mi cartera")
    st.caption("Dónde está de verdad tu dinero: por empresa, sector, país y divisa, cuánto se mueven juntas tus posiciones y "
               "de qué proveedores dependen varias a la vez.")
    with st.expander("✏️ Mis posiciones (ticker e importe actual en euros)", expanded=cartera.cargar_posiciones().empty):
        editado = st.data_editor(cartera.cargar_posiciones(), num_rows="dynamic", width="stretch", key="cartera_editor", column_config={
            "ticker": st.column_config.TextColumn("Ticker de Yahoo", help="Ej.: NVDA, SAN.MC, VWCE.DE"),
            "importe_eur": st.column_config.NumberColumn("Importe (€)", min_value=0, format="%.0f")})
        if st.button("Guardar posiciones"):
            cartera.guardar_posiciones(editado)
            st.rerun()
        st.caption("Es la misma lista que usa 💶 Mi compra. Las operaciones abiertas del 📒 Diario se suman solas.")
    pos = _posiciones()
    if pos.empty:
        st.info("Añade tus posiciones arriba para ver el reparto y los riesgos de tu cartera.")
        return
    total = float(pos["importe_eur"].sum())
    pos["peso"] = pos["importe_eur"] / total

    def info(t):
        try:
            f = datos.ficha(t)
        except Exception:  # noqa: BLE001
            f = {}
        return t, f

    with st.spinner("Leyendo los datos de tus posiciones…"):
        with ThreadPoolExecutor(max_workers=6) as ex:
            fichas = dict(ex.map(info, pos["ticker"]))
        try:
            cs = datos.cierres(tuple(pos["ticker"]), "1y")
        except Exception:  # noqa: BLE001
            cs = pd.DataFrame()
    pos["Empresa"] = [fichas[t].get("shortName") or t for t in pos["ticker"]]
    pos["Sector"] = [an.SECTOR_ES.get(fichas[t].get("sector") or "", fichas[t].get("sector") or "Fondos y otros") for t in pos["ticker"]]
    pos["País"] = [PAISES_ES.get(fichas[t].get("country"), fichas[t].get("country")) or "Varios / sin dato" for t in pos["ticker"]]
    pos["Divisa"] = [(fichas[t].get("currency") or "s/d").replace("GBp", "GBP") for t in pos["ticker"]]
    pos["Beta"] = [fichas[t].get("beta") for t in pos["ticker"]]

    mayor = pos.sort_values("peso", ascending=False).iloc[0]
    sector_mayor = pos.groupby("Sector")["peso"].sum().sort_values(ascending=False)
    no_eur = float(pos[pos["Divisa"] != "EUR"]["peso"].sum())
    m = st.columns(4)
    m[0].metric("Valor total", f"{num(total, 0)} €", f"{len(pos)} posiciones", delta_color="off")
    m[1].metric("Mayor posición", mayor["ticker"], f"{mayor['peso'] * 100:.0f} % de la cartera", delta_color="off")
    m[2].metric("Sector que más pesa", sector_mayor.index[0], f"{sector_mayor.iloc[0] * 100:.0f} %", delta_color="off")
    m[3].metric("Fuera del euro", f"{no_eur * 100:.0f} %", help="Parte de la cartera expuesta a que otra divisa baje frente al euro.")

    avisos = []
    if mayor["peso"] > 0.25:
        avisos.append(f"**{mayor['ticker']} pesa un {mayor['peso'] * 100:.0f} %**: un mal día suyo mueve toda la cartera.")
    if sector_mayor.iloc[0] > 0.45 and sector_mayor.index[0] != "Fondos y otros":
        avisos.append(f"**El {sector_mayor.iloc[0] * 100:.0f} % está en {sector_mayor.index[0]}**: si ese sector cae, cae casi todo a la vez.")
    if no_eur > 0.6:
        avisos.append(f"**El {no_eur * 100:.0f} % cotiza en otra divisa**: una caída del dólar frente al euro te resta directamente.")
    if len(pos) < 5:
        avisos.append("**Menos de 5 posiciones**: cartera poco diversificada (salvo que sean fondos indexados).")

    c1, c2 = st.columns(2)
    with c1:
        _barras_h(pos.set_index("ticker")["peso"], "Por posición", "cart_pos")
        _barras_h(pos.groupby("País")["peso"].sum(), "Por país de la empresa", "cart_pais")
    with c2:
        _barras_h(pos.groupby("Sector")["peso"].sum(), "Por sector", "cart_sector")
        _barras_h(pos.groupby("Divisa")["peso"].sum(), "Por divisa en que cotiza", "cart_divisa")

    # --- correlaciones
    if not cs.empty and cs.shape[1] >= 2:
        st.subheader("¿Se mueven juntas tus posiciones?")
        rent = cs.pct_change().dropna(how="all")
        corr = rent.corr()
        fig = go.Figure(go.Heatmap(z=corr.values, x=corr.columns, y=corr.index, zmin=-1, zmax=1, colorscale=[[0, AZUL], [0.5, "#383835"], [1, AMBAR]],
                                   text=corr.round(2).values, texttemplate="%{text}", hovertemplate="%{y} y %{x}: %{z:.2f}<extra></extra>",
                                   colorbar=dict(thickness=10)))
        fig.update_layout(height=max(280, 46 * len(corr) + 80), margin=dict(l=10, r=10, t=10, b=10), xaxis=dict(type="category"),
                          yaxis=dict(type="category", autorange="reversed"))
        st.plotly_chart(fig, width="stretch", key="cart_corr")
        pares = corr.where(np.triu(np.ones(corr.shape), 1).astype(bool)).stack()
        media = float(pares.mean()) if len(pares) else 0.0
        pesos = pos.set_index("ticker")["peso"].reindex(rent.columns).fillna(0)
        vol = float(np.sqrt(pesos.values @ rent.cov().values @ pesos.values) * math.sqrt(252)) if len(rent) > 30 else None
        st.markdown(f"Correlación media entre tus posiciones: **{media:.2f}** (1 = se mueven idénticas, 0 = cada una por su lado). "
                    + ("Muy alta: en una caída bajarán casi todas a la vez; tienes menos diversificación de la que parece." if media > 0.6 else
                       "Moderada: algo de diversificación real." if media > 0.3 else "Baja: buena diversificación.")
                    + (f" Volatilidad anual estimada de la cartera: **{vol * 100:.0f} %**; en un año malo normal puede caer del orden de un {vol * 165:.0f} %."
                       if vol else ""))
        if len(pares):
            alto = pares.idxmax()
            if pares.max() > 0.75:
                avisos.append(f"**{alto[0]} y {alto[1]}** se mueven casi igual (correlación {pares.max():.2f}): a efectos de riesgo son la misma apuesta.")

    # --- dependencias comunes en la cadena de suministro
    rel = conexiones.unificar(suministro.cargar_relaciones(), None)
    dependencias: dict[str, list[str]] = {}
    for t in pos["ticker"]:
        id_ = conexiones.entidad(t, fichas[t].get("longName") or "")
        if not id_:
            continue
        nombre = conexiones.ficha_entidad(id_)["nombre"]
        for prov in negocio.proveedores_con_finalidad(rel, nombre)["Proveedor"]:
            dependencias.setdefault(prov, []).append(t)
    comunes = {k: sorted(set(v)) for k, v in dependencias.items() if len(set(v)) >= 2}
    if comunes:
        st.subheader("Proveedores de los que dependen varias de tus posiciones")
        tabla = pd.DataFrame([{"Proveedor": k, "Tus posiciones que dependen de él": ", ".join(v), "Cuántas": len(v),
                               "Peso conjunto": float(pos[pos["ticker"].isin(v)]["peso"].sum())} for k, v in comunes.items()])
        st.dataframe(tabla.sort_values("Peso conjunto", ascending=False), hide_index=True, width="stretch",
                     column_config={"Peso conjunto": st.column_config.NumberColumn(format="percent")})
        peor = tabla.sort_values("Peso conjunto", ascending=False).iloc[0]
        if peor["Peso conjunto"] > 0.3:
            avisos.append(f"**{peor['Proveedor']}** es proveedor de posiciones que suman el {peor['Peso conjunto'] * 100:.0f} % de tu cartera: "
                          "un problema ahí te afecta por varios lados a la vez.")
    st.subheader("Lo que conviene vigilar")
    if avisos:
        for a in avisos:
            st.markdown("🟡 " + a)
    else:
        st.success("No veo concentraciones preocupantes con los datos disponibles.")
    st.dataframe(pos[["ticker", "Empresa", "importe_eur", "peso", "Sector", "País", "Divisa", "Beta"]].sort_values("peso", ascending=False),
                 hide_index=True, width="stretch", column_config={"importe_eur": st.column_config.NumberColumn("Importe (€)", format="%.0f"),
                                                                 "peso": st.column_config.NumberColumn("Peso", format="percent"),
                                                                 "Beta": st.column_config.NumberColumn(format="%.2f")})
    st.caption("Los fondos y ETF no tienen sector ni país en Yahoo, así que salen como «Fondos y otros». "
               "Las dependencias salen de la base de conexiones, que no es completa.")


# ============================================================================= 🔬 PROFUNDIZAR
@con_cache(12 * 3600)
def accionistas(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    salida = {}
    for clave, attr in (("resumen", "major_holders"), ("instituciones", "institutional_holders"), ("fondos", "mutualfund_holders"),
                        ("directivos", "insider_transactions")):
        try:
            df = getattr(t, attr)
            if df is not None and len(df):
                salida[clave] = df
        except Exception:  # noqa: BLE001
            pass
    return salida


@con_cache(30 * 60)
def cadena_opciones(ticker: str, vencimiento: str | None = None) -> dict:
    t = yf.Ticker(ticker)
    fechas = list(t.options or [])
    if not fechas:
        return {}
    venc = vencimiento if vencimiento in fechas else fechas[0]
    ch = t.option_chain(venc)
    precio = (getattr(ch, "underlying", None) or {}).get("regularMarketPrice")
    return {"fechas": fechas, "vencimiento": venc, "calls": ch.calls, "puts": ch.puts, "precio": precio}


def _max_dolor(calls: pd.DataFrame, puts: pd.DataFrame) -> float | None:
    """Precio al que los compradores de opciones pierden más en conjunto (y los vendedores menos)."""
    strikes = sorted(set(calls["strike"]) | set(puts["strike"]))
    if not strikes:
        return None
    mejor, minimo = None, None
    for s in strikes:
        pago = float(((s - calls["strike"]).clip(lower=0) * calls["openInterest"].fillna(0)).sum()
                     + ((puts["strike"] - s).clip(lower=0) * puts["openInterest"].fillna(0)).sum())
        if minimo is None or pago < minimo:
            mejor, minimo = s, pago
    return mejor


def _tab_accionistas(ticker: str) -> None:
    try:
        a = accionistas(ticker)
    except Exception:  # noqa: BLE001
        a = {}
    if not a:
        st.info("Yahoo no publica el accionariado de esta empresa (suele pasar con las que no cotizan en EE. UU.). "
                "Para empresas españolas, las participaciones significativas están en la web de la CNMV.")
        return
    res = a.get("resumen")
    if res is not None and "Value" in res:
        v = res["Value"]
        c = st.columns(3)
        if "insidersPercentHeld" in v.index:
            c[0].metric("En manos de directivos y consejeros", _pct(float(v["insidersPercentHeld"]), 1, False),
                        help="Cuanto más tengan, más alineados están con el accionista.")
        if "institutionsPercentHeld" in v.index:
            c[1].metric("En manos de fondos e instituciones", _pct(float(v["institutionsPercentHeld"]), 0, False))
        if "institutionsCount" in v.index:
            c[2].metric("Instituciones accionistas", num(float(v["institutionsCount"]), 0))
    for clave, titulo in (("instituciones", "Mayores gestoras"), ("fondos", "Mayores fondos")):
        df = a.get(clave)
        if df is None:
            continue
        st.markdown(f"**{titulo}**")
        t = pd.DataFrame({"Titular": df["Holder"], "% de la empresa": df.get("pctHeld"), "Valor (mil M)": df["Value"] / 1e9,
                          "Cambio en el trimestre": df.get("pctChange"), "Dato a": pd.to_datetime(df["Date Reported"]).dt.date})
        st.dataframe(t, hide_index=True, width="stretch", column_config={
            "% de la empresa": st.column_config.NumberColumn(format="percent"), "Valor (mil M)": st.column_config.NumberColumn(format="%.1f"),
            "Cambio en el trimestre": st.column_config.NumberColumn(format="percent", help="Positivo = ha comprado más acciones; negativo = ha vendido.")})
        if clave == "instituciones" and "pctChange" in df:
            compran, venden = int((df["pctChange"] > 0.005).sum()), int((df["pctChange"] < -0.005).sum())
            st.caption(f"De las {len(df)} mayores, {compran} han aumentado su posición y {venden} la han reducido en el último trimestre publicado. "
                       "Blackrock, Vanguard y State Street son sobre todo fondos indexados: compran y venden por obligación, no por opinión.")
    d = a.get("directivos")
    if d is not None and len(d):
        st.markdown("**Compras y ventas de directivos (últimos meses)**")
        d = d.copy()
        d["Fecha"] = pd.to_datetime(d["Start Date"]).dt.date
        texto = d["Text"].fillna("").str.lower()
        d["Tipo"] = np.where(texto.str.contains("sale"), "Venta", np.where(texto.str.contains("purchase|buy"), "Compra", "Otros (opciones, donaciones…)"))
        reciente = d[pd.to_datetime(d["Start Date"]) >= pd.Timestamp.today() - pd.Timedelta(days=180)]
        ventas, compras = float(reciente[reciente["Tipo"] == "Venta"]["Value"].sum()), float(reciente[reciente["Tipo"] == "Compra"]["Value"].sum())
        c = st.columns(2)
        c[0].metric("Ventas en 6 meses", f"{num(ventas / 1e6, 1)} M")
        c[1].metric("Compras en 6 meses", f"{num(compras / 1e6, 1)} M")
        st.dataframe(d[["Fecha", "Insider", "Position", "Tipo", "Shares", "Value"]].rename(columns={
            "Insider": "Quién", "Position": "Cargo", "Shares": "Acciones", "Value": "Importe"}).head(40), hide_index=True, width="stretch",
            column_config={"Importe": st.column_config.NumberColumn(format="%.0f"), "Acciones": st.column_config.NumberColumn(format="%.0f")})
        st.caption("Que los directivos vendan es normal (cobran en acciones y diversifican). Lo que sí dice algo es que **compren** con su dinero, "
                   "o que vendan todos a la vez y mucho más de lo habitual.")
    st.caption("Fuente: Yahoo Finance, a partir de las declaraciones trimestrales (13F) y de directivos (Form 4) a la SEC. Llegan con hasta 45 días de retraso.")


def _tab_opciones(ticker: str, precio_actual: float) -> None:
    st.caption("Las opciones dicen cuánto movimiento espera el mercado y si la gente se está cubriendo (puts) o apostando al alza (calls). "
               "No hace falta operar con ellas para aprovechar la información.")
    try:
        base = cadena_opciones(ticker)
    except Exception:  # noqa: BLE001
        base = {}
    if not base:
        st.info("Esta acción no tiene opciones en Yahoo Finance (solo cubre las que cotizan en EE. UU.).")
        return
    venc = st.selectbox("Vencimiento", base["fechas"], index=min(3, len(base["fechas"]) - 1), key=f"venc_{ticker}")
    try:
        o = cadena_opciones(ticker, venc)
    except Exception as e:  # noqa: BLE001
        st.warning(f"No pude cargar ese vencimiento ({type(e).__name__}).")
        return
    calls, puts = o["calls"], o["puts"]
    precio = o.get("precio") or precio_actual
    dias = max((pd.Timestamp(venc) - pd.Timestamp.today().normalize()).days, 1)
    strikes = sorted(set(calls["strike"]) & set(puts["strike"]))
    if not strikes:
        st.info("Sin datos suficientes para este vencimiento.")
        return
    atm = min(strikes, key=lambda s: abs(s - precio))
    c_atm, p_atm = calls[calls["strike"] == atm].iloc[0], puts[puts["strike"] == atm].iloc[0]

    def medio(f):
        return (f["bid"] + f["ask"]) / 2 if (f["bid"] and f["ask"]) else f["lastPrice"]

    movimiento = (medio(c_atm) + medio(p_atm)) / precio
    vi = float(np.nanmean([c_atm["impliedVolatility"], p_atm["impliedVolatility"]]))
    oi_c, oi_p = float(calls["openInterest"].fillna(0).sum()), float(puts["openInterest"].fillna(0).sum())
    ratio = oi_p / oi_c if oi_c else None
    dolor = _max_dolor(calls, puts)
    m = st.columns(4)
    m[0].metric(f"Movimiento esperado en {dias} días", f"±{movimiento * 100:.1f} %".replace(".", ","),
                f"entre {num(precio * (1 - movimiento), 0)} y {num(precio * (1 + movimiento), 0)}", delta_color="off",
                help="Coste de comprar a la vez una call y una put al precio actual: lo que el mercado cree que puede moverse hasta el vencimiento.")
    m[1].metric("Volatilidad implícita", f"{vi * 100:.0f} %", help="Volatilidad anual que descuentan las opciones. Compárala con la histórica en 🧠 Análisis → Momento de mercado.")
    m[2].metric("Puts por cada call", f"{ratio:.2f}".replace(".", ",") if ratio else "—",
                "más coberturas que apuestas" if (ratio or 0) > 1 else "más apuestas alcistas", delta_color="off",
                help="Contratos abiertos de venta entre contratos abiertos de compra.")
    m[3].metric("Precio de «máximo dolor»", num(dolor, 0) if dolor else "—",
                help="Precio al que más opciones vencerían sin valor. A veces el precio tiende a acercarse a él al vencimiento; no es una ley.")
    cerca = [s for s in strikes if 0.75 * precio <= s <= 1.25 * precio]
    c2, p2 = calls[calls["strike"].isin(cerca)], puts[puts["strike"].isin(cerca)]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=c2["strike"], y=c2["openInterest"], name="Calls (apuestas a que sube)", marker=dict(color=AZUL, line_width=0)))
    fig.add_trace(go.Bar(x=p2["strike"], y=p2["openInterest"], name="Puts (apuestas a que baja o coberturas)", marker=dict(color=AMBAR, line_width=0)))
    fig.add_vline(x=precio, line=dict(color=NEUTRO, width=1, dash="dot"), annotation_text="precio actual")
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10), barmode="group", legend=dict(orientation="h", y=1.15),
                      xaxis_title="Precio de ejercicio", yaxis_title="Contratos abiertos")
    st.plotly_chart(fig, width="stretch", key=f"oi_{ticker}_{venc}")
    st.caption("Los precios de ejercicio con muchos contratos abiertos suelen actuar de imán o de barrera cerca del vencimiento.")
    with st.expander("Ver la cadena completa"):
        cols = ["strike", "lastPrice", "bid", "ask", "volume", "openInterest", "impliedVolatility"]
        tabla = c2[cols].merge(p2[cols], on="strike", suffixes=(" call", " put")).rename(columns={"strike": "Ejercicio"})
        st.dataframe(tabla, hide_index=True, width="stretch", column_config={
            "impliedVolatility call": st.column_config.NumberColumn("Vol. implícita call", format="percent"),
            "impliedVolatility put": st.column_config.NumberColumn("Vol. implícita put", format="percent")})
    st.caption("Fuente: Yahoo Finance, con retraso. Fuera del horario de mercado, las horquillas son poco fiables.")


def _tab_correlaciones(ticker: str, comparables: list[str]) -> None:
    st.caption("Con qué se mueve esta acción: sirve para saber si de verdad diversifica lo que ya tienes y qué la arrastra.")
    referencias = {"S&P 500": "^GSPC", "Nasdaq-100": "^NDX", "IBEX 35": "^IBEX", "Euro Stoxx 50": "^STOXX50E", "Oro": "GC=F",
                   "Petróleo Brent": "BZ=F", "Cobre": "HG=F", "Dólar (índice)": "DX-Y.NYB", "Bono EE. UU. 10 años (tipo)": "^TNX",
                   "Bitcoin": "BTC-USD", **{c: c for c in comparables}}
    try:
        cs = datos.cierres(tuple([ticker] + list(referencias.values())), "2y").ffill()
    except Exception as e:  # noqa: BLE001
        st.warning(f"No pude cargar los precios ({type(e).__name__}).")
        return
    rent = cs.pct_change(5).dropna(how="all")  # semanal: evita el desfase horario entre bolsas
    if ticker not in rent:
        st.info("Sin datos suficientes.")
        return
    filas = []
    for nombre, sim in referencias.items():
        if sim in rent and rent[sim].notna().sum() > 60:
            par = rent[[ticker, sim]].dropna()
            c1 = float(par[ticker].corr(par[sim]))
            c2 = float(par.tail(130)[ticker].corr(par.tail(130)[sim]))
            filas.append({"Con": nombre, "2 años": c1, "Últimos 6 meses": c2})
    if not filas:
        st.info("Sin datos suficientes.")
        return
    df = pd.DataFrame(filas).sort_values("2 años")
    fig = go.Figure(go.Bar(x=df["2 años"], y=df["Con"], orientation="h", text=[f"{v:+.2f}".replace(".", ",") for v in df["2 años"]],
                           textposition="outside", cliponaxis=False,
                           marker=dict(color=df["2 años"], colorscale=[[0, AMBAR], [0.5, "#55544f"], [1, AZUL]], cmin=-1, cmax=1, line_width=0),
                           hovertemplate="%{y}: %{x:.2f}<extra></extra>"))
    fig.add_vline(x=0, line=dict(color=NEUTRO, width=1))
    fig.update_layout(height=max(260, 34 * len(df) + 60), margin=dict(l=10, r=40, t=10, b=10), xaxis=dict(range=[-1, 1.1]), showlegend=False)
    st.plotly_chart(fig, width="stretch", key=f"corr_{ticker}")
    st.dataframe(df.sort_values("2 años", ascending=False), hide_index=True, width="stretch", column_config={
        k: st.column_config.NumberColumn(format="%.2f") for k in ("2 años", "Últimos 6 meses")})
    st.caption("Correlación de las variaciones semanales: +1 se mueven igual, 0 sin relación, −1 al revés. "
               "Si la de los últimos 6 meses se aleja mucho de la de 2 años, algo ha cambiado en lo que mueve a la acción.")


def pantalla_profundizar(ticker: str, f: dict, precio: float) -> None:
    t1, t2, t3 = st.tabs(["🏛️ Quién es el dueño", "🎲 Opciones", "🔗 Con qué se mueve"])
    with t1:
        _tab_accionistas(ticker)
    with t2:
        _tab_opciones(ticker, precio)
    with t3:
        from .vistas import _comparables

        try:
            comp = _comparables(ticker, conexiones.entidad(ticker, f.get("longName") or ""))
        except Exception:  # noqa: BLE001
            comp = []
        _tab_correlaciones(ticker, comp)


# ============================================================================= señales en la cadena de suministro
def senales_cadena(corto: str, cli: pd.DataFrame, prov: pd.DataFrame) -> None:
    """Qué están haciendo en bolsa sus clientes y proveedores: si caen con fuerza, puede venir un problema."""
    pares = [(n, conexiones.ticker_por_nombre(n), "Cliente") for n in cli["Cliente"]] + \
            [(n, conexiones.ticker_por_nombre(n), "Proveedor") for n in prov["Proveedor"]]
    pares = [(n, t, r) for n, t, r in pares if t]
    if not pares:
        return
    st.subheader("🚨 Qué está pasando en su cadena")
    try:
        cs = datos.cierres(tuple(dict.fromkeys(t for _, t, _ in pares)), "6mo").ffill()
    except Exception:  # noqa: BLE001
        st.caption("No pude cargar las cotizaciones de sus clientes y proveedores.")
        return
    filas = []
    for n, t, rol in pares:
        if t in cs and cs[t].dropna().shape[0] > 25:
            s = cs[t].dropna()
            filas.append({"Empresa": n, "Relación": rol, "Ticker": t, "1 mes": float(s.iloc[-1] / s.iloc[-22] - 1),
                          "3 meses": float(s.iloc[-1] / s.iloc[-min(64, len(s))] - 1)})
    if not filas:
        return
    df = pd.DataFrame(filas).drop_duplicates(subset=["Empresa", "Relación"])
    for rol, texto_mal, texto_bien in (("Cliente", "sus clientes están cayendo en bolsa: puede anticipar menos pedidos",
                                        "a sus clientes les va bien en bolsa: buena señal para sus pedidos"),
                                       ("Proveedor", "sus proveedores están cayendo: vigila posibles problemas de suministro o de costes",
                                        "sus proveedores suben: la cadena está fuerte (o le van a subir precios)")):
        g, plural = df[df["Relación"] == rol], {"Cliente": "Clientes", "Proveedor": "Proveedores"}[rol]
        if len(g) >= 3:
            mediana = float(g["1 mes"].median())
            caen = g[g["1 mes"] < -0.10]
            if mediana < -0.05 or len(caen) >= max(3, len(g) // 3):
                st.warning(f"**{plural}:** mediana de {_pct(mediana)} en un mes; {texto_mal}. Los que más caen: "
                           + ", ".join(f"{r['Empresa']} ({_pct(r['1 mes'], 0)})" for _, r in caen.sort_values('1 mes').head(4).iterrows()) + ".")
            elif mediana > 0.05:
                st.success(f"**{plural}:** mediana de {_pct(mediana)} en un mes; {texto_bien}.")
            else:
                st.markdown(f"**{plural}:** mediana de {_pct(mediana)} en un mes, sin señal clara.")
    st.dataframe(df.sort_values("1 mes"), hide_index=True, width="stretch", column_config={
        "1 mes": st.column_config.NumberColumn(format="percent"), "3 meses": st.column_config.NumberColumn(format="percent")})
    st.caption(f"Variación en bolsa de los clientes y proveedores cotizados de {corto}. Es una pista, no una prueba: pueden caer por motivos que no tienen que ver.")


# ============================================================================= exportar el análisis
def informe_html(a: dict, m: dict, moneda: str) -> str:
    """El análisis completo en una página que se puede imprimir o guardar como PDF desde el navegador."""
    rec, cal = a["recomendacion"], a["calidad"]
    color = {"verde": "#0a7a0a", "amarillo": "#a56a00", "rojo": "#b02a2a"}[rec["color"]]

    def p(texto):
        return "<p>" + html(texto).replace("**", "") + "</p>"

    filas_m = "".join(f"<tr><td>{html(t['nombre'])}</td><td class='n'>{an.formato(t['valor'], t['fmt'])}</td><td class='n'>{an.formato(t['historia'], t['fmt'])}</td>"
                      f"<td class='n'>{an.formato(t['competidores'], t['fmt'])}</td><td class='n'>{an.formato(t['sector'], t['fmt'])}</td>"
                      f"<td class='f'>{html(t['fuente'])}</td></tr>" for t in a["metricas"])
    escenarios = "".join(f"<tr><td>{html(e['nombre'])}</td><td class='n'>{num(e['bajo'], 2)} – {num(e['alto'], 2)} {html(moneda)}</td>"
                         f"<td class='n'>{e['rent_total'] * 100:+.0f} %</td><td>{html(e['condiciones'])}</td></tr>" for e in a["escenarios"].get("escenarios", []))
    partes = [
        "<!doctype html><html lang='es'><head><meta charset='utf-8'><title>Análisis de " + html(a["nombre"]) + "</title><style>"
        "body{font-family:Segoe UI,Arial,sans-serif;max-width:900px;margin:30px auto;padding:0 20px;color:#1b1b1a;line-height:1.5}"
        "h1{margin-bottom:0}h2{border-bottom:1px solid #ccc;padding-bottom:4px;margin-top:28px}table{border-collapse:collapse;width:100%;font-size:.9rem}"
        "td,th{border-bottom:1px solid #ddd;padding:5px 8px;text-align:left;vertical-align:top}.n{text-align:right;white-space:nowrap}.f{font-size:.72rem;color:#666}"
        f".rec{{border:2px solid {color};border-radius:8px;padding:12px 16px;margin:12px 0}}.rec b.t{{color:{color};font-size:1.3rem}}"
        ".gris{color:#666;font-size:.85rem}@media print{body{margin:0}}</style></head><body>",
        f"<h1>{html(a['nombre'])} ({html(m.get('ticker', ''))})</h1><div class='gris'>Radar Inversor · {pd.Timestamp.today():%d/%m/%Y} · "
        f"precio {num(m.get('precio'), 2)} {html(moneda)}</div>",
        f"<div class='rec'><b class='t'>{html(rec['etiqueta'])}" + (f" · {html(rec['titulo'])}" if rec["titulo"] not in rec["etiqueta"] else "")
        + f"</b>{p(rec['texto'])}</div>",
        "<h2>En pocas palabras</h2>" + p(a["resumen"]),
        "<h2>Métricas fundamentales</h2><table><tr><th>Métrica</th><th class='n'>Valor</th><th class='n'>Su historia</th><th class='n'>Competidores</th>"
        "<th class='n'>Sector</th><th>Fuente</th></tr>" + filas_m + "</table>",
        f"<h2>Calidad del negocio: {html(cal['etiqueta'])}</h2>" + "".join(
            f"<p><b>{ {2: '✔', 1: '–', 0: '✘'}[c['nota']]} {html(c['criterio'])}.</b> {html(c['texto'])}</p>" for c in cal["criterios"]),
        "<h2>Perfil</h2>" + p(f"Crecimiento {a['estrellas']['crecimiento']}/5 · Dividendos {a['estrellas']['dividendos']}/5 · DCA {a['estrellas']['dca']}/5. "
                              + a["estrellas"]["encaje"]) + p(f"DCA — {a['dca']['veredicto']}. {a['dca']['frase']}"),
        "<h2>Catalizadores</h2>" + "".join(p(f"{c['tipo']} (probabilidad {c['prob']}, impacto {c['impacto']}): {c['texto']}") for c in a["catalizadores"]),
        "<h2>Momento de mercado</h2>" + "".join(p(a["tecnico"][k]) for k in ("frase_tendencia", "frase_rango", "frase_momentum", "frase_resultados") if a["tecnico"].get(k)),
        "<h2>Escenarios a 12-18 meses</h2><table><tr><th>Escenario</th><th class='n'>Precio</th><th class='n'>Rentabilidad total</th><th>Condiciones</th></tr>"
        + escenarios + "</table><p class='gris'>" + html(a["escenarios"].get("metodo", "")) + ". "
        + " ".join(html(s) for s in a["escenarios"].get("supuestos", [])) + "</p>",
        "<h2>Riesgos</h2>" + "".join(f"<p><b>{'●●' if r['severidad'] == 2 else '●'} {html(r['titulo'])}.</b> {html(r['texto'])}</p>" for r in a["riesgos"]["lista"])
        + p("¿Cuándo sale muy mal? " + a["riesgos"]["desastre"]),
        "<h2>Veredicto</h2>" + p(a["veredicto"]),
        f"<p class='gris'>Análisis generado con reglas automáticas sobre datos públicos (Yahoo Finance, SEC). {html(a['aviso'])}</p></body></html>",
    ]
    return "".join(partes)


def excel_analisis(a: dict, m: dict) -> bytes | None:
    """Métricas, histórico anual, escenarios y riesgos en un Excel. None si falta la librería."""
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        return None
    salida = io.BytesIO()
    with pd.ExcelWriter(salida, engine="openpyxl") as w:
        pd.DataFrame([{"Métrica": t["nombre"], "Valor": t["valor"], "Su historia": t["historia"], "Competidores": t["competidores"],
                       "Sector": t["sector"], "Fuente": t["fuente"]} for t in a["metricas"]]).to_excel(w, sheet_name="Métricas", index=False)
        anual = m.get("anual")
        if anual is not None and not anual.empty:
            cols = {"ingresos": "Ingresos", "bruto": "Beneficio bruto", "operativo": "Beneficio operativo", "ebitda": "EBITDA", "neto": "Beneficio neto",
                    "fcf": "Caja libre", "bpa": "BPA", "acciones": "Acciones", "margen_bruto": "Margen bruto", "margen_op": "Margen operativo",
                    "roic": "ROIC", "roe": "ROE", "deuda_neta": "Deuda neta", "per": "PER al cierre", "ev_ebitda": "EV/EBITDA al cierre"}
            t = anual[[c for c in cols if c in anual]].rename(columns=cols)
            t.index = [f"{x:%Y-%m}" for x in t.index]
            t.T.to_excel(w, sheet_name="Histórico anual")
        pd.DataFrame([{"Escenario": e["nombre"], "Precio bajo": e["bajo"], "Precio alto": e["alto"], "Rentabilidad total": e["rent_total"],
                       "Condiciones": e["condiciones"], "Método": e["metodo"]} for e in a["escenarios"].get("escenarios", [])]).to_excel(w, sheet_name="Escenarios", index=False)
        pd.DataFrame([{"Severidad": "Alta" if r["severidad"] == 2 else "Media", "Riesgo": r["titulo"], "Detalle": r["texto"]}
                      for r in a["riesgos"]["lista"]]).to_excel(w, sheet_name="Riesgos", index=False)
        pd.DataFrame([{"Criterio": c["criterio"], "Nota (0-2)": c["nota"], "Detalle": c["texto"]} for c in a["calidad"]["criterios"]]).to_excel(w, sheet_name="Calidad", index=False)
        pd.DataFrame({"": ["Recomendación", "Motivo", "Veredicto", "Resumen", "Aviso"],
                      "Texto": [a["recomendacion"]["etiqueta"] + " " + a["recomendacion"]["titulo"], a["recomendacion"]["texto"].replace("**", ""),
                                a["veredicto"].replace("**", ""), a["resumen"], a["aviso"]]}).to_excel(w, sheet_name="Conclusión", index=False)
    return salida.getvalue()


def botones_exportar(a: dict, m: dict, moneda: str, ticker: str) -> None:
    c1, c2, c3 = st.columns([1, 1, 2])
    c1.download_button("⬇️ Informe (HTML, imprimible a PDF)", informe_html(a, m, moneda).encode("utf-8"), f"analisis_{ticker}.html", "text/html",
                       width="stretch", key=f"exp_html_{ticker}")
    try:
        xls = excel_analisis(a, m)
    except Exception:  # noqa: BLE001 - el Excel es un extra: nunca debe romper la pantalla del análisis
        xls = None
    if xls:
        c2.download_button("⬇️ Datos (Excel)", xls, f"analisis_{ticker}.xlsx", width="stretch", key=f"exp_xls_{ticker}")
    c3.caption("Abre el HTML y pulsa Ctrl+P → «Guardar como PDF» para tenerlo en PDF.")
