import os
import json
import hmac
import hashlib
import base64
import urllib.request
import threading
from flask import Flask, request, abort
import anthropic

app = Flask(__name__)

LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
USER_ID = os.environ.get("LINE_USER_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SYSTEM_PROMPT = """你是嚴厲、專業的高階主管，正在對 MA 候選人 Verna 進行模擬面試批改。

Verna 的背景：
- 政大 BBA（GPA 4.23）+ 廣告學雙主修，NTU MIB 候選人
- Ogilvy CRM 實習：Python 自動化，open rate +32%，效率 +70%
- 國泰人壽實習：GCP + Gemini LLM 情感分析，200k+ 筆資料
- bettermilk 電商：Market Basket Analysis，銷售量 +23%
- TSMC Youth Dream Program：28 人團隊 Lead，NT$300k，全國第三名

當收到 Verna 的個案擬答或行為面試答案時，你必須：
1. 【邏輯盲點】：指出架構漏洞、過於表面或缺乏數據的地方
2. 【優化建議】：給出具體修改方向與更高級的商務措辭
3. 【評分】：X/10 分，並說明理由
4. 【一句話總結】：最關鍵的一個改進點

口吻：犀利、直接、有建設性，不要客套。"""


def verify_signature(body: bytes, signature: str) -> bool:
    hash_val = hmac.new(LINE_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(hash_val).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def push_line_message(text: str):
    url = "https://api.line.me/v2/bot/message/push"
    chunks = [text[i:i+2000] for i in range(0, len(text), 2000)]
    for chunk in chunks:
        payload = json.dumps({
            "to": USER_ID,
            "messages": [{"type": "text", "text": chunk}]
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={
                "Authorization": f"Bearer {LINE_TOKEN}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        urllib.request.urlopen(req)


def process_message(user_text: str):
    """背景執行：呼叫 Claude 並推播結果"""
    try:
        push_line_message("⏳ 模擬面試官批改中，請稍候 10 秒...")
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_text}]
        )
        feedback = response.content[0].text
        push_line_message(f"📋 模擬面試官批改結果：\n\n{feedback}")
    except Exception as e:
        push_line_message(f"❌ 批改時發生錯誤：{str(e)}")


@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=False)

    if not verify_signature(body, signature):
        abort(400)

    data = json.loads(body)

    for event in data.get("events", []):
        if event.get("type") != "message":
            continue
        if event["message"].get("type") != "text":
            continue

        user_text = event["message"]["text"].strip()
        if not user_text:
            continue

        # 立刻回傳 200，背景執行批改（避免 LINE 3 秒逾時）
        t = threading.Thread(target=process_message, args=(user_text,))
        t.daemon = True
        t.start()

    return "OK", 200


@app.route("/ping", methods=["GET"])
def ping():
    """防休眠用，讓 UptimeRobot 定時 ping"""
    return "pong", 200


@app.route("/", methods=["GET"])
def health():
    return "✅ MA 備戰 LINE Bot 運行中", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
