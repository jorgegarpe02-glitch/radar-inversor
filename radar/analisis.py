"""Análisis completo de una acción, generado con reglas a partir de los datos (sin IA).

Sigue siempre el mismo orden: métricas con contexto → calidad del negocio → valoración por perfil (crecimiento,
dividendos, DCA) → catalizadores → técnico → tres escenarios de precio → riesgos → veredicto → recomendación →
resumen en lenguaje llano.

Principios (los mismos que pediría a un analista prudente):
- Primero no perder: se da tanto peso a lo que puede salir mal como a lo que puede salir bien.
- Una empresa excelente puede ser mala compra hoy, y una barata puede ser una trampa: calidad y precio se puntúan aparte.
- Nada de precisión falsa: los precios objetivo son rangos y cada uno dice con qué supuestos se ha calculado.

Todo son funciones puras sobre diccionarios: se pueden probar sin conexión.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

AVISO_LEGAL = "Este análisis es informativo y no constituye asesoramiento financiero personalizado."

# sector de Yahoo → referencia orientativa de largo plazo (PER, EV/EBITDA, margen operativo, ¿cíclico?, sensibilidades)
SECTORES = {
    "Technology": (27, 18, 0.22, "medio", "gasto de las empresas en tecnología e IA, tipos de interés (pesan en las valoraciones altas) y restricciones a la exportación de chips"),
    "Communication Services": (20, 11, 0.20, "medio", "inversión publicitaria, regulación de las grandes plataformas y competencia en telecomunicaciones"),
    "Consumer Cyclical": (20, 12, 0.10, "alto", "confianza del consumidor, empleo, tipos de interés y aranceles"),
    "Consumer Defensive": (21, 14, 0.12, "bajo", "inflación de costes y capacidad de subir precios sin perder volumen"),
    "Healthcare": (21, 14, 0.18, "bajo", "vencimiento de patentes, precios regulados de los medicamentos y resultados de ensayos clínicos"),
    "Financial Services": (12, None, 0.30, "alto", "tipos de interés (margen de intereses), morosidad y exigencias de capital"),
    "Industrials": (21, 13, 0.12, "medio", "ciclo de inversión industrial, presupuestos de defensa e infraestructuras y coste de materias primas"),
    "Energy": (11, 6, 0.12, "alto", "precio del petróleo y del gas, márgenes de refino y decisiones de la OPEP"),
    "Basic Materials": (15, 8, 0.14, "alto", "precios de las materias primas, demanda de China y coste de la energía"),
    "Utilities": (17, 10, 0.18, "bajo", "tipos de interés (son negocios con mucha deuda), regulación de tarifas y precio de la electricidad"),
    "Real Estate": (30, 18, 0.30, "medio", "tipos de interés, ocupación y valor de los inmuebles"),
}
SECTOR_ES = {"Technology": "Tecnología", "Communication Services": "Comunicaciones", "Consumer Cyclical": "Consumo cíclico",
             "Consumer Defensive": "Consumo defensivo", "Healthcare": "Salud", "Financial Services": "Finanzas",
             "Industrials": "Industria", "Energy": "Energía", "Basic Materials": "Materiales", "Utilities": "Servicios públicos",
             "Real Estate": "Inmobiliario"}
# palabras del sector de la base propia (en español) → sector de Yahoo, por si Yahoo no da el sector ese día
_PISTAS_SECTOR = [
    (("semiconduct", "chip", "software", "nube", "servidor", "electrónica", "ordenador", "tecnolog", "inteligencia artificial", "redes", "óptica", "conector"), "Technology"),
    (("internet", "telecomunic", "entretenimiento", "videojuego", "streaming", "torres"), "Communication Services"),
    (("automoci", "moda", "comercio electrónico", "aerolínea", "viajes", "neumático", "movilidad", "piscina"), "Consumer Cyclical"),
    (("distribución", "tabaco", "aliment"), "Consumer Defensive"),
    (("farmac", "biotecn", "hemoderiv", "laboratorio", "salud", "inyectable", "médica"), "Healthcare"),
    (("banca", "pagos", "seguros", "gestión de activos", "inversión"), "Financial Services"),
    (("defensa", "aeroespacial", "motores", "industria", "ferroviario", "construcción", "infraestructura", "maquinaria", "naval", "aviación", "aeropuerto", "ingeniería", "equipos eléctricos", "cables", "transporte", "almacenes"), "Industrials"),
    (("petróleo", "gas", "uranio", "servicios petroleros"), "Energy"),
    (("minería", "acero", "litio", "materiales", "vidrio"), "Basic Materials"),
    (("eléctricas", "renovables", "red eléctrica", "red de gas", "aerogenerador", "paneles", "equipos energéticos"), "Utilities"),
    (("centros de datos (alquiler)", "inmobili"), "Real Estate"),
]


def sector_yahoo(sector: str | None, sector_base: str | None = None) -> str | None:
    if sector in SECTORES:
        return sector
    texto = (sector_base or sector or "").lower()
    for pistas, s in _PISTAS_SECTOR:
        if any(p in texto for p in pistas):
            return s
    return None


# ----------------------------------------------------------------------------- utilidades
def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))


def _pct(x, dec=0, signo=False) -> str:
    if not _ok(x):
        return "—"
    return f"{x * 100:{'+' if signo else ''}.{dec}f} %".replace(".", ",")


def _n(x, dec=1) -> str:
    if not _ok(x):
        return "—"
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _media(s: pd.Series, n: int = 4):
    s = s.dropna().tail(n)
    return float(s.mean()) if len(s) else None


def redondo(x: float) -> float:
    """Redondea un precio a una cifra «de rango», no de céntimo."""
    if not _ok(x) or x <= 0:
        return x
    paso = 10 ** (math.floor(math.log10(x)) - 1)
    paso = paso * (5 if x / paso > 50 else 1) / (1 if x / paso > 20 else 2)
    return round(x / paso) * paso


# ----------------------------------------------------------------------------- 2. métricas con contexto
def _juicio(valor, ref, menor_es_mejor=True, tolerancia=0.15):
    """'mejor' / 'similar' / 'peor' respecto a una referencia."""
    if not _ok(valor) or not _ok(ref) or ref == 0:
        return None
    d = valor / ref - 1
    if abs(d) <= tolerancia:
        return "similar"
    return "mejor" if (d < 0) == menor_es_mejor else "peor"


def tarjetas(m: dict, comparables: list[dict], sector: str | None, per_etf: float | None = None) -> list[dict]:
    """Métricas clave con triple contexto: su propia historia, competidores y sector."""
    ref = SECTORES.get(sector or "")

    def mediana(clave):
        vals = [c[clave] for c in comparables if _ok(c.get(clave)) and c[clave] > 0]
        return float(np.median(vals)) if len(vals) >= 2 else (vals[0] if vals else None)

    hist_per, hist_ev = m.get("per_hist") or {}, m.get("ev_ebitda_hist") or {}
    per_sector = per_etf or (ref[0] if ref else None)
    filas = [
        {"clave": "per", "nombre": "PER (últimos 12 meses)", "valor": m.get("per"), "fmt": "x", "historia": hist_per.get("mediana"),
         "rango": (hist_per.get("min"), hist_per.get("max")), "competidores": mediana("per"), "sector": per_sector, "menor_mejor": True,
         "que_es": "Años de beneficio actual que pagas al comprar. Cuanto más bajo, más barata (o más dudas hay sobre su futuro)."},
        {"clave": "per_fwd", "nombre": "PER previsto", "valor": m.get("per_fwd"), "fmt": "x", "historia": None, "rango": None,
         "competidores": mediana("per_fwd"), "sector": per_sector, "menor_mejor": True,
         "que_es": "Igual que el PER pero con el beneficio que esperan los analistas para el próximo ejercicio. Es el mejor para comparar con el sector."},
        {"clave": "peg", "nombre": "PEG", "valor": m.get("peg"), "fmt": "n2", "historia": None, "rango": None, "competidores": None,
         "sector": 1.5, "menor_mejor": True,
         "que_es": "PER dividido entre el crecimiento esperado. Por debajo de 1, el crecimiento sale barato; por encima de 2, caro."},
        {"clave": "ev_ebitda", "nombre": "EV/EBITDA", "valor": m.get("ev_ebitda"), "fmt": "x", "historia": hist_ev.get("mediana"),
         "rango": (hist_ev.get("min"), hist_ev.get("max")), "competidores": mediana("ev_ebitda"), "sector": ref[1] if ref else None,
         "menor_mejor": True, "que_es": "Valor de toda la empresa (con su deuda) entre su beneficio bruto de explotación. Difícil de maquillar."},
        {"clave": "p_fcf", "nombre": "Precio / flujo de caja libre", "valor": m.get("p_fcf"), "fmt": "x", "historia": None, "rango": None,
         "competidores": mediana("p_fcf"), "sector": None, "menor_mejor": True,
         "que_es": "Lo que pagas por cada euro de caja que le queda a la empresa después de invertir. El más difícil de manipular."},
        {"clave": "roe", "nombre": "ROE", "valor": m.get("roe"), "fmt": "%", "historia": _media(m["anual"]["roe"]) if _tiene(m, "roe") else None,
         "rango": None, "competidores": mediana("roe"), "sector": 0.12, "menor_mejor": False,
         "que_es": "Beneficio que saca por cada euro de los accionistas. Con mucha deuda o muchas recompras sale inflado."},
        {"clave": "roic", "nombre": "ROIC", "valor": m.get("roic"), "fmt": "%", "historia": _media(m["anual"]["roic"]) if _tiene(m, "roic") else None,
         "rango": None, "competidores": mediana("roic"), "sector": 0.10, "menor_mejor": False,
         "que_es": "Beneficio por cada euro invertido en el negocio (de accionistas y de deuda). Por encima del 15 % sostenido suele indicar ventaja competitiva."},
        {"clave": "deuda_neta_ebitda", "nombre": "Deuda neta / EBITDA", "valor": m.get("deuda_neta_ebitda"), "fmt": "n1",
         "historia": None, "rango": None, "competidores": mediana("deuda_neta_ebitda"), "sector": 2.0, "menor_mejor": True,
         "que_es": "Años de beneficio bruto para pagar toda la deuda. Negativo = tiene más caja que deuda. Más de 3 empieza a ser mucho."},
        {"clave": "div_yield", "nombre": "Rentabilidad por dividendo", "valor": m.get("div_yield"), "fmt": "%2", "historia": None,
         "rango": None, "competidores": mediana("div_yield"), "sector": None, "menor_mejor": False,
         "que_es": "Lo que cobras al año en dividendos por cada 100 € invertidos al precio de hoy."},
        {"clave": "crec_bpa_3a", "nombre": "Crecimiento del beneficio (3 años)", "valor": m.get("crec_bpa_3a"), "fmt": "%",
         "historia": None, "rango": None, "competidores": None, "sector": None, "menor_mejor": False,
         "que_es": "Ritmo anual al que ha crecido el beneficio por acción en los tres últimos ejercicios."},
        {"clave": "prev_crec_anio_sig", "nombre": "Crecimiento esperado del beneficio", "valor": m.get("prev_crec_anio_sig"), "fmt": "%",
         "historia": m.get("crec_bpa_3a"), "rango": None, "competidores": None, "sector": None, "menor_mejor": False,
         "que_es": "Lo que esperan los analistas que crezca el beneficio por acción el próximo ejercicio. Es una previsión, no un hecho."},
    ]
    salida = []
    for f in filas:
        if not _ok(f["valor"]):
            continue
        f["fuente"] = m.get("fuentes", {}).get(f["clave"], "")
        f["nota"] = m.get("notas", {}).get(f["clave"], "")
        f["vs_historia"] = _juicio(f["valor"], f["historia"], f["menor_mejor"])
        f["vs_competidores"] = _juicio(f["valor"], f["competidores"], f["menor_mejor"])
        f["vs_sector"] = _juicio(f["valor"], f["sector"], f["menor_mejor"])
        votos = [v for v in (f["vs_historia"], f["vs_competidores"], f["vs_sector"]) if v]
        f["color"] = ("verde" if votos.count("mejor") > votos.count("peor") else "rojo" if votos.count("peor") > votos.count("mejor")
                      else "gris")
        salida.append(f)
    return salida


def _tiene(m: dict, col: str) -> bool:
    a = m.get("anual")
    return a is not None and not a.empty and col in a and a[col].notna().any()


def formato(valor, fmt: str) -> str:
    if not _ok(valor):
        return "—"
    if fmt == "x":
        return _n(valor, 1) + "x"
    if fmt == "%":
        return _pct(valor, 0)
    if fmt == "%2":
        return _pct(valor, 2)
    if fmt == "n2":
        return _n(valor, 2)
    return _n(valor, 1)


# ----------------------------------------------------------------------------- 3. calidad del negocio
def calidad(m: dict, sector: str | None, industria: str | None = None, seg: dict | None = None,
            n_clientes: int | None = None) -> dict:
    """Siete criterios con nota 0 (mal), 1 (regular) o 2 (bien) y una valoración global."""
    a = m.get("anual") if m.get("anual") is not None else pd.DataFrame()
    ref = SECTORES.get(sector or "")
    fin = bool(m.get("es_financiera"))
    c = []

    # --- ventaja competitiva: rentabilidad sobre el capital, nivel y constancia
    if not fin and _tiene(m, "roic"):
        roic = a["roic"].dropna()
        med, minimo = float(roic.tail(4).mean()), float(roic.tail(4).min())
        nota = 2 if (med >= 0.15 and minimo >= 0.08) else 1 if med >= 0.08 else 0
        texto = (f"ROIC medio del {_pct(med)} en {len(roic.tail(4))} ejercicios (mínimo {_pct(minimo)}). "
                 + ("Gana mucho más de lo que le cuesta el capital y lo hace todos los años: eso solo se sostiene si a los "
                    "competidores les resulta difícil quitarle clientes." if nota == 2 else
                    "Rentabilidad correcta pero no excepcional: tiene negocio, pero no una barrera clara frente a competidores." if nota == 1
                    else "Gana menos de lo que cuesta el capital que emplea: no se ve ventaja competitiva en los números."))
    elif _ok(m.get("roe")):
        roe_s = a["roe"].dropna() if _tiene(m, "roe") else pd.Series([m["roe"]])
        med = float(roe_s.tail(4).mean())
        nota = 2 if med >= 0.15 else 1 if med >= 0.09 else 0
        texto = (f"ROE medio del {_pct(med)}. " + ("Rentabilidad alta para un banco o aseguradora: suele indicar buena franquicia de "
                 "clientes y eficiencia." if nota == 2 else "Rentabilidad normal del sector." if nota == 1 else
                 "Rentabilidad baja: le cuesta ganar más que su coste de capital."))
    else:
        nota, texto = 1, "No hay datos suficientes para medir la rentabilidad sobre el capital."
    c.append({"criterio": "Ventaja competitiva (moat)", "pregunta": "¿Qué impide que un competidor le quite clientes?", "nota": nota, "texto": texto})

    # --- poder de fijación de precios: margen bruto, nivel y estabilidad
    if _tiene(m, "margen_bruto"):
        mb = a["margen_bruto"].dropna().tail(4)
        nivel, cambio, rango = float(mb.iloc[-1]), float(mb.iloc[-1] - mb.iloc[0]), float(mb.max() - mb.min())
        nota = 2 if (nivel >= 0.40 and cambio >= -0.02) else 0 if (cambio <= -0.05 or nivel < 0.15) else 1
        texto = (f"Margen bruto del {_pct(nivel)} ({'+' if cambio >= 0 else ''}{cambio * 100:.0f} puntos en {len(mb) - 1} años, "
                 f"oscila {rango * 100:.0f} puntos). "
                 + ("Margen alto y estable o creciente: puede subir precios o mantenerlos sin perder demanda." if nota == 2 else
                    "El margen se está estrechando o es muy bajo: le cuesta trasladar costes a sus clientes." if nota == 0 else
                    "Margen razonable: algo de poder de precios, sin ser dominante."))
    elif _tiene(m, "margen_neto"):
        mn = a["margen_neto"].dropna().tail(4)
        nota = 2 if mn.iloc[-1] >= mn.iloc[0] and mn.iloc[-1] > 0.15 else 1 if mn.iloc[-1] > 0.05 else 0
        texto = f"Margen neto del {_pct(float(mn.iloc[-1]))} (hace {len(mn) - 1} años: {_pct(float(mn.iloc[0]))}). No publica margen bruto."
    else:
        nota, texto = 1, "Sin datos de márgenes."
    c.append({"criterio": "Poder de fijación de precios", "pregunta": "¿Puede subir precios sin perder demanda?", "nota": nota, "texto": texto})

    # --- recurrencia y dependencia del ciclo: regularidad de los ingresos
    ciclo = ref[3] if ref else "medio"
    if industria and any(x in industria.lower() for x in ("semiconductor", "steel", "mining", "auto", "airline", "oil", "chemical", "homebuilding")):
        ciclo = "alto"
    if _tiene(m, "ingresos") and a["ingresos"].dropna().shape[0] >= 3:
        var = a["ingresos"].dropna().pct_change().dropna()
        caidas, peor, disp = int((var < 0).sum()), float(var.min()), float(var.std()) if len(var) > 1 else 0.0
        nota_rec = 2 if (caidas == 0 and disp < 0.12) else 0 if (peor < -0.10 or disp > 0.35) else 1
        texto_rec = (f"Ingresos: {caidas} año(s) de caída en los últimos {len(var)}; peor año {_pct(peor, 1 if abs(peor) < 0.01 else 0, True)}. "
                     + ("Crecen todos los años y de forma regular: ingresos predecibles." if nota_rec == 2 else
                        "Ingresos irregulares: dependen del ciclo o de contratos puntuales." if nota_rec == 0 else
                        "Ingresos razonablemente estables, con algún altibajo."))
        if disp > 0.35 and caidas == 0:
            texto_rec += " Ojo: crecer muy deprisa también es irregularidad; nadie garantiza que el ritmo se mantenga."
    else:
        nota_rec, texto_rec = 1, "Sin histórico suficiente de ingresos."
    c.append({"criterio": "Recurrencia de ingresos", "pregunta": "¿Son predecibles o dependen de ciclos y contratos puntuales?",
              "nota": nota_rec, "texto": texto_rec})
    nota_ciclo = {"bajo": 2, "medio": 1, "alto": 0}[ciclo]
    beta = m.get("beta")
    texto_ciclo = {"bajo": "Sector defensivo: la gente sigue pagando por lo que vende aunque haya recesión.",
                   "medio": "Sensibilidad media al ciclo económico: en una recesión vende menos, pero no se hunde.",
                   "alto": "Sector muy cíclico: en una recesión o al girarse su ciclo los beneficios pueden caer mucho."}[ciclo]
    if _ok(beta):
        texto_ciclo += f" Beta {_n(beta, 2)}: " + ("amplifica los movimientos del mercado." if beta > 1.3 else
                                                    "se mueve menos que el mercado." if beta < 0.8 else "se mueve parecido al mercado.")
    if ref:
        texto_ciclo += f" Lo que más le afecta: {ref[4]}."
    c.append({"criterio": "Dependencia del ciclo", "pregunta": "¿Cómo le afecta una recesión o un ciclo bajista del sector?",
              "nota": nota_ciclo, "texto": texto_ciclo})

    # --- concentración (de negocio y de clientes)
    nota_con, texto_con = 1, "No tengo desglose de sus ingresos ni clientes principales: revísalo en su informe anual."
    if seg and seg.get("ejes"):
        from .negocio import principal

        p = principal(seg)
        tc = seg["ejes"].get("cliente")
        partes = []
        if p:
            partes.append(f"{'El' if seg.get('oficial') else 'En torno al'} {p[1]:.0f} % de los ingresos viene de «{p[0]}»")
            nota_con = 0 if p[1] >= 75 else 1 if p[1] >= 50 else 2
        if tc is not None and len(tc):
            t0 = tc.sort_values("pct", ascending=False).iloc[0]
            partes.append(f"su mayor grupo de clientes («{t0['segmento']}») pesa un {t0['pct']:.0f} %")
            if t0["pct"] >= 50 and "particular" not in str(t0["segmento"]).lower():
                nota_con = min(nota_con, 0)
        texto_con = "; ".join(partes) + ". " + (
            "Muy concentrada: si ese negocio o esos clientes frenan, no hay otra pata que compense." if nota_con == 0 else
            "Concentración media." if nota_con == 1 else "Negocio diversificado.")
    elif n_clientes is not None and n_clientes > 0:
        texto_con = f"Tengo {n_clientes} clientes identificados en la base, sin su peso. " + texto_con
    c.append({"criterio": "Concentración de clientes y negocio", "pregunta": "¿Depende de pocos clientes o de un solo producto?",
              "nota": nota_con, "texto": texto_con})

    # --- gestión y asignación de capital
    partes, puntos = [], 0
    if _tiene(m, "conversion_caja") and not fin:
        conv = _media(a["conversion_caja"])
        if _ok(conv):
            partes.append(f"convierte en caja el {_pct(conv)} del beneficio")
            puntos += 1 if conv >= 0.85 else -1 if conv < 0.5 else 0
    dn = m.get("deuda_neta_ebitda")
    if _ok(dn) and not fin:
        partes.append("tiene más caja que deuda" if dn < 0 else f"deuda neta de {_n(dn)} veces el EBITDA")
        puntos += 1 if dn < 1.5 else -1 if dn > 3 else 0
    if _tiene(m, "recompras") and _tiene(m, "neto"):
        rec = -float(a["recompras"].fillna(0).tail(3).sum())
        ben = float(a["neto"].tail(3).sum())
        if rec > 0 and ben > 0:
            partes.append(f"ha dedicado a recompras el {_pct(rec / ben)} del beneficio de 3 años")
    if _tiene(m, "fondo_comercio") and _tiene(m, "activos"):
        fc = float(a["fondo_comercio"].dropna().iloc[-1] / a["activos"].dropna().iloc[-1])
        if fc > 0.35:
            partes.append(f"el {_pct(fc)} de sus activos es fondo de comercio (ha crecido comprando empresas: riesgo de haber pagado de más)")
            puntos -= 1
    if _tiene(m, "roic") and len(a["roic"].dropna()) >= 3 and not fin:
        r = a["roic"].dropna()
        if r.iloc[-1] > r.iloc[0] + 0.03:
            partes.append("la rentabilidad del capital mejora")
            puntos += 1
        elif r.iloc[-1] < r.iloc[0] - 0.05:
            partes.append("la rentabilidad del capital empeora")
            puntos -= 1
    if m.get("div_recortes"):
        partes.append(f"ha recortado el dividendo {m['div_recortes']} vez/veces en 10 años")
        puntos -= 1
    nota_g = 2 if puntos >= 2 else 0 if puntos <= -1 else 1
    c.append({"criterio": "Gestión y asignación del capital", "pregunta": "¿El equipo directivo usa bien el dinero?", "nota": nota_g,
              "texto": (("En los números: " + "; ".join(partes) + ". ") if partes else "Sin datos suficientes. ")
              + ("Disciplina financiera clara." if nota_g == 2 else "Hay señales de asignación de capital mejorable." if nota_g == 0
                 else "Sin alarmas ni méritos especiales.")
              + " (Los números no dicen si el equipo es honesto o brillante: mira también quién dirige y cuántas acciones tiene.)"})

    # --- dilución
    ca = m.get("crec_acciones")
    if _ok(ca):
        nota_d = 2 if ca <= -0.01 else 0 if ca >= 0.03 else 1
        texto_d = (f"El número de acciones {'baja' if ca < 0 else 'sube'} un {_pct(abs(ca), 1)} al año. "
                   + ("Recompra acciones: cada año te toca un trozo algo mayor de la empresa." if nota_d == 2 else
                      "Emite acciones de forma continuada: tu parte de la empresa se va encogiendo." if nota_d == 0 else
                      "Número de acciones estable."))
        if _tiene(m, "sbc") and _tiene(m, "ingresos"):
            sbc = float(a["sbc"].dropna().iloc[-1] / a["ingresos"].dropna().iloc[-1])
            if sbc > 0.05:
                texto_d += f" Paga en acciones a sus empleados el equivalente al {_pct(sbc)} de las ventas: es un coste real aunque no salga de la caja."
                nota_d = min(nota_d, 1)
    else:
        nota_d, texto_d = 1, "Sin datos del número de acciones."
    c.append({"criterio": "Dilución del accionista", "pregunta": "¿Emite acciones continuamente o las recompra?", "nota": nota_d, "texto": texto_d})

    media = sum(x["nota"] for x in c) / len(c)
    # La rentabilidad pesa doble: es lo que distingue un gran negocio
    media = (media * len(c) + c[0]["nota"]) / (len(c) + 1)
    etiqueta = "Excelente" if media >= 1.6 else "Buena" if media >= 1.2 else "Aceptable" if media >= 0.8 else "Mediocre"
    fuertes = [x["criterio"].lower() for x in c if x["nota"] == 2]
    debiles = [x["criterio"].lower() for x in c if x["nota"] == 0]
    frase = f"Calidad {etiqueta.lower()}."
    if fuertes:
        frase += " Lo mejor: " + ", ".join(fuertes[:3]) + "."
    if debiles:
        frase += " Lo peor: " + ", ".join(debiles[:3]) + "."
    if not fuertes and not debiles:
        frase += " No destaca ni para bien ni para mal en ningún criterio."
    return {"criterios": c, "media": media, "etiqueta": etiqueta, "frase": frase, "ciclo": ciclo}


# ----------------------------------------------------------------------------- 6. técnico
def tecnico(h: pd.DataFrame, reaccion: pd.DataFrame | None = None) -> dict:
    c = h["Close"].dropna()
    if len(c) < 60:
        return {}
    p = float(c.iloc[-1])
    m50 = float(c.tail(50).mean())
    m200 = float(c.tail(200).mean()) if len(c) >= 200 else None
    anio = c.tail(252)
    maximo, minimo = float(anio.max()), float(anio.min())
    pos = (p - minimo) / (maximo - minimo) if maximo > minimo else 0.5
    r4 = p / float(c.iloc[-21]) - 1 if len(c) > 21 else None
    r8 = p / float(c.iloc[-41]) - 1 if len(c) > 41 else None
    if m200 is None:
        tendencia = "lateral"
    elif p > m200 and m50 > m200:
        tendencia = "alcista"
    elif p < m200 and m50 < m200:
        tendencia = "bajista"
    else:
        tendencia = "lateral"
    vol = float(np.log(c).diff().tail(252).std() * math.sqrt(252))
    t = {"precio": p, "tendencia": tendencia, "vs_m200": (p / m200 - 1) if m200 else None, "max52": maximo, "min52": minimo,
         "pos52": pos, "desde_max": p / maximo - 1, "desde_min": p / minimo - 1, "r4": r4, "r8": r8, "vol_anual": vol,
         "caida_max_5a": float((c / c.cummax() - 1).min())}
    t["frase_tendencia"] = {
        "alcista": "Tendencia de fondo **alcista**: cotiza por encima de su media de 200 sesiones y la media corta está sobre la larga.",
        "bajista": "Tendencia de fondo **bajista**: cotiza por debajo de su media de 200 sesiones y la media corta está bajo la larga.",
        "lateral": "Tendencia **lateral o en transición**: precio y medias no apuntan en la misma dirección."}[tendencia]
    t["frase_rango"] = (f"Está a un {_pct(abs(t['desde_max']), 0)} de su máximo de 52 semanas y un {_pct(t['desde_min'], 0)} por encima "
                        f"del mínimo" + (": cerca de máximos (el mercado ya ha puesto en precio buenas noticias)." if pos > 0.85 else
                                         ": cerca de mínimos (o es una oportunidad o el mercado sabe algo: mira los riesgos)." if pos < 0.15
                                         else ": en la zona media de su rango anual."))
    if _ok(r4) and _ok(r8):
        t["frase_momentum"] = (f"Impulso reciente: {_pct(r4, 0, True)} en 4 semanas y {_pct(r8, 0, True)} en 8. "
                               + ("Acelera al alza." if (r4 > 0.05 and r8 > 0.08) else "Pierde fuerza con rapidez." if (r4 < -0.05 and r8 < -0.08)
                                  else "Sin impulso claro."))
    if reaccion is not None and not reaccion.empty and len(reaccion) >= 3:
        mov = reaccion["Reacción"]
        sube = int((mov > 0).sum())
        t["resultados"] = {"n": len(mov), "media_abs": float(mov.abs().mean()), "subio": sube, "media": float(mov.mean()),
                           "bate": int((reaccion["Sorpresa"] > 0).sum())}
        t["frase_resultados"] = (
            f"En las últimas {len(mov)} presentaciones de resultados se movió de media un ±{_pct(float(mov.abs().mean()), 1)} al día "
            f"siguiente; subió en {sube} y bajó en {len(mov) - sube}. Batió previsiones en {t['resultados']['bate']} de {len(mov)}"
            + (", y aun así cayó más veces de las que subió: el listón está muy alto." if (t["resultados"]["bate"] >= len(mov) - 1 and sube < len(mov) / 2)
               else "."))
    return t


# ----------------------------------------------------------------------------- 4b. DCA
def dca(m: dict, tec: dict, cal: dict, trampa: list[str]) -> dict:
    puntos, lineas = 0, []
    vol = tec.get("vol_anual")
    if _ok(vol):
        if 0.22 <= vol <= 0.55:
            puntos += 1
            lineas.append((2, f"**Volatilidad** del {_pct(vol)} anual: oscila lo suficiente para que comprar cada mes te deje un precio medio "
                              "mejor que comprar de golpe en un mal día."))
        elif vol < 0.22:
            lineas.append((1, f"**Volatilidad** baja ({_pct(vol)} anual): el DCA aporta poco frente a comprar de una vez, pero tampoco perjudica."))
        else:
            puntos -= 1
            lineas.append((0, f"**Volatilidad** muy alta ({_pct(vol)} anual): promediar ayuda, pero puedes pasar mucho tiempo en pérdidas."))
    g = m.get("prev_crec_anio_sig") if _ok(m.get("prev_crec_anio_sig")) else m.get("crec_bpa_3a")
    g_ing = m.get("crec_ingresos_3a")
    estructural = cal["media"] >= 1.2 and (not _ok(g_ing) or g_ing > 0)
    if estructural:
        puntos += 2
        lineas.append((2, "**Tendencia estructural**: negocio de calidad con ingresos que crecen. Es razonable pensar que valdrá más en 3-5 años, "
                          "que es la condición imprescindible para promediar."))
    elif cal["media"] >= 0.8 and (not _ok(g_ing) or g_ing > -0.03):
        lineas.append((1, "**Tendencia estructural**: negocio correcto sin crecimiento claro. Promediar tiene sentido solo si confías en que no se deteriora."))
    else:
        puntos -= 2
        lineas.append((0, "**Tendencia estructural**: negocio débil o en retroceso. Sin convicción de que valdrá más en unos años, "
                          "el DCA solo aplaza una mala decisión."))
    liq = m.get("volumen_medio_eur")
    if _ok(liq):
        if liq >= 20e6:
            puntos += 1
            lineas.append((2, f"**Liquidez**: negocia unos {_n(liq / 1e6, 0)} millones al día. La horquilla de compra-venta es mínima: cada aportación cuesta poco."))
        elif liq >= 2e6:
            lineas.append((1, f"**Liquidez** suficiente ({_n(liq / 1e6, 1)} millones al día), con algo más de horquilla."))
        else:
            puntos -= 1
            lineas.append((0, f"**Liquidez** baja ({_n(liq / 1e6, 2)} millones al día): la horquilla se come parte de cada compra periódica."))
    dy = m.get("div_yield")
    if _ok(dy) and dy >= 0.015:
        puntos += 1
        lineas.append((2, f"**Dividendos**: paga un {_pct(dy, 1)} al año. Reinvertirlos compra más acciones en cada pago y acelera el interés compuesto."))
    else:
        lineas.append((1, "**Dividendos**: no paga o paga muy poco; todo el efecto vendrá del precio."))
    if trampa:
        puntos -= 2
        lineas.append((0, "**Riesgo de trampa de valor**: " + "; ".join(trampa) + ". Si está barata por un deterioro de fondo, promediar es "
                          "comprar cada vez más de algo que vale cada vez menos."))
    else:
        lineas.append((2, "**Riesgo de trampa de valor**: no veo señales de deterioro estructural en las cuentas."))
    if puntos >= 3 and not trampa:
        veredicto, frase = "Muy apta", "Negocio sólido, líquido y con vaivenes suficientes: las bajadas son ocasiones para abaratar el precio medio."
    elif puntos >= 0 and not (trampa and cal["media"] < 0.8):
        veredicto = "Apta con condiciones"
        frase = ("Sirve si el horizonte es de 3-5 años y vigilas que el negocio no se deteriore; conviene fijar un importe máximo total."
                 if not trampa else "Solo con importe limitado y revisando cada trimestre que las señales de deterioro no empeoran.")
    else:
        veredicto, frase = "No recomendable para DCA", "Sin tendencia de fondo favorable, promediar a la baja acumula pérdidas en lugar de reducirlas."
    return {"veredicto": veredicto, "frase": frase, "lineas": lineas, "puntos": puntos}


def senales_trampa(m: dict, cal: dict) -> list[str]:
    """Indicios de que está barata por motivos estructurales (y no solo porque su ciclo esté en la parte baja)."""
    a = m.get("anual") if m.get("anual") is not None else pd.DataFrame()
    blandas, duras = [], []
    if _ok(m.get("crec_ingresos_3a")) and m["crec_ingresos_3a"] < -0.02:
        blandas.append(f"los ingresos caen un {_pct(abs(m['crec_ingresos_3a']), 0)} al año")
    if _tiene(m, "margen_op") and len(a["margen_op"].dropna()) >= 3:
        mo = a["margen_op"].dropna()
        if mo.iloc[-1] < mo.iloc[0] - 0.04:
            blandas.append(f"el margen operativo ha bajado de {_pct(float(mo.iloc[0]))} a {_pct(float(mo.iloc[-1]))}")
    if _ok(m.get("deuda_neta_ebitda")) and m["deuda_neta_ebitda"] > 4:
        duras.append(f"la deuda neta es {_n(m['deuda_neta_ebitda'])} veces el EBITDA")
    if _ok(m.get("payout")) and m["payout"] > 1.0 and _ok(m.get("div_yield")) and m["div_yield"] > 0.04:
        duras.append("reparte en dividendos más de lo que gana")
    if _ok(m.get("neto")) and m["neto"] < 0:
        duras.append("está en pérdidas")
    todas = duras + blandas
    barata = _ok(m.get("per")) and m["per"] < 9
    if cal.get("ciclo") == "alto":
        # En un negocio cíclico, que bajen ventas y márgenes puede ser solo el ciclo: hace falta además una señal dura
        return todas if (duras and len(todas) >= 2) else []
    return todas if (len(todas) >= 2 or (todas and barata) or (duras and cal["media"] < 0.8)) else []


# ----------------------------------------------------------------------------- 4. valoración por perfil
def estrellas(m: dict, cal: dict, tec: dict, d: dict) -> dict:
    # --- crecimiento
    g = m.get("prev_crec_anio_sig") if _ok(m.get("prev_crec_anio_sig")) else m.get("crec_bpa_3a")
    gi = m.get("crec_ingresos_3a")
    e = 1.0
    if _ok(g):
        e += 1.5 if g >= 0.20 else 1.0 if g >= 0.10 else 0.5 if g >= 0.04 else 0
    if _ok(gi):
        e += 1.0 if gi >= 0.12 else 0.5 if gi >= 0.05 else 0
    e += 1.0 if cal["media"] >= 1.5 else 0.5 if cal["media"] >= 1.1 else 0
    peg = m.get("peg")
    if _ok(peg):
        e += 0.5 if peg < 1 else -0.5 if peg > 2.5 else 0
    crec = int(min(5, max(1, round(e))))
    por_que_c = (f"beneficio {'esperado' if _ok(m.get('prev_crec_anio_sig')) else 'histórico'} {_pct(g, 0, True)}" if _ok(g) else "sin datos de crecimiento del beneficio")
    if _ok(gi):
        por_que_c += f", ingresos {_pct(gi, 0, True)} al año"
    if _ok(peg):
        por_que_c += f", PEG {_n(peg, 2)}" + (" (el crecimiento sale barato)" if peg < 1 else " (se paga caro)" if peg > 2.5 else "")
    # --- dividendos
    dy, po = m.get("div_yield"), m.get("payout")
    if not _ok(dy) or dy < 0.005:
        div, por_que_d = 1, "no paga dividendo o es simbólico"
    else:
        e = 1.0 + (2.0 if dy >= 0.045 else 1.5 if dy >= 0.03 else 1.0 if dy >= 0.02 else 0.5)
        sostenible = (not _ok(po) or po < 0.75) and (not _ok(m.get("payout_fcf")) or m["payout_fcf"] < 0.9)
        e += 1.0 if sostenible else -0.5
        dc = m.get("div_crec_3a")
        e += 0.5 if (_ok(dc) and dc >= 0.05) else 0
        e += 0.5 if (m.get("div_recortes") == 0 and (m.get("div_anios_seguidos") or 0) >= 8) else -0.5 if (m.get("div_recortes") or 0) >= 2 else 0
        if _ok(m.get("deuda_neta_ebitda")) and m["deuda_neta_ebitda"] > 3.5:
            e -= 0.5
        div = int(min(5, max(1, round(e))))
        por_que_d = (f"paga un {_pct(dy, 1)}" + (f" repartiendo el {_pct(po)} del beneficio" if _ok(po) else "")
                     + (f", crece un {_pct(dc, 0)} al año" if _ok(dc) and dc > 0 else "")
                     + (f", {m['div_recortes']} recorte(s) en 10 años" if m.get("div_recortes") else ", sin recortes en 10 años" if (m.get("div_anios_seguidos") or 0) >= 8 else ""))
    # --- DCA
    dca_e = {"Muy apta": 5, "Apta con condiciones": 3, "No recomendable para DCA": 1}[d["veredicto"]]
    if d["veredicto"] == "Muy apta" and d["puntos"] < 5:
        dca_e = 4
    if d["veredicto"] == "Apta con condiciones" and d["puntos"] <= 0:
        dca_e = 2
    mejor = max((("crecimiento", crec), ("dividendos", div), ("DCA", dca_e)), key=lambda x: x[1])
    if crec == div:
        encaje = "Encaja por igual como valor de crecimiento y de renta: es una empresa mixta."
    elif crec > div:
        encaje = "Encaja mejor como valor de **crecimiento**: lo que puede darte es revalorización, no rentas."
    else:
        encaje = "Encaja mejor como valor de **dividendos**: su atractivo es la renta periódica, no que el precio se dispare."
    if max(crec, div) <= 2:
        encaje = "No destaca ni por crecimiento ni por dividendo: solo tendría sentido si está muy barata."
    return {"crecimiento": crec, "dividendos": div, "dca": dca_e, "por_que_crecimiento": por_que_c, "por_que_dividendos": por_que_d,
            "encaje": encaje, "mejor": mejor[0]}


# ----------------------------------------------------------------------------- 7. escenarios de precio
def escenarios_precio(m: dict, cal: dict, sector: str | None, estadistico: dict | None = None, meses: int = 15) -> dict:
    """Tres escenarios a 12-18 meses por múltiplos sobre el beneficio esperado, con sus supuestos a la vista.

    Cuando no hay beneficios, se usa el rango estadístico (volatilidad histórica) y se dice claramente.
    `estadistico`: {'p10': …, 'p50': …, 'p90': …} del simulador a ese horizonte, como contraste.
    """
    precio = m.get("precio")
    fp = m.get("factor_precio", 1.0)
    per, per_fwd = m.get("per"), m.get("per_fwd")
    ref = SECTORES.get(sector or "")
    hist = m.get("per_hist") or {}
    dy = m.get("div_yield") or 0.0
    div_total = dy * meses / 12
    salida = {"meses": meses, "dividendo_periodo": div_total, "analistas": None, "estadistico": estadistico, "supuestos": []}
    if _ok(m.get("obj_medio")) and _ok(m.get("obj_bajo")) and _ok(m.get("obj_alto")):
        salida["analistas"] = {"bajo": m["obj_bajo"], "medio": m["obj_medio"], "alto": m["obj_alto"], "n": m.get("n_analistas")}

    def rango(centro):
        return (redondo(centro * 0.94), redondo(centro * 1.06))

    def paquete(nombre, centro, condiciones, metodo):
        lo, hi = rango(centro)
        return {"nombre": nombre, "centro": centro, "bajo": lo, "alto": hi, "condiciones": condiciones, "metodo": metodo,
                "rent_precio": centro / precio - 1, "rent_total": centro / precio - 1 + div_total}

    if _ok(per) and per > 0 and _ok(precio) and per < 120:
        bpa_hoy = precio / per  # beneficio por acción en la unidad en que cotiza
        if _ok(per_fwd) and per_fwd > 0:
            g = per / per_fwd - 1
            origen_g = "previsión de los analistas para el próximo ejercicio"
        elif _ok(m.get("crec_bpa_3a")):
            g = max(min(m["crec_bpa_3a"], 0.15), -0.10) * meses / 12
            origen_g = "ritmo de los últimos 3 años, limitado al 15 % anual"
        else:
            g, origen_g = 0.0, "sin previsiones: beneficio plano"
        # Prudencia: del crecimiento entre el 20 % y el 50 % solo se da por bueno la mitad, y de lo que pasa del 50 %, la cuarta parte
        g_prud = g if g <= 0.20 else 0.20 + (min(g, 0.50) - 0.20) * 0.5 + max(g - 0.50, 0) * 0.25
        if hist.get("n", 0) >= 3 and ref:
            ancla = (hist["mediana"] + ref[0]) / 2
            origen_ancla = (f"media entre la mediana de su propio PER desde {hist.get('desde')} ({_n(hist['mediana'])}x) y el PER "
                            f"orientativo de su sector ({ref[0]}x)")
        elif hist.get("n", 0) >= 3:
            ancla, origen_ancla = hist["mediana"], f"mediana de su propio PER desde {hist.get('desde')} ({_n(hist['mediana'])}x)"
        else:
            ancla = ref[0] if ref else None
            origen_ancla = f"PER orientativo de su sector ({ref[0]}x)" if ref else "sin referencia: se mantiene el PER actual"
        ancla_lim = min(max(ancla, per * 0.7), per * 1.3) if _ok(ancla) else per
        m_base = (per + ancla_lim) / 2
        if g > 0.25:
            m_base *= 0.90  # cuando el crecimiento se normaliza, el mercado paga menos múltiplo
        if cal["media"] < 0.8:
            m_base = min(m_base, per)
        m_base = min(max(m_base, 5), 45)
        m_alc = min(max(per, ancla_lim) * 1.10, 55)
        m_baj = max(min(per, ancla_lim) * 0.72, 4)
        bpa_base = bpa_hoy * (1 + g_prud)
        bpa_alc = bpa_hoy * (1 + max(g, g_prud) * (1.05 if g > 0 else 0.5))
        bpa_baj = bpa_hoy * (1 + (0.25 * g_prud if g_prud > 0.05 else g_prud - 0.12))
        salida["escenarios"] = [
            paquete("🟢 Optimista", bpa_alc * m_alc,
                    f"{'Cumple (o supera por poco) las previsiones' if g > 0 else 'El beneficio aguanta mejor de lo previsto'}: "
                    f"beneficio por acción {_pct(bpa_alc / bpa_hoy - 1, 0, True)}, "
                    f"y el mercado le paga {_n(m_alc)} veces beneficios (hoy {_n(per)}).",
                    "Múltiplo alto de su rango × beneficio previsto"),
            paquete("🔵 Base (más probable)", bpa_base * m_base,
                    f"El beneficio por acción {'crece' if bpa_base >= bpa_hoy else 'cae'} un {_pct(abs(bpa_base / bpa_hoy - 1), 0)} "
                    + ("(doy por bueno solo parte del crecimiento previsto) " if g > 0.20 else "")
                    + f"y el PER se queda en {_n(m_base)} veces, entre el actual y su referencia.",
                    "Múltiplo intermedio × beneficio previsto con recorte de prudencia"),
            paquete("🔴 Pesimista", bpa_baj * m_baj,
                    f"El beneficio {'apenas crece' if bpa_baj >= bpa_hoy else 'cae'} ({_pct(bpa_baj / bpa_hoy - 1, 0, True)}) y el mercado deja de "
                    f"pagar prima: PER de {_n(m_baj)} veces.",
                    "Múltiplo bajo × beneficio que decepciona"),
        ]
        salida["metodo"] = "Múltiplos (PER) sobre el beneficio por acción esperado dentro de 12-18 meses"
        salida["supuestos"] = [
            f"Beneficio por acción de partida: {_n(bpa_hoy * fp, 2)} {m.get('moneda_base', '')} (últimos 12 meses).",
            f"Crecimiento del beneficio: {_pct(g, 0, True)} según {origen_g}"
            + (f"; en el escenario base uso {_pct(g_prud, 0, True)} por prudencia." if g > 0.20 else "."),
            f"Referencia de múltiplo: {origen_ancla}; se limita a ±30 % del PER actual para no extrapolar épocas excepcionales.",
            f"Dividendo cobrado en el periodo: {_pct(div_total, 1)}." if div_total > 0.002 else "No se cuenta dividendo (no paga o es simbólico).",
            "Cada precio se da como rango de ±6 % alrededor del cálculo: más precisión sería inventada.",
        ]
    elif _ok(per_fwd) and 0 < per_fwd < 80 and _ok(precio):
        # Hoy no gana dinero (o casi), pero los analistas esperan beneficios: se valora con ellos, sabiendo que es mucho más incierto
        bpa_f = precio / per_fwd
        m_ref = ref[0] if ref else 15
        m_base, m_alc, m_baj = min(per_fwd, m_ref), min(per_fwd * 1.1, m_ref * 1.3), m_ref * 0.7
        salida["escenarios"] = [
            paquete("🟢 Optimista", bpa_f * m_alc, f"Alcanza el beneficio que esperan los analistas y el mercado le paga {_n(m_alc)} veces.",
                    "Beneficio previsto × múltiplo alto"),
            paquete("🔵 Base (más probable)", bpa_f * 0.8 * m_base, f"Consigue el 80 % del beneficio previsto y cotiza a {_n(m_base)} veces.",
                    "Beneficio previsto con recorte × múltiplo del sector"),
            paquete("🔴 Pesimista", bpa_f * 0.45 * m_baj, f"La recuperación se queda a medias (45 % del beneficio previsto) y cotiza a {_n(m_baj)} veces.",
                    "Recuperación a medias × múltiplo bajo"),
        ]
        salida["metodo"] = "Múltiplos (PER) sobre el beneficio previsto por analistas (hoy no hay beneficio representativo)"
        salida["supuestos"] = [
            "La empresa está en pérdidas o casi: no se puede usar su beneficio actual. Se parte del que esperan los analistas para el próximo "
            f"ejercicio ({_n(bpa_f * fp, 2)} {m.get('moneda_base', '')} por acción), que es una previsión y puede fallar por mucho.",
            f"Múltiplo de referencia: PER orientativo del sector ({m_ref}x).",
            "Cada precio se da como rango de ±6 % alrededor del cálculo.",
        ]
    elif estadistico and all(_ok(estadistico.get(k)) for k in ("p10", "p50", "p90")):
        salida["escenarios"] = [
            paquete("🟢 Optimista", estadistico["p90"], "Solo 1 de cada 10 trayectorias históricas acaba por encima.", "Percentil 90 de la simulación"),
            paquete("🔵 Base (más probable)", estadistico["p50"], "Punto medio de las trayectorias simuladas.", "Mediana de la simulación"),
            paquete("🔴 Pesimista", estadistico["p10"], "1 de cada 10 trayectorias históricas acaba por debajo.", "Percentil 10 de la simulación"),
        ]
        salida["metodo"] = "Rango estadístico por volatilidad histórica (no por valoración)"
        salida["supuestos"] = ["La empresa no tiene beneficios positivos o su PER no es representativo: no se puede valorar por múltiplos de beneficio.",
                               "Estos rangos solo repiten cómo se ha movido el precio en el pasado; no dicen cuánto vale el negocio."]
    else:
        salida["escenarios"] = []
        salida["metodo"] = "Sin datos suficientes para construir escenarios"
    return salida


# ----------------------------------------------------------------------------- 8. riesgos
def riesgos(m: dict, cal: dict, tec: dict, sector: str | None, seg: dict | None, esc: dict, trampa: list[str],
            proveedores: list[str] | None = None, noticias_neg: list[dict] | None = None, moneda_usuario: str = "EUR") -> dict:
    ref = SECTORES.get(sector or "")
    r = []
    per, hist = m.get("per"), m.get("per_hist") or {}
    g = m.get("prev_crec_anio_sig")
    if _ok(per) and ref and per > 1.5 * ref[0] and (not hist or per > hist.get("mediana", 0) * 0.9):
        r.append((2, "Valoración exigente", f"Cotiza a {_n(per)} veces beneficios frente a ~{ref[0]} de referencia en su sector. A estos precios "
                     "no basta con que vaya bien: tiene que ir mejor de lo que ya espera el mercado."))
    elif _ok(per) and ref and per > 1.2 * ref[0]:
        r.append((1, "Valoración por encima del sector", f"PER de {_n(per)} frente a ~{ref[0]} del sector: hay prima, que se pierde si el crecimiento afloja."))
    if hist.get("n", 0) >= 3 and _ok(per) and per > 1.4 * hist["mediana"]:
        r.append((1, "Más cara que su propia historia", f"Cotiza a {_n(per)} veces beneficios cuando su mediana desde {hist.get('desde')} es "
                     f"{_n(hist['mediana'])}: el mercado ya la ha revalorizado y parte de lo bueno está en el precio."))
    if cal.get("ciclo") == "alto" and _ok(g) and g < -0.10:
        r.append((1, "Beneficios en la parte baja del ciclo", f"Se espera que el beneficio caiga un {_pct(abs(g), 0)}: con PER bajo parece barata, "
                     "pero ese PER está calculado con beneficios que no se van a repetir."))
    if _ok(g) and g > 0.30:
        r.append((2, "Expectativas muy altas", f"Los analistas esperan que el beneficio crezca un {_pct(g, 0)} el próximo ejercicio. Si se queda "
                     "corta, caen a la vez el beneficio previsto y el múltiplo que se paga por él: doble golpe."))
    if seg and seg.get("ejes"):
        from .negocio import principal

        p = principal(seg)
        if p and p[1] >= 70:
            r.append((2 if p[1] >= 85 else 1, "Depende de un solo negocio", f"«{p[0]}» aporta el {p[1]:.0f} % de los ingresos. Si esa demanda se frena, no hay nada que lo compense."))
        elif p and p[1] >= 50:
            r.append((1, "Negocio concentrado", f"«{p[0]}» es el {p[1]:.0f} % de los ingresos."))
        tc = seg["ejes"].get("cliente")
        if tc is not None and len(tc):
            t0 = tc.sort_values("pct", ascending=False).iloc[0]
            if t0["pct"] >= 40 and "particular" not in str(t0["segmento"]).lower():
                r.append((2 if t0["pct"] >= 55 else 1, "Pocos clientes muy grandes",
                          f"«{t0['segmento']}» supone en torno al {t0['pct']:.0f} % de las ventas: tienen poder para negociar precios, "
                          "recortar pedidos o fabricarse su propia alternativa."))
        geo = seg["ejes"].get("geografia")
        if geo is not None and len(geo):
            china = geo[geo["segmento"].str.contains("China|Taiw", case=False, regex=True)]
            if len(china) and china["pct"].sum() >= 15:
                r.append((1, "Exposición a China y Taiwán", f"El {china['pct'].sum():.0f} % de los ingresos se factura allí: aranceles, vetos a la "
                             "exportación o una crisis en el estrecho le afectarían directamente."))
    if proveedores and any("TSMC" in p.upper() for p in proveedores):
        r.append((1, "Fabricación concentrada en Taiwán", "Sus chips los fabrica TSMC. No hay alternativa rápida si hay un problema en Taiwán."))
    dn = m.get("deuda_neta_ebitda")
    if _ok(dn) and dn > 3.5:
        r.append((2, "Deuda elevada", f"Debe {_n(dn)} veces su EBITDA. Con tipos altos o un mal año, refinanciar puede obligarla a recortar dividendo o ampliar capital."))
    elif _ok(dn) and dn > 2.3:
        r.append((1, "Deuda apreciable", f"Deuda neta de {_n(dn)} veces el EBITDA: manejable, pero resta margen de maniobra."))
    ci = m.get("cobertura_intereses")
    if _ok(ci) and ci < 0:
        r.append((2, "Pierde dinero antes de pagar intereses", "El negocio no genera beneficio operativo: la deuda se paga con caja o con más deuda."))
    elif _ok(ci) and ci < 3:
        r.append((2, "Los intereses pesan", f"El beneficio operativo solo cubre {_n(ci)} veces los intereses de la deuda."))
    if cal.get("ciclo") == "alto":
        a = m.get("anual")
        extra = ""
        if a is not None and not a.empty and a["margen_op"].notna().sum() >= 3:
            mo = a["margen_op"].dropna()
            if mo.iloc[-1] >= mo.max() * 0.97 and mo.iloc[-1] > mo.mean() * 1.15:
                extra = f" Además, su margen ({_pct(float(mo.iloc[-1]))}) está en máximos del ciclo: lo normal es que vuelva hacia su media ({_pct(float(mo.mean()))})."
        r.append((2 if extra else 1, "Negocio cíclico", "Sus beneficios dependen del ciclo" + (f" ({ref[4]})" if ref else "") + "." + extra))
    if _ok(m.get("payout")) and m["payout"] > 0.9 and _ok(m.get("div_yield")) and m["div_yield"] > 0.02:
        r.append((2 if m["payout"] > 1.1 else 1, "Dividendo en el límite", f"Reparte el {_pct(m['payout'])} de lo que gana: cualquier bache obliga a recortarlo."))
    a = m.get("anual")
    if a is not None and not a.empty and "conversion_caja" in a and not m.get("es_financiera"):
        conv = _media(a["conversion_caja"])
        if _ok(conv) and conv < 0.6:
            r.append((1, "El beneficio no se convierte en caja", f"Solo el {_pct(conv)} del beneficio contable acaba siendo caja libre: o invierte mucho o el beneficio es menos sólido de lo que parece."))
    if _ok(m.get("crec_acciones")) and m["crec_acciones"] >= 0.03:
        r.append((1, "Dilución", f"Emite un {_pct(m['crec_acciones'], 1)} más de acciones cada año: tu parte se reduce aunque la empresa crezca."))
    if trampa:
        r.append((2, "Posible trampa de valor", "Parece barata, pero " + "; ".join(trampa) + "."))
    if tec and _ok(tec.get("vol_anual")) and tec["vol_anual"] > 0.5:
        r.append((1, "Volatilidad muy alta", f"Se mueve un {_pct(tec['vol_anual'])} al año y ya ha llegado a caer un {_pct(abs(tec.get('caida_max_5a', 0)))} desde máximos en los últimos años."))
    mb = m.get("moneda_base")
    if mb and mb != moneda_usuario:
        r.append((1, "Riesgo de divisa", f"Cotiza en {mb}. Si el {mb} se deprecia frente al {moneda_usuario}, pierdes aunque la acción suba (y al revés)."))
    liq = m.get("volumen_medio_eur")
    if _ok(liq) and liq < 1e6:
        r.append((1, "Poca liquidez", "Se negocia poco: entrar y salir puede costar más de lo que parece."))
    for n in (noticias_neg or [])[:2]:
        r.append((1, "En las noticias", f"«{n['titulo']}» ({n.get('fuente', '')})."))
    r.sort(key=lambda x: -x[0])
    r = r[:7]
    if len(r) < 4:
        genericos = [
            (1, "Riesgo de mercado", "En una caída general de la bolsa bajará con ella, por buena que sea la empresa"
                + (f" (ya cayó un {_pct(abs(tec['caida_max_5a']))} desde máximos en los últimos años)." if tec and _ok(tec.get("caida_max_5a")) else ".")),
            (1, "Competencia y cambios tecnológicos", "Una ventaja de hoy puede dejar de serlo: revisa cada año si sus márgenes y su cuota aguantan."),
            (1, "Regulación e impuestos", ("Le afectan " + ref[4] + ".") if ref else "Cambios regulatorios pueden alterar su rentabilidad."),
            (1, "Previsiones que no se cumplen", "Los escenarios se apoyan en estimaciones de analistas, que suelen pecar de optimistas."),
        ]
        vistos = {x[1] for x in r}
        for gen in genericos:
            if len(r) >= 4:
                break
            if gen[1] not in vistos:
                r.append(gen)
    # --- el escenario concreto en que sale muy mal
    graves = [x for x in r if x[0] == 2] or r[:2]
    baj = next((e for e in esc.get("escenarios", []) if e["nombre"].startswith("🔴")), None)
    if len(graves) >= 2:
        desastre = "Sale muy mal si coinciden dos cosas: " + " y ".join(x[1].lower() for x in graves[:2]) + "."
    else:
        desastre = "Sale muy mal si se confirma este riesgo: " + graves[0][1].lower() + "."
    if baj:
        desastre += (f" En ese caso el precio razonable baja hacia {_n(baj['bajo'], 0 if baj['bajo'] > 20 else 2)}–{_n(baj['alto'], 0 if baj['alto'] > 20 else 2)} "
                     f"({_pct(baj['rent_total'], 0, True)} con dividendos)")
        if tec and _ok(tec.get("caida_max_5a")):
            desastre += f"; y no es teoría: en los últimos años ya ha llegado a caer un {_pct(abs(tec['caida_max_5a']))} desde máximos."
        else:
            desastre += "."
    return {"lista": [{"severidad": s, "titulo": t, "texto": x} for s, t, x in r], "desastre": desastre}


# ----------------------------------------------------------------------------- 5. catalizadores
_CLAVES_CATALIZADOR = [
    ("Contrato o pedido", ("contrato", "adjudic", "pedido", "contract", "order", "awarded", "deal", "acuerdo", "agreement", "partnership", "alianza"), 1),
    ("Nuevo producto o expansión", ("lanza", "launch", "nuevo", "new ", "unveil", "presenta", "expansi", "fábrica", "factory", "planta", "plant", "inaugura", "opens"), 1),
    ("Mejora de previsiones", ("eleva", "raises", "mejora sus previsiones", "upgrade", "guidance", "beat", "supera", "récord", "record"), 1),
    ("Compra o fusión", ("opa", "compra de", "adquisic", "acquisition", "acquire", "merger", "fusión", "takeover"), 1),
    ("Recompra o dividendo", ("recompra", "buyback", "dividendo", "dividend"), 1),
    ("Regulación o litigio", ("multa", "sanci", "investigaci", "demanda", "lawsuit", "probe", "fine", "antitrust", "ban", "veto", "arancel", "tariff", "restricci"), -1),
    ("Rebaja o recorte", ("rebaja", "downgrade", "recorta", "cuts", "profit warning", "despidos", "layoffs", "retraso", "delay", "recall"), -1),
]


def clasificar_titular(titulo: str) -> tuple[str, int] | None:
    t = titulo.lower()
    for nombre, claves, signo in _CLAVES_CATALIZADOR:
        if any(k in t for k in claves):
            return nombre, signo
    return None


def catalizadores(m: dict, cal: dict, sector: str | None, seg: dict | None, agenda: pd.DataFrame | None, tec: dict,
                  noticias: list[dict] | None, sector_rel: float | None = None, clientes: list[str] | None = None) -> list[dict]:
    """Lista de catalizadores con probabilidad e impacto. Sale de datos (agenda, previsiones, titulares, ciclo), no de opinión."""
    ref = SECTORES.get(sector or "")
    c = []
    if agenda is not None and not agenda.empty:
        res = agenda[agenda["Evento"].str.contains("Resultados")]
        if len(res):
            f = res.iloc[0]
            mov = tec.get("resultados", {}).get("media_abs") if tec else None
            c.append({"tipo": "Resultados", "signo": 0, "prob": "alta", "impacto": "alto" if (_ok(mov) and mov > 0.05) else "medio",
                      "texto": f"Presenta resultados el {f['Fecha']:%d/%m/%Y} (en {int(f['Faltan (días)'])} días)."
                      + (f" Ese día suele moverse ±{_pct(mov, 1)}." if _ok(mov) else "")
                      + " Es el momento en que se confirman o se rompen las previsiones."})
    g = m.get("prev_crec_anio_sig")
    if _ok(g) and g >= 0.10:
        c.append({"tipo": "Crecimiento previsto", "signo": 1, "prob": "media", "impacto": "alto" if g >= 0.25 else "medio",
                  "texto": f"Los analistas esperan que el beneficio por acción crezca un {_pct(g, 0)} el próximo ejercicio"
                  + (f" y los ingresos un {_pct(m['prev_crec_ingresos_sig'], 0)}" if _ok(m.get("prev_crec_ingresos_sig")) else "")
                  + ". Probabilidad media: las previsiones a un año se incumplen a menudo."})
    elif _ok(g) and g < -0.05:
        c.append({"tipo": "Beneficio a la baja", "signo": -1, "prob": "media", "impacto": "medio",
                  "texto": f"Se espera que el beneficio por acción caiga un {_pct(abs(g), 0)} el próximo ejercicio."})
    if seg and seg.get("ejes"):
        from .negocio import principal

        p = principal(seg)
        if p:
            texto = f"Su negocio principal es «{p[0]}» ({p[1]:.0f} % de los ingresos): lo que pase con esa demanda manda sobre todo lo demás."
            if clientes:
                texto += " Vigila la inversión que anuncien sus mayores clientes: " + ", ".join(clientes[:5]) + "."
            c.append({"tipo": "Demanda de su negocio principal", "signo": 0, "prob": "alta", "impacto": "alto", "texto": texto})
    if _ok(sector_rel):
        fase = ("en fase fuerte: el sector lo hace mejor que el mercado" if sector_rel > 0.03 else
                "en fase débil: el sector lo hace peor que el mercado" if sector_rel < -0.03 else "sin tendencia frente al mercado")
        c.append({"tipo": "Ciclo del sector", "signo": 1 if sector_rel > 0.03 else -1 if sector_rel < -0.03 else 0, "prob": "media",
                  "impacto": "medio", "texto": f"Ciclo sectorial {fase} ({_pct(sector_rel, 1, True)} frente al S&P 500 en el último mes)."})
    if ref:
        c.append({"tipo": "Macro", "signo": 0, "prob": "media", "impacto": "medio",
                  "texto": f"Tendencias macro a vigilar en su sector: {ref[4]}. Pueden jugar a favor o en contra."})
    obj, precio = m.get("obj_medio"), m.get("precio")
    if _ok(obj) and _ok(precio) and m.get("n_analistas"):
        pot = obj / precio - 1
        c.append({"tipo": "Consenso de analistas", "signo": 1 if pot > 0.1 else -1 if pot < -0.05 else 0, "prob": "media", "impacto": "bajo",
                  "texto": f"{int(m['n_analistas'])} analistas le dan un precio objetivo medio un {_pct(pot, 0, True)} respecto al actual. "
                           "Sirve como termómetro de expectativas, no como predicción: suelen ir por detrás del precio."})
    vistos = set()
    for n in (noticias or []):
        cl = clasificar_titular(n["titulo"])
        if not cl or cl[0] in vistos:
            continue
        vistos.add(cl[0])
        c.append({"tipo": cl[0], "signo": cl[1], "prob": "media", "impacto": "medio", "texto": f"En las noticias: «{n['titulo']}» ({n.get('fuente', '')}).",
                  "enlace": n.get("enlace")})
        if len(vistos) >= 4:
            break
    return c


# ----------------------------------------------------------------------------- 9-10. veredicto y recomendación
def recomendacion(m: dict, cal: dict, esc: dict, tec: dict, trampa: list[str], rie: dict, en_cartera: bool = False) -> dict:
    precio = m.get("precio")
    base = next((e for e in esc.get("escenarios", []) if e["nombre"].startswith("🔵")), None)
    baj = next((e for e in esc.get("escenarios", []) if e["nombre"].startswith("🔴")), None)
    alc = next((e for e in esc.get("escenarios", []) if e["nombre"].startswith("🟢")), None)
    por_valoracion = "Múltiplos" in esc.get("metodo", "")
    graves = sum(1 for x in rie["lista"] if x["severidad"] == 2)
    if base is None:
        return {"etiqueta": "🟡 MANTENER", "color": "amarillo", "titulo": "MANTENER" if en_cartera else "ESPERAR",
                "texto": "No hay datos suficientes para valorar la empresa con rigor. Sin poder estimar cuánto vale, lo prudente es no comprar a ciegas.",
                "entrada": None, "precio_juicio": "sin valorar"}
    rb, rp = base["rent_total"], (baj["rent_total"] if baj else -0.3)
    exigido = 0.15 if cal["media"] >= 1.2 else 0.25 if cal["media"] >= 0.8 else 0.40
    exigido += 0.05 * max(0, graves - 1)
    if rb >= exigido + 0.10:
        juicio = "atractivo"
    elif rb >= 0.05:
        juicio = "justo"
    else:
        juicio = "caro"
    entrada = base["centro"] * (1 + esc.get("dividendo_periodo", 0)) / (1 + exigido)
    comprar = (por_valoracion and rb >= exigido and rb >= 0.6 * abs(min(rp, 0)) and not trampa and rp > -0.40 and cal["media"] >= 0.8
               and "previsto por analistas" not in esc.get("metodo", ""))
    evitar = (rb < -0.08) or (rb < 0 and cal["media"] < 0.8) or bool(trampa and cal["media"] < 1.2) or \
        (cal["media"] < 0.8 and rb < 0.20) or (rp < -0.50 and rb < 0.15)
    bajista_fuerte = tec.get("tendencia") == "bajista" and _ok(tec.get("vs_m200")) and tec["vs_m200"] < -0.15
    mon = m.get("moneda", "")
    dec = 0 if (precio or 0) > 20 else 2
    if comprar:
        etiqueta, color, titulo = "🟢 COMPRAR", "verde", "COMPRAR"
        texto = (f"El escenario base deja un {_pct(rb, 0, True)} en 12-18 meses (dividendos incluidos) con un negocio de calidad "
                 f"{cal['etiqueta'].lower()}, y exijo un {_pct(exigido, 0)} para comprar una empresa así. "
                 f"Si sale mal, la pérdida estimada es del {_pct(abs(rp), 0)}: asumible si el peso en cartera es moderado.")
        if bajista_fuerte:
            texto += " La tendencia es bajista: mejor entrar por partes que de golpe."
        if graves >= 2:
            texto += f" Tiene {graves} riesgos graves: no la conviertas en una posición grande."
    elif evitar:
        etiqueta, color = "🔴 VENDER / EVITAR", "rojo"
        titulo = "CONSIDERAR REDUCIR" if en_cartera else "EVITAR"
        motivo = ("el escenario más probable ya da una rentabilidad claramente negativa" if rb < -0.08 else
                  "el escenario más probable ya da rentabilidad negativa y el negocio no es de calidad" if rb < 0 else
                  "tiene señales de trampa de valor (" + "; ".join(trampa[:2]) + ")" if trampa else
                  "la calidad del negocio es baja y el precio no compensa" if cal["media"] < 0.8 else
                  "lo que puedes perder es mucho mayor que lo que puedes ganar")
        texto = (f"Al precio actual los riesgos pesan más que las oportunidades: {motivo}. "
                 f"Escenario base {_pct(rb, 0, True)}, pesimista {_pct(rp, 0, True)}. "
                 + ("Si ya la tienes, plantéate reducir en los rebotes en vez de añadir." if en_cartera else
                    f"Solo empezaría a tener sentido por debajo de {_n(entrada, dec)} {mon}."))
    else:
        etiqueta, color = "🟡 MANTENER", "amarillo"
        titulo = "MANTENER" if en_cartera else "ESPERAR MEJOR PRECIO"
        texto = (f"El escenario base da un {_pct(rb, 0, True)} en 12-18 meses y, para una empresa de calidad {cal['etiqueta'].lower()}, "
                 f"pido al menos un {_pct(exigido, 0)} para tener margen de seguridad. "
                 + ("Si ya la tienes, no hay motivo para vender, pero tampoco para comprar más a este precio. " if en_cartera else
                    "No es mala empresa ni está disparatada de precio: simplemente no hay colchón si algo falla. ")
                 + f"Precio de entrada sugerido: **{_n(entrada, dec)} {mon}** o menos (un {_pct(abs(entrada / precio - 1), 0)} por debajo del actual).")
        if not por_valoracion:
            texto = ("No se puede valorar por beneficios (no los tiene o no son representativos), así que no hay forma honesta de decir que está "
                     "barata. " + ("Si ya la tienes, mantén solo lo que estés dispuesto a ver caer mucho." if en_cartera else
                                  "Sin margen de seguridad medible, lo prudente es esperar o limitarlo a una apuesta pequeña."))
            entrada = None
    return {"etiqueta": etiqueta, "color": color, "titulo": titulo, "texto": texto, "entrada": None if (comprar or not por_valoracion) else entrada,
            "precio_juicio": juicio, "rent_base": rb, "rent_pesimista": rp, "rent_optimista": alc["rent_total"] if alc else None,
            "exigido": exigido}


def veredicto(nombre: str, m: dict, cal: dict, est: dict, rec: dict, tec: dict, d: dict, rie: dict, cat: list[dict]) -> str:
    """3-4 frases directas: para quién, precio y qué hay de especial ahora."""
    if est["mejor"] == "dividendos" and est["dividendos"] >= 3:
        perfil = "para quien busca rentas periódicas y acepta que el precio se mueva poco"
    elif est["crecimiento"] >= 4:
        perfil = "para quien busca revalorización, puede esperar 3-5 años y aguanta caídas fuertes por el camino"
    elif cal["media"] >= 1.2:
        perfil = "para un inversor de largo plazo que quiere calidad antes que emociones"
    else:
        perfil = "solo para quien entienda bien el negocio y esté dispuesto a vigilarlo de cerca"
    f1 = f"{nombre} encaja {perfil}."
    f2 = {"atractivo": "El precio actual es **atractivo**: hay margen de seguridad aunque las previsiones se cumplan solo en parte.",
          "justo": "El precio actual es **justo**: pagas más o menos lo que vale, sin descuento que te proteja si algo falla.",
          "caro": "El precio actual es **caro**: ya descuenta un futuro muy bueno y deja poco que ganar.",
          "sin valorar": "No se puede decir si está cara o barata con los datos disponibles."}[rec["precio_juicio"]]
    if cal["etiqueta"] in ("Excelente", "Buena") and rec["precio_juicio"] == "caro":
        f2 += " Buena empresa no es lo mismo que buena compra."
    if cal["etiqueta"] == "Mediocre" and rec["precio_juicio"] == "atractivo":
        f2 += " Que esté barata no la convierte en buena: comprueba que no es una trampa."
    especial = []
    res = next((c for c in cat if c["tipo"] == "Resultados"), None)
    if res and "(en " in res["texto"]:
        try:
            dias = int(res["texto"].split("(en ")[1].split(" ")[0])
            if dias <= 21:
                especial.append(f"presenta resultados en {dias} días, así que el precio puede dar un salto en cualquier dirección")
        except (ValueError, IndexError):
            pass
    if tec and tec.get("pos52") is not None:
        if tec["pos52"] > 0.93:
            especial.append("cotiza pegada a sus máximos del año")
        elif tec["pos52"] < 0.10:
            especial.append("cotiza pegada a sus mínimos del año")
    graves = [x["titulo"].lower() for x in rie["lista"] if x["severidad"] == 2]
    if graves:
        especial.append("el riesgo que más pesa es " + graves[0])
    f3 = ("Ahora mismo, lo relevante: " + "; ".join(especial[:3]) + ".") if especial else "No veo nada excepcional en este momento concreto."
    return " ".join([f1, f2, f3])


# ----------------------------------------------------------------------------- 11. resumen para no financieros
def resumen_llano(nombre: str, m: dict, cal: dict, est: dict, rec: dict, d: dict, rie: dict, seg: dict | None, esc: dict) -> str:
    from .negocio import principal

    p = principal(seg) if seg else None
    dy, per = m.get("div_yield"), m.get("per")
    base = next((e for e in esc.get("escenarios", []) if e["nombre"].startswith("🔵")), None)
    frases = []
    # 1) qué es, con una imagen cotidiana
    if cal["media"] < 0.8:
        frases.append(f"{nombre} es como un bar que ha cambiado tres veces de dueño: puede remontar, pero hoy los números no convencen.")
    elif est["mejor"] == "dividendos" and _ok(dy) and dy >= 0.03 and est["crecimiento"] <= 3:
        frases.append(f"{nombre} es como un piso alquilado a un inquilino formal: no te va a hacer rico, pero te paga "
                      f"en torno a un {_pct(dy, 0)} al año mientras el negocio aguante.")
    elif est["crecimiento"] >= 4 and cal["media"] >= 1.2:
        frases.append(f"{nombre} es como el restaurante de moda con cola en la puerta: el negocio va como un tiro"
                      + (f" (casi todo gracias a «{p[0]}»)" if p and p[1] >= 60 else "") + ", y la pregunta no es si es bueno, sino cuánto pagas por entrar.")
    elif cal["media"] >= 1.2:
        frases.append(f"{nombre} es como una buena ferretería de barrio: negocio sólido, que gana dinero todos los años y sin fuegos artificiales"
                      + (", aunque vende más cuando a la gente le sobra el dinero." if cal.get("ciclo") == "alto" else "."))
    else:
        frases.append(f"{nombre} es como un chiringuito de playa: en verano gana mucho y en invierno muy poco. "
                      "Sus beneficios suben y bajan con su ciclo, y lo importante es no comprarla en pleno agosto." if cal.get("ciclo") == "alto" else
                      f"{nombre} es como una tienda de toda la vida: funciona, pero ni crece mucho ni tiene nada que la proteja de la competencia.")
    # 2) precio
    if rec["precio_juicio"] == "caro":
        frases.append("Hoy está cara: pagas por adelantado varios años buenos, y si alguno sale regular el precio lo notará.")
    elif rec["precio_juicio"] == "atractivo":
        frases.append("Hoy está a buen precio: aunque las cosas salgan solo medio bien, hay margen para ganar.")
    elif rec["precio_juicio"] == "justo":
        frases.append("Hoy cuesta más o menos lo que vale: ni ganga ni disparate.")
    # 3) lo que se puede ganar y perder
    if base and _ok(rec.get("rent_pesimista")):
        frases.append(f"Con 1.000 € y año y medio de paciencia, lo normal sería acabar cerca de {_n(1000 * (1 + rec['rent_base']), 0)} €; "
                      f"si se tuerce, cerca de {_n(1000 * (1 + rec['rent_pesimista']), 0)} €.")
    # 4) el riesgo, uno solo y claro
    graves = [x for x in rie["lista"] if x["severidad"] == 2] or rie["lista"][:1]
    if graves:
        detalle = graves[0]["texto"].split(". ")[0].rstrip(". ")
        frases.append("El riesgo que de verdad importa: " + graves[0]["titulo"].lower() + ". " + detalle + ".")
    # 5) qué hacer
    que_hacer = {"COMPRAR": "¿Merece la pena? Sí, con una parte moderada de tus ahorros y sin prisa por vender.",
                 "ESPERAR MEJOR PRECIO": "¿Merece la pena? Todavía no: buena candidata para apuntar en la lista y esperar a que baje.",
                 "MANTENER": "Si ya la tienes, quédate como estás: ni vender ni comprar más.",
                 "EVITAR": "¿Merece la pena? Ahora no: hay sitios mejores donde poner el dinero.",
                 "CONSIDERAR REDUCIR": "Si ya la tienes, piensa en ir soltando parte cuando rebote.",
                 "ESPERAR": "Sin datos para valorarla, mejor no meterse."}.get(rec["titulo"], "")
    if rec.get("entrada") and rec["titulo"] == "ESPERAR MEJOR PRECIO":
        que_hacer = que_hacer[:-1] + f" (por debajo de {_n(rec['entrada'], 0 if rec['entrada'] > 20 else 2)} {m.get('moneda', '')} empieza a interesar)."
    frases.append(que_hacer)
    texto = " ".join(f for f in frases if f)
    if d["veredicto"] == "Muy apta" and rec["titulo"] in ("COMPRAR", "MANTENER"):
        texto += " Si prefieres ir comprando un poco cada mes, tiene sentido: se mueve bastante pero el negocio aguanta, y cada bajada abarata tu precio medio."
    elif d["veredicto"] == "Muy apta" and rec["titulo"] == "ESPERAR MEJOR PRECIO":
        texto += " Si prefieres ir comprando un poco cada mes en vez de esperar, es de las que lo admiten: el negocio aguanta y las bajadas abaratan tu precio medio."
    elif d["veredicto"] == "Apta con condiciones" and rec["titulo"] not in ("EVITAR", "CONSIDERAR REDUCIR"):
        texto += " Comprar un poco cada mes puede valer, pero ponte un tope total y revisa una vez al año que el negocio sigue sano."
    return texto


# ----------------------------------------------------------------------------- análisis completo
def completo(nombre: str, m: dict, h: pd.DataFrame, *, sector: str | None = None, industria: str | None = None,
             comparables: list[dict] | None = None, seg: dict | None = None, clientes: list[str] | None = None,
             proveedores: list[str] | None = None, agenda: pd.DataFrame | None = None, reaccion: pd.DataFrame | None = None,
             noticias: list[dict] | None = None, estadistico: dict | None = None, sector_rel: float | None = None,
             per_etf: float | None = None, en_cartera: bool = False, moneda_usuario: str = "EUR") -> dict:
    """Ejecuta las once secciones en orden y devuelve todo junto."""
    comparables = comparables or []
    tec = tecnico(h, reaccion)
    cal = calidad(m, sector, industria, seg, len(clientes) if clientes else None)
    trampa = senales_trampa(m, cal)
    d = dca(m, tec, cal, trampa)
    est = estrellas(m, cal, tec, d)
    esc = escenarios_precio(m, cal, sector, estadistico)
    neg = [n for n in (noticias or []) if (clasificar_titular(n["titulo"]) or ("", 0))[1] < 0]
    rie = riesgos(m, cal, tec, sector, seg, esc, trampa, proveedores, neg, moneda_usuario)
    cat = catalizadores(m, cal, sector, seg, agenda, tec, noticias, sector_rel, clientes)
    rec = recomendacion(m, cal, esc, tec, trampa, rie, en_cartera)
    return {"nombre": nombre, "metricas": tarjetas(m, comparables, sector, per_etf), "calidad": cal, "estrellas": est, "dca": d,
            "catalizadores": cat, "tecnico": tec, "escenarios": esc, "riesgos": rie, "recomendacion": rec,
            "veredicto": veredicto(nombre, m, cal, est, rec, tec, d, rie, cat),
            "resumen": resumen_llano(nombre, m, cal, est, rec, d, rie, seg, esc), "trampa": trampa, "sector": sector,
            "aviso": AVISO_LEGAL}


def texto_para_ia(an: dict, m: dict, instrucciones: str = "") -> str:
    """Todos los datos del análisis en texto, para pegarlos en un asistente de IA y que redacte su propia versión."""
    L = []
    if instrucciones:
        L += [instrucciones.strip(), "", "---", ""]
    L += [f"# Datos de {an['nombre']} ({m.get('ticker', '')}) recogidos por Radar Inversor el {pd.Timestamp.today():%d/%m/%Y}", "",
          f"Precio: {_n(m.get('precio'), 2)} {m.get('moneda', '')} · Capitalización: {_n((m.get('cap') or 0) / 1e9, 1)} mil M {m.get('moneda_base', '')} "
          f"· Sector: {SECTOR_ES.get(an.get('sector') or '', an.get('sector') or 's/d')}", "", "## Métricas (valor · su historia · competidores · sector · fuente)"]
    for t in an["metricas"]:
        L.append(f"- {t['nombre']}: {formato(t['valor'], t['fmt'])} · historia {formato(t['historia'], t['fmt'])} · competidores "
                 f"{formato(t['competidores'], t['fmt'])} · sector {formato(t['sector'], t['fmt'])} · {t['fuente']}")
    a = m.get("anual")
    if a is not None and not a.empty:
        L += ["", "## Histórico anual"]
        for fecha, f in a.iterrows():
            L.append(f"- {fecha:%Y}: ingresos {_n(f['ingresos'] / 1e9, 2)} mil M, beneficio {_n(f['neto'] / 1e9, 2)} mil M, margen operativo "
                     f"{_pct(f['margen_op'])}, ROIC {_pct(f['roic'])}, FCF {_n((f['fcf'] or 0) / 1e9, 2)} mil M, PER al cierre {_n(f['per'])}")
    L += ["", f"## Calidad del negocio: {an['calidad']['etiqueta']}"] + [f"- {c['criterio']}: {c['texto']}" for c in an["calidad"]["criterios"]]
    L += ["", "## Escenarios a 12-18 meses (" + an["escenarios"].get("metodo", "") + ")"]
    for e in an["escenarios"].get("escenarios", []):
        L.append(f"- {e['nombre']}: {_n(e['bajo'], 2)}–{_n(e['alto'], 2)} ({_pct(e['rent_total'], 0, True)} con dividendos). {e['condiciones']}")
    L += [f"- Supuesto: {s}" for s in an["escenarios"].get("supuestos", [])]
    if an["escenarios"].get("analistas"):
        x = an["escenarios"]["analistas"]
        L.append(f"- Analistas: objetivo bajo {_n(x['bajo'], 2)}, medio {_n(x['medio'], 2)}, alto {_n(x['alto'], 2)}")
    L += ["", "## Riesgos"] + [f"- [{'alto' if r['severidad'] == 2 else 'medio'}] {r['titulo']}: {r['texto']}" for r in an["riesgos"]["lista"]]
    L += ["", "## Catalizadores"] + [f"- {c['tipo']} (prob. {c['prob']}, impacto {c['impacto']}): {c['texto']}" for c in an["catalizadores"]]
    t = an["tecnico"]
    if t:
        L += ["", "## Técnico", f"- Tendencia {t['tendencia']}; a {_pct(t['desde_max'], 0, True)} del máximo de 52 semanas; "
              f"4 semanas {_pct(t.get('r4'), 0, True)}, 8 semanas {_pct(t.get('r8'), 0, True)}; volatilidad anual {_pct(t['vol_anual'])}"]
    L += ["", f"## Conclusión automática del programa: {an['recomendacion']['etiqueta']} — {an['recomendacion']['texto']}"]
    return "\n".join(L)
