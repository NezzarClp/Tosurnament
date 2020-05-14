"""Post results commands"""

import re
from discord.ext import commands
from bot.modules.tosurnament import module as tosurnament
from common.databases.bracket import Bracket
from common.databases.players_spreadsheet import TeamInfo
from common.databases.schedules_spreadsheet import MatchInfo, MatchIdNotFound
from common.databases.post_result_message import PostResultMessage
from common.api.spreadsheet import HttpError
from common.api import osu
from common.api import challonge


class PostResultBuilder:
    def __init__(self):
        self.tournament_acronym = ""
        self.tournament_name = ""
        self.bracket_name = ""
        self.score_team1 = 0
        self.score_team2 = 0
        self.roll_team1 = 0
        self.roll_team2 = 0
        self.team_name1 = ""
        self.team_name2 = ""
        self.match_id = ""
        self.mp_links = ""
        self.winner_roll = ""
        self.loser_roll = ""
        self.bans_team1 = ""
        self.bans_team2 = ""
        self.tb_bans_team1 = ""
        self.tb_bans_team2 = ""

    def get_score_team1(self):
        if self.score_team1 < 0:
            return "FF"
        else:
            return str(self.score_team1)

    def get_score_team2(self):
        if self.score_team2 < 0:
            return "FF"
        else:
            return str(self.score_team2)

    def get_mp_links(self):
        links = osu.build_mp_links(self.mp_links.split("\n"))
        return "\n".join(["<" + link + ">" for link in links])

    def build(self, blueprint, bot, tournament):
        result = blueprint
        if self.roll_team1 > 0 or self.roll_team2 > 0:
            if tournament.post_result_message_rolls:
                result = result.replace("%_rolls_", tournament.post_result_message_rolls)
            else:
                result = result.replace("%_rolls_", bot.get_string("post_result", "default_rolls"))
        else:
            result = result.replace("%_rolls_", "")
        if self.bans_team1 or self.bans_team2:
            if tournament.post_result_message_bans:
                result = result.replace("%_bans_", tournament.post_result_message_bans)
            else:
                result = result.replace("%_bans_", bot.get_string("post_result", "default_bans"))
        else:
            result = result.replace("%_bans_", "")
        if self.tb_bans_team1 or self.tb_bans_team2:
            if tournament.post_result_message_tb_bans:
                result = result.replace("%_tb_bans_", tournament.post_result_message_tb_bans)
            else:
                result = result.replace("%_tb_bans_", bot.get_string("post_result", "default_tb_bans"))
        else:
            result = result.replace("%_tb_bans_", "")

        result = result.replace("%tournament_acronym", self.tournament_acronym)
        result = result.replace("%tournament_name", self.tournament_name)
        result = result.replace("%bracket_name", self.bracket_name)
        result = result.replace("%match_id", self.match_id)
        result = result.replace("%mp_link", self.get_mp_links())
        result = result.replace("%team1", self.team_name1)
        result = result.replace("%team2", self.team_name2)
        result = result.replace("%score_team1", self.get_score_team1())
        result = result.replace("%score_team2", self.get_score_team2())
        result = result.replace("%bans_team1", self.bans_team1)
        result = result.replace("%bans_team2", self.bans_team2)
        result = result.replace("%tb_bans_team1", self.tb_bans_team1)
        result = result.replace("%tb_bans_team2", self.tb_bans_team2)
        result = result.replace("%roll_team1", str(self.roll_team1))
        result = result.replace("%roll_team2", str(self.roll_team2))
        if self.roll_team2 > self.roll_team1:
            result = result.replace("%roll_winner", str(self.roll_team2))
            result = result.replace("%roll_loser", str(self.roll_team1))
            result = result.replace("%team_roll_winner", self.team_name2)
            result = result.replace("%team_roll_loser", self.team_name1)
            result = result.replace("%bans_roll_winner", self.bans_team2)
            result = result.replace("%bans_roll_loser", self.bans_team1)
            result = result.replace("%tb_bans_roll_winner", self.tb_bans_team2)
            result = result.replace("%tb_bans_roll_loser", self.tb_bans_team1)
        else:
            result = result.replace("%roll_winner", str(self.roll_team1))
            result = result.replace("%roll_loser", str(self.roll_team2))
            result = result.replace("%team_roll_winner", self.team_name1)
            result = result.replace("%team_roll_loser", self.team_name2)
            result = result.replace("%bans_roll_winner", self.bans_team1)
            result = result.replace("%bans_roll_loser", self.bans_team2)
            result = result.replace("%tb_bans_roll_winner", self.tb_bans_team1)
            result = result.replace("%tb_bans_roll_loser", self.tb_bans_team2)
        return result


def get_players_id(team_info):
    players = []
    for player_cell in team_info.players:
        players.append(player_cell.value)
    return osu.usernames_to_ids(players)


def calc_match_score(post_result_message, players_team1, players_team2):
    n_warmup = post_result_message.n_warmup
    score_team1 = 0
    score_team2 = 0
    games = []
    for mp_id in post_result_message.mp_links.split("\n"):
        match = osu.get_match(mp_id)
        if not match:
            raise tosurnament.InvalidMpLink()
        games += match.games
    for i, game in enumerate(games):
        if n_warmup > 0:
            n_warmup -= 1
        else:
            if i + 1 < len(games):
                if games[i + 1].beatmap_id == game.beatmap_id:
                    i += 1
                    continue
            total_team1 = 0
            total_team2 = 0
            for score in game.scores:
                if score.passed == "1":
                    if score.user_id in players_team1:
                        total_team1 += int(score.score)
                    elif score.user_id in players_team2:
                        total_team2 += int(score.score)
            if total_team1 > total_team2:
                if score_team1 < int(post_result_message.best_of / 2) + 1:
                    score_team1 += 1
            elif total_team1 < total_team2:
                if score_team2 < int(post_result_message.best_of / 2) + 1:
                    score_team2 += 1
    return score_team1, score_team2


class TosurnamentPostResultCog(tosurnament.TosurnamentBaseModule, name="post_result"):
    """Tosurnament post results commands"""

    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot

    def cog_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        role_name = "Referee"
        tournament = self.get_tournament(ctx.guild.id)
        role_id = tournament.get_role_id(role_name)
        role = tosurnament.get_role(ctx.guild.roles, role_id, role_name)
        if not role:
            raise tosurnament.RoleDoesNotExist(role_name)
        if role in ctx.author.roles:
            return True
        raise tosurnament.NotRequiredRole(role_name)

    @commands.command(aliases=["pr"])
    async def post_result(self, ctx, match_id: str):
        """Allows referees to post the result of a match"""
        tournament, bracket = await self.init_post_result(ctx, match_id)
        await self.step0(match_id, -1, -1, tournament, bracket)

    @commands.command(aliases=["prws"])
    async def post_result_with_scores(self, ctx, match_id: str, score_team1: int, score_team2: int):
        """Allows referees to post the result of a match"""
        tournament, bracket = await self.init_post_result(ctx, match_id)
        await self.step0(match_id, score_team1, score_team2, tournament, bracket)

    @commands.command(aliases=["prol"])
    async def post_result_one_liner(
        self, ctx, match_id: str, score_team1: int, score_team2: int, best_of: int, n_warmup: int, *, others
    ):
        await self.post_result_one_liner_(ctx, match_id, score_team1, score_team2, best_of, 0, 0, n_warmup, others)

    @commands.command(aliases=["prolwr"])
    async def post_result_one_liner_with_rolls(
        self,
        ctx,
        match_id: str,
        score_team1: int,
        score_team2: int,
        best_of: int,
        roll_team1: int,
        roll_team2: int,
        n_warmup: int,
        *,
        others
    ):
        await self.post_result_one_liner_(
            ctx, match_id, score_team1, score_team2, best_of, roll_team1, roll_team2, n_warmup, others,
        )

    async def post_result_one_liner_(
        self, ctx, match_id, score_team1, score_team2, best_of, roll_team1, roll_team2, n_warmup, others,
    ):
        """Allows referees to post the result of a match"""
        tournament, bracket = await self.init_post_result(ctx, match_id)
        mp_links = []
        bans = []
        tb_bans = []
        i = 0
        others_kind = others.split("|'|")
        while i < len(others_kind):
            for other in others_kind[i].strip().split('"\'"'):
                other = other.strip()
                if i == 0:
                    mp_links.append(other)
                elif i == 1:
                    bans.append(other)
                else:
                    tb_bans.append(other)
            i += 1
        mp_links = [osu.get_from_string(mp_link) for mp_link in mp_links]
        bans_team1 = []
        bans_team2 = []
        if len(bans) % 2 == 0:
            bans_team1 = bans[: int(len(bans) / 2)]
            bans_team2 = bans[int(len(bans) / 2) :]
        tb_bans_team1 = []
        tb_bans_team2 = []
        if len(tb_bans) % 2 == 0:
            tb_bans_team1 = tb_bans[: int(len(tb_bans) / 2)]
            tb_bans_team2 = tb_bans[int(len(tb_bans) / 2) :]
        post_result_message = PostResultMessage(
            tournament_id=tournament.id,
            bracket_id=bracket.id,
            referee_id=ctx.author.id,
            step=8,
            match_id=match_id,
            score_team1=score_team1,
            score_team2=score_team2,
            best_of=best_of,
            roll_team1=roll_team1,
            roll_team2=roll_team2,
            n_warmup=n_warmup,
            mp_links="\n".join(mp_links),
            bans_team1="\n".join(bans_team1),
            bans_team2="\n".join(bans_team2),
            tb_bans_team1="\n".join(tb_bans_team1),
            tb_bans_team2="\n".join(tb_bans_team2),
        )
        message = await self.step7_send_message(ctx, tournament, post_result_message)
        self.bot.session.add(post_result_message)
        await self.add_reaction_to_setup_message(message)

    async def init_post_result(self, ctx, match_id):
        """Allows referees to post the result of a match"""
        tournament = self.get_tournament(ctx.guild.id)
        brackets = self.get_all_brackets(tournament)
        for bracket in brackets:
            schedules_spreadsheet = self.get_schedules_spreadsheet(bracket)
            if not schedules_spreadsheet:
                continue
            try:
                spreadsheet, worksheet = self.get_spreadsheet_worksheet(schedules_spreadsheet)
            except HttpError as e:
                raise tosurnament.SpreadsheetHttpError(e.code, e.operation, bracket.name, "schedules")
            try:
                MatchInfo.from_id(schedules_spreadsheet, worksheet, match_id)
            except MatchIdNotFound:
                continue
            return tournament, bracket
        raise tosurnament.InvalidMatchId()

    async def step0(self, ctx, match_id, score_team1, score_team2, tournament, bracket):
        """Step 0 (initialization) of the post_result_command"""
        message = await self.send_reply(ctx, "post_result", "step1", match_id)
        post_result_message = PostResultMessage(
            tournament_id=tournament.id,
            bracket_id=bracket.id,
            referee_id=ctx.author.id,
            setup_message_id=message.id,
            match_id=match_id,
            score_team1=score_team1,
            score_team2=score_team2,
        )
        self.bot.session.add(post_result_message)
        await self.add_reaction_to_setup_message(message)

    async def step1(self, ctx, tournament, post_result_message, parameter):
        """Step 1 (best of) of the post_result command"""
        try:
            parameter = int(parameter)
        except ValueError:
            raise commands.UserInputError
        if parameter < 0 or parameter % 2 != 1:
            raise commands.UserInputError
        post_result_message.best_of = parameter
        await ctx.message.delete()
        await self.update_post_result_setup_message(post_result_message, ctx.channel, 2)

    async def step2(self, ctx, tournament, post_result_message, parameter):
        """Step 2 (roll team1) of the post_result command"""
        try:
            parameter = int(parameter)
        except ValueError:
            raise commands.UserInputError
        if parameter < 1 or parameter > 100:
            raise commands.UserInputError
        post_result_message.roll_team1 = parameter
        await ctx.message.delete()
        await self.update_post_result_setup_message(post_result_message, ctx.channel, 3)

    async def step3(self, ctx, tournament, post_result_message, parameter):
        """Step 3 (roll team2) of the post_result command"""
        try:
            parameter = int(parameter)
        except ValueError:
            raise commands.UserInputError
        if parameter < 1 or parameter > 100:
            raise commands.UserInputError
        post_result_message.roll_team2 = parameter
        await ctx.message.delete()
        await self.update_post_result_setup_message(post_result_message, ctx.channel, 4)

    async def step4(self, ctx, tournament, post_result_message, parameter):
        """Step 4 (nb of warmups) of the post_result command"""
        try:
            parameter = int(parameter)
        except ValueError:
            raise commands.UserInputError
        if parameter < 0:
            raise commands.UserInputError
        post_result_message.n_warmup = parameter
        await ctx.message.delete()
        await self.update_post_result_setup_message(post_result_message, ctx.channel, 5)

    async def step5(self, ctx, tournament, post_result_message, parameter):
        """Step 5 (mp links) of the post_result command"""
        mp_links = []
        links = re.split(" |\n", parameter)
        for link in links:
            link = osu.get_from_string(link)
            mp_links.append(link)
        post_result_message.mp_links = "\n".join(mp_links)
        await ctx.message.delete()
        await self.update_post_result_setup_message(post_result_message, ctx.channel, 6)

    async def step6(self, ctx, tournament, post_result_message, parameter):
        """Step 6 (bans team1) of the post_result command"""
        post_result_message.bans_team1 = parameter
        await ctx.message.delete()
        await self.update_post_result_setup_message(post_result_message, ctx.channel, 7)

    async def step7_send_message(self, ctx, tournament, post_result_message):
        bracket = self.bot.session.query(Bracket).where(Bracket.id == post_result_message.bracket_id).first()
        if not bracket:
            self.bot.session.delete(post_result_message)
            raise tosurnament.NoBracket()
        schedules_spreadsheet = self.get_schedules_spreadsheet(bracket)
        if not schedules_spreadsheet:
            raise tosurnament.NoSpreadsheet("schedules")
        try:
            spreadsheet, worksheet = self.get_spreadsheet_worksheet(schedules_spreadsheet)
        except HttpError as e:
            raise tosurnament.SpreadsheetHttpError(e.code, e.operation, bracket.name, "schedules")
        match_info = MatchInfo.from_id(schedules_spreadsheet, worksheet, post_result_message.match_id, False)
        prbuilder = self.create_prbuilder(post_result_message, tournament, bracket, match_info)
        if tournament.post_result_message:
            result_string = tournament.post_result_message
        else:
            result_string = self.get_string("post_result", "default")
        result_string = prbuilder.build(result_string, self, tournament)
        message = await self.send_reply(
            ctx,
            "post_result",
            "step8",
            post_result_message.match_id,
            post_result_message.best_of,
            post_result_message.roll_team1,
            post_result_message.roll_team2,
            post_result_message.n_warmup,
            osu.build_mp_links(post_result_message.mp_links.split("\n")),
            post_result_message.bans_team1,
            post_result_message.bans_team2,
            post_result_message.tb_bans_team1,
            post_result_message.tb_bans_team2,
        )
        post_result_message.setup_message_id = message.id
        post_result_message.step = 8

        preview_message = await self.send_reply(ctx, "post_result", "preview", result_string)
        post_result_message.preview_message_id = preview_message.id

        return message

    async def step7(self, ctx, tournament, post_result_message, parameter):
        """Step 7 (bans team2) of the post_result command"""
        post_result_message.bans_team2 = parameter
        await ctx.message.delete()
        message = await ctx.channel.fetch_message(post_result_message.setup_message_id)
        await message.delete()
        message = await self.step7_send_message(ctx, tournament, post_result_message)
        self.bot.session.update(post_result_message)
        await self.add_reaction_to_setup_message(message)

    async def step8_write_in_spreadsheet(self, bracket, schedules_spreadsheet, spreadsheet, match_info, prbuilder):
        match_info.score_team1.value = prbuilder.get_score_team1()
        match_info.score_team2.value = prbuilder.get_score_team2()
        mp_links = osu.build_mp_links(prbuilder.mp_links.split("\n"))
        i = 0
        while i < len(match_info.mp_links) and i < len(mp_links):
            if i + 1 == len(match_info.mp_links):
                match_info.mp_links[i].value = "/".join(mp_links[i:])
            else:
                match_info.mp_links[i].value = mp_links[i]
            i += 1
        try:
            spreadsheet.update()
        except HttpError as e:
            raise tosurnament.SpreadsheetHttpError(e.code, e.operation, bracket.name, "schedules")

    async def step8_challonge(self, ctx, challonge_id, error_channel, prbuilder):
        try:
            tournament = challonge.get_tournament(challonge_id)
            if tournament.state == "pending":
                tournament.start()
            participant1 = None
            participant2 = None
            for participant in tournament.participants:
                if participant.name == prbuilder.team_name1:
                    participant1 = participant
                elif participant.name == prbuilder.team_name2:
                    participant2 = participant
            if not participant1 or not participant2:
                await self.send_reply(
                    error_channel, "post_result", "participant_not_found", prbuilder.match_id,
                )
                return
            participant_matches = participant1.matches
            for match in participant_matches:
                if participant1.has_id(match.player1_id) and participant2.has_id(match.player2_id):
                    match.update_score(prbuilder.score_team1, prbuilder.score_team2)
                    return
                elif participant2.has_id(match.player1_id) and participant1.has_id(match.player2_id):
                    match.update_score(prbuilder.score_team2, prbuilder.score_team1)
                    return
            raise tosurnament.MatchNotFound()
        except challonge.ChallongeException as e:
            await self.on_cog_command_error(error_channel, "post_result", e)
            return

    def create_prbuilder(self, post_result_message, tournament, bracket, match_info):
        prbuilder = PostResultBuilder()
        prbuilder.tournament_acronym = tournament.acronym
        prbuilder.tournament_name = tournament.name
        prbuilder.bracket_name = bracket.name
        prbuilder.match_id = post_result_message.match_id
        prbuilder.team_name1 = match_info.team1.value
        prbuilder.team_name2 = match_info.team2.value
        prbuilder.roll_team1 = post_result_message.roll_team1
        prbuilder.roll_team2 = post_result_message.roll_team2
        prbuilder.bans_team1 = post_result_message.bans_team1
        prbuilder.bans_team2 = post_result_message.bans_team2
        prbuilder.tb_bans_team1 = post_result_message.tb_bans_team1
        prbuilder.tb_bans_team2 = post_result_message.tb_bans_team2

        players_spreadsheet = self.get_players_spreadsheet(bracket)
        if players_spreadsheet:
            try:
                p_spreadsheet, p_worksheet = self.get_spreadsheet_worksheet(players_spreadsheet)
            except HttpError as e:
                raise tosurnament.SpreadsheetHttpError(e.code, e.operation, bracket.name, "players")
            team1_info = TeamInfo.from_team_name(prbuilder.team_name1)
            team2_info = TeamInfo.from_team_name(prbuilder.team_name2)
            players_id_team1 = get_players_id(team1_info)
            players_id_team2 = get_players_id(team2_info)
        else:
            players_id_team1 = osu.usernames_to_ids([prbuilder.team_name1])
            players_id_team2 = osu.usernames_to_ids([prbuilder.team_name2])

        score_team1 = post_result_message.score_team1
        score_team2 = post_result_message.score_team2
        if score_team1 < 0 and score_team2 < 0:
            score_team1, score_team2 = calc_match_score(post_result_message, players_id_team1, players_id_team2)
        prbuilder.score_team1 = score_team1
        prbuilder.score_team2 = score_team2
        prbuilder.mp_links = post_result_message.mp_links
        return prbuilder

    async def step8_per_bracket(self, ctx, post_result_message, tournament, bracket):
        schedules_spreadsheet = self.get_schedules_spreadsheet(bracket)
        if not schedules_spreadsheet:
            raise tosurnament.NoSpreadsheet("schedules")
        try:
            spreadsheet, worksheet = self.get_spreadsheet_worksheet(schedules_spreadsheet)
        except HttpError as e:
            raise tosurnament.SpreadsheetHttpError(e.code, e.operation, bracket.name, "schedules")
        match_info = MatchInfo.from_id(schedules_spreadsheet, worksheet, post_result_message.match_id, False)
        prbuilder = self.create_prbuilder(post_result_message, tournament, bracket, match_info)
        if tournament.post_result_message:
            result_string = tournament.post_result_message
        else:
            result_string = self.get_string("post_result", "default")
        result_string = prbuilder.build(result_string, self, tournament)
        if bracket.challonge:
            if tournament.staff_channel_id:
                error_channel = self.bot.get_channel(tournament.staff_channel_id)
            else:
                error_channel = ctx
            await self.step8_challonge(ctx, bracket.challonge, error_channel, prbuilder)
        await self.step8_write_in_spreadsheet(bracket, schedules_spreadsheet, spreadsheet, match_info, prbuilder)
        post_result_channel = ctx
        if bracket.post_result_channel_id:
            post_result_channel = self.bot.get_channel(bracket.post_result_channel_id)
        await post_result_channel.send(result_string)

    async def step8(self, ctx, tournament, post_result_message, parameter):
        """Step 8 of the post_result command"""
        if parameter == "post":
            bracket = self.bot.session.query(Bracket).where(Bracket.id == post_result_message.bracket_id).first()
            if not bracket:
                raise tosurnament.NoBracket()
            await self.step8_per_bracket(ctx, post_result_message, tournament, bracket)
            self.bot.session.delete(post_result_message)
            message = await ctx.channel.fetch_message(post_result_message.setup_message_id)
            await message.delete()
            message = await ctx.channel.fetch_message(post_result_message.preview_message_id)
            await message.delete()
            await ctx.message.delete()

    @commands.command(aliases=["a"])
    async def answer(self, ctx, *, parameter: str):
        """Allows referees to setup the result message"""
        tournament = self.get_tournament(ctx.guild.id)
        post_result_message = (
            self.bot.session.query(PostResultMessage)
            .where(PostResultMessage.tournament_id == tournament.id)
            .where(PostResultMessage.referee_id == ctx.author.id)
            .first()
        )
        if not post_result_message:
            return
        steps = [
            self.step1,
            self.step2,
            self.step3,
            self.step4,
            self.step5,
            self.step6,
            self.step7,
            self.step8,
        ]
        await steps[post_result_message.step - 1](ctx, tournament, post_result_message, parameter)

    async def on_raw_reaction_add(self, message_id, emoji, guild, channel, user):
        """on_raw_reaction_add of the Tosurnament post_result module"""
        await self.reaction_on_setup_message(message_id, emoji, guild, channel, user)

    async def reaction_on_setup_message(self, message_id, emoji, guild, channel, user):
        """Change the setup message step"""
        try:
            tournament = self.get_tournament(guild.id)
        except tosurnament.NoTournament:
            return
        post_result_message = (
            self.bot.session.query(PostResultMessage)
            .where(PostResultMessage.tournament_id == tournament.id)
            .where(PostResultMessage.referee_id == user.id)
            .first()
        )
        if not post_result_message or post_result_message.setup_message_id <= 0:
            return
        emoji_steps = ["1⃣", "2⃣", "3⃣", "4⃣", "5⃣", "6⃣", "7⃣", "8⃣"]
        if emoji.name not in emoji_steps:
            return
        await self.update_post_result_setup_message(post_result_message, channel, emoji_steps.index(emoji.name) + 1)

    async def add_reaction_to_setup_message(self, message):
        try:
            await message.add_reaction("1⃣")
            await message.add_reaction("2⃣")
            await message.add_reaction("3⃣")
            await message.add_reaction("4⃣")
            await message.add_reaction("5⃣")
            await message.add_reaction("6⃣")
            await message.add_reaction("7⃣")
            await message.add_reaction("8⃣")
        except Exception:
            return

    async def update_post_result_setup_message(self, post_result_message, channel, new_step):
        message = await channel.fetch_message(post_result_message.setup_message_id)
        await message.delete()
        if post_result_message.preview_message_id:
            message = await channel.fetch_message(post_result_message.preview_message_id)
            await message.delete()
            post_result_message.preview_message_id = 0
        message = await self.send_reply(
            channel,
            "post_result",
            "step" + str(new_step),
            post_result_message.match_id,
            post_result_message.best_of,
            post_result_message.roll_team1,
            post_result_message.roll_team2,
            post_result_message.n_warmup,
            osu.build_mp_links(post_result_message.mp_links.split("\n")),
            post_result_message.bans_team1,
            post_result_message.bans_team2,
            post_result_message.tb_bans_team1,
            post_result_message.tb_bans_team2,
        )
        post_result_message.setup_message_id = message.id
        post_result_message.step = new_step
        self.bot.session.update(post_result_message)
        await self.add_reaction_to_setup_message(message)

    async def post_result_common_handler(self, ctx, error):
        if isinstance(error, tosurnament.InvalidMatchId):
            await self.send_reply(ctx, "post_result", "invalid_match_id")
        elif isinstance(error, tosurnament.InvalidMpLink):
            await self.send_reply(ctx, "post_result", "invalid_mp_link")
        elif isinstance(error, tosurnament.MatchNotFound):
            await self.send_reply(ctx, "post_result", "match_not_found")

    @post_result.error
    async def post_result_handler(self, ctx, error):
        """Error handler of post_result function"""
        await self.post_result_common_handler(ctx, error)

    @post_result_with_scores.error
    async def post_result_with_scores_handler(self, ctx, error):
        """Error handler of post_result_with_scores function"""
        await self.post_result_common_handler(ctx, error)


def get_class(bot):
    """Returns the main class of the module"""
    return TosurnamentPostResultCog(bot)


def setup(bot):
    """Setups the cog"""
    bot.add_cog(TosurnamentPostResultCog(bot))