"""Pruebas sin conexión de las piezas nuevas (python -m pytest tests)."""
import os
import tempfile

os.environ.setdefault("RADAR_DIR", tempfile.mkdtemp())

from radar import actualizador, analisis, conexiones, negocio, noticias  # noqa: E402


def test_filtro_noticias():
    assert not noticias.es_financiera("Rodri gana el Balón de Oro", "Marca")
    assert not noticias.es_financiera("El Racing de Santander gana 2-0", "El Diario Montañés", estricto=False)
    assert noticias.es_financiera("El oro marca un nuevo máximo histórico", "Expansión")
    assert noticias.es_financiera("Nvidia presenta su nuevo chip", "Xataka", estricto=False)
    assert noticias.consulta_para("Oro")[1] and "precio del oro" in noticias.consulta_para("oro")[0]


def test_versiones():
    assert actualizador.es_mas_nueva("2.1.0", "2.0.9") and actualizador.es_mas_nueva("2.10", "2.9")
    assert not actualizador.es_mas_nueva("2.0.0", "2.0.0")


def test_base_coherente():
    empresas, rel = conexiones.cargar_base()
    ids = set(empresas["id"])
    assert not empresas["id"].duplicated().any()
    assert set(rel["proveedor"]) <= ids and set(rel["cliente"]) <= ids
    seg = negocio.segmentos_base("nvidia")
    assert abs(seg["negocio"]["pct"].sum() - 100) < 3
    cli = negocio.clientes_con_finalidad(conexiones.unificar(None, None), "NVIDIA")
    assert len(cli) > 15 and (cli["Para qué"] != "").sum() > 10


def test_nombres_y_redondeo():
    assert negocio.nombre_miembro("nvda:DataCenterMember") == "Centros de datos"
    assert negocio.nombre_miembro("country:US") == "Estados Unidos"
    assert analisis.redondo(283.4) in (280, 285, 290)


def test_jerarquia_segmentos():
    t = negocio._jerarquia({"a:DataCenterMember": 90.0, "a:ComputeMember": 75.0, "a:NetworkingMember": 15.0, "a:GamingMember": 10.0}, 100.0)
    assert list(t["segmento"]) == ["Centros de datos", "↳ Computación", "↳ Redes", "Videojuegos"]
    seg = {"ejes": {"producto": t}, "oficial": True}
    assert negocio.principal(seg) == ("Centros de datos", 90.0)


def test_max_dolor_y_exportar():
    import pandas as pd
    from radar import vistas2

    calls = pd.DataFrame({"strike": [90, 100, 110], "openInterest": [10, 50, 10]})
    puts = pd.DataFrame({"strike": [90, 100, 110], "openInterest": [10, 50, 10]})
    assert vistas2._max_dolor(calls, puts) == 100


def test_buscador_en_la_base():
    from radar import datos

    assert datos._en_la_base("microsft")[0]["symbol"] == "MSFT"
    assert datos._en_la_base("accenture")[0]["symbol"] == "ACN"
    assert datos._en_la_base("airbus")[0]["symbol"] == "AIR.PA"


def test_lectura_picks():
    import pandas as pd
    from radar import picks

    f = {"n": 8, "n_bate": 8, "n_falla": 0, "bate_sube": 3, "bate_media": -0.01, "falla_sube": 0, "falla_media": None, "sube": 3,
         "media": -0.01, "media_abs": 0.05, "peor": -0.09, "mejor": 0.08, "implicito": 0.08, "mes": 0.15, "pos52": 0.95}
    l = picks.lectura(f, {"bpa_esperado": 2.0, "bpa_hace_un_anio": 1.0, "mio": True, "cap": 5e11})
    assert "Batir no le basta" in l["si_bate"] and "no ha fallado" in l["si_falla"]
    assert l["nivel"] == "alto" and any("vender con la noticia" in a for a in l["avisos"])
    assert picks._numero("$1,234.5") == 1234.5 and picks._numero("($0.44)") == -0.44


def test_entrada_nunca_por_encima_del_precio():
    cal_mala, cal_buena = {"media": 0.75, "etiqueta": "Mediocre"}, {"media": 1.4, "etiqueta": "Buena"}
    esc = {"metodo": "Múltiplos (PER)", "dividendo_periodo": 0.0, "escenarios": [
        {"nombre": "🟢 Optimista", "centro": 300.0, "rent_total": 1.5}, {"nombre": "🔵 Base (más probable)", "centro": 170.0, "rent_total": 0.44},
        {"nombre": "🔴 Pesimista", "centro": 95.0, "rent_total": -0.19}]}
    m = {"precio": 118.0, "moneda": "USD"}
    r = analisis.recomendacion(m, cal_mala, esc, {}, [], {"lista": []})
    assert r["entrada"] is None and r["titulo"] == "SOLO COMO APUESTA PEQUEÑA"
    r = analisis.recomendacion(m, cal_buena, esc, {}, [], {"lista": []})
    assert r["titulo"] == "COMPRAR"
    esc["escenarios"][1].update(centro=125.0, rent_total=0.06)
    r = analisis.recomendacion(m, cal_buena, esc, {}, [], {"lista": []})
    assert r["titulo"] == "ESPERAR MEJOR PRECIO" and r["entrada"] < 118.0


def test_cripto_sin_conexion():
    import numpy as np
    import pandas as pd
    from radar import cripto
    idx = pd.date_range("2018-01-01", periods=3000, freq="D")
    s = pd.Series(100 * np.exp(np.cumsum(np.random.default_rng(1).normal(0.0005, 0.04, 3000))), index=idx)
    btc = {"id": "bitcoin", "nombre": "Bitcoin", "simbolo": "BTC", "puesto": 1, "precio": float(s.iloc[-1]), "cap": 1e12, "volumen": 3e10,
           "circulante": 20e6, "oferta_max": 21e6, "oferta_total": 20e6, "desde_maximo": -0.4, "fecha_maximo": "2025-10-06",
           "fecha_minimo": "2013-07-05", "cambio_7d": -0.02, "cambio_30d": -0.1, "cambio_1a": -0.2}
    btc["tipo"] = cripto.tipo_de(btc)
    a = cripto.completo(btc, s, s, {"miedo": 30})
    assert btc["tipo"] == "reserva" and a["solidez"]["puntos"] >= 9 and a["recomendacion"]["color"] in ("verde", "amarillo")
    assert a["rangos"]["bajo"] < btc["precio"] < a["rangos"]["alto"] and len(a["plazos"]) == 3
    usdt = {**btc, "id": "tether", "nombre": "Tether", "cambio_7d": 0.0, "cambio_30d": 0.001, "cambio_1a": 0.0}
    assert cripto.tipo_de(usdt) == "estable"
    meme = {**btc, "id": "pepe", "nombre": "Pepe", "puesto": 45, "oferta_max": None}
    meme["tipo"] = cripto.tipo_de(meme)
    assert cripto.completo(meme, s.tail(300), s, {})["recomendacion"]["color"] != "verde"


def test_empresa_sin_beneficios_se_valora_por_ventas():
    m = {"precio": 50.0, "p_ventas": 40.0, "per": None, "per_fwd": None, "neto": -2e8, "fcf": -1e8, "crec_ingresos_3a": 0.45,
         "prev_crec_ingresos_sig": 0.40, "moneda": "USD"}
    esc = analisis.escenarios_precio(m, {"etiqueta": "Mediocre", "puntos": 5}, None, None)
    assert esc.get("tipo") == "ventas" and len(esc["escenarios"]) == 3


def test_reparto_del_plan():
    from radar import plan

    def activo(nombre, euros, rol, accion, nota, clase="accion", tengo=0):
        return {"nombre": nombre, "escrito": nombre, "ticker": nombre, "clase": clase, "rol": rol, "accion": accion, "nota": nota,
                "euros": euros, "tengo": tengo, "motivo": "motivo de prueba.", "detalle": "", "sector": "Tecnología", "divisa": "USD"}
    act = [activo("Fondo", 200, "base", "seguir", 85, "fondo"), activo("Buena", 100, "estable", "seguir", 80),
           activo("Cara", 50, "valor", "pausar", 60), activo("Cohete", 100, "explosivo", "poco", 40), activo("Rara", 10, "desconocido", "seguir_sin_subir", 30)]
    rep, sin = plan.reparto(act)
    por = {r["nombre"]: r for r in rep}
    assert abs(sum(r["sugerido"] for r in rep) + sin - 460) < 1
    assert por["Cara"]["sugerido"] == 0 and por["Fondo"]["sugerido"] >= 200 and por["Cohete"]["sugerido"] < 100 and por["Rara"]["sugerido"] == 10
    solo, resto = plan.reparto([activo("Cara", 100, "valor", "pausar", 60), activo("Cohete", 100, "explosivo", "poco", 40)])
    assert resto > 0 and all(r["sugerido"] <= r["euros"] for r in solo)
    assert plan.flaquezas(act) and len(plan.proyeccion(act)) == 3
    # el perfil de riesgo cambia el juicio: lo mismo es demasiado especulativo para un perfil bajo y aceptable para uno alto
    mixta = [activo("Buena", 100, "estable", "seguir", 80), activo("Otra", 100, "dividendos", "seguir", 70), activo("Cohete", 60, "explosivo", "poco", 40)]
    titulos = lambda perfil: " ".join(f["titulo"] for f in plan.flaquezas(mixta, perfil))  # noqa: E731
    assert "especulativo" in titulos("Bajo") and "especulativo" not in titulos("Alto")
    # no tener fondo indexado ya no es un punto débil; el fondo va en un apartado aparte
    assert "base diversificada" not in titulos("Medio") and plan.fondo_complementario(mixta)["encajan"]
    # lo que ya tienes cuenta: una posición enorme recibe menos aportación aunque sea buena
    grande = [activo("Enorme", 100, "estable", "seguir", 80, tengo=20000), activo("Nueva", 100, "estable", "seguir", 80), activo("Tercera", 100, "valor", "seguir", 70),
              activo("Cuarta", 100, "dividendos", "seguir", 70)]
    r2 = {r["nombre"]: r for r in plan.reparto(grande)[0]}
    assert r2["Enorme"]["sugerido"] < 100 < r2["Nueva"]["sugerido"]
    import pandas as pd
    limpio = plan.limpiar(pd.DataFrame({"activo": ["A", "B", "", "C"], "euros": [10, None, 5, 0], "tengo": [None, 300, 1, 0], "tipo": ["", "", "", ""]}))
    assert list(limpio["activo"]) == ["A", "B"] and limpio["tengo"].tolist() == [0, 300]
