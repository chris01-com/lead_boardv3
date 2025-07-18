import discord
from discord.ext import commands
import logging
from bot.leaderboard import LeaderboardManager
from bot.commands import setup_commands
from bot.events import setup_events
from bot.role_commands import setup_role_commands
from bot.role_rewards import RoleRewardManager
import os
from flask import Flask
from threading import Thread
import time

# Setup logging with better formatting
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

# Keep alive web server
app = Flask('')

@app.route('/')
def home():
    return """
    <html>
        <head>
            <title>Heavenly Demon Sect Bot</title>
            <style>
                body { font-family: Arial, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; text-align: center; padding: 50px; }
                .container { max-width: 600px; margin: 0 auto; }
                h1 { font-size: 2.5em; margin-bottom: 20px; }
                p { font-size: 1.2em; margin-bottom: 30px; }
                .status { background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Heavenly Demon Sect Bot</h1>
                <p>The Discord leaderboard bot is running successfully!</p>
                <div class="status">
                    <h3>System Status: Online</h3>
                    <p>All systems operational</p>
                </div>
            </div>
        </body>
    </html>
    """

@app.route('/status')
def status():
    return {
        "status": "running",
        "service": "Heavenly Demon Sect Bot",
        "timestamp": time.time(),
        "uptime": "healthy"
    }

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# Bot setup with enhanced intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.presences = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Initialize managers
leaderboard_manager = LeaderboardManager()
role_reward_manager = RoleRewardManager(bot, leaderboard_manager)

@bot.event
async def on_ready():
    """Enhanced startup event with better logging"""
    logger.info(f'════════════════════════════════════════')
    logger.info(f'  {bot.user} has connected to Discord!')
    logger.info(f'  Connected to {len(bot.guilds)} guilds')
    logger.info(f'════════════════════════════════════════')

    # Initialize database
    db_initialized = await leaderboard_manager.initialize_db()
    if not db_initialized:
        logger.error("Failed to initialize database. Bot cannot function properly.")
        return

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        logger.info(f'Successfully synced {len(synced)} slash commands')
    except Exception as e:
        logger.error(f'Failed to sync commands: {e}')

    # Initialize leaderboard for all guilds
    for guild in bot.guilds:
        logger.info(f'Initializing leaderboard for guild: {guild.name} ({guild.id}) with {len(guild.members)} total members')
        try:
            await leaderboard_manager.initialize_guild(guild)
            logger.info(f'✅ Successfully initialized leaderboard for {guild.name}')
        except Exception as e:
            logger.error(f'❌ Failed to initialize leaderboard for {guild.name}: {e}')

    # Setup persistent views for leaderboard buttons
    try:
        from bot.commands import LeaderboardView
        # Add a generic persistent view that will handle all leaderboard interactions
        bot.add_view(LeaderboardView(0, leaderboard_manager))
        logger.info('✅ Persistent leaderboard views restored')
    except Exception as e:
        logger.error(f'❌ Failed to restore persistent views: {e}')

    logger.info('Bot initialization complete - All systems ready!')

# Setup commands and events
setup_commands(bot, leaderboard_manager)
setup_events(bot, leaderboard_manager)
setup_role_commands(bot, role_reward_manager)

# Run the bot
if __name__ == '__main__':
    token = os.getenv('DISCORD_TOKEN', 'your_discord_bot_token_here')
    database_url = os.getenv('DATABASE_URL', 'postgresql://user:password@localhost/dbname')

    if token == 'your_discord_bot_token_here':
        logger.error('Please set the DISCORD_TOKEN environment variable')
    elif not database_url or database_url == 'postgresql://user:password@localhost/dbname':
        logger.error('Please set the DATABASE_URL environment variable')
    else:
        logger.info('Starting Heavenly Demon Sect Bot...')
        keep_alive()
        try:
            bot.run(token)
        except Exception as e:
            logger.error(f'Failed to start bot: {e}')
