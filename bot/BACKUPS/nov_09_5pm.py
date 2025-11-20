import os
import logging
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from datetime import datetime


load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
guild_id = os.getenv("GUILD_ID")
if guild_id:
    GUILD_ID = int(guild_id)
else:
    GUILD_ID = None

intents = discord.Intents.default()
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# === mod list data storage ===

from typing import Dict, Literal, Optional

Status = Literal["Modding", "Break", "Away"]
user_status: Dict[int, Status] = {}
status_channel_id: Optional[int] = None

def build_topic(guild: discord.Guild) -> str:
    modding, active, away = [], [], []
    for user_id, status in user_status.items():
        member = guild.get_member(user_id)
        if not member:
            continue
        name = member.display_name
        if status == "Modding":
            modding.append(name)
        elif status == "Break":
            active.append(name)
        elif status == "Away":
            away.append(name)
    a = ", ".join(modding) if modding else "~"
    b = ", ".join(active) if active else "~"
    c = ", ".join(away) if away else "~"
    stamp = datetime.utcnow().strftime("%H:%M UTC")
    text  = f"Clock• Modding: {a} | Break: {b} | Away: {c} • {stamp}"
    return text[:1021] + "..." if len(text) > 1024 else text

async def update_status_channel(guild: discord.Guild):
    if status_channel_id is None:
        return
    channel = guild.get_channel(status_channel_id)
    if not isinstance(channel, discord.TextChannel):
        return
    text = build_topic(guild)
    await channel.edit(topic=text, reason="Updating modding status")

@bot.tree.command(name="clock_setchannel", description="Choose the channel that shows the clock roster in its topic.")
async def clock_setchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    # Needs Manage Channels in that channel
    perms = channel.permissions_for(channel.guild.me)
    if not perms.manage_channels:
        await interaction.response.send_message("I need **Manage Channels** in that channel.", ephemeral=True)
        return

    global status_channel_id
    status_channel_id = channel.id
    await update_status_channel(interaction.guild)
    await interaction.response.send_message(f"Clock channel set to #{channel.name}.", ephemeral=True)

@bot.tree.command(name="clock_in", description="Set status: Modding (active).")
async def clock_in(interaction: discord.Interaction):
    user_status[interaction.user.id] = "Modding"
    await update_status_channel(interaction.guild)
    await interaction.response.send_message("You are now **Modding** ✅", ephemeral=True)

@bot.tree.command(name="clock_break", description="Set status: Break.")
async def clock_break(interaction: discord.Interaction):
    user_status[interaction.user.id] = "Break"
    await update_status_channel(interaction.guild)
    await interaction.response.send_message("You are now on **Break** ☕", ephemeral=True)

@bot.tree.command(name="clock_out", description="Set status: Away (unavailable).")
async def clock_out(interaction: discord.Interaction):
    user_status[interaction.user.id] = "Away"
    await update_status_channel(interaction.guild)
    await interaction.response.send_message("You are now **Away** 🚫", ephemeral=True)

@bot.event
async def on_ready():
    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
        else:
            await bot.tree.sync()
        logging.info(f"✅ Logged in as {bot.user}")
    except Exception as e:
        logging.exception("Command sync failed: %s", e)

# --- start the bot ---
logging.basicConfig(level=logging.INFO)

async def main():
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN missing. Put it in your .env")
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
