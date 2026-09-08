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
  defaults `{}` in older saves) and `eventProgress` (stage 8b: `{day, done:[eventId]}`,
  defaults `{day:1,done:[]}` in older saves; unknown event ids are leniently
  dropped on validation).
  Legacy `schemaVersion:1` writes (no packId) are upgraded to v2 on write; v2
  must declare the site's active pack id. NPC/room/action whitelists are derived
  from the ACTIVE content pack stored in the `virtual_life_packs` table (stage
  4a), no longer from code. Unknown schemas/ids/packs rejected. Encoded state
  limit 2 MB; no silent history truncation. Message length 4000.

## Content packs (site-configurable)

A content pack holds the FULL site content as JSON: npcIds/npcs/portraits,
worlds (with optional `bg` image URL), rooms, presence, actions, per-day
node-graph dialogue (`dialogue[npcId]` is a 1-7 entry array of day scripts
`{start, nodes:{id:{lines:[...], image, choices:[{label, effects:{bond,stats},
replies:[...], replyImage, next}]}}}`, stage 5/8a), room events (`events`,
stage 8b: `[{id, roomId, title, icon, scripts×7}]` whose day scripts are linear
`{messages:[...]}` sequences of message groups and choice points) and
initialState. Exactly
one pack is active site-wide (A-scheme: the site admin configures content;
all players share it).

- Table `virtual_life_packs` (id/name/version/content_json/is_active/
  updated_at) is seeded on first startup from `backend/app/life_packs/*.json`;
  the JSON files are seeds only — the database is authoritative afterwards.
- `backend/app/virtual_life_packs.py`: `validate_pack_content` enforces
  structural and reference consistency (room→world, presence→room, dialogue
  node-graph jump targets per day, stat keys, initial state coverage).
  Dialogue nodes are MESSAGE GROUPS (stage 8a): `lines` is a non-empty
  sentence array (multi-line playback), `image`/`replyImage` are optional
  site-local `/uploads/` paths; choices carry `replies` arrays.
  Startup seeding migrates legacy shapes in place (`migrate_pack_content`,
  idempotent): single-script `dialogue[npcId]` → day arrays, `line`→`lines`,
  `reply`→`replies`, image defaults filled.
- Admin API (all gated by `get_role_manager`): GET `/api/virtual-life/pack`
  (active pack detail), GET/POST `/api/virtual-life/packs`, GET/PUT/DELETE
  `/packs/{id}`, POST `/packs/{id}/activate` (exactly one active; activating
  revalidates), POST `/packs/{id}/duplicate`. Content updates bump `version`.
  The active pack cannot be deleted. Save validation follows the active pack
  immediately after activation. Activation additionally MIGRATES existing
  saves in place (stage 7): every save whose `packId` differs is re-pointed
  at the new pack and re-validated (`GameState` + cross-checks); compatible
  saves are rewritten with their `revision` untouched (client CAS is not
  disturbed), incompatible ones are left as-is and keep the pre-existing
  graceful cross-pack error path. The activate response carries
  `saveMigration: {migrated, skipped}` and the admin toast reports both.
- POST `/api/virtual-life/assets` (stage 4d): single image upload for world
  backgrounds and NPC portraits — magic-byte sniffing (JPEG/PNG/GIF/WebP),
  5 MiB cap, stored under the uploads mount as `life/<uuid>.<ext>` and served
  at `/uploads/...`.

## Admin UI (/life-admin, stage 4d)

`frontend/src/views/LifeAdmin.vue` plus `frontend/src/life/admin/` (data layer
`useLifeAdmin.js` singleton, sections `AdminNpcs` / `AdminWorlds` /
`AdminActions` / `AdminDialogue` / `AdminEvents` (stage 8b) / `AdminInitial`,
shared `AdminImageField`).
The route uses the same `lifeOnly` guard as the game (role manager + desktop);
the game header links to it via 内容管理. The admin edits one pack at a time in
structured forms: NPC profiles/portraits/presence, worlds (incl. background
upload) and rooms, actions, the per-NPC dialogue node graph and the initial
player state. Dialogue is edited PER DAY (stage 5): tabs 第 1~7 天 switch the
day script being edited; packs with fewer than 7 days are padded by cloning
their last day on load. Each day is edited through a MIND-MAP canvas (stage 6):
the start node sits at the left and choice branches spread rightward as
connected cards (edges labeled with the choice text); layering uses the
LONGEST path from the start so galgame-style converging branches render as a
proper diamond — the merge node lands right of ALL its parents with solid
inbound edges and a 汇合 badge; only true back/cross edges (cycles) are
dashed, and unreachable nodes are placed apart and marked 未连接. Clicking
a card opens that node's edit panel (multi-line `lines`, node image,
choices with multi-line `replies` + reply image, effects, jump targets);
a choice's jump dropdown offers "＋ 新建节点…" to create-and-link in one
step, any node can be made the start.
Node add/delete applies to the current day only; deleting the start node
hands the start over to the first remaining node, and the last node of a day
cannot be deleted. The default pack ships 2-3 node chains (with branches)
for every NPC on all 7 days. Saving PUTs the whole content; server-side
validation errors are surfaced verbatim, and content edits bump the pack
version. Pack list operations: select, duplicate,
activate (exactly one active, player side and save validation follow
immediately; stage 7 also migrates compatible existing saves in place and
the toast reports 迁移 N 份 / 不兼容 M 份), delete (inactive only). NPC/world/room removal cascades
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

## Dialogue node-graph engine (stage 4c, per-day scripts in stage 5, message groups in 8a)

Each NPC has a 1-7 entry array of day scripts `{start, nodes:{id:{lines,
image, choices}}}` in the active pack. `scriptForDay(days, day)` picks the script for
the current game day — CLAMPED, not cycling: the content ends at day 7, and
any later game day keeps using the last day script. Pure rules live in
`frontend/src/composables/lifeDialogue.js`
(`scriptForDay`/`nodeFor`/`startMessages`/`groupMessages`/`resolveDialogueChoice`/`sanitizeDialogueNodes`);
state and mutations stay in `useLifeGame`. Semantics per NPC per game day:

- MESSAGE GROUPS (stage 8a): node `lines` and choice `replies` are sentence
  arrays played sequentially (click skips/advances as before);
  `groupMessages` expands a group into one save message per sentence and
  attaches the group's `image` to the LAST sentence's message. The bubble
  shows a thumbnail once the line finishes typing; clicking it opens the
  fullscreen lightbox (`LifeImageLightbox.vue`, click/Esc closes) — history
  drawer messages render the same thumbnail + lightbox.
- The chain starts at `start`; the start node's message group is the daily
  greeting. Different days can have entirely different chains (the default
  pack ships 2-3 node chains with distinct greetings per NPC for all 7 days).
- A choice applies its `effects` explicitly (`bond` added to the NPC bond,
  `stats` clamped 0-100) — no text parsing. The toast text is rendered from
  effects via `effectText`.
- `next` non-null advances to that node THE SAME day: the NPC's reply group
  and the next node's group are appended atomically and played in order;
  `completed` stays false and the new node's choices are offered. `next:
  null` marks the day complete (choices hide, actions remain available).
  Jumps may target ANY node of the day, so galgame-style diamonds work:
  branches diverge on choices and later converge into a shared node (stage
  6c; the default pack demos one in maoyou day 5).
- Position (`dialogueNodes`) is persisted in the save, so a mid-chain reload
  resumes at the exact node; hydration drops positions pointing at nodes that
  no longer exist. Server validation rejects unknown NPCs/node ids.
- `nextDay` clears positions and completion; every NPC greets from the NEW
  day's `start` (or the last day script once past the schedule). Choice
  effects apply per choice click — replaying a finished chain next day yields
  its effects again, as before.

## Room events (stage 8b)

Rooms can hold clickable EVENTS: each `{id, roomId, title, icon, scripts×7}`
plays a per-day LINEAR script (clamped at day 7 — no day 8, no cycling) in a
group-chat modal (`LifeEventModal.vue`, z-9000). Script items are message
groups (same shape as 8a dialogue: `speaker` is exactly one of `{npcId}` or a
free passerby `{name, avatar?}`, non-empty `lines`, optional `/uploads/`
`image` on the last sentence, lightbox on click) or choice points
(`{choice:{options:[{label, effects, reply:[groups...]}]}}`). Choice effects
are `stats` (clamped 0-100) plus an optional targeted `bond:{npcId, value}`
(-100..100, applied to that NPC's 0-100 bond on finish; unknown NPCs or other
effect keys are rejected by validation), replies are message groups
only — nested choice points are invalid. Playback: groups appear one at a
time on click; a choice point pauses, the picked label is inserted as a
player bubble (right, green), its reply groups play, then the main line
resumes; the script ends with a 剧终 marker. Effects chosen along the way are
accumulated and settled (0-100 clamp) only when the event is finished —
closing midway discards them.

Each event is playable ONCE per game day: `roomEvents` marks finished entries
done (greyed ✓, disabled); completion lives in the save as
`eventProgress:{day, done:[eventId]}` and resets when the day changes
(client-side `normalizeEventProgress`; the server stores the field and
leniently drops ids the active pack no longer defines). `derive_save_rules`
exposes `eventIds`. Pure rules live in
`frontend/src/composables/lifeEvents.js` (`eventScriptForDay`/`eventsForRoom`/
`isEventDone`/`applyEventChoice`/`eventEffectsOf`/`normalizeEventProgress`);
state and actions (`openEvent`/`closeEvent`/`finishEvent`) stay in
`useLifeGame`. The scene renders entry pills under the location tag
(`LifeScene.vue`).

Admin edits events in the 事件 section (`AdminEvents.vue`): events grouped by
room (icon/title/room editable, add/remove; removal of a room/world removes
its events, removal of an NPC rewrites event speakers to 路人), and a LINEAR
per-day editor (tabs 第 1~7 天) with two card types — message-group cards
(speaker dropdown NPC/路人, multi-line `lines`, image field, reorder) and
choice-point cards (options with label, four stat inputs and an optional
targeted 好感 row (NPC dropdown + value), inline reply message groups; no
nested choice entry). Dialogue and event numeric inputs hard-clamp on typing
(对话 bond 0..100, stats -100..100; 事件 bond -100..100). Both backend
(`validate_pack_content`) and frontend (`validateLifePack`) enforce: event id
unique, roomId exists, exactly 7 scripts, speaker exactly-one, known stat keys
in -100..100, bond target NPC exists, no nested choice points, image only
`/uploads/`. Packs lacking `events` migrate to `events:[]` idempotently. The
default pack ships two sample events (🌊 涨潮时分 in beach-1024 with choice
points on days 3/6, ☕ 柜台边的闲聊 in cafe-1101 with one on day 5).

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
