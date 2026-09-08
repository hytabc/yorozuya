<script setup>
// 功能抽屉内容：世界探索 / 房间 / 好友 / 人物资料 / 人生手记。
// 外壳(.drawer/.drawer-content)留在 LifeSimulator.vue；样式从 LifeSimulator.vue 迁出，行为不变。
import { WORLDS, STATUS_LABELS, presenceFor, worldFor, roomDecision } from '../../composables/lifePresence'

const props = defineProps({ game: { type: Object, required: true } })
const {
  panel, unlockedWorlds, selectedWorld, visibleRooms, currentRoomId,
  friends, friendIds, profileId, profileNpc, profilePresence, profileJoin,
  profileRoom, profileAdd, diaryHistory, saveReady, saveConflict,
  exploreWorld, enterRoom, selectFriend, addFriend, joinFriend, portraitFor,
} = props.game
const worlds = WORLDS
</script>

<template>
  <section v-if="panel === 'worlds'" class="drawer-body">
    <h2>世界探索 <small>{{ unlockedWorlds }} / 30</small></h2>
    <p class="reply-hint">选择地图查看房间，只能加入有人、未满的非私密房间。</p>
    <div v-for="w in worlds" :key="w.name" class="world-line">
      <div class="world-thumb" :style="{ background: 'linear-gradient(145deg,' + w.color + ',#e8e6e0)' }"><span>WORLD</span></div>
      <div><strong>{{ w.name }}</strong><small>{{ w.vibe }}</small></div>
      <div class="world-entry">
        <button @click="exploreWorld(w)">查看房间</button>
      </div>
    </div>
  </section>

  <section v-else-if="panel === 'rooms'" class="drawer-body">
    <button class="profile-back" @click="panel = 'worlds'">← 世界列表</button>
    <h2>{{ selectedWorld?.name }} · 房间</h2>
    <p class="reply-hint">人数为模拟人物与背景访客；无创建房间功能。</p>
    <div v-for="room in visibleRooms" :key="room.id" class="world-line">
      <div><strong>{{ room.label }} · {{ room.private ? '私密' : '公开' }}</strong><small>{{ room.occupants + (currentRoomId === room.id ? 1 : 0) }}/{{ room.capacity }} 人{{ currentRoomId === room.id ? ' · 你在这里' : '' }}</small></div>
      <div class="world-entry"><button :disabled="!saveReady || saveConflict || !roomDecision(room).allowed" @click="enterRoom(room.id)">{{ currentRoomId === room.id ? '返回房间' : '加入' }}</button><small v-if="!roomDecision(room).allowed">{{ roomDecision(room).reason }}</small></div>
    </div>
  </section>
  <section v-else-if="panel === 'friends'" class="drawer-body">
    <h2>好友 <small>{{ friends.length }} 位</small></h2>
    <p v-if="!friends.length" class="reply-hint">还没有好友。先在房间中互动至少一次，好感达到 10 后，从人物资料主动添加。</p>
    <div class="friend-list">
      <div v-for="npc in friends" :key="npc.id" class="friend-row">
        <button class="profile-avatar" @click="selectFriend(npc.id)" :aria-label="'查看' + npc.name + '的资料'"><img :src="portraitFor(npc.id)" :alt="npc.name" /></button>
        <span class="friend-detail"><strong>{{ npc.name }}</strong></span>
        <span class="presence-label" :class="presenceFor(npc.id).status">● {{ STATUS_LABELS[presenceFor(npc.id).status] }}</span>
      </div>
    </div>
  </section>
  <section v-else-if="panel === 'profile' && profileNpc" class="drawer-body profile-body">
    <button class="profile-back" @click="panel = 'friends'">← 好友列表</button>
    <div class="profile-heading"><img :src="portraitFor(profileNpc.id)" :alt="profileNpc.name" /><h2>{{ profileNpc.name }}</h2></div>
    <p class="presence-label" :class="profilePresence.status">● {{ STATUS_LABELS[profilePresence.status] }}</p>
    <p>{{ profileNpc.role }} · {{ profilePresence.intro }}</p>
    <p>所在世界：{{ profileRoom ? worldFor(profileRoom.worldId).name + ' · ' + profileRoom.label : '离线 · 暂无房间' }}</p>
    <div class="profile-affection"><strong>好感 {{ profileNpc.bond }}/100</strong><span class="friend-meter"><i :style="{ width: profileNpc.bond + '%' }"></i></span></div>
    <button class="profile-join" :disabled="!saveReady || saveConflict || !profileAdd.allowed" @click="addFriend">{{ friendIds.includes(profileId) ? '已是好友' : '添加好友' }}</button>
    <p class="reply-hint" role="status">{{ profileAdd.reason }}</p>
    <button v-if="friendIds.includes(profileId)" class="profile-join" :disabled="!saveReady || saveConflict || !profileJoin.allowed" @click="joinFriend">加入所在房间</button>
    <p class="reply-hint">{{ profileJoin.allowed ? '加入后，请点击场景内人物头像交谈。' : profileJoin.reason }}</p>
    <small class="profile-mock">模拟好友状态与世界，尚未连接真实 VRC。</small>
  </section>
  <section v-else-if="panel === 'diary'" class="drawer-body">
    <h2>人生手记</h2>
    <blockquote v-for="h in diaryHistory" :key="h.day">
      <p>{{ h.text }}</p>
      <small>第 {{ h.day }} 天 · {{ h.mood }}</small>
    </blockquote>
  </section>
</template>

<style scoped>
/* 功能抽屉 */
.drawer-body h2 {
  display: flex; align-items: baseline; gap: 10px;
  margin-bottom: 20px; font-size: 18px;
}
.drawer-body h2 small { color: #69736e; font-size: 11px; }
.world-line {
  display: grid;
  grid-template-columns: 56px 1fr auto;
  align-items: center; gap: 12px;
  padding: 12px 0;
  border-top: 1px solid #f0f2f0;
}
.world-thumb {
  height: 44px; border-radius: 6px;
  overflow: hidden; position: relative;
}
.world-thumb span {
  position: absolute; bottom: 4px; left: 6px;
  font-size: 7px; letter-spacing: 0.1em;
  color: rgba(255, 255, 255, 0.8);
}
.world-line strong, .world-line small { display: block; }
.world-line strong { font-size: 13px; }
.world-line small { margin-top: 3px; color: #69736e; font-size: 10px; }
.world-line > b { color: #9a9fa0; font-size: 10px; font-weight: 400; }
.world-entry { margin-left: auto; flex-shrink: 0; text-align: right; max-width: 125px; }
.world-entry button { border: 1px solid #237a57; border-radius: 7px; padding: 7px 13px; background: #237a57; color: #fff; cursor: pointer; }
.world-entry button:disabled { background: #e3e8e2; border-color: #d9dedb; color: #788576; cursor: not-allowed; }
.world-entry button:focus-visible { outline: 2px solid #237a57; outline-offset: 3px; }
blockquote {
  margin: 0 0 14px;
  padding: 14px 16px;
  border-left: 2px solid #237a57;
  background: #f8f9f8;
}
blockquote p { margin: 0 0 6px; font-size: 13px; line-height: 1.6; }
blockquote small { color: #69736e; font-size: 10px; }

.reply-hint { margin: 8px 2px 2px; font-size: 11px; color: #788576; line-height: 1.6; }

.friend-list { display: grid; gap: 9px; }
.friend-row { display: flex; align-items: center; gap: 12px; width: 100%; padding: 11px; border: 1px solid #dfe6df; border-radius: 9px; background: #fffefa; color: #263b30; text-align: left; cursor: pointer; }
.friend-row.selected { background: #edf5ed; border-color: #89b297; }
.friend-row:hover:not(:disabled) { border-color: #237a57; }
.friend-row:disabled { opacity: .55; cursor: not-allowed; }
.friend-row:focus-visible { outline: 2px solid #237a57; outline-offset: 2px; }
.friend-row img { width: 38px; height: 38px; object-fit: cover; border-radius: 50%; }
.friend-detail { flex: 1; min-width: 0; }
.friend-detail strong { font-size: 13px; }
.friend-detail small { margin-left: 5px; font-size: 10px; color: #69836f; font-weight: 400; }
.friend-meter { display: block; height: 4px; margin-top: 8px; border-radius: 4px; background: #dce7dc; overflow: hidden; }
.friend-meter i { display: block; height: 100%; background: #4d9670; }
.friend-bond { color: #237a57; font-size: 12px; white-space: nowrap; }
.friend-bond small { display: block; color: #788576; font-size: 10px; margin-top: 4px; }

.profile-avatar { padding: 0; border: 0; background: transparent; border-radius: 50%; cursor: pointer; }
.profile-avatar img { display: block; }
.profile-avatar:focus-visible { outline: 2px solid #237a57; outline-offset: 3px; }
.friend-row { cursor: default; }
.presence-label { font-size: 12px; color: #7a827e; }
.presence-label.green { color: #237a57; }
.presence-label.orange { color: #b77427; }
.presence-label.red { color: #b84949; }
.profile-back { border: 0; background: transparent; color: #237a57; cursor: pointer; padding: 8px 0; }
.profile-heading { display: flex; align-items: center; gap: 14px; margin-top: 12px; }
.profile-heading img { width: 64px; height: 64px; object-fit: cover; border-radius: 50%; }
.profile-heading h2 { margin: 0; }
.profile-body p { font-size: 13px; line-height: 1.7; }
.profile-affection { padding: 16px 0; color: #237a57; font-size: 13px; }
.profile-join { padding: 10px 18px; background: #237a57; color: #fff; border: 0; border-radius: 8px; cursor: pointer; }
.profile-join:disabled { background: #dce2dc; color: #788576; cursor: not-allowed; }
.profile-mock { display: block; margin-top: 20px; color: #788576; font-size: 10px; }
</style>
