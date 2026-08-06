# Gmail + Google Drive Setup (Email Delivery)

Reports are emailed via **Gmail (OAuth2)**. Small reports are attached; large ones are
uploaded to **Google Drive**, shared as "anyone with the link", and the Drive link is
emailed (so external recipients can download). This needs an OAuth **refresh token**
that carries **both** scopes:

```
https://www.googleapis.com/auth/gmail.send    (send email)
https://www.googleapis.com/auth/drive.file    (upload large reports to Drive)
```

---

## Part A — Google Cloud Console (one-time)

1. Open **https://console.cloud.google.com/** and select the project that owns your
   OAuth client (the one your `GMAIL_CLIENT_ID` belongs to).
2. **Enable APIs:** APIs & Services → **Library** → enable **Gmail API** and
   **Google Drive API**.
3. **OAuth consent screen** → **Scopes** → add both scopes above.
4. If the consent screen is in **Testing** mode, add your sender
   (`zaryab.ansari@eocean.net`) under **Test users**.
5. **Credentials** → open your OAuth **client** → under **Authorized redirect URIs** add:
   ```
   https://developers.google.com/oauthplayground
   ```
   → **Save**.

---

## Part B — Get the refresh token (OAuth Playground)

1. Open **https://developers.google.com/oauthplayground/**
2. Click the **⚙️ gear** (top-right) → check **"Use your own OAuth credentials"** →
   paste your **Client ID** and **Client secret**.
3. In **Step 1**, scroll to **"Input your own scopes"** and paste **both** (space-separated):
   ```
   https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/drive.file
   ```
4. **Authorize APIs** → sign in as your sender → **Allow** both permissions.
   (If it warns the app isn't verified: **Advanced → Go to (app)** — it's your own app.)
5. On **Step 2**, click **"Exchange authorization code for tokens"**.
6. Copy the **`refresh_token`** (starts with `1//…`).

> **No `refresh_token` returned?** Google already issued one for this account+app. Go to
> **https://myaccount.google.com/permissions**, remove the app, then repeat steps 4–6 to
> force a fresh consent.

---

## Part C — Configure and redeploy

1. In `backend/.env` (no inline comments):
   ```ini
   EMAIL_ENABLED=true
   EMAIL_PROVIDER=gmail
   PUBLIC_API_BASE_URL=http://<SERVER_IP>/api/v1
   GMAIL_CLIENT_ID=...
   GMAIL_CLIENT_SECRET=...
   GMAIL_REFRESH_TOKEN=1//<the-new-token>
   GMAIL_TOKEN_URI=https://oauth2.googleapis.com/token
   GMAIL_SENDER=zaryab.ansari@eocean.net
   GDRIVE_FOLDER_ID=            # optional
   # set to 0 to send ALL reports via Drive links (no attachments):
   EMAIL_MAX_ATTACHMENT_BYTES=10485760
   ```
2. Reload the containers that send email (no rebuild needed):
   ```bash
   docker compose -f deploy/docker-compose.prod.yml up -d --force-recreate api worker
   ```

---

## Part D — Test

On a completed job → **Email report** → enter a recipient. The **Live log** console
shows the steps (and the Drive upload percentage for large reports); the delivery list
shows **SENT**.

If it shows **FAILED**, read the `error` on the job page:
- `403 … insufficient … scopes` → the refresh token lacks `drive.file` (redo Part B).
- token/auth errors → re-check `GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN`.

> The email is sent by the **worker** container — that's why Part C recreates `worker`.
