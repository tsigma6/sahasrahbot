import datetime
import logging
import os

import aiohttp
import discord

from alttprbot import models
from alttprbot.exceptions import SahasrahBotException
from alttprbot_discord.bot import discordbot
from alttprbot_racetime import bot as racetime

TOURNAMENT_RESULTS_SHEET = os.environ.get('TOURNAMENT_RESULTS_SHEET', None)
RACETIME_URL = os.environ.get('RACETIME_URL', 'https://racetime.gg')
APP_URL = os.environ.get('APP_URL', 'https://sahasrahbotapi.synack.live')

class UnableToLookupUserException(SahasrahBotException):
    pass


class UnableToLookupEpisodeException(SahasrahBotException):
    pass

class TournamentPlayerBase(object):
    def __init__(self):
        self.name = None
        self.discord_id = None
        self.discord_user = None
        self.racetime_id = None

    @classmethod
    async def construct(cls, discord_id, guild):
        playerobj = cls()

        srlnick = await models.SRLNick.get_or_none(discord_user_id=discord_id)

        playerobj.discord_user = guild.get_member(discord_id)
        playerobj.discord_id = discord_id
        playerobj.name = playerobj.discord_user.name

        if srlnick:
            playerobj.racetime_id = srlnick.rtgg_id

        return playerobj


class TournamentRaceBase(object):
    def __init__(self, episode_id: int, event: str, racetime_category: racetime.SahasrahBotRaceTimeBot):
        self.episode_id = int(episode_id)
        self.schedule = "sahasrahbot"
        self.racetime_category = racetime_category
        self.event = event

    @classmethod
    async def construct(cls, episode_id: int, event: str, racetime_category: racetime.SahasrahBotRaceTimeBot):
        tournament_race = cls(episode_id, event, racetime_category)
        await discordbot.wait_until_ready()
        tournament_race.data = await models.Tournaments.get_or_none(tournament_race.event)

        await tournament_race.update_data()
        return tournament_race

    async def update_data(self):
        pass

    async def make_tournament_player(self, player):
        pass

    async def send_audit_message(self):
        pass

    async def send_commentator_message(self):
        pass

    async def send_player_dm(self):
        pass

    async def roll(self):
        pass

    async def start_race_processing(self):
        await self.racetime_handler.send_message("Generating game, please wait.  If nothing happens after a minute, contact Synack.")

    async def end_race_processing(self):
        await self.racetime_handler.send_message("Seed has been generated, you should have received a DM in Discord.  Please contact a Tournament Moderator if you haven't received the DM.")

    async def race_start(self):
        race_id = self.racetime_handler.data.get('name')

        if race_id is None:
            return

        race = await models.TournamentResults.get_or_none(srl_id=race_id)

        if race:
            race.status = "STARTED"
            await race.save(update_fields=['status'])

    async def create_or_get_race_room(self, settings):
        race = await models.TournamentResults.get_or_none(episode_id=self.episode_id, status=None)
        if race:
            async with aiohttp.request(method='get', url=self.racetime_category.http_uri(f"/{race.srl_id}/data"), raise_for_status=True) as resp:
                race_data = await resp.json()

            status = race_data.get('status', {}).get('value')
            if status == 'cancelled':
                await race.delete()
                return

            if status == 'finished':
                race.status = "FINISHED"
                await race.save(update_fields=['status'])

            self.racetime_handler = await self.racetime_category.create_handler(race_data)

        self.racetime_handler = await self.racetime_category.startrace(**settings)

        self.racetime_handler.tournament = self

        logging.info(self.racetime_handler.data.get('name'))
        await models.TournamentResults.create(srl_id=self.racetime_handler.data.get('name'), episode_id=self.episode_id, event=self.event_slug)

        for rtggid in self.player_racetime_ids:
            await self.racetime_handler.invite_user(rtggid)

        embed = discord.Embed(
            title=f"RT.gg Room Opened - {self.versus}",
            description=f"Greetings!  A RaceTime.gg race room has been automatically opened for you.\nYou may access it at {self.racetime_url}\n\nEnjoy!",
            color=discord.Colour.blue(),
            timestamp=datetime.datetime.now()
        )

        for name, player in self.player_discords:
            if player is None:
                logging.info(f'Could not DM {name}')
                continue
            try:
                await player.send(embed=embed)
            except discord.HTTPException:
                logging.info(f'Could not send room opening DM to {name}')
                continue

        await self.send_ractime_greeting()

        return self.racetime_handler

    @property
    def submit_link(self):
        return f"{APP_URL}/{self.event_slug}?episode_id={self.episodeid}"

    @property
    def game_number(self):
        if self.bracket_settings:
            return self.bracket_settings.get('game_number', None)
        return None

    @property
    def friendly_name(self):
        return None

    @property
    def versus(self):
        return ' vs. '.join(self.player_names)

    @property
    def player_discords(self):
        return [(p.name, p.discord_user) for p in self.players]

    @property
    def player_racetime_ids(self):
        return [p.data['rtgg_id'] for p in self.players]

    @property
    def player_names(self):
        return [p.name for p in self.players]

    @property
    def broadcast_channels(self):
        return None

    @property
    def racetime_room_name(self):
        return self.racetime_handler.data.get('name')

    @property
    def racetime_url(self):
        return self.racetime_handler.bot.http_uri(self.racetime_handler.data['url'])

    async def can_gatekeep(self, rtgg_id):
        guild = discordbot.get_guild(self.data.guild_id)
        nickname = await models.SRLNick.get_or_none(rtgg_id=rtgg_id)

        if not nickname:
            return False

        discord_user = guild.get_member(nickname.discord_user_id)

        if not discord_user:
            return False

        if helper_roles := self.data.helper_roles:
            if discord.utils.find(lambda m: m.name in helper_roles.split(','), discord_user.roles):
                return True

        return False
