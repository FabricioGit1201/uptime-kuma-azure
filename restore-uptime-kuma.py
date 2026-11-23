
#!/usr/bin/env python3

import os
import re
import sys
import tarfile
import shutil
import hashlib
import sqlite3
import tempfile
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "/home/uptime-kuma-data"))
BACKUP_DIR = Path("/home/uptime-kuma-backups")
PRESERVED_DIR = BACKUP_DIR / "recovery-preserved"
PENDING_FILE = DATA_DIR / ".recovery-pending"

BACKUP_PATTERN = re.compile(
    r"^uptime-kuma-[0-9]{8}_[0-9]{6}\.tar\.gz$"
)

EXCLUDED_FILES = {
    "kuma.db-wal",
    "kuma.db-shm",
    "kuma.db-journal",
    "kuma.db.danada",
}

MAX_MEMBERS = 10000
MAX_TOTAL_SIZE = 2 * 1024 * 1024 * 1024


def log(message):
    print(f"[RESTORE] {message}", flush=True)


def sha256_file(path):
    digest = hashlib.sha256()

    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def safe_backup_name():
    if not PENDING_FILE.is_file():
        raise RuntimeError("No existe la marca de recuperación.")

    name = PENDING_FILE.read_text(encoding="utf-8").strip()

    if not BACKUP_PATTERN.fullmatch(name):
        raise RuntimeError("El nombre del backup en la marca no es válido.")

    backup = BACKUP_DIR / name

    if backup.is_symlink() or not backup.is_file():
        raise RuntimeError("El backup indicado no existe o no es un archivo regular.")

    if backup.resolve().parent != BACKUP_DIR.resolve():
        raise RuntimeError("La ruta del backup no es segura.")

    return backup


def safe_member_path(member):
    name = member.name

    if not name.startswith("uptime-kuma/"):
        raise RuntimeError(f"Ruta inesperada en backup: {name}")

    relative = Path(name)

    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError(f"Ruta insegura en backup: {name}")

    if not (member.isfile() or member.isdir()):
        raise RuntimeError(f"Tipo de archivo no permitido: {name}")

    return relative


def extract_and_validate(backup, staging):
    log(f"Validando backup: {backup.name}")

    with tarfile.open(backup, "r:gz") as archive:
        members = archive.getmembers()

        if len(members) > MAX_MEMBERS:
            raise RuntimeError("El backup contiene demasiados elementos.")

        total_size = sum(
            member.size for member in members if member.isfile()
        )

        if total_size > MAX_TOTAL_SIZE:
            raise RuntimeError("El tamaño del backup supera el límite permitido.")

        validated = []

        for member in members:
            relative = safe_member_path(member)
            validated.append((member, relative))

        for member, relative in validated:
            destination = staging / relative

            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)

            source = archive.extractfile(member)

            if source is None:
                raise RuntimeError(f"No se pudo leer: {member.name}")

            with source, open(destination, "xb") as output:
                shutil.copyfileobj(source, output)

    root = staging / "uptime-kuma"

    manifest = root / "BACKUP_INFO.txt"
    database = root / "kuma.db"

    if not manifest.is_file() or not database.is_file():
        raise RuntimeError("El backup no contiene manifiesto o kuma.db.")

    manifest_text = manifest.read_text(
        encoding="utf-8", errors="replace"
    )

    if "Verificacion SQLite: OK" not in manifest_text:
        raise RuntimeError("El manifiesto no confirma la integridad SQLite.")

    log("Ejecutando integrity_check en almacenamiento temporal...")

    connection = sqlite3.connect(
        f"file:{database}?mode=ro",
        uri=True,
        timeout=30
    )

    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()

        if not result or result[0] != "ok":
            raise RuntimeError(f"Integridad SQLite incorrecta: {result}")
    finally:
        connection.close()

    log("Backup validado correctamente.")

    return root


def prepare_restore_files(source, destination):
    for item in source.iterdir():
        if item.name in EXCLUDED_FILES:
            continue

        if item.name == "BACKUP_INFO.txt":
            continue

        target = destination / item.name

        if item.is_dir():
            shutil.copytree(item, target)
        elif item.is_file():
            shutil.copy2(item, target)


def preserve_current_data():
    PRESERVED_DIR.mkdir(parents=True, exist_ok=True)

    destination = PRESERVED_DIR / "previous-data"

    if destination.exists():
        destination = PRESERVED_DIR / "previous-data-recovery"

    if DATA_DIR.exists():
        shutil.copytree(
            DATA_DIR,
            destination,
            ignore=shutil.ignore_patterns(".recovery-pending")
        )

    log(f"Datos anteriores preservados en: {destination}")

    return destination


def clear_data_directory():
    for item in DATA_DIR.iterdir():
        if item.name == ".recovery-pending":
            continue

        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()


def rollback(preserved):
    log("ERROR: iniciando rollback.")

    clear_data_directory()

    for item in preserved.iterdir():
        destination = DATA_DIR / item.name

        if item.is_dir():
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)

    log("Rollback finalizado.")


def main():
    log("Iniciando restauración manual.")

    if not PENDING_FILE.is_file():
        raise RuntimeError("No existe .recovery-pending.")

    backup = safe_backup_name()

    with tempfile.TemporaryDirectory(prefix="kuma-restore-") as temp:
        temp_path = Path(temp)
        staging = temp_path / "extracted"
        restored = temp_path / "restored"

        staging.mkdir()
        restored.mkdir()

        source = extract_and_validate(backup, staging)

        prepare_restore_files(source, restored)

        staged_database = restored / "kuma.db"

        if not staged_database.is_file():
            raise RuntimeError("No se preparó la base de datos.")

        expected_hash = sha256_file(staged_database)
        expected_size = staged_database.stat().st_size

        preserved = preserve_current_data()

        try:
            log("Preparando directorio de datos.")
            clear_data_directory()

            log("Copiando archivos restaurados.")
            for item in restored.iterdir():
                destination = DATA_DIR / item.name

                if item.is_dir():
                    shutil.copytree(item, destination)
                else:
                    shutil.copy2(item, destination)

            target_database = DATA_DIR / "kuma.db"

            actual_hash = sha256_file(target_database)
            actual_size = target_database.stat().st_size

            if actual_size != expected_size or actual_hash != expected_hash:
                raise RuntimeError(
                    "La base copiada no coincide con la base validada."
                )

            PENDING_FILE.unlink()

            log("RESTAURACIÓN COMPLETADA.")
            log(f"Backup utilizado: {backup.name}")
            log(f"SHA-256: {actual_hash}")

        except Exception:
            rollback(preserved)
            raise


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        log(f"ERROR: {error}")
        sys.exit(1)
