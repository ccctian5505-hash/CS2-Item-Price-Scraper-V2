import os
import time
import requests
import unicodedata
from datetime import datetime
import pytz
from urllib.parse import quote_plus
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import traceback

# === ENVIRONMENT VARIABLES ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# === CLEAN ITEM NAME (DO NOT REMOVE ™ OR ★) ===
def clean_item_name(name: str) -> str:
    replacements = {
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "\u00a0": " ",  # non-breaking space
    }
    for old, new in replacements.items():
        name = name.replace(old, new)

    # full unicode normalization (Steam needs exact symbols)
    name = unicodedata.normalize("NFKC", name)

    return name.strip()


# === GET PRICE (CS2 – appid=730) ===
def get_price(item_name: str, appid: int = 730, retries: int = 3) -> str:
    encoded_name = quote_plus(item_name)

    url = (
        "https://steamcommunity.com/market/priceoverview/"
        f"?country=PH&currency=12&appid={appid}&market_hash_name={encoded_name}"
    )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept-Language": "en-US,en;q=0.9",
    }

    for _ in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    return data.get("lowest_price") or data.get("median_price") or "No price listed"
            time.sleep(1.5)
        except Exception:
            time.sleep(1.5)

    return "No price listed"


# === START COMMAND ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Send me item names (one per line). I will fetch Steam Market prices (PHP).\n\n"
        "Example:\n"
        "StatTrak™ AWP | Asiimov (Field-Tested)\n"
        "★ Butterfly Knife | Doppler\n"
        "Revolution Case"
    )


# === MAIN SCRAPER HANDLER ===
async def scrape_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        items_text = update.message.text.strip()
        items = [ln.strip() for ln in items_text.splitlines() if ln.strip()]

        if not items:
            await update.message.reply_text("⚠️ Please send item names.")
            return

        loading = await update.message.reply_text(f"⏳ Scraping {len(items)} items...")

        ph_time = datetime.now(pytz.timezone("Asia/Manila"))
        now = ph_time.strftime("%Y-%m-%d_%H-%M")
        output_file = f"Price_Checker_CS2_{now}.txt"

        results = []
        total_value = 0.0
        success = 0
        fail = 0

        with open(output_file, "w", encoding="utf-8") as fout:
            fout.write("Source Name\tScraped Name\tPrice (PHP)\n")

            for i, src in enumerate(items, start=1):
                cleaned = clean_item_name(src)
                price = get_price(cleaned)

                # parse number if possible
                num = 0.0
                if price not in ("No price listed", ""):
                    try:
                        p = (
                            price.replace("₱", "")
                            .replace("P", "")
                            .replace(",", "")
                            .replace(" ", "")
                        )
                        num = float(p)
                        total_value += num
                        success += 1
                    except:
                        fail += 1
                else:
                    fail += 1

                fout.write(f"{src}\t{cleaned}\t{price}\n")
                results.append(f"{src} → {price}")

                if i % 20 == 0 or i == len(items):
                    await update.message.reply_text(f"📊 Progress: {i}/{len(items)} done...")

                time.sleep(2.2)

        await loading.delete()

        # send results (split into chunks)
        big_text = "\n".join(results)
        for i in range(0, len(big_text), 3500):
            await update.message.reply_text(big_text[i:i+3500])

        summary = (
            f"✅ Done!\n"
            f"📦 Total: {len(items)}\n"
            f"✔️ Success: {success}\n"
            f"❌ Failed: {fail}\n"
            f"💰 Total Value: ₱{total_value:,.2f}"
        )
        await update.message.reply_text(summary)

        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=open(output_file, "rb")
        )

    except Exception:
        err = traceback.format_exc()
        await update.message.reply_text(f"❌ ERROR:\n```\n{err}\n```", parse_mode="Markdown")


# === MAIN BOT ===
def main():
    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN missing.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, scrape_items))

    print("🤖 CS2 Price Checker Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
