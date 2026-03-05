"""Archive creation and extraction functions."""

import os
import tarfile
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger('2fauth-backup')


def create_archive(source_paths: List[str], output_path: str, compression: str = 'gz') -> bool:
    """Create a compressed tar archive from source paths."""
    try:
        mode = 'w:' + compression if compression else 'w'
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

        with tarfile.open(output_path, mode) as tar:
            for source_path in source_paths:
                if not os.path.exists(source_path):
                    logger.warning(f"Source path does not exist: {source_path}")
                    continue
                tar.add(source_path, arcname=os.path.basename(source_path))

        archive_size = os.path.getsize(output_path)
        logger.info(f"Created archive: {output_path} ({archive_size} bytes)")
        return True

    except Exception as e:
        logger.error(f"Failed to create archive: {e}")
        return False


def extract_archive(archive_path: str, output_dir: str, specific_files: Optional[List[str]] = None) -> bool:
    """Extract a tar archive to the specified directory."""
    try:
        os.makedirs(output_dir, exist_ok=True)

        with tarfile.open(archive_path, 'r:*') as tar:
            if specific_files:
                for member in specific_files:
                    try:
                        tar.extract(member, output_dir)
                    except KeyError:
                        logger.warning(f"File not found in archive: {member}")
            else:
                tar.extractall(output_dir)

        logger.info(f"Extracted archive: {archive_path} to {output_dir}")
        return True

    except Exception as e:
        logger.error(f"Failed to extract archive: {e}")
        return False


def list_archive_contents(archive_path: str) -> List[str]:
    """List the contents of a tar archive."""
    try:
        with tarfile.open(archive_path, 'r:*') as tar:
            return tar.getnames()
    except Exception as e:
        logger.error(f"Failed to list archive contents: {e}")
        return []
