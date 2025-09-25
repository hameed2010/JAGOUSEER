import os
import time
import re
import platform
import traceback
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import mysql.connector
import gspread
import pandas as pd
import requests
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ---------------- Directories & Paths ----------------
USER_DATA_DIR = "chrome_user_data"
SCREENSHOT_DIR = "screenshots"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "mcn_script.log")

# ---------------- Website Credentials ----------------
MAIN_EMAIL = "samialjaishi@gmail.com"
SUB_EMAIL = "hameedalradaei@gmail.com"
SUB_PASSWORD = "Hameed2010."

# ---------------- Tesseract Setup ----------------
if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    print("✅ Tesseract Path Set for Windows")
else:
    pytesseract.pytesseract.tesseract_cmd = "tesseract"
    print("✅ Using system Tesseract on Linux/Server")

# ---------------- Logging ----------------
def log(msg):
    os.makedirs(SCRIPT_DIR, exist_ok=True)
    timestamp = datetime.now(ZoneInfo("Asia/Riyadh")).strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {msg}\n")
    print(f"[{timestamp}] {msg}")

# ---------------- Image Processing ----------------
def preprocess_image(image_path):
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"الصورة غير موجودة: {image_path}")
    
    img = Image.open(image_path).convert('L')
    img = ImageEnhance.Contrast(img).enhance(2)
    img = img.filter(ImageFilter.MedianFilter())
    return img

def read_text_from_image(image_path, lang='eng'):
    img = preprocess_image(image_path)
    try:
        text = pytesseract.image_to_string(img, lang=lang)
        text_no_spaces = re.sub(r'\s+', '', text)
        return text_no_spaces.strip()
    except pytesseract.TesseractNotFoundError:
        return "خطأ: برنامج Tesseract غير موجود أو المسار خاطئ."

# ---------------- Browser Helper Functions ----------------
def launch_browser():
    try:
        p = sync_playwright().start()
        browser = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            viewport={"width": 1280, "height": 800},
            java_script_enabled=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
        )
        log("✅ Browser launched successfully.")
        return p, browser
    except Exception as e:
        log(f"❌ Error launching browser: {e}")
        return None, None

def open_page(browser, url):
    try:
        page = browser.new_page()
        page.goto(url)
        log(f"✅ Opened page: {url}")
        return page
    except Exception as e:
        log(f"❌ Error opening page: {e}")
        return None

# ---------------- Login Functions ----------------
def ensure_login(page):
    while True:
        try:
            page.wait_for_url("**/dashboard/workspace", timeout=5000)
            log("✅ Already logged in.")
            return True
        except:
            try:
                log("ℹ️ Attempting login...")
                page.goto("https://mcn.jaco.live/auth/sign-in")
                page.wait_for_selector('button:has-text("Sub Account")', timeout=10000)
                page.click('button:has-text("Sub Account")')

                page.fill('input[name="email_or_username"]', MAIN_EMAIL)
                page.fill('input[name="sub_email_or_username"]', SUB_EMAIL)
                page.fill('input[name="password"]', SUB_PASSWORD)

                canvas = page.wait_for_selector('canvas.css-6htinl', timeout=10000)
                os.makedirs(SCREENSHOT_DIR, exist_ok=True)
                screenshot_path = os.path.join(SCREENSHOT_DIR, "canvas_screenshot.png")
                canvas.screenshot(path=screenshot_path)
                log(f"✅ Canvas screenshot saved to {screenshot_path}")

                text = read_text_from_image(screenshot_path)
                log(f"📄 Captcha text: {text}")

                page.fill('input[name^="captcha_"]', text)
                if not page.is_checked('input#terms-checkbox'):
                    page.check('input#terms-checkbox')

                page.click('button[type="submit"]')
                time.sleep(3)

                page.wait_for_url("**/dashboard/workspace", timeout=5000)
                log("✅ Logged in successfully!")
                return True

            except Exception as e:
                log(f"❌ Login process error: {e}")
                log("🔄 Retrying in 5 seconds...")
                time.sleep(5)

# ---------------- Page Interaction ----------------
def click_invite_streamer(page):
    try:
        page.goto("https://mcn.jaco.live/dashboard/streamer/invitation")
        page.wait_for_selector('button:has-text("Invite Streamer")', timeout=10000)
        page.click('button:has-text("Invite Streamer")')
        log("✅ Invite Streamer button clicked.")
    except Exception as e:
        log(f"❌ Error clicking Invite Streamer button: {e}")

def fill_uid_or_username(page, user_value):
    try:
        page.wait_for_selector('input[placeholder="Please enter UID or Username"]', timeout=10000)
        page.fill('input[placeholder="Please enter UID or Username"]', user_value)
        log(f"✅ Entered value '{user_value}' in UID/Username field.")
    except Exception as e:
        log(f"❌ Error filling UID/Username field: {e}")

def click_check_status(page):
    try:
        page.wait_for_selector('button:has-text("Check Status")', timeout=10000)
        page.click('button:has-text("Check Status")')
        log("✅ Check Status button clicked.")
    except Exception as e:
        log(f"❌ Error clicking Check Status button: {e}")

def get_check_status(page, user_value):
    try:
        fill_uid_or_username(page, user_value)
        api_url = "https://mcn.jaco.live/api/agency/check_streamer"
        with page.expect_response(lambda resp: api_url in resp.url and user_value in resp.url, timeout=15000) as resp_info:
            click_check_status(page)
        response = resp_info.value
        data = response.json()
        log(f"📌 API Response for {user_value}: {data}")
        return data
    except Exception as e:
        log(f"❌ Error getting check status: {e}")
        return {}

def fetch_users_from_db(limit=10):
    """جلب أول N مستخدمين من جدول users_jaco الذين حالتهم NEW"""
    try:
        conn = mysql.connector.connect(
            host="82.197.82.21",
            user="u758694318_bigo",
            password="*A[Ph&3RdvMTCXu1",
            database="u758694318_bigo"
        )
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"SELECT * FROM users_jaco WHERE status='new' LIMIT {limit};")
        rows = cursor.fetchall()
        return rows
    except Exception as e:
        log(f"❌ Error fetching users from DB: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ---------------- Main Program ----------------
def main():
    p, browser = launch_browser()
    page = open_page(browser, "https://mcn.jaco.live/auth/sign-in")

    while True:
        try:
            log("🟢 Starting main script...")
            if not browser or not page:
                log("❌ Browser or page did not open.")
                return

            page.goto("https://mcn.jaco.live/auth/sign-in")
            ensure_login(page)
            click_invite_streamer(page)

            while True:  # حلقة لمعالجة المستخدمين الجدد دفعة 10
                users = fetch_users_from_db(limit=10)
                
                if not users:
                    log("ℹ️ لا يوجد مستخدمين جدد، التوقف لمدة 30 دقيقة...")
                    time.sleep(30 * 60)  # 30 دقيقة
                    continue

                for user in users:
                    user_value = user.get("username")  # فقط عمود username
                    if not user_value:
                        log(f"⚠️ المستخدم {user} لا يحتوي على username صالح.")
                        continue

                    # ===== محاولة التحقق مع إعادة تسجيل الدخول عند الخطأ =====
                    while True:
                        response_data = get_check_status(page, user_value)
                        if response_data:  # إذا نجحت العملية
                            data = response_data.get("data", {})  # نأخذ فقط القسم data
                            break
                        else:
                            log(f"⚠️ خطأ في get_check_status للمستخدم {user_value}, إعادة تسجيل الدخول...")
                            ensure_login(page)
                            click_invite_streamer(page)
                            time.sleep(3)  # فاصل قبل إعادة المحاولة

                    # ===== تحديث قاعدة البيانات بعد نجاح get_check_status =====
                    required_keys = ["signed", "quality_anchor", "revenue_limit", "invite_limit"]
                    try:
                        conn = mysql.connector.connect(
                            host="82.197.82.21",
                            user="u758694318_bigo",
                            password="*A[Ph&3RdvMTCXu1",
                            database="u758694318_bigo"
                        )
                        cursor = conn.cursor()

                        if all(data.get(k) == 0 for k in required_keys):
                            cursor.execute(
                                "UPDATE users_jaco SET availability='available', status='verified' WHERE username=%s",
                                (user_value,)
                            )
                            log(f"✅ تم تحديث المستخدم {user_value}: availability=available، status=verified.")
                        else:
                            cursor.execute(
                                "UPDATE users_jaco SET status='verified' WHERE username=%s",
                                (user_value,)
                            )
                            log(f"⚠️ المستخدم {user_value} غير متاح، تم تحديث status فقط إلى 'verified'.")
                        
                        conn.commit()
                    except Exception as e:
                        log(f"❌ خطأ عند تحديث قاعدة البيانات للمستخدم {user_value}: {e}")
                    finally:
                        if cursor:
                            cursor.close()
                        if conn:
                            conn.close()
                    
                    # ===== فاصل زمني قبل المستخدم التالي =====
                    time.sleep(3)

        except Exception as e:
            log(f"❌ Unexpected error in main program: {e}")
            log(traceback.format_exc())

if __name__ == "__main__":
    main()
