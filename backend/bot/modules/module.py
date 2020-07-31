"""Base of all modules. Contains utility functions."""

import inspect
import discord
from discord.ext import commands
from common.exceptions import *
from common.utils import load_json
from common.databases.guild import Guild
from common.databases.user import User

DEFAULT_HELP_EMBED_COLOR = 3447003
COMMAND_NOT_FOUND_EMBED_COLOR = 3447003


class BaseModule(commands.Cog):
    """Contains utility functions used by modules."""

    def __init__(self, bot):
        self.bot = bot

    def get_guild(self, guild_id):
        return self.bot.session.query(Guild).where(Guild.guild_id == guild_id).first()

    def get_user(self, discord_id):
        """Gets the User from their discord id."""
        return self.bot.session.query(User).where(User.discord_id == discord_id).first()

    def get_verified_user(self, discord_id):
        """Gets the User from their discord id, but only if they are verified."""
        user = self.get_user(discord_id)
        if not user:
            raise UserNotLinked()
        if not user.verified:
            raise UserNotVerified()
        return user

    def get_string(self, command_name, field_name, *args):
        """Gets string from strings.json file"""
        module_name = inspect.getmodule(inspect.stack()[1][0]).__name__[12:]
        reply = self.find_reply(self.bot.strings, field_name, module_name.split(".") + [command_name])
        if reply:
            return load_json.replace_in_string(reply, self.bot.command_prefix, *args)
        else:
            print("ERROR: reply not found: " + field_name)  # ! To transform to log
        return ""

    async def send_message(self, channel, reply, *args):
        """Sends back a message/embed response."""
        content = None
        embed = None
        if isinstance(reply, dict):
            reply = load_json.replace_in_object(reply, self.bot.command_prefix, *args)
            if "content" in reply:
                content = reply["content"]
            if "embed" in reply:
                embed = discord.Embed.from_dict(reply["embed"])
        else:
            content = load_json.replace_in_string(reply, self.bot.command_prefix, *args)
        return await channel.send(content, embed=embed)

    def find_reply(self, replies, field_name, modules):
        reply = None
        if modules and modules[0] in replies:
            reply = self.find_reply(replies[modules[0]], field_name, modules[1:])
        if reply:
            return reply
        elif field_name in replies:
            return replies[field_name]
        elif "module" in replies and field_name in replies["module"]:
            return replies["module"][field_name]
        return None

    async def send_reply(self, channel, command_name, field_name, *args):
        """Sends a reply found in the replies files."""
        module_name = inspect.getmodule(inspect.stack()[1][0]).__name__[12:]
        reply = self.find_reply(self.bot.strings, field_name, module_name.split(".") + [command_name])
        if reply:
            return await self.send_message(channel, reply, *args)
        else:
            print("ERROR: reply not found: " + field_name)  # ! To transform to log
        return None

    async def send_usage(self, ctx):
        """Sends a usage reply found in the replies files."""
        reply = self.bot.strings
        module_name = inspect.getmodule(inspect.stack()[2][0]).__name__[12:]
        modules = module_name.split(".")
        if modules and modules[-1] == "module":
            modules = modules[:-1]
        reply = self.find_reply(self.bot.strings, "usage", modules + [ctx.command.cog_name, ctx.command.name])
        if reply:
            return await self.send_message(ctx, reply)
        return None

    async def cog_command_error(self, ctx, error):
        await self.on_cog_command_error(ctx, ctx.command.name, error)

    async def on_cog_command_error(self, channel, command_name, error):
        self.bot.info(str(type(error)) + ": " + str(error))
        if isinstance(error, commands.MissingRequiredArgument):
            await self.send_usage(channel)
        elif isinstance(error, commands.BadArgument):
            await self.send_usage(channel)
        elif isinstance(error, commands.UserInputError):
            await self.send_usage(channel)
        elif isinstance(error, commands.NoPrivateMessage):
            await self.send_reply(channel, command_name, "not_on_a_server")
        elif isinstance(error, commands.DisabledCommand):
            await self.send_reply(channel, command_name, "disabled_command")
        elif isinstance(error, commands.BotMissingPermissions):
            for missing_permission in error.missing_perms:
                if missing_permission == "manage_nicknames":
                    await self.send_reply(channel, command_name, "change_nickname_forbidden")
                    return
                elif missing_permission == "manage_roles":
                    await self.send_reply(channel, command_name, "change_role_forbidden")
                    return
        elif isinstance(error, UnknownError):
            await self.send_reply(channel, command_name, "unknown_error")
        elif isinstance(error, NotGuildOwner):
            await self.send_reply(channel, command_name, "not_guild_owner")
        elif isinstance(error, NotBotAdmin):
            await self.send_reply(channel, command_name, "no_rights")
        elif isinstance(error, InvalidRoleName):
            await self.send_reply(channel, command_name, "invalid_role_name", error.role_name)
        elif isinstance(error, RoleDoesNotExist):
            await self.send_reply(channel, command_name, "role_does_not_exist", error.role)
        elif isinstance(error, NotRequiredRole):
            await self.send_reply(channel, command_name, "not_required_role", error.role)
        elif isinstance(error, UserNotFound):
            await self.send_reply(channel, command_name, "user_not_found", error.username)
        elif isinstance(error, UserNotLinked):
            await self.send_reply(channel, command_name, "not_linked")
        elif isinstance(error, UserNotVerified):
            await self.send_reply(channel, command_name, "not_verified")
        elif isinstance(error, OsuError):
            await self.send_reply(channel, command_name, "osu_error")
        else:
            return False
        return True


def is_guild_owner():
    """Check function to know if the author is the guild owner."""

    async def predicate(ctx):
        if not ctx.guild:
            raise commands.NoPrivateMessage()
        if ctx.guild.owner != ctx.author:
            raise NotGuildOwner()
        return True

    return commands.check(predicate)


def get_role(roles, role_id=None, role_name=None):
    """Gets a role from its id or name."""
    for role in roles:
        if role_id and role.id == role_id:
            return role
        if role_name and role.name == role_name:
            return role
    return None
