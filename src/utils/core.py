import aiohttp
import discord
import asyncio
from discord.ext import commands
import logging
import time

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

        # don't sync commands immediately on Render; cogs can call sync if needed
        if not self.IS_RENDER:
            await self._sync_commands()
        else:
            logger.info("🔄 Delaying command sync for Render environment...")

    async def _sync_commands(self):
        if self.target_guild_id:
            guild = discord.Object(id=self.target_guild_id)
            try:
                synced = await self.tree.sync(guild=guild)
                logger.info(f"✅ Synced {len(synced)} commands to guild {self.target_guild_id}")
            except Exception as e:
                logger.error(f"❌ Failed to sync commands: {e}")
        else:
            logger.warning("⚠️ GUILD_ID not set, skipping command sync")

    async def on_ready(self):
        logger.info(f"🚀 Bot ready! {self.user} connected to Discord")
        logger.info(f"📊 Connected to {len(self.guilds)} guilds")

        if self.target_guild_id:
            target_guild = self.get_guild(self.target_guild_id)
            if target_guild:
                logger.info(f"✅ Connected to target guild: {target_guild.name}")
                if self.IS_RENDER and not self.startup_complete:
                    logger.info("🔄 Syncing commands after successful connection...")
                    await asyncio.sleep(5)
                    await self._sync_commands()
            else:
                logger.warning(f"⚠️ Not in target guild {self.target_guild_id}")

        try:
            await self.change_presence(
                status=discord.Status.online,
                activity=discord.Activity(type=discord.ActivityType.watching, name="GitHub repos")
            )
        except Exception as e:
            logger.warning(f"Could not set presence: {e}")

        self.startup_complete = True
        self.last_heartbeat = time.time()

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
