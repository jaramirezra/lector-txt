#!/usr/bin/env bash
# Prepara el entorno virtual y las dependencias para ejecutar la app en local.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [ ! -x .venv/bin/python ]; then
  echo "Creando entorno virtual…"
  if ! python3 -m venv .venv >/dev/null 2>&1; then
    echo "ensurepip no está disponible; creando el entorno sin pip…"
    rm -rf .venv
    python3 -m venv --without-pip .venv
    TMP_DIR="$(mktemp -d)"
    trap 'rm -rf "$TMP_DIR"' EXIT
    curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$TMP_DIR/get-pip.py"
    .venv/bin/python "$TMP_DIR/get-pip.py"
  fi
fi

if [ ! -x .venv/bin/python ]; then
  echo "No se pudo crear .venv. Instala python3-venv y vuelve a intentarlo." >&2
  exit 1
fi

.venv/bin/python -m pip install --upgrade pip wheel
.venv/bin/python -m pip install -r requirements-dev.txt

echo
echo "Todo listo. Arranca la aplicación con: ./run.sh"
