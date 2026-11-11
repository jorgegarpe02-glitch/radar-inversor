"""Comprueba qué fuentes de datos responden desde tu ordenador:  python comprobar_conexion.py"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from radar import datos, energia, mundo, noticias, suministro  # noqa: E402

PRUEBAS = [
    ("Yahoo Finance · buscador", lambda: datos.buscar.sin_cache("Apple")),
    ("Yahoo Finance · precios", lambda: datos.historial.sin_cache("AAPL", "1mo")),
    ("Yahoo Finance · ficha", lambda: datos.ficha.sin_cache("AAPL")),
    ("Yahoo Finance · termómetro", lambda: datos.termometro.sin_cache()),
    ("Wikipedia · componentes del S&P 500", lambda: datos._constituyentes.sin_cache("S&P 500")),
    ("Wikipedia · componentes del IBEX 35", lambda: datos._constituyentes.sin_cache("IBEX 35")),
    ("Google News · titulares", lambda: noticias.buscar.sin_cache("petróleo")),
    ("SEC EDGAR · tabla de tickers", lambda: suministro.tabla_tickers_sec.sin_cache()),
    ("Yahoo · empresas similares", lambda: suministro.similares.sin_cache("NVDA")),
    ("FMI PortWatch · estrechos", lambda: energia.estrechos.sin_cache()),
    ("FMI PortWatch · tráfico diario", lambda: energia.pasos_diarios.sin_cache(("chokepoint6",), 30)),
    ("FMI / Banco Mundial · economía por país", lambda: mundo.economia()[0]),
    ("GDACS · alertas de desastres", lambda: mundo.alertas.sin_cache()),
    ("FMI PortWatch · petroleros por puerto", lambda: mundo.petroleros_por_puerto.sin_cache(7)),
    ("FMI PortWatch · rutas marítimas", lambda: mundo.rutas_maritimas.sin_cache()[0]),
    ("Wikidata · minas de cobre", lambda: mundo.minas_wikidata.sin_cache("cobre")),
    ("WRI · centrales eléctricas del mundo", lambda: mundo.centrales_mundo()),
    ("OpenStreetMap · refinerías de Madrid", lambda: energia.activos.sin_cache("Refinerías", (39.9, -4.0, 40.6, -3.0))),
]

if __name__ == "__main__":
    fallos = 0
    for nombre, prueba in PRUEBAS:
        t0 = time.time()
        try:
            r = prueba()
            n = len(r) if hasattr(r, "__len__") else 1
            print(f"✅ {nombre:<42} {n:>6} filas  ({time.time() - t0:.1f}s)")
        except Exception as e:  # noqa: BLE001
            fallos += 1
            print(f"❌ {nombre:<42} {type(e).__name__}: {str(e)[:90]}")
    print("\nTodo correcto." if not fallos else f"\n{fallos} fuente(s) sin respuesta. Si es puntual, vuelve a probar en unos minutos.")
