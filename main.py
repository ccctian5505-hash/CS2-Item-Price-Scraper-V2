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


# === CLEAN ITEM NAME (StatTrak™ + ★ FIXED) ===
def clean_item_name(name: str) -> str:
    # Standardize all characters Steam requires EXACTLY
    replacements = {
        # Normalize quotes and dashes
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "\u00a0": " ",  # non-breaking space

        # Normalize ALL trademark variations → real ™
        "\u2122": "™",  # standard trademark symbol
        "\u0099": "™",  # Windows-1252 hidden symbol
        "™": "™",       # ensure consistent

        # Normalize star variations → real ★
        "★": "★",
        "\u2605": "★",  # star unicode (sometimes different)
    }

    for old, new in replacements.items():
        name = name.replace(old, new)

    # Final unicode normalization
    name = unicodedata.normalize("NFKC", name)

    return name.strip()


# === GET PRICE (from Steam Market) ===
def get_price(item_name: str, appid: int = 730, retries: int = 3) -> str:
    encoded = quote_plus(item_name)

    url = (
        "https://steamcommunity.com/market/priceoverview/"
        f"?country=PH&currency=12&appid={appid}&market_hash_name={encoded}"
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
        except:
            pass
        time.sleep(1.5)

    return "No price listed"


# === /start COMMAND ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Send me CS2 item names (one per line) and I’ll fetch Steam Market prices.\n\n"
        "Example:\n"
        "StatTrak™ AWP | Asiimov (Field-Tested)\n"
        "★ Butterfly Knife | Marble Fade\n"
        "Revolution Case"
    )


# === SCRAPE HANDLER ===
async def scrape_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        items_text = update.message.text.strip()
        items = [ln.strip() for ln in items_text.splitlines() if ln.strip()]

        if not items:
            await update.message.reply_text("⚠️ Please send item names.")
            return

        loading = await update.message.reply_text(f"⏳ Scraping {len(items)} items...")

        # PH timezone timestamp
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

                # attempt numeric parsing
                value = 0.0
                if price not in ("No price listed", ""):
                    try:
                        p = (
                            price.replace("₱", "")
                            .replace("P", "")
                            .replace(",", "")
                            .replace(" ", "")
                            .strip()
                        )
                        value = float(p)
                        total_value += value
                        success += 1
                    except:
                        fail += 1
                else:
                    fail += 1

                fout.write(f"{src}\t{cleaned}\t{price}\n")
                results.append(f"{src} → {price}")

                # Progress update every 20 items
                if i % 20 == 0 or i == len(items):
                    await update.message.reply_text(f"📊 Progress: {i}/{len(items)} done...")

                time.sleep(2.2)

        # Delete loading message
        await loading.delete()

        # Send results in Telegram (chunked)
        full_text = "\n".join(results)
        for i in range(0, len(full_text), 3500):
            await update.message.reply_text(full_text[i:i+3500])

        # Summary
        summary = (
            f"✅ DONE!\n"
            f"📦 Total Items: {len(items)}\n"
            f"✔️ Success: {success}\n"
            f"❌ Failed: {fail}\n"
            f"💰 Total Value: ₱{total_value:,.2f}"
        )
        await update.message.reply_text(summary)

        # Send output file
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=open(output_file, "rb")
        )

    except Exception:
        err = traceback.format_exc()
        await update.message.reply_text(
            f"❌ ERROR:\n```\n{err}\n```",
            parse_mode="Markdown"
        )


# === MAIN BOT ===
def main():
    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN missing in environment variables.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, scrape_items))

    print("🤖 CS2 Price Checker Bot Running...")
    app.run_polling()


if __name__ == "__main__":
    main()
