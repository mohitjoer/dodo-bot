# 🦤 Dodo Bot - GitHub Discord Bot

A Discord bot that integrates with GitHub to provide user profile information and repository data directly in your Discord server. Optimized for deployment on Render with built-in health monitoring and robust error handling.

## ✨ Features

- 🔍 **GitHub User Profiles**: Fetch and display comprehensive GitHub user information
- 🏓 **Health Monitoring**: Built-in health check endpoints for deployment monitoring
- 🚀 **Render Optimized**: Specifically configured for reliable Render.com deployment
- ⚡ **Slash Commands**: Modern Discord slash command interface
- 🛡️ **Rate Limit Handling**: Smart GitHub API rate limit management
- 📊 **Connection Monitoring**: Automatic reconnection and error recovery

## 🤖 Available Commands

| Command | Description | Usage |
|---------|-------------|-------|
| `/ping` | Test bot connectivity and check latency | `/ping` |
| `/github_user` | Get detailed GitHub user profile | `/github_user username:octocat` |
| `/sync_commands` | Manually sync commands (Admin only) | `/sync_commands` |

## 🚀 Quick Start

### Prerequisites

- Python 3.10 or higher
- Discord Bot Token
- GitHub Personal Access Token (optional, but recommended for higher rate limits)
- Discord Server (Guild) ID

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/mohitjoer/dodo-bot.git
   cd dodo-bot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   
   Create a `.env` file in the project root:
   ```env
   DISCORD_TOKEN=your_discord_bot_token
   GITHUB_TOKEN=your_github_token
   GUILD_ID=your_discord_server_id
   PORT=5000
   ```

4. **Run the bot**
   ```bash
   python bot.py
   ```

## 🔧 Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_TOKEN` | ✅ Yes | Your Discord bot token from [Discord Developer Portal](https://discord.com/developers/applications) |
| `GITHUB_TOKEN` | ❌ No | GitHub personal access token (increases API rate limits from 60 to 5000 requests/hour) |
| `GUILD_ID` | ✅ Yes | Your Discord server ID (enables slash commands) |
| `PORT` | ❌ No | Port for Flask health server (default: 5000) |
| `RENDER` | ❌ No | Automatically set by Render.com deployment |

### Getting Your Tokens

#### Discord Bot Token:
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a New Application
3. Go to the "Bot" section
4. Click "Reset Token" to get your bot token
5. Enable "Message Content Intent" under Privileged Gateway Intents

#### GitHub Token:
1. Go to [GitHub Settings > Developer Settings > Personal Access Tokens](https://github.com/settings/tokens)
2. Generate a new token (classic)
3. No specific scopes needed for public data access

#### Guild ID:
1. Enable Developer Mode in Discord (Settings > Advanced > Developer Mode)
2. Right-click your server and select "Copy Server ID"

## 🌐 Deployment on Render

### Option 1: Deploy via Render Dashboard

1. **Create a new Web Service** on [Render](https://render.com)

2. **Connect your repository**: `mohitjoer/dodo-bot`

3. **Configure the service**:
   - **Name**: `dodo-bot` (or your preferred name)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
   - **Plan**: Free tier works fine

4. **Add Environment Variables**:
   - `DISCORD_TOKEN`: Your Discord bot token
   - `GUILD_ID`: Your Discord server ID
   - `GITHUB_TOKEN`: Your GitHub token (optional)

5. **Deploy** and wait for the service to start

### Option 2: Deploy via Dockerfile

The included Dockerfile allows for containerized deployment:

```bash
docker build -t dodo-bot .
docker run -e DISCORD_TOKEN=your_token -e GUILD_ID=your_guild_id dodo-bot
```

### Health Checks

The bot includes two health check endpoints:

- `GET /` - Simple status check
- `GET /health` - Detailed health information with bot status, guild count, and connection info

## 📦 Dependencies

- **discord.py** (2.5.2) - Discord API wrapper
- **aiohttp** (3.12.15) - Async HTTP client for GitHub API
- **Flask** (2.3.3) - Web server for health checks
- **python-dotenv** (1.0.0) - Environment variable management
- **requests** (2.31.0) - HTTP library

## 🏗️ Project Structure

```
dodo-bot/
├── bot.py              # Main bot application
├── requirements.txt    # Python dependencies
├── runtime.txt         # Python version specification
├── Dockerfile          # Docker configuration
├── keep-alive.yml      # GitHub Actions workflow (optional)
├── .gitignore         # Git ignore rules
└── README.md          # This file
```

## 🛠️ Development

### Adding New Commands

To add a new slash command, use the `@bot.tree.command()` decorator:

```python
@bot.tree.command(name="your_command", description="Command description")
async def your_command(interaction: discord.Interaction):
    await interaction.response.send_message("Hello!")
```

### GitHub API Integration

The bot includes a helper function for GitHub API requests:

```python
data = await github_request("https://api.github.com/users/username")
```

## 🐛 Troubleshooting

### Bot not responding to commands?
- Ensure `GUILD_ID` is correctly set
- Run `/sync_commands` in your Discord server (admin only)
- Check bot has proper permissions in Discord server

### GitHub API rate limit exceeded?
- Add a `GITHUB_TOKEN` to your environment variables
- This increases rate limit from 60 to 5000 requests per hour

### Bot keeps disconnecting on Render?
- This is normal for free tier services
- The bot includes automatic reconnection logic
- Check the health endpoint for current status

### Commands not syncing?
- Wait a few minutes after deployment
- Use the `/sync_commands` command (admin only)
- Verify the bot has `applications.commands` scope

## 📝 License

This project is open source and available for personal and educational use.

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the issues page.

## 👤 Author

**mohitjoer**
- GitHub: [@mohitjoer](https://github.com/mohitjoer)

## 🌟 Show your support

Give a ⭐️ if this project helped you!

---

**Note**: This bot is optimized for Render.com deployment but works on any platform that supports Python applications. The keep-alive workflow helps prevent the bot from sleeping on free hosting tiers.