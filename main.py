import os
import socket
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
LINE_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_TOKEN) if LINE_TOKEN else None
line_handler = WebhookHandler(LINE_SECRET) if LINE_SECRET else None

# PTT (Web / SSH / Telnet) 與 JPTT (WebSocket) 完整四通道診斷邏輯
def check_ptt_status():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    cookies = {'over18': '1'}
    
    # 1. 檢測 Web 網頁版
    web_ok = False
    try:
        r = requests.get('https://www.ptt.cc/bbs/index.html', headers=headers, cookies=cookies, timeout=4)
        if r.status_code < 500:  # 只要不是 5xx 伺服器錯誤都算 Web 服務存活
            web_ok = True
    except:
        pass

    # 備用檢測：若 HTTP 被阻擋，改測 www.ptt.cc 443 埠連線
    if not web_ok:
        try:
            s = socket.create_connection(('www.ptt.cc', 443), timeout=4)
            s.close()
            web_ok = True
        except:
            pass

    # 2. 檢測 SSH 通道 (ptt.cc:22)
    ssh_ok = False
    try:
        s = socket.create_connection(('ptt.cc', 22), timeout=4)
        s.close()
        ssh_ok = True
    except:
        pass

    # 3. 檢測 Telnet 通道 (ptt.cc:23)
    telnet_ok = False
    try:
        s = socket.create_connection(('ptt.cc', 23), timeout=4)
        s.close()
        telnet_ok = True
    except:
        pass

    # 4. 檢測 JPTT WebSocket 通道 (ws.ptt.cc:443)
    jptt_ok = False
    try:
        s = socket.create_connection(('ws.ptt.cc', 443), timeout=4)
        s.close()
        jptt_ok = True
    except:
        pass

    # 5. 彙整診斷報告
    if web_ok and ssh_ok and telnet_ok and jptt_ok:
        return "✅ PTT 所有連線通道 (Web / SSH / Telnet / JPTT) 均正常！\n若仍無法登入，請嘗試切換手機網路 IP (開關飛行模式)。"
    
    if not web_ok and not ssh_ok and not telnet_ok and not jptt_ok:
        return "❌ PTT 全面宕機！\nWeb、SSH、Telnet 與 WebSocket 均無回應。"

    report = ["📊 PTT / JPTT 連線通道診斷報告："]
    report.append(f"🌐 網頁版 (Web): {'✅ 正常' if web_ok else '❌ 斷線'}")
    report.append(f"🔒 SSH 通道 (Port 22): {'✅ 正常' if ssh_ok else '❌ 斷線'}")
    report.append(f"📞 Telnet 通道 (Port 23): {'✅ 正常' if telnet_ok else '❌ 斷線'}")
    report.append(f"⚡ JPTT 通道 (ws.ptt.cc:443): {'✅ 正常' if jptt_ok else '❌ 斷線'}")

    report.append("\n💡 診斷建議：")
    if not jptt_ok:
        report.append("• JPTT 目前連線異常！" + (" 但可改用 SSH 或網頁版登入。" if (ssh_ok or web_ok) else ""))
    if not ssh_ok:
        report.append("• SSH 通道無法連線。")
    if web_ok:
        report.append("• 網頁版依然正常，可先開啟瀏覽器看板。")

    return "\n".join(report)

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