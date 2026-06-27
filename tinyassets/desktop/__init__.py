"""Desktop application -- system tray, dashboard, notifications, launcher.

Re-exports
----------
TrayApp              -- pystray system tray icon (run_detached)
DashboardHandler     -- processes graph stream events for display
NotificationManager  -- toast / balloon notifications
LauncherApp          -- tkinter launcher GUI
create_icon_image    -- generate a branded icon PIL Image
generate_icon        -- generate multi-size .ico file
"""

from tinyassets.desktop.dashboard import DashboardHandler, DashboardMetrics
from tinyassets.desktop.host_tray import HostTrayService
from tinyassets.desktop.icon_gen import create_icon_image, generate_icon
from tinyassets.desktop.launcher import LauncherApp
from tinyassets.desktop.notifications import NotificationManager
from tinyassets.desktop.tray import TrayApp

__all__ = [
    "DashboardHandler",
    "DashboardMetrics",
    "HostTrayService",
    "LauncherApp",
    "NotificationManager",
    "TrayApp",
    "create_icon_image",
    "generate_icon",
]
