import configparser
import os
import sys

USB_VID = 0x2341
USB_PID = 0x8037

# Optional: specify a fixed COM port (e.g., "COM18"). Set to None to auto-detect.
COM_PORT = "COM17"


def _load_ini_port():
    candidates = []
    exe_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else None
    if exe_dir:
        candidates.append(os.path.join(exe_dir, "config.ini"))
    candidates.append(os.path.join(os.getcwd(), "config.ini"))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini"))
    candidates.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config.ini")))

    for path in candidates:
        if os.path.isfile(path):
            parser = configparser.ConfigParser()
            try:
                parser.read(path, encoding="utf-8")
            except Exception:
                continue
            port = parser.get("serial", "port", fallback="").strip()
            if not port or port.upper() == "AUTO":
                return None
            return port
    return None


_ini_port = _load_ini_port()
if _ini_port is not None:
    COM_PORT = _ini_port
