#!/bin/bash
# Script para iniciar el sitio de Ecocordi.
# Uso:  ./iniciar.sh    (o)   bash iniciar.sh
cd "$(dirname "$0")"
echo "Iniciando Ecocordi en http://localhost:8000 ..."
python3 server.py
