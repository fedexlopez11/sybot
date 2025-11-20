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
intents.messages = True       # Needed for edit meessages
intents.reactions = True       # Needed for reaction events

bot = commands.Bot(command_prefix='!', intents=intents)

# === mod list data storage ===

from typing import Dict, Literal, Optional

Status = Literal["🟢Modding", "☕Break", "⛔Away"]
user_status: Dict[int, Status] = {}
status_channel_id: Optional[int] = None

# Emojis used for status selection
EMO_ACTIVE = "🟢"   # or "✅"
EMO_BREAK  = "☕"
EMO_AWAY   = "⛔"

# Where the single roster message lives (channel + message)
roster_channel_id: Optional[int] = None
roster_message_id: Optional[int] = None

def build_topic(guild: discord.Guild) -> str:
    modding, active, away = [], [], []
    for user_id, status in user_status.items():
        member = guild.get_member(user_id)
        if not member:
            continue
        name = member.display_name
        if status == "🟢Modding":
            modding.append(name)
        elif status == "☕Break":
            active.append(name)
        elif status == "⛔Away":
            away.append(name)
    a = ", ".join(modding) if modding else "~"
    b = ", ".join(active) if active else "~"
    c = ", ".join(away) if away else "~"
    stamp = datetime.utcnow().strftime("%H:%M UTC")
    text = f"🕒 Mod List • 🟢Modding: {a} | ☕Break: {b} | ⛔Away: {c} • {stamp}"
    return text[:1021] + "..." if len(text) > 1024 else text

def build_roster_text(guild: discord.Guild) -> str:
    modding, on_break, away = [], [], []
    for uid, status in user_status.items():
        member = guild.get_member(uid)
        name = member.display_name if member else f"<@{uid}>"
        if status == "Modding":
            modding.append(name)
        elif status == "Break":
            on_break.append(name)
        elif status == "Away":
            away.append(name)
    a = ", ".join(modding) if modding else "—"
    b = ", ".join(on_break) if on_break else "—"
    c = ", ".join(away) if away else "—"
    stamp = datetime.utcnow().strftime("%H:%M UTC")
    return (
        f"**🕒 Mod List**\n"
        f"🟢 Modding: {a}\n"
        f"☕ Break: {b}\n"
        f"⛔ Away: {c}\n"
        f"*Updated {stamp}*"
    )
    
async def get_roster_message(guild: discord.Guild) -> Optional[discord.Message]:
    if roster_channel_id is None or roster_message_id is None:
        return None
    channel = guild.get_channel(roster_channel_id)
    if not isinstance(channel, discord.TextChannel):
        return None
    try:
        return await channel.fetch_message(roster_message_id)
    except discord.NotFound:
        return None

async def update_roster_message(guild: discord.Guild):
    msg = await get_roster_message(guild)
    if not msg:
        return
    await msg.edit(content=build_roster_text(guild))


async def update_status_channel(guild: discord.Guild):
    if status_channel_id is None:
        return
    channel = guild.get_channel(status_channel_id)
    if not isinstance(channel, discord.TextChannel):
        return
    text = build_topic(guild)
    await channel.edit(topic=text, reason="Updating modding status")


@bot.tree.command(name="clock_setup", description="Create the roster message here and add reaction controls.")
async def clock_setup(interaction: discord.Interaction):
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("Use this in a text channel.", ephemeral=True)
        return

    # Post the first roster message
    content = build_roster_text(interaction.guild)
    msg = await channel.send(content)

    # Save where it lives (module vars)
    global roster_channel_id, roster_message_id
    roster_channel_id = channel.id
    roster_message_id = msg.id

    # Add reaction controls
    for emo in (EMO_ACTIVE, EMO_BREAK, EMO_AWAY):
        await msg.add_reaction(emo)

    await interaction.response.send_message("Roster message created and controls added.", ephemeral=True)

def emoji_to_status(emoji: str) -> Optional[Status]:
    if emoji == EMO_ACTIVE:
        return "Modding"
    if emoji == EMO_BREAK:
        return "Break"
    if emoji == EMO_AWAY:
        return "Away"
    return None

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    # ignore bot reactions / DMs
    if payload.user_id == bot.user.id or payload.guild_id is None:
        return
    # only our roster message
    if payload.message_id != (roster_message_id or 0):
        return

    status = emoji_to_status(str(payload.emoji))
    if status is None:
        return

    # update status
    user_status[payload.user_id] = status

    # enforce single selection: remove other status reactions from this user
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    channel = guild.get_channel(payload.channel_id)
    if not isinstance(channel, discord.TextChannel):
        return
    try:
        msg = await channel.fetch_message(payload.message_id)
    except discord.NotFound:
        return

    for emo in (EMO_ACTIVE, EMO_BREAK, EMO_AWAY):
        if emo != str(payload.emoji):
            # remove the other emoji from this user if present
            await msg.remove_reaction(emo, discord.Object(id=payload.user_id))

    # refresh roster message
    await msg.edit(content=build_roster_text(guild))

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    # Only act if it was on our roster message
    if payload.guild_id is None or payload.message_id != (roster_message_id or 0):
        return

    # If they removed their status reaction and have no other, we could mark them Away.
    # Check if the user still has any of the status reactions:
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    channel = guild.get_channel(payload.channel_id)
    if not isinstance(channel, discord.TextChannel):
        return
    try:
        msg = await channel.fetch_message(payload.message_id)
    except discord.NotFound:
        return

    member = guild.get_member(payload.user_id)
    # Determine if user still has any status emoji on the message
    still_has = False
    for reaction in msg.reactions:
        if str(reaction.emoji) in (EMO_ACTIVE, EMO_BREAK, EMO_AWAY):
            users = [u async for u in reaction.users()]
            if any(u.id == payload.user_id for u in users):
                still_has = True
                break

    if not still_has:
        # default them to Away if they cleared reactions
        user_status[payload.user_id] = "Away"
        await msg.edit(content=build_roster_text(guild))


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
