"""Revisa tus alertas y avisa con una notificación de Windows. Lo ejecuta la tarea programada (cada 30 minutos)
cuando la activas desde el programa. También puedes lanzarlo a mano:  python revisar_alertas.py"""
import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    from radar import alertas
    from radar.config import CARPETA

    try:
        avisos = alertas.revisar_y_guardar(notificar=True)
        print(f"{datetime.now():%d/%m %H:%M} · {len(avisos)} aviso(s)")
        for a in avisos:
            print(" -", a["mensaje"])
    except Exception:  # noqa: BLE001
        (CARPETA / "alertas_error.log").write_text(traceback.format_exc(), encoding="utf-8")
