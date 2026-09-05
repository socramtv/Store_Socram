import os
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))

# --- Mini servidor web HTTP interno para cumplir con el plan gratuito de Render ---
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
# ------------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📚 ¡Hola! Envíame el título del libro o autor que deseas buscar y te proporcionaré sus enlaces de lectura y descarga directa.")

async def buscar_libros(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not TOKEN:
        return

    query = update.message.text.strip()
    mensaje_espera = await update.message.reply_text(f"🔍 Buscando '{query}' y comprobando archivos disponibles...")

    url = f"https://openlibrary.org/search.json?q={requests.utils.quote(query)}&limit=5&fields=key,title,author_name,first_publish_year,ia,ebook_access"
    
    try:
        headers = {"User-Agent": "TelegramBookBot/1.0 (botcontacto@gmail.com)"}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=mensaje_espera.message_id,
                text="Error al conectar con los servidores de Open Library."
            )
            return

        data = response.json()
        docs = data.get("docs", [])

        if not docs:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=mensaje_espera.message_id,
                text="No se encontraron libros que coincidan con tu búsqueda."
            )
            return

        texto_respuesta = f"📖 *Resultados para '{query}':*\n\n"
        
        for i, doc in enumerate(docs[:5], 1):
            title = doc.get("title", "Título desconocido")
            authors = ", ".join(doc.get("author_name", ["Autor desconocido"]))
            year = doc.get("first_publish_year", "Desconocido")
            key = doc.get("key", "")
            web_link = f"https://openlibrary.org{key}" if key else "https://openlibrary.org"
            
            texto_respuesta += f"*{i}. {title}*\n"
            texto_respuesta += f"   👤 *Autor:* {authors} ({year})\n"
            texto_respuesta += f"   🔗 [Ficha en Open Library]({web_link})\n"
            
            # Comprobar descargas directas en Internet Archive
            ia_list = doc.get("ia")
            if ia_list and isinstance(ia_list, list) and len(ia_list) > 0:
                ia_id = ia_list[0]
                pdf_link = f"https://archive.org/download/{ia_id}/{ia_id}.pdf"
                epub_link = f"https://archive.org/download/{ia_id}/{ia_id}.epub"
                texto_respuesta += f"   📥 *Descargas:* [PDF]({pdf_link}) | [EPUB]({epub_link})\n"
            else:
                texto_respuesta += f"   🔒 *Disponibilidad:* Solo lectura en web / Préstamo\n"
                
            texto_respuesta += "\n"

        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=mensaje_espera.message_id,
            text=texto_respuesta,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )

    except Exception as e:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=mensaje_espera.message_id,
            text=f"Ocurrió un error al procesar la búsqueda: {str(e)[:100]}"
        )

def main():
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN no está definido.")
        return
    
    # Inicia el mini servidor web en segundo plano
    threading.Thread(target=start_http_server, daemon=True).start()
    
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), buscar_libros))
    application.run_polling()

# ¡Aquí estaba el error de los guiones bajos!
if __name__ == "__main__":
    main()
