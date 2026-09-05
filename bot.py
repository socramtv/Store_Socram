import os
import requests
import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# --- CONFIGURACIÓN DE LOGS ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") 
PORT = int(os.getenv("PORT", "10000"))

# --- Mini servidor web HTTP interno para Render ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot activo y funcionando!")
    def log_message(self, format, *args):
        pass

def start_http_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthCheckHandler)
    server.serve_forever()

# --- FUNCIONES DEL BOT ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Comando /start recibido de {update.effective_user.first_name}")
    await update.message.reply_text("📚 ¡Hola Marco! Envíame el título del libro o autor que deseas buscar y te mostraré los resultados.")

async def buscar_libros(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not TOKEN:
        return

    query = update.message.text.strip()
    logger.info(f"Búsqueda recibida: {query}")
    mensaje_espera = await update.message.reply_text(f"🔍 Buscando '{query}' en Google Books...")

    if GOOGLE_API_KEY:
        url = f"https://www.googleapis.com/books/v1/volumes?q={requests.utils.quote(query)}&maxResults=5&key={GOOGLE_API_KEY}"
    else:
        url = f"https://www.googleapis.com/books/v1/volumes?q={requests.utils.quote(query)}&maxResults=5"
    
    try:
        response = requests.get(url, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"Error Google Books: {response.status_code}")
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=mensaje_espera.message_id,
                text=f"Error al conectar con los servidores (Código {response.status_code})."
            )
            return

        data = response.json()
        items = data.get("items", [])

        if not items:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=mensaje_espera.message_id,
                text="No se encontraron libros que coincidan con tu búsqueda."
            )
            return

        texto_respuesta = f"📖 *Resultados para '{query}':*\n\n"
        
        for i, item in enumerate(items, 1):
            vol_info = item.get("volumeInfo", {})
            acc_info = item.get("accessInfo", {})
            
            title = vol_info.get("title", "Título desconocido")
            authors = ", ".join(vol_info.get("authors", ["Autor desconocido"]))
            year = vol_info.get("publishedDate", "Desconocido")[:4]
            
            texto_respuesta += f"*{i}. {title}*\n"
            texto_respuesta += f"   👤 *Autor:* {authors}\n"
            texto_respuesta += f"   📅 *Año:* {year}\n"
            
            info_link = vol_info.get("infoLink", "")
            epub_link = acc_info.get("epub", {}).get("downloadLink", "")
            pdf_link = acc_info.get("pdf", {}).get("downloadLink", "")
            web_reader = acc_info.get("webReaderLink", "")
            
            enlaces = []
            if epub_link:
                enlaces.append(f"[Descargar EPUB]({epub_link})")
            if pdf_link:
                enlaces.append(f"[Descargar PDF]({pdf_link})")
            
            if not enlaces and web_reader:
                enlaces.append(f"[Leer en Web]({web_reader})")
            
            if not enlaces and info_link:
                enlaces.append(f"[Ficha del Libro]({info_link})")
                
            texto_respuesta += f"   📥 *Opciones:* {' | '.join(enlaces)}\n\n"

        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=mensaje_espera.message_id,
            text=texto_respuesta,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(f"Error en la búsqueda: {e}")
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=mensaje_espera.message_id,
            text=f"Ocurrió un error al procesar la búsqueda."
        )

def main():
    logger.info("Iniciando el script del bot...")
    
    if not TOKEN:
        logger.error("¡ERROR CRÍTICO! La variable TELEGRAM_BOT_TOKEN no está definida.")
        return
    
    logger.info(f"Arrancando servidor HTTP en puerto {PORT}...")
    threading.Thread(target=start_http_server, daemon=True).start()
    
    logger.info("Configurando conexión con Telegram...")
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Registro de manejadores (Handlers)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), buscar_libros))
    
    logger.info("Bot listo. Iniciando el modo de escucha (Polling)...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
