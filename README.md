# Radicale Calendar + Free Mobile SMS Notifications

Self-hosted CalDAV server (Radicale) on an OVH VPS, synced with Thunderbird,
with free SMS reminders to a French Free Mobile number — all via Docker.

Reminder default: **30 minutes before**, SMS in **French**.

## Repository layout

```
docker-compose.yml         # Radicale + notifier containers
docker/radicale/config     # Radicale config (inside container)
docker/radicale/users      # htpasswd (generated, gitignored)
docker/notifier/           # notifier Dockerfile + config + env + entrypoint
notifier/notify.py         # the SMS notifier script (built into the image)
notifier/requirements.txt
nginx/calendar.leo-nicolle.fr.conf   # reverse proxy (HTTP base, certbot adds TLS)
docs/
```

## Setup

### 1. Create the Radicale user

```bash
docker run --rm httpd:alpine htpasswd -Bbn leo '<password>' > docker/radicale/users
```

### 2. Configure the notifier

```bash
cp docker/notifier/env.example docker/notifier/env
```

Edit:

- `docker/notifier/env` — `RADICALE_PASSWORD`, `FREE_USER`, `FREE_API_KEY`
  (see `docs/free-mobile-setup.md`).
- `docker/notifier/config.ini` — `username`, `calendar`.

### 3. Start

```bash
docker compose up -d --build
```

### 4. Verify

```bash
curl -u leo:password http://localhost:5232/
docker logs -f radicale-notifier
```

The notifier polls every `NOTIFIER_INTERVAL` seconds (default 300) inside the
container and logs to stdout (`docker logs radicale-notifier`). State is kept in
the `notifier-state` volume; calendar data in `radicale-data`.

### 5. HTTPS (nginx + Let's Encrypt)

```bash
apt install -y nginx certbot python3-certbot-nginx
install -m 0644 nginx/calendar.leo-nicolle.fr.conf /etc/nginx/sites-available/
ln -s /etc/nginx/sites-available/calendar.leo-nicolle.fr.conf /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d calendar.leo-nicolle.fr
```

Then use `https://calendar.leo-nicolle.fr/<username>/<calendar-name>/` in
Thunderbird (see `docs/thunderbird-setup.md`). The container publishes Radicale
on `127.0.0.1:5232`, so it is never exposed publicly.

## Testing

```bash
# dry-run: shows what would be sent, without sending
docker compose exec notifier python /opt/radicale-notifier/notify.py --dry-run

# actually send
docker compose exec notifier python /opt/radicale-notifier/notify.py
```

## How the notifier works

1. Reads secrets from `docker/notifier/env` and settings from
   `docker/notifier/config.ini` (mounted into the container).
2. Fetches the calendar `.ics` from Radicale with basic auth.
3. Parses events (including recurring events via RRULE).
4. Finds occurrences starting within the reminder window
   (`minutes_before` = 30, with a small `lookback_minutes` tolerance).
5. Deduplicates via `sent.json` in the `notifier-state` volume
   (key = event UID + occurrence timestamp), so it never sends twice.
6. Sends each new reminder via the Free Mobile SMS API and logs the result.

## Configuration reference

`docker/notifier/config.ini`:

| Key | Default | Description |
| --- | --- | --- |
| `radicale.url` | `http://radicale:5232/` | Radicale base URL (container service name) |
| `radicale.username` | — | Radicale user |
| `radicale.calendar` | — | Calendar name |
| `reminder.minutes_before` | `30` | Reminder lead time |
| `reminder.lookback_minutes` | `5` | Catch-up tolerance for delayed runs |
| `reminder.timezone` | `Europe/Paris` | Timezone used to render times |
| `reminder.all_day_time` | `09:00` | Effective start for all-day events |
| `sms.message_template` | `Rappel : {summary} à {time}` | `{summary}` and `{time}` placeholders |
| `logging.file` | `stdout` | Log destination (`stdout`, or a file path) |

Secrets live in `docker/notifier/env` (not `config.ini`): `RADICALE_PASSWORD`,
`FREE_USER`, `FREE_API_KEY`, `FREE_PHONE` (reference only).

## Operations

- **Logs**: `docker compose logs -f radicale-notifier`
- **Restart**: `docker compose restart`
- **Rebuild notifier** (after changing code): `docker compose up -d --build`
- **Backups**: the calendar data lives in the `radicale-data` volume. Back it up
  with, e.g.:
  ```bash
  docker run --rm -v calendar_radicale-data:/data -v "$PWD":/backup alpine \
    tar czf /backup/radicale-data-$(date +%F).tar.gz -C /data .
  ```

## Security notes

- Secrets are only in `docker/notifier/env` and `docker/radicale/users` (both
  gitignored).
- Radicale is not published publicly — only `127.0.0.1:5232`; nginx terminates
  TLS.
- Radicale 3 supports `auth.delay` for brute-force protection; fail2ban can
  watch the nginx access log.
