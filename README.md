# FileSpace

FileSpace is a personal, read-only web file browser for Windows. Clone the
repository, configure one `.env` file, and run one Python command to browse a
folder or an entire drive from a browser.

Repository: <https://github.com/BuddhadebKoner/FileSpace>

## What it does

- Browse folders and files from a responsive web interface.
- Share an entire drive, such as `D:\`, or only one folder.
- Preview images, videos, audio, PDFs, and text files in the browser.
- Preview supported media files in the browser.
- Stream large files with HTTP range support for seeking.
- Search recursively within the selected root.
- Protect access with email/password login, IP allowlisting, throttling,
  session expiry, security headers, and activity logs.
- Keep the shared filesystem read-only: no upload, edit, rename, or delete
  operations are provided.

## Requirements

- Windows 10 or later.
- Python 3.10 or later.
- A trusted local network or a private VPN such as Tailscale.

The server uses Python's standard library. Pillow is optional and only
improves image thumbnail generation.

## Quick start

Open PowerShell and clone the repository:

```powershell
git clone https://github.com/BuddhadebKoner/FileSpace.git
cd .\FileSpace
Copy-Item .env.example .env
notepad .env
```

Set the folder or drive to share in `.env`. The repository can be cloned
anywhere; it does not need to be inside the shared folder:

```ini
FILESPACE_ROOT=D:\
FILESPACE_CREATE_SHORTCUT=false
```

For another installation, change this to a local path such as
`D:\Videos`. A command-line `--root` overrides `FILESPACE_ROOT` for one run.

Set `FILESPACE_CREATE_SHORTCUT=true` to create or update one `File Server.lnk`
shortcut on the current user's Desktop. The shortcut launches the same Python
script with the configured `.env` file and working directory. Set it back to
`false` to stop updating the shortcut; an existing shortcut is not deleted.

Set a real email and a long, unique password in `.env`, then start the server:

```powershell
python .\fileserver.py
```

On the first run, if `.env` does not exist, FileSpace creates it and asks you
to configure it before continuing. After saving the values above, run the
command again. The shortcut is then created automatically when
`FILESPACE_CREATE_SHORTCUT=true`.

Open the network URL printed by the server, for example:

```text
http://192.168.1.20:6789/
```

The default shared root is `D:\`.

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
FILESPACE_EMAIL=owner@example.com
FILESPACE_PASSWORD=replace-with-a-long-password
FILESPACE_ALLOWED_IPS=192.168.1.0/24
FILESPACE_PUBLIC=false
```

`FILESPACE_ROOT` must point to an existing readable folder or drive. A smaller
folder such as `D:\Shared` is usually more efficient and safer than sharing
the entire drive. The shortcut is created on the Windows Desktop selected by
Windows, including a OneDrive-managed Desktop.

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
FILESPACE_ALLOWED_IPS=192.168.1.0/24
FILESPACE_PUBLIC=false
```

| Setting | Description |
| --- | --- |
| `FILESPACE_ROOT` | Folder or drive to share; defaults to `D:\` |
| `FILESPACE_CREATE_SHORTCUT` | `true` creates or updates `File Server.lnk` on the Desktop; `false` disables shortcut creation |
| `FILESPACE_EMAIL` | Login email |
| `FILESPACE_PASSWORD` | Login password; use at least 8 characters |
| `FILESPACE_ALLOWED_IPS` | Allowed IPv4 addresses and CIDR ranges |
| `FILESPACE_PUBLIC` | `false` enforces the allowlist; `true` allows the login page from any reachable device |

## Security and privacy

Sharing `D:\` exposes every readable file under that drive to an authenticated
user. Use a smaller `--root` when whole-drive access is not necessary.

- Prefer `FILESPACE_PUBLIC=false`.
- Use a strong, unique password.
- Prefer a private LAN or VPN.
- Do not expose the built-in HTTP server directly to the public internet.
- Plain HTTP does not encrypt passwords or files in transit.
- The application folder, `.env`, and logs are excluded from sharing.
- The server is read-only; it cannot modify the shared drive.
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
|-- .env.example        # Safe settings template
|-- .gitignore          # Excludes secrets, logs, and local artifacts
|-- README.md           # This guide
```

## License

Add a `LICENSE` file before publishing if you want others to reuse or modify
FileSpace. The MIT License is a common choice for a personal utility project.
