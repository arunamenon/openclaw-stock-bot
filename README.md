# 📈 WhatsApp AI Stock Bot (OpenClaw + OpenAI)

Build an AI-powered WhatsApp assistant that understands user intent, processes it through agent workflows, and returns intelligent stock insights — all in real time.

---

## 🚀 What This Project Does

This project enables you to:

* 📱 Send a message via WhatsApp
* 🧠 Classify intent using OpenAI
* 🤖 Process using OpenClaw agent workflows
* 📊 Generate stock insights (calls/puts, summaries)
* 💬 Respond back instantly on WhatsApp

---

## 🧱 Tech Stack

* **Backend**: Flask
* **LLM**: OpenAI GPT-4o Mini
* **Agent Framework**: OpenClaw
* **Messaging**: Twilio WhatsApp API
* **Tunneling**: ngrok

---

## 🏗️ Architecture

User (WhatsApp)
⬇
Twilio Webhook
⬇
Flask Backend
⬇
OpenAI (Intent Classification)
⬇
OpenClaw (Agent Processing)
⬇
Response → WhatsApp

---

## ⚙️ Setup Instructions

### 1. Clone Repo

```bash
git clone https://github.com/YOUR_USERNAME/openclaw-stock-bot.git
cd openclaw-stock-bot
```

---

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate   # Mac
```

---

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

### 4. Add Environment Variables

Create `.env` file:

```
OPENAI_API_KEY=your_key
OPENCLAW_TOKEN=your_token
```

---

### 5. Run Flask App

```bash
python app.py
```

---

### 6. Start ngrok and setup Twilio

```bash
ngrok http 5001
```

Copy the HTTPS URL (example):

```
https://abc123.ngrok-free.app
```

---

## 📱 Twilio WhatsApp Configuration

### 7️⃣ Setup Twilio Account

* Go to: https://www.twilio.com/
* Create an account and log in

### 9️⃣ Activate WhatsApp Sandbox

Open:

https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn

You will see:

* Sandbox number
* A **join code**

---

### 🔟 Join Sandbox from Your Phone

Send this message on WhatsApp:

```
join <your-code>
```

Example:

```
join bright-tree
```

---

### 1️⃣1️⃣ Configure Webhook

In Twilio Console:

* Navigate to **Messaging → WhatsApp Sandbox**
* Find: **“When a message comes in”**

---

## 💬 Example Usage

Send message on WhatsApp:

```
Analyze market
```

Bot responds with:

- Summary
- Insights
- Calls/Puts

---

## 📌 Future Improvements

- Add real-time stock APIs
- Add portfolio tracking
- Add multi-agent workflows
- UI dashboard

---

## 👨‍💻 Author

Arun Menon

---

## ⭐ If you found this useful

Give the repo a ⭐ and share!

---
