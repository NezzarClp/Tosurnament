"""Staff commands"""

import asyncio
import datetime
import dateparser
from discord.utils import escape_markdown
from discord.ext import commands
from bot.modules.tosurnament import module as tosurnament
from common.databases.tournament import Tournament
from common.databases.bracket import Bracket
from common.databases.schedules_spreadsheet import MatchInfo, MatchIdNotFound
from common.databases.players_spreadsheet import TeamInfo
from common.databases.guild import Guild
from common.databases.match_notification import MatchNotification
from common.databases.staff_reschedule_message import StaffRescheduleMessage
from common.api.spreadsheet import HttpError


class TosurnamentStaffCog(tosurnament.TosurnamentBaseModule, name="staff"):
    """Tosurnament staff commands"""

    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot

    def cog_check(self, ctx):
        """Check function called before any command of the cog."""
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    @commands.command(aliases=["take_matches", "tm"])
    async def take_match(self, ctx, *args):
        """Allows staffs to take matches"""
        user_details = tosurnament.UserDetails.get_from_ctx(ctx)
        if not user_details.is_staff():
            await self.send_reply(ctx, ctx.command.name, "not_staff")
        else:
            await self.take_or_drop_match_with_ctx(ctx, args, True, user_details)

    @commands.command(aliases=["take_matches_as_referee", "tmar"])
    @tosurnament.has_tournament_role("Referee")
    async def take_match_as_referee(self, ctx, *args):
        """Allows referees to take matches"""
        await self.take_or_drop_match_with_ctx(
            ctx, args, True, tosurnament.UserDetails.get_as_referee(self.bot, ctx.author)
        )

    @commands.command(aliases=["take_matches_as_streamer", "tmas"])
    @tosurnament.has_tournament_role("Streamer")
    async def take_match_as_streamer(self, ctx, *args):
        """Allows streamers to take matches"""
        await self.take_or_drop_match_with_ctx(
            ctx, args, True, tosurnament.UserDetails.get_as_streamer(self.bot, ctx.author)
        )

    @commands.command(aliases=["take_matches_as_commentator", "tmac"])
    @tosurnament.has_tournament_role("Commentator")
    async def take_match_as_commentator(self, ctx, *args):
        """Allows commentators to take matches"""
        await self.take_or_drop_match_with_ctx(
            ctx, args, True, tosurnament.UserDetails.get_as_commentator(self.bot, ctx.author)
        )

    @commands.command(aliases=["drop_matches", "dm"])
    async def drop_match(self, ctx, *args):
        """Allows staffs to drop matches"""
        user_details = tosurnament.UserDetails.get_from_ctx(ctx)
        if not user_details.is_staff():
            await self.send_reply(ctx, ctx.command.name, "not_staff")
        else:
            await self.take_or_drop_match_with_ctx(ctx, args, False, user_details)

    @commands.command(aliases=["drop_matches_as_referee", "dmar"])
    @tosurnament.has_tournament_role("Referee")
    async def drop_match_as_referee(self, ctx, *args):
        """Allows referees to drop matches"""
        await self.take_or_drop_match_with_ctx(
            ctx, args, False, tosurnament.UserDetails.get_as_referee(self.bot, ctx.author)
        )

    @commands.command(aliases=["drop_matches_as_streamer", "dmas"])
    @tosurnament.has_tournament_role("Streamer")
    async def drop_match_as_streamer(self, ctx, *args):
        """Allows streamers to drop matches"""
        await self.take_or_drop_match_with_ctx(
            ctx, args, False, tosurnament.UserDetails.get_as_streamer(self.bot, ctx.author)
        )

    @commands.command(aliases=["drop_matches_as_commentator", "dmac"])
    @tosurnament.has_tournament_role("Commentator")
    async def drop_match_as_commentator(self, ctx, *args):
        """Allows commentators to drop matches"""
        await self.take_or_drop_match_with_ctx(
            ctx, args, False, tosurnament.UserDetails.get_as_commentator(self.bot, ctx.author)
        )

    def take_match_for_roles(self, schedules_spreadsheet, match_info, user_details, take):
        """Takes or drops a match of a bracket for specified roles, if possible."""
        write_cells = False
        staff_name = user_details.name
        for role_name, role_store in user_details.get_staff_roles_as_dict().items():
            if not role_store:
                continue
            take_match = False
            role_cells = getattr(match_info, role_name.lower() + "s")
            if schedules_spreadsheet.use_range:
                if not (take and staff_name in [cell.value for cell in role_cells]):
                    for role_cell in role_cells:
                        if take and not role_cell.value:
                            role_cell.value = staff_name
                            take_match = True
                            break
                        elif not take and role_cell.value == staff_name:
                            role_cell.value = ""
                            take_match = True
                            break
            elif len(role_cells) > 0:
                role_cell = role_cells[0]
                max_take = getattr(schedules_spreadsheet, "max_" + role_name.lower())
                staffs = list(filter(None, [staff.strip() for staff in role_cell.value.split("/")]))
                if take and len(staffs) < max_take and staff_name not in staffs:
                    staffs.append(staff_name)
                    role_cell.value = " / ".join(staffs)
                    take_match = True
                elif not take and staff_name in staffs:
                    staffs.remove(staff_name)
                    role_cell.value = " / ".join(staffs)
                    take_match = True
            if take_match:
                role_store.taken_matches.append(match_info.match_id.value)
                write_cells = True
            if not take_match:
                role_store.not_taken_matches.append(match_info.match_id.value)
        return write_cells

    def take_or_drop_match_in_bracket(self, bracket, match_ids, user_details, take, invalid_match_ids):
        """Takes or drops matches of a bracket, if possible."""
        schedules_spreadsheet = bracket.schedules_spreadsheet
        if not schedules_spreadsheet:
            return
        write_cells = False
        for match_id in match_ids:
            try:
                match_info = MatchInfo.from_id(schedules_spreadsheet, match_id, False)
            except MatchIdNotFound:
                invalid_match_ids.add(match_id)
                continue
            write_cells |= self.take_match_for_roles(schedules_spreadsheet, match_info, user_details, take)
        if write_cells:
            try:
                bracket.schedules_spreadsheet.spreadsheet.update()
            except HttpError as e:
                raise tosurnament.SpreadsheetHttpError(e.code, e.operation, bracket.name, "schedules", e.error)
        return write_cells

    def format_take_match_string(self, string, match_ids):
        """Appends the match ids separated by a comma to the string."""
        if match_ids:
            for i, match_id in enumerate(match_ids):
                string += match_id
                if i + 1 < len(match_ids):
                    string += ", "
                else:
                    string += "\n"
            return string
        return ""

    def build_take_match_reply(self, user_details, take, invalid_match_ids):
        """Builds the reply depending on matches taken or not and invalid matches."""
        staff_name = escape_markdown(user_details.name)
        reply = ""
        command_name = "take_match"
        if not take:
            command_name = "drop_match"
        for staff_title, staff in user_details.get_staff_roles_as_dict().items():
            if staff:
                for match_id in invalid_match_ids.copy():
                    if match_id.lower() in [match.lower() for match in staff.taken_matches] or match_id.lower() in [
                        match.lower() for match in staff.not_taken_matches
                    ]:
                        invalid_match_ids.remove(match_id)
                        continue
                reply += self.format_take_match_string(
                    self.get_string(command_name, "taken_match_ids", staff_title, staff_name), staff.taken_matches,
                )
                reply += self.format_take_match_string(
                    self.get_string(command_name, "not_taken_match_ids", staff_title, staff_name),
                    staff.not_taken_matches,
                )
        reply += self.format_take_match_string(self.get_string(command_name, "invalid_match_ids"), invalid_match_ids)
        return reply

    async def take_or_drop_match_with_ctx(self, ctx, match_ids, take, user_details):
        await self.take_or_drop_match(ctx.guild.id, ctx.channel, match_ids, take, user_details)

    async def take_or_drop_match(self, guild_id, channel, match_ids, take, user_details):
        if not match_ids:
            raise commands.UserInputError()
        tournament = self.get_tournament(guild_id)
        invalid_match_ids = set()
        for bracket in tournament.brackets:
            self.take_or_drop_match_in_bracket(bracket, match_ids, user_details, take, invalid_match_ids)
        await channel.send(self.build_take_match_reply(user_details, take, invalid_match_ids))

    def find_matches_to_notify(self, bracket):
        matches_info = []
        now = datetime.datetime.utcnow()
        schedules_spreadsheet = bracket.schedules_spreadsheet
        match_ids = bracket.schedules_spreadsheet.spreadsheet.get_cells_with_value_in_range(
            bracket.schedules_spreadsheet.range_match_id
        )
        for match_id_cell in match_ids:
            match_info = MatchInfo.from_match_id_cell(schedules_spreadsheet, match_id_cell)
            date_format = "%d %B"
            if schedules_spreadsheet.date_format:
                date_format = schedules_spreadsheet.date_format
            match_date = dateparser.parse(
                match_info.get_datetime(), date_formats=list(filter(None, [date_format + " %H:%M"])),
            )
            if match_date:
                delta = match_date - now
                if delta.days == 0 and delta.seconds >= 900 and delta.seconds < 1800:
                    matches_info.append(match_info)
        return matches_info

    def get_team_mention(self, guild, players_spreadsheet, team_name):
        if not players_spreadsheet:
            return escape_markdown(team_name)
        try:
            team_info = TeamInfo.from_team_name(players_spreadsheet, team_name)
            if players_spreadsheet.range_team_name:
                team_role = tosurnament.get_role(guild.roles, None, team_name)
                if team_role:
                    return team_role.mention
            user = tosurnament.UserAbstraction.get_from_osu_name(
                self.bot, team_info.players[0].value, team_info.discord[0].value
            )
            member = user.get_member(guild)
            if member:
                return member.mention
            return escape_markdown(team_name)
        except Exception as e:
            self.bot.info(str(type(e)) + ": " + str(e))
            return escape_markdown(team_name)

    async def player_match_notification(self, guild, tournament, bracket, channel, match_info, delta):
        if not (delta.days == 0 and delta.seconds >= 900 and delta.seconds < 1800):
            return
        players_spreadsheet = bracket.players_spreadsheet
        team1 = self.get_team_mention(guild, players_spreadsheet, match_info.team1.value)
        team2 = self.get_team_mention(guild, players_spreadsheet, match_info.team2.value)
        referee_name = match_info.referees[0].value
        referee_role = None
        notification_type = "notification"
        if referee_name:
            referee = guild.get_member_named(referee_name)
            if referee:
                referee = referee.mention
            else:
                referee = referee_name
        else:
            referee_role = tosurnament.get_role(guild.roles, tournament.referee_role_id, "Referee")
            if referee_role:
                referee = referee_role.mention
                notification_type = "notification_no_referee"
            else:
                referee = ""
                notification_type = "notification_no_referre_no_role"
        minutes_before_match = str(int(delta.seconds / 60) + 1)
        message = await self.send_reply(
            channel,
            "player_match_notification",
            notification_type,
            match_info.match_id.value,
            team1,
            team2,
            referee,
            minutes_before_match,
        )
        if referee_role:
            match_notification = MatchNotification(
                message_id_hash=message.id,
                message_id=message.id,
                tournament_id=tournament.id,
                bracket_id=bracket.id,
                match_id=match_info.match_id.value,
                team1_mention=team1,
                team2_mention=team2,
                date_info=minutes_before_match,
                notification_type=0,
            )
            self.bot.session.add(match_notification)
        try:
            await message.add_reaction("👀")
            if referee_role:
                await message.add_reaction("💪")
        except Exception as e:
            self.bot.info(str(type(e)) + ": " + str(e))

    async def referee_match_notification(self, guild, tournament, bracket, channel, match_info, delta, match_date):
        if list(filter(None, [cell.value for cell in match_info.referees])):
            return
        if not (delta.days == 0 and delta.seconds >= 20700 and delta.seconds < 21600):
            return
        referee_role = tosurnament.get_role(guild.roles, tournament.referee_role_id, "Referee")
        if referee_role:
            referee = referee_role.mention
        else:
            referee = "Referees"
        match_date_str = match_date.strftime(tosurnament.PRETTY_DATE_FORMAT)
        team1 = escape_markdown(match_info.team1.value)
        team2 = escape_markdown(match_info.team2.value)
        message = await self.send_reply(
            channel,
            "referee_match_notification",
            "notification",
            match_info.match_id.value,
            team1,
            team2,
            referee,
            match_date_str,
        )
        match_notification = MatchNotification(
            message_id_hash=message.id,
            message_id=message.id,
            tournament_id=tournament.id,
            bracket_id=bracket.id,
            match_id=match_info.match_id.value,
            team1_mention=team1,
            team2_mention=team2,
            date_info=match_date_str,
            notification_type=1,
        )
        self.bot.session.add(match_notification)
        try:
            await message.add_reaction("😱")
            await message.add_reaction("💪")
        except Exception as e:
            self.bot.info(str(type(e)) + ": " + str(e))

    async def match_notification(self, guild, now):
        tournament = self.get_tournament(guild.id)
        player_match_notification_channel = None
        if tournament.match_notification_channel_id:
            player_match_notification_channel = self.bot.get_channel(tournament.match_notification_channel_id)
        staff_channel = None
        if tournament.staff_channel_id:
            staff_channel = self.bot.get_channel(tournament.staff_channel_id)
        if not player_match_notification_channel and not staff_channel:
            return
        matches_to_ignore = [match_id.upper() for match_id in tournament.matches_to_ignore.split("\n")]
        for bracket in tournament.brackets:
            schedules_spreadsheet = bracket.schedules_spreadsheet
            if not schedules_spreadsheet:
                continue
            match_ids = bracket.schedules_spreadsheet.spreadsheet.get_cells_with_value_in_range(
                bracket.schedules_spreadsheet.range_match_id
            )
            for match_id_cell in match_ids:
                if match_id_cell.value.upper() in matches_to_ignore:
                    continue
                match_info = MatchInfo.from_match_id_cell(schedules_spreadsheet, match_id_cell)
                date_format = "%d %B"
                if schedules_spreadsheet.date_format:
                    date_format = schedules_spreadsheet.date_format
                match_date = dateparser.parse(
                    match_info.get_datetime(), date_formats=list(filter(None, [date_format + " %H:%M"])),
                )
                if match_date:
                    delta = match_date - now
                    if player_match_notification_channel:
                        await self.player_match_notification(
                            guild, tournament, bracket, player_match_notification_channel, match_info, delta
                        )
                    if staff_channel:
                        await self.referee_match_notification(
                            guild, tournament, bracket, staff_channel, match_info, delta, match_date
                        )

    async def match_notification_wrapper(self, guild):
        previous_notification_date = None
        try:
            now = datetime.datetime.utcnow()
            tosurnament_guild = self.get_guild(guild.id)
            if not tosurnament_guild:
                tosurnament_guild = Guild(guild_id=guild.id)
                self.bot.session.add(tosurnament_guild)
            elif tosurnament_guild.last_notification_date:
                previous_notification_date = datetime.datetime.strptime(
                    tosurnament_guild.last_notification_date, tosurnament.DATABASE_DATE_FORMAT
                )
                delta = now - previous_notification_date
                if (
                    delta.days == 0
                    and delta.seconds < 900
                    and int(now.minute / 15) == int(previous_notification_date.minute / 15)
                ):
                    return
            tosurnament_guild.last_notification_date = now.strftime(tosurnament.DATABASE_DATE_FORMAT)
            self.bot.session.update(tosurnament_guild)
            await self.match_notification(guild, now)
        except asyncio.CancelledError:
            if previous_notification_date:
                tosurnament_guild.last_notification_date = previous_notification_date.strftime(
                    tosurnament.DATABASE_DATE_FORMAT
                )
                self.bot.session.update(tosurnament_guild)
            return
        except Exception as e:
            self.bot.info(str(type(e)) + ": " + str(e))
            return

    async def background_task_match_notification(self):
        try:
            await self.bot.wait_until_ready()
            while not self.bot.is_closed():
                tasks = []
                try:
                    for guild in self.bot.guilds:
                        tasks.append(self.bot.loop.create_task(self.match_notification_wrapper(guild)))
                    now = datetime.datetime.utcnow()
                    delta_minutes = 15 - now.minute % 15
                    await asyncio.sleep(delta_minutes * 60)
                except asyncio.CancelledError:
                    for task in tasks:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            continue
                    return
        except asyncio.CancelledError:
            return

    def background_task(self):
        self.bot.tasks.append(self.bot.loop.create_task(self.background_task_match_notification()))

    async def on_raw_reaction_add(self, message_id, emoji, guild, channel, user):
        """on_raw_reaction_add of the Tosurnament staff module."""
        await self.reaction_on_match_notification(message_id, emoji, guild, channel, user)
        await self.reaction_on_staff_reschedule_message(message_id, emoji, guild, channel, user)

    async def reaction_on_match_notification(self, message_id, emoji, guild, channel, user):
        """Allows a referee to take a match from its notification."""
        if emoji.name != "💪":
            return
        match_notification = (
            self.bot.session.query(MatchNotification).where(MatchNotification.message_id_hash == message_id).first()
        )
        if not match_notification or match_notification.in_use:
            return
        tournament = self.bot.session.query(Tournament).where(Tournament.id == match_notification.tournament_id).first()
        if not tournament:
            self.bot.session.delete(match_notification)
            return
        referee_role = tosurnament.get_role(user.roles, tournament.referee_role_id, "Referee")
        if not referee_role:
            return
        match_notification.in_use = True
        self.bot.session.update(match_notification)
        bracket = self.bot.session.query(Bracket).where(Bracket.id == match_notification.bracket_id).first()
        if not bracket:
            self.bot.session.delete(match_notification)
            return
        try:
            self.take_or_drop_match_in_bracket(
                bracket,
                [match_notification.match_id],
                tosurnament.UserDetails.get_as_referee(self.bot, user),
                True,
                set(),
            )
            # TODO if not write_cells send error
        except Exception as e:
            match_notification.in_use = False
            self.bot.session.update(match_notification)
            await self.on_cog_command_error(channel, "take_match", e)
            return
        command_name = "player_match_notification"
        if match_notification.notification_type == 1:
            command_name = "referee_match_notification"
        match_notification_message = await channel.fetch_message(match_notification.message_id)
        await match_notification_message.edit(
            content=self.get_string(
                command_name,
                "edited",
                match_notification.match_id,
                match_notification.team1_mention,
                match_notification.team2_mention,
                referee_role.mention,
                match_notification.date_info,
                user.mention,
            )
        )
        self.bot.session.delete(match_notification)

    async def reaction_on_staff_reschedule_message(self, message_id, emoji, guild, channel, user):
        """Removes the referee from the schedule spreadsheet"""
        if emoji.name != "❌":
            return
        staff_reschedule_message = (
            self.bot.session.query(StaffRescheduleMessage)
            .where(StaffRescheduleMessage.message_id == message_id)
            .first()
        )
        if not staff_reschedule_message or staff_reschedule_message.in_use:
            return
        if user.id != staff_reschedule_message.staff_id:
            return
        tournament = (
            self.bot.session.query(Tournament).where(Tournament.id == staff_reschedule_message.tournament_id).first()
        )
        if not tournament:
            self.bot.session.delete(staff_reschedule_message)
            return
        staff_reschedule_message.in_use = True
        self.bot.session.update(staff_reschedule_message)
        bracket = self.bot.session.query(Bracket).where(Bracket.id == staff_reschedule_message.bracket_id).first()
        if not bracket:
            self.bot.session.delete(staff_reschedule_message)
            return
        try:
            user_details = tosurnament.UserDetails.get_from_user(self.bot, user, tournament)
            self.take_or_drop_match_in_bracket(
                bracket, [staff_reschedule_message.match_id], user_details, False, set(),
            )
            # TODO if not write_cells send error + update message instead of reply
            await channel.send(self.build_take_match_reply(user_details, False, set()))
        except Exception as e:
            staff_reschedule_message.in_use = False
            self.bot.session.update(staff_reschedule_message)
            await self.on_cog_command_error(channel, "take_match", e)
            return


def get_class(bot):
    """Returns the main class of the module"""
    return TosurnamentStaffCog(bot)


def setup(bot):
    """Setups the cog"""
    bot.add_cog(TosurnamentStaffCog(bot))
