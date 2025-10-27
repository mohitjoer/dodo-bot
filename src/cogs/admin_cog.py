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

    @app_commands.command(name="sync_commands", description="Manually sync commands to this server (Admin only)")
    @app_commands.default_permissions(administrator=True)
    async def sync_commands(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            if self.bot.target_guild_id and interaction.guild and interaction.guild.id == self.bot.target_guild_id:
                synced = await self.bot.tree.sync(guild=interaction.guild)
                await interaction.followup.send(f"✅ Successfully synced {len(synced)} commands to your server!", ephemeral=True)
            else:
                await interaction.followup.send("❌ This command can only be used in the target server!", ephemeral=True)
        except Exception as e:
            logger.error(f"sync_commands error: {e}")
            try:
                await interaction.followup.send(f"❌ Failed to sync commands: {e}", ephemeral=True)
            except:
                pass


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
