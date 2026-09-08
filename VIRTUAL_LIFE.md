# Virtual life private save (v1)

One private save per authenticated administrator: online `role=staff` means
管理员 and `is_admin=true` means 超级管理员; both are eligible. Virtual-life
navigation, route and page visibility use the existing `auth.canManageRoles`;
the save API independently uses the existing active-user `get_role_manager`
dependency. Ordinary users and volunteers get 403; unauthenticated requests get
401. Desktop-only UI restrictions remain (viewport >=901px and non-mobile UA).
No caller-supplied user id is accepted, and eligible users can access only their
own save. This feature does not change global roles or promote any account.

## API and storage

- GET `/api/virtual-life/save`: `{revision, state, updatedAt}`. Missing save is
  `{revision:0,state:null,updatedAt:null}`; GET never creates a save.
- PUT same route: `{revision,state}`; returns `{revision,updatedAt}` after commit.
- Revision 0 creates; subsequent requests must supply last known revision.
  Conflict is HTTP 409; there is no force-overwrite option.
- Independent `virtual_life_saves` table in existing configured database, one
  primary key `user_id`, JSON state, integer revision, UTC updated timestamp.
  Table is created by existing startup `Base.metadata.create_all`.
- State: `schemaVersion:2` with `packId`; day, stats (mood/energy/social/explore), tags,
  currentWorld, unlockedWorlds, currentNpcId, npcs, conversations, diary, completed,
  actionLedger and `dialogueNodes` (NPC -> current dialogue node id; stage 4c,
  defaults `{}` in older saves).
  Legacy `schemaVersion:1` writes (no packId) are upgraded to v2 on write; v2
  must declare the site's active pack id. NPC/room/action whitelists are derived
  from the ACTIVE content pack stored in the `virtual_life_packs` table (stage
  4a), no longer from code. Unknown schemas/ids/packs rejected. Encoded state
  limit 2 MB; no silent history truncation. Message length 4000.

## Content packs (site-configurable)

A content pack holds the FULL site content as JSON: npcIds/npcs/portraits,
worlds (with optional `bg` image URL), rooms, presence, actions, per-day
node-graph dialogue (`dialogue[npcId]` is a 1-7 entry array of day scripts
`{start, nodes:{id:{line, choices:[{label, effects:{bond,stats},
reply, next}]}}}`, stage 5) and initialState. Exactly one pack is active
site-wide (A-scheme: the site admin configures content; all players share it).

- Table `virtual_life_packs` (id/name/version/content_json/is_active/
  updated_at) is seeded on first startup from `backend/app/life_packs/*.json`;
  the JSON files are seeds only — the database is authoritative afterwards.
- `backend/app/virtual_life_packs.py`: `validate_pack_content` enforces
  structural and reference consistency (room→world, presence→room, dialogue
  node-graph jump targets per day, stat keys, initial state coverage).
  Startup seeding migrates legacy single-script `dialogue[npcId]` shapes in
  place to one-entry day arrays (`migrate_pack_content`).
- Admin API (all gated by `get_role_manager`): GET `/api/virtual-life/pack`
  (active pack detail), GET/POST `/api/virtual-life/packs`, GET/PUT/DELETE
  `/packs/{id}`, POST `/packs/{id}/activate` (exactly one active; activating
  revalidates), POST `/packs/{id}/duplicate`. Content updates bump `version`.
  The active pack cannot be deleted. Save validation follows the active pack
  immediately after activation.
- POST `/api/virtual-life/assets` (stage 4d): single image upload for world
  backgrounds and NPC portraits — magic-byte sniffing (JPEG/PNG/GIF/WebP),
  5 MiB cap, stored under the uploads mount as `life/<uuid>.<ext>` and served
  at `/uploads/...`.

## Admin UI (/life-admin, stage 4d)

`frontend/src/views/LifeAdmin.vue` plus `frontend/src/life/admin/` (data layer
`useLifeAdmin.js` singleton, sections `AdminNpcs` / `AdminWorlds` /
`AdminActions` / `AdminDialogue` / `AdminInitial`, shared `AdminImageField`).
The route uses the same `lifeOnly` guard as the game (role manager + desktop);
the game header links to it via 内容管理. The admin edits one pack at a time in
structured forms: NPC profiles/portraits/presence, worlds (incl. background
upload) and rooms, actions, the per-NPC dialogue node graph and the initial
player state. Dialogue is edited PER DAY (stage 5): tabs 第 1~7 天 switch the
day script being edited (nodes, choices, effects, jump targets, start node);
packs with fewer than 7 days are padded by cloning their last day on load.
Node add/delete applies to the current day only; deleting the start node
hands the start over to the first remaining node, and the last node of a day
cannot be deleted. Saving PUTs the whole content; server-side validation
errors are surfaced verbatim, and content edits bump the pack version. Pack
list operations: select, duplicate,
activate (exactly one active, player side and save validation follow
immediately), delete (inactive only). NPC/world/room removal cascades
references (presence, dialogue, initial conversations); node removal rewrites
jump targets to day-end.

## Frontend

File layout after the stage-1 modular split (behavior unchanged):

- `frontend/src/life/registry.js`: content-pack Registry (stage 2, extended in
  4b). A runtime pack is `{id, version, npcIds, npcs, portraits, worlds, rooms,
  presence, actions, dialogue (node graph), initialState, dialogueScripts,
  createInitialState}`; registration validates completeness and reference
  consistency. `createLifePackFromContent` builds a runtime pack from raw JSON
  content (deriving the legacy `dialogueScripts` view and deep-copying
  initialState); `effectText` renders choice effects as display text.
  `frontend/src/life/builtin.js` registers built-in packs;
  `frontend/src/life/content/defaultPack.js` is the built-in default pack —
  its content is kept identical to the backend seed JSON (asserted by test).
- `frontend/src/life/packLoader.js` (stage 4b): on game mount, fetches the
  site's active pack via GET `/api/virtual-life/pack`, registers and activates
  it; on any failure the built-in pack remains as fallback. The save load runs
  only AFTER the pack settles (`useLifeSave` `autoLoad:false`), because
  snapshot/hydrate validate against the active pack. When the fetched pack
  arrives, `useLifeGame.applyPack` rebuilds all game state from it and injects
  worlds/rooms/presence into `lifePresence.js` (`setLifePresenceData`) and
  actions into `lifeActions.js` (`setLifeActions`) — those modules keep their
  exported constants as built-in defaults and expose reactive current-data
  readers for all rule functions. Scene background: `LifeScene` renders the
  current world's `bg` image when the pack defines one, otherwise the previous
  placeholder; world thumbnails in `LifeFeatureDrawer` show `bg` likewise.
  Snapshots write `schemaVersion:2` + `packId`; hydrate accepts v1 (legacy, no
  packId) or v2 whose packId matches the active pack (stage 3).
- `frontend/src/life/useLifeGame.js`: all game state, mutations, tutorial
  wiring and save plumbing; returns a single `game` object.
- `frontend/src/life/components/`: `LifeCharPanel`, `LifeScene`,
  `LifeMenuPanel`, `LifeHistoryDrawer`, `LifeFeatureDrawer` — presentational,
  receive `game` via prop; each carries its own scoped styles.
- `frontend/src/views/LifeSimulator.vue`: shell only — header, save status,
  three-column layout, footer, drawer overlays, tutorial mount, toast.

Entry restores server save before any mutation is allowed. Failed loads do not
initialize/overwrite server data. Manual save reports success only after PUT.
Choices, NPC switching, next day trigger 700 ms debounced autosave. Requests are
serialized with revision checking; changes arriving during a save are drained.
Complete player/NPC turns are updated synchronously so navigation never drops a
pending reply. Next day retains conversation history.

The dedicated HTTP client captures the entry token (not the global interceptor).
Account changes stop further saves; data is never dispatched using a new account's
token. Route leave awaits saving, and failures require confirmation to discard.
Hard reload prompts for unsaved changes; responsive forced unmount attempts a final
save. Abrupt process/browser termination before acknowledgement cannot guarantee
saving. Conflicts require explicit reload; unsaved changes show an error/retry UI.

## Dialogue node-graph engine (stage 4c, per-day scripts in stage 5)

Each NPC has a 1-7 entry array of day scripts `{start, nodes:{id:{line,
choices}}}` in the active pack. `scriptForDay(days, day)` picks the script for
the current game day — CLAMPED, not cycling: the content ends at day 7, and
any later game day keeps using the last day script. Pure rules live in
`frontend/src/composables/lifeDialogue.js`
(`scriptForDay`/`nodeFor`/`startLine`/`resolveDialogueChoice`/`sanitizeDialogueNodes`);
state and mutations stay in `useLifeGame`. Semantics per NPC per game day:

- The chain starts at `start`; the start node's line is the daily greeting.
  Different days can have entirely different chains (stage 5: the default pack
  ships 7 distinct daily greetings per NPC).
- A choice applies its `effects` explicitly (`bond` added to the NPC bond,
  `stats` clamped 0-100) — no text parsing. The toast text is rendered from
  effects via `effectText`.
- `next` non-null advances to that node THE SAME day: the NPC's reply and the
  next node's line are appended atomically and played in order; `completed`
  stays false and the new node's choices are offered. `next: null` marks the
  day complete (choices hide, actions remain available).
- Position (`dialogueNodes`) is persisted in the save, so a mid-chain reload
  resumes at the exact node; hydration drops positions pointing at nodes that
  no longer exist. Server validation rejects unknown NPCs/node ids.
- `nextDay` clears positions and completion; every NPC greets from the NEW
  day's `start` (or the last day script once past the schedule). Choice
  effects apply per choice click — replaying a finished chain next day yields
  its effects again, as before.

## Reply actions

The warm paper/green reply panel has 对话 and 动作 tabs; action availability is
independent of daily dialogue completion. 摸摸头 gives +2 bond, 戳戳脸 +1,
and 亲亲 +3 (requires current bond >=30). Bond caps at 100 and feedback reports
the actual increase. Only the first use **per NPC, per action, per game day**
rewards bond. Repeats still produce dialogue/history but no additional reward.
`actionLedger` stores `{gameDay: {npcId: {actionId: true}}}` in the same private
save, atomically alongside bond, player/NPC messages and diary. Next day keeps
the ledger but uses a new day key. Older v1 saves omit it: server validation and
client hydration default to `{}`. No database migration is needed.

The prototype remains client-authoritative, not cheat-resistant against manually
modified HTTP requests. Ordinary repeat clicks and loading an acknowledged save
do not reset reward eligibility. Wait for save synchronization before refreshing;
unsaved changes retain the existing unload warning.

## Simulated friend presence and profiles

Worlds contain multiple stable room instances. World exploration opens a room list;
there is NO room creation. Only occupied, nonprivate, unfilled rooms may be joined.
Disabled empty/private/full mock rooms display their reason. Room counts include
explicitly simulated background visitors plus named NPCs, and the player when present.
Friends' green status enables following only if the same room gate also passes.
Orange/red prevents following, not natural meetings in an accessible public room.
Interactions and scene avatars use currentRoomId, never merely the map name.
Entering a room cancels presentation and never automatically opens dialogue.

NPCs are NOT default friends. Friend list shows only explicitly added NPCs' avatars,
names and status. Scene avatars talk; their adjacent '资料' button opens a stranger
profile. At least one completed choice/action AND bond >=10 permits explicit Add
Friend; the mock accepts immediately. Profile details hold the affection meter.

Save schema v1 gains currentRoomId (nullable for old saves), friendIds default [],
and interactedNpcIds. Old actual player messages infer past interaction; NPC greetings
do not. No friendships are inferred from history or bond. Legacy room migration selects
a valid occupied public room for the old map, or beach-1024 if unknown, and aligns the
map label. It preserves all bonds, histories and daily action ledgers. New social state
is saved on next normal save; each user remains isolated. No SQL migration needed.

`lifePresence.js` supplies static mock maps/rooms/presence/visitors, NOT real VRC or
shared multiplayer data. Server validates social ids, eligible friendship state,
enterable room ids and room-map consistency; game remains client-authoritative.
Tests: `node --test --test-isolation=none tests/lifePresence.test.mjs`.

## Xiaobai tutorial template

`frontend/src/composables/lifeTutorialSteps.js` is the editable Chinese copy/step template:
17 stable ids with title/text/target/prepare/action. Edit text independently of game rules.
`LifeTutorial.vue` teleports above the whole app and uses four dark mask panels and
an intercepted spotlight hitbox. Only safe presentation actions run; keyboard focus
is trapped in the guide, Escape skips, and missing targets still allow Next. Geometry
updates every animation frame while open, including drawer transitions/scroll/resize.
First successful save load auto-starts once per account per browser; localStorage
`wsw:life:tutorial:v1:user:<id>` stores completion/skip (not token, not server progress).
Replay via 新手指引. Xiaobai uses the existing 白 monogram, fixed local copy, no mascot
chat API. Dialogue/action stages are explicitly separate teaching demos. No rewards,
friend changes, travel, game-day changes or game-save operations are performed by
steps. Previous drawer/list selections and scroll are restored when closed. Completion
is local only; clearing browser storage or another browser shows the guide again.
Tests: `node --test --test-isolation=none tests/lifeTutorial.test.mjs`.

## Verification

From backend: `.venv/Scripts/python.exe -m unittest discover -s tests -p test_virtual_life.py -v`
Test creates isolated temporary SQLite file; verifies authenticated ownership,
staff/super-admin access and isolation, ordinary/volunteer/missing auth rejection,
owner injection rejection, stale revisions,
restoration after app/engine restart, malformed state. Does not mutate real saves.

From frontend: `npm run build` and `node --test --test-isolation=none tests/lifeSave.test.mjs`.
Permission regression: `node --test --test-isolation=none tests/lifeAccess.test.mjs`
checks navigation/page gates and executes the route guard for staff, super-admin,
ordinary user, volunteer, mobile and missing-token cases.
The frontend unit tests verify token ownership, serial saves during concurrent local edits,
and conflict preservation (using an isolated composable harness, not browser rendering).
Restart the existing backend (no reload mode) after deploying; no replacement
server or shared-business routes are introduced.
