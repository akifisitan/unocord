import os
import nextcord.ext
from nextcord.ext.commands import Bot
from config import BOT_TOKEN
import logging


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger(__name__)

intents = nextcord.Intents.default()
intents.message_content = True
intents.members = True
intents.dm_messages = False
activity = nextcord.Activity(
    name="Uno", type=nextcord.ActivityType.playing
)
bot = Bot(command_prefix="!u", intents=intents, activity=activity)


@bot.event
async def on_ready():
    logger.info(f"Connected to bot: {bot.user.name}")


def main():
    extensions_dir = os.path.join("app", "extensions")
    for extension in filter(lambda x: x.endswith("ext.py"), os.listdir(extensions_dir)):
        bot.load_extension(f"app.extensions.{extension[:-3]}")
    bot.run(BOT_TOKEN)


if __name__ == "__main__":
    main()
