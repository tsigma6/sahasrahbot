from pyz3r.sm import smClass
import discord

class SMDiscord(smClass):
    def __init__(self, *args, **kwargs):
        super(SMDiscord, self).__init__(*args, **kwargs)
        self.randomizer = 'sm'
        self.baseurl = 'https://sm.samus.link'

    @property
    def generated_goal(self):
        return "sm"

    async def embed(self, name="Requested Seed", notes="Requested SM Randomizer Game.", emojis=None):
        embed = discord.Embed(
            title=name,
            description=notes,
            color=discord.Colour.dark_red()
        )

        embed.add_field(name='File Select Code', value=self.code, inline=False)
        embed.add_field(name='Permalink', value=self.url, inline=False)
        embed.set_footer(text="Generated by SahasrahBot")
        return embed

    async def tournament_embed(self, name='Requested Tournament Seed', notes='See notes', emojis=None):
        embed = discord.Embed(
            title=name,
            description=notes,
            color=discord.Colour.dark_gold()
        )

        embed.add_field(name='File Select Code', value=self.code, inline=False)
        embed.set_footer(text="Generated by SahasrahBot")
        return embed

class SMZ3Discord(smClass):
    def __init__(self, *args, **kwargs):
        super(SMZ3Discord, self).__init__(*args, **kwargs)
        self.randomizer = 'smz3'
        self.baseurl = 'https://samus.link'

    @property
    def generated_goal(self):
        return "smz3"

    async def embed(self, name="Requested Seed", notes="Requested SMZ3 Game.", emojis=None):
        embed = discord.Embed(
            title=name,
            description=notes,
            color=discord.Colour.dark_red()
        )

        embed.add_field(name='File Select Code', value=self.code, inline=False)
        embed.add_field(name='Permalink', value=self.url, inline=False)
        embed.set_footer(text="Generated by SahasrahBot")
        return embed

    async def tournament_embed(self, name='Requested Tournament Seed', notes='See notes', emojis=None):
        embed = discord.Embed(
            title=name,
            description=notes,
            color=discord.Colour.dark_gold()
        )

        embed.add_field(name='File Select Code', value=self.code, inline=False)
        embed.set_footer(text="Generated by SahasrahBot")
        return embed