"""TinyAssets -- double-click to launch (tray mode).

Runs via pythonw.exe (no console window).  Starts the API server and
daemon with a system tray icon for control.  It publishes no public
ingress: local Cloudflare tunnel startup was removed, so this machine
never serves platform traffic.
"""
import sys

try:
    # Inject tray mode args so main() enters the tray code path
    sys.argv = [
        sys.argv[0],
        "--tray",
        "--serve",
        "--port", "8321",
    ]
    # Use default universe path (~/Documents/Fantasy Author)
    from pathlib import Path

    default_base = str(Path.home() / "Documents" / "Fantasy Author")
    sys.argv.extend(["--universe", default_base])

    from fantasy_author.__main__ import main
    main()
except ImportError as e:
    try:
        import tkinter.messagebox
        tkinter.messagebox.showerror(
            "TinyAssets",
            f"Missing dependencies. Run: pip install -e .[desktop]\n\n{e}",
        )
    except Exception:
        pass
except Exception as e:
    try:
        import tkinter.messagebox
        tkinter.messagebox.showerror(
            "TinyAssets",
            f"Startup failed:\n\n{e}",
        )
    except Exception:
        pass
