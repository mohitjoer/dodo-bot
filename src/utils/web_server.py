from flask import Flask, jsonify
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def create_flask_app(bot=None, is_render=False, guild_id=None):
    app = Flask(__name__)

    @app.route('/')
    def home():
        return "🤖 GitHub Discord Bot is running!"

    @app.route('/health')
    def health():
        try:
            bot_status = "offline"
            guild_count = 0
            target_guild = "not_connected"

            if bot and hasattr(bot, 'is_ready') and bot.is_ready():
                bot_status = "online"
                guild_count = len(bot.guilds) if hasattr(bot, 'guilds') else 0
                if guild_id and hasattr(bot, 'get_guild'):
                    target_guild = "connected" if bot.get_guild(guild_id) else "not_found"

            return jsonify({
                "status": "healthy",
                "bot_status": bot_status,
                "timestamp": datetime.utcnow().isoformat(),
                "total_guilds": guild_count,
                "target_guild": target_guild,
                "guild_id": guild_id,
                "uptime": "running",
                "environment": "render" if is_render else "local"
            }), 200

        except Exception as e:
            logger.error(f"Health check error: {e}")
            return jsonify({
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }), 500

    return app
