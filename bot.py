import os
import discord
import requests
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
    target_guild = "connected" if hasattr(bot, 'get_guild') and bot.get_guild(GUILD_ID) else "not found"
    
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
            'User-Agent': 'GitHub-Discord-Bot/1.0'
        }
        if GITHUB_TOKEN:
            self.github_headers['Authorization'] = f'token {GITHUB_TOKEN}'
        
        # Create aiohttp session that we can properly close
        self.session = None
        self.target_guild_id = GUILD_ID
    
    async def setup_hook(self):
        """Set up the bot when it starts"""
        logger.info("🔧 Setting up bot...")
        
        # Create aiohttp session
        import aiohttp
        self.session = aiohttp.ClientSession()
        
        # Only sync commands to your specific guild
        if self.target_guild_id:
            guild = discord.Object(id=self.target_guild_id)
            try:
                synced = await self.tree.sync(guild=guild)
                logger.info(f"✅ Synced {len(synced)} commands to your guild (ID: {self.target_guild_id})")
            except Exception as e:
                logger.error(f"❌ Failed to sync commands to your guild: {e}")
        else:
            logger.warning("⚠️ GUILD_ID not set, syncing globally (slower)")
            try:
                synced = await self.tree.sync()
                logger.info(f"✅ Synced {len(synced)} commands globally")
            except Exception as e:
                logger.error(f"❌ Failed to sync global commands: {e}")

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
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching, 
                name="GitHub repositories"
            )
        )

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
            logger.info(f"ℹ️ Bot joined server: {guild.name} (not target server)")
    
    async def close(self):
        """Clean up when bot shuts down"""
        if self.session:
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
    """Make async GitHub API request using bot's session"""
    try:
        if not bot.session:
            import aiohttp
            bot.session = aiohttp.ClientSession()
        
        async with bot.session.get(url, headers=bot.github_headers, timeout=10) as response:
            if response.status == 200:
                return await response.json()
            elif response.status == 404:
                return "not_found"
            else:
                logger.error(f"GitHub API returned status {response.status} for {url}")
                return None
    except Exception as e:
        logger.error(f"GitHub API Error: {e}")
        return None

@bot.tree.command(name="ping", description="Test if the bot is working")
async def ping(interaction: discord.Interaction):
    """Simple ping command to test bot functionality"""
    latency = round(bot.latency * 1000)
    guild_info = f" in {interaction.guild.name}" if interaction.guild else ""
    await interaction.response.send_message(f"🏓 Pong! Latency: {latency}ms\nGitHub bot is online and ready{guild_info}!")

@bot.tree.command(name="github_user", description="Get GitHub user profile information")
@app_commands.describe(username="GitHub username or profile URL")
async def github_user(interaction: discord.Interaction, username: str):
    """Fetch and display GitHub user profile"""
    await interaction.response.defer()
    
    username = extract_github_username(username)
    data = await github_request(f"https://api.github.com/users/{username}")
    
    if data == "not_found":
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

@bot.tree.command(name="github_repo", description="Get GitHub repository information")
@app_commands.describe(repo="Repository URL or owner/repo format")
async def github_repo(interaction: discord.Interaction, repo: str):
    """Fetch and display GitHub repository information"""
    await interaction.response.defer()
    
    repo_info = extract_github_repo(repo)
    if not repo_info:
        await interaction.followup.send("❌ Please provide a valid repository URL or use format: `owner/repo`")
        return
    
    owner, repo_name = repo_info
    data = await github_request(f"https://api.github.com/repos/{owner}/{repo_name}")
    
    if data == "not_found":
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

@bot.tree.command(name="github_repos", description="List user's repositories")
@app_commands.describe(username="GitHub username or profile URL")
async def github_repos(interaction: discord.Interaction, username: str):
    """List user's public repositories"""
    await interaction.response.defer()
    
    username = extract_github_username(username)
    data = await github_request(f"https://api.github.com/users/{username}/repos?sort=updated&per_page=10")
    
    if data == "not_found":
        await interaction.followup.send(f"❌ User **{username}** not found")
        return
    elif not data:
        await interaction.followup.send(f"❌ Failed to fetch repositories for **{username}**")
        return
    elif len(data) == 0:
        await interaction.followup.send(f"ℹ️ **{username}** has no public repositories")
        return
    
    embed = discord.Embed(
        title=f"📦 {username}'s Repositories",
        url=f"https://github.com/{username}?tab=repositories",
        color=0xf85149
    )
    
    repo_list = []
    for repo in data:
        stars = f"⭐{format_number(repo['stargazers_count'])}" if repo['stargazers_count'] > 0 else ""
        language = f"• {repo['language']}" if repo['language'] else ""
        repo_list.append(f"[**{repo['name']}**]({repo['html_url']}) {stars} {language}")
    
    embed.description = "\n".join(repo_list)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="github_commits", description="Show recent commits for a repository")
@app_commands.describe(repo="Repository URL or owner/repo format")
async def github_commits(interaction: discord.Interaction, repo: str):
    """Show recent commits for a repository"""
    await interaction.response.defer()
    
    repo_info = extract_github_repo(repo)
    if not repo_info:
        await interaction.followup.send("❌ Please provide a valid repository URL or use format: `owner/repo`")
        return
    
    owner, repo_name = repo_info
    data = await github_request(f"https://api.github.com/repos/{owner}/{repo_name}/commits?per_page=5")
    
    if data == "not_found":
        await interaction.followup.send(f"❌ Repository **{owner}/{repo_name}** not found")
        return
    elif not data:
        await interaction.followup.send(f"❌ Failed to fetch commits")
        return
    
    embed = discord.Embed(
        title=f"📝 Recent Commits - {owner}/{repo_name}",
        url=f"https://github.com/{owner}/{repo_name}/commits",
        color=0x8957e5
    )
    
    for commit in data:
        commit_data = commit['commit']
        message = commit_data['message']
        if len(message) > 60:
            message = message[:57] + "..."
        
        author = commit_data['author']['name']
        date = format_date(commit_data['author']['date'])
        sha = commit['sha'][:7]
        
        embed.add_field(
            name=f"#{sha} {message}",
            value=f"👤 **{author}** on {date}\n[View Commit]({commit['html_url']})",
            inline=False
        )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="github_issues", description="Show open issues for a repository")
@app_commands.describe(repo="Repository URL or owner/repo format")
async def github_issues(interaction: discord.Interaction, repo: str):
    """Show open issues for a repository"""
    await interaction.response.defer()
    
    repo_info = extract_github_repo(repo)
    if not repo_info:
        await interaction.followup.send("❌ Please provide a valid repository URL or use format: `owner/repo`")
        return
    
    owner, repo_name = repo_info
    data = await github_request(f"https://api.github.com/repos/{owner}/{repo_name}/issues?state=open&per_page=5")
    
    if data == "not_found":
        await interaction.followup.send(f"❌ Repository **{owner}/{repo_name}** not found")
        return
    elif not data:
        await interaction.followup.send(f"❌ Failed to fetch issues")
        return
    elif len(data) == 0:
        await interaction.followup.send(f"✅ No open issues found for **{owner}/{repo_name}**")
        return
    
    embed = discord.Embed(
        title=f"🐛 Open Issues - {owner}/{repo_name}",
        url=f"https://github.com/{owner}/{repo_name}/issues",
        color=0xd1242f
    )
    
    for issue in data:
        title = issue['title']
        if len(title) > 50:
            title = title[:47] + "..."
        
        created = format_date(issue['created_at'])
        labels = [label['name'] for label in issue['labels'][:3]]
        label_text = f"🏷️ {', '.join(labels)}" if labels else "No labels"
        
        embed.add_field(
            name=f"#{issue['number']} {title}",
            value=f"📅 {created} | {label_text}\n[View Issue]({issue['html_url']})",
            inline=False
        )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="github_search", description="Search GitHub repositories")
@app_commands.describe(
    query="Search query",
    language="Programming language (optional)",
    sort="Sort by: stars, forks, updated"
)
async def github_search(interaction: discord.Interaction, query: str, language: str = None, sort: str = "stars"):
    """Search GitHub repositories"""
    await interaction.response.defer()
    
    search_query = f"q={query.replace(' ', '+')}"
    if language:
        search_query += f"+language:{language}"
    
    url = f"https://api.github.com/search/repositories?{search_query}&sort={sort}&per_page=5"
    data = await github_request(url)
    
    if not data or not data.get('items'):
        await interaction.followup.send(f"❌ No repositories found for: **{query}**")
        return
    
    embed = discord.Embed(
        title=f"🔍 Search: {query}",
        description=f"Found {format_number(data['total_count'])} repositories (showing top 5)",
        color=0x0969da
    )
    
    for repo in data['items']:
        description = repo.get('description', 'No description')
        if len(description) > 80:
            description = description[:77] + "..."
        
        embed.add_field(
            name=f"⭐{format_number(repo['stargazers_count'])} {repo['name']}",
            value=f"{description}\n👤 [{repo['owner']['login']}]({repo['owner']['html_url']}) | [View Repo]({repo['html_url']})",
            inline=False
        )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="github_trending", description="Show trending repositories")
@app_commands.describe(
    language="Programming language (optional)",
    period="Time period: daily, weekly, monthly"
)
async def github_trending(interaction: discord.Interaction, language: str = None, period: str = "daily"):
    """Show trending repositories"""
    await interaction.response.defer()
    
    if period == "weekly":
        date = (datetime.now() - timedelta(weeks=1)).strftime('%Y-%m-%d')
    elif period == "monthly":
        date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    else: 
        date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    search_query = f"q=created:>{date}"
    if language:
        search_query += f"+language:{language}"
    
    url = f"https://api.github.com/search/repositories?{search_query}&sort=stars&order=desc&per_page=5"
    data = await github_request(url)
    
    if not data or not data.get('items'):
        await interaction.followup.send(f"❌ No trending repositories found")
        return
    
    embed = discord.Embed(
        title=f"🔥 Trending ({period.capitalize()})",
        description=f"Language: {language or 'All'}" if language else "All languages",
        color=0xff4500
    )
    
    for repo in data['items']:
        description = repo.get('description', 'No description')
        if len(description) > 70:
            description = description[:67] + "..."
        
        embed.add_field(
            name=f"⭐{format_number(repo['stargazers_count'])} {repo['name']}",
            value=f"{description}\n👤 [{repo['owner']['login']}]({repo['owner']['html_url']}) | [View Repo]({repo['html_url']})",
            inline=False
        )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="sync_commands", description="Manually sync commands to this server (Admin only)")
@app_commands.default_permissions(administrator=True)
async def sync_commands(interaction: discord.Interaction):
    """Manual command sync for administrators"""
    await interaction.response.defer(ephemeral=True)
    
    try:
        if GUILD_ID and interaction.guild and interaction.guild.id == GUILD_ID:
            synced = await bot.tree.sync(guild=interaction.guild)
            await interaction.followup.send(f"✅ Successfully synced {len(synced)} commands to your server!", ephemeral=True)
        else:
            await interaction.followup.send("❌ This command can only be used in the target server!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to sync commands: {e}", ephemeral=True)

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    logger.error(f"Command error: {error}")
    try:
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"⏰ Command on cooldown. Try again in {error.retry_after:.1f} seconds.",
                ephemeral=True
            )
        else:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred while processing your command.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ An error occurred while processing your command.",
                    ephemeral=True
                )
    except Exception as e:
        logger.error(f"Error handling command error: {e}")

def run_flask():
    """Run Flask server in a separate thread"""
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

async def start_bot_with_retry():
    """Start bot with exponential backoff retry logic"""
    max_retries = 3  # Reduced retries
    base_delay = 300  # Start with 5 minutes for rate limits
    
    for attempt in range(max_retries):
        try:
            logger.info(f"🔄 Starting bot (attempt {attempt + 1}/{max_retries})")
            await bot.start(TOKEN)
            break
        except discord.errors.HTTPException as e:
            error_msg = str(e)
            logger.error(f"Discord HTTP Error: {error_msg}")
            
            if "429" in error_msg or "Too Many Requests" in error_msg or "rate limit" in error_msg.lower():
                if attempt < max_retries - 1:
                    # For rate limits, wait longer
                    delay = base_delay + (attempt * 300)  # 5, 10, 15 minutes
                    logger.warning(f"⏰ Discord rate limited! Waiting {delay//60} minutes before retry {attempt + 2}...")
                    await asyncio.sleep(delay)
                else:
                    logger.error("❌ Max retries reached. Discord rate limiting persists.")
                    # Don't exit completely, keep Flask running
                    logger.info("🌐 Keeping Flask server alive for health checks...")
                    return
            else:
                logger.error(f"❌ Other Discord error: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(60)
                else:
                    raise
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(60)
            else:
                logger.error("❌ Bot failed to start, but keeping Flask alive")
                return

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
    
    logger.info("🚀 Starting GitHub Discord Bot with Keep-Alive...")
    
    # Start Flask server in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info(f"🌐 Flask health server started on port {PORT}")
    
    # Add a small delay before starting Discord bot
    time.sleep(5)
    
    # Start Discord bot with retry logic
    try:
        asyncio.run(start_bot_with_retry())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Bot startup error: {e}")
    
    # Keep Flask server running even if Discord bot fails
    logger.info("🌐 Flask server continues running for health checks...")
    try:
        while True:
            time.sleep(60)  # Keep main thread alive
    except KeyboardInterrupt:
        logger.info("🛑 Application stopped by user")