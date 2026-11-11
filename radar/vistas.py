"""Pantallas nuevas: 🧠 Análisis, 💼 Negocio y 🟩 Mapa de calor.

Aquí solo se pinta. Los cálculos están en analisis.py, fundamentales.py y negocio.py.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from . import analisis as an
from . import (cartera, conexiones, config, datos, diario, escenarios, eventos, fundamentales as fu, negocio, noticias,
               senales, suministro)

AZUL = "#3987e5"
VERDE, ROJO, AMBAR, NEUTRO = "#0ca30c", "#d03b3b", "#fab219", "#898781"
RUTA_PROMPT = config.CARPETA / "prompt_analisis.md"
RUTA_PROMPT_BASE = Path(__file__).resolve().parent.parent / "datos" / "prompt_analisis.md"

CSS = """
<style>
.ri-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:10px;margin:.3rem 0 1rem 0}
.ri-card{border:1px solid rgba(137,135,129,.35);border-left:4px solid var(--c);border-radius:8px;padding:10px 12px;
         background:rgba(137,135,129,.07)}
.ri-card h4{margin:0;font-size:.78rem;font-weight:600;opacity:.75;padding:0}
.ri-card .v{font-size:1.5rem;font-weight:700;line-height:1.25}
.ri-card .r{font-size:.76rem;display:flex;justify-content:space-between;gap:6px;opacity:.9}
.ri-card .r b{font-weight:600}
.ri-card .f{font-size:.66rem;opacity:.55;margin-top:4px}
.ri-box{border-radius:10px;padding:16px 18px;margin:.4rem 0 1rem 0;border:2px solid var(--c);background:color-mix(in srgb,var(--c) 12%,transparent)}
.ri-box .t{font-size:1.5rem;font-weight:800;letter-spacing:.02em}
.ri-esc{border:1px solid rgba(137,135,129,.35);border-top:4px solid var(--c);border-radius:8px;padding:12px 14px;height:100%;
        background:rgba(137,135,129,.07)}
.ri-esc .p{font-size:1.35rem;font-weight:700}
.ri-esc .s{font-size:.8rem;opacity:.85}
.ri-chip{display:inline-block;border:1px solid rgba(137,135,129,.5);border-radius:999px;padding:1px 10px;margin:0 6px 4px 0;font-size:.8rem}
.ri-star{font-size:1.35rem;letter-spacing:2px}
</style>
"""


# ----------------------------------------------------------------------------- utilidades de formato
def num(x, dec: int = 2) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _dec(x) -> int:
    return 0 if abs(x or 0) >= 100 else 2


def esc(texto: str) -> str:
    return str(texto).replace("$", "\\$").replace("[", "(").replace("]", ")")


def html(texto: str) -> str:
    return str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def con_euros(valor: float, moneda: str, a_eur: float | None) -> str:
    """'1.100 USD (≈ 1.015 €)'. Si ya cotiza en euros, solo el importe."""
    if valor is None or pd.isna(valor):
        return "—"
    base = f"{num(valor, _dec(valor))} {moneda}".strip()
    if a_eur and moneda not in ("EUR", ""):
        return f"{base} (≈ {num(valor * a_eur, _dec(valor * a_eur))} €)"
    return base


@st.cache_data(ttl=3600, show_spinner=False)
def cambio_a_euros(moneda: str) -> float | None:
    """Euros que vale 1 unidad de la divisa en la que cotiza (peniques incluidos)."""
    if not moneda or moneda == "EUR":
        return None
    factor = 0.01 if moneda in ("GBp", "GBX", "ZAc", "ILA") else 1.0
    base = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ILA": "ILS"}.get(moneda, moneda)
    try:
        s = fu.serie_cambio(base, "EUR")
        return float(s.iloc[-1]) * factor if len(s) else None
    except Exception:  # noqa: BLE001
        return None


def instrucciones_ia() -> str:
    for ruta in (RUTA_PROMPT, RUTA_PROMPT_BASE):
        try:
            return ruta.read_text(encoding="utf-8")
        except OSError:
            continue
    return ""


# ----------------------------------------------------------------------------- reunir datos
def _comparables(ticker: str, id_base: str | None) -> list[str]:
    """Competidores: primero los del mismo sector en la base propia; si no hay, los «similares» de Yahoo."""
    tickers = []
    if id_base:
        empresas, _ = conexiones.cargar_base()
        yo = empresas[empresas["id"] == id_base]
        if not yo.empty:
            mismos = empresas[(empresas["sector"] == yo.iloc[0]["sector"]) & (empresas["id"] != id_base) & (empresas["tickers"] != "")]
            tickers = [t.split("|")[0] for t in mismos["tickers"]][:3]
    if len(tickers) < 2:
        try:
            for t in suministro.similares(ticker):
                if t not in tickers and t != ticker:
                    tickers.append(t)
        except Exception:  # noqa: BLE001
            pass
    return tickers[:3]


def _un_comparable(t: str) -> dict:
    try:
        f = datos.ficha(t)
    except Exception:  # noqa: BLE001
        f = {}
    r = fu.resumen_comparable(t, f)
    if r:
        r["nombre"] = f.get("shortName") or t
    return r


def reunir(ticker: str, f: dict, h: pd.DataFrame, nombre: str, ref_close: pd.Series | None, prudencia: float,
           idioma: tuple[str, str], usar_sec: bool) -> dict:
    """Descarga y calcula todo lo que necesita el análisis. Tarda unos segundos la primera vez; luego va de caché."""
    m = fu.calcular(ticker, f)
    id_base = conexiones.entidad(ticker, nombre)
    ficha_base = conexiones.ficha_entidad(id_base) if id_base else {}
    sector = an.sector_yahoo(f.get("sector"), ficha_base.get("sector"))
    corto = ficha_base.get("nombre") or conexiones.nombre_corto(nombre)
    with ThreadPoolExecutor(max_workers=4) as ex:
        fut_comp = [ex.submit(_un_comparable, t) for t in _comparables(ticker, id_base)]
        fut_seg = ex.submit(negocio.segmentos, ticker, id_base, usar_sec)
        fut_ag = ex.submit(eventos.agenda, [ticker], 120)
        fut_fechas = ex.submit(fu.fechas_resultados, ticker)
        fut_not = ex.submit(noticias.buscar, corto, idioma[0], idioma[1], 14, 25, "empresa")
        comparables = [c for c in (x.result() for x in fut_comp) if c]

        def seguro(fut, defecto):
            try:
                return fut.result()
            except Exception:  # noqa: BLE001
                return defecto

        seg = seguro(fut_seg, {"ejes": {}})
        agenda = seguro(fut_ag, pd.DataFrame())
        fechas = seguro(fut_fechas, pd.DataFrame())
        titulares = seguro(fut_not, [])
    rel = conexiones.unificar(suministro.cargar_relaciones(), None)
    clientes = negocio.clientes_con_finalidad(rel, corto)
    proveedores = negocio.proveedores_con_finalidad(rel, corto)
    reaccion = fu.reaccion_resultados(fechas, (fu.mercado(ticker) or {}).get("precios"))
    estadistico = None
    if ref_close is not None and len(h) > 300:
        try:
            e = escenarios.analizar(h["Close"], ref_close, 315, prudencia)["escenarios"]["mixto"]["percentiles"]
            estadistico = {"p10": e[10], "p50": e[50], "p90": e[90]}
        except Exception:  # noqa: BLE001
            pass
    sector_rel, per_etf, etf = None, None, senales.etf_sector(f.get("sector"), f.get("industry"))
    if etf:
        try:
            cs = datos.cierres((etf, "SPY"), "6mo").dropna()
            if len(cs) > 22:
                sector_rel = float(cs[etf].iloc[-1] / cs[etf].iloc[-22] - cs["SPY"].iloc[-1] / cs["SPY"].iloc[-22])
            per_etf = datos.ficha(etf).get("trailingPE")
        except Exception:  # noqa: BLE001
            pass
    try:
        mios = set(cartera.cargar_posiciones()["ticker"].dropna().astype(str).str.upper())
        d = diario.cargar()
        if "fecha_salida" in d:
            mios |= set(d[d["fecha_salida"].isna()]["ticker"].astype(str).str.upper())
    except Exception:  # noqa: BLE001
        mios = set()
    analisis = an.completo(corto, m, h, sector=sector, industria=f.get("industry"), comparables=comparables, seg=seg,
                           clientes=list(clientes["Cliente"]), proveedores=list(proveedores["Proveedor"]), agenda=agenda,
                           reaccion=reaccion, noticias=titulares, estadistico=estadistico, sector_rel=sector_rel, per_etf=per_etf,
                           en_cartera=ticker.upper() in mios)
    return {"m": m, "an": analisis, "comparables": comparables, "seg": seg, "clientes": clientes, "proveedores": proveedores,
            "reaccion": reaccion, "corto": corto, "id_base": id_base, "etf": etf, "per_etf": per_etf, "noticias": titulares,
            "momento": pd.Timestamp.now()}


# ----------------------------------------------------------------------------- 🧠 ANÁLISIS
_ICONO = {"mejor": "▲ mejor", "peor": "▼ peor", "similar": "● similar", None: ""}
_COLOR = {"verde": VERDE, "rojo": ROJO, "gris": NEUTRO}


def _tarjeta(t: dict) -> str:
    filas = ""
    for etiqueta, clave, juicio in (("Su historia", "historia", "vs_historia"), ("Competidores", "competidores", "vs_competidores"),
                                    ("Sector", "sector", "vs_sector")):
        if t.get(clave) is not None and not pd.isna(t[clave]):
            filas += (f"<div class='r'><span>{etiqueta}: <b>{an.formato(t[clave], t['fmt'])}</b></span>"
                      f"<span>{_ICONO[t.get(juicio)]}</span></div>")
    if t.get("rango") and t["rango"][0] is not None:
        filas += f"<div class='r'><span>Rango histórico: {an.formato(t['rango'][0], t['fmt'])} – {an.formato(t['rango'][1], t['fmt'])}</span></div>"
    return (f"<div class='ri-card' style='--c:{_COLOR[t['color']]}' title='{html(t['que_es'])}'><h4>{html(t['nombre'])}</h4>"
            f"<div class='v'>{an.formato(t['valor'], t['fmt'])}</div>{filas}<div class='f'>{html(t['fuente'])}</div></div>")


def _estrellas(n: int) -> str:
    return "★" * n + "☆" * (5 - n)


def analisis(ticker: str, f: dict, h: pd.DataFrame, nombre: str, ref_close, prudencia: float, idioma: tuple[str, str]) -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    clave = f"analisis_{ticker}"
    usar_sec = "@" in config.sec_ua()
    if clave not in st.session_state or st.session_state[clave].get("prudencia") != prudencia:
        with st.spinner("Reuniendo cuentas, previsiones, comparables y noticias… (10-20 segundos la primera vez)"):
            try:
                datos_an = reunir(ticker, f, h, nombre, ref_close, prudencia, idioma, usar_sec)
            except Exception as e:  # noqa: BLE001
                st.error(f"No pude completar el análisis ({type(e).__name__}: {e}). Revisa la conexión y vuelve a intentarlo.")
                return
        datos_an["prudencia"] = prudencia
        st.session_state[clave] = datos_an
    d = st.session_state[clave]
    m, a = d["m"], d["an"]
    moneda = m.get("moneda") or f.get("currency") or ""
    a_eur = cambio_a_euros(moneda)
    rec, cal, est = a["recomendacion"], a["calidad"], a["estrellas"]
    color_rec = {"verde": VERDE, "amarillo": AMBAR, "rojo": ROJO}[rec["color"]]

    if m.get("tipo") in ("ETF", "INDEX", "MUTUALFUND") or (not m.get("periodo") and f.get("quoteType") in ("ETF", "INDEX")):
        st.info("Esto es un fondo o un índice, no una empresa: no tiene cuentas que analizar. Mira 🏢 Ficha, 🚦 Señales y 🎯 Escenarios.")
        return

    # --- cabecera: lo esencial de un vistazo
    c1, c2, c3, c4 = st.columns([2.2, 1, 1, 1])
    c1.markdown(f"<div class='ri-box' style='--c:{color_rec};margin:0'><div class='t'>{rec['etiqueta'].split(' ')[0]} {html(rec['titulo'])}</div>"
                f"<div>Precio {html(con_euros(m.get('precio'), moneda, a_eur))} · precio <b>{rec['precio_juicio']}</b> · "
                f"calidad <b>{cal['etiqueta'].lower()}</b></div></div>", unsafe_allow_html=True)
    c2.metric("Escenario base (12-18 m)", f"{rec['rent_base'] * 100:+.0f} %".replace(".", ",") if rec.get("rent_base") is not None else "—",
              help="Rentabilidad total estimada, dividendos incluidos, si las cosas van como es más probable.")
    c3.metric("Si sale mal", f"{rec['rent_pesimista'] * 100:+.0f} %".replace(".", ",") if rec.get("rent_pesimista") is not None else "—")
    c4.metric("Calidad del negocio", cal["etiqueta"])
    st.caption("Análisis generado con reglas automáticas sobre datos públicos (no lo escribe una persona ni una IA). Abajo tienes cada paso "
               "con sus supuestos. " + a["aviso"])

    from . import vistas3

    vistas3.panel_plazos(h, ref_close, prudencia, rec)

    # --- 1. datos
    st.subheader("1 · Datos y fuentes")
    fuentes = [f"**Precio y cotización:** Yahoo Finance, {eventos.bolsa_de(ticker)} (con ~15 min de retraso)",
               f"**Cuentas:** Yahoo Finance, {m.get('periodo') or 'sin cuentas disponibles'}"
               + (f", en {m['moneda_cuentas']}" if m.get("moneda_cuentas") and m["moneda_cuentas"] != m.get("moneda_base") else ""),
               "**Previsiones y precios objetivo:** consenso de analistas recogido por Yahoo Finance",
               "**Histórico de valoración:** cálculo propio con precios y cuentas anuales",
               "**Sector:** " + (f"PER del ETF sectorial {d['etf']} (Yahoo Finance)" if d.get("per_etf") else "referencias orientativas de largo plazo")]
    if d["seg"].get("fuente"):
        fuentes.append("**Negocio:** " + d["seg"]["fuente"])
    st.markdown(" · ".join(fuentes))
    for aviso in m.get("avisos", []):
        st.warning(aviso)
    st.caption(f"Datos reunidos el {d['momento']:%d/%m/%Y a las %H:%M}. Si otra web te da un PER o un EV/EBITDA distinto, suele ser porque "
               "usa beneficio previsto en vez del de los últimos 12 meses, beneficio «ajustado» en vez del contable, o la cotización de otra bolsa.")
    if st.button("🔄 Volver a calcular con datos nuevos", key=f"recalc_{ticker}"):
        st.session_state.pop(clave, None)
        st.rerun()

    # --- 2. métricas
    st.subheader("2 · Métricas fundamentales")
    if a["metricas"]:
        st.markdown("<div class='ri-grid'>" + "".join(_tarjeta(t) for t in a["metricas"]) + "</div>", unsafe_allow_html=True)
        st.caption("Borde verde = mejor que sus referencias · rojo = peor · gris = parecido o sin referencia. Pasa el ratón por una tarjeta "
                   "para ver qué mide. El PER de «Sector» es "
                   + (f"el del ETF {d['etf']}." if d.get("per_etf") else "una referencia orientativa de largo plazo, no un dato de hoy."))
        peg = m.get("peg")
        if peg is not None and 0 < peg < 1:
            st.success(f"PEG de {num(peg)}: por debajo de 1, estás pagando poco por el crecimiento esperado. Es una señal positiva, "
                       "siempre que ese crecimiento se cumpla.")
    else:
        st.info("Yahoo no tiene cuentas de esta empresa, así que no puedo calcular sus ratios.")
    if d["comparables"]:
        with st.expander("Competidores usados en la comparación"):
            tabla = pd.DataFrame([{"Empresa": c.get("nombre"), "Ticker": c["ticker"], "PER": c.get("per"), "PER previsto": c.get("per_fwd"),
                                   "EV/EBITDA": c.get("ev_ebitda"), "P/FCF": c.get("p_fcf"), "ROE": c.get("roe"), "ROIC": c.get("roic"),
                                   "Margen operativo": c.get("margen_op"), "Dividendo": c.get("div_yield")} for c in d["comparables"]])
            st.dataframe(tabla, hide_index=True, width="stretch", column_config={
                **{k: st.column_config.NumberColumn(format="%.1f") for k in ("PER", "PER previsto", "EV/EBITDA", "P/FCF")},
                **{k: st.column_config.NumberColumn(format="percent") for k in ("ROE", "ROIC", "Margen operativo", "Dividendo")}})
            st.caption("Del mismo sector en la base del programa o, si no hay, los que Yahoo considera similares. Calculados igual que los de la empresa.")
    anual = m.get("anual")
    if anual is not None and not anual.empty:
        with st.expander("Evolución de los últimos ejercicios"):
            div = 1e9
            evo = pd.DataFrame({"Ejercicio": [f"{x:%Y}" for x in anual.index], "Ingresos (mil M)": anual["ingresos"] / div,
                                "Beneficio (mil M)": anual["neto"] / div, "Caja libre (mil M)": anual["fcf"] / div,
                                "Margen operativo": anual["margen_op"], "ROIC": anual["roic"], "PER al cierre": anual["per"],
                                "Acciones (M)": anual["acciones"] / 1e6})
            c1, c2 = st.columns(2)
            for col, columna in ((c1, "Ingresos (mil M)"), (c2, "Beneficio (mil M)")):
                fig = go.Figure(go.Bar(x=evo["Ejercicio"], y=evo[columna], marker_color=AZUL, marker_line_width=0,
                                       text=[num(v, 1) for v in evo[columna]], textposition="outside",
                                       hovertemplate="%{x}: %{y:,.2f} mil M<extra></extra>"))
                fig.update_layout(title=f"{columna} · {m.get('moneda_cuentas', '')}", height=260, margin=dict(l=10, r=10, t=40, b=10),
                                  yaxis=dict(showgrid=True, zeroline=True), xaxis=dict(type="category"), showlegend=False, bargap=0.45)
                col.plotly_chart(fig, width="stretch", key=f"evo_{columna}_{ticker}")
            st.dataframe(evo, hide_index=True, width="stretch", column_config={
                **{k: st.column_config.NumberColumn(format="%.2f") for k in ("Ingresos (mil M)", "Beneficio (mil M)", "Caja libre (mil M)")},
                "Margen operativo": st.column_config.NumberColumn(format="percent"), "ROIC": st.column_config.NumberColumn(format="percent"),
                "PER al cierre": st.column_config.NumberColumn(format="%.1f"), "Acciones (M)": st.column_config.NumberColumn(format="%.0f")})

    # --- 3. calidad
    st.subheader(f"3 · Calidad del negocio: {cal['etiqueta']}")
    for c in cal["criterios"]:
        icono = {2: "✅", 1: "➖", 0: "⚠️"}[c["nota"]]
        st.markdown(f"{icono} **{c['criterio']}** — *{c['pregunta']}*  \n{esc(c['texto'])}")
    st.info(f"**Valoración global: {cal['etiqueta']}.** {cal['frase'].split('.', 1)[1].strip()} "
            "Recuerda: esto mide lo buena que es la empresa, no si la acción es buena compra al precio de hoy.")

    # --- 4. perfiles
    st.subheader("4 · ¿Para qué tipo de inversión sirve?")
    c1, c2, c3 = st.columns(3)
    for col, titulo, n, porque in ((c1, "¿Interesa para crecimiento?", est["crecimiento"], est["por_que_crecimiento"]),
                                   (c2, "¿Interesa para dividendos?", est["dividendos"], est["por_que_dividendos"]),
                                   (c3, "¿Es apta para DCA?", est["dca"], a["dca"]["veredicto"])):
        col.markdown(f"**{titulo}**<div class='ri-star'>{_estrellas(n)}</div><small>{html(porque[0].upper() + porque[1:])}</small>",
                     unsafe_allow_html=True)
    st.markdown(est["encaje"])
    st.markdown("**4b · ¿Apta para ir comprando poco a poco (DCA)?**")
    for nota, linea in a["dca"]["lineas"]:
        st.markdown(f"{ {2: '✅', 1: '➖', 0: '⚠️'}[nota]} {esc(linea)}")
    (st.success if a["dca"]["veredicto"] == "Muy apta" else st.warning if a["dca"]["veredicto"].startswith("Apta") else st.error)(
        f"**Veredicto DCA — {a['dca']['veredicto']}.** {a['dca']['frase']}")

    # --- 5. catalizadores
    st.subheader("5 · Catalizadores y proyectos futuros")
    if a["catalizadores"]:
        for c in a["catalizadores"]:
            flecha = {1: "🟢", -1: "🔴", 0: "⚪"}[c["signo"]]
            enlace = f" [abrir]({c['enlace']})" if c.get("enlace") else ""
            st.markdown(f"{flecha} **{c['tipo']}** · probabilidad {c['prob']} · impacto {c['impacto']}  \n{esc(c['texto'])}{enlace}")
        st.caption("🟢 a favor · 🔴 en contra · ⚪ puede ir en cualquier dirección. Los proyectos concretos (fábricas, productos, contratos) "
                   "salen de los titulares de las dos últimas semanas: mira también 📰 Noticias.")
    else:
        st.caption("No he encontrado catalizadores claros con los datos disponibles.")

    # --- 6. técnico
    st.subheader("6 · Momento de mercado (solo para afinar la entrada, no para valorar)")
    t = a["tecnico"]
    if t:
        c = st.columns(4)
        c[0].metric("Tendencia", t["tendencia"].capitalize(), f"{t['vs_m200'] * 100:+.0f} % vs media 200".replace(".", ",") if t.get("vs_m200") is not None else None,
                    delta_color="off")
        c[1].metric("Desde máximo 52 sem.", f"{t['desde_max'] * 100:.0f} %", f"máx. {num(t['max52'], _dec(t['max52']))}", delta_color="off")
        c[2].metric("Últimas 4 / 8 semanas", f"{(t.get('r4') or 0) * 100:+.0f} % / {(t.get('r8') or 0) * 100:+.0f} %")
        c[3].metric("Volatilidad anual", f"{t['vol_anual'] * 100:.0f} %", f"peor caída {t['caida_max_5a'] * 100:.0f} %", delta_color="off")
        for k in ("frase_tendencia", "frase_rango", "frase_momentum", "frase_resultados"):
            if t.get(k):
                st.markdown("- " + esc(t[k]))
        if not d["reaccion"].empty:
            with st.expander("Reacción a las últimas presentaciones de resultados"):
                st.dataframe(d["reaccion"], hide_index=True, width="stretch", column_config={
                    "Sorpresa": st.column_config.NumberColumn(format="percent"), "Reacción": st.column_config.NumberColumn("Reacción al día siguiente", format="percent"),
                    "BPA esperado": st.column_config.NumberColumn(format="%.2f"), "BPA publicado": st.column_config.NumberColumn(format="%.2f")})

    # --- 7. escenarios
    e = a["escenarios"]
    st.subheader(f"7 · Tres escenarios de precio a 12-18 meses")
    if e.get("escenarios"):
        cols = st.columns(3)
        for col, s in zip(cols, e["escenarios"]):
            color = VERDE if s["nombre"].startswith("🟢") else ROJO if s["nombre"].startswith("🔴") else AZUL
            etiqueta_rent = "Pérdida estimada" if s["rent_total"] < 0 else "Rentabilidad total"
            col.markdown(
                f"<div class='ri-esc' style='--c:{color}'><b>{html(s['nombre'])}</b>"
                f"<div class='p'>{num(s['bajo'], _dec(s['bajo']))} – {num(s['alto'], _dec(s['alto']))} {html(moneda)}</div>"
                + (f"<div class='s'>≈ {num(s['bajo'] * a_eur, _dec(s['bajo'] * a_eur))} – {num(s['alto'] * a_eur, _dec(s['alto'] * a_eur))} €</div>" if a_eur else "")
                + f"<div class='s'><b>{etiqueta_rent}: {s['rent_total'] * 100:+.0f} %</b> (precio {s['rent_precio'] * 100:+.0f} %"
                + (f" + dividendo {e['dividendo_periodo'] * 100:.1f} %".replace(".", ",") if e["dividendo_periodo"] > 0.002 else "")
                + f")</div><div class='s' style='margin-top:6px'><b>Condiciones:</b> {html(s['condiciones'])}</div>"
                f"<div class='s'><b>Método:</b> {html(s['metodo'])}</div></div>", unsafe_allow_html=True)
        st.caption(f"Metodología: {e['metodo']}. Los precios son rangos a propósito.")
        with st.expander("Supuestos y contraste con otras dos referencias", expanded=False):
            for sup in e["supuestos"]:
                st.markdown("- " + esc(sup))
            contraste = []
            if e.get("analistas"):
                x = e["analistas"]
                contraste.append({"Referencia": f"Analistas ({int(x['n'] or 0)})", "Bajo": x["bajo"], "Central": x["medio"], "Alto": x["alto"]})
            if e.get("estadistico"):
                x = e["estadistico"]
                contraste.append({"Referencia": "Estadístico (volatilidad histórica, 15 meses)", "Bajo": x["p10"], "Central": x["p50"], "Alto": x["p90"]})
            if contraste:
                esc_ = {s["nombre"][:1]: s["centro"] for s in e["escenarios"]}
                contraste.insert(0, {"Referencia": "Estos escenarios (múltiplos)", "Bajo": esc_.get("🔴"), "Central": esc_.get("🔵"), "Alto": esc_.get("🟢")})
                st.dataframe(pd.DataFrame(contraste), hide_index=True, width="stretch", column_config={
                    k: st.column_config.NumberColumn(f"{k} ({moneda})", format="%.2f") for k in ("Bajo", "Central", "Alto")})
                st.caption("Si los tres métodos coinciden, más confianza. Si discrepan mucho (típico cuando los analistas extrapolan un "
                           "crecimiento muy alto), fíate del más prudente.")
    else:
        st.warning("No hay datos suficientes para construir escenarios de precio con una metodología defendible.")

    # --- 8. riesgos
    st.subheader("8 · Riesgos y tesis bajista")
    for r in a["riesgos"]["lista"]:
        st.markdown(f"{'🔴' if r['severidad'] == 2 else '🟡'} **{r['titulo']}** — {esc(r['texto'])}")
    st.error("**¿En qué escenario concreto sale muy mal?** " + a["riesgos"]["desastre"])

    # --- 9. veredicto
    st.subheader("9 · Veredicto")
    st.markdown(esc(a["veredicto"]))

    # --- 10. recomendación
    st.subheader("10 · Recomendación")
    st.markdown(f"<div class='ri-box' style='--c:{color_rec}'><div class='t'>{html(rec['etiqueta'])}"
                + (f" · {html(rec['titulo'])}" if rec["titulo"] not in rec["etiqueta"] else "") + "</div>"
                f"<div style='margin-top:6px'>{html(rec['texto']).replace('**', '')}</div>"
                + (f"<div style='margin-top:6px'><b>Precio de entrada sugerido: {html(con_euros(rec['entrada'], moneda, a_eur))} o menos.</b></div>" if rec.get("entrada") else "")
                + "</div>", unsafe_allow_html=True)
    st.markdown(f"*{a['aviso']}*")

    # --- 11. resumen llano
    st.subheader("11 · En cristiano")
    st.markdown(f"<div class='ri-box' style='--c:{NEUTRO}'>{html(a['resumen'])}</div>", unsafe_allow_html=True)

    st.subheader("Guardar o compartir este análisis")
    from . import vistas2

    vistas2.botones_exportar(a, m, moneda, ticker)
    with st.expander("🤖 ¿Quieres una segunda opinión de una IA? Copia este texto y pégalo en Claude o ChatGPT"):
        st.caption("Incluye tus instrucciones de análisis y todos los datos que ha reunido el programa, para que la IA redacte su propia versión "
                   "y la puedas comparar con esta. Las instrucciones se pueden editar: están en " + str(RUTA_PROMPT) + ".")
        texto = an.texto_para_ia(a, m, instrucciones_ia())
        st.download_button("⬇️ Descargar como archivo de texto", texto.encode("utf-8"), f"analisis_{ticker}.md", "text/markdown")
        st.code(texto, language="markdown")


# ----------------------------------------------------------------------------- 💼 NEGOCIO
def _barras(tabla: pd.DataFrame, titulo: str, clave: str) -> None:
    t = tabla.copy()
    t["etiqueta"] = t["segmento"]
    t = t.iloc[::-1]
    opacidad = [0.55 if str(s).startswith("↳") else 1.0 for s in t["etiqueta"]]
    fig = go.Figure(go.Bar(x=t["pct"], y=t["etiqueta"], orientation="h", marker=dict(color=AZUL, opacity=opacidad, line_width=0),
                           text=[f"{v:.0f} %" if v >= 1 else f"{v:.1f} %".replace(".", ",") for v in t["pct"]], textposition="outside",
                           hovertemplate="%{y}: %{x:.1f} % de los ingresos<extra></extra>", cliponaxis=False))
    fig.update_layout(title=titulo, height=max(170, 44 * len(t) + 70), margin=dict(l=10, r=50, t=40, b=10), showlegend=False,
                      xaxis=dict(range=[0, max(100, float(t["pct"].max()) * 1.1)], showgrid=True, ticksuffix=" %"), bargap=0.4)
    st.plotly_chart(fig, width="stretch", key=clave)


def pantalla_negocio(ticker: str, f: dict, nombre: str, abrir_empresa) -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    id_base = conexiones.entidad(ticker, nombre)
    corto = conexiones.ficha_entidad(id_base)["nombre"] if id_base else conexiones.nombre_corto(nombre)
    usar_sec = "@" in config.sec_ua()
    with st.spinner("Leyendo de dónde vienen sus ingresos…"):
        try:
            seg = negocio.segmentos(ticker, id_base, usar_sec)
        except Exception:  # noqa: BLE001
            seg = {"ejes": {}}
    st.subheader("💰 De dónde viene el dinero")
    if seg["ejes"]:
        frase = negocio.frase_resumen(corto, seg)
        if frase:
            st.markdown("#### " + frase)
        st.caption(f"Fuente: {seg['fuente']}" + (f" · {seg['ejercicio']}" if seg.get("ejercicio") else "")
                   + (f" · [ver informe]({seg['url']})" if seg.get("url") else ""))
        ejes = [e for e in ("producto", "negocio", "cliente", "geografia") if e in seg["ejes"]]
        cols = st.columns(2)
        for i, eje in enumerate(ejes):
            tabla = seg["ejes"][eje]
            with cols[i % 2]:
                _barras(tabla, negocio.EJES[eje] + (" (aprox.)" if "aprox" in tabla else ""), f"seg_{eje}_{ticker}")
                desc = tabla if "descripcion" in tabla else seg.get("descripciones", {}).get(eje)
                if desc is not None and "descripcion" in desc and (desc["descripcion"] != "").any():
                    with st.expander("Qué incluye cada uno"):
                        for _, r in desc[desc["descripcion"] != ""].iterrows():
                            st.markdown(f"- **{r['segmento']}** ({r['pct']:.0f} %): {esc(r['descripcion'])}")
        if seg.get("oficial") and seg.get("total"):
            st.caption(f"Ingresos totales del ejercicio: {num(seg['total'] / 1e9, 1)} mil millones. Las filas con ↳ son partes de la fila de arriba.")
    else:
        st.info("No tengo el desglose de ingresos de esta empresa. "
                + ("" if usar_sec else "Si cotiza en EE. UU., guarda tu nombre y correo para la SEC (abajo) y lo leeré de su informe anual. ")
                + "Para empresas europeas fuera de la base, míralo en su informe anual (sección «información por segmentos»).")
    if not usar_sec:
        with st.expander("🔓 Activar las cifras oficiales de la SEC (empresas que cotizan en EE. UU.)"):
            st.caption("La SEC exige identificarse con nombre y correo en cada consulta. Se guarda solo en tu ordenador y sirve también para 🕸️ Conexiones.")
            contacto = st.text_input("Tu nombre y correo", placeholder="Nombre Apellido tu_correo@dominio.com", key="sec_negocio")
            if st.button("Guardar", key="sec_negocio_btn") and "@" in contacto:
                config.guardar_sec_contacto(contacto)
                st.rerun()

    rel = conexiones.unificar(suministro.cargar_relaciones(), None)
    cli = negocio.clientes_con_finalidad(rel, corto)
    prov = negocio.proveedores_con_finalidad(rel, corto)
    st.subheader(f"📦 A dónde va lo que produce: quién le compra y para qué ({len(cli)})")
    if len(cli):
        grupos = negocio.por_categoria(cli)
        if len(grupos) > 1:
            st.markdown(" ".join(f"<span class='ri-chip'><b>{html(r['Categoría'] or 'Otros')}</b> · {r['n']}</span>" for _, r in grupos.iterrows()),
                        unsafe_allow_html=True)
        st.dataframe(cli.drop(columns=["Categoría"]), hide_index=True, width="stretch", column_config={
            "Qué le compra": st.column_config.TextColumn(width="medium"), "Para qué": st.column_config.TextColumn("Para qué lo usa", width="large")})
        st.caption("Confianza **alta** = relación pública y conocida · **media** = publicada, conviene verificar · **tuya** = la añadiste tú. "
                   "La lista no es completa: por ley las empresas solo publican los clientes que superan el 10 % de sus ventas.")
        nombres_cli = [c for c in cli["Cliente"] if conexiones.ticker_por_nombre(c)][:8]
        if nombres_cli:
            st.markdown("**Abrir un cliente:**")
            for col, c in zip(st.columns(len(nombres_cli)), nombres_cli):
                col.button(c[:18], key=f"cli_{c}", on_click=abrir_empresa, args=(conexiones.ticker_por_nombre(c), "💼 Negocio"), width="stretch")
    else:
        st.info(f"No tengo clientes identificados de {corto}. Si vende sobre todo a particulares, es normal. Puedes buscarlos en "
                "🕸️ Conexiones → «Buscar en informes de otras empresas» o añadirlos en tu tabla.")
    st.subheader(f"🏭 De quién depende para producir: proveedores ({len(prov)})")
    if len(prov):
        st.dataframe(prov.drop(columns=["Categoría"]), hide_index=True, width="stretch", column_config={
            "Qué le vende": st.column_config.TextColumn(width="medium"), "Para qué": st.column_config.TextColumn("Para qué lo necesita", width="large")})
    else:
        st.caption("Sin proveedores identificados en la base.")
    from . import vistas2

    vistas2.senales_cadena(corto, cli, prov)
    st.caption("Para ver todo esto como un mapa y pinchar de empresa en empresa, ve a 🕸️ Conexiones.")


# ----------------------------------------------------------------------------- 🟩 MAPA DE CALOR
def pantalla_calor(abrir_empresa) -> None:
    st.caption("Cada casilla es un valor del índice: el tamaño es el dinero que mueve al día y el color, lo que sube o baja. "
               "Sirve para ver de un vistazo si el día es bueno o malo y dónde está la acción.")
    c1, c2 = st.columns([2, 2])
    indice = c1.selectbox("Índice", ["IBEX 35", "Nasdaq-100", "Dow Jones", "S&P 100", "Euro Stoxx 50", "DAX 40", "CAC 40", "FTSE 100",
                                     "FTSE MIB", "S&P 500 (tarda ~1 min)"])
    periodo = c2.radio("Variación", ["Hoy", "1 semana", "1 mes"], horizontal=True)
    try:
        tickers = datos.lista_indice(indice.split(" (")[0])
        ohlc = datos.ohlc_varios(tuple(tickers), "3mo")
    except Exception as e:  # noqa: BLE001
        st.warning(f"No pude cargar el índice ({type(e).__name__}). Inténtalo de nuevo en unos minutos.")
        return
    saltos = {"Hoy": 1, "1 semana": 5, "1 mes": 21}[periodo]
    filas = []
    for t, df in ohlc.items():
        c = df["Close"].dropna()
        if len(c) <= saltos:
            continue
        negociado = float((df["Close"] * df["Volume"]).tail(20).mean()) if "Volume" in df else 1.0
        filas.append({"Ticker": t, "Variación": float(c.iloc[-1] / c.iloc[-1 - saltos] - 1), "Precio": float(c.iloc[-1]),
                      "Negociado": max(negociado, 1.0)})
    if not filas:
        st.info("Sin datos para este índice ahora mismo.")
        return
    df = pd.DataFrame(filas).sort_values("Negociado", ascending=False)
    limite = {"Hoy": 0.04, "1 semana": 0.08, "1 mes": 0.15}[periodo]
    fig = go.Figure(go.Treemap(
        labels=df["Ticker"], parents=[""] * len(df), values=np.sqrt(df["Negociado"]),
        text=[f"{v * 100:+.1f} %".replace(".", ",") for v in df["Variación"]], textinfo="label+text",
        customdata=np.stack([df["Precio"], df["Variación"] * 100], axis=-1),
        hovertemplate="<b>%{label}</b><br>Precio %{customdata[0]:,.2f}<br>Variación %{customdata[1]:+.2f} %<extra></extra>",
        marker=dict(colors=df["Variación"].clip(-limite, limite), colorscale=[[0, ROJO], [0.5, "#383835"], [1, VERDE]],
                    cmid=0, cmin=-limite, cmax=limite, line=dict(width=2, color="#0d0d0d"),
                    colorbar=dict(thickness=10, tickformat="+.0%", len=0.6)),
        textfont=dict(color="#ffffff"), tiling=dict(pad=0)))
    fig.update_layout(height=560, margin=dict(l=0, r=0, t=6, b=0), paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#c3c2b7"))
    st.plotly_chart(fig, width="stretch", key=f"calor_{indice}_{periodo}", on_select="rerun", theme=None)
    suben, bajan = int((df["Variación"] > 0).sum()), int((df["Variación"] < 0).sum())
    m = st.columns(4)
    m[0].metric("Suben / bajan", f"{suben} / {bajan}")
    m[1].metric("Variación mediana", f"{df['Variación'].median() * 100:+.2f} %".replace(".", ","))
    mejor, peor = df.loc[df["Variación"].idxmax()], df.loc[df["Variación"].idxmin()]
    m[2].metric("Mejor", mejor["Ticker"], f"{mejor['Variación'] * 100:+.1f} %".replace(".", ","))
    m[3].metric("Peor", peor["Ticker"], f"{peor['Variación'] * 100:+.1f} %".replace(".", ","))
    with st.expander("Ver como tabla (y abrir un valor)"):
        st.dataframe(df.sort_values("Variación", ascending=False).drop(columns=["Negociado"]), hide_index=True, width="stretch",
                     column_config={"Variación": st.column_config.NumberColumn(format="percent"),
                                    "Precio": st.column_config.NumberColumn(format="%.2f")})
        elegido = st.selectbox("Abrir el análisis de", list(df["Ticker"]), key="calor_abrir")
        st.button(f"🧠 Analizar {elegido}", on_click=abrir_empresa, args=(elegido,), key="calor_btn")
