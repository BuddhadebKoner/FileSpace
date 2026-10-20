# FileSpace

FileSpace is a personal web file browser for Windows. It is read-only by
default, with an optional authenticated upload mode. Clone the repository,
answer the terminal setup questions, and run one Python command to browse a
folder or an entire drive from a browser.

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
- Keep the shared filesystem read-only by default.
- Optionally allow authenticated users to create folders and upload permitted
  file types when uploads are enabled during setup.

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
python .\fileserver.py
```

When `python .\fileserver.py` is started in an interactive terminal, FileSpace
asks setup questions first and saves the answers before generating the startup
QR code. Use `--no-setup` only for scripted runs that should reuse existing
saved settings.

Example answers:

| Question | Example answer | What it does |
| --- | --- | --- |
| `FILESPACE_ROOT` | `D:\Shared` | Shares this folder or drive |
| `FILESPACE_CREATE_SHORTCUT` | `Y` | Creates/updates `File Server.lnk` on the Desktop |
| `Use QR login?` | `Y` | Prints a one-time QR login code in the terminal |
| `FILESPACE_PUBLIC` | `N` | Restricts login page access to this PC and allowed IPs |
| `FILESPACE_ALLOWED_IPS` | `192.168.1.0/24` | Allows devices on that network |
| `CANDIDATE_FILE_UPLOAD_ENABLED` | `Y` | Enables folder creation and uploads |
| `Use default FILESPACE_UPLOAD_MAX_MB=1000?` | `Y` | Allows uploads up to 1000 MB each |

If you answer `N` to `Use QR login?`, FileSpace asks for `FILESPACE_EMAIL` and
`FILESPACE_PASSWORD` and uses those credentials instead of a terminal QR code.

The shared root must point to an existing readable folder or drive. A smaller
folder such as `D:\Shared` is usually more efficient and safer than sharing
the entire drive. The shortcut is created on the Windows Desktop selected by
Windows, including a OneDrive-managed Desktop.

## Access modes

Login is required in every mode. Choose the mode that matches how you use
FileSpace.

### Same Wi-Fi or local network

Allow your home or office subnet only by answering `N` to `FILESPACE_PUBLIC`,
then entering your subnet at `FILESPACE_ALLOWED_IPS`.

Use the actual subnet shown by your router. Common examples are
`192.168.0.0/24`, `192.168.1.0/24`, `10.0.0.0/24`, or a private Tailscale
range.

### Public login page

Any reachable device can open the login page when you answer `Y` to
`FILESPACE_PUBLIC`.

This is useful only when a VPN, firewall, router rule, or HTTPS reverse proxy
already protects the server. Public mode does not make plain HTTP safe for
direct internet exposure.

### IP-restricted access

Allow only selected devices or networks by answering `N` to `FILESPACE_PUBLIC`
and then entering those values at `FILESPACE_ALLOWED_IPS`.

Individual IPv4 addresses and CIDR ranges can be separated by commas, spaces,
or semicolons, for example `192.168.1.25, 192.168.1.0/24,
100.101.102.103`.

Devices outside the allowlist are rejected before the login page. The local
computer running FileSpace is always allowed.

The startup output and **Server health** panel show the active access mode.

## Select the shared root

Share the whole `D:\` drive by answering `D:\` at `FILESPACE_ROOT`, or pass it
for one run:

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
| `--root` | saved root, or `D:\` | Folder or drive to share for one run |
| `--host` | `0.0.0.0` | Address to listen on |
| `--port` | `6789` | HTTP port |
| `--env` | saved file beside the script | Path to saved setup answers |
| `--log` | `logs.txt` beside the script | Activity log |
| `--no-setup` | off | Skip interactive setup prompts |

Run `python .\fileserver.py --help` for the complete command reference.

## Setup Questions

The setup questions are the normal way to configure FileSpace. Run the server,
answer the prompts, and FileSpace saves the answers for later runs.

| Question | Answer format |
| --- | --- |
| `FILESPACE_ROOT` | Existing folder or drive, such as `D:\Shared` |
| `FILESPACE_CREATE_SHORTCUT` | `Y` or `N` |
| `Use QR login?` | `Y` for QR, `N` for email/password |
| `FILESPACE_EMAIL` | Asked only when QR login is disabled |
| `FILESPACE_PASSWORD` | Asked only when QR login is disabled |
| `FILESPACE_PUBLIC` | `Y` to allow any reachable device to open login, `N` to use an allowlist |
| `FILESPACE_ALLOWED_IPS` | Asked only when public mode is disabled |
| `CANDIDATE_FILE_UPLOAD_ENABLED` | `Y` or `N` |
| `Use default FILESPACE_UPLOAD_MAX_MB=1000?` | `Y` for 1000 MB, `N` to enter a custom limit |

### Candidate folder creation and uploads

Candidate write access is controlled by the `CANDIDATE_FILE_UPLOAD_ENABLED`
setup question. When disabled, the upload and new-folder UI is hidden and the
backend rejects `/api/upload` and `/api/folder` requests with a forbidden
response. When enabled, authenticated users can create folders inside the
shared root and upload allowed files into the current folder.

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

Answer `N` to `Use QR login?` if you want to use email/password login instead.

Only one FileSpace server can use the same port at a time. If you start it
again while another terminal is already serving that port, the new run exits
with a clear message instead of taking over the old terminal.

## Security and privacy

Sharing `D:\` exposes every readable file under that drive to an authenticated
user. Use a smaller `--root` when whole-drive access is not necessary.

- Prefer restricted access unless you are behind a VPN, firewall, or reverse
  proxy you trust.
- Use a strong, unique password if password login is enabled.
- QR login is authentication, not encryption; plain HTTP still exposes traffic
  to devices that can observe the network.
- Prefer a private LAN or VPN.
- Do not expose the built-in HTTP server directly to the public internet.
- Plain HTTP does not encrypt passwords or files in transit.
- The application folder, saved setup answers, and logs are excluded from sharing.
- The server is read-only unless uploads are enabled during setup.
- If candidate writes are enabled, authenticated users can create folders and
  upload files under the shared root, subject to the configured allowlist and
  size limit.
- Do not commit saved setup answers, `logs.txt`, or personal files.

For internet access, use a properly configured VPN or an HTTPS reverse proxy
with additional authentication and access controls.

## Logs and troubleshooting

Activity is written to `logs.txt`. The startup output and health panel report
the shared-folder state, disk space, login configuration, access mode, and
thumbnail support.

Check the environment:

```powershell
python --version
python .\fileserver.py --help
```

If a device cannot connect, check the selected access mode, the IP/CIDR value,
Windows Firewall, and whether both devices are on the same network or VPN.

## Repository layout

```text
FileSpace/
|-- fileserver.py       # Backward-compatible launcher
|-- filespace/          # Server package
|   |-- app.py          # CLI startup and server wiring
|   |-- routes.py       # HTTP routes and request handler
|   |-- settings.py     # Saved setup parsing and live config reloads
|   |-- constants.py    # Shared limits, defaults, and security headers
|   |-- uploads.py      # Upload validation and rate limiting
|   |-- ui/             # HTML templates for app, login, and QR auth
|-- .gitignore          # Excludes secrets, logs, and local artifacts
|-- README.md           # This guide
```

## License

Add a `LICENSE` file before publishing if you want others to reuse or modify
FileSpace. The MIT License is a common choice for a personal utility project.
