<p align="center">
  <img src="../logo.png" alt="FileSpace logo" width="128">
</p>

# FileSpace Flow And HTTPS Guide

This document explains how FileSpace works from startup to browser usage, and
how to move access from plain HTTP to HTTPS.

Related docs:

- [README.md](../README.md): simple user guide.
- [Developer.md](../Developer.md): core developer notes.

## 1. Startup Flow

1. User runs:

   ```powershell
   python .\fileserver.py
   ```

2. `fileserver.py` imports `filespace.app.main()`.

3. `filespace/app.py` builds CLI options:

   - `--root`
   - `--host`
   - `--port`
   - `--env`
   - `--log`
   - `--no-setup`

4. If running in an interactive terminal and `--no-setup` is not used,
   `filespace/setup_wizard.py` asks setup questions and saves the answers.

5. `filespace/settings.py` reads the saved answers and builds a `Settings`
   object.

6. `filespace/app.py` creates shared runtime services:

   - `ActivityLog`
   - `ConfigStore`
   - `SessionStore`
   - `QrLoginStore`
   - login throttles
   - upload rate limiter
   - thumbnail cache
   - MKV playback cache

7. `filespace/routes.py` creates the HTTP request handler.

8. `ThreadingHTTPServer` starts on the chosen host and port.

9. If QR login is enabled, FileSpace creates one short-lived QR token and
   prints a QR code or one-time login link in the terminal.

## 2. Setup Question Flow

The normal configuration flow is terminal-driven. Every yes/no prompt uses
`[Y/n]`, so pressing Enter chooses `Y`.

1. `FILESPACE_ROOT`
   User enters the folder or drive to share.

2. `FILESPACE_CREATE_SHORTCUT`
   `Y` creates/updates the Desktop shortcut with the FileSpace logo.

3. `Use QR login?`
   `Y` sets QR login. `N` switches to email/password login.

4. `FILESPACE_EMAIL` and `FILESPACE_PASSWORD`
   Asked only when QR login is disabled.

5. `FILESPACE_PUBLIC`
   `Y` allows any reachable device to open the login page. `N` uses an
   allowlist.

6. `FILESPACE_ALLOWED_IPS`
   Asked only when public mode is disabled.

7. `CANDIDATE_FILE_UPLOAD_ENABLED`
   Controls whether authenticated users can create folders and upload files.

8. `FILESPACE_UPLOAD_MAX_MB`
   Pressing Enter keeps the shown upload limit, which defaults to 1000 MB.

## 3. Request Flow

### Public Pages

- `GET /healthz`
  Minimal liveness check. Still respects IP allowlist.

- `GET /`
  Shows either the FileSpace app or the login page.

- `GET /auth/qr`
  Opens the QR login consumer page.

### Login APIs

- `POST /auth/qr/consume`
  Validates a one-time QR token and creates a session cookie.

- `POST /login`
  Validates email/password and creates a session cookie.

- `POST /logout`
  Destroys the current session cookie.

### File APIs

All `/api/*` routes require a valid session.

- `GET /api/list`
  Lists files and folders for a relative path.

- `GET /api/search`
  Searches recursively under the current folder.

- `GET /api/download`
  Downloads a file as an attachment.

- `GET /api/file`
  Serves a previewable file inline.

- `GET /api/playback`
  Serves browser-compatible playback for MKV files through FFmpeg conversion.

- `GET /api/thumb`
  Serves image thumbnails when Pillow is available.

- `GET /api/health`
  Returns detailed health checks for the UI.

- `GET /api/keepalive`
  Extends the active session timeout.

### Write APIs

These routes require login and upload mode to be enabled.

- `POST /api/folder`
  Creates a folder under the shared root.

- `POST /api/upload`
  Validates and stores one uploaded file.

## 4. Security Flow

FileSpace has several protection layers:

1. IP access check
   Requests are rejected before login if the client is not allowed.

2. Login
   QR login or email/password login creates a session cookie.

3. Session expiry
   Sessions expire after inactivity and after a maximum lifetime.

4. Path resolution
   Relative paths are normalized and must stay inside the shared root.

5. Hidden/system exclusions
   Hidden files, system folders, app files, saved setup, and logs are not
   shared.

6. Upload validation
   Uploads are checked by extension, content type, file signature, size, and
   rate limits.

7. Security headers
   Responses include content type, frame, referrer, cache, and CSP headers.

## 5. Current HTTP Model

FileSpace currently runs a standard-library HTTP server:

```text
Browser/device -> http://host:6789 -> FileSpace Python server
```

This is simple and good for trusted LAN or VPN use, but plain HTTP does not
encrypt passwords, session cookies, file names, or file contents in transit.

## 6. Recommended HTTPS Model

The safest upgrade is to keep FileSpace on local HTTP and put an HTTPS reverse
proxy in front of it:

```text
Browser/device -> https://your-domain -> reverse proxy -> http://127.0.0.1:6789
```

Recommended server command:

```powershell
python .\fileserver.py --host 127.0.0.1 --port 6789
```

Binding to `127.0.0.1` means only the local reverse proxy can reach FileSpace
directly.

## 7. Option A: Caddy Reverse Proxy

Caddy is the easiest HTTPS option when you have a domain pointing to the
machine.

Example `Caddyfile`:

```caddyfile
files.example.com {
    reverse_proxy 127.0.0.1:6789
}
```

Then start FileSpace:

```powershell
python .\fileserver.py --host 127.0.0.1 --port 6789
```

With Caddy, HTTPS certificates and HTTP-to-HTTPS redirects are usually handled
by Caddy.

## 8. Option B: Nginx Reverse Proxy

Example Nginx site:

```nginx
server {
    listen 80;
    server_name files.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name files.example.com;

    ssl_certificate     C:/path/to/fullchain.pem;
    ssl_certificate_key C:/path/to/privkey.pem;

    client_max_body_size 1000M;

    location / {
        proxy_pass http://127.0.0.1:6789;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Then start FileSpace:

```powershell
python .\fileserver.py --host 127.0.0.1 --port 6789
```

## 9. Option C: HTTPS Inside Python

This is possible, but less flexible than a reverse proxy. You would wrap
`ThreadingHTTPServer` with Python's `ssl` module.

Conceptual code location:

- `filespace/app.py`
- after `ThreadingHTTPServer((args.host, args.port), handler)`
- before `serve_forever()`

Conceptual code:

```python
import ssl

context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain("cert.pem", "key.pem")
httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
```

You would also add CLI options such as:

- `--tls-cert cert.pem`
- `--tls-key key.pem`

This makes FileSpace itself speak HTTPS:

```text
Browser/device -> https://host:6789 -> FileSpace Python server
```

Reverse proxy is still recommended because it handles certificates, redirects,
large upload tuning, and production TLS behavior better.

## 10. Code Changes Needed For First-Class HTTPS Support

If you want FileSpace to fully understand HTTPS, add these features:

1. Public URL setting

   Add a setup question or CLI option:

   ```text
   FILESPACE_PUBLIC_URL=https://files.example.com
   ```

   Use this URL when printing QR links. Currently QR startup URLs are built in
   `filespace/app.py` with `browser_host(args.host, args.port)`, which produces
   an `http://...` URL.

2. Secure cookies

   In `filespace/routes.py`, update session cookies when HTTPS is enabled:

   ```text
   HttpOnly; SameSite=Strict; Secure; Path=/; Max-Age=...
   ```

   Only add `Secure` when the app is actually behind HTTPS, otherwise cookies
   will not work over plain HTTP.

3. Reverse proxy trust

   FileSpace currently checks the socket client IP. Behind a reverse proxy, the
   socket client is usually `127.0.0.1`, not the real device IP.

   If you want FileSpace itself to enforce the original client IP, add trusted
   proxy handling for `X-Forwarded-For`. Only trust that header from known local
   proxy IPs.

4. Optional HTTP-to-HTTPS redirect

   If using Caddy or Nginx, let the proxy redirect HTTP to HTTPS.

   If serving HTTPS directly from Python, add an HTTP listener that redirects to
   the HTTPS port.

## 11. Important HTTPS Notes

- HTTPS protects traffic in transit. It does not replace login.
- Keep QR login or password login enabled.
- For public internet access, prefer VPN plus HTTPS, or HTTPS reverse proxy
  with additional access controls.
- If using a reverse proxy, bind FileSpace to `127.0.0.1`.
- If upload mode is enabled, set the reverse proxy body-size limit to at least
  the FileSpace upload limit.
- Browser camera QR scanning works much more reliably on HTTPS than plain
  LAN HTTP.

## 12. Best Upgrade Path For This Project

Recommended path:

1. Keep FileSpace's built-in server as HTTP on localhost.
2. Add Caddy or Nginx in front.
3. Bind FileSpace with:

   ```powershell
   python .\fileserver.py --host 127.0.0.1 --port 6789
   ```

4. Configure the proxy domain, for example:

   ```text
   https://files.example.com
   ```

5. Add a future `FILESPACE_PUBLIC_URL` setting so the terminal QR code prints
   the HTTPS URL instead of the local HTTP URL.

