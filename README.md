# FileSpace

FileSpace is a lightweight, private web file browser for Windows. Clone the
repository, configure one environment file, and run one Python command to
browse a selected folder or an entire drive from any browser on your trusted
network.

## Features

- Browse folders and files from a clean web interface.
- Share a complete drive, such as `D:\`, or a smaller folder.
- Preview images, videos, audio, PDFs, and text files in the browser.
- Play MKV videos in the browser through server-side FFmpeg transcoding.
- Stream large files with HTTP range support for seeking.
- Search recursively within the shared folder.
- Login protection, IP/CIDR allowlisting, session expiry, login throttling,
  security headers, and activity logging.
- Read-only by design: no uploads, edits, renames, or deletes.

## Requirements

- Windows 10 or later.
- Python 3.10 or later.
- FFmpeg available as `ffmpeg.exe` on `PATH` for MKV browser playback.
- A trusted network or VPN such as Tailscale.

FileSpace itself uses Python's standard library. Pillow is optional and only
improves image thumbnail generation.

## Quick start

Open PowerShell:

```powershell
git clone https://github.com/YOUR-USERNAME/filespace.git
cd filespace
Copy-Item .env.example .env
notepad .env
```

Set a real email and a strong password in `.env`. For access from other
devices, either set `FILESPACE_PUBLIC=true` or add the device/network IPs to
`FILESPACE_ALLOWED_IPS`.

Start FileSpace:

```powershell
python .\fileserver.py
```

Open the printed network URL in a browser, for example:

```text
http://192.168.1.20:6789/
```

The default shared root is `D:\`.

## Choose what to share

Share the whole `D:\` drive:

```powershell
python .\fileserver.py --root D:\
```

Share only a folder:

```powershell
python .\fileserver.py --root "D:\Videos"
```

Other options:

```powershell
python .\fileserver.py --root D:\ --host 0.0.0.0 --port 6789
```

Use `python .\fileserver.py --help` for all options.

## FFmpeg for browser video playback

`ffmpeg-python` is not required. FileSpace uses the normal system
`ffmpeg.exe` executable.

Install FFmpeg using an elevated PowerShell if Chocolatey is available:

```powershell
choco install ffmpeg -y
```

Verify it:

```powershell
ffmpeg -version
```

Restart FileSpace after installing FFmpeg. The Server health panel should
report:

```text
Browser video: FFmpeg is available for MKV playback
```

The first time an MKV is opened, FileSpace creates a cached browser-compatible
MP4 in the system temporary directory. The original file is never modified.

## Configuration

`.env` is created automatically if it does not exist. You can also copy
`.env.example` manually.

| Setting | Description |
| --- | --- |
| `FILESPACE_EMAIL` | Login email |
| `FILESPACE_PASSWORD` | Login password; use at least 8 characters |
| `FILESPACE_ALLOWED_IPS` | Comma-separated IP addresses or CIDR ranges |
| `FILESPACE_PUBLIC` | `false` restricts access to allowed IPs; `true` allows the login page from any device |

Examples:

```ini
FILESPACE_EMAIL=me@example.com
FILESPACE_PASSWORD=use-a-long-unique-password
FILESPACE_ALLOWED_IPS=192.168.1.0/24,100.101.102.103
FILESPACE_PUBLIC=false
```

The settings file is re-read automatically when it changes.

## Security and privacy

This application can expose every readable file under the selected root. Do
not expose it directly to the public internet.

- Use `FILESPACE_PUBLIC=false` whenever possible.
- Prefer a VPN or private LAN.
- Use a strong, unique password.
- Do not commit `.env`, `logs.txt`, or credentials.
- Plain HTTP does not encrypt passwords or files in transit.
- The FileSpace application folder, `.env`, and logs are excluded from sharing.
- The server is read-only; it cannot change files on the shared drive.

If internet access is required, place FileSpace behind a properly configured
HTTPS reverse proxy and VPN or another strong access-control layer.

## Logs and troubleshooting

Activity is written to `logs.txt`. The health panel and startup output show:

- shared-folder accessibility;
- free disk space;
- login and network configuration;
- FFmpeg availability;
- thumbnail capability.

Common checks:

```powershell
python --version
Get-Command ffmpeg
Test-Path .\.env
```

If the browser cannot play an MKV, confirm `ffmpeg -version` works in the same
PowerShell environment used to start FileSpace, then restart the server.

## Repository layout

```text
filespace/
|-- fileserver.py       # Complete FileSpace server and web UI
|-- .env.example        # Safe configuration template
|-- .gitignore          # Prevents credentials, logs, caches, and local files
|-- README.md           # Setup, usage, and security documentation
```

## License

Choose and add a license before publishing this repository. The MIT License
is a suitable option if you want others to reuse and modify FileSpace.
