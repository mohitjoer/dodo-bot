import aiohttp
import discord
import asyncio
from discord.ext import commands
import logging
import time
import os

logger = logging.getLogger(__name__)

class RenderOptimizedBot(commands.Bot):
    """Bot class extracted from root bot.py. Pass configuration into the constructor.

    Parameters:
    - guild_id: int | None - target guild for command syncing
    - github_token: str | None - optional GitHub token
    - is_render: bool - whether running on Render (affects timeouts/rate-limits)
    """
    def __init__(self, guild_id=None, github_token=None, is_render=False):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix='!',
            intents=intents,
            heartbeat_timeout=60.0,
            chunk_guilds_at_startup=False,
        )

        self.IS_RENDER = is_render
        self.github_headers = {
            'User-Agent': 'GitHub-Discord-Bot/1.0',
            'Accept': 'application/vnd.github.v3+json'
        }
        if github_token:
            self.github_headers['Authorization'] = f'token {github_token}'

        self.session = None
        self.target_guild_id = guild_id

        # rate limiting/backoff
        self.last_api_call = 0
        self.api_call_delay = 2.0 if self.IS_RENDER else 1.0
        self.startup_complete = False

        # connection monitoring
        self.last_heartbeat = time.time()
        self.connection_issues = 0
        # command sync tracking
        self._commands_synced = False

    async def setup_hook(self):
        logger.info("🔧 Setting up bot session...")
        timeout = aiohttp.ClientTimeout(total=45, connect=15)
        connector = aiohttp.TCPConnector(
            limit=5,
            limit_per_host=3,
            ttl_dns_cache=300,
            use_dns_cache=True,
            enable_cleanup_closed=True,
        )

        self.session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers=self.github_headers
        )

        # helper utility to make sure commands successfully connect to Discord
        registered = list(self.tree.get_commands())
        logger.info(f"🔎 Currently {len(registered)} app commands registered on the tree")

        if not self.IS_RENDER:
            if registered:
                await self._sync_commands()
            else:
                logger.info("🔄 No commands found during setup_hook — deferring command sync to on_ready")
        else:
            logger.info("🔄 Delaying command sync for Render environment...")

    async def _sync_commands(self):
        try:
            # Log what commands the tree currently exposes for debugging
            available = list(self.tree.get_commands())
            logger.info(f"🔎 About to sync {len(available)} commands globally: {[c.name for c in available]}")
            synced = await self.tree.sync()
            logger.info(f"✅ Synced {len(synced)} commands globally")
        except Exception as e:
            logger.error(f"❌ Failed to sync commands: {e}")

    async def on_ready(self):
        logger.info(f"🚀 Bot ready! {self.user} connected to Discord")
        logger.info(f"📊 Connected to {len(self.guilds)} guilds")

        if self.target_guild_id:
            target_guild = self.get_guild(self.target_guild_id)
            if target_guild:
                logger.info(f"✅ Connected to target guild: {target_guild.name}")
            else:
                logger.warning(f"⚠️ Not in target guild {self.target_guild_id}")

        # Ensure commands are synced globally after cogs have been loaded
        if not self._commands_synced:
            logger.info("🔄 Syncing commands globally after successful connection...")
            await asyncio.sleep(3)
            try:
                await self._log_guild_commands()
            except Exception as e:
                logger.debug(f"Could not list global commands before sync: {e}")
            try:
                await self._sync_commands()
                try:
                    await self._log_guild_commands()
                except Exception as e:
                    logger.debug(f"Could not list global commands after sync: {e}")
                self._commands_synced = True
            except Exception as e:
                logger.error(f"❌ Command sync after ready failed: {e}")

        try:
            await self.change_presence(
                status=discord.Status.online,
                activity=discord.Activity(type=discord.ActivityType.watching, name="GitHub repos")
            )
        except Exception as e:
            logger.warning(f"Could not set presence: {e}")

        self.startup_complete = True
        self.last_heartbeat = time.time()

    async def _log_guild_commands(self):
        # diagnostic to list what Discord commands are synced globally
        try:
            app_info = await self.application_info()
            app_id = getattr(app_info, 'id', None)
            if not app_id:
                logger.warning("🔍 Could not determine application id for diagnostics")
                return

            url = f"https://discord.com/api/v10/applications/{app_id}/commands"
            token = os.getenv('DISCORD_TOKEN')
            if not token:
                logger.warning("🔍 DISCORD_TOKEN not available in environment for diagnostic request")
                return

            headers = {"Authorization": f"Bot {token}"}

            session = self.session or aiohttp.ClientSession()

            async with session.get(url, headers=headers) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    text = await resp.text()
                    logger.exception(f"🔍 Failed to parse global commands response (status={resp.status}): {text}")
                    return

            if isinstance(data, list):
                names = [c.get('name') for c in data]
                logger.info(f"🔍 Discord has {len(data)} registered global app commands: {names}")
            else:
                logger.info(f"🔍 Unexpected global commands payload: {data}")

            if self.session is None:
                await session.close()

        except Exception as e:
            logger.exception(f"🔍 Error while fetching global commands: {e}")

    async def on_resumed(self):
        logger.info("🔄 Bot resumed connection")
        self.last_heartbeat = time.time()
        self.connection_issues = 0

    async def on_disconnect(self):
        logger.warning("⚠️ Bot disconnected from Discord")
        self.connection_issues += 1

    async def on_error(self, event, *args, **kwargs):
        logger.error(f"Bot error in {event}: {args}", exc_info=True)

    async def close(self):
        logger.info("🛑 Bot shutting down...")
        if self.session and not self.session.closed:
            await self.session.close()
        await super().close()
