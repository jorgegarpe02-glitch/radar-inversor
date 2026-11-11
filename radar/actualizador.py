"""Actualizaciones automáticas del programa.

Al arrancar, el programa mira si hay una versión más nueva en el sitio donde se publica (un repositorio de GitHub),
la descarga y sustituye sus ficheros. Tus datos (diario, posiciones, relaciones, alertas, claves) viven en otra carpeta
(~/.radar_inversor) y no se tocan nunca.

Dónde mirar se configura en `actualizacion.json`, junto al programa:

    {"repositorio": "usuario/radar-inversor", "rama": "main"}

o, si se publica en otro sitio, con dos direcciones completas:

    {"url_version": "https://…/VERSION", "url_zip": "https://…/radar-inversor.zip"}

Si el fichero no existe o está vacío, el programa no busca actualizaciones.
"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUTA_CONFIG = RAIZ / "actualizacion.json"
RUTA_VERSION = RAIZ / "VERSION"
COPIA = RAIZ / "_version_anterior"
# Nunca se sobrescriben: el entorno de Python, la copia de seguridad y los lanzadores que pueden estar en uso
NO_TOCAR = {".venv", "_version_anterior", ".acceso_creado", "__pycache__", ".git", "iniciar.bat", "iniciar.command"}
UA = {"User-Agent": "RadarInversor-actualizador"}


def version_local() -> str:
    try:
        return RUTA_VERSION.read_text(encoding="utf-8").strip() or "0"
    except OSError:
        return "0"


def _tupla(v: str) -> tuple:
    partes = []
    for x in str(v).strip().lstrip("vV").split("."):
        digitos = "".join(c for c in x if c.isdigit())
        partes.append(int(digitos) if digitos else 0)
    return tuple(partes)


def es_mas_nueva(remota: str, local: str) -> bool:
    return _tupla(remota) > _tupla(local)


def configuracion() -> dict:
    try:
        c = json.loads(RUTA_CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return c if isinstance(c, dict) else {}


def guardar_configuracion(repositorio: str, rama: str = "main") -> None:
    RUTA_CONFIG.write_text(json.dumps({"repositorio": repositorio.strip().strip("/"), "rama": rama.strip() or "main"},
                                      indent=2, ensure_ascii=False), encoding="utf-8")


def _urls(c: dict) -> tuple[str, str] | None:
    if c.get("url_version") and c.get("url_zip"):
        return c["url_version"], c["url_zip"]
    repo = (c.get("repositorio") or "").strip().strip("/")
    if repo.count("/") != 1:
        return None
    rama = c.get("rama") or "main"
    return (f"https://raw.githubusercontent.com/{repo}/{rama}/VERSION",
            f"https://codeload.github.com/{repo}/zip/refs/heads/{rama}")


def comprobar(espera: float = 4.0) -> dict:
    """{'configurado', 'local', 'remota', 'hay_nueva', 'error'}. No modifica nada."""
    import requests

    info = {"configurado": False, "local": version_local(), "remota": None, "hay_nueva": False, "error": None}
    urls = _urls(configuracion())
    if not urls:
        return info
    info["configurado"] = True
    if not all(u.startswith("https://") for u in urls):
        info["error"] = "Las direcciones de actualización deben empezar por https://"
        return info
    try:
        r = requests.get(urls[0], headers=UA, timeout=espera)
        r.raise_for_status()
        info["remota"] = r.text.strip().splitlines()[0].strip()[:20]
        info["hay_nueva"] = es_mas_nueva(info["remota"], info["local"])
    except Exception as e:  # noqa: BLE001 - sin conexión o repositorio caído: se sigue con la versión que hay
        info["error"] = f"{type(e).__name__}"
    return info


def _raiz_del_zip(carpeta: Path) -> Path | None:
    """Carpeta dentro del zip que contiene el programa (la que tiene app.py)."""
    if (carpeta / "app.py").exists():
        return carpeta
    for candidato in sorted(carpeta.rglob("app.py"), key=lambda p: len(p.parts)):
        if (candidato.parent / "radar").is_dir():
            return candidato.parent
    return None


def aplicar(espera: float = 60.0) -> dict:
    """Descarga la última versión y sustituye los ficheros del programa. Devuelve {'ok', 'version', 'mensaje', 'requisitos'}."""
    import requests

    urls = _urls(configuracion())
    if not urls:
        return {"ok": False, "mensaje": "No hay un sitio de actualizaciones configurado."}
    try:
        r = requests.get(urls[1], headers=UA, timeout=espera)
        r.raise_for_status()
        with tempfile.TemporaryDirectory() as tmp:
            destino_tmp = Path(tmp).resolve()
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                for miembro in z.infolist():  # nada puede salirse de la carpeta temporal
                    objetivo = (destino_tmp / miembro.filename).resolve()
                    if destino_tmp not in objetivo.parents and objetivo != destino_tmp:
                        return {"ok": False, "mensaje": "El paquete de actualización no es válido."}
                z.extractall(destino_tmp)
            origen = _raiz_del_zip(destino_tmp)
            if origen is None or not (origen / "VERSION").exists():
                return {"ok": False, "mensaje": "El paquete descargado no contiene el programa."}
            nueva = (origen / "VERSION").read_text(encoding="utf-8").strip()
            requisitos_antes = (RAIZ / "requirements.txt").read_text(encoding="utf-8") if (RAIZ / "requirements.txt").exists() else ""
            # copia de seguridad de la versión actual (solo código y datos del programa, sin el entorno de Python)
            shutil.rmtree(COPIA, ignore_errors=True)
            COPIA.mkdir(exist_ok=True)
            for elemento in RAIZ.iterdir():
                if elemento.name in NO_TOCAR:
                    continue
                try:
                    if elemento.is_dir():
                        shutil.copytree(elemento, COPIA / elemento.name, ignore=shutil.ignore_patterns("__pycache__"))
                    else:
                        shutil.copy2(elemento, COPIA / elemento.name)
                except OSError:
                    pass
            # sustitución
            for elemento in origen.iterdir():
                if elemento.name in NO_TOCAR:
                    continue
                if elemento.name == "actualizacion.json" and RUTA_CONFIG.exists():
                    continue  # se respeta el sitio de actualizaciones que ya tenga configurado cada uno
                final = RAIZ / elemento.name
                if elemento.is_dir():
                    shutil.copytree(elemento, final, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
                else:
                    shutil.copy2(elemento, final)
            requisitos_despues = (RAIZ / "requirements.txt").read_text(encoding="utf-8") if (RAIZ / "requirements.txt").exists() else ""
        return {"ok": True, "version": nueva, "mensaje": f"Actualizado a la versión {nueva}.",
                "requisitos": requisitos_antes != requisitos_despues}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "mensaje": f"No pude actualizar ({type(e).__name__}). Sigo con la versión actual."}


def instalar_requisitos() -> None:
    """Instala librerías nuevas que pida la versión recién descargada."""
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r",
                    str(RAIZ / "requirements.txt")], cwd=RAIZ, check=False)


def restaurar_anterior() -> bool:
    """Vuelve a la versión guardada antes de la última actualización."""
    if not COPIA.exists() or not (COPIA / "app.py").exists():
        return False
    for elemento in COPIA.iterdir():
        final = RAIZ / elemento.name
        if elemento.is_dir():
            shutil.copytree(elemento, final, dirs_exist_ok=True)
        else:
            shutil.copy2(elemento, final)
    return True


def al_arrancar() -> str:
    """Se llama desde lanzar.py antes de abrir el programa. Devuelve un mensaje para la ventana (o cadena vacía)."""
    try:
        info = comprobar()
        if not info["configurado"] or not info["hay_nueva"]:
            return ""
        print(f"  Hay una version nueva ({info['remota']}; tienes la {info['local']}). Descargando...")
        r = aplicar()
        if r.get("ok") and r.get("requisitos"):
            print("  Instalando librerias nuevas...")
            instalar_requisitos()
        return r.get("mensaje", "")
    except Exception:  # noqa: BLE001 - una actualización fallida nunca debe impedir abrir el programa
        return ""
