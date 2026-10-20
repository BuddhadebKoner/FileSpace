# FileSpace

FileSpace is a personal, read-only web file browser for Windows. Clone the
repository, configure one `.env` file, and run one Python command to browse a
folder or an entire drive from a browser.

Repository: <https://github.com/BuddhadebKoner/FileSpace>

## What it does

- Browse folders and files from a responsive web interface.
- Share an entire drive, such as `D:\`, or only one folder.
- Preview images, videos, audio, PDFs, and text files in the browser.
- Play MKV files through server-side FFmpeg transcoding to browser-compatible
  MP4 with AAC audio.
- Stream large files with HTTP range support for seeking.
- Search recursively within the selected root.
- Protect access with email/password login, IP allowlisting, throttling,
  session expiry, security headers, and activity logs.
- Keep the shared filesystem read-only: no upload, edit, rename, or delete
  operations are provided.

## Requirements

- Windows 10 or later.
- Python 3.10 or later.
- FFmpeg available as `ffmpeg.exe` on `PATH` for MKV browser playback.
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

Set a real email and a long, unique password in `.env`. Then start the server:

```powershell
python .\fileserver.py
```

Open the network URL printed by the server, for example:

```text
http://192.168.1.20:6789/
```

The default shared root is `D:\`.

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
| `--root` | `D:\` | Folder or drive to share |
| `--host` | `0.0.0.0` | Address to listen on |
| `--port` | `6789` | HTTP port |
| `--env` | `.env` beside the script | Settings file |
| `--log` | `logs.txt` beside the script | Activity log |

Run `python .\fileserver.py --help` for the complete command reference.

## Browser video playback

FileSpace uses the normal system `ffmpeg.exe`; the Python packages
`ffmpeg-python` and `imageio-ffmpeg` are not required.

Install FFmpeg with Chocolatey from an elevated PowerShell:

```powershell
choco install ffmpeg -y
```

Verify it in the same PowerShell environment used to start FileSpace:

```powershell
Get-Command ffmpeg
ffmpeg -version
```

Restart FileSpace after installing FFmpeg. Server health should show:

```text
Browser video: FFmpeg is available for MKV playback
```

When an MKV is opened for the first time, FileSpace creates a cached,
browser-compatible MP4 in the system temporary directory. The source video is
not changed. Subsequent playback reuses the cache when the source file has not
changed.

## Configuration

`.env` is ignored by Git and must never be committed. Start from
[.env.example](./.env.example):

```ini
FILESPACE_EMAIL=me@example.com
FILESPACE_PASSWORD=use-a-long-unique-password
FILESPACE_ALLOWED_IPS=192.168.1.0/24
FILESPACE_PUBLIC=false
```

| Setting | Description |
| --- | --- |
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
the shared-folder state, disk space, login configuration, access mode, FFmpeg,
and thumbnail support.

Check the environment:

```powershell
python --version
Get-Command ffmpeg
Test-Path .\.env
```

If MKV playback fails:

1. Run `ffmpeg -version`.
2. Confirm the command works in the same PowerShell used to start the server.
3. Stop FileSpace with `Ctrl+C`.
4. Start it again with `python .\fileserver.py`.
5. Check **Server health** and retry the video.

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
