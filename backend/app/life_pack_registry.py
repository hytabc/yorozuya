"""Virtual-life content packs: server-side save validation authority.

Each pack is a JSON manifest in ``app/life_packs/``:

    {
      "id": "wsw-default-life",
      "version": 1,
      "npcIds": ["ache", ...],        // ordered, unique
      "actionIds": ["headpat", ...],  // rewardable action ids
      "roomIds": ["beach-1024", ...], // enterable room whitelist
      "roomWorlds": {"beach-1024": "潮汐之后", ...}  // room -> world name
    }

Saves are validated against the ACTIVE pack (env ``LIFE_PACK_ID``, default
``wsw-default-life``). The frontend pack of the same id provides gameplay
content; keep both copies in sync when adding content.
"""
import json
import os
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parent / 'life_packs'
DEFAULT_PACK_ID = 'wsw-default-life'


class LifePackError(RuntimeError):
    pass


def _validate_pack(pack: dict, source: Path) -> None:
    where = f'{source.name}: '
    if not isinstance(pack.get('id'), str) or not pack['id'].strip():
        raise LifePackError(where + 'missing id')
    if not isinstance(pack.get('version'), int) or pack['version'] < 1:
        raise LifePackError(where + 'version must be a positive integer')
    npc_ids = pack.get('npcIds')
    if not isinstance(npc_ids, list) or not npc_ids or len(set(npc_ids)) != len(npc_ids):
        raise LifePackError(where + 'npcIds must be a non-empty unique list')
    action_ids = pack.get('actionIds')
    if not isinstance(action_ids, list) or not action_ids or len(set(action_ids)) != len(action_ids):
        raise LifePackError(where + 'actionIds must be a non-empty unique list')
    room_ids = pack.get('roomIds')
    room_worlds = pack.get('roomWorlds')
    if not isinstance(room_ids, list) or not room_ids or len(set(room_ids)) != len(room_ids):
        raise LifePackError(where + 'roomIds must be a non-empty unique list')
    if not isinstance(room_worlds, dict) or set(room_worlds) != set(room_ids):
        raise LifePackError(where + 'roomWorlds keys must equal roomIds')
    if any(not isinstance(name, str) or not name for name in room_worlds.values()):
        raise LifePackError(where + 'roomWorlds values must be non-empty strings')


def _load_packs() -> dict[str, dict]:
    packs: dict[str, dict] = {}
    for path in sorted(PACK_DIR.glob('*.json')):
        pack = json.loads(path.read_text(encoding='utf-8'))
        _validate_pack(pack, path)
        if pack['id'] in packs:
            raise LifePackError(f'duplicate pack id: {pack["id"]}')
        packs[pack['id']] = pack
    if not packs:
        raise LifePackError(f'no virtual life packs found in {PACK_DIR}')
    return packs


LIFE_PACKS = _load_packs()
ACTIVE_LIFE_PACK_ID = os.environ.get('LIFE_PACK_ID', DEFAULT_PACK_ID)
if ACTIVE_LIFE_PACK_ID not in LIFE_PACKS:
    raise LifePackError(f'active LIFE_PACK_ID not registered: {ACTIVE_LIFE_PACK_ID}')
ACTIVE_LIFE_PACK = LIFE_PACKS[ACTIVE_LIFE_PACK_ID]
