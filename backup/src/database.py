"""SQLite database backup handler for 2FAuth."""

import os
import shutil
import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger('2fauth-backup')


class SQLiteHandler:
    """Handler for SQLite database backups using hot backup."""

    def __init__(self, database_path: str = None):
        self.db_path = Path(database_path or os.getenv('DB_DATABASE', '/2fauth/database.sqlite'))

    def backup(self, output_path: str) -> bool:
        """Create a hot backup of SQLite database."""
        if not self.db_path.exists():
            logger.error(f"SQLite database not found at {self.db_path}")
            return False

        try:
            conn = sqlite3.connect(str(self.db_path))
            backup_conn = sqlite3.connect(output_path)

            with backup_conn:
                conn.backup(backup_conn)

            backup_conn.close()
            conn.close()

            logger.info(f"SQLite database backed up to {output_path}")
            return True

        except Exception as e:
            logger.error(f"SQLite backup failed: {e}")
            return False

    def restore(self, backup_path: str) -> bool:
        """Restore SQLite database from backup."""
        try:
            source_path = Path(backup_path)
            if not source_path.exists() or not source_path.is_file():
                logger.error(f"SQLite backup file is invalid: {backup_path}")
                return False

            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            target_owner = self.db_path.parent.stat()

            for ext in ['-wal', '-shm', '-journal']:
                sidecar_path = Path(f"{self.db_path}{ext}")
                if sidecar_path.exists():
                    try:
                        sidecar_path.unlink()
                    except Exception as e:
                        logger.warning(f"Could not remove sidecar file {sidecar_path}: {e}")

            temp_path = self.db_path.with_suffix(self.db_path.suffix + '.restore_tmp')
            if temp_path.exists():
                temp_path.unlink()

            shutil.copy2(str(source_path), str(temp_path))
            os.chmod(temp_path, 0o664)
            os.replace(temp_path, self.db_path)

            if target_owner is not None:
                try:
                    os.chown(self.db_path, target_owner.st_uid, target_owner.st_gid)
                except (PermissionError, AttributeError) as e:
                    logger.warning(f"Could not set ownership for {self.db_path}: {e}")

            logger.info(f"SQLite database restored from {backup_path}")
            return True

        except Exception as e:
            logger.error(f"SQLite restore failed: {e}")
            return False

    def get_info(self) -> dict:
        """Get SQLite database information."""
        info = {
            'type': 'sqlite',
            'path': str(self.db_path),
            'size_bytes': 0,
            'page_count': 0,
            'page_size': 0,
            'journal_mode': 'unknown'
        }

        if self.db_path.exists():
            info['size_bytes'] = self.db_path.stat().st_size
            try:
                conn = sqlite3.connect(str(self.db_path))
                cursor = conn.cursor()

                cursor.execute("PRAGMA page_count")
                info['page_count'] = cursor.fetchone()[0]

                cursor.execute("PRAGMA page_size")
                info['page_size'] = cursor.fetchone()[0]

                cursor.execute("PRAGMA journal_mode")
                info['journal_mode'] = cursor.fetchone()[0]

                conn.close()
            except Exception as e:
                logger.warning(f"Could not get SQLite info: {e}")

        return info
