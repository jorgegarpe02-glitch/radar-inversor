"""Caché en disco con caducidad.

Evita machacar las fuentes gratuitas y permite seguir viendo el último dato
conocido si pierdes la conexión (si la fuente falla, se devuelve lo guardado).
"""
from __future__ import annotations

import functools
import hashlib
import pickle
import time

from .config import CARPETA

CACHE = CARPETA / "cache"


def _vacio(valor) -> bool:
    if valor is None:
        return True
    if hasattr(valor, "empty"):
        return bool(valor.empty)
    try:
        return len(valor) == 0
    except TypeError:
        return False


def _ruta(clave: str):
    CACHE.mkdir(parents=True, exist_ok=True)
    return CACHE / (hashlib.sha1(clave.encode("utf-8")).hexdigest() + ".pkl")


def con_cache(ttl_segundos: int):
    """Decorador: cachea el resultado `ttl_segundos`. No guarda resultados vacíos."""

    def decorador(funcion):
        @functools.wraps(funcion)
        def envoltura(*args, **kwargs):
            clave = f"{funcion.__module__}.{funcion.__name__}|{args!r}|{sorted(kwargs.items())!r}"
            try:
                ruta = _ruta(clave)
            except OSError:
                return funcion(*args, **kwargs)
            if ruta.exists() and time.time() - ruta.stat().st_mtime < ttl_segundos:
                try:
                    return pickle.loads(ruta.read_bytes())
                except Exception:
                    pass
            try:
                valor = funcion(*args, **kwargs)
            except Exception:
                if ruta.exists():  # sin conexión o fuente caída: mejor dato viejo que nada
                    try:
                        return pickle.loads(ruta.read_bytes())
                    except Exception:
                        pass
                raise
            if not _vacio(valor):
                try:
                    ruta.write_bytes(pickle.dumps(valor))
                except Exception:
                    pass
            return valor

        envoltura.sin_cache = funcion
        return envoltura

    return decorador


def limpiar() -> int:
    """Borra toda la caché. Devuelve cuántos ficheros eliminó."""
    n = 0
    if CACHE.exists():
        for f in CACHE.glob("*.pkl"):
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
    return n
