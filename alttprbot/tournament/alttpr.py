import copy
import datetime
import logging
import json
import random

import aiohttp
import discord
import pyz3r.customizer

from alttprbot.alttprgen import preset
from alttprbot.database import (tournament_results, srlnick, tournaments, tournament_games)
from alttprbot.util import speedgaming
from alttprbot.exceptions import SahasrahBotException
from alttprbot_discord.bot import discordbot
from alttprbot_racetime.bot import racetime_bots

SETTINGSMAP = {
    'Defeat Ganon': 'ganon',
    'Fast Ganon': 'fast_ganon',
    'All Dungeons': 'dungeons',
    'Standard': 'standard',
    'Open': 'open',
    'Inverted': 'inverted',
    'Retro': 'retro',
    'Randomized': 'randomized',
    'Assured': 'assured',
    'Vanilla': 'vanilla',
    'Swordless': 'swordless',
    'Shuffled': 'shuffled',
    'Full': 'full',
    'Random': 'random',
    'Hard': 'hard',
    'Normal': 'normal',
    'Off': 'off',
    'On': 'on'
}


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


class TournamentRace():
    def __init__(self, episodeid: int, create_seed=True):
        self.episodeid = int(episodeid)
        self.create_seed = create_seed
        self.players = []

    @classmethod
    async def construct(cls, episodeid, create_seed=True):
        tournament_race = cls(episodeid, create_seed)

        tournament_race.episode = await speedgaming.get_episode(tournament_race.episodeid)

        tournament_race.data = await tournaments.get_tournament(tournament_race.episode['event']['slug'])
        if tournament_race.data is None:
            raise Exception('SG Episode ID not a recognized event.  This should not have happened.')
        tournament_race.guild = discordbot.get_guild(tournament_race.data['guild_id'])

        for player in tournament_race.episode['match1']['players']:
            # first try a more concrete match of using the discord id cached by SG
            looked_up_player = await tournament_race.make_tournament_player(player)
            tournament_race.players.append(looked_up_player)

        if tournament_race.create_seed:
            await tournament_race._roll_general()

        return tournament_race

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

    async def _roll_general(self):
        game_mode = self.episode['match1']['title']
        if game_mode == 'Open':
            self.seed, self.preset_dict = await preset.get_preset('open', nohints=True, allow_quickswap=True)
        elif game_mode == 'Standard':
            self.seed, self.preset_dict = await preset.get_preset('standard', nohints=True, allow_quickswap=True)
        else:
            raise Exception(f"Invalid Match Title, must be Open or Standard!  Please contact a tournament admin for help.")

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
    def player_names(self):
        return [p.name for p in self.players]

    @property
    def broadcast_channels(self):
        return [a['name'] for a in self.episode['channels'] if not " " in a['name']]


async def process_tournament_race(handler, episodeid=None):
    await handler.send_message("Generating game, please wait.  If nothing happens after a minute, contact Synack.")

    race = await tournament_results.get_active_tournament_race(handler.data.get('name'))
    if race:
        episodeid = race.get('episode_id')
    if race is None and episodeid is None:
        await handler.send_message("Please provide an SG episode ID.")
        return

    try:
        tournament_race = await TournamentRace.construct(episodeid=episodeid)
    except Exception as e:
        logging.exception("Problem creating tournament race.")
        await handler.send_message(f"Could not process tournament race: {str(e)}")
        return

    goal = f"{tournament_race.event_name} - {tournament_race.versus} - {tournament_race.friendly_name}"

    embed = await tournament_race.seed.embed(
        name=goal,
        notes=tournament_race.versus,
        emojis=discordbot.emojis
    )

    tournament_embed = await tournament_race.seed.tournament_embed(
        name=goal,
        notes=tournament_race.versus,
        emojis=discordbot.emojis
    )

    goal += f" - ({'/'.join(tournament_race.seed.code)})"

    tournament_embed.insert_field_at(
        0, name='RaceTime.gg', value=f"https://racetime.gg{handler.data['url']}", inline=False)
    embed.insert_field_at(
        0, name='RaceTime.gg', value=f"https://racetime.gg{handler.data['url']}", inline=False)

    if broadcast_channels := tournament_race.broadcast_channels:
        tournament_embed.insert_field_at(
            0, name="Broadcast Channels", value=', '.join([f"[{a}](https://twitch.tv/{a})" for a in broadcast_channels]), inline=False)
        embed.insert_field_at(
            0, name="Broadcast Channels", value=', '.join([f"[{a}](https://twitch.tv/{a})" for a in broadcast_channels]), inline=False)

        goal += f" - Restream(s) at {', '.join(broadcast_channels)}"

    await handler.set_raceinfo(goal, overwrite=True)

    audit_channel_id = tournament_race.data['audit_channel_id']
    if audit_channel_id is not None:
        audit_channel = discordbot.get_channel(audit_channel_id)
        await audit_channel.send(embed=embed)
    else:
        audit_channel = None

    commentary_channel_id = tournament_race.data['commentary_channel_id']
    if commentary_channel_id is not None:
        commentary_channel = discordbot.get_channel(int(commentary_channel_id))
        if commentary_channel and len(broadcast_channels) > 0:
            await commentary_channel.send(embed=tournament_embed)

    for name, player in tournament_race.player_discords:
        if player is None:
            await audit_channel.send(f"@here could not send DM to {name}", allowed_mentions=discord.AllowedMentions(everyone=True))
            await handler.send_message(f"Could not send DM to {name}.  Please contact a Tournament Moderator for assistance.")
            continue
        try:
            await player.send(embed=embed)
        except discord.HTTPException:
            if audit_channel is not None:
                await audit_channel.send(f"@here could not send DM to {player.name}#{player.discriminator}", allowed_mentions=discord.AllowedMentions(everyone=True))
                await handler.send_message(f"Could not send DM to {player.name}#{player.discriminator}.  Please contact a Tournament Moderator for assistance.")

    if race is None:
        await tournament_results.insert_tournament_race(
            srl_id=handler.data.get('name'),
            episode_id=tournament_race.episodeid,
            permalink=tournament_race.seed.url,
            event=tournament_race.event_slug,
            spoiler=None
        )
    else:
        await tournament_results.update_tournament_results_rolled(
            srl_id=handler.data.get('name'),
            permalink=tournament_race.seed.url
        )

    await handler.send_message("Seed has been generated, you should have received a DM in Discord.  Please contact a Tournament Moderator if you haven't received the DM.")
    handler.seed_rolled = True


async def process_tournament_race_start(handler):
    race_id = handler.data.get('name')

    if race_id is None:
        return

    race = await tournament_results.get_active_tournament_race(race_id)

    if race is None:
        return

    await tournament_results.update_tournament_results(race_id, status="STARTED")


async def create_tournament_race_room(episodeid):
    rtgg_alttpr = racetime_bots['alttpr']
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

    tournament_race = await TournamentRace.construct(episodeid=episodeid, create_seed=False)

    handler = await rtgg_alttpr.startrace(
        goal="Beat the game",
        invitational=True,
        unlisted=True,
        info=f"{tournament_race.event_name} - {tournament_race.versus}",
        start_delay=15,
        time_limit=24,
        streaming_required=True,
        auto_start=True,
        allow_comments=True,
        hide_comments=True,
        allow_midrace_chat=True,
        allow_non_entrant_chat=False,
        chat_message_delay=0
    )

    print(handler.data.get('name'))
    await tournament_results.insert_tournament_race(
        srl_id=handler.data.get('name'),
        episode_id=tournament_race.episodeid,
        event=tournament_race.event_slug
    )

    for rtggid in [p.data['rtgg_id'] for p in tournament_race.players]:
        await handler.invite_user(rtggid)

    embed = discord.Embed(
        title=f"RT.gg Room Opened - {tournament_race.versus}",
        description=f"Greetings!  A RaceTime.gg race room has been automatically opened for you.\nYou may access it at https://racetime.gg{handler.data['url']}\n\nEnjoy!",
        color=discord.Colour.blue(),
        timestamp=datetime.datetime.now()
    )

    for name, player in tournament_race.player_discords:
        if player is None:
            print(f'Could not DM {name}')
            continue
        try:
            await player.send(embed=embed)
        except discord.HTTPException:
            print(f'Could not send room opening DM to {name}')
            continue

    await handler.send_message('Welcome. Use !tournamentrace (without any arguments) to roll your seed!  This should be done about 5 minutes prior to the start of you race.  If you need help, ping @Mods in the ALTTPR Tournament Discord.')
    await handler.edit(unlisted=False)

    return handler.data


async def alttprde_process_settings_form(form):
    episode_id = int(form['SpeedGaming Episode ID'])
    game_number = int(form['Game Number'])

    existing_playoff_race = await tournament_games.get_game_by_episodeid_submitted(episode_id)
    if existing_playoff_race:
        return

    tournament_race = await TournamentRace.construct(episodeid=episode_id, create_seed=False)

    embed = discord.Embed(
        title=f"ALTTPR DE - Game #{game_number} - {tournament_race.versus}",
        description='Thank you for submitting your settings for this race!  Below is what will be played.\nIf this is incorrect, please contact a tournament admin.',
        color=discord.Colour.blue()
    )

    if form['Game Number'] == '1':
        goal = random.choice(['Defeat Ganon', 'Fast Ganon', 'All Dungeons'])
        crystals = '7/7'
        world_state = random.choice(['Open', 'Standard'])
        swords = random.choice(['Assured', 'Randomized'])
        enemy_shuffle = 'Off'
        boss_shuffle = 'Off'
        dungeon_item_shuffle = 'Standard'
        item_pool = random.choice(['Normal', 'Hard'])
        item_functionality = 'Normal'
        extra_start_item = "None"
        hints = 'Off'
    else:
        goal = form['Goal']
        crystals = form['Tower/Ganon Requirements']
        world_state = form['World State']
        swords = form['Swords']
        enemy_shuffle = form['Enemy Shuffle']
        boss_shuffle = form['Boss Shuffle']
        dungeon_item_shuffle = form['Dungeon Item Shuffle']
        item_pool = form['Item Pool']
        item_functionality = form['Item Functionality']
        extra_start_item = form['Extra Start Item']
        hints = form['Hints']

    embed.add_field(
        name='Settings',
        value=(
            f"**Goal**: {goal}\n"
            f"**Tower/Ganon Requirements**: {crystals}\n"
            f"**World State**: {world_state}\n"
            f"**Swords**: {swords}\n"
            f"**Enemy Shuffle**: {enemy_shuffle}\n"
            f"**Boss Shuffle**: {boss_shuffle}\n"
            f"**Dungeon Item Shuffle**: {dungeon_item_shuffle}\n"
            f"**Item Pool**: {item_pool}\n"
            f"**Item Functionality**: {item_functionality}\n"
            f"**Extra Start Item**: {extra_start_item}\n"
            f"**Hints**: {hints}"
        )
    )

    settings = copy.deepcopy(pyz3r.customizer.BASE_CUSTOMIZER_PAYLOAD)

    settings['custom']['customPrizePacks'] = False

    settings["glitches"] = "none"
    settings["item_placement"] = "advanced"
    settings["dungeon_items"] = "standard"
    settings["accessibility"] = "items"
    settings['goal'] = SETTINGSMAP[goal]
    settings["crystals"]["ganon"] = "7" if crystals == "7/7" else "6"
    settings["crystals"]["tower"] = "7" if crystals == "7/7" else "6"
    settings["mode"] = SETTINGSMAP[world_state]
    settings["hints"] = SETTINGSMAP[hints]
    settings["weapons"] = SETTINGSMAP[swords]
    settings["item"]["pool"] = SETTINGSMAP[item_pool]
    settings["item"]["functionality"] = SETTINGSMAP[item_functionality]
    settings["tournament"] = False
    settings["spoilers"] = "off"
    settings["enemizer"]["boss_shuffle"] = SETTINGSMAP[boss_shuffle]
    settings["enemizer"]["enemy_shuffle"] = SETTINGSMAP[enemy_shuffle]
    settings["enemizer"]["enemy_damage"] = "default"
    settings["enemizer"]["enemy_health"] = "default"
    settings["enemizer"]["pot_shuffle"] = "off"
    settings["entrances"] = "off"
    settings["allow_quickswap"] = True

    settings['custom']['region.wildKeys'] = dungeon_item_shuffle in ['Small Keys', 'Keysanity']
    settings['custom']['region.wildBigKeys'] = dungeon_item_shuffle in ['Big Keys', 'Keysanity']
    settings['custom']['region.wildCompasses'] = dungeon_item_shuffle in ['Maps/Compasses', 'Keysanity']
    settings['custom']['region.wildMaps'] = dungeon_item_shuffle in ['Maps/Compasses', 'Keysanity']

    if settings['custom'].get('region.wildKeys', False) or settings['custom'].get('region.wildBigKeys', False) or settings['custom'].get('region.wildCompasses', False) or settings['custom'].get('region.wildMaps', False):
        settings['custom']['rom.freeItemMenu'] = True
        settings['custom']['rom.freeItemText'] = True

    if settings['custom'].get('region.wildMaps', False):
        settings['custom']['rom.mapOnPickup'] = True

    if settings['custom'].get('region.wildCompasses', False):
        settings['custom']['rom.dungeonCount'] = 'pickup'

    eq = []
    if extra_start_item == "Boots":
        eq += ["PegasusBoots"]
    if extra_start_item == "Flute":
        eq += ["OcarinaActive"]
    for item in eq:
        if item == 'OcarinaActive':
            item = 'OcarinaInactive'

        settings['custom']['item']['count'][item] = settings['custom']['item']['count'].get(
            item, 0) - 1 if settings['custom']['item']['count'].get(item, 0) > 0 else 0

    # re-add 3 heart containers as a baseline
    eq += ['BossHeartContainer'] * 3

    # update the eq section of the settings
    settings['eq'] = eq

    if settings["mode"] == 'standard':
        settings['eq'] = [item if item != 'OcarinaActive' else 'OcarinaInactive' for item in settings.get('eq', {})]

    await tournament_games.insert_game(episode_id=episode_id, event='alttprde', game_number=game_number, settings=settings)

    audit_channel_id = tournament_race.data['audit_channel_id']
    if audit_channel_id is not None:
        audit_channel = discordbot.get_channel(audit_channel_id)
        await audit_channel.send(embed=embed)
    else:
        audit_channel = None

    for name, player in tournament_race.player_discords:
        if player is None:
            await audit_channel.send(f"@here could not send DM to {name}", allowed_mentions=discord.AllowedMentions(everyone=True), embed=embed)
            continue
        try:
            await player.send(embed=embed)
        except discord.HTTPException:
            if audit_channel is not None:
                await audit_channel.send(f"@here could not send DM to {player.name}#{player.discriminator}", allowed_mentions=discord.AllowedMentions(everyone=True), embed=embed)


async def is_tournament_race(name):
    race = await tournament_results.get_active_tournament_race(name)
    if race:
        return True
    return False


async def can_gatekeep(rtgg_id, name):
    race = await tournament_results.get_active_tournament_race(name)

    tournament = await tournaments.get_tournament(race['event'])
    if tournament is None:
        return False
    guild = discordbot.get_guild(tournament['guild_id'])
    nicknames = await srlnick.get_discord_id_by_rtgg(rtgg_id)

    if not nicknames:
        return False

    discord_user = guild.get_member(nicknames[0]['discord_user_id'])

    if not discord_user:
        return False

    if helper_roles := tournament.get('helper_roles', None):
        if discord.utils.find(lambda m: m.name in helper_roles.split(','), discord_user.roles):
            return True

    return False
