import discord
import logging
from datetime import datetime
import math

logger = logging.getLogger(__name__)


# Enhanced color palette for professional appearance
class Colors:
    PRIMARY = 0x2C3E50  # Dark blue-gray
    SECONDARY = 0x3498DB  # Blue
    SUCCESS = 0x27AE60  # Green
    WARNING = 0xF39C12  # Orange
    ERROR = 0xE74C3C  # Red
    INFO = 0x9B59B6  # Purple
    GOLD = 0xF1C40F  # Gold for top ranks
    SILVER = 0xBDC3C7  # Silver for second place
    BRONZE = 0xD35400  # Bronze for third place
    GRADIENT_START = 0x667eea  # Gradient colors
    GRADIENT_END = 0x764ba2
    RANK_COLORS = {
        "Demon God": 0x36393F,  # Gray (from screenshot)
        "Heavenly Demon": 0x4B0082,  # Purple/Indigo (from screenshot)
        "Supreme Demon": 0xE74C3C,  # Red (from screenshot)
        "Guardian": 0x3498DB,  # Blue (from screenshot)
        "Demon Council": 0x9B59B6,  # Purple (from screenshot)
        "Young Master": 0x3498DB,  # Blue (from screenshot)
        "Core Disciple": 0xF1C40F,  # Yellow (from screenshot - Hermes role)
        "Inner Disciple": 0x3498DB,  # Blue (similar to other roles)
        "Outer Disciple": 0x95A5A6,  # Light gray
        "Servant": 0x7F8C8D  # Dark gray
    }


def get_rank_title_by_points(points, member=None):
    """Get rank title based on contribution points and member roles"""
    if member:
        # Check for special roles that override contribution requirements
        special_roles = {
            1266143259801948261: "Demon God",
            1281115906717650985: "Heavenly Demon",
            1276607675735736452: "Guardian",
            1304283446016868424: "Supreme Demon",
            1266242655642456074: "Demon Council",
            1390279781827874937: "Young Master"
        }

        # Check if member has any special roles (highest priority first)
        for role in member.roles:
            if role.id in special_roles:
                return special_roles[role.id]

        # Define role requirements for each rank
        rank_roles = {
            "Core Disciple":
            [1391059979167072286, 1391060071189971075, 1382602945752727613],
            "Inner Disciple":
            [1268528848740290580, 1308823860740624384, 1391059841505689680],
            "Outer Disciple":
            [1389474689818296370, 1266826177163694181, 1308823565881184348]
        }

        # Check for Core Disciple (requires 750+ points AND specific role)
        if points >= 750:
            user_has_core_role = any(role.id in rank_roles["Core Disciple"]
                                     for role in member.roles)
            if user_has_core_role:
                return "Core Disciple"

        # Check for Inner Disciple (requires 350-750 points AND specific role)
        if points >= 350:
            user_has_inner_role = any(role.id in rank_roles["Inner Disciple"]
                                      for role in member.roles)
            if user_has_inner_role:
                return "Inner Disciple"

        # Check for Outer Disciple (requires 10-349 points AND specific role)
        if points >= 10:
            user_has_outer_role = any(role.id in rank_roles["Outer Disciple"]
                                      for role in member.roles)
            if user_has_outer_role:
                return "Outer Disciple"

        # Servant (less than 10 points, no role requirement)
        if points < 10:
            return "Servant"

        # If no matching role found, return based on points only (fallback)
        if points >= 750:
            return "Inner Disciple"
        elif points >= 350:
            return "Inner Disciple"
        elif points >= 10:
            return "Outer Disciple"
        else:
            return "Servant"

    # Standard point-based ranks (when no member object available)
    if points >= 750:
        return "Inner Disciple"
    elif points >= 350:
        return "Inner Disciple"
    elif points >= 10:
        return "Outer Disciple"
    else:
        return "Servant"


def get_rank_color(rank_title):
    """Get color for specific rank"""
    return Colors.RANK_COLORS.get(rank_title, Colors.PRIMARY)


def get_next_rank_info(points, member=None):
    """Get information about the next rank advancement"""
    current_rank = get_rank_title_by_points(points, member)

    # Define rank progression with point thresholds
    rank_progression = [("Servant", 0), ("Outer Disciple", 10),
                        ("Inner Disciple", 350), ("Core Disciple", 750)]

    # Special roles don't have point-based progression
    special_ranks = [
        "Demon God", "Heavenly Demon", "Guardian", "Supreme Demon",
        "Demon Council", "Young Master"
    ]

    if current_rank in special_ranks:
        return current_rank, None, None

    # Find current rank in progression
    for i, (rank_name, threshold) in enumerate(rank_progression):
        if current_rank == rank_name:
            # Check if there's a next rank
            if i + 1 < len(rank_progression):
                next_rank_name, next_threshold = rank_progression[i + 1]
                return current_rank, next_threshold, next_rank_name
            else:
                # Already at highest point-based rank
                return current_rank, None, None

    # Fallback - shouldn't happen normally
    return current_rank, None, None


def get_status_message_by_points(points, member=None):
    """Get appropriate status message based on points and rank"""
    rank_title = get_rank_title_by_points(points, member)

    # Custom messages for different point ranges and ranks
    if rank_title in [
            "Demon God", "Heavenly Demon", "Guardian", "Supreme Demon",
            "Demon Council", "Young Master"
    ]:
        return f"You hold the prestigious rank of {rank_title}. Your authority in the sect is unquestionable."
    elif rank_title == "Core Disciple":
        if points >= 1500:
            return "You are a distinguished Core Disciple with exceptional contributions to the sect."
        elif points >= 1000:
            return "Your dedication as a Core Disciple is evident through your substantial contributions."
        else:
            return "You have achieved Core Disciple status. Continue your cultivation journey."
    elif rank_title == "Inner Disciple":
        if points >= 500:
            return "You are approaching Core Disciple status. Your progress is commendable."
        else:
            return "As an Inner Disciple, you have proven your commitment to the sect."
    elif rank_title == "Outer Disciple":
        if points >= 200:
            return "You are making excellent progress toward Inner Disciple advancement."
        elif points >= 100:
            return "Your contributions are growing. Inner Disciple status awaits."
        else:
            return "You have begun your journey as an Outer Disciple. Keep contributing to advance."
    else:  # Servant
        return "Begin your cultivation journey by contributing to the sect to advance your rank."


async def get_total_guild_points(leaderboard_manager, guild_id):
    """Get total contribution points for all members in the guild"""
    try:
        if not leaderboard_manager.pool:
            return 0

        async with leaderboard_manager.pool.acquire() as conn:
            result = await conn.fetchval(
                '''
                SELECT COALESCE(SUM(points), 0) FROM leaderboard WHERE guild_id = $1
            ''', guild_id)
            return result or 0
    except Exception as e:
        logger.error(f"Error getting total guild points: {e}")
        return 0


def create_enhanced_divider():
    """Create a visual divider for embeds"""
    return "═" * 40


def format_large_number(number):
    """Format large numbers with appropriate suffixes"""
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    elif number >= 1_000:
        return f"{number / 1_000:.1f}K"
    else:
        return str(number)


def create_leaderboard_embeds(leaderboard_data,
                              guild_name,
                              guild=None,
                              total_guild_points=None,
                              search_query=None):
    """Backward compatibility wrapper - now creates single embed for pagination"""
    return [
        create_leaderboard_embed(leaderboard_data, 1, 1, guild_name, guild,
                                 total_guild_points, search_query)
    ]


def create_leaderboard_embed(leaderboard_data,
                             current_page,
                             total_pages,
                             guild_name,
                             guild=None,
                             total_guild_points=None):
    """Create a single leaderboard embed with enhanced pagination (50 members per page)"""
    embed = discord.Embed(title=f"Heavenly Demon Sect Leaderboard",
                          color=Colors.PRIMARY,
                          timestamp=datetime.now())

    if not leaderboard_data:
        embed.add_field(
            name="No Data Available",
            value=
            "The leaderboard is currently empty.\nMembers will appear here as they gain contribution points.",
            inline=False)
        return embed

    # Enhanced header with guild info
    header_text = f"**Cultivation Leaderboard**\n"
    header_text += f"{guild_name}\n"
    if total_guild_points:
        header_text += f"Total Sect Contribution: **{format_large_number(total_guild_points)}**\n"
    header_text += f"Page {current_page} of {total_pages} • Showing up the members of heavenly demon sect."

    embed.description = header_text

    # Create rankings with enhanced formatting - split into multiple fields if needed
    rankings_texts = [""]
    current_field = 0

    for i, member in enumerate(leaderboard_data):
        rank = member['rank']
        username = member['username']
        points = member['points']

        # Get Discord member for role-based rank
        discord_member = None
        if guild:
            try:
                discord_member = guild.get_member(int(member['user_id']))
            except:
                pass

        # Get rank title
        rank_title = get_rank_title_by_points(points, discord_member)

        # Create compact ranking entry
        username_display = username[:12] + "..." if len(
            username) > 12 else username

        # Get ordinal suffix for rank
        if rank == 1:
            rank_display = "1st"
        elif rank == 2:
            rank_display = "2nd"
        elif rank == 3:
            rank_display = "3rd"
        else:
            rank_display = f"{rank}th"

        # Format entry - very compact to fit more
        entry = f"{rank_display} {username_display} - {points:,} pts • {rank_title}\n"

        # Check if adding this entry would exceed field limit
        if len(rankings_texts[current_field] +
               entry) > 950:  # Stay well under 1024
            # Start new field
            rankings_texts.append(entry)
            current_field += 1
        else:
            rankings_texts[current_field] += entry

        # Safety check for Discord's 25 field limit
        if current_field >= 20:  # Leave room for stats field
            break

    # Add ranking fields to embed
    for field_idx, rankings_text in enumerate(rankings_texts):
        if rankings_text.strip():  # Only add non-empty fields
            embed.add_field(
                name="\u200b",  # Zero-width space for empty field name
                value=rankings_text,
                inline=False)

    # Add statistics
    page_total = sum(member['points'] for member in leaderboard_data)
    stats_text = f"**Page Total:** {format_large_number(page_total)}\n"
    stats_text += f"**Page:** {current_page}/{total_pages}\n"
    stats_text += f"**Members on Page:** {len(leaderboard_data)}"

    embed.add_field(name="Statistics", value=stats_text, inline=True)

    # Enhanced footer
    embed.set_footer(
        text=
        f"Heavenly Demon Sect • Page {current_page}/{total_pages} • Use buttons to navigate"
    )

    return embed


def create_user_stats_embed(user, stats, guild_name, profile=None):
    """Create an enhanced user statistics embed with profile customization"""
    rank_title = get_rank_title_by_points(stats['points'], user)

    # Use custom color if available, otherwise use rank color
    if profile and profile.get('preferred_color'):
        try:
            embed_color = int(profile['preferred_color'].replace('#', ''), 16)
        except:
            embed_color = get_rank_color(rank_title)
    else:
        embed_color = get_rank_color(rank_title)

    # Use custom title if available
    title_text = f"{user.display_name}'s Cultivation Profile"
    if profile and profile.get('custom_title'):
        title_text = f"{profile['custom_title']} - {user.display_name}"

    embed = discord.Embed(title=title_text,
                          color=embed_color,
                          timestamp=datetime.now())

    # User avatar as thumbnail
    if user.avatar:
        embed.set_thumbnail(url=user.avatar.url)

    # Main stats section
    stats_text = f"**Contribution Points:** {format_large_number(stats['points'])}\n"
    stats_text += f"**Current Rank:** {rank_title}\n"
    stats_text += f"**Member Since:** {stats['last_updated'][:10]}"

    embed.add_field(name="Cultivation Status", value=stats_text, inline=False)

    # Add custom status message if available
    if profile and profile.get('status_message'):
        embed.add_field(name="Personal Motto",
                        value=f"*{profile['status_message']}*",
                        inline=False)

    # Progress section with improved logic
    current_rank_name, next_threshold, next_rank = get_next_rank_info(
        stats['points'], user)

    if next_threshold:
        points_needed = next_threshold - stats['points']
        progress_percentage = (stats['points'] / next_threshold) * 100
        progress_bar = create_enhanced_progress_bar(stats['points'],
                                                    next_threshold)

        progress_text = f"**Next Rank:** {next_rank}\n"
        progress_text += f"**Points Needed:** {points_needed}\n"
        progress_text += f"**Progress:** {progress_percentage:.1f}%\n"
        progress_text += f"{progress_bar}"

        embed.add_field(name="Advancement Progress",
                        value=progress_text,
                        inline=False)
    else:
        # Use the new status message system instead of "pinnacle of power"
        status_message = get_status_message_by_points(stats['points'], user)
        embed.add_field(name="Current Status",
                        value=status_message,
                        inline=False)

    # Footer
    embed.set_footer(text=f"Heavenly Demon Sect • {guild_name}",
                     icon_url=user.avatar.url if user.avatar else None)

    return embed


def create_enhanced_progress_bar(current, target, length=20):
    """Create an enhanced visual progress bar"""
    if target <= 0:
        return "█" * length

    progress = min(current / target, 1.0)
    filled = int(progress * length)
    empty = length - filled

    # Use different characters for a more modern look
    filled_char = "█"
    empty_char = "░"

    bar = filled_char * filled + empty_char * empty
    percentage = int(progress * 100)

    return f"`{bar}` {percentage}%"


def create_success_embed(title, description, fields=None):
    """Create a standardized success embed"""
    embed = discord.Embed(title=title,
                          description=description,
                          color=Colors.SUCCESS,
                          timestamp=datetime.now())

    if fields:
        for field in fields:
            embed.add_field(name=field.get('name', 'Field'),
                            value=field.get('value', 'No value'),
                            inline=field.get('inline', False))

    return embed


def create_error_embed(title, description, suggestion=None):
    """Create a standardized error embed"""
    embed = discord.Embed(title=title,
                          description=description,
                          color=Colors.ERROR,
                          timestamp=datetime.now())

    if suggestion:
        embed.add_field(name="Suggestion", value=suggestion, inline=False)

    return embed


def create_info_embed(title, description, fields=None):
    """Create a standardized info embed"""
    embed = discord.Embed(title=title,
                          description=description,
                          color=Colors.INFO,
                          timestamp=datetime.now())

    if fields:
        for field in fields:
            embed.add_field(name=field.get('name', 'Field'),
                            value=field.get('value', 'No value'),
                            inline=field.get('inline', False))

    return embed


def create_warning_embed(title, description, fields=None):
    """Create a standardized warning embed"""
    embed = discord.Embed(title=title,
                          description=description,
                          color=Colors.WARNING,
                          timestamp=datetime.now())

    if fields:
        for field in fields:
            embed.add_field(name=field.get('name', 'Field'),
                            value=field.get('value', 'No value'),
                            inline=field.get('inline', False))

    return embed


def get_rank_emoji(rank):
    """Get emoji for rank (returns empty string since no emojis requested)"""
    return ""


def format_points_change(change):
    """Format points change with appropriate sign"""
    if change > 0:
        return f"+{change}"
    elif change < 0:
        return str(change)
    else:
        return "0"


def calculate_rank_progress(current_points, target_points):
    """Calculate progress percentage toward next rank"""
    if target_points <= 0:
        return 100
    return min((current_points / target_points) * 100, 100)


def get_user_rank_position(user_points, leaderboard_data):
    """Get user's position in leaderboard"""
    for i, member in enumerate(leaderboard_data):
        if member['points'] <= user_points:
            return i + 1
    return len(leaderboard_data) + 1


def truncate_text(text, max_length=50):
    """Truncate text to specified length with ellipsis"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def create_rank_distribution_text(rank_distribution):
    """Create formatted text for rank distribution"""
    if not rank_distribution:
        return "No rank data available"


def create_promotion_embed(member,
                           old_rank,
                           new_rank,
                           current_points,
                           role_received=None):
    """Create a clean promotion notification embed without emojis or code blocks"""
    # Use rank-specific color for better visual impact
    rank_color = get_rank_color(new_rank)

    embed = discord.Embed(
        title="RANK ADVANCEMENT",
        description=
        f"**{member.display_name}** has ascended to a new rank in the Heavenly Demon Sect!",
        color=rank_color,
        timestamp=datetime.now())

    # Add member avatar as thumbnail for better visual identification
    if member.avatar:
        embed.set_thumbnail(url=member.avatar.url)

    # Main promotion info with clean formatting
    promotion_info = f"**Previous Tier:** {old_rank}\n"
    promotion_info += f"**New Tier:** {new_rank}"

    embed.add_field(name="Rank Progression",
                    value=promotion_info,
                    inline=False)

    # Points and role information in a structured layout
    details_text = f"**Contribution Points:** {current_points:,}\n"
    if role_received:
        details_text += f"**New Rank:** {role_received.name}\n"
    details_text += f"**Disciple of HDS:** {member.guild.name}"

    embed.add_field(name="Details", value=details_text, inline=False)

    # Achievement message with clean formatting
    achievement_messages = {
        "Outer Disciple":
        "You have proven your dedication and begun your true cultivation journey.",
        "Inner Disciple":
        "Your commitment to the sect has been recognized. Greater opportunities await.",
        "Core Disciple":
        "You have achieved elite status within the sect. Your influence grows.",
        "Young Master":
        "Your exceptional talent has earned you a prestigious position.",
        "Demon Council":
        "You now hold authority over the sect's important decisions.",
        "Supreme Demon":
        "Your power and wisdom place you among the sect's highest ranks.",
        "Guardian":
        "You are entrusted with protecting the sect's most sacred secrets.",
        "Heavenly Demon":
        "You have reached the pinnacle of cultivation and authority.",
        "Demon God":
        "You transcend mortal limitations and command absolute respect."
    }

    achievement_text = achievement_messages.get(
        new_rank, "Your advancement brings honor to the Heavenly Demon Sect.")

    embed.add_field(name="Achievement Recognition",
                    value=achievement_text,
                    inline=False)

    # Add motivational footer message
    motivational_messages = [
        "Continue your cultivation journey!", "Your dedication is inspiring!",
        "The sect grows stronger with you!",
        "May your path lead to enlightenment!"
    ]

    import random
    footer_message = random.choice(motivational_messages)

    embed.set_footer(
        text=f"Heavenly Demon Sect • {footer_message}",
        icon_url=member.guild.icon.url if member.guild.icon else None)

    return embed

    distribution_text = ""
    for rank, count in sorted(rank_distribution.items(),
                              key=lambda x: x[1],
                              reverse=True):
        distribution_text += f"**{rank}:** {count} members\n"

    return distribution_text


def validate_points_input(points_str):
    """Validate points input and return integer or None"""
    try:
        points = int(points_str)
        if points < -10000 or points > 10000:
            return None
        return points
    except ValueError:
        return None


def format_datetime(dt):
    """Format datetime for display"""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt

    return dt.strftime('%Y-%m-%d %H:%M UTC')


def get_member_display_name(member):
    """Get appropriate display name for member"""
    if hasattr(member, 'display_name'):
        return member.display_name
    elif hasattr(member, 'name'):
        return member.name
    else:
        return str(member)
