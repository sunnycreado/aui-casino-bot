import discord
import asyncio
import os
import json
from dotenv import load_dotenv
import logging
import time

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize client without intents (default for self-bot)
client = discord.Client()

# Global variables for bot configuration
CONFIG = {
    'channel_id': None,
    'messages': [],
    'msg_delay': 5,
    'loop_delay': 60,
    'role_id': None,
    'prefix': '!'
}

# Load configuration from JSON
CONFIG_FILE = 'config.json'
def load_config():
    global CONFIG
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                CONFIG.update(json.load(f))
            logger.info("Loaded configuration from config.json")
        else:
            logger.info("No config.json found, using default configuration")
    except json.JSONDecodeError as e:
        logger.error(f"JSON error in config: {e}")
    except Exception as e:
        logger.error(f"Error loading config: {e}")

# Save configuration to JSON
def save_config():
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(CONFIG, f, indent=4)
        logger.info("Saved configuration to config.json")
    except Exception as e:
        logger.error(f"Error saving config: {e}")

# Message loop task with exponential backoff
async def send_messages():
    max_retries = 5
    base_delay = 1
    while True:
        if not CONFIG['messages'] or not CONFIG['channel_id']:
            await asyncio.sleep(CONFIG['loop_delay'] * 60)
            continue
        channel = client.get_channel(CONFIG['channel_id'])
        if not channel:
            logger.warning("Target channel not found!")
            await asyncio.sleep(CONFIG['loop_delay'] * 60)
            continue
        for msg in CONFIG['messages']:
            retries = 0
            while retries < max_retries:
                try:
                    await channel.send(msg)
                    logger.info(f"Sent message: {msg}")
                    await asyncio.sleep(CONFIG['msg_delay'])
                    break
                except discord.errors.Forbidden:
                    logger.error(f"No permission to send messages in channel {channel.id}")
                    break
                except discord.errors.HTTPException as e:
                    if e.status == 429:  # Rate limit
                        retry_after = e.retry_after or 1
                        backoff = base_delay * (2 ** retries)
                        sleep_time = min(retry_after, backoff)
                        logger.warning(f"Rate limited, retrying after {sleep_time} seconds (attempt {retries + 1}/{max_retries})")
                        await asyncio.sleep(sleep_time)
                        retries += 1
                    else:
                        logger.error(f"Error sending message: {e}")
                        break
                except Exception as e:
                    logger.error(f"Error sending message: {e}")
                    break
            if retries >= max_retries:
                logger.error(f"Max retries reached for message: {msg}")
                break
        await asyncio.sleep(CONFIG['loop_delay'] * 60)

# Global variable to track loop task
loop_task = None

@client.event
async def on_ready():
    global CONFIG, loop_task
    logger.info(f'Logged in as {client.user}')
    load_config()
    if loop_task:
        try:
            loop_task.cancel()
            logger.info("Message loop stopped on startup")
        except Exception as e:
            logger.error(f"Error stopping loop task: {e}")

@client.event
async def on_disconnect():
    logger.warning("Disconnected from Discord Gateway")

@client.event
async def on_connect():
    logger.info("Connected to Discord Gateway")

# Check if user has the required role
async def has_required_role(user, guild):
    if guild is None or CONFIG['role_id'] is None:
        return True
    role = discord.utils.get(guild.roles, id=CONFIG['role_id'])
    return role in user.roles if role else False

# Message-based confirmation
async def wait_for_confirmation(message):
    await message.channel.send("Reply with 'yes' to confirm or 'no' to cancel.")
    def check(m):
        return m.author == message.author and m.channel == message.channel and m.content.lower() in ['yes', 'no']
    try:
        response = await client.wait_for('message', timeout=30.0, check=check)
        return response.content.lower() == 'yes'
    except asyncio.TimeoutError:
        await message.channel.send("Confirmation timed out")
        return False

# Validate message length
def validate_message(msg):
    if len(msg) > 2000:
        return False, "Message exceeds Discord's 2000-character limit"
    if not msg.strip():
        return False, "Message cannot be empty"
    return True, None

@client.event
async def on_message(message):
    global loop_task
    # Check if user has the required role (skip in DMs)
    if not await has_required_role(message.author, message.guild):
        logger.info(f"User {message.author} denied access in guild {message.guild.id if message.guild else 'DM'} due to role restriction")
        return

    if not message.content.startswith(CONFIG['prefix']):
        return

    logger.info(f"Processing command from {message.author} in guild {message.guild.id if message.guild else 'DM'}: {message.content}")
    content = message.content[len(CONFIG['prefix']):].strip()
    args = content.split()
    if not args:
        return
    command = args[0].lower()
    args = args[1:]

    try:
        if command == "setprefix":
            if not args:
                await message.channel.send("Missing required argument: prefix")
                return
            new_prefix = args[0]
            await message.channel.send(f"Are you sure you want to change prefix to `{new_prefix}`?")
            if await wait_for_confirmation(message):
                CONFIG['prefix'] = new_prefix
                save_config()
                await message.channel.send(f"Prefix changed to `{new_prefix}`")
                logger.info(f"Prefix changed: {new_prefix}")
            else:
                await message.channel.send("Prefix change canceled")

        elif command == "setchannel":
            if not args or not message.channel_mentions:
                await message.channel.send("Missing channel mention")
                return
            channel = message.channel_mentions[0]
            CONFIG['channel_id'] = channel.id
            save_config()
            await message.channel.send(f"Messages will be sent to {channel.mention}")
            logger.info(f"Channel set: {channel.id}")

        elif command == "am":
            if not args:
                await message.channel.send("Missing message content")
                return
            msg = ' '.join(args)
            is_valid, error = validate_message(msg)
            if not is_valid:
                await message.channel.send(error)
                return
            CONFIG['messages'].append(msg)
            save_config()
            await message.channel.send(f"Added message: `{msg}`")
            logger.info(f"Added message: {msg}")

        elif command == "rm":
            if not args:
                await message.channel.send("Missing index")
                return
            try:
                index = int(args[0])
                if index < 1 or index > len(CONFIG['messages']):
                    await message.channel.send(f"Invalid index. Use 1 to {len(CONFIG['messages'])}")
                    return
                msg = CONFIG['messages'].pop(index - 1)
                save_config()
                await message.channel.send(f"Removed message: `{msg}`")
                logger.info(f"Removed message: {msg}")
            except ValueError:
                await message.channel.send("Index must be a number")

        elif command == "clearmsgs":
            if not CONFIG['messages']:
                await message.channel.send("No messages to clear")
                return
            await message.channel.send("Clear all messages?")
            if await wait_for_confirmation(message):
                CONFIG['messages'] = []
                save_config()
                await message.channel.send("Messages cleared")
                logger.info("Messages cleared")
            else:
                await message.channel.send("Clear canceled")

        elif command == "listmsgs":
            if not CONFIG['messages']:
                await message.channel.send("No messages set")
                return
            response = "Messages:\n" + "\n".join(f"{i+1}. {msg}" for i, msg in enumerate(CONFIG['messages']))
            await message.channel.send(response)

        elif command == "setmsgdelay":
            if not args:
                await message.channel.send("Missing seconds")
                return
            try:
                seconds = float(args[0])
                if seconds <= 0:
                    await message.channel.send("Delay must be positive")
                    return
                CONFIG['msg_delay'] = seconds
                save_config()
                await message.channel.send(f"Message delay set to {seconds} seconds")
                logger.info(f"Message delay: {seconds}")
            except ValueError:
                await message.channel.send("Seconds must be a number")

        elif command == "setloopdelay":
            if not args:
                await message.channel.send("Missing minutes")
                return
            try:
                minutes = float(args[0])
                if minutes <= 0:
                    await message.channel.send("Delay must be positive")
                    return
                CONFIG['loop_delay'] = minutes
                save_config()
                await message.channel.send(f"Loop delay set to {minutes} minutes")
                logger.info(f"Loop delay: {minutes}")
            except ValueError:
                await message.channel.send("Minutes must be a number")

        elif command == "setrole":
            if not message.guild:
                await message.channel.send("This command can only be used in a server")
                return
            if not args or not message.role_mentions:
                await message.channel.send("Missing role mention")
                return
            role = message.role_mentions[0]
            await message.channel.send(f"Restrict commands to {role.mention}?")
            if await wait_for_confirmation(message):
                CONFIG['role_id'] = role.id
                save_config()
                await message.channel.send(f"Commands restricted to {role.mention}")
                logger.info(f"Role set: {role.id}")
            else:
                await message.channel.send("Role change canceled")

        elif command == "clearrole":
            if CONFIG['role_id'] is None:
                await message.channel.send("No role restriction is set")
                return
            await message.channel.send("Remove role restriction for commands?")
            if await wait_for_confirmation(message):
                CONFIG['role_id'] = None
                save_config()
                await message.channel.send("Role restriction removed, all users can now use commands")
                logger.info("Role restriction cleared")
            else:
                await message.channel.send("Role restriction removal canceled")

        elif command == "ping":
            latency = round(client.latency * 1000)  # Convert to milliseconds
            await message.channel.send(f"Pong! Latency: {latency}ms")
            logger.info(f"Ping command executed: Latency {latency}ms")

        elif command == "status":
            channel = client.get_channel(CONFIG['channel_id']) if CONFIG['channel_id'] else None
            status_text = (
                f"**Self-Bot Status**\n"
                f"Prefix: `{CONFIG['prefix']}`\n"
                f"Channel: {channel.mention if channel else 'Not set'}\n"
                f"Messages:\n{chr(10).join([f'{i+1}. {msg}' for i, msg in enumerate(CONFIG['messages'])]) if CONFIG['messages'] else 'None'}\n"
                f"Message Delay: {CONFIG['msg_delay']} seconds\n"
                f"Loop Delay: {CONFIG['loop_delay']} minutes\n"
                f"Loop Status: {'Running' if loop_task and not loop_task.done() else 'Stopped'}"
            )
            await message.channel.send(status_text)

        elif command == "startloop":
            if loop_task and not loop_task.done():
                await message.channel.send("Loop already running")
                return
            if not CONFIG['channel_id'] or not CONFIG['messages']:
                await message.channel.send("Set channel and messages first")
                return
            loop_task = client.loop.create_task(send_messages())
            await message.channel.send("Loop started")
            logger.info("Loop started")

        elif command == "stoploop":
            if not loop_task or loop_task.done():
                await message.channel.send("Loop not running")
                return
            loop_task.cancel()
            await message.channel.send("Loop stopped")
            logger.info("Loop stopped")

        elif command == "help":
            help_text = (
                "**Self-Bot Commands**\n"
                f"`{CONFIG['prefix']}setprefix <prefix>`: Change command prefix\n"
                f"`{CONFIG['prefix']}setchannel <channel>`: Set message channel\n"
                f"`{CONFIG['prefix']}am <message>`: Add message to loop\n"
                f"`{CONFIG['prefix']}rm <index>`: Remove message by index\n"
                f"`{CONFIG['prefix']}clearmsgs`: Clear all messages\n"
                f"`{CONFIG['prefix']}listmsgs`: List messages\n"
                f"`{CONFIG['prefix']}setmsgdelay <seconds>`: Set message delay\n"
                f"`{CONFIG['prefix']}setloopdelay <minutes>`: Set loop delay\n"
                f"`{CONFIG['prefix']}setrole <role>`: Restrict commands to role\n"
                f"`{CONFIG['prefix']}clearrole`: Remove role restriction\n"
                f"`{CONFIG['prefix']}ping`: Check bot latency\n"
                f"`{CONFIG['prefix']}status`: Show status\n"
                f"`{CONFIG['prefix']}startloop`: Start message loop\n"
                f"`{CONFIG['prefix']}stoploop`: Stop message loop\n"
                f"`{CONFIG['prefix']}help`: Show this help"
            )
            await message.channel.send(help_text)

        else:
            await message.channel.send(f"Unknown command. Use {CONFIG['prefix']}help")

    except Exception as e:
        await message.channel.send(f"Error: {str(e)}")
        logger.error(f"Command error: {e}")