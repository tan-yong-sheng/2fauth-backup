#!/usr/bin/env python3
"""
2FAuth Backup - Main backup script.

Creates automated, encrypted, cloud-backed backups of 2FAuth SQLite database.
"""

import sys
import time
import tempfile
import shutil
from datetime import datetime

from utils import (
    setup_logging, load_config, get_env, generate_backup_filename,
    format_bytes
)
from database import SQLiteHandler
from archive import create_archive
from encryption import encrypt_file
from storage import upload_to_all_destinations
from retention import cleanup_all_backups, should_delete_local_after_upload
from notifications import get_notification_manager

try:
    from croniter import croniter
except ImportError:
    print("Error: croniter not installed. Run: pip install croniter")
    sys.exit(1)

logger = setup_logging()


def create_backup() -> bool:
    """Execute a complete backup operation."""
    start_time = time.time()
    temp_dir = None
    backup_id = 'unknown'

    try:
        backup_dir = get_env('BACKUP_DIR', '/backups')
        encryption_key = get_env('BACKUP_ENCRYPTION_KEY')

        temp_dir = tempfile.mkdtemp(prefix='2fauth-backup-')
        logger.debug(f"Using temp directory: {temp_dir}")

        db_handler = SQLiteHandler()
        db_info = db_handler.get_info()
        db_type = db_info.get('type', 'sqlite')

        backup_id = generate_backup_filename(db_type)
        logger.info(f"Starting backup: {backup_id}")

        db_backup_path = f"{temp_dir}/database_backup.sqlite"
        if not db_handler.backup(db_backup_path):
            raise RuntimeError("SQLite backup failed")

        archive_name = f"{backup_id}.tar.gz"
        archive_path = f"{backup_dir}/{archive_name}"

        if not create_archive([db_backup_path], archive_path, compression='gz'):
            raise RuntimeError("Failed to create archive")

        archive_size = db_info.get('size_bytes', 0)
        logger.info(f"Archive created: {archive_path} ({format_bytes(archive_size)})")

        if encryption_key:
            encrypted_path = archive_path + '.gpg'
            if not encrypt_file(archive_path, encrypted_path, encryption_key):
                raise RuntimeError("Encryption failed")
            archive_path = encrypted_path
            logger.info(f"Archive encrypted: {archive_path}")

        logger.info("Uploading to cloud destinations...")
        upload_success, failed_destinations = upload_to_all_destinations(archive_path)

        if not upload_success:
            logger.warning(f"Failed to upload to some destinations: {failed_destinations}")
        else:
            logger.info("Upload completed successfully")

        if should_delete_local_after_upload() and upload_success and not failed_destinations:
            import os
            if os.path.exists(archive_path):
                os.remove(archive_path)
                logger.info("Local backup deleted after successful upload")

        retention_days = int(get_env('BACKUP_RETENTION_DAYS', '30'))
        if retention_days > 0:
            logger.info(f"Running retention cleanup (retention: {retention_days} days)...")
            cleanup_stats = cleanup_all_backups(retention_days)
            logger.info(f"Retention cleanup completed: {cleanup_stats}")

        duration = time.time() - start_time
        notifier = get_notification_manager()
        notifier.notify_backup_success(backup_id, archive_path, archive_size, duration)

        logger.info(f"Backup completed successfully in {duration:.2f} seconds")
        return True

    except Exception as e:
        duration = time.time() - start_time
        logger.exception(f"Backup failed: {e}")

        notifier = get_notification_manager()
        notifier.notify_backup_failure(backup_id, str(e), duration)

        return False

    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.debug(f"Cleaned up temp directory: {temp_dir}")


def run_scheduler():
    """Run the backup scheduler loop."""
    schedule = get_env('BACKUP_SCHEDULE', '0 2 * * *')

    try:
        itr = croniter(schedule, datetime.utcnow())
        logger.info(f"Backup scheduler started with schedule: {schedule}")
    except Exception as e:
        logger.error(f"Invalid cron schedule: {schedule} - {e}")
        sys.exit(1)

    if get_env('BACKUP_RUN_ON_START', 'false').lower() == 'true':
        logger.info("Running backup on startup (BACKUP_RUN_ON_START=true)")
        create_backup()

    while True:
        next_run = itr.get_next(datetime)
        wait_seconds = (next_run - datetime.utcnow()).total_seconds()

        if wait_seconds > 0:
            logger.info(f"Next backup scheduled for: {next_run.isoformat()} (in {wait_seconds:.0f} seconds)")
            time.sleep(wait_seconds)

        logger.info("Starting scheduled backup...")
        create_backup()
        itr = croniter(schedule, datetime.utcnow())


def main():
    """Main entry point."""
    load_config()

    if len(sys.argv) > 1 and sys.argv[1] == '--now':
        logger.info("Running backup immediately (--now flag)")
        success = create_backup()
        sys.exit(0 if success else 1)

    run_scheduler()


if __name__ == '__main__':
    main()
