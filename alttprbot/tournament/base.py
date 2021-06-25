import datetime
import logging
import os

import aiohttp
import discord

from alttprbot import models
from alttprbot.exceptions import SahasrahBotException
from alttprbot_discord.bot import discordbot
from alttprbot_racetime import bot as racetime
from alttprbot.util import speedgaming

TOURNAMENT_RESULTS_SHEET = os.environ.get('TOURNAMENT_RESULTS_SHEET', None)
RACETIME_URL = os.environ.get('RACETIME_URL', 'https://racetime.gg')
APP_URL = os.environ.get('APP_URL', 'https://sahasrahbotapi.synack.live')

class UnableToLookupUserException(SahasrahBotException):
    pass


class UnableToLookupEpisodeException(SahasrahBotException):
    pass

class Tournament(object):
    def __init__(self, event):
        self.data = None
        self.audit_channel = None
        self.commentary_channel = None
        self.scheduling_needs_channel = None
        self.mod_channel = None
        self.event = event
        self.racetime_category = None

    @classmethod
    async def construct(cls, event):
        tournament = cls(event)
        await tournament.update()

    async def update(self):
        self.data = await models.Tournaments.get(self.event)
        self.racetime_category = racetime.racetime_bots[self.data.category]

        self.guild = discordbot.get_guild(self.data.guild_id)

        if self.data.audit_channel_id:
            self.audit_channel = discordbot.get_channel(self.data.audit_channel_id)

        if self.data.commentary_channel_id:
            self.commentary_channel = discordbot.get_channel(self.data.commentary_channel_id)

        if self.data.scheduling_needs_channel_id:
            self.scheduling_needs_channel = discordbot.get_channel(self.data.scheduling_needs_channel_id)

        if self.data.mod_channel_id:
            self.mod_channel = discordbot.get_channel(self.data.mod_channel_id)

class TournamentPerson(object):
    def __init__(self):
        self.name = None
        self.discord_id = None
        self.discord_user = None
        self.racetime_id = None
        self.twitch_name = None

    @classmethod
    async def construct(cls, discord_id, guild):
        person = cls()

        srlnick = await models.SRLNick.get_or_none(discord_user_id=discord_id)

        person.discord_user = guild.get_member(discord_id)
        person.discord_id = discord_id
        person.name = person.discord_user.name

        if srlnick:
            person.racetime_id = srlnick.rtgg_id
            person.twitch_name = srlnick.twitch_name

        return person


class TournamentRaceSpeedGaming(object):
    def __init__(self, episode_id: int, tournament: Tournament):
        self.episode_id = int(episode_id)
        self.schedule = "speedgaming"
        self.tournament = tournament

    @classmethod
    async def construct(cls, episode_id: int, tournament: Tournament):
        await discordbot.wait_until_ready()

        tournament_race = cls(episode_id, tournament)
        await tournament_race.update_data()
        return tournament_race

    async def update_data(self):
        self.episode = await speedgaming.get_episode(self.episodeid)

        if self.episode is None:
            raise UnableToLookupEpisodeException('SG Episode ID not a recognized event.  This should not have happened.')

        self.players = await self.lookup_persons(self.episode['match1']['players'])
        self.commentators = await self.lookup_persons([c for c in self.episode['commentators'] if c['approved']])
        self.trackers = await self.lookup_persons([c for c in self.episode['trackers'] if c['approved']])
        self.broadcasters = await self.lookup_persons([c for c in self.episode['broadcasters'] if c['approved']])

        # self.bracket_settings = await tournament_games.get_game_by_episodeid_submitted(self.episodeid)
        self.seed_settings = await models.TournamentGames.get_or_none(episode_id=self.episode_id)

    @staticmethod
    async def lookup_persons(data):
        persons = []
        for p in data:
            # first try a more concrete match of using the discord id cached by SG
            looked_up_player = await TournamentPerson.construct(discord_id=int(p['discordId']), guild=self.guild)
            if looked_up_player:
                persons.append(looked_up_player)
                continue

            looked_up_player = await TournamentPerson.construct(discord_id=int(p['discordTag']), guild=self.guild)
            if looked_up_player:
                persons.append(looked_up_player)
                continue

            raise UnableToLookupUserException(f"Cannot lookup {p['displayName']}")

        return persons

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
    def event_name(self):
        return self.episode['event']['shortName']

    @property
    def event_slug(self):
        return self.episode['event']['slug']

    @property
    def friendly_name(self):
        return self.episode['match1']['title']

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
        return [a['name'] for a in self.episode['channels'] if not " " in a['name']]

    @property
    def racetime_room_name(self):
        return self.tournament.racetime_handler.data.get('name')

    @property
    def racetime_url(self):
        return self.tournament.racetime_handler.bot.http_uri(self.tournament.racetime_handler.data['url'])

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
