import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from playwright.async_api import async_playwright

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola! Envíame el nombre de la aplicación que deseas buscar en HappyMod.")

async def procesar_busqueda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not TOKEN:
        await update.message.reply_text("El token del bot no está configurado en el servidor.")
        return

    nombre_app = update.message.text.strip()
    mensaje_espera = await update.message.reply_text(f"Buscando '{nombre_app}', por favor espera unos segundos...")

    apk_path = None
    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context_browser = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context_browser.new_page()

            # Navegar a HappyMod
            await page.goto("https://www.happymod.cloud/", timeout=60000)
            
            # Localizar barra de búsqueda e introducir la consulta
            search_input_selector = "input[name='q'], input[type='text'], .search-input"
            await page.wait_for_selector(search_input_selector, timeout=10000)
            await page.fill(search_input_selector, nombre_app)
            await page.press(search_input_selector, "Enter")

            # Esperar resultados y hacer clic en el primero
            await page.wait_for_load_state("networkidle", timeout=10000)
            first_result = "h3 a, .title a, .search-item-title, .box-img-s a"
            await page.click(first_result, timeout=5000)

            # Esperar página de descarga y capturar el archivo
            await page.wait_for_load_state("networkidle", timeout=10000)
            async with page.expect_download(timeout=30000) as download_info:
                download_button = "a.download-btn, .btn-download, a:has-text('Download')"
                await page.click(download_button, timeout=5000)
            
            download = await download_info.value
            os.makedirs("./downloads", exist_ok=True)
            apk_path = os.path.join("./downloads", download.suggested_filename)
            await download.save_as(apk_path)
            await browser.close()

    except Exception as e:
        if browser:
            await browser.close()
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=mensaje_espera.message_id,
            text=f"No se pudo completar la descarga automáticamente. Es posible que los selectores requieran ajustes. Detalle: {str(e)}"
        )
        return

    if apk_path and os.path.exists(apk_path):
        file_size = os.path.getsize(apk_path) / (1024 * 1024)
        
        if file_size > 50:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=mensaje_espera.message_id,
                text="El archivo supera los 50 MB permitidos por la API estándar de Telegram y no se puede enviar."
            )
            os.remove(apk_path)
        else:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=mensaje_espera.message_id,
                text="¡Descarga completada! Enviando archivo..."
            )
            with open(apk_path, 'rb') as apk_file:
                await update.message.reply_document(document=apk_file, caption=f"APK de: {nombre_app}")
            os.remove(apk_path)
    else:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=mensaje_espera.message_id,
            text="No se pudo obtener el archivo APK."
        )

def main():
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN no está definido.")
        return
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), procesar_busqueda))
    application.run_polling()

if __name__ == "__main__":
    main()
