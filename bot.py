import os
import discord
import asyncio
import threading
import time
import logging
from datetime import datetime, timedelta
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from urllib.parse import urlparse
from flask import Flask, jsonify
import aiohttp
import sys

# Set up logging with more detailed output for debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Suppress some noisy discord.py logs in production
logging.getLogger('discord.http').setLevel(logging.WARNING)
logging.getLogger('discord.gateway').setLevel(logging.INFO)

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID")) if os.getenv("GUILD_ID") else None
PORT = int(os.getenv("PORT", 5000))

# Render-specific settings
IS_RENDER = os.getenv("RENDER") is not None
if IS_RENDER:
    logger.info("🚀 Detected Render deployment environment")

# Flask app for health checks
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 GitHub Discord Bot is running!"

@app.route('/health')
def health():
    """Enhanced health check for Render"""
    try:
        bot_status = "offline"
        guild_count = 0
        target_guild = "not_connected"
        
        if hasattr(bot, 'is_ready') and bot.is_ready():
            bot_status = "online"
            guild_count = len(bot.guilds) if hasattr(bot, 'guilds') else 0
            
            if GUILD_ID and hasattr(bot, 'get_guild'):
                target_guild = "connected" if bot.get_guild(GUILD_ID) else "not_found"
        
        return jsonify({
            "status": "healthy",
            "bot_status": bot_status,
            "timestamp": datetime.utcnow().isoformat(),
            "total_guilds": guild_count,
            "target_guild": target_guild,
            "guild_id": GUILD_ID,
            "uptime": "running",
            "environment": "render" if IS_RENDER else "local"
        }), 200
        
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }), 500

class RenderOptimizedBot(commands.Bot):
    def __init__(self):
        # Conservative intents for Render
        intents = discord.Intents.default()
        intents.message_content = True
        
        super().__init__(
            command_prefix='!',
            intents=intents,
            heartbeat_timeout=60.0,  # Increased timeout for Render
            chunk_guilds_at_startup=False,  # Don't chunk guilds to reduce startup load
        )
        
        self.github_headers = {
            'User-Agent': 'GitHub-Discord-Bot/1.0',
            'Accept': 'application/vnd.github.v3+json'
        }
        if GITHUB_TOKEN:
            self.github_headers['Authorization'] = f'token {GITHUB_TOKEN}'
        
        self.session = None
        self.target_guild_id = GUILD_ID
        
        # Enhanced rate limiting for Render
        self.last_api_call = 0
        self.api_call_delay = 2.0 if IS_RENDER else 1.0  # Slower on Render
        self.startup_complete = False
        
        # Connection monitoring
        self.last_heartbeat = time.time()
        self.connection_issues = 0
    
    async def setup_hook(self):
        """Render-optimized setup"""
        logger.info("🔧 Setting up bot for Render deployment...")
        
        # Create session with conservative settings for Render
        timeout = aiohttp.ClientTimeout(total=45, connect=15)
        connector = aiohttp.TCPConnector(
            limit=5,  # Lower connection limit for Render
            limit_per_host=3,
            ttl_dns_cache=300,
            use_dns_cache=True,
            enable_cleanup_closed=True,
        )
        
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={'User-Agent': 'GitHub-Discord-Bot/1.0'}
        )
        
        # Don't sync commands immediately on Render to avoid rate limits
        if not IS_RENDER:
            await self._sync_commands()
        else:
            logger.info("🔄 Delaying command sync for Render environment...")
    
    async def _sync_commands(self):
        """Separate method for command syncing"""
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
        
        # Check target guild
        if self.target_guild_id:
            target_guild = self.get_guild(self.target_guild_id)
            if target_guild:
                logger.info(f"✅ Connected to target guild: {target_guild.name}")
                
                # Sync commands after successful connection on Render
                if IS_RENDER and not self.startup_complete:
                    logger.info("🔄 Syncing commands after successful connection...")
                    await asyncio.sleep(5)  # Wait a bit before syncing
                    await self._sync_commands()
            else:
                logger.warning(f"⚠️ Not in target guild {self.target_guild_id}")
        
        # Set presence carefully
        try:
            await self.change_presence(
                status=discord.Status.online,
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name="GitHub repos"
                )
            )
        except Exception as e:
            logger.warning(f"Could not set presence: {e}")
        
        self.startup_complete = True
        self.last_heartbeat = time.time()
    
    async def on_resumed(self):
        """Handle reconnections"""
        logger.info("🔄 Bot resumed connection")
        self.last_heartbeat = time.time()
        self.connection_issues = 0
    
    async def on_disconnect(self):
        """Handle disconnections"""
        logger.warning("⚠️ Bot disconnected from Discord")
        self.connection_issues += 1
    
    async def on_error(self, event, *args, **kwargs):
        """Enhanced error handling"""
        logger.error(f"Bot error in {event}: {args}", exc_info=True)
    
    async def close(self):
        """Clean shutdown"""
        logger.info("🛑 Bot shutting down...")
        if self.session and not self.session.closed:
            await self.session.close()
        await super().close()

# Initialize bot
bot = RenderOptimizedBot()

def extract_github_username(text):
    """Extract username from GitHub URL or return the text as-is"""
    if text.startswith("http"):
        path = urlparse(text).path.strip("/")
        return path.split("/")[0] if path else text
    return text.strip()

def extract_github_repo(text):
    """Extract owner and repo from GitHub URL or username/repo format"""
    if text.startswith("http"):
        path = urlparse(text).path.strip("/")
        parts = path.split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
    elif "/" in text:
        parts = text.split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
    return None

def format_date(date_string):
    """Format ISO date string to readable format"""
    if not date_string:
        return "N/A"
    try:
        dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d')
    except:
        return "N/A"

def format_number(num):
    """Format large numbers with K, M suffixes"""
    if num >= 1000000:
        return f"{num/1000000:.1f}M"
    elif num >= 1000:
        return f"{num/1000:.1f}K"
    return str(num)

async def github_request(url):
    """GitHub API request with enhanced error handling for Render"""
    if not bot.session or bot.session.closed:
        logger.error("Session not available for GitHub request")
        return None
    
    try:
        # Enhanced rate limiting for Render
        current_time = time.time()
        time_since_last_call = current_time - bot.last_api_call
        if time_since_last_call < bot.api_call_delay:
            sleep_time = bot.api_call_delay - time_since_last_call
            await asyncio.sleep(sleep_time)
        
        bot.last_api_call = time.time()
        
        async with bot.session.get(url, headers=bot.github_headers) as response:
            # Enhanced rate limit handling
            if response.status == 403:
                rate_limit_remaining = response.headers.get('X-RateLimit-Remaining', '0')
                if rate_limit_remaining == '0':
                    reset_time = response.headers.get('X-RateLimit-Reset', '0')
                    logger.warning(f"GitHub API rate limit exceeded. Resets at: {reset_time}")
                    return "rate_limited"
            
            if response.status == 200:
                return await response.json()
            elif response.status == 404:
                return "not_found"
            else:
                logger.error(f"GitHub API returned status {response.status} for {url}")
                return None
                
    except asyncio.TimeoutError:
        logger.error(f"Timeout error for GitHub request: {url}")
        return None
    except Exception as e:
        logger.error(f"GitHub API Error: {e}")
        return None

@bot.tree.command(name="ping", description="Test if the bot is working")
async def ping(interaction: discord.Interaction):
    """Simple ping command with enhanced error handling"""
    try:
        await interaction.response.defer()
        
        latency = round(bot.latency * 1000)
        guild_info = f" in {interaction.guild.name}" if interaction.guild else ""
        
        # Add environment info
        env_info = " (Render)" if IS_RENDER else " (Local)"
        
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Bot is online and responding{guild_info}{env_info}",
            color=0x00ff00
        )
        embed.add_field(name="Latency", value=f"{latency}ms", inline=True)
        embed.add_field(name="Guilds", value=len(bot.guilds), inline=True)
        embed.add_field(name="Status", value="✅ Healthy", inline=True)
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Ping command error: {e}")
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error occurred", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error occurred", ephemeral=True)
        except:
            pass

@bot.tree.command(name="github_user", description="Get GitHub user profile information")
@app_commands.describe(username="GitHub username or profile URL")
async def github_user(interaction: discord.Interaction, username: str):
    """Fetch and display GitHub user profile with enhanced error handling"""
    try:
        await interaction.response.defer()
        
        username = extract_github_username(username)
        data = await github_request(f"https://api.github.com/users/{username}")
        
        if data == "rate_limited":
            await interaction.followup.send("❌ GitHub API rate limit exceeded. Please try again later.")
            return
        elif data == "not_found":
            await interaction.followup.send(f"❌ User **{username}** not found on GitHub")
            return
        elif not data:
            await interaction.followup.send(f"❌ Failed to fetch data for **{username}**")
            return
        
        embed = discord.Embed(
            title=f"{data.get('name', username)}'s GitHub Profile",
            url=data['html_url'],
            description=data.get('bio', 'No bio available'),
            color=0x238636
        )
        
        embed.set_thumbnail(url=data['avatar_url'])
        embed.add_field(name="👤 Username", value=f"[{username}]({data['html_url']})", inline=True)
        embed.add_field(name="📦 Public Repos", value=format_number(data.get('public_repos', 0)), inline=True)
        embed.add_field(name="👥 Followers", value=format_number(data.get('followers', 0)), inline=True)
        embed.add_field(name="👤 Following", value=format_number(data.get('following', 0)), inline=True)
        embed.add_field(name="📍 Location", value=data.get('location', 'N/A'), inline=True)
        embed.add_field(name="🏢 Company", value=data.get('company', 'N/A'), inline=True)
        embed.add_field(name="📅 Joined", value=format_date(data.get('created_at')), inline=True)
        
        socials = []
        if data.get('blog'):
            socials.append(f"🌐 [Website]({data['blog']})")
        if data.get('twitter_username'):
            socials.append(f"🐦 [Twitter](https://twitter.com/{data['twitter_username']})")
        
        if socials:
            embed.add_field(name="🔗 Links", value=" | ".join(socials), inline=False)
        
        await interaction.followup.send(embed=embed)

    except Exception as e:
        logger.error(f"github_user command error: {e}")
        try:
            await interaction.followup.send("❌ An error occurred while fetching user data.")
        except:
            pass

@bot.tree.command(name="github_repo", description="Get GitHub repository details")
@app_commands.describe(repo="owner/repo or repository URL")
async def github_repo(interaction: discord.Interaction, repo: str):
    """Fetch and display GitHub repository details with robust handling"""
    try:
        await interaction.response.defer()

        parsed = extract_github_repo(repo)
        if not parsed:
            await interaction.followup.send("❌ Please provide a valid repository in the form `owner/repo` or a GitHub URL.")
            return

        owner, name = parsed
        data = await github_request(f"https://api.github.com/repos/{owner}/{name}")

        if data == "rate_limited":
            await interaction.followup.send("❌ GitHub API rate limit exceeded. Please try again later.")
            return
        elif data == "not_found":
            await interaction.followup.send(f"❌ Repository **{owner}/{name}** not found on GitHub")
            return
        elif not data:
            await interaction.followup.send(f"❌ Failed to fetch data for **{owner}/{name}**")
            return

        description = data.get('description') or 'No description provided.'
        embed = discord.Embed(
            title=f"{owner}/{name}",
            url=data.get('html_url', f"https://github.com/{owner}/{name}"),
            description=description,
            color=0x0d1117
        )

        if data.get('owner', {}).get('avatar_url'):
            embed.set_thumbnail(url=data['owner']['avatar_url'])

        # Key stats
        embed.add_field(name="⭐ Stars", value=format_number(data.get('stargazers_count', 0)), inline=True)
        embed.add_field(name="🍴 Forks", value=format_number(data.get('forks_count', 0)), inline=True)
        embed.add_field(name="🐛 Open Issues", value=format_number(data.get('open_issues_count', 0)), inline=True)

        # Meta
        embed.add_field(name="🗣️ Language", value=data.get('language', 'N/A'), inline=True)
        embed.add_field(name="📄 License", value=(data.get('license') or {}).get('name', 'N/A'), inline=True)
        embed.add_field(name="🕒 Updated", value=format_date(data.get('updated_at')), inline=True)

        # Optional links
        links = []
        if data.get('homepage'):
            links.append(f"🌐 [Homepage]({data['homepage']})")
        links.append(f"📦 [Repo]({data.get('html_url', f'https://github.com/{owner}/{name}')} )")
        embed.add_field(name="🔗 Links", value=" | ".join(links), inline=False)

        # Topics
        topics = data.get('topics') or []
        if topics:
            embed.add_field(name="🏷️ Topics", value=", ".join(topics[:10]), inline=False)

        await interaction.followup.send(embed=embed)

    except Exception as e:
        logger.error(f"github_repo command error: {e}")
        try:
            await interaction.followup.send("❌ An error occurred while fetching repository data.")
        except:
            pass


@bot.tree.command(name="github_tree", description="Show GitHub repository file tree")
@app_commands.describe(
    repo="owner/repo or GitHub URL (supports /tree/branch/subpath)",
    max_depth="Maximum depth to display (default 5)"
)
async def github_tree(interaction: discord.Interaction, repo: str, max_depth: int = 5):
    """Fetch and display GitHub repository file tree with size constraint."""
    try:
        await interaction.response.defer()

        # CONFIG / CONSTANTS
        EMBED_COLOR = 0x000000          # define a default embed color (Discord blurple)
        MAX_PATH_LIMIT = 5000           # maximum number of paths we'll process
        MAX_EMBEDS = 4                 # how many embed parts to allow before fallback
        # Discord embed field limit ~1024 chars; keep a safe margin for code fences and other text
        MAX_FIELD_VALUE = 1024 - 15
        # Use a default chunk size not exceeding the safe field value
        MAX_CONTENT_CHARS = min(750, MAX_FIELD_VALUE)

        branch = None
        subpath = ""

        # PARSE REPOSITORY INPUT
        from urllib.parse import urlparse

        if repo.startswith("http"):
            url_parts = urlparse(repo).path.strip("/").split("/")
            if len(url_parts) >= 2:
                owner, name = url_parts[:2]
                # detect /tree/<branch>/optional/subpath...
                if len(url_parts) >= 4 and url_parts[2] == "tree":
                    branch = url_parts[3]
                    subpath = "/".join(url_parts[4:]) if len(url_parts) > 4 else ""
            else:
                await interaction.followup.send("❌ Invalid GitHub URL.")
                return
        elif "/" in repo:
            owner, name = repo.split("/")[:2]
        else:
            await interaction.followup.send("❌ Invalid repository format. Use `owner/repo` or a GitHub URL.")
            return

        # TREE
        repo_data = await github_request(f"https://api.github.com/repos/{owner}/{name}")
        if repo_data == "not_found":
            await interaction.followup.send("❌ Repository not found.")
            return
        if repo_data == "rate_limited":
            await interaction.followup.send("❌ GitHub API rate limit exceeded. Try again later or use a token.")
            return
        if not isinstance(repo_data, dict):
            await interaction.followup.send("❌ Unexpected response from GitHub API.")
            return

        branch = branch or repo_data.get("default_branch", "main")

        tree_url = f"https://api.github.com/repos/{owner}/{name}/git/trees/{branch}?recursive=1"
        tree_data = await github_request(tree_url)

        if tree_data == "not_found":
            await interaction.followup.send(f"❌ Branch `{branch}` or repository tree not found.")
            return
        if tree_data == "rate_limited":
            await interaction.followup.send("❌ GitHub API rate limit exceeded while fetching the tree.")
            return
        if not isinstance(tree_data, dict) or "tree" not in tree_data:
            await interaction.followup.send("❌ Failed to fetch repository tree (unexpected API response).")
            return

        # PATH LIMIT CHECK AND FILTERING 
        all_paths = [item["path"] for item in tree_data.get("tree", []) if item.get("type") in ("blob", "tree")]

        if not all_paths:
            await interaction.followup.send(f"❌ The repository `{owner}/{name}` appears empty on branch `{branch}`.")
            return

        if len(all_paths) > MAX_PATH_LIMIT:
            await interaction.followup.send(
                f"⚠️ **Repository Too Large:** `{owner}/{name}` has **{len(all_paths)}** files/directories, exceeding the limit of **{MAX_PATH_LIMIT}** items.\n"
                f"Try specifying a smaller subpath, e.g. `{owner}/{name}/tree/{branch}/src`."
            )
            return

        paths = []
        if subpath:
            filtered_paths = [p for p in all_paths if p == subpath or p.startswith(subpath + "/")]
            if not filtered_paths:
                await interaction.followup.send(f"❌ Subpath `{subpath}` not found or is a dead end.")
                return

            if any(p.startswith(subpath + "/") for p in filtered_paths):
                subpath_len = len(subpath) + 1
                paths = [p[subpath_len:] for p in filtered_paths if p.startswith(subpath + "/")]
            else:
                # subpath exists but is a single file
                paths = [subpath]
        else:
            paths = all_paths

        if not paths:
            await interaction.followup.send(f"❌ No files or directories found in `{owner}/{name}/{subpath}`.")
            return

        # TREE FORMATTING LOGIC 
        def format_tree(paths_list, max_depth=3):
            tree_dict = {}
            for p in paths_list:
                parts = p.split("/")
                current = tree_dict
                for i, part in enumerate(parts):
                    if i >= max_depth:
                        if isinstance(current, dict) and part not in current:
                            current[part] = "..."
                        break

                    if part not in current:
                        current[part] = {}

                    if current[part] != "...":
                        current = current[part]

                    if i == len(parts) - 1:
                        break

            lines = []

            def build_lines(d, prefix=""):
                def sort_key(item):
                    key, value = item
                    is_dir = isinstance(value, dict) and value != {}
                    return (not is_dir, key.lower())

                sorted_items = sorted(d.items(), key=sort_key)
                for i, (key, value) in enumerate(sorted_items):
                    is_directory = isinstance(value, dict) and value != {}
                    is_truncated = value == "..."
                    is_last = (i == len(sorted_items) - 1)

                    connector = "└── " if is_last else "├── "
                    next_prefix = prefix + ("    " if is_last else "│   ")
                    suffix = "/" if is_directory or is_truncated else ""

                    lines.append(f"{prefix}{connector}{key}{suffix}")

                    if is_directory and value:
                        build_lines(value, next_prefix)

            root_name = f"📦 {owner}/{name}/tree/{branch}/{subpath}" if subpath else f"📦 {owner}/{name}/tree/{branch}"
            lines.append(root_name)
            build_lines(tree_dict)
            return lines

        tree_lines = format_tree(paths, max_depth=max_depth)

        #CHUNKING & TRUNCATION maybe some fixes has to be done here later!
        chunks = []
        current_chunk = []
        current_len = 0

        for line in tree_lines:
            if len(line) > MAX_CONTENT_CHARS:
                line = line[:MAX_CONTENT_CHARS - 3] + "..."

            if current_len + len(line) + 1 > MAX_CONTENT_CHARS:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_len = 0

            current_chunk.append(line)
            current_len += len(line) + 1

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        # If too many chunks, cut and add truncation notice
        if len(chunks) > MAX_EMBEDS:
            chunks = chunks[:MAX_EMBEDS]
            trunc_msg = "\n\n… (Output truncated by embed limit)"
            if len(chunks[-1]) + len(trunc_msg) > MAX_CONTENT_CHARS:
                available = max(0, MAX_CONTENT_CHARS - len(trunc_msg) - 3)
                chunks[-1] = chunks[-1][:available] + "..." + trunc_msg
            else:
                chunks[-1] = chunks[-1] + trunc_msg

        if any(len(c) + 10 > MAX_FIELD_VALUE for c in chunks):
            import io
            file_content = "\n".join(tree_lines)
            fp = io.BytesIO(file_content.encode("utf-8"))
            fp.seek(0)
            filename = f"{owner}-{name}-tree-{branch}{('-' + subpath.replace('/', '_')) if subpath else ''}.txt"
            await interaction.followup.send(
                content=f"📁 Repository tree is large — sending as a file: `{filename}`",
                file=discord.File(fp, filename=filename)
            )
            return

        embeds_to_send = []
        repo_url = f"https://github.com/{owner}/{name}"
        author_url = f"https://github.com/{owner}/{name}/tree/{branch}/{subpath}" if subpath else f"https://github.com/{owner}/{name}/tree/{branch}"

        total_parts = len(chunks)

        for idx, chunk in enumerate(chunks, start=1):
            embed = discord.Embed(
                title=f"File Tree for {owner}/{name}",
                description=f"**Branch:** `{branch}` **Path:** `/{subpath if subpath else ''}`",
                color=EMBED_COLOR,
                url=repo_url,
            )

            embed.set_author(
                name=f"{owner}/{name} (branch: {branch})",
                url=author_url,
            )

            embed.add_field(
                name=f"Tree Structure (Max Depth: {max_depth}) - Part {idx}/{total_parts}",
                value=f"```fix\n{chunk}\n```",
                inline=False
            )

            embed.set_footer(
                text=f"Requested by {interaction.user.display_name} | {len(all_paths)} total files/dirs",
                icon_url=interaction.user.display_avatar.url
            )
            embed.timestamp = discord.utils.utcnow()
            embeds_to_send.append(embed)

        if not embeds_to_send:
            await interaction.followup.send(f"❌ No content to display for `{owner}/{name}`.")
            return

        import io, traceback

        # Send first embed
        try:
            await interaction.followup.send(embeds=[embeds_to_send[0]])
        except Exception as e:
            print("Error sending first embed:", e)
            traceback.print_exc()
            file_content = "\n".join(tree_lines)
            fp = io.BytesIO(file_content.encode("utf-8"))
            fp.seek(0)
            filename = f"{owner}-{name}-tree-{branch}{('-' + subpath.replace('/', '_')) if subpath else ''}.txt"
            await interaction.followup.send(
                content="📁 Unable to send embeds reliably; sending full tree as a file.",
                file=discord.File(fp, filename=filename)
            )
            return

        for i, embed in enumerate(embeds_to_send[1:], start=1):
            try:
                await interaction.followup.send(embeds=[embed])
            except Exception as send_err:
                # Log the error
                print(f"Error sending embed part {i+1}:", send_err)
                traceback.print_exc()

                remaining_chunks = []
                try:
                    remaining_chunks = chunks[i:]  # from failed part to end
                except Exception:
                    remaining_chunks = ["(Could not reconstruct chunk text)"]

                combined_text = "\n\n--- Part Break ---\n\n".join(remaining_chunks)
                # Prepend a header with repo info
                header = f"Repository tree for {owner}/{name} (branch: {branch})\nPath: /{subpath if subpath else ''}\n\n"
                file_content = header + combined_text

                fp = io.BytesIO(file_content.encode("utf-8"))
                fp.seek(0)
                filename = f"{owner}-{name}-tree-{branch}-remaining.txt"
                await interaction.followup.send(
                    content="📁 Part of the output couldn't be sent as embeds — sending remaining parts as a single .txt file.",
                    file=discord.File(fp, filename=filename)
                )
                return  # done after fallback

        return

    except Exception:
        import traceback
        print(f"--- GITHUB TREE COMMAND ERROR ---")
        print(f"Repo: {repo}, User: {interaction.user.display_name}")
        traceback.print_exc()
        print(f"---------------------------------")
        await interaction.followup.send("❌ An unexpected internal error occurred while fetching the repository tree. Check bot logs for details.")



@bot.tree.command(name="github_search", description="Search for GitHub repositories by criteria")
@app_commands.describe(query="Search query, e.g., language:python stars:>1000")
async def github_search(interaction: discord.Interaction, query: str):
    """Search GitHub repositories with enhanced error handling"""
    try:
        await interaction.response.defer()

        # Construct the search URL
        search_url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page=5"

        data = await github_request(search_url)

        if data == "rate_limited":
            await interaction.followup.send("❌ GitHub API rate limit exceeded. Please try again later.")
            return
        elif not data or not data.get("items"):
            await interaction.followup.send(f"❌ No repositories found for query: **{query}**")
            return
        elif data.get("incomplete_results", False):
            logger.warning("GitHub search returned incomplete results")

        # Create embed for results
        embed = discord.Embed(
            title=f"🔍 GitHub Repository Search Results for '{query}'",
            description=f"Showing top {len(data['items'])} results:",
            color=0x238636
        )

        for i, repo in enumerate(data["items"], start=1):
            name = repo.get("name", "N/A")
            owner = repo.get("owner", {}).get("login", "N/A")
            full_name = f"{owner}/{name}"
            description = repo.get("description", "No description available.")[:200] + "..." if len(repo.get("description", "")) > 200 else repo.get("description", "No description available.")
            stars = format_number(repo.get("stargazers_count", 0))
            language = repo.get("language", "N/A")
            repo_url = repo.get("html_url", "")

            # Add each result as a field
            embed.add_field(
                name=f"{i}. {full_name}",
                value=f"⭐ {stars} | 🗣️ {language}\n{description}\n🔗 [View Repo]({repo_url})",
                inline=False
            )

        embed.set_footer(text=f"Total results: {data.get('total_count', 0)} | Powered by GitHub API")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        logger.error(f"github_search command error: {e}")
        try:
            await interaction.followup.send("❌ An error occurred while searching repositories.")
        except:
            pass

@bot.tree.command(name="sync_commands", description="Manually sync commands to this server (Admin only)")
@app_commands.default_permissions(administrator=True)
async def sync_commands(interaction: discord.Interaction):
    """Manual command sync for administrators"""
    try:
        await interaction.response.defer(ephemeral=True)
        if GUILD_ID and interaction.guild and interaction.guild.id == GUILD_ID:
            synced = await bot.tree.sync(guild=interaction.guild)
            await interaction.followup.send(f"✅ Successfully synced {len(synced)} commands to your server!", ephemeral=True)
        else:
            await interaction.followup.send("❌ This command can only be used in the target server!", ephemeral=True)
    except Exception as e:
        logger.error(f"sync_commands error: {e}")
        try:
            await interaction.followup.send(f"❌ Failed to sync commands: {e}", ephemeral=True)
        except:
            pass

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Enhanced error handler for slash commands"""
    logger.error(f"Command error: {error}")
    
    try:
        if isinstance(error, app_commands.CommandOnCooldown):
            message = f"⏰ Command on cooldown. Try again in {error.retry_after:.1f} seconds."
        elif isinstance(error, app_commands.MissingPermissions):
            message = "❌ You don't have permission to use this command."
        else:
            message = "❌ An error occurred while processing your command."
        
        if not interaction.response.is_done():
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.followup.send(message, ephemeral=True)
            
    except Exception as e:
        logger.error(f"Error in error handler: {e}")

def run_flask():
    """Run Flask server with error handling"""
    try:
        logger.info(f"🌐 Starting Flask server on port {PORT}")
        app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Flask server error: {e}")

async def start_bot():
    """Start bot with Render-optimized settings"""
    try:
        logger.info("🔄 Starting Discord bot...")
        
        # Add connection retry logic specifically for Render
        if IS_RENDER:
            logger.info("🚀 Using Render-optimized connection settings...")
            
        await bot.start(TOKEN)
        
    except discord.LoginFailure:
        logger.error("❌ Invalid Discord token!")
        return False
    except discord.HTTPException as e:
        error_str = str(e)
        if "429" in error_str or "rate limit" in error_str.lower():
            logger.error("❌ Discord rate limited - this is a known Render issue")
            logger.info("💡 Try switching to a different hosting provider or wait 24 hours")
            return False
        else:
            logger.error(f"❌ Discord HTTP error: {e}")
            return False
    except Exception as e:
        logger.error(f"❌ Unexpected bot startup error: {e}")
        return False
    
    return True

# Main execution
if __name__ == "__main__":
    if not TOKEN:
        logger.error("❌ DISCORD_TOKEN not found in environment variables!")
        logger.error("Please add DISCORD_TOKEN to your Render environment variables")
        exit(1)
    
    if not GUILD_ID:
        logger.warning("⚠️ GUILD_ID not found! Add it to environment variables")
    else:
        logger.info(f"🎯 Bot configured for guild ID: {GUILD_ID}")
    
    logger.info("🚀 Starting GitHub Discord Bot for Render deployment...")
    
    # Start Flask server
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info(f"🌐 Flask health server started on port {PORT}")
    
    # Small delay for Flask to start
    time.sleep(3)
    
    # Start Discord bot
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
    
    # Keep Flask alive for health checks
    logger.info("🌐 Keeping Flask server alive for health checks...")
    try:
        while True:
            time.sleep(30)  # Check every 30 seconds
            if IS_RENDER:
                logger.info("💓 Heartbeat - Flask server still running")
    except KeyboardInterrupt:
        logger.info("🛑 Application stopped by user")