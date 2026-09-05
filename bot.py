import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📚 ¡Hola! Envíame el título del libro o el nombre del autor que deseas buscar en Open Library.")

async def buscar_libros(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not TOKEN:
        return

    query = update.message.text.strip()
    mensaje_espera = await update.message.reply_text(f"🔍 Buscando '{query}' en Open Library...")

    # Petición a la API JSON pública de Open Library
    url = f"https://openlibrary.org/search.json?q={requests.utils.quote(query)}&limit=5"
    
    try:
        # Open Library solicita un User-Agent identificativo en las peticiones frecuentes
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
            year = doc.get("first_publish_year", "Año desconocido")
            key = doc.get("key", "") # Ej: /works/OL123W
            link = f"https://openlibrary.org{key}" if key else "https://openlibrary.org"
            
            texto_respuesta += f"*{i}. {title}*\n"
            texto_respuesta += f"   👤 *Autor:* {authors}\n"
            texto_respuesta += f"   📅 *Publicación:* {year}\n"
            texto_respuesta += f"   🔗 [Ver / Leer en Open Library]({link})\n\n"

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
    
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), buscar_libros))
    application.run_polling()

if __name__ == "__main__":
    main()
