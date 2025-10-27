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
        if self.target_guild_id:
            guild = discord.Object(id=self.target_guild_id)
            try:
                # Log what commands the tree currently exposes for debugging
                available = list(self.tree.get_commands())
                logger.info(f"🔎 About to sync {len(available)} commands: {[c.name for c in available]}")
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

                # Ensure commands are synced after cogs have been loaded.
                # There is a startup race where setup_hook can run before
                # extensions are loaded in some deployment flows. Run a
                # guarded sync here once per startup to avoid syncing too
                # early and ending up with 0 commands registered.
                if not self._commands_synced:
                    logger.info("🔄 Syncing commands after successful connection...")
                    # small delay to allow any external cog loading to finish
                    await asyncio.sleep(3)
                    # diagnostic: list what Discord currently has registered for this
                    # application's guild commands before we attempt to sync
                    try:
                        await self._log_guild_commands()
                    except Exception as e:
                        logger.debug(f"Could not list guild commands before sync: {e}")
                    try:
                        await self._sync_commands()
                        # diagnostic: inspect guild commands after syncing as well
                        try:
                            await self._log_guild_commands()
                        except Exception as e:
                            logger.debug(f"Could not list guild commands after sync: {e}")
                        self._commands_synced = True
                    except Exception as e:
                        logger.error(f"❌ Command sync after ready failed: {e}")
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

    async def _log_guild_commands(self):
        """Fetch and log the application's guild commands from Discord REST API.

        This helps debug when tree.sync reports zero changes but commands are
        not visible in the client — it shows what Discord actually has
        registered for the application in the target guild.
        """
        if not self.target_guild_id:
            logger.info("🔍 No target guild id set; skipping guild command listing")
            return

        try:
            app_info = await self.application_info()
            app_id = getattr(app_info, 'id', None)
            if not app_id:
                logger.warning("🔍 Could not determine application id for diagnostics")
                return

            url = f"https://discord.com/api/v10/applications/{app_id}/guilds/{self.target_guild_id}/commands"
            token = os.getenv('DISCORD_TOKEN')
            if not token:
                logger.warning("🔍 DISCORD_TOKEN not available in environment for diagnostic request")
                return

            headers = {"Authorization": f"Bot {token}"}

            # Use our existing aiohttp session (created in setup_hook) if available
            session = self.session or aiohttp.ClientSession()
            close_session = self.session is None

            async with session.get(url, headers=headers) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    text = await resp.text()
                    logger.error(f"🔍 Failed to parse guild commands response (status={resp.status}): {text}")
                    return

            if isinstance(data, list):
                names = [c.get('name') for c in data]
                logger.info(f"🔍 Discord guild has {len(data)} registered app commands: {names}")
            else:
                logger.info(f"🔍 Unexpected guild commands payload: {data}")

        except Exception as e:
            logger.error(f"🔍 Error while fetching guild commands: {e}")

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
