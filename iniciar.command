#!/bin/bash
cd "$(dirname "$0")"
echo "Preparando Radar Inversor (la primera vez tarda un par de minutos)..."
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
python -m pip install -q -r requirements.txt
python lanzar.py
