"""Lectura de titulares con IA (FinBERT), gratis y en tu ordenador.

FinBERT es un modelo de lenguaje entrenado con textos financieros en inglés para decir si una frase es positiva,
negativa o neutra para los inversores. Es opcional: pesa ~1 GB entre librerías y modelo (se descarga una vez).
Si no está instalado, el programa sigue usando el método de palabras clave.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from functools import lru_cache

MODELO = "ProsusAI/finbert"


def disponible() -> bool:
    return all(importlib.util.find_spec(m) is not None for m in ("torch", "transformers"))


def instalar() -> tuple[bool, str]:
    """Instala torch (versión CPU, más ligera) y transformers en el Python que ejecuta el programa."""
    pasos = [
        [sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "torch",
         "--index-url", "https://download.pytorch.org/whl/cpu"],
        [sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "transformers>=4.40"],
    ]
    log = []
    for cmd in pasos:
        r = subprocess.run(cmd, capture_output=True, text=True)
        log.append((r.stdout or "") + (r.stderr or ""))
        if r.returncode != 0:
            return False, "\n".join(log)[-3000:]
    importlib.invalidate_caches()
    return True, "Instalado."


@lru_cache(maxsize=1)
def _clasificador():
    from transformers import pipeline  # import tardío: solo si se usa
    return pipeline("text-classification", model=MODELO, top_k=None, truncation=True)


def puntuar(titulares: list[str]) -> list[float]:
    """Tono de cada titular de -1 (muy negativo) a +1 (muy positivo) = P(positivo) − P(negativo)."""
    if not titulares:
        return []
    salidas = _clasificador()(list(titulares), batch_size=16)
    tonos = []
    for s in salidas:
        p = {d["label"].lower(): d["score"] for d in s}
        tonos.append(float(p.get("positive", 0.0) - p.get("negative", 0.0)))
    return tonos


def aplicar(items: list[dict]) -> list[dict]:
    """Sustituye el tono por palabras clave por el de FinBERT (los titulares deben estar en inglés)."""
    from .noticias import etiqueta
    tonos = puntuar([i["titulo"] for i in items])
    salida = []
    for i, t in zip(items, tonos):
        salida.append({**i, "sentimiento": t, "marca": etiqueta(t), "metodo": "IA (FinBERT)"})
    return salida
