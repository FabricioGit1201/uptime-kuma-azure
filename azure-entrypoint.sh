
#!/bin/sh
set -eu

DATA_DIR="${DATA_DIR:-/home/uptime-kuma-data}"

echo "=========================================="
echo " UPTIME KUMA - ARRANQUE PERSONALIZADO"
echo "=========================================="
echo "Directorio de datos: $DATA_DIR"

echo "Comprobando si existe una recuperación pendiente..."

if [ -f "$DATA_DIR/.recovery-pending" ]; then
    echo "Se encontró una marca de recuperación pendiente."
    echo "La recuperación automática todavía no está habilitada."
    echo "Se detiene el arranque por seguridad."
    exit 1
fi

echo "No hay recuperación pendiente."
echo "Iniciando Uptime Kuma..."

exec node server/server.js
