# Thunderbird Setup

Connect Thunderbird to your Radicale calendar.

## Prerequisites

- Radicale is running on the VPS (see `README.md`)
- You know the Radicale username/password and the calendar name

## Steps

1. Open Thunderbird.
2. Open the **Calendar** tab.
3. Right-click in the calendar list (left sidebar) → **New Calendar…**.
4. Choose **On the Network** → Next.
5. Enter:
   - **Username**: `<radicale user>`
   - **Location**: `https://calendar.leo-nicolle.fr/<username>/<calendar-name>/`
6. Click **Find Calendars** or **Next**. If auto-discovery fails, enter the URL manually.
7. Thunderbird prompts for the password on first sync — enter the Radicale password.

## Example

| Field    | Value                                    |
| -------- | ---------------------------------------- |
| Username | `leo`                                    |
| Location | `https://calendar.leo-nicolle.fr/leo/calendar/` |

## Notes

- The calendar is created automatically on first write in some clients. If
  Thunderbird complains the collection does not exist, create it first via the
  Radicale web UI (`https://calendar.leo-nicolle.fr/`), or use a URL that ends
  in a new calendar name and let Thunderbird create it.
- **HTTPS**: Radicale listens on `127.0.0.1:5232`; nginx terminates TLS at
  `calendar.leo-nicolle.fr` (see `README.md`). Always use `https://`.

## Troubleshooting

- **401 Unauthorized**: wrong username/password, or the htpasswd file was not
  created. Re-run `htpasswd -B /etc/radicale/users <username>`.
- **Connection refused**: nginx or Radicale not running. Check
  `systemctl status radicale` and `systemctl status nginx`.
