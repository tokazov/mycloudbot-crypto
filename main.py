"""
MyCloudBot Crypto Payment Service
Создаёт платёжные ссылки Cryptomus и обрабатывает webhook
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import hashlib, json, base64, httpx, os, time

app = FastAPI()

MERCHANT_ID = os.getenv("CRYPTOMUS_MERCHANT_ID", "9f81f0f1-60c7-477c-9e39-f3e65f1c8797")
API_KEY = os.getenv("CRYPTOMUS_API_KEY", "zpqHBVr1yGNHQffDnoDsrTJTRE14t0zhhVjh5ugpyYgBO655GHu4G9GqI1r4U8xkRoF0vfmJP0QuGJfaySbG5lKQnlqAMUFJ2dhhuzFMJz7qnAtWV5XD8r4cFelSQOi5")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8765627934:AAHeaYn2CajXekIw03Ht7dAxmYgy-OUThIY")
ADMIN_ID = os.getenv("ADMIN_ID", "5309206282")
HETZNER_BOT_URL = os.getenv("HETZNER_BOT_URL", "http://46.225.80.44:8080")
PRICE_USD = 49

def make_sign(payload: dict) -> str:
    data_str = base64.b64encode(json.dumps(payload).encode()).decode()
    return hashlib.md5((data_str + API_KEY).encode()).hexdigest()

async def tg_send(chat_id, text):
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        )

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/create-payment/{uid}")
async def create_payment(uid: int):
    """Создаёт платёжную ссылку для клиента"""
    order_id = f"mcb_{uid}_{int(time.time())}"
    payload = {
        "amount": str(PRICE_USD),
        "currency": "USD",
        "order_id": order_id,
        "url_callback": "https://mycloudbot-crypto-production.up.railway.app/webhook",
        "url_success": "https://t.me/mycloudbot_ai_bot",
        "lifetime": 3600,
        "is_payment_multiple": False,
    }
    sign = make_sign(payload)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.cryptomus.com/v1/payment",
            json=payload,
            headers={"merchant": MERCHANT_ID, "sign": sign, "Content-Type": "application/json"}
        )
    data = resp.json()
    if resp.status_code == 200 and data.get("result", {}).get("url"):
        return {"url": data["result"]["url"], "order_id": order_id}
    raise HTTPException(status_code=400, detail=str(data))

@app.post("/webhook")
async def webhook(request: Request):
    """Обрабатывает уведомление от Cryptomus об оплате"""
    data = await request.json()
    received_sign = data.pop("sign", "")
    data_str = base64.b64encode(json.dumps(data).encode()).decode()
    expected_sign = hashlib.md5((data_str + API_KEY).encode()).hexdigest()

    if received_sign != expected_sign:
        raise HTTPException(status_code=400, detail="Invalid sign")

    if data.get("payment_status") in ("paid", "paid_over"):
        order_id = data.get("order_id", "")
        parts = order_id.split("_")
        if len(parts) >= 2 and parts[0] == "mcb":
            uid = int(parts[1])
            paid_until = int(time.time()) + 30 * 24 * 3600

            # Активируем подписку на Hetzner
            async with httpx.AsyncClient(timeout=5) as client:
                try:
                    await client.post(
                        f"{HETZNER_BOT_URL}/internal/activate",
                        json={"uid": uid, "paid_until": paid_until}
                    )
                except: pass

            # Уведомляем клиента и админа
            await tg_send(uid, "✅ <b>Оплата подтверждена!</b>\n\nПодписка активна на 30 дней.\nТвой AI-партнёр работает 🚀")
            await tg_send(ADMIN_ID, f"💰 <b>Крипто-оплата!</b>\n🆔 {uid}\n💵 ${PRICE_USD} USDT\n📋 {order_id}")

    return {"status": "ok"}
