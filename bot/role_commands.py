import discord
from discord.ext import commands
from discord import app_commands
import logging
from bot.utils import create_success_embed, create_error_embed, create_info_embed, get_rank_title_by_points, Colors

logger = logging.getLogger(__name__)

def setup_role_commands(bot, role_reward_manager):
    """Setup enhanced role reward management commands"""

    @bot.tree.command(name='assignrolepoints', description='Assign points to all users with a specific role (Admin only)')
    @app_commands.describe(
        role_id='The role ID to assign points to',
        points='Number of points to assign (can be negative)'
    )
    @app_commands.default_permissions(administrator=True)
    async def assign_role_points(interaction: discord.Interaction, role_id: str, points: int):
        """Enhanced role point assignment with better feedback"""
        try:
            # Defer response as this might take time
            await interaction.response.defer(ephemeral=True)

            # Validate and get the role
            try:
                role_id_int = int(role_id)
                role = interaction.guild.get_role(role_id_int)
            except ValueError:
                embed = create_error_embed(
                    "Invalid Role ID",
                    "Please provide a valid numeric role ID.",
                    "You can find role IDs by right-clicking on a role and selecting 'Copy ID' (Developer Mode required)."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            if not role:
                embed = create_error_embed(
                    "Role Not Found",
                    f"No role found with ID `{role_id}` in this server.",
                    "Please verify the role ID and try again."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Get all members with this role
            members_with_role = []
            total_guild_members = len(interaction.guild.members)

            logger.info(f"🔍 Checking role {role.name} (ID: {role_id}) - Guild has {total_guild_members} total members")

            for member in interaction.guild.members:
                if not member.bot and role in member.roles:
                    members_with_role.append(member)

            logger.info(f"✅ Found {len(members_with_role)} members with role {role.name}")

            if not members_with_role:
                embed = create_info_embed(
                    "No Members Found",
                    f"No non-bot members found with role **{role.name}**.",
                    fields=[
                        {"name": "Guild Statistics", "value": f"Total members: {total_guild_members}", "inline": True},
                        {"name": "Role Statistics", "value": f"Members with role: 0", "inline": True},
                        {"name": "Suggestion", "value": f"Try using `/checkrole role_id:{role_id}` to debug this.", "inline": False}
                    ]
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Process point assignment
            success_count = 0
            failed_members = []

            for member in members_with_role:
                success = await role_reward_manager.leaderboard_manager.update_points(
                    interaction.guild.id, member.id, points, member.display_name
                )
                if success:
                    success_count += 1
                else:
                    failed_members.append(member.display_name)

            # Trigger auto-update for all active leaderboard views
            await role_reward_manager.trigger_leaderboard_updates(interaction.guild.id)

            # Create comprehensive success embed
            embed_color = Colors.SUCCESS if points >= 0 else Colors.WARNING
            embed = discord.Embed(
                title="Role Points Assignment Complete",
                description=f"Successfully processed point assignment for role **{role.name}**",
                color=embed_color,
                timestamp=discord.utils.utcnow()
            )

            # Assignment details
            embed.add_field(
                name="Assignment Details",
                value=f"**Role:** {role.name}\n**Points:** {points:+d}\n**Members Processed:** {success_count}/{len(members_with_role)}",
                inline=False
            )

            # Show rank distribution after assignment
            rank_distribution = {}
            for member in members_with_role:
                try:
                    current_stats = await role_reward_manager.leaderboard_manager.get_user_stats(
                        interaction.guild.id, member.id
                    )
                    if current_stats:
                        member_points = current_stats['points']
                        rank_title = get_rank_title_by_points(member_points, member)
                        rank_distribution[rank_title] = rank_distribution.get(rank_title, 0) + 1
                except Exception as e:
                    logger.warning(f"Failed to get stats for {member.display_name}: {e}")

            if rank_distribution:
                rank_text = ""
                for rank, count in sorted(rank_distribution.items(), key=lambda x: x[1], reverse=True):
                    rank_text += f"**{rank}:** {count} members\n"

                embed.add_field(
                    name="Rank Distribution",
                    value=rank_text,
                    inline=True
                )

            # Add statistics
            stats_text = f"**Total Points Distributed:** {points * success_count:+d}\n"
            stats_text += f"**Success Rate:** {(success_count/len(members_with_role)*100):.1f}%"

            embed.add_field(
                name="Statistics",
                value=stats_text,
                inline=True
            )

            # Add failure info if any
            if failed_members:
                failure_text = f"**Failed Updates:** {len(failed_members)}\n"
                if len(failed_members) <= 5:
                    failure_text += "Members: " + ", ".join(failed_members)
                else:
                    failure_text += f"Members: {', '.join(failed_members[:5])}... and {len(failed_members)-5} more"

                embed.add_field(
                    name="Failures",
                    value=failure_text,
                    inline=False
                )

            # Add admin info
            embed.set_footer(
                text=f"Executed by {interaction.user.display_name} • Heavenly Demon Sect",
                icon_url=interaction.user.avatar.url if interaction.user.avatar else None
            )

            await interaction.followup.send(embed=embed)
            logger.info(f"✅ Assigned {points} points to {success_count} members with role {role.name}")

        except Exception as e:
            logger.error(f"❌ Error assigning role points: {e}")
            embed = create_error_embed(
                "Assignment Failed",
                "An unexpected error occurred during role point assignment.",
                "Please try again or contact technical support if the issue persists."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @bot.tree.command(name='checkrole', description='Check members with a specific role (Debug)')
    @app_commands.describe(role_id='The role ID to check')
    @app_commands.default_permissions(administrator=True)
    async def check_role(interaction: discord.Interaction, role_id: str):
        """Enhanced role debugging command"""
        try:
            await interaction.response.defer(ephemeral=True)

            # Validate and get the role
            try:
                role_id_int = int(role_id)
                role = interaction.guild.get_role(role_id_int)
            except ValueError:
                embed = create_error_embed(
                    "Invalid Role ID",
                    "Please provide a valid numeric role ID.",
                    "Enable Developer Mode and right-click on a role to copy its ID."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            if not role:
                embed = create_error_embed(
                    "Role Not Found",
                    f"No role found with ID `{role_id}` in this server.",
                    "Please verify the role ID is correct and the role exists."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Get all members with this role
            members_with_role = []
            bot_members_with_role = []

            for member in interaction.guild.members:
                if role in member.roles:
                    if member.bot:
                        bot_members_with_role.append(member)
                    else:
                        members_with_role.append(member)

            # Create comprehensive debug embed
            embed = discord.Embed(
                title="Role Analysis Report",
                description=f"Detailed analysis for role **{role.name}**",
                color=Colors.INFO,
                timestamp=discord.utils.utcnow()
            )

            # Role information
            embed.add_field(
                name="Role Information",
                value=f"**Name:** {role.name}\n**ID:** {role.id}\n**Color:** {role.color}\n**Position:** {role.position}",
                inline=False
            )

            # Member statistics
            embed.add_field(
                name="Member Statistics",
                value=f"**Human Members:** {len(members_with_role)}\n**Bot Members:** {len(bot_members_with_role)}\n**Total Members:** {len(members_with_role) + len(bot_members_with_role)}",
                inline=True
            )

            # Guild statistics
            embed.add_field(
                name="Guild Statistics",
                value=f"**Total Guild Members:** {len(interaction.guild.members)}\n**Human Members:** {len([m for m in interaction.guild.members if not m.bot])}\n**Bot Members:** {len([m for m in interaction.guild.members if m.bot])}",
                inline=True
            )

            # Show first 10 members with their stats
            if members_with_role:
                member_list = ""
                for i, member in enumerate(members_with_role[:10]):
                    try:
                        current_stats = await role_reward_manager.leaderboard_manager.get_user_stats(
                            interaction.guild.id, member.id
                        )
                        if current_stats:
                            member_points = current_stats['points']
                            rank_title = get_rank_title_by_points(member_points, member)
                            member_list += f"**{member.display_name}**\n  Points: {member_points} | Rank: {rank_title}\n"
                        else:
                            member_list += f"**{member.display_name}**\n  Not in leaderboard\n"
                    except Exception as e:
                        member_list += f"**{member.display_name}**\n  Error loading stats\n"
                        logger.warning(f"Failed to load stats for {member.display_name}: {e}")

                if len(members_with_role) > 10:
                    member_list += f"\n... and {len(members_with_role) - 10} more members"

                embed.add_field(
                    name="Members with Role (First 10)",
                    value=member_list,
                    inline=False
                )
            else:
                embed.add_field(
                    name="Members with Role",
                    value="No human members found with this role",
                    inline=False
                )

            # Show rank distribution
            if members_with_role:
                rank_distribution = {}
                for member in members_with_role:
                    try:
                        current_stats = await role_reward_manager.leaderboard_manager.get_user_stats(
                            interaction.guild.id, member.id
                        )
                        if current_stats:
                            member_points = current_stats['points']
                            rank_title = get_rank_title_by_points(member_points, member)
                            rank_distribution[rank_title] = rank_distribution.get(rank_title, 0) + 1
                    except Exception:
                        pass

                if rank_distribution:
                    rank_text = ""
                    for rank, count in sorted(rank_distribution.items(), key=lambda x: x[1], reverse=True):
                        rank_text += f"**{rank}:** {count}\n"

                    embed.add_field(
                        name="Rank Distribution",
                        value=rank_text,
                        inline=True
                    )

            # Add admin info
            embed.set_footer(
                text=f"Requested by {interaction.user.display_name} • Heavenly Demon Sect",
                icon_url=interaction.user.avatar.url if interaction.user.avatar else None
            )

            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"✅ Role analysis completed for {role.name} by {interaction.user.display_name}")

        except Exception as e:
            logger.error(f"❌ Error in checkrole command: {e}")
            embed = create_error_embed(
                "Analysis Failed",
                "An unexpected error occurred during role analysis.",
                "Please try again or contact technical support if the issue persists."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @bot.tree.command(name='setchannel', description='Set the notification channel for rank promotions (Admin only)')
    @app_commands.describe(channel='The channel to send promotion notifications to')
    @app_commands.default_permissions(administrator=True)
    async def set_notification_channel(interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the notification channel for rank promotions"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Check if bot has permissions to send messages in the channel
            if not channel.permissions_for(interaction.guild.me).send_messages:
                embed = create_error_embed(
                    "Permission Error",
                    f"The bot does not have permission to send messages in {channel.mention}.",
                    "Please grant the bot 'Send Messages' permission in that channel."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Store the channel preference in the database
            success = await role_reward_manager.leaderboard_manager.set_guild_config(
                interaction.guild.id, 'notification_channel', channel.id
            )
            
            if success:
                embed = create_success_embed(
                    "Notification Channel Set",
                    f"Rank promotion notifications will now be sent to {channel.mention}.",
                    fields=[
                        {
                            "name": "Channel",
                            "value": f"{channel.name} ({channel.id})",
                            "inline": True
                        },
                        {
                            "name": "Permissions",
                            "value": "Bot can send messages",
                            "inline": True
                        }
                    ]
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(f"Set notification channel to {channel.name} for guild {interaction.guild.name}")
            else:
                embed = create_error_embed(
                    "Configuration Failed",
                    "Failed to save the notification channel setting.",
                    "Please try again or contact support."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error setting notification channel: {e}")
            embed = create_error_embed(
                "Command Error",
                "An error occurred while setting the notification channel.",
                "Please try again later."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @bot.tree.command(name='removepoints', description='Remove contribution points from a user (Admin only)')
    @app_commands.describe(
        user='The user to remove points from',
        points='Number of points to remove (positive number)'
    )
    @app_commands.default_permissions(administrator=True)
    async def remove_points(interaction: discord.Interaction, user: discord.Member, points: int):
        """Remove points from a user (convenience command for negative point assignment)"""
        try:
            if user.bot:
                embed = create_error_embed(
                    "Invalid Target",
                    "Cannot remove points from bot users.",
                    "Please select a human member."
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Validate points
            if points <= 0:
                embed = create_error_embed(
                    "Invalid Points",
                    "Points to remove must be a positive number.",
                    "Use a positive number to specify how many points to remove."
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
                
            if points > 10000:
                embed = create_error_embed(
                    "Invalid Points",
                    "Cannot remove more than 10,000 points at once.",
                    "Please use a smaller number."
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Get current points
            current_stats = await role_reward_manager.leaderboard_manager.get_user_stats(interaction.guild.id, user.id)
            old_points = current_stats['points'] if current_stats else 0
            
            # Remove points (convert to negative)
            success = await role_reward_manager.leaderboard_manager.update_points(
                interaction.guild.id, user.id, -points, user.display_name
            )
            
            if success:
                # Get updated stats
                updated_stats = await role_reward_manager.leaderboard_manager.get_user_stats(interaction.guild.id, user.id)
                new_points = updated_stats['points'] if updated_stats else 0
                
                # Create success embed
                embed = create_success_embed(
                    "Points Removed",
                    f"Successfully removed {points:,} points from {user.display_name}",
                    fields=[
                        {
                            "name": "Previous Points",
                            "value": f"{old_points:,}",
                            "inline": True
                        },
                        {
                            "name": "Points Removed",
                            "value": f"{points:,}",
                            "inline": True
                        },
                        {
                            "name": "New Total",
                            "value": f"{new_points:,}",
                            "inline": True
                        }
                    ]
                )
                
                await interaction.response.send_message(embed=embed)
                
                # Update all active leaderboard views
                await role_reward_manager.trigger_leaderboard_updates(interaction.guild.id)
                
                logger.info(f"{interaction.user.display_name} removed {points} points from {user.display_name}")
                
            else:
                embed = create_error_embed(
                    "Removal Failed",
                    "Failed to remove points. Please try again.",
                    "Make sure the user is in the leaderboard system."
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in remove_points command: {e}")
            embed = create_error_embed(
                "Command Error",
                "An error occurred while removing points.",
                "Please try again later."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    logger.info("✅ Role management commands registered successfully")
