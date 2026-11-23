#!/bin/sh
set -eu

DATA_DIR="${DATA_DIR:-/home/uptime-kuma-data}"

echo "=========================================="
echo " UPTIME KUMA - ARRANQUE PERSONALIZADO"
echo "=========================================="

echo "Directorio de datos: $DATA_DIR"
echo "Comprobando recuperación pendiente..."

if [ -f "$DATA_DIR/.recovery-pending" ]; then

    echo "Se encontró una marca de recuperación."

    echo "Iniciando restauración automática..."

    /usr/bin/python3 /app/restore-uptime-kuma.py

    echo "Restauración finalizada correctamente."

else

    echo "No hay recuperación pendiente."

fi

echo "Iniciando Uptime Kuma..."

exec node server/server.js
