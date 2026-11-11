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
