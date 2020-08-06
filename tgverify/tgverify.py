#Standard Imports
import logging
from typing import Union

#Discord Imports
import discord

#Redbot Imports
from redbot.core import commands, checks, Config


__version__ = "1.0.0"
__author__ = "oranges"

log = logging.getLogger("red.oranges_tgverify")

BaseCog = getattr(commands, "Cog", object)

#Subtype the commands checkfailure
class UnableToVerify(commands.CheckFailure):
    pass

class TGverifySystemError(commands.CheckFailure):
    pass

class TGverify(BaseCog):
    """
    Connector that will integrate with any database using the latest tg schema, provides utility functionality
    """
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=672261474290237490, force_registration=True)
        self.visible_config = ["min_living_minutes", "verified_role"]

        default_guild = {
            "min_living_minutes": 60,
            "verified_role": None,
        }

        self.config.register_guild(**default_guild)
    

    @commands.guild_only()
    @commands.group()
    @checks.admin_or_permissions(administrator=True)
    async def tgverify_config(self,ctx): 
        """
        SS13 Configure the MySQL database connection settings
        """
        pass
    
    @checks.mod_or_permissions(administrator=True)
    @tgverify_config.command()
    async def current(self, ctx):
        """
        Gets the current settings for the notes database
        """
        settings = await self.config.guild(ctx.guild).all()
        embed=discord.Embed(title="__Current settings:__")
        for k, v in settings.items():
            # Ensures that the database password is not sent
            # Whitelist for extra safety
            if k in self.visible_config:
                if v == "":
                    v = None
                embed.add_field(name=f"{k}:",value=v,inline=False)
            else:
                embed.add_field(name=f"{k}:",value="`redacted`",inline=False)
        await ctx.send(embed=embed)


    @tgverify_config.command()
    async def living_minutes(self, ctx, min_living_minutes: int = None):
        """
        Sets the minimum required living minutes before this bot will apply a verification role to a user
        """
        try:
            if min_living_minutes is None:
                await self.config.guild(ctx.guild).min_living_minutes.set(0)
                await ctx.send(f"Minimum living minutes required for verification removed!")
            else:
                await self.config.guild(ctx.guild).min_living_minutes.set(min_living_minutes)
                await ctx.send(f"Minimum living minutes required for verification set to: `{min_living_minutes}`")
        
        except (ValueError, KeyError, AttributeError):
            await ctx.send("There was a problem setting the minimum required living minutes")

    @tgverify_config.command()
    async def verified_role(self, ctx, verified_role: int = None):
        """
        Set what role is applied when a user verifies
        """
        try:
            role = ctx.guild.get_role(verified_role)
            if not role:
                return await ctx.send(f"This is not a valid role for this discord!")
            if verified_role is None:
                await self.config.guild(ctx.guild).verified_role.set(None)
                await ctx.send(f"No role will be set when the user verifies!")
            else:
                await self.config.guild(ctx.guild).verified_role.set(verified_role)
                await ctx.send(f"When a user meets minimum verification this role will be applied: `{verified_role}`")
        
        except (ValueError, KeyError, AttributeError):
            await ctx.send("There was a problem setting the verified role")    

    @commands.command()
    async def verify(self, ctx, *, one_time_token: str):
        """
        Attempt to verify the user, based on the passed in one time code
        """
        #Get the minimum required living minutes
        min_required_living_minutes = await self.config.guild(ctx.guild).min_living_minutes()
        role = await self.config.guild(ctx.guild).verified_role()
        role = ctx.guild.get_role(role)
        TGDB = self.bot.get_cog("TGDB")
        if not TGDB:
            raise TGverifySystemError("TGDB must exist and be configured for tgverify cog to work")

        message = await ctx.send("Attempting to verify you....")
        async with ctx.typing():
            # First lets try to remove their one time token
            try:
                await ctx.message.delete()
            except(discord.DiscordException):
                await ctx.send("I do not have the required permissions to delete messages, please remove/edit the one time token. manually.")
            # Attempt to find the user based on the one time token passed in.
            ckey = await TGDB.lookup_ckey_by_token(ctx, one_time_token)
            if ckey is None:
                    raise UnableToVerify(f"Sorry {ctx.author} looks like we don't recognise this one use token, or couldn't link it to a user account, go back into game and generate another! if it's still failing, ask for support from the verification team")
            
            
            log.info(f"Verification request by {ctx.author.id}, for ckey {ckey}")
            # Now look for the user based on the ckey
            player = await TGDB.get_player_by_ckey(ctx, ckey)
            
            if player is None:
                raise UnableToVerify(f"Sorry {ctx.author} looks like we couldn't look up your user, ask the verification team for support!")

            if player['living_time'] <= min_required_living_minutes:
                return await message.edit(content=f"Sorry {ctx.author} you only have {player['living_time']} minutes as a living player on our servers, and you require at least {min_required_living_minutes}! You will need to play more on our servers to access all the discord channels")
    
            if role:
                await ctx.author.add_roles(role, reason="User has verified against their in game living minutes")
        
        # Record that the user is linked against a discord id
        await TGDB.update_discord_link(ctx, one_time_token, ctx.author.id)
        return await message.edit(content=f"Congrats {ctx.author} your verification is complete", color=0xff0000)

    @verify.error
    async def verify_error(self, ctx, error):
        # Our custom, something recoverable went wrong error type
        if isinstance(error, UnableToVerify):
            embed=discord.Embed(title=f"Error attempting to verify you:", description=f"{format(error)}", color=0xff0000)
            await ctx.send(content=f"", embed=embed)
        else:
            # Something went badly wrong, log to the console
            log.error("Internal error while verifying", error)
            # now pretend everything is fine to the user :>
            embed=discord.Embed(title=f"System error occurred", description=f"Contact the server admins for assistance", color=0xff0000)
            await ctx.send(content=f"", embed=embed)
