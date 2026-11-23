
#!/usr/bin/env python3

import os
import re
import sys
import tarfile
import sqlite3
import tempfile
from pathlib import Path

DATA_DIR = Path("/home/uptime-kuma-data")
BACKUP_DIR = Path("/home/uptime-kuma-backups")
PENDING_FILE = DATA_DIR / ".recovery-pending"

PATTERN = re.compile(
    r"^uptime-kuma-[0-9]{8}_[0-9]{6}\.tar\.gz$"
)

MAX_MEMBERS = 10000
MAX_TOTAL_SIZE = 2 * 1024 * 1024 * 1024


def log(message):
    print(f"[MANUAL-RESTORE] {message}", flush=True)


def validate_backup(backup):
    with tempfile.TemporaryDirectory(prefix="kuma-manual-check-") as temp:
        staging = Path(temp)

        with tarfile.open(backup, "r:gz") as archive:
            members = archive.getmembers()

            if len(members) > MAX_MEMBERS:
                raise RuntimeError("Demasiados elementos en el backup.")

            total_size = sum(
                m.size for m in members if m.isfile()
            )

            if total_size > MAX_TOTAL_SIZE:
                raise RuntimeError("El backup supera el tamaño permitido.")

            for member in members:
                name = member.name.rstrip("/")

                if name == "uptime-kuma" and member.isdir():
                    continue

                if not name.startswith("uptime-kuma/"):
                    raise RuntimeError(f"Ruta inesperada: {name}")

                relative = Path(name)

                if relative.is_absolute() or ".." in relative.parts:
                    raise RuntimeError(f"Ruta insegura: {name}")

                if not (member.isfile() or member.isdir()):
                    raise RuntimeError(f"Tipo no permitido: {name}")

            archive.extractall(staging)

        root = staging / "uptime-kuma"
        manifest = root / "BACKUP_INFO.txt"
        database = root / "kuma.db"

        if not manifest.is_file() or not database.is_file():
            raise RuntimeError("Falta el manifiesto o kuma.db.")

        manifest_text = manifest.read_text(
            encoding="utf-8", errors="replace"
        )

        if "Verificacion SQLite: OK" not in manifest_text:
            raise RuntimeError("El manifiesto no confirma integridad SQLite.")

        connection = sqlite3.connect(
            f"file:{database}?mode=ro",
            uri=True,
            timeout=30
        )

        try:
            result = connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()

            if not result or result[0] != "ok":
                raise RuntimeError(f"Integrity check fallido: {result}")
        finally:
            connection.close()


def main():
    if not DATA_DIR.is_dir() or not BACKUP_DIR.is_dir():
        raise RuntimeError("No se encontraron los directorios de datos y backups.")

    if PENDING_FILE.exists():
        raise RuntimeError(
            "Ya existe una solicitud de recuperación pendiente. "
            "No se sobrescribirá."
        )

    backups = [
        path for path in BACKUP_DIR.iterdir()
        if PATTERN.fullmatch(path.name)
        and path.is_file()
        and not path.is_symlink()
    ]

    backups.sort(key=lambda path: (path.name, path.stat().st_mtime), reverse=True)

    if not backups:
        raise RuntimeError("No hay backups disponibles.")

    log(f"Se encontraron {len(backups)} backups.")

    for backup in backups:
        log(f"Validando: {backup.name}")

        try:
            validate_backup(backup)

            temporary_marker = DATA_DIR / ".recovery-pending.tmp"

            with open(temporary_marker, "x", encoding="utf-8") as file:
                file.write(backup.name + "\n")
                file.flush()
                os.fsync(file.fileno())

            os.replace(temporary_marker, PENDING_FILE)

            log("BACKUP SELECCIONADO Y VALIDADO.")
            log(f"Archivo: {backup.name}")
            log("Solicitud de recuperación preparada.")
            log("Reinicie manualmente el App Service desde Azure Portal.")
            return

        except Exception as error:
            log(f"Backup descartado: {error}")

    raise RuntimeError("Ningún backup superó la validación.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        log(f"ERROR: {error}")
        sys.exit(1)
