import discord
import logging
from datetime import datetime, timedelta
import asyncio

logger = logging.getLogger(__name__)

class RoleRewardManager:
    """Enhanced role reward manager with improved logging and error handling"""

    def __init__(self, bot, leaderboard_manager):
        self.bot = bot
        self.leaderboard_manager = leaderboard_manager
        self.role_rewards = {}  # guild_id -> {role_id: points_per_interval}
        self.reward_intervals = {}  # guild_id -> interval_hours
        self.last_reward_time = {}  # guild_id -> {user_id: last_reward_datetime}
        self.active_tasks = {}  # guild_id -> asyncio.Task
        
        logger.info("✅ Role reward manager initialized")

    async def trigger_leaderboard_updates(self, guild_id):
        """Enhanced leaderboard update trigger with better error handling"""
        try:
            # Import here to avoid circular imports
            import bot.commands as commands_module

            guild_id = int(guild_id)
            logger.info(f"🔄 Triggering leaderboard updates for guild {guild_id}")

            # Find and update all active leaderboard views for this guild
            if hasattr(commands_module, 'active_leaderboard_views'):
                views_updated = 0
                failed_updates = 0
                
                for view in commands_module.active_leaderboard_views[:]:  # Create a copy to iterate safely
                    if view.guild_id == guild_id:
                        try:
                            await view.auto_update_leaderboard()
                            views_updated += 1
                            logger.debug(f"✅ Updated leaderboard view for guild {guild_id}")
                        except Exception as e:
                            logger.error(f"❌ Failed to update leaderboard view: {e}")
                            failed_updates += 1
                            # Remove failed view from active list
                            try:
                                commands_module.active_leaderboard_views.remove(view)
                            except ValueError:
                                pass  # Already removed

                logger.info(f"✅ Leaderboard updates complete for guild {guild_id} - Updated: {views_updated}, Failed: {failed_updates}")

                # Also trigger the update function directly
                await commands_module.update_active_leaderboards(guild_id)
            else:
                logger.warning("⚠️ No active_leaderboard_views found in commands module")

        except Exception as e:
            logger.error(f"❌ Error triggering leaderboard updates: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
    
    async def check_member_rank_eligibility(self, member, points):
        """Enhanced rank eligibility check with better logic"""
        try:
            from bot.utils import get_rank_title_by_points
            rank_title = get_rank_title_by_points(points, member)
            
            logger.debug(f"📊 Member {member.display_name} has {points} points and rank {rank_title}")
            return rank_title
            
        except Exception as e:
            logger.error(f"❌ Error checking rank eligibility for {member.display_name}: {e}")
            return "Unknown"

    async def setup_role_rewards(self, guild_id, role_rewards_config, interval_hours=24):
        """Setup automatic role rewards for a guild"""
        try:
            self.role_rewards[guild_id] = role_rewards_config
            self.reward_intervals[guild_id] = interval_hours
            
            # Start the reward task for this guild
            if guild_id in self.active_tasks:
                self.active_tasks[guild_id].cancel()
            
            self.active_tasks[guild_id] = asyncio.create_task(
                self._role_reward_loop(guild_id)
            )
            
            logger.info(f"✅ Role rewards configured for guild {guild_id} with {interval_hours}h interval")
            
        except Exception as e:
            logger.error(f"❌ Error setting up role rewards for guild {guild_id}: {e}")

    async def _role_reward_loop(self, guild_id):
        """Background task for distributing role rewards"""
        try:
            while True:
                await asyncio.sleep(self.reward_intervals.get(guild_id, 24) * 3600)  # Convert hours to seconds
                
                try:
                    await self._distribute_role_rewards(guild_id)
                except Exception as e:
                    logger.error(f"❌ Error in role reward distribution for guild {guild_id}: {e}")
                    
        except asyncio.CancelledError:
            logger.info(f"🛑 Role reward loop cancelled for guild {guild_id}")
        except Exception as e:
            logger.error(f"❌ Role reward loop error for guild {guild_id}: {e}")

    async def _distribute_role_rewards(self, guild_id):
        """Distribute rewards to members based on their roles"""
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                logger.error(f"❌ Guild {guild_id} not found for role rewards")
                return

            role_config = self.role_rewards.get(guild_id, {})
            if not role_config:
                logger.warning(f"⚠️ No role reward configuration for guild {guild_id}")
                return

            rewards_distributed = 0
            
            for member in guild.members:
                if member.bot:
                    continue
                
                # Check if member has any rewarded roles
                member_rewards = 0
                for role in member.roles:
                    if role.id in role_config:
                        member_rewards += role_config[role.id]
                
                if member_rewards > 0:
                    # Check if enough time has passed since last reward
                    last_reward = self.last_reward_time.get(guild_id, {}).get(member.id)
                    now = datetime.now()
                    
                    if last_reward is None or (now - last_reward).total_seconds() >= self.reward_intervals.get(guild_id, 24) * 3600:
                        # Get current points before update for rank progression check
                        current_stats = await self.leaderboard_manager.get_user_stats(guild_id, member.id)
                        old_points = current_stats['points'] if current_stats else 0

                        # Distribute reward
                        success = await self.leaderboard_manager.update_points(
                            guild_id, member.id, member_rewards, member.display_name
                        )
                        
                        if success:
                            # Update last reward time
                            if guild_id not in self.last_reward_time:
                                self.last_reward_time[guild_id] = {}
                            self.last_reward_time[guild_id][member.id] = now
                            
                            rewards_distributed += 1
                            logger.debug(f"✅ Distributed {member_rewards} points to {member.display_name}")

                            # Get updated points for rank progression check
                            updated_stats = await self.leaderboard_manager.get_user_stats(guild_id, member.id)
                            new_points = updated_stats['points'] if updated_stats else 0

                            # Import and call rank progression check
                            try:
                                from bot.commands import check_and_announce_rank_progression
                                await check_and_announce_rank_progression(
                                    self.bot, guild_id, member.id, old_points, new_points, member.display_name
                                )
                            except Exception as e:
                                logger.error(f"Error checking rank progression in role rewards: {e}")

            if rewards_distributed > 0:
                logger.info(f"✅ Distributed role rewards to {rewards_distributed} members in guild {guild_id}")
                # Trigger leaderboard updates
                await self.trigger_leaderboard_updates(guild_id)
            else:
                logger.debug(f"ℹ️ No role rewards distributed for guild {guild_id}")

        except Exception as e:
            logger.error(f"❌ Error distributing role rewards for guild {guild_id}: {e}")

    async def stop_role_rewards(self, guild_id):
        """Stop role rewards for a guild"""
        try:
            if guild_id in self.active_tasks:
                self.active_tasks[guild_id].cancel()
                del self.active_tasks[guild_id]
                logger.info(f"✅ Stopped role rewards for guild {guild_id}")
            
            # Clean up configuration
            if guild_id in self.role_rewards:
                del self.role_rewards[guild_id]
            if guild_id in self.reward_intervals:
                del self.reward_intervals[guild_id]
            if guild_id in self.last_reward_time:
                del self.last_reward_time[guild_id]
                
        except Exception as e:
            logger.error(f"❌ Error stopping role rewards for guild {guild_id}: {e}")

    async def get_role_reward_status(self, guild_id):
        """Get the current status of role rewards for a guild"""
        try:
            return {
                'active': guild_id in self.active_tasks,
                'role_rewards': self.role_rewards.get(guild_id, {}),
                'interval_hours': self.reward_intervals.get(guild_id, 24),
                'last_distribution': self.last_reward_time.get(guild_id, {})
            }
        except Exception as e:
            logger.error(f"❌ Error getting role reward status for guild {guild_id}: {e}")
            return None

    def __del__(self):
        """Cleanup when manager is destroyed"""
        try:
            for task in self.active_tasks.values():
                if not task.done():
                    task.cancel()
            logger.info("✅ Role reward manager cleanup completed")
        except Exception as e:
            logger.error(f"❌ Error during role reward manager cleanup: {e}")
