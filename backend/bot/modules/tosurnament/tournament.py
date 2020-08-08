"""Contains all tournament settings commands related to Tosurnament."""

import asyncio
import datetime
import discord
from discord.ext import commands
from bot.modules.tosurnament import module as tosurnament
from common.databases.bracket import Bracket
from common.databases.allowed_reschedule import AllowedReschedule


class TosurnamentTournamentCog(tosurnament.TosurnamentBaseModule, name="tournament"):
    """Tosurnament tournament settings commands."""

    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot

    def cog_check(self, ctx):
        """Check function called before any command of the cog."""
        if not ctx.guild:
            raise commands.NoPrivateMessage()
        if ctx.guild.owner == ctx.author:
            return True
        guild = self.get_guild(ctx.guild.id)
        if not guild or not guild.admin_role_id:
            raise tosurnament.NotBotAdmin()
        if not tosurnament.get_role(ctx.author.roles, guild.admin_role_id):
            raise tosurnament.NotBotAdmin()
        return True

    @commands.command(aliases=["stn"])
    async def set_tournament_name(self, ctx, *, name: str):
        """Sets the tournament name."""
        await self.set_tournament_values(ctx, {"name": name})

    @commands.command(aliases=["cb"])
    async def create_bracket(self, ctx, *, name: str):
        """Creates a bracket and sets it as current bracket (for bracket settings purpose)."""
        tournament = self.get_tournament(ctx.guild.id)
        bracket = Bracket(tournament_id=tournament.id, name=name)
        self.bot.session.add(bracket)
        tournament.current_bracket_id = bracket.id
        self.bot.session.update(tournament)
        await self.send_reply(ctx, ctx.command.name, "success", name)

    @commands.command(aliases=["get_brackets", "gb"])
    async def get_bracket(self, ctx, *, number: int = None):
        """Sets a bracket as current bracket or shows them all."""
        tournament = self.get_tournament(ctx.guild.id)
        brackets = tournament.brackets
        if number or number == 0:
            number -= 1
            if not (number >= 0 and number < len(brackets)):
                raise commands.UserInputError()
            tournament.current_bracket_id = brackets[number].id
            self.bot.session.update(tournament)
            await self.send_reply(ctx, ctx.command.name, "success", brackets[number].name)
        else:
            brackets_string = ""
            for i, bracket in enumerate(brackets):
                brackets_string += str(i + 1) + ": `" + bracket.name + "`"
                if bracket.id == tournament.current_bracket_id:
                    brackets_string += " (current bracket)"
                brackets_string += "\n"
            await self.send_reply(ctx, ctx.command.name, "default", brackets_string)

    @commands.command(aliases=["ssc"])
    async def set_staff_channel(self, ctx, *, channel: discord.TextChannel):
        """Sets the staff channel."""
        await self.set_tournament_values(ctx, {"staff_channel_id": channel.id})

    @commands.command(aliases=["smnc"])
    async def set_match_notification_channel(self, ctx, *, channel: discord.TextChannel):
        """Sets the match notification channel."""
        await self.set_tournament_values(ctx, {"match_notification_channel_id": channel.id})

    @commands.command(aliases=["srr"])
    async def set_referee_role(self, ctx, *, role: discord.Role):
        """Sets the referee role."""
        await self.set_tournament_values(ctx, {"referee_role_id": role.id})

    @commands.command(aliases=["ssr"])
    async def set_streamer_role(self, ctx, *, role: discord.Role):
        """Sets the streamer role."""
        await self.set_tournament_values(ctx, {"streamer_role_id": role.id})

    @commands.command(aliases=["scr"])
    async def set_commentator_role(self, ctx, *, role: discord.Role):
        """Sets the commentator role."""
        await self.set_tournament_values(ctx, {"commentator_role_id": role.id})

    @commands.command(aliases=["spr"])
    async def set_player_role(self, ctx, *, role: discord.Role):
        """Sets the player role."""
        await self.set_tournament_values(ctx, {"player_role_id": role.id})

    @commands.command(aliases=["stcr", "set_team_leader_role", "stlr"])
    async def set_team_captain_role(self, ctx, *, role: discord.Role = None):
        """Sets the team captain role."""
        if not role:
            await self.set_tournament_values(ctx, {"team_captain_role_id": 0})
        else:
            await self.set_tournament_values(ctx, {"team_captain_role_id": role.id})

    @commands.command(aliases=["spt"])
    async def set_ping_team(self, ctx, ping_team: bool):
        """Sets if team should be pinged or team captain should be pinged."""
        await self.set_tournament_values(ctx, {"reschedule_ping_team": ping_team})

    @commands.command(aliases=["sprm"])
    async def set_post_result_message(self, ctx, *, message: str = ""):
        """Sets the post result message."""
        await self.set_tournament_values(ctx, {"post_result_message": message})

    @commands.command(aliases=["sprmt1ws"])
    async def set_post_result_message_team1_with_score(self, ctx, *, message: str = ""):
        """Sets the post result message."""
        await self.set_tournament_values(ctx, {"post_result_message_team1_with_score": message})

    @commands.command(aliases=["sprmt2ws"])
    async def set_post_result_message_team2_with_score(self, ctx, *, message: str = ""):
        """Sets the post result message."""
        await self.set_tournament_values(ctx, {"post_result_message_team2_with_score": message})

    @commands.command(aliases=["sprmml"])
    async def set_post_result_message_mp_link(self, ctx, *, message: str = ""):
        """Sets the post result message."""
        await self.set_tournament_values(ctx, {"post_result_message_mp_link": message})

    @commands.command(aliases=["sprmr"])
    async def set_post_result_message_rolls(self, ctx, *, message: str = ""):
        """Sets the post result message."""
        await self.set_tournament_values(ctx, {"post_result_message_rolls": message})

    @commands.command(aliases=["sprmb"])
    async def set_post_result_message_bans(self, ctx, *, message: str = ""):
        """Sets the post result message."""
        await self.set_tournament_values(ctx, {"post_result_message_bans": message})

    @commands.command(aliases=["sprmtb"])
    async def set_post_result_message_tb_bans(self, ctx, *, message: str = ""):
        """Sets the post result message."""
        await self.set_tournament_values(ctx, {"post_result_message_tb_bans": message})

    @commands.command(aliases=["srdhbct"])
    async def set_reschedule_deadline_hours_before_current_time(self, ctx, hours: int):
        """Allows to change the deadline (in hours) before the current match time to reschedule a match."""
        await self.set_tournament_values(ctx, {"reschedule_deadline_hours_before_current_time": hours})

    @commands.command(aliases=["srdhbnt"])
    async def set_reschedule_deadline_hours_before_new_time(self, ctx, hours: int):
        """Allows to change the deadline (in hours) before the new match time to reschedule a match."""
        await self.set_tournament_values(ctx, {"reschedule_deadline_hours_before_new_time": hours})

    @commands.command(aliases=["snnsr"])
    async def set_notify_no_staff_reschedule(self, ctx, notify: bool):
        await self.set_tournament_values(ctx, {"notify_no_staff_reschedule": notify})

    async def set_tournament_values(self, ctx, values):
        """Puts the input values into the corresponding tournament."""
        tournament = self.get_tournament(ctx.guild.id)
        for key, value in values.items():
            setattr(tournament, key, value)
        self.bot.session.update(tournament)
        await self.send_reply(ctx, ctx.command.name, "success", value)

    @commands.command(aliases=["amti", "add_matches_to_ignore"])
    async def add_match_to_ignore(self, ctx, *match_ids):
        """Adds matches in the list of matches to ignore in other commands."""
        await self.add_or_remove_match_to_ignore(ctx, match_ids, True)

    @commands.command(aliases=["rmti", "remove_matches_to_ignore"])
    async def remove_match_to_ignore(self, ctx, *match_ids):
        """Removes matches in the list of matches to ignore in other commands."""
        await self.add_or_remove_match_to_ignore(ctx, match_ids, False)

    async def add_or_remove_match_to_ignore(self, ctx, match_ids, add):
        """Removes matches in the list of matches to ignore in other commands."""
        tournament = self.get_tournament(ctx.guild.id)
        matches_to_ignore = [match_id.upper() for match_id in tournament.matches_to_ignore.split("\n")]
        for match_id in match_ids:
            match_id_upper = match_id.upper()
            if add and match_id_upper not in matches_to_ignore:
                matches_to_ignore.append(match_id_upper)
            elif not add and match_id_upper in matches_to_ignore:
                matches_to_ignore.remove(match_id_upper)
        tournament.matches_to_ignore = "\n".join(matches_to_ignore)
        self.bot.session.update(tournament)
        await self.send_reply(ctx, ctx.command.name, "success", " ".join(matches_to_ignore))

    @commands.command(aliases=["anr"])
    async def allow_next_reschedule(self, ctx, match_id: str, allowed_hours: int = 24):
        """Allows a match to be reschedule without any time constraint applied."""
        tournament = self.get_tournament(ctx.guild.id)
        allowed_reschedule = AllowedReschedule(
            tournament_id=tournament.id, match_id=match_id, allowed_hours=allowed_hours
        )
        self.bot.session.add(allowed_reschedule)
        await self.send_reply(ctx, ctx.command.name, "success", match_id, allowed_hours)

    async def clean_allowed_reschedule(self, guild):
        tournament = self.get_tournament(guild.id)
        allowed_reschedules = (
            self.bot.session.query(AllowedReschedule).where(AllowedReschedule.tournament_id == tournament.id).all()
        )
        now = datetime.datetime.utcnow()
        for allowed_reschedule in allowed_reschedules:
            created_at = datetime.datetime.fromtimestamp(allowed_reschedule.created_at)
            if now > created_at + datetime.timedelta(seconds=(allowed_reschedule.allowed_hours * 3600)):
                self.bot.session.delete(allowed_reschedule)

    async def background_task_clean_allowed_reschedule(self):
        try:
            await self.bot.wait_until_ready()
            while not self.bot.is_closed():
                for guild in self.bot.guilds:
                    try:
                        await self.clean_allowed_reschedule(guild)
                    except asyncio.CancelledError:
                        return
                    except Exception:
                        continue
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            return

    def background_task(self):
        self.bot.tasks.append(self.bot.loop.create_task(self.background_task_clean_allowed_reschedule()))


def get_class(bot):
    """Returns the main class of the module."""
    return TosurnamentTournamentCog(bot)


def setup(bot):
    """Setups the cog."""
    bot.add_cog(TosurnamentTournamentCog(bot))
