#!/usr/bin/env bash
# Arranca el servidor local. Uso: ./run.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [ ! -x .venv/bin/python ]; then
  echo "Falta el entorno virtual. Ejecuta ./setup.sh primero." >&2
  exit 1
fi

HOST="${LECTOR_HOST:-127.0.0.1}"
PORT="${LECTOR_PORT:-8000}"

if ! .venv/bin/python - "$HOST" "$PORT" <<'PY'
import socket
import sys

host, port = sys.argv[1], int(sys.argv[2])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    sock.bind((host, port))
except OSError:
    sys.exit(1)
finally:
    sock.close()
PY
then
  echo "El puerto $PORT está ocupado en $HOST." >&2
  echo "Prueba con otro puerto: LECTOR_PORT=8001 ./run.sh" >&2
  exit 1
fi

echo "Lector TXT disponible en http://$HOST:$PORT"
exec .venv/bin/python app.py
