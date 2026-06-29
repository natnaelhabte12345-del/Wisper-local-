"""
System tray icon — right-click menu for settings and quit.
"""
import threading
import pystray
from PIL import Image, ImageDraw
import startup


def _make_icon() -> Image.Image:
    """Create a simple microphone icon as a 64x64 PIL image."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Background circle
    d.ellipse([2, 2, 62, 62], fill="#7c6af5")
    # Mic body
    d.rounded_rectangle([24, 14, 40, 38], radius=8, fill="white")
    # Mic stand arc
    d.arc([18, 28, 46, 50], start=0, end=180, fill="white", width=3)
    # Stand pole
    d.line([32, 50, 32, 56], fill="white", width=3)
    d.line([26, 56, 38, 56], fill="white", width=3)
    return img


def run_tray(on_quit):
    """Blocking — run the tray icon. Call on_quit() when user clicks Quit."""

    def toggle_startup(icon, item):
        if startup.is_enabled():
            startup.disable()
        else:
            startup.enable()

    def startup_label(item):
        return "✓ Start with Windows" if startup.is_enabled() else "  Start with Windows"

    def quit_app(icon, item):
        icon.stop()
        on_quit()

    icon = pystray.Icon(
        "WisprWin",
        _make_icon(),
        "WisprWin — voice typing",
        menu=pystray.Menu(
            pystray.MenuItem(startup_label, toggle_startup),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", quit_app),
        ),
    )
    icon.run()   # blocks
