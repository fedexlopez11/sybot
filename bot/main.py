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

Status = Literal["Modding", "Break", "Away"]

# For every guild (server), store its users' statuses
guild_user_status: Dict[int, Dict[int, Status]] = {}

status_channel_id: Optional[int] = None

# Emojis used for status selection
EMO_ACTIVE = "🟢"   # or "✅"
EMO_BREAK  = "☕"
EMO_AWAY   = "⛔"

# For every guild, store the channel ID and message ID of its roster message
rosters: Dict[int, tuple[int, int]] = {}

def build_topic(guild: discord.Guild) -> str:
    gmap = guild_user_status.get(guild.id, {})
    modding, active, away = [], [], []
    for user_id, status in gmap.items():
        member = guild.get_member(user_id)
        if not member:
            continue
        name = member.display_name
        if status == "Modding":
            modding.append(name)
        elif status == "Break":
            active.append(name)
        else:
            away.append(name)
    a = ", ".join(modding) if modding else "~"
    b = ", ".join(active) if active else "~"
    c = ", ".join(away) if away else "~"
    stamp = datetime.utcnow().strftime("%H:%M UTC")
    text = f" Mod List • 🟢Modding: {a} | ☕Break: {b} | ⛔Away: {c} • {stamp}"
    return text[:1021] + "..." if len(text) > 1024 else text

def build_roster_text(guild: discord.Guild) -> str:
    gmap = guild_user_status.get(guild.id, {})
    modding, on_break, away = [], [], []
    for uid, status in gmap.items():
        member = guild.get_member(uid)
        name = member.display_name if member else f"<@{uid}>"
        if status == "Modding":
            modding.append(name)
        elif status == "Break":
            on_break.append(name)
        else:
            away.append(name)
    a = ", ".join(modding) if modding else "—"
    b = ", ".join(on_break) if on_break else "—"
    c = ", ".join(away) if away else "—"
    stamp = datetime.utcnow().strftime("%H:%M UTC")
    return (
        f"** Mod List**\n"
        f"-------------------\n"
        f"🟢 Modding: {a}\n"
        f"☕ Break: {b}\n"
        f"⛔ Away: {c}\n"
        f"-------------------\n"
        f"*Updated {stamp}*"
    )
    
#async def get_roster_message(guild: discord.Guild) -> Optional[discord.Message]:
#    if roster_channel_id is None or roster_message_id is None:
#        return None
#    channel = guild.get_channel(roster_channel_id)
#    if not isinstance(channel, discord.TextChannel):
#        return None
#    try:
#        return await channel.fetch_message(roster_message_id)
#    except discord.NotFound:
#        return None

async def update_roster_message(guild: discord.Guild):

    """Update the roster message in the guild."""
    # Make sure this guild actually has a roster message recorded
    if guild_id not in rosters:
        return
    
    #unpack the channel and message IDs for this guild
    chan_id, msg_id = rosters[guild.id]

    #get the channel and message objects
    channel = guild.get_channel(chan_id)
    if not isinstance(channel, discord.TextChannel):
        return
    try:
        msg = await channel.fetch_message(msg_id)
    except discord.NotFound:
        return
    #edit the message content
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
    guild = interaction.guild
    channel = interaction.channel
    if guild is None or not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("This command can only be used in a server text channel.", ephemeral=True)
        return
    
    #if roster already exists for this guild, refresh it instead
    if guild.id in rosters:
        chan_id, msg_id = rosters[guild.id]
        ch = guild.get_channel(chan_id)
        try:
            if isinstance(ch, discord.TextChannel):
                msg = await ch.fetch_message(msg_id)
                await msg.edit(content=build_roster_text(guild))
                await interaction.response.send_message("Roster message already exists; refreshed its content.", ephemeral=True)
                return
        except discord.NotFound:
            pass  # proceed to create a new roster message

    #create the roster message
    content = build_roster_text(guild)
    msg = await channel.send(content)
    rosters[guild.id] = (channel.id, msg.id)

    #add reaction controls
    for emo in (EMO_ACTIVE, EMO_BREAK, EMO_AWAY):
        await msg.add_reaction(emo)
    await interaction.response.send_message("Roster message created and controls added.", ephemeral=True)


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
    gid = payload.guild_id
    if gid is None or gid not in rosters or payload.user_id == bot.user.id:
        return
    chan_id, msg_id = rosters[gid]
    if payload.message_id != msg_id:
        return

    status = emoji_to_status(str(payload.emoji))
    if status is None:
        return

    # update this guild's map
    gmap = guild_user_status.setdefault(gid, {})
    gmap[payload.user_id] = status

    guild = bot.get_guild(gid)
    channel = guild.get_channel(chan_id)
    msg = await channel.fetch_message(msg_id)

    # keep a single selection per user
    for emo in (EMO_ACTIVE, EMO_BREAK, EMO_AWAY):
        if emo != str(payload.emoji):
            await msg.remove_reaction(emo, discord.Object(id=payload.user_id))

    await msg.edit(content=build_roster_text(guild))


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    gid = payload.guild_id
    if gid is None or gid not in rosters:
        return
    chan_id, msg_id = rosters[gid]
    if payload.message_id != msg_id:
        return

    guild = bot.get_guild(gid)
    channel = guild.get_channel(chan_id)
    msg = await channel.fetch_message(msg_id)

    # if user has none of the status reactions left → Away
    has_any = False
    for reaction in msg.reactions:
        if str(reaction.emoji) in (EMO_ACTIVE, EMO_BREAK, EMO_AWAY):
            users = [u async for u in reaction.users()]
            if any(u.id == payload.user_id for u in users):
                has_any = True
                break
    if not has_any:
        gmap = guild_user_status.setdefault(gid, {})
        gmap[payload.user_id] = "Away"
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
