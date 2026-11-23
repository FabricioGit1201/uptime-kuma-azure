
#!/bin/sh
set -eu

DATA_DIR="${DATA_DIR:-/home/uptime-kuma-data}"

echo "=========================================="
echo " UPTIME KUMA - ARRANQUE PERSONALIZADO"
echo "=========================================="

echo "Directorio de datos: $DATA_DIR"

# Instalar WebJob manual en almacenamiento persistente de Azure
WEBJOB_SOURCE="/app/webjobs/KumaRestoreManual/run.sh"
WEBJOB_TARGET="/home/site/wwwroot/App_Data/jobs/triggered/KumaRestoreManual"

if [ -f "$WEBJOB_SOURCE" ]; then
    mkdir -p "$WEBJOB_TARGET"
    cp "$WEBJOB_SOURCE" "$WEBJOB_TARGET/run.sh"
    chmod +x "$WEBJOB_TARGET/run.sh"
    echo "WebJob KumaRestoreManual instalado en almacenamiento persistente."
else
    echo "ADVERTENCIA: No se encontró el archivo del WebJob: $WEBJOB_SOURCE"
fi

# Instalar restaurador manual en almacenamiento compartido con Kudu
mkdir -p /home/uptime-kuma-backups

if [ -f "/app/prepare-manual-restore.py" ]; then
    cp /app/prepare-manual-restore.py \
       /home/uptime-kuma-backups/prepare-manual-restore.py

    chmod +x /home/uptime-kuma-backups/prepare-manual-restore.py

    echo "Restaurador manual instalado en almacenamiento compartido."
else
    echo "ADVERTENCIA: No se encontró prepare-manual-restore.py"
fi

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

