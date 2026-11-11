"""Alertas: avisos cuando un precio, una variación, una noticia o unos resultados cumplen tu condición.

Se revisan mientras el programa está abierto y, si lo activas, también con el programa cerrado mediante una tarea
programada de Windows (cada 30 minutos). Los avisos salen como notificación de Windows y quedan en un historial.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

from .config import CARPETA

RUTA_REGLAS = CARPETA / "alertas.json"
RUTA_HISTORIAL = CARPETA / "alertas_historial.json"
NOMBRE_TAREA = "RadarInversorAlertas"

TIPOS = {
    "precio_mayor": "El precio sube por encima de…",
    "precio_menor": "El precio baja por debajo de…",
    "sube_dia": "Sube en el día más de… (%)",
    "baja_dia": "Baja en el día más de… (%)",
    "noticia": "Aparece una noticia con la palabra…",
    "operacion": "Noticia de OPA, fusión, compra o venta de la empresa",
    "resultados": "Presenta resultados dentro de… (días)",
}
NECESITA_VALOR = {"precio_mayor", "precio_menor", "sube_dia", "baja_dia", "noticia", "resultados"}


# ----------------------------------------------------------------------------- almacenamiento
def _leer(ruta: Path, defecto):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defecto


def _escribir(ruta: Path, datos) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, ruta)


def cargar_reglas() -> list[dict]:
    return _leer(RUTA_REGLAS, [])


def guardar_reglas(reglas: list[dict]) -> None:
    _escribir(RUTA_REGLAS, reglas)


def nueva_regla(ticker: str, tipo: str, valor=None, nota: str = "") -> dict:
    if tipo not in TIPOS:
        raise ValueError(f"Tipo de alerta desconocido: {tipo}")
    if tipo in NECESITA_VALOR and (valor is None or valor == ""):
        raise ValueError("Esta alerta necesita un valor.")
    return {"id": uuid.uuid4().hex[:8], "ticker": ticker.strip().upper(), "tipo": tipo, "valor": valor, "nota": nota,
            "activa": True, "creada": datetime.now().isoformat(timespec="minutes"), "disparos": {}, "vistos": []}


def historial(n: int = 100) -> list[dict]:
    return _leer(RUTA_HISTORIAL, [])[-n:][::-1]


def _apuntar(mensajes: list[dict]) -> None:
    if mensajes:
        h = _leer(RUTA_HISTORIAL, [])
        _escribir(RUTA_HISTORIAL, (h + mensajes)[-500:])


def describir(r: dict) -> str:
    v = r.get("valor")
    textos = {
        "precio_mayor": f"{r['ticker']} por encima de {v}", "precio_menor": f"{r['ticker']} por debajo de {v}",
        "sube_dia": f"{r['ticker']} sube más de un {v}% en el día", "baja_dia": f"{r['ticker']} baja más de un {v}% en el día",
        "noticia": f"Noticia de {r['ticker']} con «{v}»", "operacion": f"OPA, fusión, compra o venta relacionada con {r['ticker']}",
        "resultados": f"{r['ticker']} presenta resultados en {v} días o menos",
    }
    return textos.get(r["tipo"], r["tipo"])


# ----------------------------------------------------------------------------- evaluación
def evaluar(reglas: list[dict], precio_de=None, titulares_de=None, operaciones_de=None, dias_resultados_de=None,
            hoy: date | None = None) -> tuple[list[dict], list[dict]]:
    """Comprueba las reglas. Devuelve (avisos nuevos, reglas actualizadas). Cada regla avisa como mucho una vez al día
    (las de noticias, una vez por titular nuevo). Las funciones *_de permiten inyectar datos (útil para pruebas)."""
    from . import eventos, noticias  # import tardío: este módulo también lo usa el revisor en segundo plano

    precio_de = precio_de or eventos.ultimo_precio
    titulares_de = titulares_de or (lambda t: noticias.buscar(t, "es", "ES", 2, 30) + noticias.buscar(t, "en", "US", 2, 30))
    operaciones_de = operaciones_de or (lambda t: eventos.operaciones_corporativas(t, "es", "ES", 3)
                                        + eventos.operaciones_corporativas(t, "en", "US", 3))
    hoy = hoy or date.today()
    clave_dia = hoy.isoformat()
    avisos = []
    cache_precio, cache_tit = {}, {}

    def nombre_busqueda(r):
        return (r.get("nota") or "").strip() or r["ticker"]

    for r in reglas:
        if not r.get("activa", True):
            continue
        try:
            tipo, t, v = r["tipo"], r["ticker"], r.get("valor")
            mensaje = None
            if tipo in ("precio_mayor", "precio_menor", "sube_dia", "baja_dia"):
                if r.get("disparos", {}).get(clave_dia):
                    continue
                if t not in cache_precio:
                    cache_precio[t] = precio_de(t)
                info = cache_precio[t]
                p, var = info["precio"], info.get("var_dia")
                if tipo == "precio_mayor" and p >= float(v):
                    mensaje = f"{t} está en {p:.2f}, por encima de tu nivel de {float(v):.2f}"
                elif tipo == "precio_menor" and p <= float(v):
                    mensaje = f"{t} está en {p:.2f}, por debajo de tu nivel de {float(v):.2f}"
                elif tipo == "sube_dia" and var is not None and var * 100 >= float(v):
                    mensaje = f"{t} sube un {var * 100:.1f}% hoy (precio {p:.2f})"
                elif tipo == "baja_dia" and var is not None and -var * 100 >= float(v):
                    mensaje = f"{t} baja un {abs(var) * 100:.1f}% hoy (precio {p:.2f})"
                if mensaje:
                    r.setdefault("disparos", {})[clave_dia] = True
            elif tipo in ("noticia", "operacion"):
                busq = nombre_busqueda(r)
                if tipo == "noticia":
                    if busq not in cache_tit:
                        cache_tit[busq] = titulares_de(busq)
                    candidatos = [i for i in cache_tit[busq] if str(v).lower() in i["titulo"].lower()]
                else:
                    candidatos = operaciones_de(busq)
                vistos = set(r.get("vistos", []))
                nuevos = [i for i in candidatos if hashlib.md5(i["titulo"].encode()).hexdigest()[:10] not in vistos]
                if nuevos:
                    i = nuevos[0]
                    etiqueta = f" [{i['operacion']}]" if i.get("operacion") else ""
                    mensaje = f"{t}{etiqueta}: {i['titulo']} ({i.get('fuente', '')})"
                    r["vistos"] = (list(vistos) + [hashlib.md5(x["titulo"].encode()).hexdigest()[:10] for x in nuevos])[-300:]
            elif tipo == "resultados":
                if r.get("disparos", {}).get(clave_dia):
                    continue
                faltan = dias_resultados_de(t) if dias_resultados_de else _dias_a_resultados(t, hoy)
                if faltan is not None and 0 <= faltan <= int(v):
                    mensaje = f"{t} presenta resultados {'hoy' if faltan == 0 else f'en {faltan} días'}"
                    r.setdefault("disparos", {})[clave_dia] = True
            if mensaje:
                avisos.append({"momento": datetime.now().isoformat(timespec="minutes"), "regla": r["id"],
                               "ticker": t, "mensaje": mensaje})
        except Exception:  # noqa: BLE001 - una regla con error no debe parar las demás
            continue
        # limpia disparos antiguos
        r["disparos"] = {k: val for k, val in r.get("disparos", {}).items() if k >= clave_dia}
    return avisos, reglas


def _dias_a_resultados(ticker: str, hoy: date) -> int | None:
    from . import eventos
    a = eventos.agenda([ticker], dias=60)
    res = a[a["Evento"].str.contains("Resultados")] if not a.empty else a
    return int(res["Faltan (días)"].iloc[0]) if len(res) else None


def revisar_y_guardar(notificar: bool = True) -> list[dict]:
    """Evalúa todas las reglas, guarda su estado, apunta el historial y lanza notificaciones de Windows."""
    reglas = cargar_reglas()
    if not reglas:
        return []
    avisos, reglas = evaluar(reglas)
    guardar_reglas(reglas)
    _apuntar(avisos)
    if notificar:
        for a in avisos[:5]:
            notificar_windows("Radar Inversor · " + a["ticker"], a["mensaje"])
    return avisos


# ----------------------------------------------------------------------------- Windows
_AUMID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"


def notificar_windows(titulo: str, texto: str) -> bool:
    """Notificación nativa de Windows 10/11 (sin instalar nada). En otros sistemas no hace nada."""
    if sys.platform != "win32":
        return False
    def limpio(s):
        return str(s).replace("'", "’").replace("\n", " ")[:240]
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
        "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
        f"$t.GetElementsByTagName('text').Item(0).AppendChild($t.CreateTextNode('{limpio(titulo)}')) > $null;"
        f"$t.GetElementsByTagName('text').Item(1).AppendChild($t.CreateTextNode('{limpio(texto)}')) > $null;"
        "$n = [Windows.UI.Notifications.ToastNotification]::new($t);"
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{_AUMID}').Show($n)"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                       capture_output=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except Exception:  # noqa: BLE001
        return False


def _lanzador_vbs() -> Path:
    """Script que ejecuta el revisor sin abrir ventanas (ruta corta, dentro de tu carpeta de datos)."""
    raiz = Path(__file__).resolve().parent.parent
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        pythonw = Path(sys.executable)
    vbs = CARPETA / "revisar_alertas.vbs"
    vbs.write_text(
        'Set sh = CreateObject("WScript.Shell")\r\n'
        f'sh.CurrentDirectory = "{raiz}"\r\n'
        f'sh.Run """{pythonw}"" ""{raiz / "revisar_alertas.py"}""", 0, False\r\n', encoding="utf-16")
    return vbs


def activar_tarea(minutos: int = 30) -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Solo disponible en Windows."
    vbs = _lanzador_vbs()
    r = subprocess.run(["schtasks", "/Create", "/F", "/SC", "MINUTE", "/MO", str(minutos), "/TN", NOMBRE_TAREA,
                        "/TR", f'wscript.exe "{vbs}"'], capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode == 0, (r.stdout or r.stderr or "").strip()


def desactivar_tarea() -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Solo disponible en Windows."
    r = subprocess.run(["schtasks", "/Delete", "/F", "/TN", NOMBRE_TAREA], capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode == 0, (r.stdout or r.stderr or "").strip()


def tarea_activa() -> bool:
    if sys.platform != "win32":
        return False
    r = subprocess.run(["schtasks", "/Query", "/TN", NOMBRE_TAREA], capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode == 0
