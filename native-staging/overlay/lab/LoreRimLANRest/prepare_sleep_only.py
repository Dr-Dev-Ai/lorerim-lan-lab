"""Build a sleep-only alias from our source without private follower/IED adapters."""
import argparse
from pathlib import Path


def prepare(destination):
    source = Path(__file__).parent / 'source'
    text = (source / 'SkyrimTogetherPlayerAliasScript.psc').read_text(encoding='utf-8')
    start = '    campaignFollowerPoll += 1\n'
    end = '    Actor player = Game.GetPlayer()\n'
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError('Alias source changed; review sleep-only extraction')
    before, tail = text.split(start)
    adapters, after = tail.split(end)
    if 'LoreRimCampaignReportFollowers' not in adapters or 'IED.Reset' not in adapters:
        raise ValueError('Expected adapter block not found')
    text = (before + end + after).replace('Int campaignFollowerPoll = 0\n', '')
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'SkyrimTogetherPlayerAliasScript.psc').write_text(text, encoding='utf-8')
    (destination / 'LoreRimLANRest.psc').write_text((source / 'LoreRimLANRest.psc').read_text(encoding='utf-8'), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    prepare(parser.parse_args().destination)
