import copy
import datetime
import logging
import json
import random
import os
import isodate

import aiohttp
import discord
import pyz3r.customizer
import gspread_asyncio
import pytz

from alttprbot.alttprgen import preset
from alttprbot.database import (tournament_results, srlnick, tournaments, tournament_games)
from alttprbot.tournament.core import SpeedgamingTournamentRace
from alttprbot.util import gsheet, speedgaming
from alttprbot.exceptions import SahasrahBotException
from alttprbot_discord.bot import discordbot
from alttprbot_discord.util import alttpr_discord
from alttprbot_racetime import bot as racetime

TOURNAMENT_RESULTS_SHEET = os.environ.get('TOURNAMENT_RESULTS_SHEET', None)

SETTINGSMAP = {
    'Defeat Ganon': 'ganon',
    'Fast Ganon': 'fast_ganon',
    'All Dungeons': 'dungeons',
    'Pedestal': 'pedestal',
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
    'On': 'on',
    'None': 'none'
}

class AlttprTournamentRace(SpeedgamingTournamentRace):
    pass

class AlttprMainTournamentRace(AlttprTournamentRace):
    async def roll(self):
        self.seed, self.preset_dict = await preset.get_preset('tournament', nohints=True, allow_quickswap=True)


async def process_tournament_race_start(handler):
    race_id = handler.data.get('name')

    if race_id is None:
        return

    race = await tournament_results.get_active_tournament_race(race_id)

    if race is None:
        return

    await tournament_results.update_tournament_results(race_id, status="STARTED")


async def alttprde_process_settings_form(form):
    episode_id = int(form['SpeedGaming Episode ID'])
    game_number = int(form['Game Number'])

    existing_playoff_race = await tournament_games.get_game_by_episodeid_submitted(episode_id)
    if existing_playoff_race:
        return

    tournament_race = await TournamentRace.construct(episodeid=episode_id)

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
        enemy_shuffle = 'None'
        boss_shuffle = 'None'
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
    settings["tournament"] = True
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

async def race_recording_task():
    if TOURNAMENT_RESULTS_SHEET is None:
        return

    races = await tournament_results.get_unrecorded_races()
    if races is None:
        return

    agcm = gspread_asyncio.AsyncioGspreadClientManager(gsheet.get_creds)
    agc = await agcm.authorize()
    wb = await agc.open_by_key(TOURNAMENT_RESULTS_SHEET)

    for race in races:
        logging.info(f"Recording {race['episode_id']}")
        try:

            sheet_name = race['event']
            wks = await wb.worksheet(sheet_name)

            async with aiohttp.request(
                    method='get',
                    url=f"https://racetime.gg/{race['srl_id']}/data",
                    raise_for_status=True) as resp:
                race_data = json.loads(await resp.read())

            if race_data['status']['value'] == 'finished':
                winner = [e for e in race_data['entrants'] if e['place'] == 1][0]
                runnerup = [e for e in race_data['entrants'] if e['place'] in [2, None]][0]

                started_at = isodate.parse_datetime(race_data['started_at']).astimezone(pytz.timezone('US/Eastern'))
                await wks.append_row(values=[
                    race['episode_id'],
                    started_at.strftime("%Y-%m-%d %H:%M:%S"),
                    f"https://racetime.gg/{race['srl_id']}",
                    winner['user']['name'],
                    runnerup['user']['name'],
                    str(isodate.parse_duration(winner['finish_time'])) if isinstance(winner['finish_time'], str) else None,
                    str(isodate.parse_duration(runnerup['finish_time'])) if isinstance(runnerup['finish_time'], str) else None,
                    race['permalink'],
                    race['spoiler']
                ])
                await tournament_results.update_tournament_race_status(race['srl_id'], "RECORDED")
                await tournament_results.mark_as_written(race['srl_id'])
            elif race_data['status']['value'] == 'cancelled':
                await tournament_results.delete_active_tournament_race_all(race['srl_id'])
            else:
                return
        except Exception as e:
            logging.exception("Encountered a problem when attempting to record a race.")

    logging.debug('done')
