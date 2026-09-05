import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from playwright.async_api import async_playwright

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))

# --- Mini servidor web HTTP interno para cumplir con el puerto libre de Render ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")
    def log_message(self, format, *args):
        pass # Evita saturar los logs de Render con peticiones de estado

def start_http_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthCheckHandler)
    server.serve_forever()
# ------------------------------------------------------------------------------

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
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars"
                ]
            )
            
            context_browser = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            
            await context_browser.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            page = await context_browser.new_page()

            # Navegar a HappyMod
            await page.goto("https://www.happymod.cloud/", timeout=60000)
            
            # Buscar aplicación
            search_input_selector = "input[name='q'], input[type='text'], .search-input"
            await page.wait_for_selector(search_input_selector, timeout=15000)
            await page.fill(search_input_selector, nombre_app)
            await page.press(search_input_selector, "Enter")

            await asyncio.sleep(3)

            # Clic en el primer resultado
            first_result = "a.title, .card-title a, h3 a, .search-item a, .box-img-s a"
            await page.wait_for_selector(first_result, timeout=15000)
            await page.click(first_result)

            await asyncio.sleep(2)
            
            # Descargar APK
            async with page.expect_download(timeout=45000) as download_info:
                download_button = "a.download-btn, .btn-download, a.btn-normal, a:has-text('Download')"
                await page.click(download_button)
            
            download = await download_info.value
            os.makedirs("./downloads", exist_ok=True)
            apk_path = os.path.join("./downloads", download.suggested_filename)
            await download.save_as(apk_path)
            await browser.close()

    except Exception as e:
        if browser:
            try:
                await browser.close()
            except:
                pass
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=mensaje_espera.message_id,
            text=f"No se pudo completar la descarga automáticamente. Es posible que la web requiera resolución manual de CAPTCHA o haya bloqueado la petición. Detalle técnico: {str(e)[:150]}"
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

    # Inicia el servidor HTTP interno en segundo plano para abrir el puerto en Render
    threading.Thread(target=start_http_server, daemon=True).start()

    # Arranca el bot de Telegram con polling
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), procesar_busqueda))
    application.run_polling()

if __name__ == "__main__":
    main()
