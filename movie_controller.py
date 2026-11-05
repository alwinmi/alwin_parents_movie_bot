import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

try:
    from pycaw.pycaw import AudioUtilities
except ImportError:
    print("Missing packages. Run:")
    print("Python -m pip install requests pycaw comtypes")
    svs.exit(1)


BASE_DIR = path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
OFFSET_FILE = BASE_DIR / "telegram_offset.txt"

shutdown_requested_by = None


def load_config():
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"configuration file not found: {CONFIG_FILE}")

    with open(CONFIG_FILE,"r", encoding="utf-8") as file:
        return json.load(file)


config = load_config()

BOT_TOKEN = config["bot_token"].strip()
ALLOWED_CHAT_ID = int(config.get("allowed_chat_id", 0))
BRAVE_PATH = config["brave_path"]
DEFAULT_VOLUME = int(config.get("default_volume",40))

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


def load_offset():
    try:
        return int(OFFSET_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return 0


def save_offset(offset):
    OFFSET_FILE.write_text(str(offset), encoding="utf-8")


def send_message(chat_id, message):
    try:
        requests.post(
            f"{API_URL}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": message
            },
            timeout=15
        )
    except Exception as error:
        print(f"Could not send Telegram message: {error}")


def is_authorized(chat_id):
    return ALLOWED_CHAT_ID != 0 and int(chat_id) == ALLOWED_CHAT_ID


def get_volume_interface():
    speakers = AudioUtilities.GetSpeakers()

    if hasattr(speakers, "EndpintVolume"):
        return speakers.EndpointVolume

    try:
        from ctypes import POINTER, cast
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import IAudioEndpointVolume

        interface = speakers.Activate(
            IAudioEndpointVolume._lid_,
            CLSCTX_ALL,
            None
        )

        return cast(interface, POINTER(IAudioEndpointVolume))
    except Exception as error:
        raise RuntimeError(f"Could not access Windows volume: {error}")


