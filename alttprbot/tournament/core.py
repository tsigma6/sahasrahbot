from alttprbot.exceptions import SahasrahBotException
from alttprbot.util import speedgaming
from alttprbot.database import (tournament_results, srlnick, tournaments, tournament_games)
from alttprbot_discord.bot import discordbot
from alttprbot_racetime import bot as racetime

class UnableToLookupUserException(SahasrahBotException):
    pass


class TournamentPlayer():
    def __init__(self):
        pass

    @classmethod
    async def construct(cls, discord_id: int, guild):
        playerobj = cls()

        result = await srlnick.get_nickname(discord_id)
        playerobj.data = result
        playerobj.discord_user = guild.get_member(result['discord_user_id'])
        playerobj.name = playerobj.discord_user.name

        return playerobj

    @classmethod
    async def construct_discord_name(cls, discord_name: str, guild):
        playerobj = cls()

        playerobj.discord_user = guild.get_member_named(discord_name)
        playerobj.name = discord_name
        result = await srlnick.get_nickname(playerobj.discord_user.id)
        playerobj.data = result

        return playerobj


class SpeedgamingTournamentRace():
    def __init__(self, episodeid: int):
        self.episodeid = int(episodeid)
        self.players = []

    @classmethod
    async def construct(cls, episodeid):
        tournament_race = cls(episodeid)
        await tournament_race.update_data()

        # commentary_channel_id = tournament_race.data['commentary_channel_id']
        # if commentary_channel_id is not None:
        #     tournament_race.commentary_channel = discordbot.get_channel(int(commentary_channel_id))
        # else:
        #     tournament_race.commentary_channel = None

        # audit_channel_id = tournament_race.data['audit_channel_id']
        # if audit_channel_id is not None:
        #     tournament_race.audit_channel = discordbot.get_channel(audit_channel_id)
        # else:
        #     tournament_race.audit_channel = None

        return tournament_race

    async def update_data(self):
        self.episode = await speedgaming.get_episode(self.episodeid)
        self.data = await tournaments.get_tournament(self.episode['event']['slug'])

        if self.data is None:
            raise Exception('SG Episode ID not a recognized event.  This should not have happened.')

        self.guild = discordbot.get_guild(self.data['guild_id'])

        self.players = []
        for player in self.episode['match1']['players']:
            # first try a more concrete match of using the discord id cached by SG
            looked_up_player = await self.make_tournament_player(player)
            self.players.append(looked_up_player)

        self.bracket_settings = await tournament_games.get_game_by_episodeid_submitted(self.episodeid)

    async def make_tournament_player(self, player):
        if not player['discordId'] == "":
            looked_up_player = await TournamentPlayer.construct(discord_id=player['discordId'], guild=self.guild)
        else:
            looked_up_player = None

        # then, if that doesn't work, try their discord tag kept by SG
        if looked_up_player is None and not player['discordTag'] == '':
            looked_up_player = await TournamentPlayer.construct_discord_name(discord_name=player['discordTag'], guild=self.guild)

        # and failing all that, bomb
        if looked_up_player is None:
            raise UnableToLookupUserException(
                f"Unable to lookup the player `{player['displayName']}`.  Please contact a Tournament moderator for assistance.")

        return looked_up_player


    async def generate_game(self):
        await self.pre_generate_message()
        await self.update_data()

        await self.roll()

        await self.send_player_seed()
        await self.send_audit_log()
        await self.send_commentary()

        await self.handler.set_raceinfo(self.goal, overwrite=True)

        await tournament_results.update_tournament_results_rolled(
            srl_id=self.handler.data.get('name'),
            permalink=self.seed.url
        )

        await self.post_generate_message()
        self.handler.seed_rolled = True

    async def create_room(self):
        racetime_category = racetime.racetime_bots[self.racetime_category]
        race = await tournament_results.get_active_tournament_race_by_episodeid(episodeid)
        if race:
            async with aiohttp.request(
                    method='get',
                    url=rtgg_alttpr.http_uri(f"/{race['srl_id']}/data"),
                    raise_for_status=True) as resp:
                race_data = json.loads(await resp.read())
            status = race_data.get('status', {}).get('value')
            if not status == 'cancelled':
                return
            await tournament_results.delete_active_tournament_race(race['srl_id'])

        handler = await rtgg_alttpr.startrace(
            goal=goal,
            invitational=True,
            unlisted=False,
            info=f"{tournament_race.event_name} - {tournament_race.versus}",
            start_delay=15,
            time_limit=24,
            streaming_required=True,
            auto_start=True,
            allow_comments=True,
            hide_comments=True,
            allow_prerace_chat=True,
            allow_midrace_chat=True,
            allow_non_entrant_chat=False,
            chat_message_delay=0
        )

        logging.info(handler.data.get('name'))
        await tournament_results.insert_tournament_race(
            srl_id=handler.data.get('name'),
            episode_id=tournament_race.episodeid,
            event=tournament_race.event_slug
        )

        for rtggid in tournament_race.player_racetime_ids:
            await handler.invite_user(rtggid)

        embed = discord.Embed(
            title=f"RT.gg Room Opened - {tournament_race.versus}",
            description=f"Greetings!  A RaceTime.gg race room has been automatically opened for you.\nYou may access it at https://racetime.gg{handler.data['url']}\n\nEnjoy!",
            color=discord.Colour.blue(),
            timestamp=datetime.datetime.now()
        )

        for name, player in tournament_race.player_discords:
            if player is None:
                logging.info(f'Could not DM {name}')
                continue
            try:
                await player.send(embed=embed)
            except discord.HTTPException:
                logging.info(f'Could not send room opening DM to {name}')
                continue

        if category != 'smw-hacks':
            await handler.send_message('Welcome. Use !tournamentrace (without any arguments) to roll your seed!  This should be done about 5 minutes prior to the start of you race.  If you need help, ping @Mods in the ALTTPR Tournament Discord.')

        return handler.data

    async def pre_generate_message(self):
        pass

    async def post_generate_message(self):
        pass

    async def send_player_seed(self):
        pass

    async def send_commentary(self):
        pass

    async def send_audit_log(self):
        pass

    async def send_seed(self):
        pass

    async def roll(self):
        pass

    @property
    def race_info(self):
        return f"{self.event_name} - {self.versus} - {self.friendly_name}"

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
    def racetime_category(self):
        return None