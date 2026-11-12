"""📅 Plan mensual: analiza en conjunto lo que aportas cada mes (de 2 a 20 activos) y propone cómo repartirlo mejor.

Admite acciones, fondos y ETF, criptomonedas y materias primas. No usa IA: reutiliza el análisis de cada activo que ya
hace el programa (🧠 Análisis, 🪙 Cripto) y añade la mirada de conjunto: para qué sirve cada pieza, por dónde flaquea la
cartera, qué conviene pausar y cómo repartir los mismos euros con más cabeza.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import yfinance as yf

from . import analisis as an
from . import conexiones, cripto, datos, materias, negocio
from . import fundamentales as fu
from .cache import con_cache
from .config import CARPETA

RUTA = CARPETA / "plan_mensual.json"
MAXIMO = 20
TIPOS_MANUALES = {
    "Fondo indexado mundial": ("fondo", "base"), "Fondo indexado EE. UU.": ("fondo", "base"), "Fondo indexado Europa": ("fondo", "base"),
    "Fondo de emergentes": ("fondo", "tematico"), "Fondo temático o sectorial": ("fondo", "tematico"),
    "Fondo de renta fija / monetario": ("fondo", "renta_fija"), "Oro": ("materia", "refugio"),
}
ROLES = {
    "base": ("🌍 Base diversificada", "El cimiento: muchas empresas de golpe. Es lo que más debería pesar."),
    "tematico": ("🎯 Fondo concentrado", "Fondo centrado en un sector, país o tema: diversifica menos de lo que parece."),
    "renta_fija": ("🧯 Estabilizador", "Renta fija o monetario: da poco, pero amortigua las caídas."),
    "dividendos": ("💰 Dividendos de cara al futuro", "Paga un dividendo apreciable y sostenible: renta que crece con los años."),
    "dividendo_dudoso": ("💸 Dividendo en duda", "Paga mucho dividendo, pero hay señales de que puede no sostenerlo."),
    "estable": ("🌱 Crecimiento estable", "Negocio de calidad que crece año tras año sin sobresaltos."),
    "rapido": ("📈 Crecimiento rápido", "Crece deprisa y ya gana dinero. Si el crecimiento se frena, la acción cae fuerte."),
    "explosivo": ("🚀 Crecimiento explosivo (especulativo)", "Puede multiplicarse o hundirse: aún no gana dinero de verdad."),
    "ciclica": ("🔄 Cíclica", "Sus beneficios suben y bajan con la economía o con el precio de una materia prima."),
    "valor": ("🧱 Valor / defensiva", "Negocio maduro a precio razonable: crece poco, aguanta bien."),
    "mixta": ("⚖️ Sin perfil claro", "No destaca ni por dividendo, ni por crecimiento, ni por precio."),
    "refugio": ("🛡️ Refugio", "Suele aguantar o subir cuando la bolsa cae. No produce nada: protege, no crece."),
    "materia": ("⛏️ Materia prima", "Depende de la oferta y la demanda mundiales. Muy cíclica y sin rentas."),
    "reserva_digital": ("🪙 Reserva de valor digital", "Bitcoin: la criptomoneda más sólida, pero puede caer a la mitad en meses."),
    "cripto": ("🎲 Cripto especulativa", "Criptomoneda distinta de bitcoin: más recorrido en las subidas y mucho más en las bajadas."),
    "nada": ("⚪ No aporta", "No es una inversión que pueda crecer (moneda estable o copia de otro activo)."),
    "desconocido": ("❓ Sin datos", "No he encontrado datos de este activo."),
}
ESPECULATIVOS = ("explosivo", "cripto", "reserva_digital")
# Rentabilidad anual supuesta (pesimista, base, optimista) para la proyección. Son supuestos prudentes, no predicciones.
SUPUESTOS = {"base": (0.02, 0.06, 0.09), "tematico": (0.0, 0.06, 0.10), "renta_fija": (0.01, 0.025, 0.04), "dividendos": (0.01, 0.06, 0.09),
             "dividendo_dudoso": (-0.04, 0.03, 0.08), "estable": (0.01, 0.07, 0.10), "rapido": (-0.03, 0.07, 0.12),
             "explosivo": (-0.12, 0.05, 0.14), "ciclica": (-0.03, 0.05, 0.10), "valor": (0.0, 0.05, 0.09), "mixta": (-0.02, 0.05, 0.09),
             "refugio": (0.0, 0.03, 0.06), "materia": (-0.04, 0.02, 0.07), "reserva_digital": (-0.10, 0.07, 0.15),
             "cripto": (-0.20, 0.04, 0.18), "nada": (0.0, 0.0, 0.0), "desconocido": (-0.02, 0.04, 0.08)}
_SECTOR_FONDO = {"technology": "Tecnología", "communication_services": "Comunicaciones", "consumer_cyclical": "Consumo cíclico",
                 "consumer_defensive": "Consumo defensivo", "healthcare": "Salud", "financial_services": "Finanzas", "industrials": "Industria",
                 "energy": "Energía", "basic_materials": "Materiales", "utilities": "Servicios públicos", "realestate": "Inmobiliario"}
# Candidatas conocidas para tapar huecos. Solo se enseñan las que HOY pasan el análisis del programa.
CANDIDATAS = {
    "dividendos": ["IBE.MC", "ALV.DE", "JNJ", "PG", "KO", "SAN.PA", "NESN.SW", "ENG.MC", "PEP", "ULVR.L"],
    "estable": ["MSFT", "V", "MA", "GOOGL", "ASML.AS", "ITX.MC", "SAP.DE", "MC.PA", "NOVO-B.CO", "AAPL"],
    "rapido": ["NVDA", "AVGO", "AMZN", "META", "TSM", "LLY", "NOW", "ANET", "MELI", "ASML.AS"],
}
RUTA_PERFIL = CARPETA / "plan_perfil.txt"
# Perfil de riesgo: cambia los topes y qué tipo de piezas se premian. «espec» y «cripto» son el peso máximo conjunto;
# «topes» el máximo por activo según su perfil; «sector» a partir de qué peso un sector cuenta como concentración;
# «extra» puntos que se suman o restan a la nota de cada pieza al repartir.
PERFILES = {
    "Bajo": {"espec": 0.10, "cripto": 0.05, "sector": 0.35, "unico": 0.25,
             "topes": {"reserva_digital": 0.05, "cripto": 0.02, "explosivo": 0.03, "refugio": 0.15, "materia": 0.05, "renta_fija": 0.60},
             "extra": {"dividendos": 12, "valor": 10, "renta_fija": 10, "refugio": 8, "base": 5, "estable": 5, "ciclica": -5, "rapido": -8,
                       "reserva_digital": -10, "explosivo": -15, "cripto": -15},
             "frase": "Prefieres dormir tranquilo: se premian dividendos, negocios maduros y refugio, y lo especulativo se limita mucho."},
    "Medio": {"espec": 0.20, "cripto": 0.10, "sector": 0.40, "unico": 0.30,
              "topes": {"reserva_digital": 0.10, "cripto": 0.04, "explosivo": 0.08, "refugio": 0.10, "materia": 0.05, "renta_fija": 0.40},
              "extra": {}, "frase": "Equilibrio: crecimiento con algo de protección, y lo especulativo como parte pequeña."},
    "Alto": {"espec": 0.40, "cripto": 0.15, "sector": 0.60, "unico": 0.35,
             "topes": {"reserva_digital": 0.15, "cripto": 0.06, "explosivo": 0.15, "refugio": 0.10, "materia": 0.08, "renta_fija": 0.20},
             "extra": {"rapido": 10, "explosivo": 8, "estable": 3, "refugio": -5, "renta_fija": -10},
             "frase": "Aceptas caídas fuertes a cambio de más recorrido: se admite mucho más crecimiento rápido, tecnología y apuestas."},
}
DEFENSIVOS = ("dividendos", "valor", "refugio", "renta_fija", "base")
CRECIMIENTO = ("estable", "rapido", "explosivo")


def cargar_perfil() -> str:
    try:
        t = RUTA_PERFIL.read_text(encoding="utf-8").strip()
        return t if t in PERFILES else "Medio"
    except OSError:
        return "Medio"


def guardar_perfil(perfil: str) -> None:
    if perfil in PERFILES:
        RUTA_PERFIL.parent.mkdir(parents=True, exist_ok=True)
        RUTA_PERFIL.write_text(perfil, encoding="utf-8")


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and np.isnan(x))


# ----------------------------------------------------------------------------- guardar y cargar
def cargar() -> pd.DataFrame:
    try:
        df = pd.DataFrame(json.loads(RUTA.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        df = pd.DataFrame()
    for col in ("activo", "euros", "tengo", "tipo"):
        if col not in df:
            df[col] = pd.Series(dtype="float" if col in ("euros", "tengo") else "str")
    df = df[["activo", "euros", "tengo", "tipo"]]
    for col in ("euros", "tengo"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["tipo"] = df["tipo"].fillna("").astype(str)
    return df


def limpiar(df: pd.DataFrame) -> pd.DataFrame:
    """Filas válidas: con nombre y con algo que aportar al mes o algo ya invertido. Vacío cuenta como cero."""
    d = df.copy()
    d["activo"] = d["activo"].fillna("").astype(str).str.strip()
    for col in ("euros", "tengo"):
        d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0.0).clip(lower=0) if col in d else 0.0
    d["tipo"] = d["tipo"].fillna("").astype(str) if "tipo" in d else ""
    d = d[(d["activo"] != "") & ((d["euros"] > 0) | (d["tengo"] > 0))]
    d = d.groupby("activo", as_index=False, sort=False).agg(euros=("euros", "sum"), tengo=("tengo", "sum"), tipo=("tipo", "first"))
    return d.head(MAXIMO).reset_index(drop=True)


def guardar(df: pd.DataFrame) -> None:
    RUTA.parent.mkdir(parents=True, exist_ok=True)
    RUTA.write_text(json.dumps(limpiar(df).to_dict("records"), ensure_ascii=False), encoding="utf-8")


# ----------------------------------------------------------------------------- reconocer qué es cada cosa
def _sin_tildes(t: str) -> str:
    return datos._sin_tildes(t) if hasattr(datos, "_sin_tildes") else t.lower()


def resolver(texto: str, tipo_manual: str = "") -> dict:
    """Averigua qué es lo que ha escrito el usuario: cripto, materia prima, fondo o acción."""
    t = texto.strip()
    bajo = _sin_tildes(t).lower()
    if tipo_manual in TIPOS_MANUALES:
        clase, rol = TIPOS_MANUALES[tipo_manual]
        if tipo_manual == "Oro":
            return {"clase": "materia", "ticker": "GC=F", "nombre": "Oro", "materia": "Oro"}
        return {"clase": "manual", "ticker": None, "nombre": t, "rol": rol, "tipo_manual": tipo_manual}
    # criptomonedas: por nombre, por sigla de las grandes o por par de Yahoo (BTC-EUR)
    par = re.fullmatch(r"([A-Za-z0-9]{2,10})-(USD|EUR|USDT)", t)
    try:
        mer = cripto.mercado(100)
    except Exception:  # noqa: BLE001
        mer = pd.DataFrame()
    if not mer.empty and "." not in t and "=" not in t:
        sig = (par.group(1) if par else t).upper()
        m1 = mer[(mer["nombre"].str.lower() == bajo) | (mer["id"] == bajo)]
        m2 = mer[(mer["simbolo"] == sig) & ((mer["puesto"] <= 40) | bool(par))]
        hit = m1 if len(m1) else m2 if (par or sig == t.upper() and len(t) <= 5 and len(m2) and not _es_accion_conocida(t)) else m1
        if len(hit):
            f = hit.iloc[0].to_dict()
            return {"clase": "cripto", "ticker": f"{f['simbolo']}-USD", "nombre": f["nombre"], "cripto": f}
    # materias primas: por nombre del catálogo o por ticker de futuro
    for nombre, datos_m in materias.MATERIAS.items():
        n = _sin_tildes(nombre).lower()
        if bajo == n or bajo == n.split()[0] and bajo not in ("gas",) or t.upper() == datos_m[0]:
            return {"clase": "materia", "ticker": datos_m[0], "nombre": nombre, "materia": nombre}
    if t.upper().endswith("=F"):
        return {"clase": "materia", "ticker": t.upper(), "nombre": t.upper(), "materia": None}
    # acciones y fondos
    try:
        res = datos.buscar_valores(t)
    except Exception:  # noqa: BLE001
        res = []
    ticker = res[0]["symbol"] if res else t.upper()
    try:
        f = datos.ficha(ticker)
    except Exception:  # noqa: BLE001
        f = {}
    nombre = f.get("shortName") or f.get("longName") or (res[0]["nombre"] if res else t)
    qt = f.get("quoteType") or (res[0].get("tipo") if res else None)
    if qt in ("ETF", "MUTUALFUND"):
        return {"clase": "fondo", "ticker": ticker, "nombre": nombre, "ficha": f}
    if qt == "CRYPTOCURRENCY":
        return {"clase": "cripto_yahoo", "ticker": ticker, "nombre": nombre, "ficha": f}
    if qt == "FUTURE":
        return {"clase": "materia", "ticker": ticker, "nombre": nombre, "materia": None}
    if not f.get("precio"):
        return {"clase": "desconocido", "ticker": ticker, "nombre": t}
    if not f.get("sector") and re.search(r"PHYSICAL|GOLD|ETC\b|SILVER|BULLION", str(nombre).upper()):
        oro = bool(re.search(r"GOLD|PHYSICAL MARKETS|BULLION", str(nombre).upper()))
        return {"clase": "materia", "ticker": ticker, "nombre": nombre, "materia": "Oro" if oro else None}
    return {"clase": "accion", "ticker": ticker, "nombre": nombre, "ficha": f}


def _es_accion_conocida(t: str) -> bool:
    try:
        return any(x.get("symbol", "").upper() == t.upper() for x in datos._en_la_base(t))
    except Exception:  # noqa: BLE001
        return False


# ----------------------------------------------------------------------------- evaluar cada activo
def _base(r: dict, **k) -> dict:
    d = {"clase": r["clase"], "ticker": r.get("ticker"), "nombre": r.get("nombre"), "sector": None, "pais": None, "divisa": None,
         "dividendo": None, "sectores": None, "dentro": None, "detalle": "", "comision": None}
    d.update(k)
    return d


def _eval_accion(r: dict) -> dict:
    t, f = r["ticker"], r.get("ficha") or {}
    m = fu.calcular(t, f)
    h = datos.historial(t, "5y")
    id_base = conexiones.entidad(t, f.get("longName") or "")
    ficha_base = conexiones.ficha_entidad(id_base) if id_base else {}
    try:
        seg = negocio.segmentos(t, id_base, usar_sec=False)
    except Exception:  # noqa: BLE001
        seg = None
    sector = an.sector_yahoo(f.get("sector"), ficha_base.get("sector"))
    nombre = ficha_base.get("nombre") or conexiones.nombre_corto(f.get("longName") or r["nombre"] or t)
    a = an.completo(nombre, m, h, sector=sector, industria=f.get("industry"), seg=seg)
    rec, cal, esc, trampa = a["recomendacion"], a["calidad"], a["escenarios"], a.get("trampa") or []
    div = m.get("div_yield") or 0
    crec = m.get("prev_crec_anio_sig") if _ok(m.get("prev_crec_anio_sig")) else m.get("crec_bpa_3a")
    crec_v = m.get("crec_ingresos_3a")
    per = m.get("per")
    buena = cal.get("media", 1) >= 1.3
    # --- para qué sirve
    if esc.get("tipo") == "ventas" or "ESPECULATIVA" in rec["etiqueta"]:
        rol = "explosivo"
    elif div >= 0.027:
        rol = "dividendo_dudoso" if (trampa or (_ok(m.get("payout")) and m["payout"] > 0.95) or cal.get("media", 1) < 0.9) else "dividendos"
    elif (_ok(crec) and crec >= 0.18 and _ok(crec_v) and crec_v >= 0.10) or (_ok(crec_v) and crec_v >= 0.18):
        rol = "rapido"
    elif buena and ((_ok(crec_v) and crec_v >= 0.05) or (_ok(crec) and crec >= 0.07)):
        rol = "estable"
    elif sector in ("Energy", "Basic Materials") or (cal.get("ciclo") == "alto" and not buena):
        rol = "ciclica"
    elif div >= 0.015 or (_ok(per) and per < 16):
        rol = "valor"
    else:
        rol = "mixta"
    # --- qué hacer
    rb, juicio = rec.get("rent_base"), rec.get("precio_juicio")
    if rec["color"] == "verde":
        accion, motivo = "seguir", f"Buen negocio a buen precio (escenario base {_p(rb)})."
    elif "ESPECULATIVA" in rec["etiqueta"]:
        accion, motivo = "poco", "Apuesta de crecimiento que no se puede valorar con rigor: solo con una parte pequeña."
    elif rec["color"] == "rojo":
        accion = "reducir" if trampa else "pausar"
        motivo = ("El negocio da señales de deterioro: " + ", ".join(trampa[:2]) + "." if trampa else
                  f"Ni el escenario base compensa ({_p(rb)})." if _ok(rb) else "El análisis no la recomienda.")
    elif juicio == "caro":
        accion, motivo = "pausar", f"Buena empresa, pero cara ahora (escenario base {_p(rb)}): mejor guardar esas aportaciones hasta que baje."
    elif juicio == "barato solo sobre el papel":
        accion, motivo = "poco", "Parece barata, pero el negocio no da confianza: no aumentar."
    else:
        accion, motivo = "seguir_sin_subir", f"Precio razonable, sin ganga (escenario base {_p(rb)}): seguir, sin aumentar."
    nota = 50 + 100 * max(min(rb if _ok(rb) else 0, 0.30), -0.25) + 15 * (cal.get("media", 1) - 1)
    nota += 5 if (a.get("tecnico") or {}).get("tendencia") == "alcista" else -5 if (a.get("tecnico") or {}).get("tendencia") == "bajista" else 0
    if rol == "explosivo":
        nota = min(nota, 40)
    if rol == "dividendo_dudoso":
        nota = min(nota, 35)
    return _base(r, nombre=nombre, rol=rol, accion=accion, motivo=motivo, nota=float(max(min(nota, 95), 5)),
                 sector=an.SECTOR_ES.get(sector or "", sector), pais=f.get("country"), divisa=(f.get("currency") or "").replace("GBp", "GBP"),
                 dividendo=div or None, etiqueta=rec["etiqueta"], calidad=cal["etiqueta"], rent_base=rb, rent_pesimista=rec.get("rent_pesimista"),
                 detalle=f"Calidad {cal['etiqueta'].lower()} · precio {juicio}" + (f" · dividendo {_p(div, False)}" if div else ""))


def _p(x, signo: bool = True) -> str:
    if not _ok(x):
        return "—"
    return (f"{x * 100:+.0f} %" if signo else f"{x * 100:.1f} %").replace(".", ",")


def _eval_cripto(r: dict) -> dict:
    f = r["cripto"]
    pan = cripto.panorama()
    s = cripto.historial(f["id"], f["simbolo"], f["precio"])
    a = cripto.completo(f, s, None, pan)
    rec, sol = a["recomendacion"], a["solidez"]
    if f["tipo"] in ("estable", "oro", "copia"):
        return _base(r, rol="nada", accion="pausar", motivo=rec["texto"].split(".")[0] + ".", nota=5.0, divisa="USD", etiqueta=rec["etiqueta"],
                     detalle=cripto.TIPOS[f["tipo"]][0], serie=s)
    rol = "reserva_digital" if f["id"] == "bitcoin" else "cripto"
    accion = {"verde": "seguir", "rojo": "reducir"}.get(rec["color"], "poco")
    if "MAL MOMENTO" in rec["etiqueta"]:
        accion = "seguir_sin_subir"
    nota = min(sol["puntos"] * 5.5, 55) - (10 if rec["color"] == "rojo" else 0)
    return _base(r, rol=rol, accion=accion, motivo=rec["texto"].split(". ")[0] + ".", nota=float(max(nota, 5)), divisa="USD",
                 etiqueta=rec["etiqueta"], peso_max=rec.get("peso"), serie=s,
                 detalle=f"Solidez {str(sol['puntos']).replace('.', ',')}/10 · {_p(f.get('desde_maximo'))} desde su máximo")


def _eval_materia(r: dict) -> dict:
    h = datos.historial(r["ticker"], "5y")
    s = h["Close"].dropna() if h is not None and len(h) else pd.Series(dtype=float)
    refugio = (r.get("materia") in ("Oro", "Plata")) or r["ticker"] in ("GC=F", "SI=F")
    detalle, accion, motivo, nota = "", "seguir_sin_subir", "", 50.0 if refugio else 32.0
    if len(s) > 220:
        mm = float(s.tail(200).mean())
        dist = float(s.iloc[-1] / mm - 1)
        detalle = f"{_p(dist)} respecto a su media de 200 días · {_p(float(s.iloc[-1] / s.iloc[-253] - 1)) if len(s) > 260 else '—'} en un año"
        if dist > 0.25:
            accion, motivo = "pausar", "Ha subido muchísimo en poco tiempo (más de un 25 % sobre su media): mal momento para seguir comprando."
        elif dist < -0.10 and not refugio:
            accion, motivo, nota = "poco", "En tendencia bajista: las materias primas pueden pasar años cayendo.", 22.0
    if not motivo:
        motivo = ("Protege la cartera en las caídas; con un 5-10 % del total es suficiente." if refugio else
                  "Las materias primas no dan rentas y son muy cíclicas: mejor como parte pequeña.")
    aviso = " Ojo: esto es un contrato de futuros; para invertir se usa un ETC o ETF que lo siga." if r["ticker"].endswith("=F") else ""
    return _base(r, rol="refugio" if refugio else "materia", accion=accion, motivo=motivo + aviso, nota=nota, divisa="USD", detalle=detalle,
                 sector="Materias primas")


@con_cache(24 * 3600)
def _dentro_del_fondo(ticker: str) -> dict:
    fd = yf.Ticker(ticker).funds_data
    top = fd.top_holdings
    dentro = {str(i).upper(): (str(f.get("Name") or i), float(f.get("Holding Percent") or 0)) for i, f in top.iterrows()} if top is not None else {}
    sect = {_SECTOR_FONDO.get(k, k): float(v) for k, v in (fd.sector_weightings or {}).items() if v}
    clases = {k: float(v) for k, v in (fd.asset_classes or {}).items() if v}
    comision = None
    try:
        comision = float(fd.fund_operations.loc["Annual Report Expense Ratio"].iloc[0])
    except Exception:  # noqa: BLE001
        pass
    return {"dentro": dentro, "sectores": sect, "clases": clases, "comision": comision if _ok(comision) else None}


def _eval_fondo(r: dict) -> dict:
    f = r.get("ficha") or {}
    try:
        x = _dentro_del_fondo(r["ticker"])
    except Exception:  # noqa: BLE001
        x = {"dentro": {}, "sectores": {}, "clases": {}, "comision": None}
    dentro, sect, clases = x["dentro"], x["sectores"], x["clases"]
    nombre = str(r.get("nombre") or "")
    if clases.get("bondPosition", 0) > 0.5 or clases.get("cashPosition", 0) > 0.5 or re.search(r"BOND|TREASURY|GOVT|AGGREGATE|MONEY|RENTA FIJA", nombre.upper()):
        rol, nota, motivo = "renta_fija", 45.0, "Da estabilidad. Tiene sentido si quieres que la cartera se mueva menos."
    elif re.search(r"GOLD|PHYSICAL|BULLION", nombre.upper()):
        rol, nota, motivo = "refugio", 50.0, "Sigue al oro: protege en las caídas; con un 5-10 % del total es suficiente."
    else:
        mayor = max((p for _, p in dentro.values()), default=0)
        sector_max = max(sect.values(), default=0)
        concentrado = mayor > 0.11 or sector_max > 0.42 or (not sect and not dentro)
        if concentrado and (sect or dentro):
            rol, nota = "tematico", 45.0
            motivo = ("Está muy cargado en " + (f"un sector ({max(sect, key=sect.get)}, {_p(sector_max, False)})" if sector_max > 0.42 else
                                              f"una sola empresa ({_p(mayor, False)})") + ": no lo cuentes como la base diversificada.")
        elif concentrado:
            rol, nota, motivo = "tematico", 45.0, "No he podido ver qué lleva dentro: lo trato como fondo concentrado por prudencia."
        else:
            rol, nota, motivo = "base", 85.0, "Muchas empresas de golpe y a bajo coste: es la pieza que más debería pesar."
    com = x["comision"]
    if com and com > 0.006:
        motivo += f" Cobra un {_p(com, False)} al año, que es caro para un fondo: hay equivalentes por menos del 0,3 %."
        nota -= 8
    det = ("Lleva dentro: " + ", ".join(f"{n.split(' ')[0]} {_p(p, False)}" for n, p in list(dentro.values())[:4])) if dentro else ""
    return _base(r, rol=rol, accion="seguir", motivo=motivo, nota=nota, divisa=(f.get("currency") or ""), sectores=sect or None, dentro=dentro or None,
                 comision=com, detalle=det + (f" · comisión {_p(com, False)}" if com else ""), sector="Fondos")


def _eval_manual(r: dict) -> dict:
    rol = r["rol"]
    nota = {"base": 85.0, "tematico": 45.0, "renta_fija": 45.0}.get(rol, 45.0)
    return _base(r, rol=rol, accion="seguir", motivo=ROLES[rol][1], nota=nota, detalle=f"Indicado a mano: {r['tipo_manual']}", sector="Fondos")


def evaluar(texto: str, tipo_manual: str = "") -> dict:
    """Reconoce el activo y lo analiza. Nunca lanza excepción: si algo falla, lo marca como «sin datos»."""
    try:
        r = resolver(texto, tipo_manual)
    except Exception:  # noqa: BLE001
        r = {"clase": "desconocido", "ticker": None, "nombre": texto}
    try:
        if r["clase"] == "accion":
            e = _eval_accion(r)
        elif r["clase"] == "cripto":
            e = _eval_cripto(r)
        elif r["clase"] == "cripto_yahoo":
            e = _base(r, clase="cripto", rol="cripto", accion="poco", motivo="Criptomoneda fuera de las 100 mayores: trátala como una apuesta.",
                      nota=15.0, divisa="USD")
        elif r["clase"] == "materia":
            e = _eval_materia(r)
        elif r["clase"] == "fondo":
            e = _eval_fondo(r)
        elif r["clase"] == "manual":
            e = _eval_manual(r)
        else:
            raise ValueError("desconocido")
    except Exception:  # noqa: BLE001
        e = _base(r, rol="desconocido", accion="seguir_sin_subir", nota=30.0,
                  motivo="No he encontrado datos. Prueba con su ticker de Yahoo o indica el tipo a mano en la tercera columna.")
    e["escrito"] = texto
    return e


def evaluar_todos(plan: pd.DataFrame, progreso=None) -> list[dict]:
    filas = list(plan.itertuples(index=False))
    salida = [None] * len(filas)
    with ThreadPoolExecutor(max_workers=4) as ex:
        futuros = {ex.submit(evaluar, f.activo, getattr(f, "tipo", "") or ""): i for i, f in enumerate(filas)}
        hechos = 0
        for fut, i in futuros.items():
            salida[i] = fut.result()
            salida[i]["euros"] = float(filas[i].euros)
            salida[i]["tengo"] = float(getattr(filas[i], "tengo", 0) or 0)
            hechos += 1
            if progreso:
                progreso(hechos / len(filas), f"Analizando {hechos} de {len(filas)}…")
    return salida


# ----------------------------------------------------------------------------- mirada de conjunto
def peso_eur(a: dict) -> float:
    """Lo que cuenta cada activo en la cartera: lo que ya tienes más un año de aportaciones."""
    return float(a.get("tengo") or 0) + 12 * float(a.get("euros") or 0)


def sectores_reales(act: list[dict]) -> pd.Series:
    """Peso por sector mirando también dentro de los fondos."""
    total = sum(peso_eur(a) for a in act) or 1
    s: dict[str, float] = {}
    for a in act:
        if a.get("sectores"):
            suma = sum(a["sectores"].values()) or 1
            for k, v in a["sectores"].items():
                s[k] = s.get(k, 0) + peso_eur(a) * v / suma
        else:
            k = a.get("sector") or {"cripto": "Criptomonedas", "materia": "Materias primas"}.get(a["clase"], "Otros")
            s[k] = s.get(k, 0) + peso_eur(a)
    return (pd.Series(s) / total).sort_values(ascending=False)


def correlaciones(act: list[dict]) -> list[tuple[str, str, float]]:
    """Parejas de activos (no fondos) que se han movido casi igual en el último año."""
    cand = [a for a in act if a["clase"] in ("accion", "materia") and a.get("ticker")]
    if len(cand) < 2:
        return []
    try:
        cs = datos.cierres(tuple(a["ticker"] for a in cand), "1y")
    except Exception:  # noqa: BLE001
        return []
    ret = np.log(cs.ffill()).diff().dropna(how="all")
    if len(ret) < 120:
        return []
    c = ret.corr()
    nombre = {a["ticker"]: a["nombre"] for a in cand}
    pares = []
    for i, x in enumerate(c.columns):
        for y in c.columns[i + 1:]:
            if _ok(c.loc[x, y]) and c.loc[x, y] >= 0.75:
                pares.append((nombre.get(x, x), nombre.get(y, y), float(c.loc[x, y])))
    return sorted(pares, key=lambda p: -p[2])[:4]


def solapes(act: list[dict]) -> list[str]:
    """Acciones que compras sueltas y que además ya van dentro de alguno de tus fondos."""
    salida = []
    for fondo in [a for a in act if a.get("dentro")]:
        for acc in [a for a in act if a["clase"] == "accion" and a.get("ticker")]:
            raiz = acc["ticker"].split(".")[0].upper()
            for simbolo, (nombre, peso) in fondo["dentro"].items():
                if simbolo.split(".")[0] == raiz or acc["nombre"].split(" ")[0].lower() == nombre.split(" ")[0].lower():
                    salida.append(f"**{acc['nombre']}** ya es el {_p(peso, False)} de **{fondo['nombre']}**: la estás comprando dos veces.")
                    break
    return salida


def _cfg(perfil: str) -> dict:
    return PERFILES.get(perfil, PERFILES["Medio"])


def flaquezas(act: list[dict], perfil: str = "Medio") -> list[dict]:
    """Lista de {grave: 2|1|0, titulo, texto}. 2 = importante, 1 = a vigilar, 0 = nota.

    Juzga la cartera tal como es (no penaliza que no haya un fondo indexado) y según el perfil de riesgo elegido.
    """
    cfg = _cfg(perfil)
    total = sum(peso_eur(a) for a in act) or 1
    n = len(act)
    peso = lambda cond: sum(peso_eur(a) for a in act if cond(a)) / total  # noqa: E731
    f = []
    espec = peso(lambda a: a["rol"] in ESPECULATIVOS)
    cri = peso(lambda a: a["clase"] == "cripto")
    defen = peso(lambda a: a["rol"] in DEFENSIVOS)
    crece = peso(lambda a: a["rol"] in CRECIMIENTO)
    sueltas = [a for a in act if a["clase"] == "accion"]
    tiene_fondo = any(a["rol"] in ("base", "tematico") for a in act)
    frenadas = [a for a in act if a["accion"] in ("pausar", "reducir") and a["euros"] > 0]
    mensual = sum(a["euros"] for a in act) or 1
    if frenadas:
        eur = sum(a["euros"] for a in frenadas)
        f.append({"grave": 2 if eur / mensual > 0.25 else 1, "titulo": f"{eur:.0f} € al mes van a activos que hoy no conviene comprar",
                  "texto": "Son " + ", ".join(a["nombre"] for a in frenadas) + ". No hace falta vender: basta con dejar de aportar ahí por ahora."})
    vender = [a for a in act if a["accion"] == "reducir" and a.get("tengo", 0) > 0]
    if vender:
        f.append({"grave": 2, "titulo": "Posiciones que plantearse reducir",
                  "texto": ", ".join(f"{a['nombre']} ({a['tengo']:.0f} €)" for a in vender) + ": el negocio da señales de deterioro. "
                           "Antes de vender, mira su análisis completo y ten en cuenta los impuestos."})
    if espec > cfg["espec"]:
        f.append({"grave": 2, "titulo": f"Demasiado peso especulativo para un perfil {perfil.lower()}: {_p(espec, False)}",
                  "texto": f"Entre empresas que aún no ganan dinero de verdad y criptomonedas. Para tu perfil, la referencia es no pasar del {_p(cfg['espec'], False)}: "
                           "si salen mal, se llevan por delante lo que ganes con el resto."})
    if cri > cfg["cripto"]:
        f.append({"grave": 2 if cri > 2 * cfg["cripto"] else 1, "titulo": f"Criptomonedas: {_p(cri, False)} de la cartera",
                  "texto": f"Pueden caer un 70-80 % y tardar años en volver. Para un perfil {perfil.lower()}, la referencia es menos del {_p(cfg['cripto'], False)}."})
    if not tiene_fondo and len(sueltas) + sum(1 for a in act if a["clase"] in ("cripto", "materia")) <= 4 and n >= 1:
        f.append({"grave": 1, "titulo": f"Pocas piezas: {n} {'activo' if n == 1 else 'activos'}",
                  "texto": "Con tan pocos, lo que le pase a uno solo se nota mucho. A partir de 8-10 empresas de sectores distintos el riesgo de "
                           "una sola baja bastante."})
    if n >= 4:
        for a in act:
            w = peso_eur(a) / total
            if a["rol"] not in ("base", "renta_fija") and w > cfg["unico"]:
                f.append({"grave": 2 if a["rol"] in ESPECULATIVOS else 1, "titulo": f"{a['nombre']} es el {_p(w, False)} de la cartera",
                          "texto": "Es mucho para un solo activo: si le va mal, arrastra todo lo demás. Asumir riesgo no es lo mismo que jugárselo a una carta."})
    sec = sectores_reales(act)
    sec = sec[~sec.index.isin(["Fondos", "Otros"])]
    if len(sec) and sec.iloc[0] > cfg["sector"] and n >= 3:
        f.append({"grave": 1, "titulo": f"Mucha concentración en {sec.index[0]}: {_p(float(sec.iloc[0]), False)}",
                  "texto": "Contando también lo que llevan dentro tus fondos. Cuando ese sector cae, cae casi todo a la vez."})
    if perfil == "Bajo" and defen < 0.50 and n >= 2:
        f.append({"grave": 2 if defen < 0.25 else 1, "titulo": f"Poco defensivo para un perfil bajo: {_p(defen, False)}",
                  "texto": "Dividendos sostenibles, negocios maduros, oro o renta fija deberían ser al menos la mitad si no quieres sustos."})
    elif perfil == "Medio" and defen == 0 and n >= 2:
        f.append({"grave": 1, "titulo": "No hay nada defensivo",
                  "texto": "Todo lo que tienes sube y baja con el apetito por el riesgo. Algo de dividendos, negocios maduros u oro amortigua las caídas."})
    if perfil == "Alto" and crece < 0.30 and n >= 2:
        f.append({"grave": 0, "titulo": f"Poco crecimiento para un perfil alto: {_p(crece, False)}",
                  "texto": "La cartera es más tranquila de lo que dices querer. No es un problema, pero tienes margen para más crecimiento."})
    for texto in solapes(act):
        f.append({"grave": 0, "titulo": "Compra duplicada", "texto": texto})
    for x, y, c in correlaciones(act):
        f.append({"grave": 0, "titulo": f"{x} y {y} se mueven casi igual",
                  "texto": f"Correlación de {c:.2f}".replace(".", ",") + " en el último año: tener las dos diversifica poco."})
    usd = peso(lambda a: a.get("divisa") == "USD")
    if usd > 0.75 and n >= 3:
        f.append({"grave": 0, "titulo": f"El {_p(usd, False)} está en dólares",
                  "texto": "Si el dólar baja frente al euro, pierdes aunque las acciones suban. No es grave a largo plazo, pero conviene saberlo."})
    for a in [a for a in act if a.get("comision") and a["comision"] > 0.006]:
        f.append({"grave": 0, "titulo": f"{a['nombre']} es caro", "texto": f"Cobra un {_p(a['comision'], False)} al año."})
    sin = [a for a in act if a["rol"] == "desconocido"]
    if sin:
        f.append({"grave": 0, "titulo": "Activos sin datos", "texto": ", ".join(a["escrito"] for a in sin) + ": no entran en el análisis de conjunto."})
    return sorted(f, key=lambda x: -x["grave"])


def nota_global(act: list[dict], fl: list[dict]) -> dict:
    graves = sum(1 for x in fl if x["grave"] == 2)
    medias = sum(1 for x in fl if x["grave"] == 1)
    if graves >= 2:
        return {"etiqueta": "🔴 ARRIESGADA", "color": "rojo", "texto": "Tiene varios puntos débiles importantes. Revisa primero los marcados en rojo."}
    if graves == 1 or medias >= 2:
        return {"etiqueta": "🟡 MEJORABLE", "color": "amarillo", "texto": "La idea general vale, pero hay cosas que conviene corregir."}
    return {"etiqueta": "🟢 EQUILIBRADA", "color": "verde", "texto": "Sin puntos débiles importantes. Los ajustes que propongo son de detalle."}


def resumen(act: list[dict], perfil: str = "Medio") -> dict:
    """Cifras de conjunto, para comparar dos versiones de la cartera."""
    total = sum(peso_eur(a) for a in act) or 1
    fl = flaquezas(act, perfil)
    sec = sectores_reales(act)
    sec = sec[~sec.index.isin(["Fondos", "Otros"])]
    return {"nota": nota_global(act, fl), "flaquezas": fl,
            "especulativo": sum(peso_eur(a) for a in act if a["rol"] in ESPECULATIVOS) / total,
            "defensivo": sum(peso_eur(a) for a in act if a["rol"] in DEFENSIVOS) / total,
            "sector": (sec.index[0], float(sec.iloc[0])) if len(sec) else ("—", 0.0), "dividendo": renta_dividendos(act)}


# ----------------------------------------------------------------------------- reparto sugerido
def _tope(a: dict, n: int, perfil: str = "Medio") -> float:
    """Peso máximo razonable de un activo en la cartera, según lo que es y el perfil de riesgo."""
    cfg = _cfg(perfil)
    if a["rol"] == "base":
        return 1.0
    if a["rol"] in cfg["topes"]:
        return cfg["topes"][a["rol"]]
    return max(cfg["unico"] - 0.10, min(0.60, 1.6 / max(n, 1)))  # con pocos activos no tiene sentido exigir pesos pequeños


def reparto(act: list[dict], perfil: str = "Medio") -> tuple[list[dict], float]:
    """Propone cómo repartir el MISMO presupuesto mensual. Devuelve (activos con «sugerido», euros sin asignar).

    Tiene en cuenta lo que ya tienes: si un activo ya pesa mucho en la cartera, recibe menos aportación aunque sea bueno.
    Reglas: lo que conviene pausar baja a cero; solo sube lo que el análisis recomienda seguir comprando; la base
    diversificada nunca baja; lo especulativo tiene tope según tu perfil; y se cambia poco a poco.
    """
    cfg = _cfg(perfil)
    total = sum(a["euros"] for a in act)
    n = len(act)
    if n == 0:
        return [], 0.0
    if total <= 0:
        return [{**a, "sugerido": 0.0, "cambio": 0.0, "porque": a["motivo"]} for a in act], 0.0
    paso = 5 if total >= 100 else 1
    actual = np.array([a["euros"] for a in act], dtype=float)
    tengo = np.array([a.get("tengo") or 0 for a in act], dtype=float)
    cartera = tengo.sum() + 12 * total  # tamaño de la cartera dentro de un año
    fuera = np.array([a["accion"] in ("pausar", "reducir") or a["rol"] == "nada" for a in act])
    fijo = np.array([a["rol"] == "desconocido" for a in act])
    vivo = ~fuera & ~fijo
    sugerido = np.where(fuera, 0.0, actual)
    sube = np.array([a["accion"] == "seguir" for a in act]) & vivo
    if not sube.any():  # si nada está claramente para comprar, lo «razonable» puede recibir (pero nunca lo especulativo)
        sube = np.array([a["accion"] == "seguir_sin_subir" and a["rol"] not in ESPECULATIVOS for a in act]) & vivo
    fuerza = np.array([max(a["nota"] + cfg["extra"].get(a["rol"], 0), 5) ** 1.5 for a in act])
    tope_w = np.array([_tope(a, n, perfil) for a in act])
    # tope de aportación mensual: lo que cabe hasta el peso máximo, descontando lo que ya tienes
    tope = np.clip((tope_w * cartera - tengo) / 12, 0, None)
    if vivo.any():
        w = np.where(vivo, fuerza, 0.0)
        w = np.minimum(w / w.sum(), tope_w)
        for grupo, maximo in ((lambda a: a["clase"] == "cripto", cfg["cripto"]), (lambda a: a["rol"] in ESPECULATIVOS, cfg["espec"])):
            idx = np.array([grupo(a) for a in act]) & vivo
            if idx.any() and (~idx & vivo).any() and w[idx].sum() > maximo:
                w[idx] *= maximo / w[idx].sum()
        # aportación que acerca cada activo a su peso objetivo en la cartera completa
        objetivo = np.clip((w * cartera - tengo) / 12, 0, None)
        disponible = actual[vivo | fuera].sum()
        if objetivo.sum() > disponible > 0:
            objetivo *= disponible / objetivo.sum()
        paso_a = actual + 0.6 * (objetivo - actual)  # freno: solo se recorre parte del camino
        for i, a in enumerate(act):
            if not vivo[i]:
                continue
            v = paso_a[i]
            if not sube[i]:
                v = min(v, actual[i])
            if a["rol"] == "base":
                v = max(v, actual[i])
            if abs(v - actual[i]) < max(paso, 0.12 * actual[i]):  # cambios pequeños no merecen la pena
                v = actual[i]
            sugerido[i] = max(v, 0.0)
    falta = total - sugerido.sum()
    if falta > 0 and sube.any():  # dinero liberado: a lo que conviene comprar, hasta su tope
        for _ in range(8):
            hueco = np.where(sube, np.clip(tope - sugerido, 0, None), 0.0)
            if falta < 1e-6 or hueco.sum() < 1e-6:
                break
            pesos = np.where(hueco > 0, fuerza, 0.0)
            extra = np.minimum(falta * pesos / pesos.sum(), hueco)
            sugerido += extra
            falta -= extra.sum()
    elif falta < 0:  # se ha propuesto subir más de lo que se libera: se recortan las subidas
        subida = np.clip(sugerido - actual, 0, None)
        if subida.sum() > 0:
            sugerido -= subida * min(1.0, -falta / subida.sum())
    sugerido = np.round(np.clip(sugerido, 0, None) / paso) * paso
    resto = total - sugerido.sum()
    if sube.any() and abs(resto) >= 0.5:  # el redondeo va al mejor activo que puede recibir
        mejor = int(np.argmax(np.where(sube, fuerza, -1)))
        if 0 <= sugerido[mejor] + resto <= tope[mejor] + paso:
            sugerido[mejor] += resto
            resto = 0.0
    salida = []
    for i, (a, s_) in enumerate(zip(act, sugerido)):
        cambio = s_ - a["euros"]
        ya = tengo[i] / cartera if cartera else 0
        if a["accion"] in ("pausar", "reducir") or a["rol"] == "nada":
            porque = a["motivo"]
        elif cambio > 0.5:
            porque = ("Es la base: conviene que pese más." if a["rol"] == "base" else f"De lo mejor que tienes ahora mismo. {a['motivo']}")
        elif cambio < -0.5:
            if a["rol"] in ESPECULATIVOS:
                porque = ("Especulativo" + (f" y ya es el {_p(ya, False)} de tu cartera" if tengo[i] > 0 else "")
                          + f": para un perfil {perfil.lower()}, mejor aportar menos. " + a["motivo"])
            elif tengo[i] > 0 and (tengo[i] + 12 * a["euros"]) / cartera > tope_w[i]:
                porque = f"Ya pesa mucho con lo que tienes invertido ({_p(ya, False)} de la cartera): mejor aportar menos aquí. " + a["motivo"]
            elif a["euros"] > tope[i]:
                porque = "Pesa demasiado para un solo activo. " + a["motivo"]
            else:
                porque = "Hay piezas mejores en tu propia lista. " + a["motivo"]
        else:
            porque = "Bien como está. " + a["motivo"]
        salida.append({**a, "sugerido": float(s_), "cambio": float(cambio), "porque": porque})
    return salida, float(max(resto, 0.0))


# ----------------------------------------------------------------------------- qué le falta, qué le sobra, fondo aparte
def huecos(act: list[dict], perfil: str = "Medio") -> list[dict]:
    """Qué tipo de pieza le falta a la cartera, según el perfil. No incluye fondos: eso va en `fondo_complementario`."""
    total = sum(peso_eur(a) for a in act) or 1
    vivos = [a for a in act if a["accion"] != "reducir"]
    peso = lambda roles: sum(peso_eur(a) for a in vivos if a["rol"] in roles) / total  # noqa: E731
    h = []
    div, est, rap, ref = peso(("dividendos", "valor")), peso(("estable", "base")), peso(("rapido", "explosivo")), peso(("refugio", "renta_fija"))
    if div < (0.25 if perfil == "Bajo" else 0.01 if perfil == "Medio" else -1):
        h.append({"rol": "dividendos", "titulo": "Empresas que paguen dividendos sostenibles",
                  "texto": "Negocios maduros que reparten parte de lo que ganan: dan renta y caen menos en las crisis."
                           + (" Para un perfil bajo deberían ser una parte importante." if perfil == "Bajo" else ""), "buscar": True})
    if est + peso(("rapido",)) < 0.01 or (perfil == "Bajo" and est < 0.15):
        h.append({"rol": "estable", "titulo": "Crecimiento estable de calidad",
                  "texto": "Negocios que crecen cada año sin depender de una moda: el motor a largo plazo de cualquier cartera.", "buscar": True})
    if perfil == "Alto" and rap < 0.25:
        h.append({"rol": "rapido", "titulo": "Más crecimiento rápido",
                  "texto": "Para un perfil alto tienes poco en empresas que crecen deprisa y ya ganan dinero, que es donde está el recorrido.",
                  "buscar": True})
    if ref < 0.01 and len(act) >= 4 and perfil != "Alto":
        h.append({"rol": "refugio", "titulo": "Un amortiguador (oro)",
                  "texto": ("Recomendable" if perfil == "Bajo" else "Opcional") + ": un 5-10 % en oro hace que la cartera caiga menos cuando todo "
                           "baja. Escribe «oro» en «¿Y si…?» para ver cómo cambia.", "buscar": False})
    return h


def sobras(act: list[dict], perfil: str = "Medio") -> list[str]:
    """Qué le sobra a la cartera: piezas repetidas, que no aportan o que exceden lo razonable para el perfil."""
    cfg = _cfg(perfil)
    total = sum(peso_eur(a) for a in act) or 1
    s = []
    for a in act:
        if a["rol"] == "nada":
            s.append(f"**{a['nombre']}** no es una inversión que pueda crecer: no aporta nada a la cartera.")
        elif a["rol"] == "dividendo_dudoso":
            s.append(f"**{a['nombre']}**: su dividendo alto parece poco sostenible. No cuenta como pieza de dividendos fiable.")
    por_rol: dict[str, list] = {}
    for a in act:
        por_rol.setdefault(a["rol"], []).append(a)
    for rol in ("explosivo", "cripto"):
        lista = por_rol.get(rol, [])
        if len(lista) >= 3:
            s.append(f"Tienes {len(lista)} piezas de «{ROLES[rol][0]}» ({', '.join(a['nombre'] for a in lista)}): repartir entre muchas apuestas "
                     "del mismo tipo no las hace más seguras. Quédate con las dos que más te convenzan.")
    exceso = sum(peso_eur(a) for a in act if a["rol"] in ESPECULATIVOS) / total - cfg["espec"]
    if exceso > 0.02:
        s.append(f"Sobra en torno a un {_p(exceso, False)} de peso especulativo respecto a lo razonable para un perfil {perfil.lower()}.")
    for x, y, _c in correlaciones(act)[:2]:
        s.append(f"**{x}** y **{y}** hacen casi lo mismo en tu cartera: con una bastaría.")
    return s


def fondo_complementario(act: list[dict], perfil: str = "Medio") -> dict:
    """Apartado independiente: si quisieras añadir un fondo indexado, cuál encajaría con lo que ya tienes y cuál no."""
    total = sum(peso_eur(a) for a in act) or 1
    sec = sectores_reales(act)
    sec = sec[~sec.index.isin(["Fondos", "Otros"])]
    usd = sum(peso_eur(a) for a in act if a.get("divisa") == "USD") / total
    eur = sum(peso_eur(a) for a in act if a.get("divisa") == "EUR") / total
    tec = float(sec.get("Tecnología", 0) + sec.get("Comunicaciones", 0))
    div = sum(peso_eur(a) for a in act if a["rol"] in ("dividendos", "valor")) / total
    fondos = [a for a in act if a["rol"] in ("base", "tematico", "renta_fija")]
    sueltas = [a for a in act if a["clase"] == "accion"]
    encajan, evitar = [], []
    if tec > 0.40:
        evitar.append(f"Fondos del Nasdaq o tecnológicos: ya tienes un {_p(tec, False)} en tecnología y te lo duplicarían.")
        encajan.append("Uno que pese poco en tecnología: de dividendos, de «valor» o de pequeñas empresas (índices tipo MSCI World Value o "
                       "MSCI World Small Cap).")
    if usd > 0.65:
        evitar.append(f"Fondos del S&P 500: ya tienes un {_p(usd, False)} en dólares y en empresas de EE. UU.")
        encajan.append("Uno de Europa o de mercados emergentes (índices tipo MSCI Europe o MSCI Emerging Markets), para no depender solo de EE. UU.")
    elif eur > 0.65:
        encajan.append("Uno mundial o de EE. UU. (índices tipo MSCI World o S&P 500): casi todo lo tuyo está en Europa.")
    if div < 0.10 and perfil != "Alto":
        encajan.append("Uno de dividendos (índices de «dividend aristocrats» o «high dividend»): cubriría la parte de rentas que no tienes.")
    if perfil == "Bajo":
        encajan.append("Uno de renta fija a corto plazo o monetario, como colchón: da poco pero apenas se mueve.")
    if len(sueltas) <= 6 and not fondos:
        encajan.append("Uno mundial amplio (índices tipo MSCI World o FTSE All-World): te da miles de empresas de golpe y reduce el efecto de "
                       "que una de las tuyas salga mal.")
    if not encajan:
        encajan.append("Uno mundial amplio (índices tipo MSCI World o FTSE All-World) es el comodín: complementa casi cualquier cartera.")
    ya = ""
    if fondos:
        ya = "Ya tienes " + ", ".join(a["nombre"] for a in fondos) + ". "
        dup = solapes(act)
        ya += (f"Ojo, hay {len(dup)} {'compra duplicada' if len(dup) == 1 else 'compras duplicadas'} con tus acciones (ver puntos débiles)." if dup else
               "No veo duplicidades importantes con tus acciones.")
    requisitos = ["Comisión total por debajo del 0,3 % al año.", "De acumulación (reinvierte los dividendos solo), para no pagar impuestos cada año por ellos.",
                  "Que siga un índice amplio y conocido, con cientos de empresas.",
                  "Que su mayor posición no sea una acción que ya tienes en cantidad."]
    return {"ya": ya, "encajan": encajan[:4], "evitar": evitar, "requisitos": requisitos}


def candidatas(rol: str, ya: set[str], cuantas: int = 3) -> list[dict]:
    """Empresas conocidas que HOY pasan el análisis del programa y tienen el perfil que falta."""
    lista = [t for t in CANDIDATAS.get(rol, []) if t.upper() not in ya]
    with ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(lambda t: evaluar(t), lista))
    validos = {"dividendos": ("dividendos", "valor"), "estable": ("estable", "rapido"), "rapido": ("rapido", "estable")}.get(rol, (rol,))
    buenas = [e for e in res if e["rol"] in validos and e["accion"] in ("seguir", "seguir_sin_subir")]
    return sorted(buenas, key=lambda e: (e["accion"] != "seguir", -e["nota"]))[:cuantas]


def proyeccion(act: list[dict], clave: str = "euros") -> pd.DataFrame:
    """Lo que podría valer (lo que ya tienes más las aportaciones) a 5, 10 y 20 años. Supuestos prudentes, no predicciones."""
    inicial = sum(a.get("tengo") or 0 for a in act)
    filas = []
    for anios in (5, 10, 20):
        meses = anios * 12
        fila = {"Años": anios, "Puesto de tu bolsillo": inicial + sum(a[clave] for a in act) * meses}
        for i, nombre in enumerate(("Si va mal", "Normal", "Si va bien")):
            v = 0.0
            for a in act:
                r = SUPUESTOS.get(a["rol"], SUPUESTOS["desconocido"])[i]
                rm = (1 + r) ** (1 / 12) - 1
                v += (a.get("tengo") or 0) * (1 + r) ** anios
                v += a[clave] * (meses if abs(rm) < 1e-9 else ((1 + rm) ** meses - 1) / rm)
            fila[nombre] = v
        filas.append(fila)
    return pd.DataFrame(filas)


def renta_dividendos(act: list[dict]) -> float:
    """Rentabilidad por dividendo media de la cartera (ponderada por lo que pesa cada activo)."""
    total = sum(peso_eur(a) for a in act) or 1
    return sum(peso_eur(a) * (a.get("dividendo") or 0) for a in act) / total


def accion_texto(a: dict) -> str:
    return {"seguir": "✅ Seguir acumulando", "seguir_sin_subir": "🆗 Seguir, sin aumentar", "poco": "⚠️ Solo con poco",
            "pausar": "⏸️ Pausar (sin vender)", "reducir": "🔻 Dejar de comprar y plantearse reducir"}[a["accion"]]


def texto_para_ia(act: list[dict], fl: list[dict], rep: list[dict], perfil: str = "Medio") -> str:
    L = [f"Analiza esta cartera y su plan de aportaciones mensuales. Mi perfil de riesgo es {perfil.lower()}. Datos recogidos por Radar Inversor "
         "(reglas automáticas, sin IA). Dime si estás de acuerdo con el reparto sugerido, qué cambiarías y por qué.", "", "## Activos"]
    for r in rep:
        L.append(f"- {r['nombre']} ({r.get('ticker') or r['escrito']}): ya tengo {r.get('tengo') or 0:.0f} €; aporto {r['euros']:.0f} €/mes → "
                 f"sugerido {r['sugerido']:.0f} €. Perfil: {ROLES[r['rol']][0]}. {r.get('detalle') or ''} Motivo: {r['motivo']}")
    L += ["", "## Puntos débiles detectados"] + [f"- {x['titulo']}: {x['texto']}" for x in fl]
    return "\n".join(L)
