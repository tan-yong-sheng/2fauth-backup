"""Utility functions for 2fauth-backup."""

import os
import sys
import json
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv


def setup_logging(log_level: Optional[str] = None) -> logging.Logger:
    """Configure logging with proper formatting."""
    if log_level is None:
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        stream=sys.stdout
    )
    return logging.getLogger('2fauth-backup')


def load_config():
    """Load environment variables from .env file if present."""
    env_path = Path('/app/.env')
    if env_path.exists():
        load_dotenv(env_path)
    load_dotenv(Path('.env'))


def get_env(key: str, default=None, required: bool = False):
    """Get environment variable with optional default and required check."""
    value = os.getenv(key, default)
    if required and value is None:
        raise ValueError(f"Required environment variable {key} is not set")
    return value


def calculate_sha256(file_path: str) -> str:
    """Calculate SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def generate_backup_filename(db_type: str = 'sqlite') -> str:
    """Generate a timestamped backup filename with database type."""
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    return f"2fauth-backup-{timestamp}-{db_type}"


def format_bytes(size_bytes: int) -> str:
    """Format bytes to human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


class BackupMetadata:
    """Class to handle backup metadata."""

    def __init__(self, backup_id: str, source: str):
        self.backup_id = backup_id
        self.source = source
        self.timestamp = datetime.utcnow().isoformat()
        self.files = {}
        self.database_info = {}
        self.hostname = os.getenv('HOSTNAME', 'unknown')

    def add_file(self, file_path: str, relative_path: str):
        """Add a file to metadata with checksum."""
        if os.path.exists(file_path):
            self.files[relative_path] = {
                'checksum': calculate_sha256(file_path),
                'size': os.path.getsize(file_path)
            }

    def set_database_info(self, **kwargs):
        """Set database backup information."""
        self.database_info = kwargs

    def to_dict(self) -> dict:
        """Convert metadata to dictionary."""
        return {
            'backup_id': self.backup_id,
            'timestamp': self.timestamp,
            'source': self.source,
            'hostname': self.hostname,
            'database': self.database_info,
            'files': self.files
        }

    def save(self, output_path: str):
        """Save metadata to JSON file."""
        with open(output_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, metadata_path: str):
        """Load metadata from JSON file."""
        with open(metadata_path, 'r') as f:
            data = json.load(f)

        instance = cls(data['backup_id'], data['source'])
        instance.timestamp = data['timestamp']
        instance.hostname = data['hostname']
        instance.database_info = data.get('database', {})
        instance.files = data.get('files', {})
        return instance
