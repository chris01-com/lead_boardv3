import discord
from discord.ext import commands
import logging
from bot.utils import create_error_embed, create_info_embed, create_success_embed, Colors, get_rank_title_by_points, create_promotion_embed

logger = logging.getLogger(__name__)

def setup_events(bot, leaderboard_manager):
    """Setup all bot events with enhanced error handling and logging"""
    
    @bot.event
    async def on_member_join(member):
        """Enhanced event for when a member joins the server"""
        try:
            if not member.bot:  # Skip bots
                await leaderboard_manager.add_member(
                    member.guild.id, member.id, member.display_name
                )
                logger.info(f"✓ Added new member {member.display_name} to leaderboard for guild {member.guild.name}")
                
                # Auto-update all active leaderboard views for this guild
                from bot.commands import update_active_leaderboards
                await update_active_leaderboards(member.guild.id)
                
        except Exception as e:
            logger.error(f"✗ Error adding new member {member.display_name} to leaderboard: {e}")

    @bot.event
    async def on_member_remove(member):
        """Enhanced event for when a member leaves the server"""
        try:
            if not member.bot:  # Skip bots
                await leaderboard_manager.remove_member(member.guild.id, member.id)
                logger.info(f"✓ Removed member {member.display_name} from leaderboard for guild {member.guild.name}")
                
                # Auto-update all active leaderboard views for this guild
                from bot.commands import update_active_leaderboards
                await update_active_leaderboards(member.guild.id)
                
        except Exception as e:
            logger.error(f"✗ Error removing member {member.display_name} from leaderboard: {e}")

    @bot.event
    async def on_member_update(before, after):
        """Enhanced event for when a member's roles change - handles rank promotions"""
        try:
            if before.bot:  # Skip bots
                return
                
            # Check if roles have changed
            before_roles = set(before.roles)
            after_roles = set(after.roles)
            
            # Get newly added roles
            added_roles = after_roles - before_roles
            removed_roles = before_roles - after_roles
            
            if not added_roles and not removed_roles:
                return  # No role changes
                
            # Get member's current contribution points
            user_stats = await leaderboard_manager.get_user_stats(after.guild.id, after.id)
            if not user_stats:
                logger.warning(f"No stats found for {after.display_name} in role update event")
                return
                
            current_points = user_stats['points']
            
            # Check for rank promotions with newly added roles
            if added_roles:
                await check_rank_promotion(after, added_roles, current_points)
                
            # Update active leaderboards if roles changed
            from bot.commands import update_active_leaderboards
            await update_active_leaderboards(after.guild.id)
            
        except Exception as e:
            logger.error(f"✗ Error in member update event for {after.display_name}: {e}")

    async def check_rank_promotion(member, added_roles, current_points):
        """Check if role addition qualifies for rank promotion congratulations"""
        try:
            # Define rank-eligible roles with their point requirements
            rank_roles = {
                # Core Disciple roles (750+ points required)
                1391059979167072286: {"rank": "Core Disciple", "points_required": 750},
                1391060071189971075: {"rank": "Core Disciple", "points_required": 750},
                1382602945752727613: {"rank": "Core Disciple", "points_required": 750},
                
                # Inner Disciple roles (350+ points required)
                1268528848740290580: {"rank": "Inner Disciple", "points_required": 350},
                1308823860740624384: {"rank": "Inner Disciple", "points_required": 350},
                1391059841505689680: {"rank": "Inner Disciple", "points_required": 350},
                
                # Outer Disciple roles (10+ points required)
                1389474689818296370: {"rank": "Outer Disciple", "points_required": 10},
                1266826177163694181: {"rank": "Outer Disciple", "points_required": 10},
                1308823565881184348: {"rank": "Outer Disciple", "points_required": 10},
                
                # Special roles (no point requirements)
                1266143259801948261: {"rank": "Demon God", "points_required": 0},
                1281115906717650985: {"rank": "Heavenly Demon", "points_required": 0},
                1276607675735736452: {"rank": "Guardian", "points_required": 0},
                1304283446016868424: {"rank": "Supreme Demon", "points_required": 0},
                1266242655642456074: {"rank": "Demon Council", "points_required": 0},
                1390279781827874937: {"rank": "Young Master", "points_required": 0}
            }
            
            # Check each newly added role
            for role in added_roles:
                if role.id in rank_roles:
                    rank_info = rank_roles[role.id]
                    required_points = rank_info["points_required"]
                    rank_name = rank_info["rank"]
                    
                    # Check if user has sufficient points for this rank
                    if current_points >= required_points:
                        await send_rank_promotion_congratulations(member, rank_name, current_points, role)
                        logger.info(f"✅ Sent rank promotion congratulations to {member.display_name} for {rank_name}")
                    else:
                        logger.info(f"ℹ️ {member.display_name} received {rank_name} role but only has {current_points} points (needs {required_points})")
                        
        except Exception as e:
            logger.error(f"❌ Error checking rank promotion for {member.display_name}: {e}")

    async def send_rank_promotion_congratulations(member, rank_name, current_points, role):
        """Send congratulations message for rank promotion"""
        try:
            # Get the previous rank for comparison
            previous_rank = get_rank_title_by_points(max(0, current_points - 1), member)
            
            # Create beautiful promotion embed without emojis, passing the role information
            embed = create_promotion_embed(member, previous_rank, rank_name, current_points, role)
            
            # Get configured notification channel
            notification_channel_id = await leaderboard_manager.get_guild_config(
                member.guild.id, 'notification_channel'
            )
            
            # Determine where to send the notification
            if notification_channel_id:
                # Use configured channel
                channel = member.guild.get_channel(notification_channel_id)
                if channel and channel.permissions_for(member.guild.me).send_messages:
                    await channel.send(content=f"{member.mention}", embed=embed)
                    logger.info(f"✅ Sent promotion notification to configured channel #{channel.name}")
                else:
                    # Fallback to first available channel
                    await send_to_fallback_channel(member.guild, embed, member)
            else:
                # No channel configured, use fallback
                await send_to_fallback_channel(member.guild, embed, member)
            
            # Send DM to the user
            await send_promotion_dm(member, embed)
                
        except Exception as e:
            logger.error(f"❌ Error sending rank promotion congratulations: {e}")
    
    async def send_to_fallback_channel(guild, embed, member):
        """Send message to the first available channel as fallback"""
        try:
            # Try to find a general or announcements channel first
            preferred_names = ['general', 'announcements', 'leaderboard', 'bot-commands']
            
            for channel_name in preferred_names:
                channel = discord.utils.get(guild.text_channels, name=channel_name)
                if channel and channel.permissions_for(guild.me).send_messages:
                    await channel.send(content=f"{member.mention}", embed=embed)
                    logger.info(f"✅ Sent promotion notification to fallback channel #{channel.name}")
                    return
            
            # If no preferred channels found, use the first available text channel
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    await channel.send(content=f"{member.mention}", embed=embed)
                    logger.info(f"✅ Sent promotion notification to available channel #{channel.name}")
                    return
                    
            logger.warning(f"⚠️ No available channels found to send promotion notification in {guild.name}")
            
        except Exception as e:
            logger.error(f"❌ Error sending to fallback channel: {e}")
    
    async def send_promotion_dm(member, embed):
        """Send promotion notification to user's DMs"""
        try:
            # Send DM to the user
            await member.send(embed=embed)
            logger.info(f"✅ Sent promotion DM to {member.display_name}")
            
        except discord.Forbidden:
            logger.warning(f"⚠️ Cannot send DM to {member.display_name} - DMs are disabled")
        except discord.HTTPException as e:
            logger.error(f"❌ Failed to send DM to {member.display_name}: {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error sending DM to {member.display_name}: {e}")

    @bot.event
    async def on_guild_join(guild):
        """Enhanced event for when bot joins a new guild"""
        try:
            logger.info(f"✓ Bot joined new guild: {guild.name} (ID: {guild.id})")
            logger.info(f"  Guild has {len(guild.members)} members")
            
            # Initialize leaderboard for the new guild
            await leaderboard_manager.initialize_guild(guild)
            logger.info(f"✓ Initialized leaderboard for new guild: {guild.name}")
            
        except Exception as e:
            logger.error(f"✗ Error initializing new guild {guild.name}: {e}")

    @bot.event
    async def on_guild_remove(guild):
        """Enhanced event for when bot leaves a guild"""
        logger.info(f"✓ Bot left guild: {guild.name} (ID: {guild.id})")
        # Note: We don't automatically delete guild data in case the bot rejoins

    @bot.tree.error
    async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        """Enhanced global error handler for slash commands"""
        logger.error(f"App command error in {interaction.command.name if interaction.command else 'unknown'}: {error}")
        
        # Create appropriate error embed based on error type
        if isinstance(error, discord.app_commands.MissingPermissions):
            embed = create_error_embed(
                "Permission Denied",
                "You don't have the required permissions to use this command.",
                "This command requires administrator privileges."
            )
            
        elif isinstance(error, discord.app_commands.CommandOnCooldown):
            embed = create_error_embed(
                "Command Cooldown",
                f"Please wait {error.retry_after:.1f} seconds before using this command again.",
                "Cooldowns help prevent spam and ensure fair usage."
            )
            
        elif isinstance(error, discord.app_commands.BotMissingPermissions):
            missing_perms = ", ".join(error.missing_permissions)
            embed = create_error_embed(
                "Bot Missing Permissions",
                f"The bot is missing required permissions: {missing_perms}",
                "Please contact a server administrator to grant the necessary permissions."
            )
            
        elif isinstance(error, discord.app_commands.CommandNotFound):
            embed = create_error_embed(
                "Command Not Found",
                "The command you tried to use doesn't exist.",
                "Use `/help` to see available commands."
            )
            
        elif isinstance(error, discord.app_commands.CheckFailure):
            embed = create_error_embed(
                "Command Check Failed",
                "You don't meet the requirements to use this command.",
                "Check if you have the right roles or permissions."
            )
            
        else:
            # Generic error for unexpected issues
            embed = create_error_embed(
                "Unexpected Error",
                "An unexpected error occurred while processing your command.",
                "Please try again later. If the problem persists, contact support."
            )
            
            # Log the full error for debugging
            logger.error(f"Unhandled app command error: {type(error).__name__}: {error}")
            
        # Send error response
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")

    @bot.event
    async def on_error(event, *args, **kwargs):
        """Enhanced global error handler for general bot events"""
        logger.error(f"Error in event {event}: {args}, {kwargs}")
        
        # Log additional context for debugging
        if args:
            logger.error(f"Event args: {args}")
        if kwargs:
            logger.error(f"Event kwargs: {kwargs}")

    @bot.event
    async def on_command_error(ctx, error):
        """Enhanced error handler for prefix commands (if any)"""
        logger.error(f"Prefix command error: {error}")
        
        # Since we're mainly using slash commands, this is mainly for fallback
        if isinstance(error, commands.CommandNotFound):
            return  # Ignore unknown commands
            
        elif isinstance(error, commands.MissingPermissions):
            embed = create_error_embed(
                "Permission Denied",
                "You don't have permission to use this command.",
                "Contact an administrator if you believe this is incorrect."
            )
            await ctx.send(embed=embed, delete_after=10)
            
        else:
            embed = create_error_embed(
                "Command Error",
                "An error occurred while executing the command.",
                "Please try again or contact support."
            )
            await ctx.send(embed=embed, delete_after=10)

    @bot.event
    async def on_disconnect():
        """Enhanced disconnect event logging"""
        logger.warning("⚠️ Bot disconnected from Discord")

    @bot.event
    async def on_resumed():
        """Enhanced resume event logging"""
        logger.info("✓ Bot connection resumed")

    @bot.event
    async def on_connect():
        """Enhanced connect event logging"""
        logger.info("✓ Bot connected to Discord")

    logger.info("✓ Enhanced event handlers registered successfully")
