<script setup>
import { computed } from 'vue'
import { Globe, MapPin, Users } from '@lucide/vue'
import { commonFriendsText, commonGroupsText, worldNames } from '../trust'

const props = defineProps({
  trust: { type: Object, default: null },
})

const friends = computed(() => commonFriendsText(props.trust))
const groups = computed(() => commonGroupsText(props.trust))
const worlds = computed(() => worldNames(props.trust))
const visible = computed(
  () => Boolean(props.trust?.verified && (friends.value || groups.value || worlds.value.length)),
)
</script>

<template>
  <ul v-if="visible" class="vr-trust-facts">
    <li v-if="friends"><Users :size="13" aria-hidden="true" /><span>{{ friends }}</span></li>
    <li v-if="groups"><Globe :size="13" aria-hidden="true" /><span>{{ groups }}</span></li>
    <li v-if="worlds.length">
      <MapPin :size="13" aria-hidden="true" /><span>常驻 World：{{ worlds.join('、') }}</span>
    </li>
  </ul>
</template>
