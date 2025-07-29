import os
import logging
from dotenv import load_dotenv
import selfbot

def run_bot():
    load_dotenv()
    selfbot.load_config()
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        logging.warning("No token found in .env file - bot will not start until token is provided")
        return  # Don't crash, just return without starting the bot
    selfbot.client.run(TOKEN)

if __name__ == '__main__':
    run_bot() 