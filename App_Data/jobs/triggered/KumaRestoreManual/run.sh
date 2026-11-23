#!/bin/sh
set -eu

echo "=========================================="
echo " UPTIME KUMA - RESTAURACION MANUAL"
echo "=========================================="

/usr/bin/python3 /app/prepare-manual-restore.py

echo "Solicitud de restauracion preparada."
echo "Ahora reinicie manualmente el App Service."
