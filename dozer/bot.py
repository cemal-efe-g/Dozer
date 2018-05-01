"""Bot object for Dozer"""

import logging
import re
import sys
import traceback
import discord
from discord.ext import commands

from . import utils

DOZER_LOGGER = logging.Logger(name='dozer')
DOZER_LOGGER.level = logging.INFO
DOZER_HANDLER = logging.StreamHandler(stream=sys.stdout)
DOZER_HANDLER.level = logging.INFO
DOZER_LOGGER.addHandler(DOZER_HANDLER)
DOZER_HANDLER.setFormatter(fmt=logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s'))

if discord.version_info.major < 1:
    DOZER_LOGGER.error("Your installed discord.py version is too low "
                       "%d.%d.%d, please upgrade to at least 1.0.0a" % discord.version_info.major,
                       discord.version_info.minor,
                       discord.version_info.micro)
    sys.exit(1)


class InvalidContext(commands.CheckFailure):
    """
    Check failure raised by the global check for an invalid command context - executed by a bot, exceeding global rate-limit, etc.
    The message will be ignored.
    """


class DozerContext(commands.Context):
    async def send(self, content=None, **kwargs):
        if content is not None:
            content = utils.clean(self, content, mass=True, member=False, role=False, channel=False)
        return await super().send(content, **kwargs)


class Dozer(commands.Bot):
    _global_cooldown = commands.Cooldown(1, 1, commands.BucketType.user)  # One command per second per user

    def __init__(self, config):
        super().__init__(command_prefix=config['prefix'])
        self.config = config
        self.check(self.global_checks)

    async def on_ready(self):
        DOZER_LOGGER.info('Signed in as %d!s (%d.id)'% self.user)
        if self.config['is_backup']:
            status = discord.Status.dnd
        else:
            status = discord.Status.online
        game = discord.Game(name='%shelp | %d guilds' % (self.config['prefix'], len(self.guilds)))
        try:
            await self.change_presence(activity=game, status=status)
        except TypeError:
            DOZER_LOGGER.warning("You are running an older version of the discord.py rewrite (with breaking changes)! "
                                 "To upgrade, run `pip install -r requirements.txt --upgrade`")
            await self.change_presence(game=game, status=status)


    async def get_context(self, message):
        ctx = await super().get_context(message, cls=DozerContext)
        return ctx

    async def on_command_error(self, ctx, err):
        if isinstance(err, commands.NoPrivateMessage):
            await ctx.send('{}, This command cannot be used in DMs.'.format(ctx.author.mention))
        elif isinstance(err, commands.UserInputError):
            await ctx.send('{}, {}'.format(ctx.author.mention, self.format_error(ctx, err)))
        elif isinstance(err, commands.NotOwner):
            await ctx.send('{}, {}'.format(ctx.author.mention, err.args[0]))
        elif isinstance(err, commands.MissingPermissions):
            permission_names = [name.replace('guild', 'server').replace('_', ' ').title() for name in err.missing_perms]
            await ctx.send('{}, you need {} permissions to run this command!'.format(
                ctx.author.mention, utils.pretty_concat(permission_names)))
        elif isinstance(err, commands.BotMissingPermissions):
            permission_names = [name.replace('guild', 'server').replace('_', ' ').title() for name in err.missing_perms]
            await ctx.send('{}, I need {} permissions to run this command!'.format(
                ctx.author.mention, utils.pretty_concat(permission_names)))
        elif isinstance(err, commands.CommandOnCooldown):
            await ctx.send(
                '{}, That command is on cooldown! Try again in {:.2f}s!'.format(ctx.author.mention, err.retry_after))
        elif isinstance(err, (commands.CommandNotFound, InvalidContext)):
            pass  # Silent ignore
        else:
            await ctx.send('```\n%s\n```' % ''.join(traceback.format_exception_only(type(err), err)).strip())
            if isinstance(ctx.channel, discord.TextChannel):
                DOZER_LOGGER.error('Error in command <%d> (%d.name!r(%d.id) %d(%d.id) %d(%d.id) %d)' %
                                   ctx.command, ctx.guild, ctx.channel, ctx.author, ctx.message.content)
            else:
                DOZER_LOGGER.error('Error in command <%d> (DM %d(%d.id) %d)' % ctx.command, ctx.channel.recipient,
                                   ctx.message.content)
            DOZER_LOGGER.error(''.join(traceback.format_exception(type(err), err, err.__traceback__)))

    @staticmethod
    def format_error(ctx, err, *, word_re=re.compile('[A-Z][a-z]+')):
        type_words = word_re.findall(type(err).__name__)
        type_msg = ' '.join(map(str.lower, type_words))

        if err.args:
            return '%s: %s' % (type_msg, utils.clean(ctx, err.args[0]))
        else:
            return type_msg

    def global_checks(self, ctx):
        if ctx.author.bot:
            raise InvalidContext('Bots cannot run commands!')
        retry_after = self._global_cooldown.update_rate_limit()
        if retry_after:
            raise InvalidContext('Global rate-limit exceeded!')
        return True

    def run(self):
        token = self.config['discord_token']
        del self.config['discord_token']  # Prevent token dumping
        super().run(token)

    async def shutdown(self):
        await self.logout()
        await self.close()
        self.loop.stop()
