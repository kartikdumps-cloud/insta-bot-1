import os
import time
import subprocess
import yt_dlp
import glob
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException

CHECK_INTERVAL = 1  # seconds
AUTO_REFRESH_INTERVAL = 180  # auto-refresh change as per your need

INSTAGRAM_USERNAME = 'your ig username'     # <-- update!
INSTAGRAM_PASSWORD = 'your ig password'     # <-- update!
COOKIES_FILE = 'ig_cookies.pkl'

def create_uc_driver_with_fallback():
    from selenium.common.exceptions import SessionNotCreatedException
    options = uc.ChromeOptions()
    # options.add_argument("--headless")  # Uncomment for headless mode
    try:
        driver = uc.Chrome(options=options)
    except SessionNotCreatedException:
        raise
    return driver

def instagram_login(driver):
    print("[*] Attempting automatic Instagram login...")
    driver.get("https://www.instagram.com/accounts/login/")
    time.sleep(2)
    try:
        username_inp = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "username"))
        )
        username_inp.send_keys(INSTAGRAM_USERNAME)
        pass_inp = driver.find_element(By.NAME, "password")
        pass_inp.send_keys(INSTAGRAM_PASSWORD)
        pass_inp.send_keys(Keys.RETURN)
        time.sleep(3)
        try:
            notnow_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'Not Now')]"))
            )
            notnow_btn.click()
        except Exception:
            pass
        print("[+] Login attempted.")
    except Exception as e:
        print("[!] Could not automatically log in:", e)

def save_cookies(driver, filename):
    import pickle
    with open(filename, 'wb') as filehandler:
        pickle.dump(driver.get_cookies(), filehandler)

def load_cookies(driver, filename):
    import pickle
    if not os.path.exists(filename):
        return
    with open(filename, 'rb') as cookiesfile:
        cookies = pickle.load(cookiesfile)
        for cookie in cookies:
            driver.add_cookie(cookie)

def send_text_in_current_chat(driver, text):
    try:
        inp = WebDriverWait(driver, 8).until(EC.presence_of_element_located(
            (By.XPATH, "//div[@role='textbox' or @contenteditable='true'] | //textarea")))
        inp.click()
        inp.send_keys(text)
        inp.send_keys(Keys.RETURN)
        return True
    except Exception as e:
        print("Send text error:", e)
        return False

def send_audio_file_in_current_chat(driver, filepath):
    try:
        file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")
        for file_input in file_inputs:
            file_input.send_keys(os.path.abspath(filepath))
        time.sleep(2)
        send_btns = driver.find_elements(By.XPATH, "//button[contains(.,'Send') and not(@disabled)] | //button[@type='submit']")
        for btn in send_btns:
            try:
                btn.click()
                time.sleep(1)
                return True
            except WebDriverException as ex:
                print("Selenium error (ignored):", ex)
                continue
        send_text_in_current_chat(driver, "")
        return True
    except Exception as e:
        print("File send error (ignored):", e)
        return False

def download_from_youtube(query, format="mp3"):
    out_base = f"./spotify_song_{int(time.time() * 1000)}"
    ydl_opts = {
        'format': 'bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'outtmpl': out_base + '.%(ext)s',
        'prefer_ffmpeg': True,
        'extract_flat': False,
    }
    if format == "mp3":
        ydl_opts.update({
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        })
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"ytsearch1:{query}"])
    except Exception as e:
        print("YouTube download error:", e)
        return None
    for ext in ['.mp3', '.m4a', '.opus', '.webm']:
        file_path = f"{out_base}{ext}"
        if os.path.exists(file_path):
            return file_path
    files = glob.glob(f"{out_base}.*")
    if files:
        return files[0]
    return None

def process_spotify_command(driver, song_query):
    print(f"[/spotify] Command detected: {song_query}")
    file_path = download_from_youtube(song_query, format="mp3")
    if not file_path:
        print("Download failed.")
        return False

    ogg_path = file_path.replace('.mp3', '.ogg')
    try:
        cmd = [
            'ffmpeg', '-y', '-i', file_path,
            '-c:a', 'libopus', '-b:a', '64k',
            '-ar', '48000', '-ac', '2', '-application', 'voip',
            ogg_path
        ]
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ok = send_audio_file_in_current_chat(driver, ogg_path)
        msg = f"send the {song_query} song in chat"
        if ok:
            send_text_in_current_chat(driver, msg)
            print(f"[/spotify] {msg} (confirmation sent)")
        return ok
    except Exception as e:
        print(f"Audio processing error: {e}")
        return False
    finally:
        for f in [file_path, ogg_path]:
            try:
                if f and os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass
        try:
            for f in glob.glob("./spotify_song_*.mp3") + glob.glob("./spotify_song_*.ogg") + glob.glob("./spotify_song_*.*"):
                try: os.remove(f)
                except Exception: pass
        except Exception:
            pass

def get_last_spotify_command(driver, last_seen):
    try:
        messages = driver.find_elements(By.XPATH, "//div[contains(@role,'presentation')]//div[@dir='auto'] | //span[contains(@dir,'auto')]")
        message_texts = [m.text.strip() for m in messages if m.text.strip()]
        spotify_cmds = [msg for msg in message_texts if msg.lower().startswith("/spotify ")]
        new_cmds = [cmd for cmd in spotify_cmds if cmd != last_seen]
        return new_cmds[-1] if new_cmds else None
    except Exception as e:
        return None

def main():
    driver = create_uc_driver_with_fallback()
    driver.maximize_window()
    cookies_loaded = False
    if os.path.exists(COOKIES_FILE):
        driver.get("https://www.instagram.com/")
        load_cookies(driver, COOKIES_FILE)
        driver.refresh()
        time.sleep(3)
        print("[*] Loaded Instagram cookies.")
        cookies_loaded = True
    if not cookies_loaded:
        instagram_login(driver)
        time.sleep(3)
        try:
            save_cookies(driver, COOKIES_FILE)
            print("[*] Cookies saved for future sessions.")
        except Exception:
            pass

    driver.get("https://www.instagram.com/direct/inbox/")
    input("Open the chat to monitor and press Enter again...")

    print("👂 Bot is now monitoring for /spotify commands.")

    last_processed = ""
    last_refresh_time = time.time()
    while True:
        try:
            now = time.time()
            if now - last_refresh_time > AUTO_REFRESH_INTERVAL:
                print("🔄 Auto-refreshing Instagram Direct to prevent staleness...")
                driver.refresh()
                last_refresh_time = now
                time.sleep(6)
            cmd_message = get_last_spotify_command(driver, last_processed)
            if cmd_message:
                song_query = cmd_message[9:].strip()
                if song_query:
                    process_spotify_command(driver, song_query)
                last_processed = cmd_message
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            break
        except Exception as ex:
            print(f"Ignored selenium or other error: {ex}")
            time.sleep(CHECK_INTERVAL)

    driver.quit()
    print("Bot stopped and browser closed.")

if __name__ == "__main__":
    main()
