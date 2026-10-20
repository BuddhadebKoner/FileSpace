# FileSpace

FileSpace lets you open a folder or drive from a browser and browse your files
from another device. It starts from one command, asks a few setup questions in
the terminal, then shows a login QR code or login page.

It is read-only by default. You can choose to enable uploads during setup.

## Quick Start

Open PowerShell:

```powershell
git clone https://github.com/BuddhadebKoner/FileSpace.git
cd .\FileSpace
python .\fileserver.py
```

FileSpace will ask questions in the terminal. Answer them, then scan the QR
code or open the printed browser link.

## What It Can Do

- Browse files and folders from a web browser.
- Share one folder, such as `D:\Shared`, or a whole drive, such as `D:\`.
- Preview images, videos, audio, PDFs, and text files.
- Search inside the shared folder.
- Log in with a one-time QR code or email/password.
- Keep files read-only unless you enable uploads.
- Optionally create folders and upload allowed files.

## Requirements

- Windows 10 or later.
- Python 3.10 or later.
- A trusted Wi-Fi/LAN, private VPN, or HTTPS reverse proxy.

Optional:

- `qrcode` package for nicer terminal QR codes.
- Pillow for faster image thumbnails.
- FFmpeg for browser playback of MKV videos.

## Setup Questions

When you run FileSpace, answer the questions like this:

| Question | Example | Meaning |
| --- | --- | --- |
| `FILESPACE_ROOT` | `D:\Shared` | Folder or drive to share |
| `FILESPACE_CREATE_SHORTCUT` | `Y` | Create a Desktop shortcut |
| `Use QR login?` | `Y` | Use one-time QR login |
| `FILESPACE_PUBLIC` | `N` | Restrict who can open the login page |
| `FILESPACE_ALLOWED_IPS` | `192.168.1.0/24` | Allowed network or devices |
| `CANDIDATE_FILE_UPLOAD_ENABLED` | `N` | Keep FileSpace read-only |
| `Use default FILESPACE_UPLOAD_MAX_MB=1000?` | `Y` | Use 1000 MB upload limit |

If you answer `N` to `Use QR login?`, FileSpace asks for an email and password
instead.

Press Enter to keep the shown default on later runs.

## Which Access Mode Should I Choose?

For home Wi-Fi or office LAN, choose:

- `FILESPACE_PUBLIC`: `N`
- `FILESPACE_ALLOWED_IPS`: your local network, for example `192.168.1.0/24`

For VPN use, choose:

- `FILESPACE_PUBLIC`: `N`
- `FILESPACE_ALLOWED_IPS`: your VPN range or device IPs

For public internet access, use HTTPS and extra protection. Plain HTTP is not
safe for direct internet exposure.

## How To Connect

After startup, FileSpace prints addresses such as:

```text
Local URL   : http://127.0.0.1:6789/
Network URL : http://192.168.1.10:6789/
```

Use the network URL on another phone, tablet, or computer on the allowed
network. If QR login is enabled, scan the QR code shown in the terminal.

## Common Commands

Run normally:

```powershell
python .\fileserver.py
```

Share a specific folder for one run:

```powershell
python .\fileserver.py --root "D:\Videos"
```

Use a different port:

```powershell
python .\fileserver.py --port 8080
```

Skip setup questions and reuse saved answers:

```powershell
python .\fileserver.py --no-setup
```

Show help:

```powershell
python .\fileserver.py --help
```

## Safety Notes

- Prefer sharing a smaller folder instead of a whole drive.
- Keep upload mode off unless you really need it.
- QR login protects access, but plain HTTP does not encrypt traffic.
- Use a VPN or HTTPS reverse proxy for anything beyond a trusted local network.
- Do not expose the built-in HTTP server directly to the public internet.
- Saved setup answers, app files, and logs are excluded from sharing.

## Troubleshooting

If another device cannot open FileSpace:

- Check that both devices are on the same Wi-Fi, LAN, or VPN.
- Check the IP/CIDR value you entered in `FILESPACE_ALLOWED_IPS`.
- Check Windows Firewall.
- Try opening the local URL on the computer running FileSpace first.
- Run `python .\fileserver.py --help` to confirm Python can start the app.

If the QR camera scanner does not open, use the printed login link instead.
Camera access works best on localhost or HTTPS.

## Videos

Setup video:

[Watch setup on YouTube](https://www.youtube.com/watch?v=l5ruuVoDug4)

Usage walkthrough:

[Open usage walkthrough video](https://res.cloudinary.com/dnnvq0dg6/video/upload/v1792480337/how_to_use_ds3wmv.mp4)

## More Documentation

- [Developer.md](Developer.md): core developer notes and inner working details.
- [docs/FLOW_AND_HTTPS.md](docs/FLOW_AND_HTTPS.md): full tool flow and how to
  move from HTTP to HTTPS.

## Repository Layout

```text
FileSpace/
|-- fileserver.py       # Main launcher
|-- filespace/          # Application package
|-- docs/               # Flow and HTTPS guide
|-- Developer.md        # Developer-facing documentation
|-- README.md           # This user guide
```

