"""Configuración común. Todo se puede cambiar con variables de entorno."""
from __future__ import annotations

import os
from pathlib import Path

# Carpeta donde se guardan caché, tus relaciones y tus posiciones.
CARPETA = Path(os.environ.get("RADAR_DIR", Path.home() / ".radar_inversor"))
try:
    CARPETA.mkdir(parents=True, exist_ok=True)
except OSError:  # carpeta de solo lectura: seguimos sin persistencia
    pass

# La SEC exige identificarse en cada petición con nombre y correo ("Tu Nombre tu_correo@dominio.com").
# Se toma de la variable RADAR_SEC_UA o del fichero que guarda la propia aplicación en tu ordenador.
RUTA_SEC = CARPETA / "sec_contacto.txt"


def sec_ua() -> str:
    valor = os.environ.get("RADAR_SEC_UA", "").strip()
    if not valor:
        try:
            valor = RUTA_SEC.read_text(encoding="utf-8").strip()
        except OSError:
            valor = ""
    return valor


def guardar_sec_contacto(texto: str) -> None:
    RUTA_SEC.write_text(texto.strip(), encoding="utf-8")


# Cabeceras para webs públicas.
UA_WEB = {"User-Agent": "Mozilla/5.0 (compatible; RadarInversor/1.0; uso personal)"}
# Overpass rechaza (HTTP 406) los agentes genéricos: pide uno descriptivo.
UA_OVERPASS = {"User-Agent": "RadarInversor/1.0 (uso personal; radar-inversor local)"}


def leer_clave(servicio: str) -> str:
    """Claves opcionales de servicios gratuitos (p. ej. aisstream). Se guardan solo en tu ordenador."""
    try:
        return (CARPETA / f"clave_{servicio}.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def guardar_clave(servicio: str, valor: str) -> None:
    (CARPETA / f"clave_{servicio}.txt").write_text(valor.strip(), encoding="utf-8")
