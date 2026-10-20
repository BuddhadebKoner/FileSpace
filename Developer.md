<p align="center">
  <img src="logo.png" alt="FileSpace logo" width="128">
</p>

# FileSpace

Developer-facing notes for FileSpace. For normal user setup, start with
[README.md](README.md). For the full runtime flow and HTTP-to-HTTPS upgrade
notes, see [docs/FLOW_AND_HTTPS.md](docs/FLOW_AND_HTTPS.md).

FileSpace is a personal web file browser for Windows. It can run read-only or
with authenticated uploads. Clone the repository, configure one `.env` file,
and run one Python command to browse a folder or an entire drive from a browser.

Repository: <https://github.com/BuddhadebKoner/FileSpace>

## What it does

- Browse folders and files from a responsive web interface.
- Share an entire drive, such as `D:\`, or only one folder.
- Preview images, videos, audio, PDFs, and text files in the browser.
- Preview supported media files in the browser.
- Stream large files with HTTP range support for seeking.
- Search recursively within the selected root.
- Protect access with QR-code login, optional email/password fallback, IP
  allowlisting, throttling, session expiry, security headers, and activity logs.
- Keep the shared filesystem read-only when upload mode is off.
- Optionally allow authenticated users to create folders and upload permitted
  file types when `CANDIDATE_FILE_UPLOAD_ENABLED=true`.

## Requirements

- Windows 10 or later.
- Python 3.10 or later.
- A trusted local network or a private VPN such as Tailscale.

The server uses Python's standard library for the core file browser. The
`qrcode` package is recommended for terminal QR login. Pillow is optional and
only improves image thumbnail generation.

## Setup and usage videos

### Setup

[![Watch setup on YouTube](https://img.shields.io/badge/YouTube-Watch%20setup-red?logo=youtube&logoColor=white)](https://www.youtube.com/watch?v=l5ruuVoDug4)

### How to use

<video src="https://res.cloudinary.com/dnnvq0dg6/video/upload/v1792480337/how_to_use_ds3wmv.mp4" controls width="100%" title="FileSpace usage walkthrough"></video>

[Open usage walkthrough video](https://res.cloudinary.com/dnnvq0dg6/video/upload/v1792480337/how_to_use_ds3wmv.mp4)

### Recommended installation flow

```powershell
git clone https://github.com/BuddhadebKoner/FileSpace.git
cd .\FileSpace
Copy-Item .env.example .env
notepad .env
python .\fileserver.py
```

Example `.env` values:

```ini
FILESPACE_ROOT=D:\Shared
FILESPACE_CREATE_SHORTCUT=true
FILESPACE_AUTH_MODE=qr
FILESPACE_ALLOWED_IPS=192.168.1.0/24
FILESPACE_PUBLIC=true
CANDIDATE_FILE_UPLOAD_ENABLED=true
FILESPACE_UPLOAD_MAX_MB=100
FILESPACE_UPLOAD_ALLOWED_EXTENSIONS=pdf,png,jpg,jpeg,gif,webp,bmp,mp4,m4v,mov,webm,mkv,ogv,txt,md,csv,json,docx,xlsx,pptx,rtf,odt,ods,odp
```

`FILESPACE_ROOT` must point to an existing readable folder or drive. A smaller
folder such as `D:\Shared` is usually more efficient and safer than sharing
the entire drive. The shortcut is created on the Windows Desktop selected by
Windows, including a OneDrive-managed Desktop, and uses the FileSpace logo when
`logo.ico` or `logo.png` is present beside `fileserver.py`.

## Access modes

Login is required in every mode. Choose the mode that matches how you use
FileSpace.

### Same Wi-Fi or local network

Allow your home or office subnet only:

```ini
FILESPACE_ALLOWED_IPS=192.168.1.0/24
FILESPACE_PUBLIC=false
```

Use the actual subnet shown by your router. Common examples are
`192.168.0.0/24`, `192.168.1.0/24`, `10.0.0.0/24`, or a private Tailscale
range.

### Public login page

Any reachable device can open the login page:

```ini
FILESPACE_ALLOWED_IPS=
FILESPACE_PUBLIC=true
```

This is useful only when a VPN, firewall, router rule, or HTTPS reverse proxy
already protects the server. Public mode does not make plain HTTP safe for
direct internet exposure.

### IP-restricted access

Allow only selected devices or networks:

```ini
FILESPACE_ALLOWED_IPS=192.168.1.25,192.168.1.40
FILESPACE_PUBLIC=false
```

Individual IPv4 addresses and CIDR ranges can be separated by commas, spaces,
or semicolons:

```ini
FILESPACE_ALLOWED_IPS=192.168.1.25, 192.168.1.0/24, 100.101.102.103
FILESPACE_PUBLIC=false
```

Devices outside the allowlist are rejected before the login page. The local
computer running FileSpace is always allowed.

Settings are reloaded automatically after `.env` is saved. The startup output
and **Server health** panel show the active access mode.

## Select the shared root

Share the whole `D:\` drive:

In `.env`:

```ini
FILESPACE_ROOT=D:\
```

Or for one run:

```powershell
python .\fileserver.py --root D:\
```

Share only a video folder:

```powershell
python .\fileserver.py --root "D:\Videos"
```

Use a different port:

```powershell
python .\fileserver.py --root D:\ --host 0.0.0.0 --port 8080
```

Available options:

| Option | Default | Purpose |
| --- | --- | --- |
| `--root` | `FILESPACE_ROOT` from `.env`, or `D:\` | Folder or drive to share for one run |
| `--host` | `0.0.0.0` | Address to listen on |
| `--port` | `6789` | HTTP port |
| `--env` | `.env` beside the script | Settings file |
| `--log` | `logs.txt` beside the script | Activity log |

Run `python .\fileserver.py --help` for the complete command reference.

## Configuration

`.env` is ignored by Git and must never be committed. Start from
[.env.example](./.env.example):

```ini
FILESPACE_ROOT=D:\
FILESPACE_CREATE_SHORTCUT=false
FILESPACE_EMAIL=me@example.com
FILESPACE_PASSWORD=use-a-long-unique-password
FILESPACE_AUTH_MODE=qr
FILESPACE_ALLOWED_IPS=192.168.1.0/24
FILESPACE_PUBLIC=false
```

| Setting | Description |
| --- | --- |
| `FILESPACE_ROOT` | Folder or drive to share; defaults to `D:\` |
| `FILESPACE_CREATE_SHORTCUT` | `true` creates or updates `File Server.lnk` on the Desktop with the FileSpace logo; `false` disables shortcut creation |
| `FILESPACE_EMAIL` | Login email for `password` or `both` auth modes |
| `FILESPACE_PASSWORD` | Login password for `password` or `both` auth modes; use at least 8 characters |
| `FILESPACE_AUTH_MODE` | `qr`, `password`, or `both`; defaults to QR login |
| `FILESPACE_ALLOWED_IPS` | Allowed IPv4 addresses and CIDR ranges |
| `FILESPACE_PUBLIC` | `false` enforces the allowlist; `true` allows the login page from any reachable device |
| `CANDIDATE_FILE_UPLOAD_ENABLED` | `true` lets authenticated users create folders and upload permitted files; set `false` for read-only sharing |
| `FILESPACE_UPLOAD_MAX_MB` | Per-file upload limit in MB; defaults to `1000` and is capped at `1000` |
| `FILESPACE_UPLOAD_ALLOWED_EXTENSIONS` | Comma-separated upload allowlist. Unsupported or executable-style extensions are ignored |

### Candidate folder creation and uploads

Candidate write access is controlled by one Boolean setting:

```ini
CANDIDATE_FILE_UPLOAD_ENABLED=false
```

When this value is missing, invalid, or `false`, the upload and new-folder UI is
hidden and the backend rejects `/api/upload` and `/api/folder` requests with a
forbidden response. When set to `true`, authenticated users can create folders
inside the shared root and upload allowed files into the current folder.

Uploads are stored with safe, unique server-generated filenames, so uploaded
filenames are never trusted for storage. The server validates extension,
declared MIME type, file signature or text shape, request size, per-file size,
and a simple per-IP upload quota before saving. The built-in server does not
include malware scanning; keep uploads on trusted networks and rely on your OS
or security tooling to scan the shared folder when needed.

## QR login

QR login is short-lived and single-use. On startup, FileSpace creates an
in-memory token, prints a terminal QR code when `qrcode` is installed, and
expires the token after 5 minutes. The QR code does not contain your password
or a permanent credential. If `qrcode` is not installed, FileSpace prints a
one-time login link instead. If the code expires, restart FileSpace to print a
fresh one.

The sign-in page also includes an **Open camera** button when QR login is
enabled. Camera scanning depends on the browser's built-in QR scanner support
and camera permissions. Some browsers block camera access on plain local-network
HTTP addresses; use localhost, HTTPS, or scan with the phone/device camera if
that happens.

Use `FILESPACE_AUTH_MODE=both` if you want QR login with the old
email/password form as a fallback. Use `FILESPACE_AUTH_MODE=password` to roll
back to the previous behavior.

Only one FileSpace server can use the same port at a time. If you start it
again while another terminal is already serving that port, the new run exits
with a clear message instead of taking over the old terminal.

## Security and privacy

Sharing `D:\` exposes every readable file under that drive to an authenticated
user. Use a smaller `--root` when whole-drive access is not necessary.

- Prefer `FILESPACE_PUBLIC=false`.
- Use a strong, unique password if password login is enabled.
- QR login is authentication, not encryption; plain HTTP still exposes traffic
  to devices that can observe the network.
- Prefer a private LAN or VPN.
- Do not expose the built-in HTTP server directly to the public internet.
- Plain HTTP does not encrypt passwords or files in transit.
- The application folder, `.env`, and logs are excluded from sharing.
- The server is read-only unless `CANDIDATE_FILE_UPLOAD_ENABLED=true`.
- If candidate writes are enabled, authenticated users can create folders and
  upload files under the shared root, subject to the configured allowlist and
  size limit.
- Do not commit `.env`, `logs.txt`, or personal files.

For internet access, use a properly configured VPN or an HTTPS reverse proxy
with additional authentication and access controls.

## Logs and troubleshooting

Activity is written to `logs.txt`. The startup output and health panel report
the shared-folder state, disk space, login configuration, access mode, and
thumbnail support.

Check the environment:

```powershell
python --version
Test-Path .\.env
```

If a device cannot connect, check the selected access mode, the IP/CIDR value,
Windows Firewall, and whether both devices are on the same network or VPN.

## Repository layout

```text
FileSpace/
|-- fileserver.py       # Complete server and web UI
|-- logo.png            # FileSpace logo for Markdown/docs
|-- logo.ico            # FileSpace icon for Windows shortcuts
|-- .env.example        # Safe settings template
|-- .gitignore          # Excludes secrets, logs, and local artifacts
|-- README.md           # This guide
```

## License

Add a `LICENSE` file before publishing if you want others to reuse or modify
FileSpace. The MIT License is a common choice for a personal utility project.
