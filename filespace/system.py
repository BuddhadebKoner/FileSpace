from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path


try:
    import qrcode
    HAVE_QRCODE = True
except Exception:  # pragma: no cover
    qrcode = None
    HAVE_QRCODE = False


def local_ips() -> list[str]:
    found = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in found:
                found.append(ip)
    except OSError:
        pass
    return found


def browser_host(host: str, port: int) -> str:
    if host in ("0.0.0.0", ""):
        ips = [ip for ip in local_ips() if not ip.startswith("127.")]
        host = ips[0] if ips else "127.0.0.1"
    elif host == "::":
        host = "127.0.0.1"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{port}"


def print_terminal_qr(url: str) -> bool:
    if not HAVE_QRCODE or qrcode is None:
        return False
    try:
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(out=sys.stdout, tty=False)
        return True
    except Exception:
        return False


def shortcut_icon_path(script_path: Path) -> Path | None:
    """Return the best local logo file for a Windows shortcut icon."""
    app_dir = script_path.resolve().parent
    for filename in ("logo.ico", "logo.png"):
        candidate = app_dir / filename
        if candidate.is_file():
            return candidate
    return None


def create_desktop_shortcut(script_path: Path, env_path: Path) -> None:
    """Create or update the FileSpace launcher shortcut for this user."""
    powershell = r"""
$ErrorActionPreference = 'Stop'
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop 'File Server.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $env:FILESPACE_SHORTCUT_TARGET
$shortcut.Arguments = $env:FILESPACE_SHORTCUT_ARGUMENTS
$shortcut.WorkingDirectory = $env:FILESPACE_SHORTCUT_WORKING_DIRECTORY
$shortcut.Description = 'Start the FileSpace server'
if ($env:FILESPACE_SHORTCUT_ICON) {
    $shortcut.IconLocation = "$($env:FILESPACE_SHORTCUT_ICON),0"
}
$shortcut.Save()
Write-Output $shortcutPath
"""
    try:
        environment = os.environ.copy()
        cmd = Path(os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"))
        python = str(sys.executable)
        arguments = f'/k ""{python}" "{script_path}" --env "{env_path}""'
        environment.update({
            "FILESPACE_SHORTCUT_TARGET": str(cmd),
            "FILESPACE_SHORTCUT_ARGUMENTS": arguments,
            "FILESPACE_SHORTCUT_WORKING_DIRECTORY": str(script_path.parent),
        })
        icon_path = shortcut_icon_path(script_path)
        if icon_path is not None:
            environment["FILESPACE_SHORTCUT_ICON"] = str(icon_path)
        result = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-Command", powershell,
            ],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        shortcut = Path(result.stdout.strip().splitlines()[-1])
        print(f" Shortcut    : {shortcut}")
    except (OSError, subprocess.CalledProcessError) as e:
        detail = e.stderr.strip() if isinstance(e, subprocess.CalledProcessError) and e.stderr else str(e)
        print(f" WARNING     : could not create desktop shortcut ({detail})", flush=True)

