import os
import sys
import time
import asyncio
import threading
import logging
from dotenv import load_dotenv
import discord

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.utils.core import RenderOptimizedBot
from src.utils.web_server import create_flask_app

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Load env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID")) if os.getenv("GUILD_ID") else None
PORT = int(os.getenv("PORT", 5000))
IS_RENDER = os.getenv("RENDER") is not None


def run_flask(bot_instance):
    try:
        logger.info(f"🌐 Starting Flask server on port {PORT}")
        app = create_flask_app(bot=bot_instance, is_render=IS_RENDER, guild_id=GUILD_ID)
        app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Flask server error: {e}")


async def start_bot(bot_instance):
    try:
        logger.info("🔄 Starting Discord bot...")
        try:
            await bot_instance.load_extension('src.cogs.github_cog')
        except Exception as e:
            logger.error(f"Failed to load github_cog: {e}")
        try:
            await bot_instance.load_extension('src.cogs.admin_cog')
        except Exception as e:
            logger.error(f"Failed to load admin_cog: {e}")

        await bot_instance.start(TOKEN)

    except discord.LoginFailure:
        logger.error("❌ Invalid Discord token!")
        return False
    except discord.HTTPException as e:
        error_str = str(e)
        if "429" in error_str or "rate limit" in error_str.lower():
            logger.error("❌ Discord rate limited - this is a known Render issue")
            return False
        else:
            logger.error(f"❌ Discord HTTP error: {e}")
            return False
    except Exception as e:
        logger.error(f"❌ Unexpected bot startup error: {e}")
        return False

    return True


def main():
    if not TOKEN:
        logger.error("❌ DISCORD_TOKEN not found in environment variables!")
        sys.exit(1)

    bot = RenderOptimizedBot(guild_id=GUILD_ID, github_token=GITHUB_TOKEN, is_render=IS_RENDER)

    flask_thread = threading.Thread(target=run_flask, args=(bot,), daemon=True)
    flask_thread.start()
    logger.info(f"🌐 Flask health server started on port {PORT}")

    time.sleep(1)

    try:
        asyncio.run(start_bot(bot))
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")


if __name__ == "__main__":
    main()
    