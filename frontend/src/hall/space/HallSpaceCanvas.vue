<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { clusterLinks, nodeColor } from './layout'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  selectedId: { type: Number, default: null },
})
const emit = defineEmits(['select', 'open', 'fallback'])

const host = ref(null)
const labels = ref([])
const failed = ref('')

let renderer = null
let scene = null
let camera = null
let controls = null
let observer = null
let frame = 0
let group = null
let viewHeight = 32
const geometry = new THREE.CircleGeometry(0.42, 24)
const selectedGeometry = new THREE.RingGeometry(0.62, 0.76, 32)

function updateLabels() {
  if (!host.value || !camera) return
  const rect = host.value.getBoundingClientRect()
  labels.value = props.nodes.map((node) => {
    const projected = new THREE.Vector3(node.x, node.y, 0).project(camera)
    return {
      id: node.id,
      task: node.task,
      left: `${((projected.x * 0.5) + 0.5) * rect.width}px`,
      top: `${((-projected.y * 0.5) + 0.5) * rect.height}px`,
      visible: projected.z < 1,
    }
  })
}

function draw() {
  if (frame) return
  frame = requestAnimationFrame(() => {
    frame = 0
    if (!renderer || !scene || !camera) return
    updateLabels()
    renderer.render(scene, camera)
  })
}

function clearGroup() {
  if (!group) return
  for (const child of [...group.children]) {
    group.remove(child)
    if (child.geometry && child.geometry !== geometry && child.geometry !== selectedGeometry) {
      child.geometry.dispose()
    }
    if (child.material) child.material.dispose()
  }
}

function rebuild() {
  if (!scene) return
  if (!group) {
    group = new THREE.Group()
    scene.add(group)
  }
  clearGroup()

  for (const node of props.nodes) {
    const material = new THREE.MeshBasicMaterial({ color: nodeColor(node.task) })
    const mesh = new THREE.Mesh(geometry, material)
    mesh.position.set(node.x, node.y, node.z)
    group.add(mesh)
    if (node.id === props.selectedId) {
      const ring = new THREE.Mesh(selectedGeometry, new THREE.MeshBasicMaterial({ color: '#e8e2d2' }))
      ring.position.set(node.x, node.y, 0.05)
      group.add(ring)
    }
  }

  const positions = []
  const byId = new Map(props.nodes.map((node) => [node.id, node]))
  for (const link of clusterLinks(props.nodes)) {
    const from = byId.get(link.from)
    const to = byId.get(link.to)
    if (!from || !to) continue
    positions.push(from.x, from.y, 0, to.x, to.y, 0)
  }
  if (positions.length) {
    const lineGeometry = new THREE.BufferGeometry()
    lineGeometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
    group.add(new THREE.LineSegments(
      lineGeometry,
      new THREE.LineBasicMaterial({ color: '#5b7a6c', transparent: true, opacity: 0.45 }),
    ))
  }
  draw()
}

function resize() {
  if (!host.value || !renderer || !camera) return
  const rect = host.value.getBoundingClientRect()
  if (!rect.width || !rect.height) return
  const aspect = rect.width / rect.height
  camera.left = (-viewHeight * aspect) / 2
  camera.right = (viewHeight * aspect) / 2
  camera.top = viewHeight / 2
  camera.bottom = -viewHeight / 2
  camera.updateProjectionMatrix()
  renderer.setSize(rect.width, rect.height)
  draw()
}

onMounted(() => {
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  } catch {
    failed.value = '此浏览器无法启动 WebGL，请切换回列表视图。'
    emit('fallback')
    return
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
  renderer.domElement.setAttribute('aria-hidden', 'true')
  host.value.appendChild(renderer.domElement)

  scene = new THREE.Scene()
  camera = new THREE.OrthographicCamera(-16, 16, 16, -16, 0.1, 200)
  camera.position.set(0, 0, 40)
  camera.lookAt(0, 0, 0)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableRotate = false
  controls.enableDamping = false
  controls.screenSpacePanning = true
  controls.minZoom = 0.5
  controls.maxZoom = 3
  controls.addEventListener('change', draw)

  observer = new ResizeObserver(resize)
  observer.observe(host.value)
  rebuild()
  resize()
})

onBeforeUnmount(() => {
  if (frame) cancelAnimationFrame(frame)
  observer?.disconnect()
  controls?.dispose()
  clearGroup()
  geometry.dispose()
  selectedGeometry.dispose()
  renderer?.dispose()
  renderer?.domElement?.remove()
  renderer = null
  scene = null
  camera = null
  controls = null
})

watch(() => props.nodes, rebuild, { deep: false })
watch(() => props.selectedId, rebuild)
</script>

<template>
  <div class="hall-space-stage">
    <div ref="host" class="hall-space-canvas" />
    <p v-if="failed" class="scene-failure">{{ failed }}</p>
    <button
      v-for="label in labels"
      v-show="label.visible"
      :key="label.id"
      type="button"
      class="hall-space-label"
      :class="{ active: label.id === selectedId }"
      :style="{ left: label.left, top: label.top }"
      @click="$emit('select', label.task)"
      @dblclick="$emit('open', label.task)"
    >
      <span class="hall-space-dot" :style="{ background: nodeColor(label.task) }" />
      {{ label.task.title }}
    </button>
  </div>
</template>
