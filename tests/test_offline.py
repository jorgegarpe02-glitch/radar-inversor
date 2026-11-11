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
