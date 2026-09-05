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
PORT = int(os.getenv("PORT", "10000"))

# --- Mini servidor web HTTP interno ---
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

# --- LÓGICA DEL BOT ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📚 ¡Hola! Envíame el título del libro o autor que deseas buscar. Te ofreceré enlaces de descarga directa.")

async def buscar_libros(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not TOKEN:
        return

    query = update.message.text.strip()
    mensaje_espera = await update.message.reply_text(f"🔍 Buscando '{query}' en la biblioteca libre...")

    # Petición a la API de Gutendex (Project Gutenberg)
    url = f"https://gutendex.com/books?search={requests.utils.quote(query)}"
    
    try:
        # Añadimos un User-Agent de navegador real para evitar que nos bloqueen
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"Error Gutendex: {response.status_code} - {response.text}")
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=mensaje_espera.message_id,
                text=f"Error al conectar con los servidores (Código {response.status_code})."
            )
            return

        data = response.json()
        results = data.get("results", [])

        if not results:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=mensaje_espera.message_id,
                text="No se encontraron libros que coincidan con tu búsqueda."
            )
            return

        texto_respuesta = f"📖 *Resultados para '{query}':*\n\n"
        
        # Procesamos hasta 5 resultados
        for i, doc in enumerate(results[:5], 1):
            title = doc.get("title", "Título desconocido")
            
            # Formatear autores
            authors_data = doc.get("authors", [])
            if authors_data:
                authors = ", ".join([a.get("name", "") for a in authors_data])
                authors = authors.replace(", ", " ") 
            else:
                authors = "Autor desconocido"

            # Idiomas disponibles
            languages = ", ".join(doc.get("languages", ["Desconocido"])).upper()
            
            texto_respuesta += f"*{i}. {title}*\n"
            texto_respuesta += f"   👤 *Autor:* {authors}\n"
            texto_respuesta += f"   🌐 *Idioma:* {languages}\n"
            
            # Extraer enlaces de descarga
            formats = doc.get("formats", {})
            epub_link = formats.get("application/epub+zip")
            pdf_link = formats.get("application/pdf")
            html_link = formats.get("text/html")
            
            enlaces = []
            if epub_link:
                enlaces.append(f"[EPUB]({epub_link})")
            if pdf_link:
                enlaces.append(f"[PDF]({pdf_link})")
            if html_link:
                html_clean = html_link.split(';')[0] if ';' in html_link else html_link
                enlaces.append(f"[Leer Web]({html_clean})")
                
            if enlaces:
                texto_respuesta += f"   📥 *Descargas:* {' | '.join(enlaces)}\n\n"
            else:
                texto_respuesta += "   📥 *Descargas:* No disponibles temporalmente\n\n"

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
            text=f"Ocurrió un error de conexión al procesar la búsqueda."
        )

def main():
    logger.info("Iniciando el script del bot...")
    
    if not TOKEN:
        logger.error("¡ERROR CRÍTICO! La variable TELEGRAM_BOT_TOKEN no está definida o está vacía.")
        return
    
    logger.info(f"Arrancando servidor HTTP en puerto {PORT}...")
    threading.Thread(target=start_http_server, daemon=True).start()
    
    logger.info("Configurando conexión con Telegram...")
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), buscar_libros))
    
    logger.info("Bot listo. Iniciando el modo de escucha (Polling)...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
