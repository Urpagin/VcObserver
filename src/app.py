import logging
import os
import pathlib

import discord
from discord import app_commands, Object
from dotenv import load_dotenv

from vc_observer import VcObserver

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GUILD_ID = 926441829157716019

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
)

intents = discord.Intents.all()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@client.event
async def on_ready():
    logging.info("Bot is ready.")
    # Start observing VCs in the specified guild
    VcObserver(
        bot=client,
        tree=tree,
        filepath=pathlib.Path("./vc_time_elapsed.json")
    )
    # Register slash commands for this guild only
    await tree.sync(guild=Object(id=GUILD_ID))
    await client.change_presence(activity=discord.Game("The Cave is waiting for you 👀"))


@tree.command(
    name="test_command",
    description="Test command.",
    guild=Object(id=GUILD_ID)
)
async def test_command(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.send_message(f"Hello {user.name}.")


if __name__ == "__main__":
    client.run(BOT_TOKEN)
