<script setup>
import { CHARACTER_COLOR, CHARACTER_LABEL } from '../engine/constants.js'

defineProps({
  characters: { type: Array, required: true },
  relationships: { type: Array, default: () => [] },
})

function relationshipLabel(pair) {
  return `${CHARACTER_LABEL[pair.from] || pair.from} → ${CHARACTER_LABEL[pair.to] || pair.to}｜${pair.label}`
}
</script>

<template>
  <div>
    <div class="frost-char-grid">
      <article
        v-for="character in characters"
        :key="character.id"
        class="frost-char"
        :style="{ borderLeftColor: CHARACTER_COLOR[character.id] || '#D8D8D2' }"
      >
        <h4>{{ character.name }} <span class="frost-char-role">{{ character.vrcId }}</span></h4>
        <p class="frost-char-role">{{ character.role }}<template v-if="character.occupation"> · {{ character.occupation }}</template></p>
        <p class="frost-char-line">{{ character.personality }}</p>
        <p class="frost-char-line"><strong>口头禅：</strong>{{ character.catchphrase }}</p>
        <template v-if="character.bond !== undefined">
          <div class="frost-char-bond">
            羁绊值 {{ character.bond > 0 ? `+${character.bond}` : character.bond }}
            <div class="frost-bond-bar">
              <span :style="{ width: `${Math.abs(character.bond)}%`, background: character.bond >= 0 ? '' : '#8fa9a0' }" />
            </div>
          </div>
        </template>
      </article>
    </div>

    <div v-if="relationships.length" class="frost-panel" style="margin-top: 16px">
      <h3>关系网络</h3>
      <p v-for="(pair, index) in relationships" :key="index" class="frost-char-line">
        {{ relationshipLabel(pair) }}<template v-if="pair.bidirectional">（双向）</template>
      </p>
    </div>
  </div>
</template>
