# ============================================================
# CORE2 WEATHER STATION
# ============================================================

from m5stack import *
from m5stack_ui import *
from uiflow import *
from m5ui import *

import unit
import urequests
import hashlib
import binascii
import wifiCfg
import ujson
import ubinascii
from machine import I2C, Pin
import time

# ---------------- CONFIG ----------------
CLOUD_BASE = "https://weather-flask-297113273467.europe-west6.run.app"
SOURCE_ID = "F"
PASSWD = "Cloud1802"

#Put your most reliable WiFi first. If scan fails, the code manually tries each WiFi in this order.
WIFI_LIST = [
    ("iot-unil", "Password"),   
    ("Home_Wifi", "..."),
    ("Phone_hotspot", "...")
]


LOOP_DELAY_S = 1
SEND_EVERY_S = 400
PERIOD = max(1, int(SEND_EVERY_S / LOOP_DELAY_S))

WEATHER_EVERY_S = 1800
WEATHER_PERIOD = max(1, int(WEATHER_EVERY_S / LOOP_DELAY_S))

WIFI_CHECK_EVERY_S = 300
WIFI_CHECK_PERIOD = max(1, int(WIFI_CHECK_EVERY_S / LOOP_DELAY_S))

MOTION_SEND_COOLDOWN_S = 30
AI_VOICE_COOLDOWN_S = 3600
RUN_STARTUP_AI_IN_BACKGROUND = True

SWISS_TZONE = 2
RTC_HOST = "de.pool.ntp.org"
USE_12H_CLOCK = True

AI_BASE_PROMPT = (
    "Based on the data you have about indoor and outdoor conditions, give recommendations, "
    "either to improve indoor air quality or to help decide what to do before going outside, "
    "such as taking an umbrella, avoiding direct sun during heat, dressing warmer, "
    "or opening or closing windows. Also say if no action is needed. "
    "You can mention a historical trend only if there is an important change. "
    "Use the current OpenWeather icon code as extra context for the current outdoor weather forecast. "
    "Interpret OpenWeather icon codes as follows: "
    "01 means clear sky, 02 means few clouds or partly cloudy, 03 means scattered clouds, "
    "04 means broken or overcast clouds, 09 means shower rain, 10 means rain, "
    "11 means thunderstorm, 13 means snow, and 50 means mist or fog. "
    "The final letter d means daytime and n means nighttime. "
)

AI_REQUEST = (
    "Current OpenWeather icon code: {}. "
    "Please summarize the current and historical indoor indicators and the current outdoor weather, then give your recommendation."
)

REQUEST_AUDIO = True
SPEAKER_VOLUME = 6
AI_MAX_CHARS = 550
DEG_C = chr(176) + "C"

# ---------------- COLORS ----------------
C_BG = 0xDFF4FF
C_HEADER = 0xBDEBFF
C_CARD = 0xFFFFFF
C_SHADOW = 0xB8DDED
C_BORDER = 0x91C9E8
C_TEXT = 0x1F2933
C_MUTED = 0x66788A
C_OK = 0x27AE60
C_ERR = 0xE74C3C
C_WARN = 0xF39C12
C_BLUE = 0x2D9CDB
C_YELLOW = 0xF2C94C
C_CLOUD = 0x90A4AE
C_CLOUD_DARK = 0x78909C
C_PURPLE = 0x9B51E0

DOT_GOOD = C_OK
DOT_MID = C_WARN
DOT_BAD = C_ERR
DOT_NONE = C_CARD

FONT_14 = globals().get('FONT_MONT_14', FONT_MONT_18)
FONT_18 = globals().get('FONT_MONT_18', FONT_MONT_18)
FONT_22 = globals().get('FONT_MONT_22', FONT_MONT_18)
HASH = binascii.hexlify(hashlib.sha256(PASSWD.encode()).digest()).decode()

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# ---------------- GLOBAL STATE ----------------
selected_wifi_ssid = ""
last_icon_code = None
last_outdoor_icon = None
startup_ai_done = False

last_temp_value = None
last_hum_value = None
last_tvoc_value = None
last_eco2_value = None
last_hum_dot = None
last_tvoc_dot = None
last_eco2_dot = None

counter = 0
weather_counter = 0
wifi_check_counter = 0
prev_motion = 0
warmup_ticks = 0
warmup_done = False
last_ai_voice_s = 0
last_motion_send_s = 0
last_motion_state = None

wifi_lbl = None
status_lbl = None
time_lbl = None
out_temp_lbl = None
out_desc_lbl = None
date_lbl = None
clock_lbl = None
temp_lbl = None
hum_lbl = None
tvoc_lbl = None
eco2_lbl = None
fc_lbls = []
dot_hum = (312, 102)
dot_tvoc = (148, 158)
dot_eco2 = (312, 158)

# ---------------- BASIC HELPERS ----------------
def weather_symbol(desc):
    d = (desc or "").lower()
    if "thunder" in d:
        return "STRM"
    if "drizzle" in d:
        return "DRZL"
    if "rain" in d:
        return "RAIN"
    if "snow" in d:
        return "SNOW"
    if "fog" in d or "mist" in d:
        return "FOG"
    if "clear" in d:
        return "SUN"
    if "few clouds" in d:
        return "SUN"
    if "scattered clouds" in d:
        return "PART"
    if "broken clouds" in d or "overcast" in d:
        return "CLDY"
    if "cloud" in d:
        return "CLDY"
    return "----"


def format_12h(hh, mm):
    suffix = "PM" if hh >= 12 else "AM"
    h12 = hh % 12
    if h12 == 0:
        h12 = 12
    return "{}:{:02d} {}".format(h12, mm, suffix)


def format_countdown(seconds):
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return str(seconds) + "s"
    minutes = seconds // 60
    if minutes < 60:
        return str(minutes) + "m"
    hours = minutes // 60
    minutes = minutes % 60
    return str(hours) + "h" + str(minutes) + "m"


def temp_text(value, decimals=0):
    if value is None:
        return "--" + DEG_C
    if decimals == 1:
        return "{:.1f}{}".format(float(value), DEG_C)
    return "{:.0f}{}".format(float(value), DEG_C)


def _fill_round_rect(x, y, w, h, r, color):
    try:
        lcd.fillRoundRect(x, y, w, h, r, color)
    except:
        lcd.fillRect(x, y, w, h, color)


def _draw_round_rect(x, y, w, h, r, color):
    try:
        lcd.drawRoundRect(x, y, w, h, r, color)
    except:
        lcd.drawRect(x, y, w, h, color)


def draw_card(x, y, w, h):
    _fill_round_rect(x + 2, y + 2, w, h, 8, C_SHADOW)
    _fill_round_rect(x, y, w, h, 8, C_CARD)
    _draw_round_rect(x, y, w, h, 8, C_BORDER)


def draw_dot(cx, cy, color, r=4):
    try:
        lcd.fillCircle(cx, cy, r, color)
    except:
        lcd.fillRect(cx - r, cy - r, r * 2, r * 2, color)


def set_label_safe(label, text, color=None, max_len=None):
    try:
        s = str(text)
        if max_len is not None:
            s = s[:max_len]
        label.set_text(s)
        if color is not None:
            label.set_text_color(color)
    except Exception as e:
        print("Label error:", e)

# ---------------- ICON DRAWING ----------------
def clear_icon_area(x, y, w=44, h=42):
    try:
        lcd.fillRect(x, y, w, h, C_CARD)
    except:
        pass


def draw_sun(cx, cy, r=7):
    try:
        lcd.fillCircle(cx, cy, r, C_YELLOW)
        lcd.drawLine(cx - 13, cy, cx - 10, cy, C_YELLOW)
        lcd.drawLine(cx + 10, cy, cx + 13, cy, C_YELLOW)
        lcd.drawLine(cx, cy - 13, cx, cy - 10, C_YELLOW)
        lcd.drawLine(cx, cy + 10, cx, cy + 13, C_YELLOW)
        lcd.drawLine(cx - 9, cy - 9, cx - 7, cy - 7, C_YELLOW)
        lcd.drawLine(cx + 7, cy + 7, cx + 9, cy + 9, C_YELLOW)
        lcd.drawLine(cx + 9, cy - 9, cx + 7, cy - 7, C_YELLOW)
        lcd.drawLine(cx - 7, cy + 7, cx - 9, cy + 9, C_YELLOW)
    except:
        lcd.fillRect(cx - r, cy - r, r * 2, r * 2, C_YELLOW)


def draw_cloud(cx, cy, heavy=False):
    cloud_color = C_CLOUD_DARK if heavy else C_CLOUD
    try:
        lcd.fillCircle(cx - 8, cy + 3, 7, cloud_color)
        lcd.fillCircle(cx, cy, 9, cloud_color)
        lcd.fillCircle(cx + 10, cy + 4, 7, cloud_color)
        lcd.fillRect(cx - 16, cy + 4, 32, 8, cloud_color)
    except:
        lcd.fillRect(cx - 16, cy, 32, 14, cloud_color)


def draw_partly_cloudy(cx, cy):
    lcd.fillRect(cx - 25, cy - 20, 55, 45, C_CARD)
    draw_sun(cx - 9, cy - 5, 7)
    draw_cloud(cx + 7, cy + 4, False)


def draw_rain(cx, cy):
    draw_cloud(cx, cy)
    try:
        lcd.drawLine(cx - 8, cy + 17, cx - 11, cy + 23, C_BLUE)
        lcd.drawLine(cx, cy + 17, cx - 3, cy + 23, C_BLUE)
        lcd.drawLine(cx + 8, cy + 17, cx + 5, cy + 23, C_BLUE)
    except:
        pass


def draw_weather_icon(desc, x, y):
    d = (desc or "").lower()
    if "rain" in d or "drizzle" in d:
        clear_icon_area(x - 22, y - 18, 44, 42)
        draw_rain(x, y)
    elif "snow" in d:
        clear_icon_area(x - 22, y - 18, 44, 42)
        draw_cloud(x, y)
        try:
            lcd.drawLine(x - 8, y + 17, x - 8, y + 23, C_BLUE)
            lcd.drawLine(x, y + 17, x, y + 23, C_BLUE)
            lcd.drawLine(x + 8, y + 17, x + 8, y + 23, C_BLUE)
        except:
            pass
    elif "few clouds" in d or "scattered clouds" in d:
        draw_partly_cloudy(x, y)
    elif "broken clouds" in d or "overcast" in d or "cloud" in d:
        clear_icon_area(x - 22, y - 18, 44, 42)
        draw_cloud(x, y, True)
    else:
        clear_icon_area(x - 22, y - 18, 44, 42)
        draw_sun(x, y)


def draw_drop(cx, cy, color):
    try:
        lcd.fillCircle(cx, cy + 5, 5, color)
        lcd.fillTriangle(cx, cy - 7, cx - 5, cy + 4, cx + 5, cy + 4, color)
    except:
        lcd.fillRect(cx - 5, cy - 5, 10, 14, color)


def draw_home_icon(x, y, color):
    try:
        lcd.fillTriangle(x, y + 8, x + 12, y - 4, x + 24, y + 8, color)
        lcd.fillRect(x + 4, y + 8, 16, 13, color)
        lcd.fillRect(x + 10, y + 14, 5, 7, C_CARD)
    except:
        lcd.fillRect(x, y, 22, 18, color)

# Small forecast icons from OpenWeather icon codes
def draw_small_sun(cx, cy):
    try:
        lcd.fillCircle(cx, cy, 5, C_YELLOW)
        lcd.drawLine(cx - 9, cy, cx - 7, cy, C_YELLOW)
        lcd.drawLine(cx + 7, cy, cx + 9, cy, C_YELLOW)
        lcd.drawLine(cx, cy - 9, cx, cy - 7, C_YELLOW)
        lcd.drawLine(cx, cy + 7, cx, cy + 9, C_YELLOW)
    except:
        lcd.fillRect(cx - 5, cy - 5, 10, 10, C_YELLOW)


def draw_small_cloud(cx, cy, heavy=False):
    cloud_color = C_CLOUD_DARK if heavy else C_CLOUD
    try:
        lcd.fillCircle(cx - 5, cy + 2, 5, cloud_color)
        lcd.fillCircle(cx + 1, cy, 6, cloud_color)
        lcd.fillCircle(cx + 7, cy + 3, 5, cloud_color)
        lcd.fillRect(cx - 10, cy + 3, 22, 6, cloud_color)
    except:
        lcd.fillRect(cx - 10, cy, 22, 10, cloud_color)


def draw_small_partly_cloudy(cx, cy):
    draw_small_sun(cx - 5, cy - 3)
    draw_small_cloud(cx + 4, cy + 2, False)


def draw_small_rain(cx, cy):
    draw_small_cloud(cx, cy)
    try:
        lcd.drawLine(cx - 5, cy + 12, cx - 7, cy + 16, C_BLUE)
        lcd.drawLine(cx + 1, cy + 12, cx - 1, cy + 16, C_BLUE)
        lcd.drawLine(cx + 7, cy + 12, cx + 5, cy + 16, C_BLUE)
    except:
        pass


def draw_small_snow(cx, cy):
    draw_small_cloud(cx, cy)
    try:
        lcd.drawLine(cx - 5, cy + 12, cx - 5, cy + 16, C_BLUE)
        lcd.drawLine(cx + 2, cy + 12, cx + 2, cy + 16, C_BLUE)
        lcd.drawLine(cx + 9, cy + 12, cx + 9, cy + 16, C_BLUE)
    except:
        pass


def draw_small_fog(cx, cy):
    try:
        lcd.drawLine(cx - 12, cy - 3, cx + 14, cy - 3, C_CLOUD)
        lcd.drawLine(cx - 15, cy + 3, cx + 11, cy + 3, C_CLOUD)
        lcd.drawLine(cx - 10, cy + 9, cx + 15, cy + 9, C_CLOUD)
    except:
        draw_small_cloud(cx, cy)


def draw_forecast_icon_code(icon_code, fallback_symbol, cx, cy):
    lcd.fillRect(cx - 16, cy - 12, 34, 26, C_CARD)
    icon = (icon_code or "").lower()
    code = icon[:2]
    sym = (fallback_symbol or "").upper()
    if code == "01":
        draw_small_sun(cx, cy)
    elif code == "02":
        draw_small_partly_cloudy(cx, cy)
    elif code == "03":
        draw_small_cloud(cx, cy, False)
    elif code == "04":
        draw_small_cloud(cx, cy, True)
    elif code in ("09", "10"):
        draw_small_rain(cx, cy)
    elif code == "11":
        draw_small_rain(cx, cy)
    elif code == "13":
        draw_small_snow(cx, cy)
    elif code == "50":
        draw_small_fog(cx, cy)
    else:
        if "SUN" in sym:
            draw_small_sun(cx, cy)
        elif "RAIN" in sym or "DRZL" in sym:
            draw_small_rain(cx, cy)
        elif "SNOW" in sym:
            draw_small_snow(cx, cy)
        elif "CLD" in sym or "CLDY" in sym or "CLOUD" in sym:
            draw_small_cloud(cx, cy)
        else:
            draw_small_cloud(cx, cy)

# ---------------- SCREEN INIT ----------------
screen = M5Screen()
screen.clean_screen()
screen.set_screen_bg_color(C_BG)
lcd.fillScreen(C_BG)

# ---------------- WIFI HELPERS ----------------
def wifi_is_connected():
    try:
        return wifiCfg.wlan_sta.isconnected()
    except:
        return False


def scan_known_wifi_once():
    best_ssid = None
    best_pwd = None
    best_rssi = -999
    scan = []

    try:
        try:
            scan = wifiCfg.wlan_sta.scan()
        except:
            scan = wifiCfg.scan()
    except Exception as e:
        print("WiFi scan error:", e)
        scan = []

    print("Networks found:", len(scan))

    try:
        for net in scan:
            try:
                seen_ssid = net[0]
                if isinstance(seen_ssid, bytes):
                    seen_ssid = seen_ssid.decode()
                rssi = -999
                try:
                    rssi = net[3]
                except:
                    pass
                print("Seen WiFi:", seen_ssid, "RSSI:", rssi)
            except Exception as e:
                print("Scan print error:", e)
    except Exception as e:
        print("Scan list print error:", e)

    try:
        for ssid, pwd in WIFI_LIST:
            for net in scan:
                try:
                    found_ssid = net[0]
                    if isinstance(found_ssid, bytes):
                        found_ssid = found_ssid.decode()
                    rssi = -999
                    try:
                        rssi = net[3]
                    except:
                        pass
                    if found_ssid == ssid and rssi > best_rssi:
                        best_ssid = ssid
                        best_pwd = pwd
                        best_rssi = rssi
                except Exception as e:
                    print("WiFi parse error:", e)
    except Exception as e:
        print("WiFi select error:", e)

    if best_ssid is not None:
        print("Selected WiFi from scan:", best_ssid, "RSSI:", best_rssi)

    return best_ssid, best_pwd


def scan_best_known_wifi():
    # After standalone boot, first scan can be empty. Retry before giving up.
    wait(2)
    for attempt in range(5):
        print("WiFi scan attempt:", attempt + 1)
        ssid, pwd = scan_known_wifi_once()
        if ssid is not None:
            return ssid, pwd
        wait(2)

    print("No known WiFi found by scan")
    return None, None


def connect_known_wifi(ssid, pwd, timeout=10): 
    if not ssid:
        return False
    try:
        wifiCfg.doConnect(ssid, pwd)
    except Exception as e:
        print("WiFi connect error:", e)
    start = time.time()
    while time.time() - start < timeout:
        if wifi_is_connected():
            print("Connected to:", ssid)
            try:
                print("IP:", wifiCfg.wlan_sta.ifconfig())
            except:
                pass
            return True
        wait(1)
    return False


def try_wifi_list_manually(status_label=None, detail_label=None):
    # Manual fallback: directly try each configured WiFi if scan fails.
    for ssid, pwd in WIFI_LIST:
        try:
            print("Manual WiFi try:", ssid)
            if status_label is not None:
                status_label.set_text("Trying WiFi")
            if detail_label is not None:
                detail_label.set_text(ssid[:22])
            if connect_known_wifi(ssid, pwd, 20):
                return ssid, pwd
        except Exception as e:
            print("Manual WiFi error:", e)
    return None, None


def ensure_wifi_connected():
    global selected_wifi_ssid
    if wifi_is_connected():
        return True
    set_status("WIFI RECON", C_WARN)
    update_wifi_badge()

    ssid, pwd = scan_best_known_wifi()
    if ssid is None:
        ssid, pwd = try_wifi_list_manually()

    if ssid is None:
        set_status("NO WIFI", C_ERR)
        return False

    selected_wifi_ssid = ssid
    if connect_known_wifi(ssid, pwd, 45):
        set_status("WIFI OK", C_OK)
        update_wifi_badge()
        return True

    set_status("WIFI FAIL", C_ERR)
    update_wifi_badge()
    return False

# ---------------- WIFI LOADING ----------------
def wifi_loading_screen():
    global selected_wifi_ssid
    screen.clean_screen()
    screen.set_screen_bg_color(C_BG)
    lcd.fillScreen(C_BG)
    M5Label("SMART WEATHER", x=62, y=30, color=C_TEXT, font=FONT_18, parent=None)
    status = M5Label("Scanning WiFi...", x=55, y=88, color=C_WARN, font=FONT_18, parent=None)
    detail = M5Label("", x=35, y=124, color=C_MUTED, font=FONT_14, parent=None)
    M5Label("Scan first, manual fallback", x=52, y=202, color=C_MUTED, font=FONT_14, parent=None)

    ssid, pwd = scan_best_known_wifi()
    if ssid is None:
        status.set_text("Manual WiFi...")
        ssid, pwd = try_wifi_list_manually(status, detail)

    if ssid is None:
        status.set_text("NO WIFI LIST")
        detail.set_text("Starting offline")
        wait(2)
        start_main_app()
        return

    selected_wifi_ssid = ssid
    detail.set_text(ssid[:22])
    status.set_text("Connecting...")

    if wifi_is_connected() or connect_known_wifi(ssid, pwd, 60):
        status.set_text("WiFi OK")
        detail.set_text(ssid[:22])
        wait(1)
    else:
        status.set_text("WiFi FAIL")
        detail.set_text("Starting offline")
        wait(2)

    start_main_app()

# ---------------- DASHBOARD UI ----------------
def build_dashboard_ui():
    global wifi_lbl, status_lbl, time_lbl
    global out_temp_lbl, out_desc_lbl, date_lbl, clock_lbl
    global temp_lbl, hum_lbl, tvoc_lbl, eco2_lbl, fc_lbls
    screen.clean_screen()
    screen.set_screen_bg_color(C_BG)
    lcd.fillScreen(C_BG)
    lcd.fillRect(0, 0, 320, 26, C_HEADER)
    lcd.drawRect(0, 0, 320, 26, C_BORDER)
    wifi_lbl = M5Label("WiFi:--", x=6, y=6, color=C_MUTED, font=FONT_14, parent=None)
    status_lbl = M5Label("BOOT", x=103, y=6, color=C_WARN, font=FONT_14, parent=None)
    time_lbl = M5Label("Next:--", x=218, y=6, color=C_BLUE, font=FONT_14, parent=None)
    draw_card(2, 28, 154, 66)
    M5Label("OUTDOOR", x=10, y=34, color=C_MUTED, font=FONT_14, parent=None)
    out_temp_lbl = M5Label("--" + DEG_C, x=10, y=50, color=C_BLUE, font=FONT_22, parent=None)
    out_desc_lbl = M5Label("----", x=10, y=76, color=C_MUTED, font=FONT_14, parent=None)
    draw_weather_icon("clear", 128, 58)
    draw_card(158, 28, 160, 66)
    M5Label("DATE / TIME", x=166, y=34, color=C_MUTED, font=FONT_14, parent=None)
    date_lbl = M5Label("--- -- ----", x=166, y=50, color=C_TEXT, font=FONT_18, parent=None)
    clock_lbl = M5Label("--:--", x=166, y=72, color=C_BLUE, font=FONT_18, parent=None)
    draw_card(2, 96, 154, 54)
    draw_card(158, 96, 160, 54)
    M5Label("INDOOR TEMP", x=10, y=102, color=C_MUTED, font=FONT_14, parent=None)
    M5Label("HUMIDITY", x=166, y=102, color=C_MUTED, font=FONT_14, parent=None)
    temp_lbl = M5Label("--" + DEG_C, x=10, y=120, color=C_TEXT, font=FONT_22, parent=None)
    hum_lbl = M5Label("--%", x=166, y=120, color=C_TEXT, font=FONT_22, parent=None)
    draw_home_icon(124, 113, C_BLUE)
    draw_drop(304, 124, C_BLUE)
    draw_dot(dot_hum[0], dot_hum[1], DOT_NONE)
    draw_card(2, 152, 154, 54)
    draw_card(158, 152, 160, 54)
    M5Label("TVOC (ppb)", x=10, y=158, color=C_MUTED, font=FONT_14, parent=None)
    M5Label("eCO2 (ppm)", x=166, y=158, color=C_MUTED, font=FONT_14, parent=None)
    tvoc_lbl = M5Label("--", x=10, y=176, color=C_TEXT, font=FONT_22, parent=None)
    eco2_lbl = M5Label("--", x=166, y=176, color=C_TEXT, font=FONT_22, parent=None)
    M5Label("CO2", x=277, y=178, color=C_PURPLE, font=FONT_14, parent=None)
    draw_dot(dot_tvoc[0], dot_tvoc[1], DOT_NONE)
    draw_dot(dot_eco2[0], dot_eco2[1], DOT_NONE)
    draw_card(2, 208, 316, 30)
    fc_lbls = [
        M5Label("---", x=10, y=217, color=C_TEXT, font=FONT_14, parent=None),
        M5Label("---", x=113, y=217, color=C_TEXT, font=FONT_14, parent=None),
        M5Label("---", x=216, y=217, color=C_TEXT, font=FONT_14, parent=None),
    ]

# ---------------- STATUS / WIFI ----------------
def update_wifi_badge():
    if wifi_lbl is None:
        return
    try:
        if wifi_is_connected():
            set_label_safe(wifi_lbl, "WiFi:OK", C_OK)
        else:
            set_label_safe(wifi_lbl, "WiFi:OFF", C_ERR)
    except:
        set_label_safe(wifi_lbl, "WiFi:--", C_MUTED)


def set_status(text, color=None):
    if status_lbl is not None:
        set_label_safe(status_lbl, text, color or C_MUTED, 12)


def update_next_send(count):
    if time_lbl is not None:
        seconds_left = max(0, (PERIOD - count) * LOOP_DELAY_S)
        set_label_safe(time_lbl, "Next:" + format_countdown(seconds_left), C_BLUE, 12)


def wait_for_wifi(max_wait_s=60):
    if wifi_is_connected():
        set_status("WIFI OK", C_OK)
        update_wifi_badge()
        return True
    start = time.time()
    while True:
        if wifi_is_connected():
            set_status("WIFI OK", C_OK)
            update_wifi_badge()
            return True
        if time.time() - start > max_wait_s:
            set_status("WIFI FAIL", C_ERR)
            update_wifi_badge()
            return False
        set_status("WAIT WIFI", C_WARN)
        update_wifi_badge()
        wait(1)

# ---------------- DOT HELPERS ----------------
def humidity_dot_color(hum):
    if hum is None:
        return DOT_NONE
    if hum >= 40 and hum <= 60:
        return DOT_GOOD
    if (hum >= 30 and hum < 40) or (hum > 60 and hum <= 70):
        return DOT_MID
    return DOT_BAD


def tvoc_dot_color(ppb):
    if ppb is None:
        return DOT_NONE
    if ppb < 250:
        return DOT_GOOD
    if ppb < 1000:
        return DOT_MID
    return DOT_BAD


def eco2_dot_color(ppm):
    if ppm is None:
        return DOT_NONE
    if ppm < 800:
        return DOT_GOOD
    if ppm < 1200:
        return DOT_MID
    return DOT_BAD

# ---------------- RTC ----------------
_rtc_synced = False


def rtc_sync_once():
    global _rtc_synced
    try:
        if not wait_for_wifi(60):
            set_status("NO WIFI", C_ERR)
            return False
        set_status("RTC NTP", C_WARN)
        rtc.settime('ntp', host=RTC_HOST, tzone=SWISS_TZONE)
        _rtc_synced = True
        set_status("TIME OK", C_OK)
        print("RTC datetime:", rtc.datetime())
        return True
    except Exception as e:
        print("RTC sync error:", e)
        set_status("TIME ERR", C_ERR)
        return False


def update_clock():
    if date_lbl is None or clock_lbl is None:
        return
    try:
        dt = rtc.datetime()
        y, mo, d, wd, hh, mm = dt[0], dt[1], dt[2], dt[3], dt[4], dt[5]
        if y < 2024:
            set_label_safe(date_lbl, "TIME UNSYNC", C_WARN)
            set_label_safe(clock_lbl, "--:--", C_BLUE)
            return
        set_label_safe(date_lbl, "{} {} {}".format(d, MONTHS[mo - 1], y), C_TEXT)
        if USE_12H_CLOCK:
            set_label_safe(clock_lbl, "{} {}".format(DAYS[wd], format_12h(hh, mm)), C_BLUE)
        else:
            set_label_safe(clock_lbl, "{} {:02d}:{:02d}".format(DAYS[wd], hh, mm), C_BLUE)
    except Exception as e:
        print("RTC clock error:", e)


def get_device_date_time():
    try:
        dt = rtc.datetime()
        y, mo, d, hh, mm = dt[0], dt[1], dt[2], dt[4], dt[5]
        try:
            ss = dt[6]
        except:
            ss = 0
        if y < 2024:
            return None, None
        return "{:04d}-{:02d}-{:02d}".format(y, mo, d), "{:02d}:{:02d}:{:02d}".format(hh, mm, ss)
    except Exception as e:
        print("Device time error:", e)
        return None, None

# ---------------- SENSORS ----------------
env3 = None
try:
    env3 = unit.get(unit.ENV3, unit.PORTA)
    print("ENV3 OK on PORT A")
except Exception as e:
    print("ENV3 init error:", e)

pir_unit = None
pir_pin = None
try:
    pir_unit = unit.get(unit.PIR, unit.PORTB)
    print("PIR OK on PORT B")
except:
    try:
        pir_pin = Pin(26, Pin.IN)
        print("PIR using GPIO26")
    except Exception as e:
        print("PIR not available:", e)


def read_motion():
    try:
        if pir_unit is not None:
            return int(pir_unit.state)
        if pir_pin is not None:
            return int(pir_pin.value())
    except Exception as e:
        print("PIR read error:", e)
    return 0

I2C_ENV = None
SGP30_ADDR = 0x58
CMD_INIT_AIR = b'\x20\x03'
CMD_MEASURE_AIR = b'\x20\x08'
try:
    I2C_ENV = I2C(0, scl=Pin(13), sda=Pin(14), freq=100000)
    print("I2C scan Port C:", I2C_ENV.scan())
    try:
        I2C_ENV.writeto(SGP30_ADDR, CMD_INIT_AIR)
        time.sleep(1)
        print("SGP30 init attempted")
    except Exception as e:
        print("SGP30 init safe error:", e)
except Exception as e:
    print("I2C init error:", e)
    I2C_ENV = None


def _crc8(data2):
    crc = 0xFF
    for b in data2:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x31) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def sgp30_measure_safe():
    try:
        if I2C_ENV is None:
            return None, None
        I2C_ENV.writeto(SGP30_ADDR, CMD_MEASURE_AIR)
        time.sleep_ms(50)
        data = I2C_ENV.readfrom(SGP30_ADDR, 6)
        if len(data) != 6:
            return None, None
        if _crc8(data[0:2]) != data[2]:
            return None, None
        if _crc8(data[3:5]) != data[5]:
            return None, None
        eco2 = (data[0] << 8) | data[1]
        tvoc = (data[3] << 8) | data[4]
        return eco2, tvoc
    except Exception as e:
        print("SGP30 SAFE ERROR:", e)
        return None, None

# ---------------- HTTP ----------------
def get_json(path):
    r = urequests.get(CLOUD_BASE + path)
    raw = r.text
    r.close()
    print("GET", path, raw[:120])
    return ujson.loads(raw), raw


def post_json(path, payload):
    headers = {"Content-Type": "application/json"}
    r = urequests.post(CLOUD_BASE + path, data=ujson.dumps(payload), headers=headers)
    raw = r.text
    r.close()
    print("POST", path, raw[:120])
    return ujson.loads(raw), raw

# ---------------- CLOUD SEND ----------------
def send_to_cloud(t, h, p, motion, tvoc_ppb=None, eco2_ppm=None):
    dev_date, dev_time = get_device_date_time()
    values = {
        "source": SOURCE_ID,
        "indoor_temp": t,
        "indoor_humidity": h,
        "indoor_pressure": p,
        "motion_detected": motion,
    }
    if dev_date is not None:
        values["date"] = dev_date
    if dev_time is not None:
        values["time"] = dev_time
    if tvoc_ppb is not None:
        values["indoor_tvoc_ppb"] = tvoc_ppb
    if eco2_ppm is not None:
        values["indoor_eco2_ppm"] = eco2_ppm
    payload = {"passwd": HASH, "values": values}
    try:
        data, raw = post_json("/send-to-bigquery", payload)
        if data.get("status") == "ok":
            set_status("MOTION SENT" if motion == 1 else "SENT OK", C_OK)
            return True
        set_status("SEND ?", C_WARN)
        return False
    except Exception as e:
        print("Send error:", e)
        set_status("SEND ERR", C_ERR)
        return False

# ---------------- AI VOICE ----------------
def play_audio_b64(audio_b64):
    try:
        if not audio_b64:
            set_status("NO AUDIO", C_WARN)
            return False
        set_status("AI DECODE", C_WARN)
        wav_bytes = ubinascii.a2b_base64(audio_b64)
        filename = "/flash/ai_answer.wav"
        with open(filename, "wb") as f:
            f.write(wav_bytes)
        set_status("AI PLAY", C_WARN)
        try:
            speaker.playWAV(filename, volume=SPEAKER_VOLUME)
        except Exception as e:
            print("speaker.playWAV /flash error:", e)
            try:
                speaker.playWAV("ai_answer.wav", volume=SPEAKER_VOLUME)
            except Exception as e2:
                print("speaker.playWAV fallback error:", e2)
                set_status("PLAY ERR", C_ERR)
                return False
        set_status("AI SPOKE", C_OK)
        return True
    except Exception as e:
        print("Audio decode/play error:", e)
        set_status("AUDIO ERR", C_ERR)
        return False


def build_ai_question():
    icon = last_outdoor_icon or "unknown"
    return AI_BASE_PROMPT + " " + AI_REQUEST.format(icon)


def ask_ai_voice():
    try:
        set_status("AI ASK", C_WARN)
        payload = {"question": build_ai_question(), "audio": REQUEST_AUDIO, "max_chars": AI_MAX_CHARS}
        data, raw = post_json("/voice/ask", payload)
        set_status("AI GOT", C_WARN)
        if "error" in data:
            print("AI backend error:", data.get("error"))
            set_status("AI ERR", C_ERR)
            return False
        if "audio_b64" in data:
            return play_audio_b64(data.get("audio_b64", ""))
        if "answer" in data:
            print("AI answer text only:", data.get("answer", ""))
            set_status("AI NOAUD", C_WARN)
            return False
        set_status("AI BAD", C_WARN)
        return False
    except Exception as e:
        print("AI voice request error:", e)
        set_status("AI REQ ERR", C_ERR)
        return False


def background_ai_startup_once():
    global startup_ai_done
    if startup_ai_done or not RUN_STARTUP_AI_IN_BACKGROUND:
        return
    if not wifi_is_connected():
        return
    startup_ai_done = True
    try:
        set_status("AI TEST", C_WARN)
        payload = {"question": build_ai_question(), "audio": True, "max_chars": AI_MAX_CHARS}
        data, raw = post_json("/voice/ask", payload)
        if "audio_b64" in data:
            play_audio_b64(data.get("audio_b64", ""))
            set_status("AI OK", C_OK)
        elif "answer" in data:
            print("Startup AI answer:", data.get("answer", ""))
            set_status("AI OK", C_OK)
        else:
            set_status("AI NOAUD", C_WARN)
    except Exception as e:
        print("Startup AI background error:", e)
        set_status("AI FAIL", C_ERR)

# ---------------- OUTDOOR WEATHER ICON ----------------
def show_weather_icon(icon_code, fallback_desc=None):
    global last_icon_code
    if not icon_code:
        draw_weather_icon(fallback_desc or "", 128, 58)
        return
    if icon_code == last_icon_code:
        return
    last_icon_code = icon_code
    try:
        url = "https://openweathermap.org/img/wn/{}.png".format(icon_code)
        r = urequests.get(url)
        img_data = r.content
        r.close()
        filename = "/flash/weather.png"
        with open(filename, "wb") as f:
            f.write(img_data)
        try:
            lcd.fillRect(100, 36, 52, 52, C_CARD)
            lcd.image(104, 38, filename)
        except Exception as e:
            print("lcd.image failed:", e)
            draw_weather_icon(fallback_desc or "", 128, 58)
    except Exception as e:
        print("ICON ERROR:", e)
        draw_weather_icon(fallback_desc or "", 128, 58)

# ---------------- WEATHER ----------------
def fetch_outdoor():
    global last_outdoor_icon
    try:
        data, raw = get_json("/weather/mini")
        t = data.get("t")
        desc = data.get("d", "")
        icon = data.get("icon")
        last_outdoor_icon = icon
        d_lower = (desc or "").lower()
        if "few clouds" in d_lower or "scattered clouds" in d_lower:
            icon = "02d"
        set_label_safe(out_temp_lbl, temp_text(t, 0), C_BLUE)
        set_label_safe(out_desc_lbl, weather_symbol(desc), C_MUTED)
        show_weather_icon(icon, desc)
        print("Outdoor OK:", t, desc, icon)
        return True
    except Exception as e:
        print("Outdoor fetch error:", e)
        set_status("OUT ERR", C_ERR)
        return False


def fetch_forecast():
    try:
        days_list, raw = get_json("/forecast/mini")
        icon_positions = [(84, 222), (187, 222), (290, 222)]
        for i, lbl in enumerate(fc_lbls):
            if i >= len(days_list):
                set_label_safe(lbl, "---", C_MUTED)
                lcd.fillRect(icon_positions[i][0] - 16, icon_positions[i][1] - 12, 34, 26, C_CARD)
                continue
            d = days_list[i]
            day_name = d.get("n", "---")
            temp = d.get("t", "--")
            symbol = d.get("s", "")
            icon = d.get("icon", "")
            text = "{} {}".format(day_name, temp_text(temp, 0))
            if len(text) > 9:
                text = text[:9]
            set_label_safe(lbl, text, C_TEXT)
            draw_forecast_icon_code(icon, symbol, icon_positions[i][0], icon_positions[i][1])
        print("Forecast OK:", len(days_list), "days")
        return True
    except Exception as e:
        print("Forecast fetch error:", e)
        set_status("FC ERR", C_ERR)
        return False


def boot_sync():
    global last_temp_value, last_hum_value, last_tvoc_value, last_eco2_value
    try:
        data, raw = get_json("/indoor/latest")
        t = data.get("indoor_temp")
        h = data.get("indoor_humidity")
        tvoc = data.get("indoor_tvoc_ppb")
        eco2 = data.get("indoor_eco2_ppm")
        if t is not None:
            last_temp_value = float(t)
        if h is not None:
            last_hum_value = float(h)
        if tvoc is not None:
            last_tvoc_value = int(tvoc)
        if eco2 is not None:
            last_eco2_value = int(eco2)
        display_last_values()
        set_status("SYNCED", C_OK)
    except Exception as e:
        print("Boot sync failed:", e)
        set_status("NO SYNC", C_ERR)


def display_last_values():
    global last_hum_dot, last_tvoc_dot, last_eco2_dot
    if last_temp_value is not None:
        set_label_safe(temp_lbl, temp_text(last_temp_value, 1), C_TEXT)
    else:
        set_label_safe(temp_lbl, "--" + DEG_C, C_MUTED)
    h_dot = humidity_dot_color(last_hum_value)
    if last_hum_value is not None:
        set_label_safe(hum_lbl, "{:.0f}%".format(last_hum_value), C_ERR if h_dot == DOT_BAD else C_WARN if h_dot == DOT_MID else C_TEXT)
    else:
        set_label_safe(hum_lbl, "--%", C_MUTED)
    if h_dot != last_hum_dot:
        draw_dot(dot_hum[0], dot_hum[1], h_dot)
        last_hum_dot = h_dot
    tv_dot = tvoc_dot_color(last_tvoc_value)
    if last_tvoc_value is not None:
        set_label_safe(tvoc_lbl, str(last_tvoc_value), C_ERR if tv_dot == DOT_BAD else C_WARN if tv_dot == DOT_MID else C_TEXT)
    else:
        set_label_safe(tvoc_lbl, "--", C_MUTED)
    if tv_dot != last_tvoc_dot:
        draw_dot(dot_tvoc[0], dot_tvoc[1], tv_dot)
        last_tvoc_dot = tv_dot
    co_dot = eco2_dot_color(last_eco2_value)
    if last_eco2_value is not None:
        set_label_safe(eco2_lbl, str(last_eco2_value), C_ERR if co_dot == DOT_BAD else C_WARN if co_dot == DOT_MID else C_TEXT)
    else:
        set_label_safe(eco2_lbl, "--", C_MUTED)
    if co_dot != last_eco2_dot:
        draw_dot(dot_eco2[0], dot_eco2[1], co_dot)
        last_eco2_dot = co_dot

# ---------------- MAIN APP ----------------
def start_main_app():
    global counter, weather_counter, wifi_check_counter, prev_motion, warmup_ticks, warmup_done
    global last_ai_voice_s, last_motion_send_s, last_motion_state
    global last_temp_value, last_hum_value, last_tvoc_value, last_eco2_value
    build_dashboard_ui()
    update_wifi_badge()
    wait_for_wifi(60)
    rtc_sync_once()
    update_clock()
    update_next_send(counter)
    fetch_outdoor()
    fetch_forecast()
    boot_sync()
    while True:
        if wifi_check_counter >= WIFI_CHECK_PERIOD:
            ensure_wifi_connected()
            wifi_check_counter = 0
        background_ai_startup_once()
        update_wifi_badge()
        update_clock()
        update_next_send(counter)
        t = h = p = None
        if env3 is not None:
            try:
                t = float(env3.temperature)
                h = float(env3.humidity)
                p = float(env3.pressure)
            except Exception as e:
                print("ENV3 read error:", e)
        if t is not None and -20 < t < 60:
            last_temp_value = t
        if h is not None and 0 <= h <= 100:
            last_hum_value = h
        m = read_motion()
        motion_event = False
        if m != last_motion_state:
            print("Motion:", m)
            last_motion_state = m
        now_s = time.time()
        if m == 1 and prev_motion == 0:
            motion_event = True
            set_status("MOTION", C_WARN)
        eco2_ppm, tvoc_ppb = sgp30_measure_safe()
        if tvoc_ppb is not None and 0 <= tvoc_ppb < 60000:
            last_tvoc_value = tvoc_ppb
        if eco2_ppm is not None and 400 <= eco2_ppm < 60000:
            last_eco2_value = eco2_ppm
        display_last_values()
        if motion_event:
            if (now_s - last_motion_send_s) >= MOTION_SEND_COOLDOWN_S:
                if t is not None and h is not None and p is not None:
                    send_to_cloud(round(t, 1), int(round(h)), round(p, 2), 1, tvoc_ppb=tvoc_ppb, eco2_ppm=eco2_ppm)
                    last_motion_send_s = now_s
                else:
                    set_status("MOTION NOENV", C_WARN)
            else:
                set_status("MOTION COOL", C_WARN)
            if (now_s - last_ai_voice_s) >= AI_VOICE_COOLDOWN_S:
                last_ai_voice_s = now_s
                ask_ai_voice()
            else:
                print("AI voice cooldown")
        if warmup_ticks < int(20 / LOOP_DELAY_S):
            warmup_ticks += 1
            if not motion_event:
                set_status("SGP WARM", C_WARN)
        elif not warmup_done:
            warmup_done = True
            set_status("RUN", C_OK)
        if t is not None and h is not None and p is not None:
            if counter >= PERIOD:
                send_to_cloud(round(t, 1), int(round(h)), round(p, 2), 0, tvoc_ppb=tvoc_ppb, eco2_ppm=eco2_ppm)
                counter = 0
        if weather_counter >= WEATHER_PERIOD:
            fetch_outdoor()
            fetch_forecast()
            weather_counter = 0
        prev_motion = m
        counter += 1
        weather_counter += 1
        wifi_check_counter += 1
        wait(LOOP_DELAY_S)

# ---------------- START PROGRAM ----------------
wifi_loading_screen()
while True:
    wait(1)
