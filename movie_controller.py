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


def get_volume():
    volume = get_volume_interface()
    return round(volume.GetMasterVolumeLevelScalar() * 100)


def set_volume(level):
    level = max(0, min(100,int(level)))
    volume = get_volume_interface()
    volume.SetMasterVolumeLevelScalar(level / 100.0, None)
    volume.setMute(0, None)
    return level


def change_volume(amount):
    current = get_volume()
    return set_volume(current + amount)


def set_mute(muted):
    volume = get_volume_interface()
    volume.SetMute(1 if muted else 0, None)


def get_mute_status():
    volume = get_volume_interface()
    return bool(volume.GetMute())


def extract_youtube_video_id(text):
    text = text.strip()

    try:
        parsed = urlparse(text)
        hostname = parsed.netloc.lower().replace("wwww.","")

        if hostname == "youtube.be":
            video_id = parsed.path.strip("/").split("/")[0]
            return video_id if valid_video_id(video_id) else None

        if hostname in {
            "youtube.com",
            "m.youtube.com",
            "music.youtube.com"
        }:
            if parsed.path == "/watch":
                video_id = parse_qs(parsed.query).get("v", [None])[0]
                return video_id if valid_video_id(video_id) else None

            if parsed.path.startswith("/shorts/"):
                video_id = parsed.path.split("/shorts/")[1].split("/")[0]
                return video_id if valid_video_id(video_id) else None

            if parsed.path.startswith("/embed/"):
                video_id = parsed.path.split("/embed/")[1].split("/")[0]
                return video_id if valid_video_id(video_id) else None

            if parsed.path.startswith("/live/"):
                video_id = parsed.path.split("/live/")[1].split("/")[0]
                return video_id if valid_video_id(video_id) else None
            
    except Exception:
        return None

    return None 


def valid_video_id(video_id):
    if not video_id:
        return False

    return bool(re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id))


def stop_brave();
    subprocess.run(
        ["taskkill","/F", "/IM", "brave.exe"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW
    )

    time.sleep(2)


def play_youtube(video_id):
    if not os.path.exists(BRAVE_PATH):
        raise FileNotFoundError(
            f"Brave was not found at:\n{BRAVE_PATH}"
        )

    stop_brave()

    youtube_url = (
        f"https://www.youtube.com/embed/{video_id}"
        f"?autoplay=1&rel=0&controls=1"
    )

    command = [
        BRAVE_PATH,
        "--kiosk",
        "--start-fullscreen",
        "--autoplay-policy=no-user-gestur-required",
        "--no-first-run",
        "--disable-session-crashed-bubble",
        "--disable-features=Translate",
        youtube_url
    ]

    subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


def schedule_shutdown():
    subprocess.run(
        ["shutdown", "/s", "/t" ,"60" ,"/c" ,"Telegram requested shutdown"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW
    )


def cancel_shutdown():
    result = subprocess.run(
        ["shutdown", "/a"],
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW
    )

    return result.returncode == 0


def send_help(chat_id):
    message = (
        "Movie Controller commands:\n\n"
        "Send a Youtube link to play it\n"
        "/vlume 40 - Set vlume to 40%\n"
        "/vlumeup - Increase volume by 10%\n"
        "/volumedown - Reduce volume by 10%\n"
        "/mute - Mute Windows audio\n"
        "/unmute - Unmute Windows audio\n"
        "stop - Close Brave\n"
        "/status - Show PC status\n"
        "/shutdown - Request PC shutdown\n"
        "/confirmshutdown - Confirm shutdown\n"
        "/cancelshutdown - Cancel shutdown\n"
        "/id -  Show your Telegram chat ID\n"
        "/help - Show commands"
    )

    send_message(chat_id, message)


def process_message(chat_id, text):
    global shutdown_requested_by

    text = text.strip()
    command = text.lower()

    # Initial setup comman. This works before authorization is configured/
    if command == "/id":
        send_message(
            chat_id,
            f"Your Telegram chat ID is:\n{chat_id}\n\n"
            "Put this number in config.json as allowed_chat_id."
        )
        return

    if not is_authorized(chat_id):
        print(f"Ignored unauthorised chat ID: {chat_id}")

        if ALLOWED_CHAT_ID == 0:
            send_message(
                chat_id,
                "The controller is not configured yet.\n"
                "Send /id and add the displayed number to config.json."
            )

            return

        if command in {"/start", "/help"}:
            send_help(chat_id)
            return

        video_id = extract_youtube_video_id(text)

        if video_id:
            try:
                play_youtube(video_id)

                if DEFAULT_VOLUME >= 0:
                    set_volume(DEFAULT_VOLUME)

                    send_message(
                        chat_id,
                        f"Video opened in Brave.\n"
                        f"Volume: {get_volume()}%"
                    )
            except Exception as error:
                send_message(chat_id,f"Could not play vide:\n{error}")

            return

        if command.startswith("/volume "):
            try:
                requested_level = int(command.split(maxsplit=1)[1])

                if requested_level < 0 or requested_level > 100:
                    send_message(chat_id, "Enter a vlume between 0 and 100.")
                    return

                actual_level = set_volume(requested_level)
                send_message(chat_id,f"Vlume set to {actual_level}%.")

            except ValueError:
                send_message(chat_id, "Example: /volume 40")
            except Exception as error:
                send_message(chat_id, f"Volume control failed:\n{error}")

                return

            if command == "/volumeup":
                try:
                    level = change_volume(10)
                    send_message(chat_id,f"Volume increased to {level}%.")
                except Exception as error:
                    send_message(chat_id,f"Volume control failed:\n{error}")
                return

            if command ==  "/volumedown":
                try:
                    level = change_volume(-10)
                    send_message(chat_id,f"Volume reduced to  {level}%.")
                except Exception as error:
                    send_message(chat_id,f"Volume control failed:\n{error}")
                return

            if command == "/mute":
                try:
                    set_mute(True)
                    send_message(chat_id, "Windows audio muted.")
                except Exception as error:
                    send_message(chat_id, f"Mute failed:\n{error}")
                return

            if command == "/unmute":
                try:
                    set_mute(False)
                    send_message(chat_id, "Windows audio unmuted.")
                except Exception as error:
                    send_message(chat_id, f"Unmute failed:\n{error}")
                return
            