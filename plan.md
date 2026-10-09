# Plan: Radicale Calendar + Free Mobile SMS Notifications on OVH VPS

## Goal
Deploy **Radicale** (CalDAV server) on a cheap OVH VPS, use **Thunderbird** as the desktop client, and send **free SMS reminders** to the user's own French Free Mobile number when calendar events are approaching.

## Environment Assumptions
- OVH VPS (cheapest tier, likely 1 vCPU / 2 GB RAM / Debian or Ubuntu)
- Root or sudo access
- User is a Free Mobile subscriber (French number)
- Thunderbird on desktop (native CalDAV support)
- No Docker required, but Docker is acceptable if preferred

---

## Phase 1 — Radicale Installation & Configuration

### Tasks
1. **System prep**
   - Update packages: `apt update && apt upgrade -y`
   - Install dependencies: `python3`, `python3-pip`, `python3-venv`, `curl`, `git`

2. **Install Radicale in a virtualenv**
   - Create dedicated user: `radicale`
   - Create venv at `/opt/radicale/venv`
   - `pip install radicale`
   - Install bcrypt: `pip install bcrypt` (for htpasswd hashing)

3. **Directory layout**
   ```
   /var/lib/radicale/collections/   # calendar data
   /etc/radicale/config              # main config
   /etc/radicale/users               # htpasswd file
   /var/log/radicale/                # logs
   ```
   - Set ownership to `radicale:radicale`

4. **Configure `/etc/radicale/config`**
   ```ini
   [server]
   hosts = 0.0.0.0:5232
   max_connections = 20

   [auth]
   type = htpasswd
   htpasswd_filename = /etc/radicale/users
   htpasswd_encryption = bcrypt

   [storage]
   filesystem_folder = /var/lib/radicale/collections

   [logging]
   level = info
   ```
   - **Important**: Radicale by default allows public access. Ensure `[rights]` config or set `type = authenticated` so only logged-in users can access.

5. **Create user**
   - `htpasswd -B -c /etc/radicale/users <username>`

6. **Systemd service**
   - Create `/etc/systemd/system/radicale.service` running the venv's `radicale` binary with `--config /etc/radicale/config`
   - `systemctl enable --now radicale`

7. **Firewall**
   - If using `ufw`: allow `5232/tcp` (or leave closed and only access via SSH tunnel / reverse proxy — user's choice)

8. **Verification**
   - `curl http://localhost:5232/` returns Radicale's web interface
   - Log in with created user via browser

### Acceptance Criteria
- Radicale is running under systemd and survives reboot
- User can authenticate via web UI
- A test calendar can be created

---

## Phase 2 — Thunderbird Client Setup (Manual / Documentation)

### Tasks
1. Write a short doc `docs/thunderbird-setup.md` for the user:
   - Open Thunderbird → Calendar tab → New Calendar → On the Network
   - Username: `<radicale user>`
   - Location: `http://<vps-ip>:5232/<username>/<calendar-name>/`
   - Thunderbird auto-discovers via `.well-known` (may need to enter URL manually)
   - Password prompt on first sync

2. Recommend **HTTPS via reverse proxy** (Caddy or nginx + Let's Encrypt) as an optional hardening step — document it but don't implement in Phase 2.

### Acceptance Criteria
- Doc exists with clear steps and example URLs
- (User validates manually)

---

## Phase 3 — Free Mobile SMS API Integration

### Prerequisites (user must do manually)
- Enable "Notification par SMS" in Free Mobile account
- Retrieve **User ID** and **API Key**
- Store them in `/etc/radicale-notifier/env` (chmod 600, owned by root or a dedicated `notifier` user):
  ```
  FREE_USER=12345678
  FREE_API_KEY=xxxxxxxxxxxx
  FREE_PHONE=+336xxxxxxxx   # optional, for reference only
  ```

### API Reference
- Endpoint: `GET https://smsapi.free-mobile.fr/sendmsg`
- Query params: `user`, `pass`, `msg` (URL-encoded)
- Success: HTTP 200
- Errors: 400 (bad request), 402 (rate limit), 403 (not enabled / bad creds), 500 (Free-side error)

### Tasks
1. **Create notifier script** at `/opt/radicale-notifier/notify.py`
   - Language: Python 3
   - Deps: `requests`, `icalendar`, `python-dateutil`, `pytz`
   - Behavior:
     - Read env file
     - Fetch `.ics` from Radicale: `http://localhost:5232/<user>/<calendar>/` with basic auth
     - Parse events with `icalendar`
     - Determine which events start within the reminder window (e.g., next 30–60 min)
     - Deduplicate: maintain a state file `/var/lib/radicale-notifier/sent.json` mapping event UID + occurrence → timestamp to avoid re-sending
     - For each matching event, call Free API with a short message like:
       `📅 {summary} à {HH:MM}`
     - Handle HTTP errors and log them
     - Exit cleanly

2. **Config file** at `/etc/radicale-notifier/config.ini`
   ```ini
   [radicale]
   url = http://localhost:5232/
   username = <radicale user>
   password = <radicale password>
   calendar = <calendar-name>

   [reminder]
   minutes_before = 30
   lookback_minutes = 5

   [logging]
   file = /var/log/radicale-notifier/notifier.log
   ```

3. **Logging**
   - Rotate logs via `logrotate` config in `/etc/logrotate.d/radicale-notifier`
   - Keep 7 days

4. **Cron job**
   - Run every 5 minutes:
     ```
     */5 * * * * notifier /opt/radicale-notifier/venv/bin/python /opt/radicale-notifier/notify.py
     ```
   - Or use a systemd timer (`radicale-notifier.timer`) — preferred for consistency

5. **Test harness**
   - Script `tests/test_notify.py` or `scripts/test_sms.sh` that sends a test SMS directly via Free API
   - Document expected HTTP codes

### Acceptance Criteria
- Running the script manually sends an SMS for an event within the reminder window
- Running it twice in a row does **not** send duplicate SMS (state file works)
- Errors are logged, not silently swallowed
- Cron/timer fires reliably every 5 minutes

---

## Phase 4 — Hardening & Operations (Optional / Recommended)

### Tasks
1. **HTTPS reverse proxy** (Caddy recommended for auto-TLS)
   - Caddyfile example: proxy `cal.example.com` → `localhost:5232`
   - Update Thunderbird doc to use `https://`

2. **Fail2ban** or Radicale's built-in brute-force protection
3. **Backups**: nightly `tar` of `/var/lib/radicale/collections/` to `/var/backups/` (and optionally offsite)
4. **Monitoring**: simple healthcheck script that verifies Radicale responds and notifier ran recently; email or SMS alert on failure (careful of SMS rate limits)

### Acceptance Criteria
- Backups run nightly and are restorable
- HTTPS works if implemented

---

## Deliverables Checklist

- [ ] `install-radicale.sh` — idempotent install script
- [ ] `/etc/radicale/config` — committed to repo as template
- [ ] `radicale.service` — systemd unit
- [ ] `/opt/radicale-notifier/notify.py` — notifier script
- [ ] `/opt/radicale-notifier/requirements.txt`
- [ ] `/etc/radicale-notifier/config.ini` — template
- [ ] `radicale-notifier.service` + `.timer` — systemd units
- [ ] `docs/thunderbird-setup.md`
- [ ] `docs/free-mobile-setup.md` — how to get API creds
- [ ] `README.md` — overview + quick start
- [ ] Test: `scripts/test_sms.sh`

---

## Open Questions for the User

1. **OS version** on the VPS? (affects apt packages & systemd syntax)
2. **Domain name** available for HTTPS, or is IP-only fine?
3. **Radicale port** — keep 5232 public, or restrict to localhost + reverse proxy?
4. **Reminder timing** — 30 min before? 1 hour? Both (multiple reminders)?
5. **Multiple calendars** or just one?
6. **Preferred language** for SMS content (French)?
7. **Password storage** for the notifier — plaintext in a root-owned file, or use a systemd credential / `pass`?

---

## Suggested Agent Execution Order

1. Confirm open questions with user
2. Phase 1 (Radicale) → verify
3. Phase 3 (notifier) → verify with a test SMS
4. Phase 2 (Thunderbird doc) → hand to user
5. Phase 4 (hardening) → only if user requests

Each phase should end with a **manual verification step** before moving on, especially the SMS send (to avoid burning test messages or triggering Free's rate limit).