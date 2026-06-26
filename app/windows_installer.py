from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
import winreg
import zipfile
from pathlib import Path


APP_NAME = "Codex Phone"
APP_EXE = "CodexPhone.exe"
PUBLISHER = "MaRuiZhiG"
APP_URL = "https://github.com/MaRuiZhiG/codex_phone"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\CodexPhone"
LOG_FILE = Path(tempfile.gettempdir()) / "codex-phone-installer.log"


def _log(message: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def _message(text: str, title: str = APP_NAME, flags: int = 0x40) -> int:
    return ctypes.windll.user32.MessageBoxW(None, text, title, flags)


def _app_version() -> str:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    version_file = root / "installer-version.txt"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8-sig").strip() or "0.1.0"
    return os.getenv("CODEX_PHONE_INSTALLER_VERSION", "0.1.0")


def _install_dir() -> Path:
    base = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Programs" / APP_NAME


def _start_menu_dir() -> Path:
    base = os.getenv("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP_NAME


def _desktop_dir() -> Path:
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"


def _payload_zip() -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    candidate = root / "payload" / "CodexPhone-payload.zip"
    if candidate.exists():
        return candidate
    candidate = Path(__file__).resolve().parent.parent / "build" / "installer" / "CodexPhone-payload.zip"
    if candidate.exists():
        return candidate
    raise FileNotFoundError("Installer payload was not found.")


def _run_powershell(script: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", encoding="utf-8", delete=False) as handle:
        handle.write(script)
        script_path = handle.name
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path],
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    finally:
        Path(script_path).unlink(missing_ok=True)


def _taskkill(image_name: str) -> None:
    subprocess.run(
        ["taskkill", "/IM", image_name, "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _stop_running_app(include_maintenance: bool = False) -> None:
    _taskkill(APP_EXE)
    if include_maintenance:
        _taskkill("CodexPhoneMaintenance.exe")


def _create_shortcut(shortcut: Path, target: Path, working_dir: Path, icon: Path) -> None:
    shortcut.parent.mkdir(parents=True, exist_ok=True)
    ps = f"""
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut({str(shortcut)!r})
$shortcut.TargetPath = {str(target)!r}
$shortcut.WorkingDirectory = {str(working_dir)!r}
$shortcut.IconLocation = {str(icon)!r}
$shortcut.Save()
"""
    _run_powershell(ps)


def _write_uninstall_registry(install_dir: Path, version: str) -> None:
    app_exe = install_dir / APP_EXE
    maintenance_exe = install_dir / "CodexPhoneMaintenance.exe"
    estimated_size = sum(path.stat().st_size for path in install_dir.rglob("*") if path.is_file()) // 1024
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, version)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, PUBLISHER)
        winreg.SetValueEx(key, "URLInfoAbout", 0, winreg.REG_SZ, APP_URL)
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(install_dir))
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, str(app_exe))
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{maintenance_exe}" /uninstall')
        winreg.SetValueEx(key, "QuietUninstallString", 0, winreg.REG_SZ, f'"{maintenance_exe}" /uninstall /quiet')
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, estimated_size)


def _remove_uninstall_registry() -> None:
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except FileNotFoundError:
        pass


def install(quiet: bool = False) -> None:
    _log(f"install start argv={sys.argv!r} exe={sys.executable!r}")
    version = _app_version()
    install_dir = _install_dir()
    app_exe = install_dir / APP_EXE
    start_menu = _start_menu_dir()
    desktop_shortcut = _desktop_dir() / "Codex Phone.lnk"
    start_shortcut = start_menu / "Codex Phone.lnk"
    uninstall_shortcut = start_menu / "Uninstall Codex Phone.lnk"

    _stop_running_app(include_maintenance=True)
    if install_dir.exists():
        shutil.rmtree(install_dir)
    install_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(_payload_zip(), "r") as archive:
        archive.extractall(install_dir)

    maintenance_exe = install_dir / "CodexPhoneMaintenance.exe"
    shutil.copy2(sys.executable, maintenance_exe)

    _create_shortcut(desktop_shortcut, app_exe, install_dir, app_exe)
    _create_shortcut(start_shortcut, app_exe, install_dir, app_exe)
    _create_shortcut(uninstall_shortcut, maintenance_exe, install_dir, maintenance_exe)
    _write_uninstall_registry(install_dir, version)
    _log(f"install complete install_dir={install_dir}")

    if quiet:
        return

    _message(
        f"{APP_NAME} {version} has been installed.\n\n"
        f"Install location:\n{install_dir}\n\n"
        "You can launch it from the desktop or Start menu.",
    )
    subprocess.Popen([str(app_exe)], cwd=str(install_dir), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def uninstall(quiet: bool = False) -> None:
    _log(f"uninstall start argv={sys.argv!r} exe={sys.executable!r}")
    install_dir = _install_dir()
    if not quiet:
        answer = _message(f"Uninstall {APP_NAME}?", flags=0x30 | 0x04)
        if answer != 6:
            return

    _stop_running_app()
    (_desktop_dir() / "Codex Phone.lnk").unlink(missing_ok=True)
    if _start_menu_dir().exists():
        shutil.rmtree(_start_menu_dir(), ignore_errors=True)
    _remove_uninstall_registry()
    _log("shortcuts and registry removed")

    cleanup = Path(tempfile.gettempdir()) / f"codex-phone-uninstall-{int(time.time())}.cmd"
    cleanup.write_text(
        "@echo off\n"
        "ping 127.0.0.1 -n 3 > nul\n"
        f'rmdir /s /q "{install_dir}"\n'
        f'del "{cleanup}"\n',
        encoding="utf-8",
    )
    subprocess.Popen(
        ["cmd", "/c", str(cleanup)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    _log(f"cleanup scheduled path={cleanup}")
    if not quiet:
        _message(f"{APP_NAME} has been uninstalled.")


def main() -> None:
    args = {arg.lower() for arg in sys.argv[1:]}
    try:
        if "/uninstall" in args or "--uninstall" in args:
            uninstall(quiet="/quiet" in args or "--quiet" in args)
        else:
            install(quiet="/quiet" in args or "--quiet" in args)
    except Exception as exc:
        _message(f"{APP_NAME} setup failed:\n\n{type(exc).__name__}: {exc}", flags=0x10)
        raise


if __name__ == "__main__":
    main()
