# 2FAuth Backup

SQLite-focused backup/restore system for [2FAuth](https://github.com/Bubka/2FAuth), modeled after the workflow and structure of [shiori-backup](https://github.com/tan-yong-sheng/shiori-backup).

## Features

- Scheduled backups with cron expression (`BACKUP_SCHEDULE`)
- Manual backup trigger (`python backup.py --now`)
- SQLite hot-backup and restore
- `tar.gz` archive output
- Optional GPG encryption (`.tar.gz.gpg`)
- Cloud upload via rclone (R2/S3/B2/etc.)
- Local and cloud retention cleanup
- Webhook/SMTP notifications

## Project Structure

```text
2fauth-backup/
├── docker-compose.yml
└── backup/
    ├── Dockerfile
    ├── requirements.txt
    ├── .env.example
    ├── rclone.conf.example
    └── src/
        ├── backup.py
        ├── restore.py
        ├── database.py
        ├── archive.py
        ├── encryption.py
        ├── storage.py
        ├── retention.py
        ├── notifications.py
        └── utils.py
```

## Setup

1. Copy environment file:

```bash
cp backup/.env.example backup/.env
```

2. Configure rclone:

```bash
cp backup/rclone.conf.example backup/rclone.conf
```

3. Start services:

```bash
docker-compose up -d
```

## Usage

Run commands exactly through the backup service container.

### Backup

```bash
docker-compose exec backup python backup.py --now
```

### List backups

```bash
# Cloud (default)
docker-compose exec backup python restore.py --list

# Local
docker-compose exec backup python restore.py --list --source local

# Include all types
docker-compose exec backup python restore.py --list --all
```

### Restore

Stop 2FAuth before restore to avoid SQLite write contention.

```bash
# Latest cloud backup
docker-compose stop 2fauth
docker-compose exec backup python restore.py --restore-latest --force
docker-compose start 2fauth

# Specific backup (cloud)
docker-compose stop 2fauth
docker-compose exec backup python restore.py --restore r2:bucket/2fauth-backup-YYYYMMDD_HHMMSS-sqlite.tar.gz.gpg --force
docker-compose start 2fauth

# Specific backup (local)
docker-compose stop 2fauth
docker-compose exec backup python restore.py --restore /backups/2fauth-backup-YYYYMMDD_HHMMSS-sqlite.tar.gz.gpg --force
docker-compose start 2fauth
```

## Naming Convention

```text
2fauth-backup-YYYYMMDD_HHMMSS-sqlite.tar.gz
2fauth-backup-YYYYMMDD_HHMMSS-sqlite.tar.gz.gpg
```

## Main Environment Variables

- `DB_DATABASE` (default: `/2fauth/database.sqlite`)
- `BACKUP_DIR` (default: `/backups`)
- `BACKUP_ENCRYPTION_KEY`
- `BACKUP_RCLONE_DESTINATIONS`
- `BACKUP_SCHEDULE`
- `BACKUP_RETENTION_DAYS`
- `BACKUP_RUN_ON_START`
- `BACKUP_DELETE_LOCAL_AFTER_UPLOAD`
- `BACKUP_WEBHOOK_URL`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_TO`

## Notes

- `backup/rclone.conf` contains secrets and should not be committed.
- The service stores local backups in docker volume `2fauth_backups` mounted at `/backups`.
