<script setup>
// 世界与房间区块:世界列表(含背景图)、各世界房间实例。
import { computed, reactive } from 'vue'
import { adminState, addWorld, removeWorld, addRoom, removeRoom } from './useLifeAdmin'
import AdminImageField from './AdminImageField.vue'

const content = computed(() => adminState.content)
const roomsOf = worldId => content.value.rooms.filter(r => r.worldId === worldId)

const worldDraft = reactive({ id: '', name: '', error: '' })
function submitAddWorld() {
  const id = worldDraft.id.trim()
  if (!/^[a-z0-9-]+$/.test(id)) { worldDraft.error = 'id 只能用小写字母、数字、连字符'; return }
  worldDraft.error = addWorld(id, worldDraft.name.trim())
  if (!worldDraft.error) { worldDraft.id = ''; worldDraft.name = '' }
}
function submitRemoveWorld(world) {
  if (!window.confirm(`删除世界「${world.name}」？其全部房间将一并删除，相关人物改为离线。`)) return
  removeWorld(world.id)
}

const roomDraft = reactive({ id: '', worldId: '', label: '', error: '' })
function submitAddRoom() {
  const id = roomDraft.id.trim()
  if (!/^[a-z0-9-]+$/.test(id)) { roomDraft.error = 'id 只能用小写字母、数字、连字符'; return }
  roomDraft.error = addRoom(id, roomDraft.worldId, roomDraft.label.trim())
  if (!roomDraft.error) { roomDraft.id = ''; roomDraft.label = '' }
}
function submitRemoveRoom(room) {
  if (!window.confirm(`删除房间「${room.id}」？房间内人物将改为离线。`)) return
  removeRoom(room.id)
}
</script>

<template>
  <section class="la-section">
    <h2>世界与房间</h2>
    <p>世界是玩家探索的地图，背景图（bg）会渲染为游戏场景大图；房间是世界内的可加入实例，只能加入有人、未满的非私密房间。</p>

    <table class="la-table">
      <thead><tr><th>id</th><th>名称</th><th>氛围</th><th>主题色</th><th>背景图</th><th></th></tr></thead>
      <tbody>
        <tr v-for="w in content.worlds" :key="w.id">
          <td><code>{{ w.id }}</code></td>
          <td><input v-model="w.name" type="text" style="width:110px" /></td>
          <td><input v-model="w.vibe" type="text" style="width:150px" /></td>
          <td><input v-model="w.color" type="color" style="width:40px;height:28px;padding:1px" /></td>
          <td><AdminImageField v-model="w.bg" placeholder="留空用占位场景" /></td>
          <td><button class="la-mini la-danger" :disabled="content.worlds.length <= 1" @click="submitRemoveWorld(w)">删</button></td>
        </tr>
      </tbody>
    </table>
    <div class="la-add-row">
      <input v-model="worldDraft.id" type="text" placeholder="新世界 id（如 forest）" />
      <input v-model="worldDraft.name" type="text" placeholder="名称" />
      <button class="la-mini" @click="submitAddWorld">+ 新增世界</button>
      <small v-if="worldDraft.error" class="la-missing">{{ worldDraft.error }}</small>
    </div>

    <h3 class="la-sub">房间</h3>
    <table class="la-table">
      <thead><tr><th>id</th><th>所属世界</th><th>房号</th><th>私密</th><th>容量</th><th>人数</th><th></th></tr></thead>
      <tbody>
        <template v-for="w in content.worlds" :key="w.id">
          <tr v-for="room in roomsOf(w.id)" :key="room.id">
            <td><code>{{ room.id }}</code></td>
            <td>{{ w.name }}</td>
            <td><input v-model="room.label" type="text" style="width:80px" /></td>
            <td><input v-model="room.private" type="checkbox" /></td>
            <td><input v-model.number="room.capacity" type="number" min="1" /></td>
            <td><input v-model.number="room.occupants" type="number" min="0" /></td>
            <td><button class="la-mini la-danger" @click="submitRemoveRoom(room)">删</button></td>
          </tr>
        </template>
      </tbody>
    </table>
    <div class="la-add-row">
      <input v-model="roomDraft.id" type="text" placeholder="新房间 id（如 beach-3001）" />
      <select v-model="roomDraft.worldId">
        <option value="" disabled>选择世界</option>
        <option v-for="w in content.worlds" :key="w.id" :value="w.id">{{ w.name }}</option>
      </select>
      <input v-model="roomDraft.label" type="text" placeholder="房号（如 #3001）" />
      <button class="la-mini" :disabled="!roomDraft.worldId" @click="submitAddRoom">+ 新增房间</button>
      <small v-if="roomDraft.error" class="la-missing">{{ roomDraft.error }}</small>
      <small v-else class="la-hint">人数为模拟占位；空房(0)、满房、私密房玩家不可加入。</small>
    </div>
  </section>
</template>
