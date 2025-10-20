import os
import time
import requests
import unicodedata
from datetime import datetime
import pytz
from urllib.parse import quote
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import traceback

# === ENVIRONMENT VARIABLES ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# === CLEAN ITEM NAME (remove ™ and normalize special chars) ===
def clean_item_name(name: str) -> str:
    # Remove trademark & other symbols that Steam's API may not like
    replacements = {
        "™": "",
        "®": "",
        "★": "",          # remove star (optional)
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "\u00a0": " ",    # non-breaking space
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    # Normalize unicode (NFKC) and trim
    name = unicodedata.normalize("NFKC", name)
    return name.strip()

# === SCRAPE PRICE FUNCTION (PHP currency, CS2 by default uses appid=730) ===
def get_price(item_name: str, appid: int = 730, retries: int = 3) -> str:
    # URL encode the cleaned name to be safe
    encoded_name = quote(item_name, safe='')
    url = f"https://steamcommunity.com/market/priceoverview/?country=PH&currency=12&appid={appid}&market_hash_name={encoded_name}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept-Language": "en-US,en;q=0.9",
    }

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    # prefer lowest_price, fallback to median_price
                    return data.get("lowest_price") or data.get("median_price") or "No price listed"
            else:
                # non-200 — wait and retry
                time.sleep(2)
        except Exception:
            # ignore and retry after a short wait
            time.sleep(2)
    return "No price listed"

# === TELEGRAM COMMANDS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Send me item names (one per line). I will remove trademark symbols (™) and scrape Steam Market prices in PHP.\n\n"
        "Example input:\n"
        "```\nStatTrak™ AK-47 | Redline (Field-Tested)\n★ M9 Bayonet | Doppler\nRevolution Case\n```",
        parse_mode="Markdown",
    )

# === SCRAPE HANDLER ===
async def scrape_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # extract text from message
        items_text = (update.message.text or "").strip()
        items = [ln.strip() for ln in items_text.splitlines() if ln.strip()]

        if not items:
            await update.message.reply_text("⚠️ Please send item names (one per line).")
            return

        # start timing
        start_time = time.time()

        # send initial loading message
        loading = await update.message.reply_text(f"⏳ Starting scrape for {len(items)} items...")

        # prepare output filename (PH timezone)
        ph_time = datetime.now(pytz.timezone("Asia/Manila"))
        now = ph_time.strftime("%Y-%m-%d_%H-%M")
        output_file = f"Price_Checker_CS2_{now}.txt"

        results = []
        success_count = 0
        fail_count = 0
        total_value = 0.0

        # write header and rows
        with open(output_file, "w", encoding="utf-8") as fout:
            fout.write("Source Name\tScraped Name\tPrice (PHP)\n")

            for i, src_item in enumerate(items, start=1):
                cleaned = clean_item_name(src_item)
                price = get_price(cleaned, appid=730)  # CS2 uses 730

                # try parse numeric value for total
                price_num = 0.0
                if isinstance(price, str) and price not in ("No price listed", ""):
                    # remove currency symbols and commas/spaces
                    p = price.replace("₱", "").replace("P", "").replace(",", "").replace(" ", "").strip()
                    # sometimes price contains non-numeric characters, attempt float
                    try:
                        price_num = float(p)
                        total_value += price_num
                    except Exception:
                        # can't parse numeric
                        price_num = 0.0

                if price != "No price listed":
                    success_count += 1
                else:
                    fail_count += 1

                results.append(f"{src_item} → {price}")
                fout.write(f"{src_item}\t{cleaned}\t{price}\n")

                # progress update in Telegram every 20 items (and on last)
                if i % 20 == 0 or i == len(items):
                    await update.message.reply_text(f"📊 Progress: {i}/{len(items)} items scraped...")

                # polite delay to avoid rate limits — adjust as needed
                time.sleep(2.5)

        # remove loading message
        await loading.delete()

        # send the results back in chunks (messages)
        result_text = "\n".join(results)
        max_chunk = 3500
        for start_idx in range(0, len(result_text), max_chunk):
            chunk = result_text[start_idx:start_idx + max_chunk]
            await update.message.reply_text(chunk)

        # elapsed and summary
        elapsed = time.time() - start_time
        mins, secs = divmod(int(elapsed), 60)
        summary = (
            f"\n✅ *Scraping complete!*\n"
            f"📦 Total Items: {len(items)}\n"
            f"✅ Success: {success_count}\n"
            f"❌ Failed: {fail_count}\n"
            f"💰 Total Value: ₱{total_value:,.2f}\n"
            f"⏱ Duration: {mins}m {secs}s"
        )
        await update.message.reply_text(summary, parse_mode="Markdown")

        # send txt file
        await context.bot.send_document(chat_id=update.effective_chat.id, document=open(output_file, "rb"))

    except Exception:
        err = traceback.format_exc()
        try:
            await update.message.reply_text(f"❌ Error occurred:\n```\n{err}\n```", parse_mode="Markdown")
        except Exception:
            # last-resort print
            print("Failed to notify user about error:\n", err)

# === MAIN ===
def main():
    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN environment variable is missing.")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, scrape_items))
    print("🤖 CS2 Price Checker Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
