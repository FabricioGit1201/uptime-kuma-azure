
#!/usr/bin/env python3

import os
import sys
import tarfile
import sqlite3
import shutil
import tempfile
import subprocess

from pathlib import Path
from datetime import datetime, timezone


DATA_DIR = Path("/home/uptime-kuma-data")
BACKUP_DIR = Path("/home/uptime-kuma-backups")
PRESERVED_DIR = BACKUP_DIR / "recovery-preserved"

PENDING_FILE = DATA_DIR / ".recovery-pending"

EXCLUDED_FILES = {
    "BACKUP_INFO.txt",
    "kuma.db.danada",
    "kuma.db-wal",
    "kuma.db-shm",
    "kuma.db-journal",
}


def log(message):
    print(f"[AUTO-RECOVERY] {message}", flush=True)


def utc_timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def validate_database(database):
    try:
        result = subprocess.run(
            ["sqlite3", str(database), "PRAGMA integrity_check;"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

        output = result.stdout.strip()

        if result.returncode != 0 or output != "ok":
            log(f"Base de datos inválida: {database}")
            log(f"Resultado SQLite: {output or result.stderr.strip()}")
            return False

        return True

    except Exception as error:
        log(f"Error validando SQLite: {error}")
        return False


def safe_member_path(member_name):
    if "\\" in member_name:
        raise ValueError("Ruta con separadores no permitidos")

    path = Path(member_name)

    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Ruta insegura dentro del backup")

    if not path.parts or path.parts[0] != "uptime-kuma":
        raise ValueError("El backup contiene rutas fuera de uptime-kuma")

    if any(part in ("", ".") for part in path.parts):
        raise ValueError("Ruta inválida dentro del backup")

    return path


def extract_backup(archive_path, destination):
    seen = set()
    database_found = False
    manifest_found = False

    with tarfile.open(archive_path, "r:gz") as archive:

        for member in archive.getmembers():

            relative = safe_member_path(member.name)

            if member.name in seen:
                raise ValueError(f"Archivo duplicado: {member.name}")

            seen.add(member.name)

            if not (member.isdir() or member.isfile()):
                raise ValueError(
                    f"Tipo de archivo no permitido: {member.name}"
                )

            if not member.isdir() and not member.isfile():
                raise ValueError(f"Miembro inválido: {member.name}")

            if relative.parts == ("uptime-kuma",):
                continue

            if len(relative.parts) < 2:
                raise ValueError("Estructura de backup incorrecta")

            filename = relative.name

            if filename in EXCLUDED_FILES:
                continue

            if filename in {"kuma.db"}:
                if relative.parts != ("uptime-kuma", "kuma.db"):
                    raise ValueError("kuma.db fuera de la raíz esperada")
                database_found = True

            if filename == "BACKUP_INFO.txt":
                if relative.parts != ("uptime-kuma", "BACKUP_INFO.txt"):
                    raise ValueError("Manifiesto fuera de la raíz esperada")
                manifest_found = True

            target = destination.joinpath(*relative.parts[1:])

            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)

            source = archive.extractfile(member)

            if source is None:
                raise ValueError(f"No se pudo leer: {member.name}")

            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)

    if not database_found or not manifest_found:
        raise ValueError("El backup no contiene los archivos obligatorios")

    manifest = destination / "BACKUP_INFO.txt"

    content = manifest.read_text(encoding="utf-8")

    if "Verificacion SQLite: OK" not in content:
        raise ValueError("El manifiesto no confirma integridad SQLite")

    database = destination / "kuma.db"

    if not validate_database(database):
        raise ValueError("La base de datos del backup no es válida")


def preserve_current_data():
    PRESERVED_DIR.mkdir(parents=True, exist_ok=True)

    destination = PRESERVED_DIR / utc_timestamp()

    if destination.exists():
        destination = PRESERVED_DIR / (
            utc_timestamp() + "_" + str(os.getpid())
        )

    shutil.copytree(
        DATA_DIR,
        destination,
        symlinks=True,
    )

    log(f"Datos actuales preservados en: {destination}")

    return destination


def clear_data_directory():
    for item in DATA_DIR.iterdir():

        if item.name == ".recovery-pending":
            continue

        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()


def copy_restored_data(source):
    for item in source.iterdir():

        if item.name in EXCLUDED_FILES:
            continue

        if item.name == ".recovery-pending":
            continue

        destination = DATA_DIR / item.name

        if item.is_dir() and not item.is_symlink():
            shutil.copytree(item, destination, symlinks=True)
        elif item.is_symlink():
            destination.symlink_to(os.readlink(item))
        else:
            shutil.copy2(item, destination)


def rollback(preserved):
    log("Intentando recuperar los datos anteriores...")

    clear_data_directory()

    for item in preserved.iterdir():

        destination = DATA_DIR / item.name

        if item.is_dir() and not item.is_symlink():
            shutil.copytree(item, destination, symlinks=True)
        elif item.is_symlink():
            destination.symlink_to(os.readlink(item))
        else:
            shutil.copy2(item, destination)

    log("Se restauró la copia de seguridad de los datos anteriores.")


def main():

    log("Iniciando proceso de recuperación.")

    if not PENDING_FILE.is_file():
        log("No existe marca de recuperación. No se requiere restauración.")
        return 0

    if not DATA_DIR.is_dir():
        log("ERROR: no existe el directorio de datos.")
        return 1

    if not BACKUP_DIR.is_dir():
        log("ERROR: no existe el directorio de backups.")
        return 1

    backups = sorted(
        BACKUP_DIR.glob("uptime-kuma-*.tar.gz"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )

    if not backups:
        log("ERROR: no hay backups disponibles.")
        return 1

    log(f"Backups encontrados: {len(backups)}")

    selected_backup = None

    with tempfile.TemporaryDirectory(prefix="kuma-restore-") as temporary:

        temporary_root = Path(temporary)

        for backup in backups:

            log(f"Validando backup: {backup.name}")

            staging = temporary_root / "candidate"

            if staging.exists():
                shutil.rmtree(staging)

            staging.mkdir()

            try:
                extract_backup(backup, staging)

                selected_backup = backup

                log(f"Backup válido seleccionado: {backup.name}")
                break

            except Exception as error:
                log(f"Backup rechazado: {backup.name}")
                log(f"Motivo: {error}")

        if selected_backup is None:
            log("ERROR: ningún backup superó las validaciones.")
            return 1

        preserved = preserve_current_data()

        try:
            log("Preparando directorio de datos.")

            clear_data_directory()

            copy_restored_data(staging)

            restored_database = DATA_DIR / "kuma.db"

            if not validate_database(restored_database):
                raise RuntimeError(
                    "La base restaurada no superó la validación final."
                )

            log("Base restaurada y validada correctamente.")

            PENDING_FILE.unlink(missing_ok=True)

            log("Marca de recuperación eliminada.")
            log(f"Backup utilizado: {selected_backup.name}")
            log(f"Datos anteriores preservados en: {preserved}")
            log("RECUPERACIÓN COMPLETADA.")

            return 0

        except Exception as error:

            log(f"ERROR durante la restauración: {error}")

            try:
                rollback(preserved)
            except Exception as rollback_error:
                log(f"ERROR CRÍTICO durante rollback: {rollback_error}")

            log("La marca de recuperación se conserva.")
            return 1


if __name__ == "__main__":
    sys.exit(main())
