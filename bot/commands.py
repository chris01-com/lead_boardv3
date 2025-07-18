import discord
from discord.ext import commands
from discord import app_commands
import logging
from bot.utils import (
    create_leaderboard_embed, create_user_stats_embed, create_success_embed,
    create_error_embed, create_info_embed, Colors, get_total_guild_points
)
import asyncio

logger = logging.getLogger(__name__)

# Global list to track active leaderboard views
active_leaderboard_views = []

class LeaderboardView(discord.ui.View):
    """Enhanced leaderboard view with improved pagination and mystat functionality"""

    def __init__(self, guild_id, leaderboard_manager, per_page=50):
        super().__init__(timeout=None)  # No timeout
        self.guild_id = guild_id
        self.leaderboard_manager = leaderboard_manager
        self.per_page = per_page
        self.current_page = 1
        self.total_pages = 1
        self.leaderboard_data = []
        self.guild = None
        self.total_guild_points = 0
        self.is_active = True
        self.message = None  # Store message reference for auto-updates

        # Add to active views list
        active_leaderboard_views.append(self)

    async def fetch_leaderboard_data(self):
        """Fetch current leaderboard data"""
        try:
            self.leaderboard_data, self.current_page, self.total_pages = await self.leaderboard_manager._get_leaderboard_async(
                self.guild_id, self.current_page, self.per_page
            )

            # Get guild object for member data
            if hasattr(self.leaderboard_manager, 'bot'):
                self.guild = self.leaderboard_manager.bot.get_guild(self.guild_id)

            # Get total guild points
            self.total_guild_points = await get_total_guild_points(self.leaderboard_manager, self.guild_id)

            logger.debug(f"✅ Fetched leaderboard data for guild {self.guild_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Error fetching leaderboard data: {e}")
            return False

    async def update_embed(self, interaction):
        """Update the leaderboard embed"""
        try:
            guild_name = self.guild.name if self.guild else "Unknown Guild"
            embed = create_leaderboard_embed(
                self.leaderboard_data, 
                self.current_page, 
                self.total_pages, 
                guild_name,
                self.guild,
                self.total_guild_points
            )

            # Update button states
            self.update_button_states()

            await interaction.response.edit_message(embed=embed, view=self)

        except Exception as e:
            logger.error(f"❌ Error updating leaderboard embed: {e}")
            await interaction.response.send_message("An error occurred while updating the leaderboard.", ephemeral=True)

    def update_button_states(self):
        """Update button enabled/disabled states"""
        # Previous page button
        self.previous_page.disabled = (self.current_page <= 1)

        # Next page button
        self.next_page.disabled = (self.current_page >= self.total_pages)

    async def auto_update_leaderboard(self):
        """Auto-update leaderboard data without user interaction"""
        try:
            await self.fetch_leaderboard_data()

            # Get the original message and update it
            if hasattr(self, 'message') and self.message:
                try:
                    guild_name = self.guild.name if self.guild else "Unknown Guild"
                    embed = create_leaderboard_embed(
                        self.leaderboard_data, 
                        self.current_page, 
                        self.total_pages, 
                        guild_name,
                        self.guild,
                        self.total_guild_points
                    )

                    # Update button states
                    self.update_button_states()

                    await self.message.edit(embed=embed, view=self)
                    logger.debug(f"✅ Auto-updated leaderboard message for guild {self.guild_id}")

                except discord.NotFound:
                    # Message was deleted, mark view as inactive
                    self.is_active = False
                    self.cleanup_view()
                    logger.warning(f"Leaderboard message not found - view deactivated for guild {self.guild_id}")
                except discord.HTTPException as e:
                    if e.status == 404:
                        # Message not found
                        self.is_active = False
                        self.cleanup_view()
                        logger.warning(f"Leaderboard message not found - view deactivated for guild {self.guild_id}")
                    else:
                        logger.error(f"❌ HTTP error updating leaderboard message: {e}")
                except Exception as e:
                    logger.error(f"❌ Error updating leaderboard message: {e}")
            else:
                logger.debug(f"✅ Auto-updated leaderboard data for guild {self.guild_id}")

        except Exception as e:
            logger.error(f"❌ Error auto-updating leaderboard: {e}")

    @discord.ui.button(label='Previous', style=discord.ButtonStyle.secondary, emoji='◀️')
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page"""
        if self.current_page > 1:
            self.current_page -= 1
            await self.fetch_leaderboard_data()
            await self.update_embed(interaction)

    @discord.ui.button(label='My Stats', style=discord.ButtonStyle.primary, emoji='📊')
    async def my_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show user's personal statistics with fixed status messages"""
        try:
            user_stats = await self.leaderboard_manager.get_user_stats(self.guild_id, interaction.user.id)

            if not user_stats:
                embed = create_error_embed(
                    "Stats Not Found",
                    "You are not currently in the leaderboard.",
                    "Contribute to the sect to appear in the leaderboard!"
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Get user profile for customization
            profile = await self.leaderboard_manager.get_user_profile(self.guild_id, interaction.user.id)

            # Create enhanced stats embed with fixed status messages
            guild_name = self.guild.name if self.guild else "Unknown Guild"
            embed = create_user_stats_embed(interaction.user, user_stats, guild_name, profile)

            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info(f"✅ Displayed stats for {interaction.user.display_name}")

        except Exception as e:
            logger.error(f"❌ Error showing user stats: {e}")
            embed = create_error_embed(
                "Error",
                "An error occurred while retrieving your statistics.",
                "Please try again later."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label='Next', style=discord.ButtonStyle.secondary, emoji='▶️')
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page"""
        if self.current_page < self.total_pages:
            self.current_page += 1
            await self.fetch_leaderboard_data()
            await self.update_embed(interaction)

    async def on_timeout(self):
        """Handle view timeout"""
        try:
            # Remove from active views
            if self in active_leaderboard_views:
                active_leaderboard_views.remove(self)

            # Disable all buttons
            for item in self.children:
                item.disabled = True

            logger.debug(f"✅ Leaderboard view timed out for guild {self.guild_id}")

        except Exception as e:
            logger.error(f"❌ Error handling view timeout: {e}")

    def cleanup_view(self):
        """Cleanup view resources"""
        try:
            # Remove from active views
            if self in active_leaderboard_views:
                active_leaderboard_views.remove(self)

            # Disable all buttons
            for item in self.children:
                item.disabled = True

            self.stop()  # Stop listening for interactions

            logger.debug(f"✅ Leaderboard view cleaned up for guild {self.guild_id}")

        except Exception as e:
            logger.error(f"❌ Error cleaning up leaderboard view: {e}")

async def update_active_leaderboards(guild_id):
    """Update all active leaderboard views for a guild"""
    try:
        guild_id = int(guild_id)
        updated_count = 0

        for view in active_leaderboard_views[:]:  # Create a copy to iterate safely
            if view.guild_id == guild_id and view.is_active:
                try:
                    await view.auto_update_leaderboard()
                    updated_count += 1
                except Exception as e:
                    logger.error(f"❌ Failed to update leaderboard view: {e}")
                    # Remove failed view
                    try:
                        active_leaderboard_views.remove(view)
                    except ValueError:
                        pass

        if updated_count > 0:
            logger.info(f"✅ Updated {updated_count} active leaderboard views for guild {guild_id}")

    except Exception as e:
        logger.error(f"❌ Error updating active leaderboards: {e}")

async def check_and_announce_rank_progression(bot, guild_id, user_id, old_points, new_points, username):
    """Check if user has progressed to a new rank and announce it"""
    try:
        # This function can be used by other modules to check rank progression
        # For now, it's a placeholder that can be enhanced later
        logger.debug(f"Checking rank progression for {username}: {old_points} -> {new_points}")

    except Exception as e:
        logger.error(f"❌ Error checking rank progression: {e}")

def setup_commands(bot, leaderboard_manager):
    """Setup all leaderboard commands"""

    @bot.tree.command(name='leaderboard', description='View the Heavenly Demon Sect leaderboard')
    @app_commands.describe(page='Page number to view (default: 1)')
    async def leaderboard(interaction: discord.Interaction, page: int = 1):
        """Enhanced leaderboard command with pagination"""
        try:
            await interaction.response.defer()

            # Create and initialize view
            view = LeaderboardView(interaction.guild.id, leaderboard_manager)
            view.current_page = max(1, page)

            # Fetch initial data
            success = await view.fetch_leaderboard_data()
            if not success:
                embed = create_error_embed(
                    "Error",
                    "Failed to load leaderboard data.",
                    "Please try again later."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Create embed
            guild_name = interaction.guild.name
            embed = create_leaderboard_embed(
                view.leaderboard_data, 
                view.current_page, 
                view.total_pages, 
                guild_name,
                interaction.guild,
                view.total_guild_points
            )

            # Update button states
            view.update_button_states()

            # Store the message object for auto-updates
            message = await interaction.followup.send(embed=embed, view=view)
            view.message = message  # Store message for updates

            logger.info(f"✅ Displayed leaderboard for {interaction.user.display_name}")

        except Exception as e:
            logger.error(f"❌ Error in leaderboard command: {e}")
            embed = create_error_embed(
                "Command Error",
                "An error occurred while processing the leaderboard command.",
                "Please try again later."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @bot.tree.command(name='addpoints', description='Add contribution points to a user (Admin only)')
    @app_commands.describe(
        user='The user to add points to',
        points='Number of points to add (can be negative to subtract)'
    )
    @app_commands.default_permissions(administrator=True)
    async def add_points(interaction: discord.Interaction, user: discord.Member, points: int):
        """Enhanced add points command with better validation"""
        try:
            if user.bot:
                embed = create_error_embed(
                    "Invalid Target",
                    "Cannot add points to bot users.",
                    "Please select a human member."
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Validate points range
            if points < -10000 or points > 10000:
                embed = create_error_embed(
                    "Invalid Points",
                    "Points must be between -10,000 and 10,000.",
                    "Please enter a valid point amount."
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Get current points for rank progression check
            current_stats = await leaderboard_manager.get_user_stats(interaction.guild.id, user.id)
            old_points = current_stats['points'] if current_stats else 0

            # Update points
            success = await leaderboard_manager.update_points(
                interaction.guild.id, user.id, points, user.display_name
            )

            if success:
                # Get updated stats
                updated_stats = await leaderboard_manager.get_user_stats(interaction.guild.id, user.id)
                new_points = updated_stats['points'] if updated_stats else 0

                # Create success embed
                embed = create_success_embed(
                    "Points Updated",
                    f"Successfully {'added' if points > 0 else 'removed'} {abs(points)} points {'to' if points > 0 else 'from'} {user.display_name}",
                    fields=[
                        {
                            "name": "Previous Points",
                            "value": f"{old_points:,}",
                            "inline": True
                        },
                        {
                            "name": "Points Change",
                            "value": f"{points:+,}",
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
                await update_active_leaderboards(interaction.guild.id)

                # Check for rank progression
                await check_and_announce_rank_progression(
                    bot, interaction.guild.id, user.id, old_points, new_points, user.display_name
                )

                logger.info(f"✅ {interaction.user.display_name} added {points} points to {user.display_name}")

            else:
                embed = create_error_embed(
                    "Update Failed",
                    "Failed to update points. Please try again.",
                    "Make sure the user is in the leaderboard system."
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"❌ Error in add_points command: {e}")
            embed = create_error_embed(
                "Command Error",
                "An error occurred while updating points.",
                "Please try again later."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name='mystats', description='View your personal cultivation statistics')
    async def my_stats(interaction: discord.Interaction):
        """Enhanced personal stats command"""
        try:
            user_stats = await leaderboard_manager.get_user_stats(interaction.guild.id, interaction.user.id)

            if not user_stats:
                embed = create_error_embed(
                    "Stats Not Found",
                    "You are not currently in the leaderboard.",
                    "Contribute to the sect to appear in the leaderboard!"
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Get user profile for customization
            profile = await leaderboard_manager.get_user_profile(interaction.guild.id, interaction.user.id)

            # Create enhanced stats embed
            embed = create_user_stats_embed(interaction.user, user_stats, interaction.guild.name, profile)

            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info(f"✅ Displayed stats for {interaction.user.display_name}")

        except Exception as e:
            logger.error(f"❌ Error in mystats command: {e}")
            embed = create_error_embed(
                "Command Error",
                "An error occurred while retrieving your statistics.",
                "Please try again later."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name='search', description='Search for users in the leaderboard')
    @app_commands.describe(query='Username to search for')
    async def search_users(interaction: discord.Interaction, query: str):
        """Enhanced user search command"""
        try:
            if len(query) < 2:
                embed = create_error_embed(
                    "Invalid Search",
                    "Search query must be at least 2 characters long.",
                    "Please enter a longer search term."
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            await interaction.response.defer()

            # Search for users
            results = await leaderboard_manager.search_users(interaction.guild.id, query)

            if not results:
                embed = create_info_embed(
                    "No Results",
                    f"No users found matching '{query}'.",
                    fields=[
                        {
                            "name": "Suggestion",
                            "value": "Try a different search term or check the spelling.",
                            "inline": False
                        }
                    ]
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Create results embed
            embed = create_info_embed(
                "Search Results",
                f"Found {len(results)} user(s) matching '{query}'"
            )

            # Add results to embed
            results_text = ""
            for user in results[:10]:  # Limit to 10 results
                results_text += f"**{user['rank']}.** {user['username']} - {user['points']} points\n"

            if len(results) > 10:
                results_text += f"\n... and {len(results) - 10} more results"

            embed.add_field(
                name="Members Found",
                value=results_text,
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"✅ Search completed for '{query}' by {interaction.user.display_name}")

        except Exception as e:
            logger.error(f"❌ Error in search command: {e}")
            embed = create_error_embed(
                "Search Error",
                "An error occurred while searching for users.",
                "Please try again later."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    logger.info("✅ Leaderboard commands registered successfully")