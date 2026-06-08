import os
import json
import hmac
import hashlib
import base64
import urllib.request
import threading
from flask import Flask, request, abort
from groq import Groq

app = Flask(__name__)

LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
USER_ID = os.environ.get("LINE_USER_ID", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

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

HELP_TEXT = """👋 MA備戰衝衝衝 Bot 使用說明

📋 觸發方式：
「擬答：」+ 你的回答內容
→ 模擬面試官將批改你的答案

範例：
擬答：我認為金控導入AI KYC應先從低風險客群開始Pilot，評估錯誤率後再逐步擴大...

📅 每日日報：
每天早上 8:00 自動推播"""


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


def process_feedback(user_text: str):
    try:
        push_line_message("⏳ 模擬面試官批改中，請稍候...")
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ],
            max_tokens=1500
        )
        feedback = response.choices[0].message.content
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

        if user_text.startswith("擬答") or user_text.startswith("擬打"):
            answer = user_text.split("：", 1)[-1].strip() if "：" in user_text else user_text[2:].strip()
            t = threading.Thread(target=process_feedback, args=(answer,))
            t.daemon = True
            t.start()
        elif user_text in ["說明", "help", "Help", "HELP", "?", "？"]:
            push_line_message(HELP_TEXT)
        else:
            push_line_message('請用「擬答：」開頭輸入你的答案，例如：\n擬答：我認為應該先分析ROI...')

    return "OK", 200


@app.route("/ping", methods=["GET"])
def ping():
    return "pong", 200


@app.route("/", methods=["GET"])
def health():
    return "✅ MA 備戰 LINE Bot 運行中", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
