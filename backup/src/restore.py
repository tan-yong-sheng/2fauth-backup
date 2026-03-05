#!/usr/bin/env python3
"""
2FAuth Backup - Restore script.

Restore 2FAuth SQLite data from backup archives with integrity verification.
Supports both local and cloud backups.
"""

import os
import sys
import argparse
import tempfile
import shutil
from datetime import datetime
from pathlib import Path

from utils import setup_logging, load_config, get_env, format_bytes
from database import SQLiteHandler
from archive import extract_archive, list_archive_contents
from encryption import decrypt_file, is_encrypted
from storage import RcloneStorage, get_destinations, download_from_destination
from notifications import get_notification_manager

logger = setup_logging()


def extract_db_type_from_filename(filename: str) -> str:
    """Extract database type from backup filename."""
    base = filename
    for ext in ['.tar.gz.gpg', '.tar.gz']:
        if base.endswith(ext):
            base = base[:-len(ext)]
            break

    parts = base.split('-')
    if len(parts) >= 4:
        potential_type = parts[-1]
        if potential_type in ['sqlite']:
            return potential_type

    return 'unknown'


def list_available_backups(source: str = 'cloud', include_all: bool = False) -> list:
    """List available backups from specified source."""
    db_type = 'sqlite'
    backups = []

    if source == 'local':
        backup_dir = get_env('BACKUP_DIR', '/backups')
        backup_path = Path(backup_dir)

        if backup_path.exists():
            for file_path in sorted(backup_path.glob('2fauth-backup-*'), reverse=True):
                if file_path.is_file() and file_path.name.endswith(('.tar.gz', '.tar.gz.gpg')):
                    backup_info = {
                        'name': file_path.name,
                        'path': str(file_path),
                        'size': file_path.stat().st_size,
                        'mod_time': file_path.stat().st_mtime
                    }

                    if include_all:
                        backups.append(backup_info)
                    else:
                        backup_db_type = extract_db_type_from_filename(file_path.name)
                        if backup_db_type == db_type or backup_db_type == 'unknown':
                            backups.append(backup_info)

    elif source == 'cloud':
        storage = RcloneStorage()
        destinations = get_destinations()

        for destination in destinations:
            cloud_backups = storage.list_backups(destination)
            for backup in cloud_backups:
                backup['full_remote'] = f"{destination}/{backup['name']}"

                if include_all:
                    backups.append(backup)
                else:
                    backup_db_type = extract_db_type_from_filename(backup['name'])
                    if backup_db_type == db_type or backup_db_type == 'unknown':
                        backups.append(backup)

        backups.sort(key=lambda x: x.get('mod_time', ''), reverse=True)

    return backups


def download_backup(backup_spec: str, temp_dir: str) -> str:
    """Download a backup to the temp directory."""
    if ':' in backup_spec and not backup_spec.startswith('/'):
        local_path = download_from_destination(backup_spec, temp_dir)
        if not local_path:
            raise RuntimeError(f"Failed to download backup from {backup_spec}")
        return local_path

    if not os.path.exists(backup_spec):
        raise FileNotFoundError(f"Backup not found: {backup_spec}")

    filename = os.path.basename(backup_spec)
    local_path = os.path.join(temp_dir, filename)

    if os.path.abspath(backup_spec) == os.path.abspath(local_path):
        return local_path

    shutil.copy2(backup_spec, local_path)
    return local_path


def restore_backup(backup_path: str, force: bool = False) -> bool:
    """Restore 2FAuth from a backup archive."""
    temp_dir = None

    try:
        logger.info(f"Starting restore from: {backup_path}")

        if not force:
            print("\nWARNING: This will overwrite current 2FAuth SQLite database!")
            print(f"Backup: {backup_path}")
            confirmation = input('Type "RESTORE" to continue: ')
            if confirmation.strip() != "RESTORE":
                logger.info("Restore cancelled by user")
                return False

        temp_dir = tempfile.mkdtemp(prefix='2fauth-restore-')
        local_backup = download_backup(backup_path, temp_dir)
        logger.info(f"Backup available at: {local_backup}")

        if is_encrypted(local_backup):
            logger.info("Decrypting backup...")
            decrypted_path = local_backup + '.decrypted'
            if not decrypt_file(local_backup, decrypted_path):
                raise RuntimeError("Failed to decrypt backup")
            local_backup = decrypted_path

        extract_dir = os.path.join(temp_dir, 'extracted')
        logger.info(f"Extracting archive to {extract_dir}...")
        if not extract_archive(local_backup, extract_dir):
            raise RuntimeError("Failed to extract archive")

        contents = list_archive_contents(local_backup)
        logger.info(f"Extracted contents: {contents}")

        db_candidates = [
            os.path.join(extract_dir, name)
            for name in os.listdir(extract_dir)
            if name.endswith('.sqlite') or name == 'database_backup'
        ]

        if not db_candidates:
            raise FileNotFoundError("SQLite backup file not found in archive")

        db_backup_path = db_candidates[0]

        db_handler = SQLiteHandler()

        target_db = get_env('DB_DATABASE', '/2fauth/database.sqlite')
        safety_backup = f"{target_db}.safety-{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        if os.path.exists(target_db):
            shutil.copy2(target_db, safety_backup)
            logger.info(f"Safety backup created: {safety_backup}")

        if not db_handler.restore(db_backup_path):
            raise RuntimeError("SQLite restore failed")

        backup_id = os.path.basename(backup_path).replace('.tar.gz.gpg', '').replace('.tar.gz', '')
        notifier = get_notification_manager()
        notifier.notify_restore_success(backup_id, target_db)

        logger.info("Restore completed successfully")
        logger.info(f"Safety backup available at: {safety_backup}")

        return True

    except Exception as e:
        logger.exception(f"Restore failed: {e}")

        backup_id = os.path.basename(backup_path).replace('.tar.gz.gpg', '').replace('.tar.gz', '')
        notifier = get_notification_manager()
        notifier.notify_restore_failure(backup_id, str(e))

        return False

    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.debug(f"Cleaned up temp directory: {temp_dir}")


def main():
    """Main entry point."""
    load_config()

    parser = argparse.ArgumentParser(
        description='Restore 2FAuth from backup',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python restore.py --list                    # List cloud backups (sqlite only)
  python restore.py --list --all              # List all backups
  python restore.py --list --source local     # List local backups
  python restore.py --restore-latest          # Restore latest cloud backup
  python restore.py --restore-latest --source local
  python restore.py --restore r2:bucket/2fauth-backup-20260224_020000-sqlite.tar.gz.gpg
        """
    )

    parser.add_argument('--list', action='store_true',
                        help='List available backups for current database type')
    parser.add_argument('--all', action='store_true',
                        help='Show all backups regardless of database type')
    parser.add_argument('--source', choices=['cloud', 'local'], default='cloud',
                        help='Backup source (default: cloud)')
    parser.add_argument('--restore-latest', action='store_true',
                        help='Restore the most recent backup')
    parser.add_argument('--restore', metavar='BACKUP',
                        help='Restore specific backup (local path or remote:path)')
    parser.add_argument('--force', action='store_true',
                        help='Skip confirmation prompt')

    args = parser.parse_args()

    if args.list:
        backups = list_available_backups(args.source, include_all=args.all)

        if not backups:
            print(f"No backups found in {args.source}")
            return

        header = f"Available backups ({args.source})"
        if args.all:
            header += " - ALL TYPES"
        else:
            header += " - SQLITE only"

        print(f"\n{header}:")
        print("-" * 100)
        print(f"{'Name':<60} {'Size':>12} {'Modified':>20}")
        print("-" * 100)

        for backup in backups:
            name = backup['name'][:59]
            size = format_bytes(backup.get('size', 0))
            mod_time = backup.get('mod_time', 'unknown')
            if isinstance(mod_time, (int, float)):
                mod_time = datetime.fromtimestamp(mod_time).strftime('%Y-%m-%d %H:%M:%S')
            print(f"{name:<60} {size:>12} {mod_time:>20}")

        print("-" * 100)
        print(f"Total: {len(backups)} backup(s) displayed")
        print()

    elif args.restore_latest:
        backups = list_available_backups(args.source)

        if not backups:
            logger.error(f"No backups found in {args.source}")
            sys.exit(1)

        latest = backups[0]
        backup_spec = latest.get('full_remote', latest['path'])
        logger.info(f"Restoring latest backup: {latest['name']}")
        success = restore_backup(backup_spec, args.force)
        sys.exit(0 if success else 1)

    elif args.restore:
        success = restore_backup(args.restore, args.force)
        sys.exit(0 if success else 1)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
