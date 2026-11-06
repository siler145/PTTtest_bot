import os
import socket
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# 讀取雲端環境變數
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
LINE_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_TOKEN) if LINE_TOKEN else None
line_handler = WebhookHandler(LINE_SECRET) if LINE_SECRET else None

# PTT / JPTT 雙重檢測邏輯 (修正版)
def check_ptt_status():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    # 1. 檢測 PTT 主站
    ptt_ok = False
    try:
        r = requests.get('https://www.ptt.cc/bbs/index.html', headers=headers, timeout=5)
        if r.status_code == 200:
            ptt_ok = True
    except:
        pass

    if not ptt_ok:
        try:
            s = socket.create_connection(('ptt.cc', 23), timeout=5)
            s.close()
            ptt_ok = True
        except:
            pass

    # 2. 檢測 JPTT API
    jptt_ok = False
    try:
        res = requests.get('https://api.jptt.cc/v1/hot_articles', headers=headers, timeout=5)
        # 只要伺服器有回應 (狀態碼小於 500 代表伺服器運作中)
        if res.status_code < 500:
            jptt_ok = True
    except:
        pass

    # 3. 診斷結果判斷
    if not ptt_ok:
        return "❌ PTT 全面宕機！\n主站與 Web 版均無法連線。"
    elif ptt_ok and not jptt_ok:
        return "⚠️ PTT 主站正常，但 JPTT 伺服器異常！\n請改用 Pitt、Mo PTT 或 Web 版登入。"
    else:
        return "✅ PTT 與 JPTT 連線均正常！\n若仍無法登入，請檢查個人帳密或切換 IP (開關飛行模式)。"

# --- LINE Webhook 接收點 ---
@app.route("/callback/line", methods=['POST'])
def line_callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        line_handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

if line_handler:
    @line_handler.add(MessageEvent, message=TextMessage)
    def handle_line_message(event):
        msg = event.message.text.strip().lower()
        if "ptt" in msg:
            result = check_ptt_status()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=result))

# --- Telegram Webhook 接收點 ---
@app.route("/callback/telegram", methods=['POST'])
def telegram_callback():
    data = request.get_json()
    if data and "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"]["text"].lower()
        if "ptt" in text:
            result = check_ptt_status()
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={
                "chat_id": chat_id,
                "text": result
            })
    return 'OK'

@app.route("/")
def index():
    return "PTT Monitor Service is Running!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))