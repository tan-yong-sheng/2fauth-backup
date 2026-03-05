"""GPG encryption and decryption functions."""

import os
import subprocess
import logging
from typing import Optional

logger = logging.getLogger('2fauth-backup')


def encrypt_file(input_path: str, output_path: Optional[str] = None, passphrase: Optional[str] = None) -> bool:
    """Encrypt a file using GPG symmetric encryption (AES256)."""
    if passphrase is None:
        passphrase = os.getenv('BACKUP_ENCRYPTION_KEY')

    if not passphrase:
        logger.error("No encryption passphrase provided")
        return False

    if output_path is None:
        output_path = input_path + '.gpg'

    try:
        cmd = [
            'gpg',
            '--symmetric',
            '--cipher-algo', 'AES256',
            '--compress-algo', '1',
            '--batch',
            '--yes',
            '--passphrase-fd', '0',
            '--output', output_path,
            input_path
        ]

        result = subprocess.run(cmd, input=passphrase.encode(), capture_output=True)

        if result.returncode == 0:
            logger.info(f"Encrypted: {input_path} -> {output_path}")
            return True

        logger.error(f"GPG encryption failed: {result.stderr.decode()}")
        return False

    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        return False


def decrypt_file(input_path: str, output_path: Optional[str] = None, passphrase: Optional[str] = None) -> bool:
    """Decrypt a GPG encrypted file."""
    if passphrase is None:
        passphrase = os.getenv('BACKUP_ENCRYPTION_KEY')

    if not passphrase:
        logger.error("No decryption passphrase provided")
        return False

    if output_path is None:
        output_path = input_path[:-4] if input_path.endswith('.gpg') else input_path + '.decrypted'

    try:
        cmd = [
            'gpg',
            '--decrypt',
            '--batch',
            '--yes',
            '--passphrase-fd', '0',
            '--output', output_path,
            input_path
        ]

        result = subprocess.run(cmd, input=passphrase.encode(), capture_output=True)

        if result.returncode == 0:
            logger.info(f"Decrypted: {input_path} -> {output_path}")
            return True

        logger.error(f"GPG decryption failed: {result.stderr.decode()}")
        return False

    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return False


def is_encrypted(file_path: str) -> bool:
    """Check if a file is GPG encrypted by extension."""
    return file_path.endswith('.gpg')
