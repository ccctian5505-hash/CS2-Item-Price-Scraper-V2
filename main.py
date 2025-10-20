import os
import time
import requests
import unicodedata
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import traceback
import urllib.parse

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# === Clean item name properly for Steam ===
def clean_item_name(name):
    # Normalize and replace characters
    name = name.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    name = name.replace("–", "-").replace("—", "-").replace("\xa0", " ")
    name = name.replace("™", "\u2122")  # Ensure correct TM symbol
    name = name.replace("★", "★")       # Keep star as-is
    name = unicodedata.normalize("NFKC", name)
    return name.strip()

# === Get price from Steam ===
def get_price(item_name, retries=3):
    url = "https://steamcommunity.com/market/priceoverview/"
    params = {
        "country": "PH",
        "currency": 12,
        "appid": 730,
        "market_hash_name": item_name,
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Encode safely
    params["market_hash_name"] = urllib.parse.quote(params["market_hash_name"], safe="")

    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    return data.get("lowest_price") or data.get("median_price") or "No price listed"
        except Exception:
            pass
        time.sleep(2)
    return "Error fetching price"

# === Telegram Commands ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *CS2 Price Checker Bot*\n\n"
        "Send item names (one per line) to check their Steam Market prices in PHP.\n\n"
        "Example:\n"
        "```\n★ Bowie Knife | Bright Water (Minimal Wear)\nStatTrak™ Glock-18 | Moonrise (Field-Tested)\n```",
        parse_mode="Markdown"
    )

async def scrape_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        items_text = update.message.text.strip()
        items = [line.strip() for line in items_text.splitlines() if line.strip()]
        if not items:
            await update.message.reply_text("⚠️ Please send valid item names (one per line).")
            return

        loading_msg = await update.message.reply_text(f"⏳ Starting scrape for {len(items)} items...")

        ph_time = datetime.now(pytz.timezone("Asia/Manila"))
        now = ph_time.strftime("%Y-%m-%d_%H-%M")
        output_file = f"Price_Checker_CS2_{now}.txt"

        results, total_value, success_count, fail_count = [], 0.0, 0, 0

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("Source Name\tScraped Name\tPrice (PHP)\n")

            for i, item in enumerate(items, start=1):
                clean_name = clean_item_name(item)
                price = get_price(clean_name)

                # Convert price text to numeric
                clean_price = str(price).replace("₱", "").replace("P", "").replace(",", "").strip()
                try:
                    total_value += float(clean_price)
                except ValueError:
                    pass

                if price not in ["Error fetching price", "No price listed"]:
                    success_count += 1
                else:
                    fail_count += 1

                results.append(f"{item} → {price}")
                f.write(f"{item}\t{clean_name}\t{price}\n")

                # Update progress
                if i % 20 == 0 or i == len(items):
                    await update.message.reply_text(f"📊 Progress: {i}/{len(items)} items scraped...")

                time.sleep(2.5)

        await loading_msg.delete()

        # Send results
        result_text = "\n".join(results)
        chunk_size = 3500
        for i in range(0, len(result_text), chunk_size):
            await update.message.reply_text(result_text[i:i + chunk_size])

        summary = (
            f"\n✅ *Scraping complete!*\n"
            f"📦 Total Items: {len(items)}\n"
            f"✅ Success: {success_count}\n"
            f"❌ Failed: {fail_count}\n"
            f"💰 Total Value: ₱{total_value:,.2f}"
        )
        await update.message.reply_text(summary, parse_mode="Markdown")

        await context.bot.send_document(chat_id=update.effective_chat.id, document=open(output_file, "rb"))

    except Exception:
        await update.message.reply_text(f"❌ Error:\n```\n{traceback.format_exc()}\n```", parse_mode="Markdown")

# === MAIN ===
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, scrape_items))
    print("🤖 CS2 Price Checker Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
