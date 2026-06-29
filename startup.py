"""
Registers / unregisters WisprWin in the Windows autostart registry key.
HKCU\Software\Microsoft\Windows\CurrentVersion\Run
"""
import sys
import winreg

APP_NAME = "WisprWin"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _launcher_path() -> str:
    """Path to the silent VBScript launcher (no CMD window on boot)."""
    import os
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "run.vbs")


def enable() -> None:
    path = _launcher_path()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                        winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ,
                          f'wscript.exe "{path}"')
    print(f"[startup] Autostart enabled: {path}")


def disable() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_NAME)
        print("[startup] Autostart disabled.")
    except FileNotFoundError:
        pass


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False
