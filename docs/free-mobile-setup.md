# Free Mobile SMS Notifications Setup

Get your Free Mobile API credentials to enable SMS reminders.

## Prerequisites

- You must be a Free Mobile subscriber (French number).

## Steps

1. Log in to your **Free Mobile account** (https://mobile.free.fr).
2. Go to **Mes Services** / **Notifications par SMS** (or
   "Mes informations personnelles" → "Notifications par SMS").
3. Enable **Notification par SMS**.
4. Note the **Identifiant** (User ID, 8 digits) and the **Clé d'identification**
   (API key). Free shows the key only once — copy it immediately.

## Fill the env file

On the VPS, edit `/etc/radicale-notifier/env` (root-owned, chmod 600):

```
RADICALE_PASSWORD=<radicale password>
FREE_USER=12345678
FREE_API_KEY=xxxxxxxxxxxxxxxx
FREE_PHONE=+336xxxxxxxx
```

## API Reference

- Endpoint: `GET https://smsapi.free-mobile.fr/sendmsg`
- Query parameters: `user`, `pass`, `msg` (URL-encoded)
- Responses:
  - `200` success
  - `400` missing/incorrect parameter
  - `402` too many messages (rate limit)
  - `403` service not enabled or bad credentials
  - `500` Free-side error

## Notes

- Free limits the number of SMS per day (rate limits return HTTP 402).
  The notifier deduplicates and only sends once per event, but keep the
  reminder cadence modest to avoid hitting the cap.
- The message is limited to ~160 characters and may not support emoji or
  accents reliably. The default template is `Rappel : {summary} à {time}`.

## Test

Send a test SMS:

```
scripts/test_sms.sh "Hello from radicale-notifier"
```

Expected output ends with `HTTP 200`.
