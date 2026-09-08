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
- State: `schemaVersion:1`, day, stats (mood/energy/social/explore), tags,
  currentWorld, unlockedWorlds, currentNpcId, npcs, conversations, diary, completed.
  v1 NPC ids/order: ache, xiaomi, maoyou, yu. Unknown schemas/ids rejected.
  Encoded state limit 2 MB; no silent history truncation. Message length 4000.

## Frontend

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
