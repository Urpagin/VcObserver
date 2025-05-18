# Name: vc_observer.py
# Date: 2025-04-17 (YYYY-MM-DD)
# Author: Urpagin
import asyncio
import json
import logging
import pathlib
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Optional

import discord
from discord import Client, Member, VoiceState, VoiceChannel, Interaction, Object, Guild, Embed
from discord.app_commands import CommandTree


class VcObserver:
    """
    Observes VCs (Voice Channels) and logs how much time members passed in which channels.
    """

    def __init__(self, bot: Client, tree: CommandTree[Client], filepath: pathlib.Path,
                 guild_ids: list[int] | None = None) -> None:
        """

        :param bot: The Discord bot instance.
        :param tree: To register slashcommands.
        :param filepath: The path/name of the **JSON** file where all the elapsed times will be saved.
        :param guild_ids: Specify a list of guild IDs to only monitor those servers.
        """
        if filepath.suffix.lower() != '.json':
            raise ValueError(f"Expected a .json file, got: {filepath.name}")

        self._bot = bot
        self._tree = tree
        self.filepath = filepath
        # Filter guilds.
        self._guild_ids = guild_ids if guild_ids else [g.id for g in bot.guilds]

        # Dict like so: { user_id: (voice_channel_id, time_connected_seconds), ... }
        self._connected_members: dict[int, tuple[int, datetime]] = dict()

        # The embed color for showing stats of a single member.
        self.EMBED_MEMBER_STATS_COLOR: int = 0x2ECC71  # green
        self.EMBED_LEADERBOARD_COLOR: int = 0x3498DB  # blue

        self._init_scan()
        self._register_events()

        # TODO: use logging instead of writing to stdout.
        logging.info("Registered VcObserver events! VcObserver is OBSERVING!")

    def _init_scan(self) -> None:
        """
        Runs once when an instance of `VcObserver` is initialised.
        Scans all voice channels for connected users and adds them to the `_connected_members` class attribute.

        This addresses the edge case where members were already connected before the bot started.
        """
        for g_id in self._guild_ids:
            guild: Guild | None = self._bot.get_guild(g_id)

            if guild is None:
                logging.warning(f"Guild {g_id} not in cache.")
                continue

            for vc in guild.voice_channels:
                for member in vc.members:
                    if member.bot:
                        continue  # Skip bots

                    logging.debug(f"User '{member.name}' was already in a VC before observing.")

                    self._connected_members[member.id] = (
                        vc.id,
                        datetime.now(timezone.utc)
                    )

    def _read_file(self) -> dict[str, dict[str, float]]:
        """Returns the parsed JSON contents of the `self.filepath` file."""
        # Ensure file exists with initial content.
        if not self.filepath.exists():
            self.filepath.write_text('{}', encoding='utf-8')

        # Load JSON in memory.
        with self.filepath.open('r', encoding='utf-8') as f:
            try:
                # This is because JSON keys MUST be strings.
                # source: https://www.w3schools.com/js/js_json_objects.asp
                json_data: dict[str, dict[str, float]] = json.load(f)
            except JSONDecodeError:
                logging.error(f"Failed to decode JSON file '{self.filepath}'")
                json_data = dict()
            except Exception as e:
                logging.error(f"Error while trying to load JSON: {e}")
                json_data = dict()

        return json_data

    def _update_file(self, member_id: int, vc_id: int, elapsed_secs: float) -> None:
        """
        Updates the JSON file: updates elapsed times for `member`, adds an entry if not in file.
        :param member_id: The member to update in the file.
        :param vc_id: The Snowflake ID of the Voice Channel `member` was in.
        :param elapsed_secs: How much time in seconds with microsecond precision `member` passed in the VC.
        """

        # Load file contents into memory
        json_data: dict[str, dict[str, float]] = self._read_file()

        member_id_str = str(member_id)
        vc_id_str = str(vc_id)

        # Add new or update existing.
        json_data.setdefault(member_id_str, {})
        json_data[member_id_str][vc_id_str] = json_data[member_id_str].get(vc_id_str, 0.0) + elapsed_secs

        # The warning is supposed to be a false-positive.
        # Because TextIO supports SupportsWrite[str]
        with self.filepath.open('w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=4)

    def _handle_connected(self, member: Member, vc: VoiceChannel) -> None:
        """The logic when `member` connects to a VC"""
        assert vc and member

        self._connected_members[member.id] = (
            vc.id,
            datetime.now(timezone.utc)
        )

    def _handle_disconnected(self, member: Member, vc: VoiceChannel) -> None:
        """The logic when `member` disconnects from a VC"""
        assert vc and member

        cached_member = self._connected_members.get(member.id, None)
        if cached_member is None:
            logging.warning("A user disconnected without having been monitored.")
            return

        delta_time_secs: float = (datetime.now(timezone.utc) - cached_member[1]).total_seconds()
        self._update_file(member.id, vc.id, delta_time_secs)
        # Prevent stale entries.
        del self._connected_members[member.id]

    @staticmethod
    def _is_in_vc(member: Member, vc: VoiceChannel | None) -> bool:
        """Returns ``True`` if `member` is inside `vc`, otherwise False."""
        return member in vc.members if vc else False

    async def _get_vc_from_id(self, vc_id: int | str) -> VoiceChannel | None:
        """
        Returns a VoiceChannel object if the given ID corresponds to an existing voice channel;
        otherwise returns None.

        Behavior:
        - Try to retrieve the channel from cache.
        - If not found, fetch it from Discord.
        - Return None if it doesn't exist or is not a VoiceChannel.

        Guarantee: If the result is not None, it is a valid VoiceChannel.
        """
        vc_id_int: int = int(vc_id) if isinstance(vc_id, str) else vc_id

        channel = self._bot.get_channel(vc_id_int)
        if channel is None:
            try:
                channel = await self._bot.fetch_channel(vc_id_int)
            except discord.NotFound:
                channel = None

        if isinstance(channel, VoiceChannel):
            return channel
        return None

    async def _get_member_stats(self, member: Member | int) -> dict[VoiceChannel, float]:
        """
        Retrieves voice channel statistics for a given member.

        This method returns the total time (in seconds, with microsecond precision) the member has spent
        in each voice channel they have connected to.

        Note: **Deleted voice channels are not included in the result**.

        :param member: A `discord.Member` instance or the member's Snowflake ID (`int`).
        :return: A dictionary mapping `VoiceChannel` objects to the time spent in each, in seconds.
        """

        # JSON object keys must be strings, so we convert the user ID.
        user_id_str: str = str(member) if isinstance(member, int) else str(member.id)

        # What we'll return.
        res: dict[VoiceChannel, float] = dict()

        # Load JSON into memory
        json_data: dict[str, dict[str, float]] = self._read_file()
        if user_id_str not in json_data:
            return res  # No stats recorded for this user

        for vc_id_str, t_elapsed in json_data[user_id_str].items():
            # VC deleted if None
            vc: VoiceChannel | None = await self._get_vc_from_id(vc_id_str)
            if vc is not None:
                res[vc] = t_elapsed

        return res

    async def _get_members_stats(self, guild: Guild | int) -> dict[Member, dict[VoiceChannel, float]]:
        """
        Retrieves voice channel statistics for all members in the specified guild.

        This method returns a mapping of each member to a dictionary containing
        the total time (in seconds, with microsecond precision) they have spent
        in each voice channel they have connected to.

        Members are not included in the result if they have no stats from the JSON file.

        Note: **Deleted voice channels are not included in the result.**

        :param guild: A `discord.Guild` instance or the guild's Snowflake ID (`int`).
        :return: A dictionary mapping each `Member` to their per-channel voice activity.
        """

        # Make sure we have a `discord.Guild` object.
        if isinstance(guild, Guild):
            guild_obj = guild
        else:
            guild_obj = self._bot.get_guild(guild)
            if guild_obj is None:
                try:
                    guild_obj = await self._bot.fetch_guild(guild)
                except discord.NotFound:
                    raise Exception(f"Guild not found while fetching the guild with id {guild}")

        member_list = guild_obj.members
        stats_list = await asyncio.gather(*(self._get_member_stats(m) for m in member_list))

        # Only keep members with stats.
        res: dict[Member, dict[VoiceChannel, float]] = {
            member: stats for member, stats in zip(member_list, stats_list) if stats
        }

        return res

    @staticmethod
    def _format_time(t_secs: float) -> str:
        """
        Formats a time duration into a compact string like '1h 2m 3s'.
        Examples:
            120.2345 -> '2m'
            3661.0   -> '1h 1m 1s'
            0.5      -> '0s'
        """
        seconds = int(round(t_secs))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if seconds or not parts:
            parts.append(f"{seconds}s")

        return " ".join(parts)

    async def _build_embed_member(self, member: Member) -> Embed:
        """Builds the embed showing the stats of a single user."""
        stats: dict[VoiceChannel, float] = await self._get_member_stats(member)

        embed = Embed(
            title=f"Statistiques vocales pour {member.display_name}",
            description="Temps passé dans les salons vocaux",
            color=self.EMBED_MEMBER_STATS_COLOR
        )

        if not stats:
            embed.description = "Aucune activité vocale enregistrée."
            return embed

        # TODO: filter the ones outside of the member's guild.
        # Sort by descending order with the time as key.
        # Truncate to 25 (Discord allows up to 25 fields)
        sorted_stats: list[tuple[VoiceChannel, float]] = sorted(stats.items(), key=lambda x: x[1], reverse=True)[:25]

        # In ALL VCs. (not truncated sum)
        total_time: float = sum(stats.values())

        embed.set_footer(text=f"Temps total (tous les salons) : {self._format_time(total_time)}")
        embed.set_thumbnail(url=member.display_avatar.url)
        if member.guild.icon:
            embed.set_image(url=member.guild.icon.url)

        for idx, (vc, seconds) in enumerate(sorted_stats, start=1):
            # Prevents ZeroDivisionError (better safe than sorry)
            percent = (seconds / total_time * 100) if total_time else 0.0

            embed.add_field(
                name=f"**{idx}.** {vc.mention}",
                value=f"{self._format_time(seconds)} ({percent:.1f}%)",
                inline=False
            )

        return embed

    @staticmethod
    def _top_vc_with_total(stats: dict[VoiceChannel, float]) -> tuple[float, tuple[VoiceChannel, float]]:
        """
        Summarizes a member's voice activity.

        Given a dictionary mapping voice channels to time spent (in seconds),
        returns:
          - The total time spent across all channels
          - The voice channel where the member spent the most time, along with that time

        If the input is empty, returns None.

        :param stats: A dictionary mapping `VoiceChannel` objects to time spent (in seconds).
        :return: A tuple (total_time, (top_channel, top_time)).
        """
        if not stats:
            logging.warning("Got empty 'stats'")
            raise Exception("Cannot parse empty 'stats'!")

        total: float = sum(stats.values())
        # max will error on empty stats; you may want to guard or define a default.
        top_channel, top_time = max(stats.items(), key=lambda kv: kv[1])
        return total, (top_channel, top_time)

    async def _build_embed_leaderboard(self, guild: Guild) -> Embed:
        """
        Builds and returns an embed displaying the voice activity leaderboard.

        The embed shows which members have spent the most time in voice channels.
        Pagination should be used if the number of entries exceeds the embed field limit.
        :param guild: The guild for which the leaderboard will be built.
        """
        stats: dict[Member, dict[VoiceChannel, float]] = await self._get_members_stats(guild)

        embed = Embed(
            title=f"Statistiques vocales globales",
            description="Temps passé dans les salons vocaux",
            color=self.EMBED_LEADERBOARD_COLOR
        )

        # Complicated but sorts them just like in the other function.
        # Max 25
        sorted_stats = sorted(stats.items(), key=lambda x: sum(x[1].values()), reverse=True)[:25]

        # The sum of all member stats.
        total_time_global: float = sum(
            time
            for member_stats in stats.values()
            for time in member_stats.values()
        )

        embed.set_footer(
            text=f"Temps total cumulé en vocal pour tous les membres : {self._format_time(total_time_global)}")
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        #   int, (Member, dict[VoiceChannel, float])
        for idx, (member, vc_stats) in enumerate(sorted_stats, start=1):
            if not vc_stats:
                logging.warning("vc_stats is empty.")
                continue

            total_time, (top_vc, top_time) = self._top_vc_with_total(vc_stats)
            percent = (total_time / total_time_global * 100) if total_time_global else 0.0

            value: str = (
                f"**{self._format_time(total_time)}** ({percent:.1f}%) / "
                f"Top vocal : {top_vc.mention} ({self._format_time(top_time)})"
            )

            embed.add_field(
                name=f"**{idx}.** {member.display_name}",
                value=value,
                inline=False
            )

        return embed

    def _register_events(self):
        """Registers events to be notified when members do things."""

        @self._bot.event
        async def on_voice_state_update(member: Member, before: VoiceState, after: VoiceState):
            """Is called whenever a member updates their states in a VC. E.g.: connects, disconnects, mutes, deafens, ..."""
            # ONLY specified guilds.
            if member.guild.id not in self._guild_ids:
                return

            # ONLY handle real members.
            if member.bot:
                return

            # if None, the member is CURRENTLY connected to a VC.
            vc_before: VoiceChannel | None = before.channel
            # if None, the member is NOT connected to a VC.
            vc_after: VoiceChannel | None = after.channel

            # ONLY handle connect/disconnect events
            if vc_before == vc_after:
                return

            if vc_before and vc_after:
                # Switch from one VC to another
                logging.debug(f"User '{member.name}' switched VCs: '{vc_before.name}' -> '{vc_after.name}'")
                self._handle_disconnected(member, vc_before)
                self._handle_connected(member, vc_after)

            elif vc_before and not vc_after:
                # Left VC entirely
                logging.debug(f"User '{member.name}' left VC '{vc_before.name}'")
                self._handle_disconnected(member, vc_before)

            elif not vc_before and vc_after:
                # Joined a VC
                logging.debug(f"User '{member.name}' joined VC '{vc_after.name}'")
                self._handle_connected(member, vc_after)

        @self._tree.command(name="vc-leaderboard",
                            description="Top des membres en vocal!",
                            guilds=[Object(id=g) for g in self._guild_ids])
        async def vc_leaderboard_command(ctx: Interaction, member: Optional[Member]):
            d_member: str = 'None' if not member else member.name
            logging.debug(f"User '{ctx.user.name}' used /vc-leaderboard command with member={d_member}")

            if member:
                embed: Embed = await self._build_embed_member(member)
                await ctx.response.send_message(embed=embed)
            else:
                embed: Embed = await self._build_embed_leaderboard(ctx.guild)
                await ctx.response.send_message(embed=embed)
