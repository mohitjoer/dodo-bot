import discord
from discord import app_commands
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)


class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Test if the bot is working")
    async def ping(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            latency = round(self.bot.latency * 1000)
            guild_info = f" in {interaction.guild.name}" if interaction.guild else ""
            env_info = " (Render)" if self.bot.IS_RENDER else " (Local)"

            embed = discord.Embed(
                title="🏓 Pong!",
                description=f"Bot is online and responding{guild_info}{env_info}",
                color=0x00ff00,
            )
            embed.add_field(name="Latency", value=f"{latency}ms", inline=True)
            embed.add_field(name="Guilds", value=len(self.bot.guilds), inline=True)
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

    @app_commands.command(name="help", description="Show help and usage instructions for the bot")
    async def help(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()

            embed = discord.Embed(
                title="🤖 Dodo Bot - Command Help",
                description="Complete guide to all available commands\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                color=0x5865F2,
            )

            # Admin Commands
            embed.add_field(
                name="",
                value=(
                    "**⚙️  ADMIN COMMANDS**\n"
                    "> **`/ping`**\n"
                    "> Test bot status and check latency\n"
                    "> \n"
                    "> **`/sync_commands`**\n"
                    "> Manually sync commands globally (Admin only)\n"
                    "> \n"
                    "> **`/help`**\n"
                    "> Show this help message\n"
                    "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                ),
                inline=False
            )

            # GitHub User & Repo Commands
            embed.add_field(
                name="",
                value=(
                    "**👤  GITHUB USER & REPOSITORY**\n"
                    "> **`/github_user <username>`**\n"
                    "> Get detailed GitHub user profile\n"
                    "> \n"
                    "> *Example:* `/github_user octocat`\n"
                    "> \n"
                    "> **`/github_repo <owner/repo>`**\n"
                    "> Get repository details and statistics\n"
                    "> \n"
                    "> *Example:* `/github_repo torvalds/linux`\n"
                    "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                ),
                inline=False
            )

            # GitHub Search & Trending
            embed.add_field(
                name="",
                value=(
                    "**🔍  GITHUB SEARCH & TRENDING**\n"
                    "> **`/github_search <query>`**\n"
                    "> Search repositories with advanced filters\n"
                    "> \n"
                    "> *Example:* `/github_search language:python stars:>1000`\n"
                    "> \n"
                    "> **`/github_trending <date_range> <type> [language]`**\n"
                    "> Show trending repositories or developers\n"
                    "> • **Date Range:** `today`, `this_week`, `this_month`\n"
                    "> • **Type:** `repositories`, `developers`\n"
                    "> • **Language:** Leave empty for ALL languages\n"
                    "> \n"
                    "> *Examples:*\n"
                    "> `/github_trending this_week repositories`\n"
                    "> `/github_trending today developers python`\n"
                    "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                ),
                inline=False
            )

            # GitHub Tree Command
            embed.add_field(
                name="",
                value=(
                    "**📁  REPOSITORY FILE TREE**\n"
                    "> **`/github_tree <repo> [max_depth]`**\n"
                    "> Display repository file structure\n"
                    "> \n"
                    "> *Example:* `/github_tree owner/repo 3`\n"
                    "> Supports GitHub URLs too!"
                ),
                inline=False
            )

            embed.set_footer(text="Made with Discord.py | Powered by GitHub API")
            embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"help command error: {e}")
            try:
                await interaction.followup.send("❌ An error occurred while displaying help.")
            except:
                pass

    @app_commands.command(name="sync_commands", description="Manually sync commands globally (Admin only)")
    @app_commands.default_permissions(administrator=True)
    async def sync_commands(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            synced = await self.bot.tree.sync()
            await interaction.followup.send(f"✅ Successfully synced {len(synced)} commands globally! Commands will appear in all servers in ~1 hour.", ephemeral=True)
        except Exception as e:
            logger.error(f"sync_commands error: {e}")
            try:
                await interaction.followup.send(f"❌ Failed to sync commands: {e}", ephemeral=True)
            except:
                pass


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
