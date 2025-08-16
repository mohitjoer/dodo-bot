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

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # Optional for higher rate limits
GUILD_ID = int(os.getenv("GUILD_ID")) if os.getenv("GUILD_ID") else None  # Your server ID
PORT = int(os.getenv("PORT", 5000))  # Render provides PORT env variable

# Flask app for health checks
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 GitHub Discord Bot is running!"

@app.route('/health')
def health():
    """Health check endpoint for keeping the bot alive"""
    bot_status = "online" if hasattr(bot, 'is_ready') and bot.is_ready() else "offline"
    guild_count = len(bot.guilds) if hasattr(bot, 'guilds') and bot.is_ready() else 0
    target_guild = "connected" if hasattr(bot, 'get_guild') and GUILD_ID and bot.get_guild(GUILD_ID) else "not found"
    
    return jsonify({
        "status": "healthy",
        "bot_status": bot_status,
        "timestamp": datetime.utcnow().isoformat(),
        "total_guilds": guild_count,
        "target_guild": target_guild,
        "guild_id": GUILD_ID,
        "uptime": "running"
    })

class GitHubBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # Enable message content intent
        super().__init__(command_prefix='!', intents=intents)
        
        self.github_headers = {
            'User-Agent': 'GitHub-Discord-Bot/1.0',
            'Accept': 'application/vnd.github.v3+json'
        }
        if GITHUB_TOKEN:
            self.github_headers['Authorization'] = f'token {GITHUB_TOKEN}'
        
        # Initialize session as None - will be created in setup_hook
        self.session = None
        self.target_guild_id = GUILD_ID
        
        # Rate limiting
        self.last_api_call = 0
        self.api_call_delay = 1.0  # 1 second between API calls
    
    async def setup_hook(self):
        """Set up the bot when it starts"""
        logger.info("🔧 Setting up bot...")
        
        # Create aiohttp session with proper settings
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        connector = aiohttp.TCPConnector(
            limit=10,  # Total connection limit
            limit_per_host=5,  # Per-host connection limit
            ttl_dns_cache=300,  # DNS cache TTL
            use_dns_cache=True,
        )
        
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={'User-Agent': 'GitHub-Discord-Bot/1.0'}
        )
        
        # Only sync commands to your specific guild for faster updates
        if self.target_guild_id:
            guild = discord.Object(id=self.target_guild_id)
            try:
                synced = await self.tree.sync(guild=guild)
                logger.info(f"✅ Synced {len(synced)} commands to your guild (ID: {self.target_guild_id})")
            except Exception as e:
                logger.error(f"❌ Failed to sync commands to your guild: {e}")
        else:
            logger.warning("⚠️ GUILD_ID not set, commands will be synced on first use")

    async def on_ready(self):
        logger.info(f"🚀 Bot is ready! Logged in as {self.user}")
        logger.info(f"📊 Connected to {len(self.guilds)} servers")
        
        # Check if bot is in your target guild
        if self.target_guild_id:
            target_guild = self.get_guild(self.target_guild_id)
            if target_guild:
                logger.info(f"✅ Successfully connected to your server: {target_guild.name}")
                logger.info("💡 Commands are now available in your server!")
            else:
                logger.warning(f"⚠️ Bot is not in the target guild (ID: {self.target_guild_id})")
                logger.warning("Please make sure the bot is invited to your server")
        
        # Set bot status
        try:
            await self.change_presence(
                status=discord.Status.online,
                activity=discord.Activity(
                    type=discord.ActivityType.watching, 
                    name="GitHub repositories"
                )
            )
        except Exception as e:
            logger.warning(f"Could not set presence: {e}")

    async def on_guild_join(self, guild):
        """Handle when bot joins a guild"""
        if self.target_guild_id and guild.id == self.target_guild_id:
            logger.info(f"✅ Bot joined your target server: {guild.name}!")
            # Sync commands to this guild immediately
            try:
                synced = await self.tree.sync(guild=guild)
                logger.info(f"✅ Synced {len(synced)} commands to {guild.name}")
            except Exception as e:
                logger.error(f"❌ Failed to sync commands to {guild.name}: {e}")
        else:
            logger.info(f"ℹ️ Bot joined server: {guild.name}")
    
    async def close(self):
        """Clean up when bot shuts down"""
        if self.session and not self.session.closed:
            await self.session.close()
        await super().close()

# Initialize bot
bot = GitHubBot()

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
    """Make async GitHub API request with proper rate limiting"""
    if not bot.session or bot.session.closed:
        logger.error("Session not available for GitHub request")
        return None
    
    try:
        # Rate limiting - ensure minimum delay between API calls
        current_time = time.time()
        time_since_last_call = current_time - bot.last_api_call
        if time_since_last_call < bot.api_call_delay:
            await asyncio.sleep(bot.api_call_delay - time_since_last_call)
        
        bot.last_api_call = time.time()
        
        async with bot.session.get(url, headers=bot.github_headers) as response:
            # Check for rate limiting
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
    """Simple ping command to test bot functionality"""
    try:
        # Respond immediately to avoid timeout
        await interaction.response.defer()
        
        latency = round(bot.latency * 1000)
        guild_info = f" in {interaction.guild.name}" if interaction.guild else ""
        
        await interaction.followup.send(
            f"🏓 Pong! Latency: {latency}ms\nGitHub bot is online and ready{guild_info}!"
        )
    except Exception as e:
        logger.error(f"Ping command error: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Error occurred", ephemeral=True)

@bot.tree.command(name="github_user", description="Get GitHub user profile information")
@app_commands.describe(username="GitHub username or profile URL")
async def github_user(interaction: discord.Interaction, username: str):
    """Fetch and display GitHub user profile"""
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

@bot.tree.command(name="github_repo", description="Get GitHub repository information")
@app_commands.describe(repo="Repository URL or owner/repo format")
async def github_repo(interaction: discord.Interaction, repo: str):
    """Fetch and display GitHub repository information"""
    try:
        await interaction.response.defer()
        
        repo_info = extract_github_repo(repo)
        if not repo_info:
            await interaction.followup.send("❌ Please provide a valid repository URL or use format: `owner/repo`")
            return
        
        owner, repo_name = repo_info
        data = await github_request(f"https://api.github.com/repos/{owner}/{repo_name}")
        
        if data == "rate_limited":
            await interaction.followup.send("❌ GitHub API rate limit exceeded. Please try again later.")
            return
        elif data == "not_found":
            await interaction.followup.send(f"❌ Repository **{owner}/{repo_name}** not found")
            return
        elif not data:
            await interaction.followup.send(f"❌ Failed to fetch repository data")
            return
        
        embed = discord.Embed(
            title=f"📦 {data['name']}",
            url=data['html_url'],
            description=data.get('description', 'No description available'),
            color=0x1f6feb
        )
        
        embed.set_thumbnail(url=data['owner']['avatar_url'])
        embed.add_field(name="👤 Owner", value=f"[{owner}]({data['owner']['html_url']})", inline=True)
        embed.add_field(name="⭐ Stars", value=format_number(data['stargazers_count']), inline=True)
        embed.add_field(name="🍴 Forks", value=format_number(data['forks_count']), inline=True)
        embed.add_field(name="👀 Watchers", value=format_number(data['watchers_count']), inline=True)
        embed.add_field(name="🐛 Open Issues", value=format_number(data['open_issues_count']), inline=True)
        embed.add_field(name="💻 Language", value=data.get('language', 'N/A'), inline=True)
        embed.add_field(name="📅 Created", value=format_date(data['created_at']), inline=True)
        embed.add_field(name="🔄 Updated", value=format_date(data['updated_at']), inline=True)
        
        license_info = data.get('license')
        embed.add_field(name="📄 License", value=license_info['name'] if license_info else 'N/A', inline=True)
        
        topics = data.get('topics', [])
        if topics:
            embed.add_field(name="🏷️ Topics", value=', '.join(topics[:5]), inline=False)
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        logger.error(f"github_repo command error: {e}")
        try:
            await interaction.followup.send("❌ An error occurred while fetching repository data.")
        except:
            pass

# Add similar error handling to other commands...
# (I'll include the essential ones for space, but apply same pattern to all)

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
    """Global error handler for slash commands"""
    logger.error(f"Command error: {error}")
    
    try:
        if isinstance(error, app_commands.CommandOnCooldown):
            message = f"⏰ Command on cooldown. Try again in {error.retry_after:.1f} seconds."
        else:
            message = "❌ An error occurred while processing your command."
        
        if not interaction.response.is_done():
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.followup.send(message, ephemeral=True)
            
    except Exception as e:
        logger.error(f"Error in error handler: {e}")

def run_flask():
    """Run Flask server in a separate thread"""
    try:
        app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Flask server error: {e}")

async def start_bot():
    """Start bot with simplified error handling"""
    try:
        logger.info("🔄 Starting Discord bot...")
        await bot.start(TOKEN)
    except discord.LoginFailure:
        logger.error("❌ Invalid Discord token!")
        return False
    except discord.HTTPException as e:
        if "429" in str(e) or "rate limit" in str(e).lower():
            logger.error("❌ Discord rate limited the bot. This usually resolves automatically.")
            logger.info("🌐 Keeping Flask server alive for health checks...")
            return False
        else:
            logger.error(f"❌ Discord HTTP error: {e}")
            return False
    except Exception as e:
        logger.error(f"❌ Unexpected error starting bot: {e}")
        return False
    
    return True

# Main execution
if __name__ == "__main__":
    if not TOKEN:
        logger.error("❌ DISCORD_TOKEN not found in environment variables!")
        logger.error("Please add DISCORD_TOKEN to your .env file or Render environment variables")
        exit(1)
    
    if not GUILD_ID:
        logger.warning("⚠️ GUILD_ID not found! Bot will sync commands globally (slower)")
        logger.warning("Add GUILD_ID environment variable with your server ID for faster command sync")
    else:
        logger.info(f"🎯 Bot configured for guild ID: {GUILD_ID}")
    
    logger.info("🚀 Starting GitHub Discord Bot...")
    
    # Start Flask server in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info(f"🌐 Flask health server started on port {PORT}")
    
    # Small delay to let Flask start
    time.sleep(2)
    
    # Start Discord bot
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Bot startup error: {e}")
    
    # Keep Flask server running
    logger.info("🌐 Flask server continues running for health checks...")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("🛑 Application stopped by user")