from flask import Flask, request, Response
import html
from market_screener import format_output, screen_stocks, screen_options
from openai import OpenAI
import subprocess
import os, json, uuid, time, websocket
from dotenv import load_dotenv
# Load .env file
load_dotenv()

app = Flask(__name__)

client = OpenAI()


# 🔹 Step 1: Intent classification (fast)
def interpret_query(message):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Return ONLY one word: FULL_ANALYSIS, CALLS_ONLY, PUTS_ONLY, or HELP"
                },
                {"role": "user", "content": message}
            ],
            temperature=0
        )

        intent = response.choices[0].message.content.strip().upper()

        if "FULL" in intent:
            return "FULL_ANALYSIS"
        elif "CALL" in intent:
            return "CALLS_ONLY"
        elif "PUT" in intent:
            return "PUTS_ONLY"
        else:
            return "HELP"

    except Exception as e:
        print("LLM ERROR:", str(e))
        return "HELP"


# 🔹 Step 2: OpenClaw (minor task only — formatting polish)
def refine_with_openclaw(text: str) -> str:
    try:
        OPENCLAW_TOKEN = os.getenv("OPENCLAW_TOKEN")
        ws = websocket.create_connection("ws://127.0.0.1:18789/", timeout=5, suppress_origin=True)

        def send_json(payload):
            ws.send(json.dumps(payload))

        def recv_json():
            return json.loads(ws.recv())

        def extract_text(message):
            if not message:
                return ""
            if isinstance(message.get("text"), str):
                return message["text"]
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "\n".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ).strip()
            return ""

        first_msg = recv_json()
        print("OpenClaw first:", first_msg, flush=True)

        connect_id = str(uuid.uuid4())
        send_json({
            "type": "req",
            "id": connect_id,
            "method": "connect",
            "params": {
                "minProtocol": 3,
                "maxProtocol": 3,
                "client": {
                    "id": "gateway-client",
                    "displayName": "whatsapp-flask",
                    "platform": "python",
                    "mode": "backend",
                    "version": "1.0.0",
                    "instanceId": "whatsapp-flask-local"
                },
                "auth": {"token": OPENCLAW_TOKEN},
                "role": "operator",
                "scopes": ["operator.read", "operator.write"]
            }
        })

        while True:
            msg = recv_json()
            print("OpenClaw connect:", msg, flush=True)
            if msg.get("type") == "res" and msg.get("id") == connect_id:
                if not msg.get("ok"):
                    raise RuntimeError(msg.get("error"))
                break

        req_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())

        send_json({
            "type": "req",
            "id": req_id,
            "method": "chat.send",
            "params": {
                "sessionKey": "agent:main:main",
                "message": f"Summarize for WhatsApp in under 100 words:\n{text[:1200]}",
                "idempotencyKey": run_id
            }
        })

        final_text = text
        start = time.time()

        while time.time() - start < 8:
            msg = recv_json()
            print("OpenClaw WS:", msg, flush=True)

            if msg.get("type") == "event" and msg.get("event") in ["chat", "agent", "session.message"]:
                payload = msg.get("payload", {})
                message = payload.get("message", {})
                assistant_text = extract_text(message)

                if assistant_text:
                    final_text = assistant_text

                if payload.get("state") in ["final", "end"] or payload.get("phase") == "end":
                    break

        ws.close()
        return final_text

    except Exception as e:
        print("OpenClaw WS ERROR:", str(e), flush=True)
        return text

@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    try:
        incoming_msg = request.form.get("Body", "")
        print("Incoming:", incoming_msg, flush=True)

        intent = interpret_query(incoming_msg)
        print("Intent:", intent, flush=True)

        # 🔹 Step 3: Core logic (fast)
        if intent == "FULL_ANALYSIS":
            reply = format_output()

        elif intent == "CALLS_ONLY":
            stock_df = screen_stocks()
            calls, _ = screen_options(stock_df)

            if calls.empty:
                reply = "No good call options found."
            else:
                reply = "\n".join([
                    f"{i+1}. {row['Ticker']} {row['Expiry']} ${row['strike']} CALL"
                    for i, row in calls.head(5).iterrows()
                ])

        elif intent == "PUTS_ONLY":
            stock_df = screen_stocks()
            _, puts = screen_options(stock_df)

            if puts.empty:
                reply = "No good put options found."
            else:
                reply = "\n".join([
                    f"{i+1}. {row['Ticker']} {row['Expiry']} ${row['strike']} PUT"
                    for i, row in puts.head(5).iterrows()
                ])

        else:
            reply = (
                "📈 Try:\n"
                "- analyze market\n"
                "- top calls\n"
                "- top puts"
            )

        # 🔹 Step 4: OPTIONAL OpenClaw refinement (safe)
        reply = refine_with_openclaw(reply)

        # 🔹 Step 5: Return safely
        safe_reply = html.escape(reply[:1200])

        return Response(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{safe_reply}</Message>
</Response>""", mimetype="text/xml")

    except Exception as e:
        print("ERROR:", str(e))
        return Response("Error", status=200)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)