import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from playwright.async_api import async_playwright

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")
    def log_message(self, format, *args):
        pass

def start_http_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthCheckHandler)
    server.serve_forever()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola! Envíame el nombre de la aplicación que deseas buscar en HappyMod.")

async def procesar_busqueda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not TOKEN:
        await update.message.reply_text("El token del bot no está configurado en el servidor.")
        return

    nombre_app = update.message.text.strip().replace(" ", "+")
    mensaje_espera = await update.message.reply_text(f"Buscando '{update.message.text.strip()}', por favor espera unos segundos...")

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

            # Navegación directa a la URL de resultados de búsqueda para evitar bloqueos de formulario
            search_url = f"https://www.happymod.cloud/search.html?q={nombre_app}"
            await page.goto(search_url, timeout=60000)
            
            # Esperar a que aparezca cualquier enlace de resultado de la lista
            result_selector = "a.title, .card-title a, h3 a, .search-item a, .box-img-s a, .p-name a"
            await page.wait_for_selector(result_selector, timeout=15000)
            
            # Hacer clic en el primer resultado válido
            await page.click(result_selector)

            await asyncio.sleep(2)
            
            # Capturar la descarga al pulsar el botón de descarga final
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
            text=f"No se pudo completar la descarga. Es posible que Cloudflare haya bloqueado la IP de Render o la app no exista. Detalle: {str(e)[:120]}"
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
                await update.message.reply_document(document=apk_file, caption=f"APK de la búsqueda")
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

    threading.Thread(target=start_http_server, daemon=True).start()

    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), procesar_busqueda))
    application.run_polling()

if __name__ == "__main__":
    main()
