import json
import os
import asyncio
from datetime import datetime
import logging
import asyncpg
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class LeaderboardManager:
    """Enhanced leaderboard manager with improved error handling and logging"""
    
    def __init__(self, database_url=None):
        self.database_url = database_url or os.getenv('DATABASE_URL')
        self.pool = None
        
    async def initialize_db(self):
        """Initialize database connection with enhanced error handling"""
        if not self.database_url:
            logger.error("❌ No DATABASE_URL provided. Please set the DATABASE_URL environment variable.")
            return False
            
        try:
            # Parse database URL to log connection info (without password)
            parsed = urlparse(self.database_url)
            logger.info(f"🔗 Connecting to database: {parsed.hostname}:{parsed.port}/{parsed.path[1:]}")
            
            # Create connection pool with enhanced settings
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,
                max_size=10,
                command_timeout=30,
                server_settings={'jit': 'off'}  # Disable JIT for better compatibility
            )
            
            await self.create_tables()
            logger.info("✅ Database initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error initializing database: {e}")
            return False
    
    async def create_tables(self):
        """Create necessary tables with enhanced schema"""
        async with self.pool.acquire() as conn:
            # Create leaderboard table with enhanced constraints
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS leaderboard (
                    guild_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    username VARCHAR(255) NOT NULL,
                    points INTEGER DEFAULT 0 CHECK (points >= 0),
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, user_id)
                )
            ''')
            
            # Create user profiles table for customization
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_profiles (
                    guild_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    custom_title VARCHAR(100),
                    status_message VARCHAR(200),
                    preferred_color VARCHAR(7) DEFAULT '#2C3E50',
                    notification_dm BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, user_id),
                    FOREIGN KEY (guild_id, user_id) REFERENCES leaderboard(guild_id, user_id)
                )
            ''')
            
            # Create indexes for better performance
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_leaderboard_guild_points 
                ON leaderboard (guild_id, points DESC)
            ''')
            
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_leaderboard_username 
                ON leaderboard (guild_id, username)
            ''')
            
            # Create trigger to automatically update last_updated
            await conn.execute('''
                CREATE OR REPLACE FUNCTION update_last_updated()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.last_updated = CURRENT_TIMESTAMP;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            ''')
            
            await conn.execute('''
                DROP TRIGGER IF EXISTS update_leaderboard_timestamp ON leaderboard;
                CREATE TRIGGER update_leaderboard_timestamp
                    BEFORE UPDATE ON leaderboard
                    FOR EACH ROW
                    EXECUTE FUNCTION update_last_updated();
            ''')
            
            # Create index for user profiles
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_user_profiles_guild_user 
                ON user_profiles (guild_id, user_id)
            ''')
            
            # Create guild configuration table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS guild_config (
                    guild_id BIGINT NOT NULL,
                    config_key VARCHAR(100) NOT NULL,
                    config_value TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, config_key)
                )
            ''')
            
            # Create index for guild config
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_guild_config_guild_key 
                ON guild_config (guild_id, config_key)
            ''')
            
            logger.info("✅ Database tables and indexes created successfully")
    
    async def initialize_guild(self, guild):
        """Initialize leaderboard for a guild with enhanced logging"""
        if not self.pool:
            logger.error("❌ Database not initialized")
            return
            
        guild_id = guild.id
        logger.info(f"🔄 Initializing leaderboard for guild: {guild.name} (ID: {guild_id})")
        
        # Add all current members to leaderboard
        non_bot_members = [member for member in guild.members if not member.bot]
        
        for member in non_bot_members:
            await self.add_member(guild_id, member.id, member.display_name)
        
        logger.info(f"✅ Initialized leaderboard for guild {guild.name} with {len(non_bot_members)} members")
    
    async def add_member(self, guild_id, user_id, username):
        """Add a member to the leaderboard with enhanced error handling"""
        if not self.pool:
            logger.error("❌ Database not initialized")
            return
            
        try:
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO leaderboard (guild_id, user_id, username, points, last_updated, created_at)
                    VALUES ($1, $2, $3, 0, $4, $4)
                    ON CONFLICT (guild_id, user_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        last_updated = EXCLUDED.last_updated
                ''', guild_id, user_id, username[:255], datetime.now())  # Truncate username if too long
                
            logger.debug(f"✅ Added/updated member {username} to leaderboard for guild {guild_id}")
            
        except Exception as e:
            logger.error(f"❌ Error adding member {username} to leaderboard: {e}")
    
    async def remove_member(self, guild_id, user_id):
        """Remove a member from the leaderboard with enhanced logging"""
        if not self.pool:
            logger.error("❌ Database not initialized")
            return
            
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute('''
                    DELETE FROM leaderboard 
                    WHERE guild_id = $1 AND user_id = $2
                ''', guild_id, user_id)
                
            if result == "DELETE 1":
                logger.info(f"✅ Removed member from leaderboard for guild {guild_id}")
            else:
                logger.warning(f"⚠️ Member not found in leaderboard for removal (guild: {guild_id}, user: {user_id})")
                
        except Exception as e:
            logger.error(f"❌ Error removing member from leaderboard: {e}")
    
    async def update_points(self, guild_id, user_id, points_change, username=None, bot=None):
        """Update points for a user with enhanced validation and logging"""
        if not self.pool:
            logger.error("❌ Database not initialized")
            return False
            
        try:
            async with self.pool.acquire() as conn:
                # Start transaction for consistency
                async with conn.transaction():
                    # Ensure user exists if username provided
                    if username:
                        await conn.execute('''
                            INSERT INTO leaderboard (guild_id, user_id, username, points, last_updated, created_at)
                            VALUES ($1, $2, $3, 0, $4, $4)
                            ON CONFLICT (guild_id, user_id) DO UPDATE SET
                                username = EXCLUDED.username
                        ''', guild_id, user_id, username[:255], datetime.now())
                    
                    # Get current points to validate the update
                    current_points = await conn.fetchval('''
                        SELECT points FROM leaderboard 
                        WHERE guild_id = $1 AND user_id = $2
                    ''', guild_id, user_id)
                    
                    if current_points is None:
                        logger.warning(f"⚠️ User {user_id} not found in leaderboard for guild {guild_id}")
                        return False
                    
                    # Validate that points won't go negative
                    new_points = current_points + points_change
                    if new_points < 0:
                        logger.warning(f"⚠️ Points update would result in negative points for user {user_id}")
                        new_points = 0
                        points_change = -current_points
                    
                    # Update points
                    result = await conn.execute('''
                        UPDATE leaderboard 
                        SET points = $3, last_updated = $4
                        WHERE guild_id = $1 AND user_id = $2
                    ''', guild_id, user_id, new_points, datetime.now())
                    
                    if result == "UPDATE 0":
                        logger.warning(f"⚠️ No rows updated for user {user_id} in guild {guild_id}")
                        return False
                    
                    # Get updated info for logging
                    row = await conn.fetchrow('''
                        SELECT username, points FROM leaderboard 
                        WHERE guild_id = $1 AND user_id = $2
                    ''', guild_id, user_id)
                    
                    if row:
                        logger.info(f"✅ Updated contribution for {row['username']}: {points_change:+d} points (Total: {row['points']})")
                    
                    return True
                    
        except Exception as e:
            logger.error(f"❌ Error updating points for user {user_id}: {e}")
            return False
    
    def get_leaderboard(self, guild_id, page=1, per_page=10):
        """Get leaderboard data with enhanced pagination"""
        return asyncio.create_task(self._get_leaderboard_async(guild_id, page, per_page))
    
    async def _get_leaderboard_async(self, guild_id, page=1, per_page=10):
        """Async version of get_leaderboard with enhanced error handling"""
        if not self.pool:
            logger.error("❌ Database not initialized")
            return [], 0, 0
            
        try:
            async with self.pool.acquire() as conn:
                # Get total count with better error handling
                total_members = await conn.fetchval('''
                    SELECT COUNT(*) FROM leaderboard 
                    WHERE guild_id = $1 AND points >= 0
                ''', guild_id)
                
                if total_members == 0:
                    logger.info(f"ℹ️ No members found in leaderboard for guild {guild_id}")
                    return [], 0, 0
                
                # Calculate pagination
                total_pages = max(1, (total_members + per_page - 1) // per_page)
                page = max(1, min(page, total_pages))  # Clamp page to valid range
                offset = (page - 1) * per_page
                
                # Get page data with enhanced query
                rows = await conn.fetch('''
                    SELECT user_id, username, points, last_updated,
                           ROW_NUMBER() OVER (ORDER BY points DESC, last_updated ASC) as rank
                    FROM leaderboard 
                    WHERE guild_id = $1 AND points >= 0
                    ORDER BY points DESC, last_updated ASC
                    LIMIT $2 OFFSET $3
                ''', guild_id, per_page, offset)
                
                # Format leaderboard data
                leaderboard = []
                for row in rows:
                    leaderboard.append({
                        'rank': row['rank'],
                        'user_id': str(row['user_id']),
                        'username': row['username'],
                        'points': row['points'],
                        'last_updated': row['last_updated'].isoformat() if row['last_updated'] else None
                    })
                
                logger.debug(f"✅ Retrieved leaderboard page {page}/{total_pages} for guild {guild_id}")
                return leaderboard, page, total_pages
                
        except Exception as e:
            logger.error(f"❌ Error getting leaderboard for guild {guild_id}: {e}")
            return [], 0, 0
    
    async def get_user_stats(self, guild_id, user_id):
        """Get statistics for a specific user with enhanced error handling"""
        if not self.pool:
            logger.error("❌ Database not initialized")
            return None
            
        try:
            async with self.pool.acquire() as conn:
                # Get user stats with rank
                row = await conn.fetchrow('''
                    SELECT username, points, last_updated, created_at,
                           ROW_NUMBER() OVER (ORDER BY points DESC, last_updated ASC) as rank
                    FROM leaderboard 
                    WHERE guild_id = $1 AND user_id = $2
                ''', guild_id, user_id)
                
                if not row:
                    logger.warning(f"⚠️ User {user_id} not found in leaderboard for guild {guild_id}")
                    return None
                
                return {
                    'username': row['username'],
                    'points': row['points'],
                    'rank': row['rank'],
                    'last_updated': row['last_updated'].isoformat() if row['last_updated'] else None,
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None
                }
                
        except Exception as e:
            logger.error(f"❌ Error getting user stats for {user_id}: {e}")
            return None
    
    async def get_user_profile(self, guild_id, user_id):
        """Get user profile customization data"""
        if not self.pool:
            logger.error("❌ Database not initialized")
            return None
            
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow('''
                    SELECT custom_title, status_message, preferred_color, notification_dm
                    FROM user_profiles 
                    WHERE guild_id = $1 AND user_id = $2
                ''', guild_id, user_id)
                
                if row:
                    return {
                        'custom_title': row['custom_title'],
                        'status_message': row['status_message'],
                        'preferred_color': row['preferred_color'],
                        'notification_dm': row['notification_dm']
                    }
                
                return None
                
        except Exception as e:
            logger.error(f"❌ Error getting user profile for {user_id}: {e}")
            return None
    
    async def update_user_profile(self, guild_id, user_id, **kwargs):
        """Update user profile customization"""
        if not self.pool:
            logger.error("❌ Database not initialized")
            return False
            
        try:
            async with self.pool.acquire() as conn:
                # First ensure user exists in leaderboard
                user_exists = await conn.fetchval('''
                    SELECT 1 FROM leaderboard WHERE guild_id = $1 AND user_id = $2
                ''', guild_id, user_id)
                
                if not user_exists:
                    logger.warning(f"⚠️ Cannot update profile for user {user_id} - not in leaderboard")
                    return False
                
                # Build update query dynamically
                update_fields = []
                values = [guild_id, user_id]
                param_count = 2
                
                for field, value in kwargs.items():
                    if field in ['custom_title', 'status_message', 'preferred_color', 'notification_dm']:
                        param_count += 1
                        update_fields.append(f"{field} = ${param_count}")
                        values.append(value)
                
                if not update_fields:
                    return False
                
                # Add updated_at
                param_count += 1
                update_fields.append(f"updated_at = ${param_count}")
                values.append(datetime.now())
                
                query = f'''
                    INSERT INTO user_profiles (guild_id, user_id, {', '.join(kwargs.keys())}, updated_at)
                    VALUES ($1, $2, {', '.join(f'${i+3}' for i in range(len(kwargs)))}, ${param_count})
                    ON CONFLICT (guild_id, user_id) DO UPDATE SET
                        {', '.join(update_fields)}
                '''
                
                await conn.execute(query, *values)
                logger.info(f"✅ Updated profile for user {user_id} in guild {guild_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error updating user profile: {e}")
            return False
    
    async def search_users(self, guild_id, query):
        """Search users by username with enhanced error handling"""
        if not self.pool:
            logger.error("❌ Database not initialized")
            return []
            
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT user_id, username, points, last_updated,
                           ROW_NUMBER() OVER (ORDER BY points DESC, last_updated ASC) as rank
                    FROM leaderboard 
                    WHERE guild_id = $1 AND username ILIKE $2
                    ORDER BY points DESC, last_updated ASC
                    LIMIT 50
                ''', guild_id, f'%{query}%')
                
                results = []
                for row in rows:
                    results.append({
                        'rank': row['rank'],
                        'user_id': str(row['user_id']),
                        'username': row['username'],
                        'points': row['points'],
                        'last_updated': row['last_updated'].isoformat() if row['last_updated'] else None
                    })
                
                logger.info(f"✅ Found {len(results)} users matching '{query}' in guild {guild_id}")
                return results
                
        except Exception as e:
            logger.error(f"❌ Error searching users: {e}")
            return []
    
    async def get_guild_stats(self, guild_id):
        """Get comprehensive guild statistics"""
        if not self.pool:
            logger.error("❌ Database not initialized")
            return None
            
        try:
            async with self.pool.acquire() as conn:
                # Get basic stats
                basic_stats = await conn.fetchrow('''
                    SELECT COUNT(*) as total_members,
                           COALESCE(SUM(points), 0) as total_points,
                           COALESCE(AVG(points), 0) as avg_points,
                           COALESCE(MAX(points), 0) as max_points
                    FROM leaderboard 
                    WHERE guild_id = $1
                ''', guild_id)
                
                # Get rank distribution
                rank_stats = await conn.fetch('''
                    SELECT points, username FROM leaderboard 
                    WHERE guild_id = $1 
                    ORDER BY points DESC
                ''', guild_id)
                
                return {
                    'total_members': basic_stats['total_members'],
                    'total_points': basic_stats['total_points'],
                    'avg_points': float(basic_stats['avg_points']),
                    'max_points': basic_stats['max_points'],
                    'rank_distribution': rank_stats
                }
                
        except Exception as e:
            logger.error(f"❌ Error getting guild stats: {e}")
            return None
    
    async def cleanup_old_data(self, days_old=90):
        """Cleanup old inactive data"""
        if not self.pool:
            logger.error("❌ Database not initialized")
            return
            
        try:
            async with self.pool.acquire() as conn:
                cutoff_date = datetime.now() - timedelta(days=days_old)
                
                result = await conn.execute('''
                    DELETE FROM leaderboard 
                    WHERE last_updated < $1 AND points = 0
                ''', cutoff_date)
                
                logger.info(f"✅ Cleanup completed - removed old inactive records")
                
        except Exception as e:
            logger.error(f"❌ Error during cleanup: {e}")
    
    async def set_guild_config(self, guild_id, config_key, config_value):
        """Set a guild configuration value"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO guild_config (guild_id, config_key, config_value, updated_at)
                    VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
                    ON CONFLICT (guild_id, config_key)
                    DO UPDATE SET config_value = $3, updated_at = CURRENT_TIMESTAMP
                ''', guild_id, config_key, str(config_value))
                return True
        except Exception as e:
            logger.error(f"Error setting guild config: {e}")
            return False
    
    async def get_guild_config(self, guild_id, config_key, default_value=None):
        """Get a guild configuration value"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchval('''
                    SELECT config_value FROM guild_config
                    WHERE guild_id = $1 AND config_key = $2
                ''', guild_id, config_key)
                
                if result is not None:
                    # Try to convert back to int if it looks like a number
                    if result.isdigit():
                        return int(result)
                    return result
                return default_value
        except Exception as e:
            logger.error(f"Error getting guild config: {e}")
            return default_value

    async def close(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("✅ Database connection pool closed")
