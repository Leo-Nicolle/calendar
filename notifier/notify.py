#!/usr/bin/env python3
import argparse
import configparser
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from dateutil.rrule import rrulestr
from icalendar import Calendar

DEFAULT_ENV = "/etc/radicale-notifier/env"
DEFAULT_CONFIG = "/etc/radicale-notifier/config.ini"
DEFAULT_STATE = "/var/lib/radicale-notifier/sent.json"

DEFAULTS = {
    "radicale": {"url": "http://localhost:5232/", "username": "", "calendar": ""},
    "reminder": {
        "minutes_before": "30",
        "lookback_minutes": "5",
        "timezone": "Europe/Paris",
        "all_day_time": "09:00",
    },
    "sms": {"message_template": "Rappel : {summary} à {time}"},
    "logging": {"file": "/var/log/radicale-notifier/notifier.log"},
}


def load_env(path):
    data = {}
    file = Path(path)
    if not file.exists():
        return data
    for line in file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def load_config(path):
    parser = configparser.ConfigParser()
    parser.read_dict(DEFAULTS)
    parser.read(path)
    return parser


def load_state(path):
    file = Path(path)
    if not file.exists():
        return {}
    try:
        return json.loads(file.read_text())
    except (json.JSONDecodeError, OSError):
        logging.warning("Could not read state file %s; starting empty", path)
        return {}


def save_state(path, state):
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(state, indent=2, sort_keys=True))


def parse_time(value):
    hour, minute = value.split(":")
    return int(hour), int(minute)


def get_dtstart(component):
    if "dtstart" not in component:
        return None, None
    prop = component["dtstart"]
    return prop.dt, prop.params.get("TZID")


def resolve_tz(dt, tzid, default_tz):
    if isinstance(dt, datetime) and dt.tzinfo is not None:
        return dt.tzinfo
    if tzid:
        try:
            return ZoneInfo(tzid)
        except ZoneInfoNotFoundError:
            pass
    return default_tz


def expand_occurrences(component, default_tz, all_day_time, after_utc, before_utc):
    dt, tzid = get_dtstart(component)
    if dt is None:
        return []

    tz = resolve_tz(dt, tzid, default_tz)

    if isinstance(dt, datetime):
        naive = dt.replace(tzinfo=None)
    elif isinstance(dt, date):
        hour, minute = all_day_time
        naive = datetime(dt.year, dt.month, dt.day, hour, minute)
    else:
        return []

    rule = None
    if "rrule" in component:
        try:
            rule = rrulestr(component["rrule"].to_ical().decode(), dtstart=naive)
        except (ValueError, TypeError):
            logging.warning("Could not parse RRULE; treating event as single occurrence")

    after_naive = after_utc.astimezone(tz).replace(tzinfo=None)
    before_naive = before_utc.astimezone(tz).replace(tzinfo=None)

    if rule is not None:
        starts = rule.between(after_naive, before_naive, inc=True)
    else:
        starts = [naive] if after_naive <= naive <= before_naive else []

    return [s.replace(tzinfo=tz).astimezone(timezone.utc) for s in starts]


def send_sms(user, key, message):
    try:
        response = requests.get(
            "https://smsapi.free-mobile.fr/sendmsg",
            params={"user": user, "pass": key, "msg": message},
            timeout=15,
        )
    except requests.RequestException as exc:
        logging.error("Free API request failed: %s", exc)
        return False
    if response.status_code == 200:
        logging.info("SMS sent: %s", message)
        return True
    logging.error("Free API error HTTP %s: %s", response.status_code, response.text)
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description="Send SMS reminders for Radicale events via Free Mobile.")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--env", default=DEFAULT_ENV)
    parser.add_argument("--state", default=DEFAULT_STATE)
    parser.add_argument("--dry-run", action="store_true", help="Log messages without sending SMS")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    env = load_env(args.env)

    log_file = config.get("logging", "file", fallback=DEFAULTS["logging"]["file"])
    if log_file in ("", "-", "stdout", "stderr"):
        handlers = [logging.StreamHandler()]
        streaming = True
    else:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers = [logging.FileHandler(log_file)]
        streaming = False
    if args.dry_run and not streaming:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)

    radicale = config["radicale"]
    reminder = config["reminder"]
    sms = config["sms"]

    free_user = env.get("FREE_USER", "")
    free_key = env.get("FREE_API_KEY", "")
    if not free_user or not free_key:
        logging.error("FREE_USER/FREE_API_KEY missing from %s", args.env)
        return 1

    radicale_password = env.get("RADICALE_PASSWORD", "")
    url = radicale.get("url", "").rstrip("/")
    username = radicale.get("username", "")
    calendar_name = radicale.get("calendar", "")
    if not (url and username and calendar_name and radicale_password):
        logging.error("Radicale settings incomplete (url/username/calendar and RADICALE_PASSWORD)")
        return 1

    minutes_before = int(reminder.get("minutes_before", "30"))
    lookback = int(reminder.get("lookback_minutes", "5"))
    try:
        local_tz = ZoneInfo(reminder.get("timezone", "Europe/Paris"))
    except ZoneInfoNotFoundError:
        logging.error("Unknown timezone: %s", reminder.get("timezone"))
        return 1
    all_day_time = parse_time(reminder.get("all_day_time", "09:00"))

    now = datetime.now(timezone.utc)
    after = now - timedelta(minutes=lookback)
    before = now + timedelta(minutes=minutes_before)

    ics_url = f"{url}/{username}/{calendar_name}/"
    try:
        response = requests.get(ics_url, auth=(username, radicale_password), timeout=15)
    except requests.RequestException as exc:
        logging.error("Radicale request failed: %s", exc)
        return 1
    if response.status_code != 200:
        logging.error("Radicale returned HTTP %s for %s", response.status_code, ics_url)
        return 1

    try:
        calendar = Calendar.from_ical(response.content)
    except Exception as exc:
        logging.error("Failed to parse calendar data: %s", exc)
        return 1

    state = load_state(args.state)
    template = sms.get("message_template", DEFAULTS["sms"]["message_template"])

    for component in calendar.walk("VEVENT"):
        uid = str(component.get("uid", "no-uid"))
        summary = str(component.get("summary", "Sans titre"))
        for occ_utc in expand_occurrences(component, local_tz, all_day_time, after, before):
            key = f"{uid}::{occ_utc.isoformat()}"
            if key in state:
                continue
            message = template.format(
                summary=summary,
                time=occ_utc.astimezone(local_tz).strftime("%H:%M"),
            )
            if args.dry_run:
                logging.info("DRY-RUN would send: %s", message)
                continue
            if send_sms(free_user, free_key, message):
                state[key] = now.isoformat()

    cutoff = now - timedelta(days=30)
    state = {k: v for k, v in state.items() if v >= cutoff.isoformat()}
    save_state(args.state, state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
