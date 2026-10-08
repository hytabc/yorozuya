<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { normalizedVoxels } from './engine'

const props = defineProps({ room: Object, assets: { type: Object, default: () => ({}) }, selected: String,
  data: Object, invalidId: String, tool: { type: String, default: 'camera' }, sliceAxis: { type: Number, default: 2 }, slice: { type: Number, default: -1 },
  textureUrls: { type: Object, default: () => ({}) }, readonly: Boolean, compact: Boolean })
const emit = defineEmits(['pick', 'voxel', 'stroke-start', 'stroke-end', 'drag', 'drag-end', 'error'])
const host = ref(), failed = ref('')
let renderer, scene, camera, controls, observer, frame, disposed = false, content, floor, down, dragging, stroking = false
const ray = new THREE.Raycaster(), pointer = new THREE.Vector2(), geometry = new THREE.BoxGeometry(1, 1, 1)
const materials = new Set(), textures = new Map(), pickables = [], meshes = [], cube = new THREE.Object3D()
const mapping = ([x, y, z]) => new THREE.Vector3(x, z, y)

function draw() {
  if (!renderer || disposed || frame) return
  frame = requestAnimationFrame(() => { frame = 0; if (!disposed) renderer.render(scene, camera) })
}
function material(options) { const m = new THREE.MeshLambertMaterial(options); materials.add(m); return m }
function resetCamera() {
  if (!camera) return
  const n = props.data?.gridSize || 256, h = props.data ? n / 3 : 22
  camera.position.set(-n * 1.1, n * 1.5, -n * 1.1); controls.target.set(n / 2, h, n / 2)
  camera.zoom = 1; camera.updateProjectionMatrix(); controls.update(); draw()
}
function zoom(delta) { if (!camera) return; camera.zoom = Math.max(.25, Math.min(10, camera.zoom * delta)); camera.updateProjectionMatrix(); draw() }
function orbit(delta) {
  if (!camera) return
  const v = camera.position.clone().sub(controls.target).applyAxisAngle(new THREE.Vector3(0, 1, 0), delta)
  camera.position.copy(controls.target).add(v); controls.update(); draw()
}
function texture(url, repeat) {
  if (!url) return null
  const key = `${url}:${repeat}`
  if (textures.has(key)) return textures.get(key)
  const t = new THREE.TextureLoader().load(url, draw, undefined, () => emit('error', '纹理暂时无法加载，已保留底色'))
  t.colorSpace = THREE.SRGBColorSpace; t.wrapS = t.wrapT = THREE.RepeatWrapping
  t.repeat.set(repeat, repeat); textures.set(key, t); return t
}
function addPlane(w, h, mat, position, rotation = 0) {
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), mat)
  mesh.position.copy(position); mesh.rotation.x = rotation; content.add(mesh); return mesh
}
function addVoxels(data, position, rotation, ident, overrides = {}, editor = false) {
  const points = editor ? data.voxels : normalizedVoxels(data, rotation)
  const cells = new Set(points.map((p) => p.slice(0, 3).join(',')))
  const visible = points.filter(([x, y, z]) => {
    if (editor && props.slice >= 0 && [x, y, z][props.sliceAxis] > props.slice) return false
    return [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]].some(([a, b, c]) => !cells.has([x + a, y + b, z + c].join(',')) || editor && props.slice >= 0 && [x + a, y + b, z + c][props.sliceAxis] > props.slice)
  })
  const m = material({ color: '#ffffff' })
  for (let offset = 0; offset < visible.length; offset += 16384) {
    const batch = visible.slice(offset, offset + 16384)
    const mesh = new THREE.InstancedMesh(geometry, m, batch.length)
    const palette = data.palette.map((s) => new THREE.Color(ident === props.invalidId ? '#cf5360' : s.editable && overrides[s.key] || s.color))
    batch.forEach(([x, y, z, c], i) => {
      cube.position.set(x + .5 + position.x, z + .5 + position.z, y + .5 + position.y); cube.updateMatrix()
      mesh.setMatrixAt(i, cube.matrix); mesh.setColorAt(i, palette[c] || new THREE.Color('#cbbba5'))
    })
    mesh.instanceMatrix.needsUpdate = true; if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
    mesh.computeBoundingSphere(); mesh.computeBoundingBox(); mesh.userData = { id: ident, points: batch, position }
    content.add(mesh); meshes.push(mesh); pickables.push(mesh)
  }
  if (ident && props.selected === ident && points.length) {
    const box = new THREE.Box3()
    for (const [x, y, z] of points) { box.expandByPoint(mapping([x + position.x, y + position.y, z + position.z])); box.expandByPoint(mapping([x + 1 + position.x, y + 1 + position.y, z + 1 + position.z])) }
    const helper = new THREE.Box3Helper(box, '#358462'); content.add(helper)
  }
}
function rebuild() {
  if (!scene || disposed) return
  if (content) {
    scene.remove(content)
    content.traverse((o) => { if (o.geometry && o.geometry !== geometry) o.geometry.dispose(); if (o.material) (Array.isArray(o.material)?o.material:[o.material]).forEach((m)=>m.dispose()); if (o.isInstancedMesh) o.dispose() })
  }
  materials.forEach((m) => m.dispose()); materials.clear(); meshes.length = pickables.length = 0
  content = new THREE.Group(); scene.add(content)
  const n = props.data?.gridSize || 256
  const grid = new THREE.GridHelper(n, props.data ? n : 32, '#b8b0a1', '#ded6c5')
  grid.position.set(n / 2, -.02, n / 2); content.add(grid)
  if (props.data) {
    floor = addPlane(n, n, material({ color: '#e6e0d3', side: THREE.DoubleSide }), new THREE.Vector3(n / 2, -.2, n / 2), -Math.PI / 2)
    addVoxels(props.data, { x: 0, y: 0, z: 0 }, 0, '', {}, true)
    if (props.slice >= 0) {
      const slice = new THREE.Mesh(new THREE.PlaneGeometry(n, n), new THREE.MeshBasicMaterial({ color: '#52977a', transparent: true, opacity: .055, side: THREE.DoubleSide, depthWrite: false }))
      slice.position.set(n / 2, n / 2, n / 2)
      if (props.sliceAxis === 2) { slice.rotation.x = -Math.PI / 2; slice.position.y = props.slice + .02 }
      else if (props.sliceAxis === 0) { slice.rotation.y = Math.PI / 2; slice.position.x = props.slice + .02 }
      else slice.position.z = props.slice + .02
      content.add(slice)
    }
  } else {
    const room = props.room
    if (!room) return
    const floorMat = material({ color: room.floor.color, map: texture(props.textureUrls[room.floor.textureId], room.floor.mode === 'stretch' ? 1 : 8), side: THREE.DoubleSide })
    floor = addPlane(256, 256, floorMat, new THREE.Vector3(128, -.2, 128), -Math.PI / 2)
    const wallMat = material({ color: room.wall.color, map: texture(props.textureUrls[room.wall.textureId], room.wall.mode === 'stretch' ? 1 : 4), side: THREE.DoubleSide })
    addPlane(256, 128, wallMat, new THREE.Vector3(128, 64, 256))
    const side = addPlane(256, 128, wallMat, new THREE.Vector3(256, 64, 128)); side.rotation.y = Math.PI / 2
    for (const p of room.placements) {
      const asset = props.assets[p.versionId]
      if (asset) addVoxels(asset.data, p.position, p.rotation, p.id, p.paletteOverrides)
    }
  }
  draw()
}
let rebuilding
function scheduleRebuild() { cancelAnimationFrame(rebuilding); rebuilding = requestAnimationFrame(rebuild) }
function cast(event) {
  const rect = renderer.domElement.getBoundingClientRect()
  pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1)
  ray.setFromCamera(pointer, camera)
  return ray.intersectObjects([...pickables, ...(floor ? [floor] : [])], false)[0]
}
function voxelAt(event) {
  cast(event)
  if (props.slice >= 0) {
    const normal = mapping([0, 0, 0]); normal.setComponent([0, 2, 1][props.sliceAxis], 1)
    const intersection = ray.ray.intersectPlane(new THREE.Plane(normal, -props.slice), new THREE.Vector3())
    if (!intersection) return
    const p = [Math.floor(intersection.x), Math.floor(intersection.z), Math.floor(intersection.y)]; p[props.sliceAxis] = props.slice
    return p
  }
  const hit = cast(event)
  if (!hit) return
  if (hit.object.userData.points) {
    const p = hit.object.userData.points[hit.instanceId].slice(0, 3)
    if (props.tool === 'add') {
      const n = hit.face.normal
      p[0] += Math.round(n.x); p[1] += Math.round(n.z); p[2] += Math.round(n.y)
    }
    return p
  }
  if (props.tool === 'add') return [Math.floor(hit.point.x), Math.floor(hit.point.z), 0]
}
let lastVoxel
function paint(event) {
  const p = voxelAt(event)
  if (p && p.every((n) => n >= 0 && n < props.data.gridSize) && p.join(',') !== lastVoxel) {
    lastVoxel = p.join(','); emit('voxel', p)
  }
}
function pointerDown(event) {
  if (event.button !== 0 || props.readonly) return
  down = { x: event.clientX, y: event.clientY, id: event.pointerId }
  if (props.data && props.tool !== 'camera') {
    controls.enableRotate = false; stroking = true; lastVoxel = ''; emit('stroke-start'); paint(event)
    renderer.domElement.setPointerCapture(event.pointerId)
  } else if (props.room && props.tool === 'move') {
    const hit = cast(event)
    if (hit?.object.userData.id) {
      dragging = hit.object.userData.id; controls.enableRotate = false
      emit('pick', { id: dragging }); renderer.domElement.setPointerCapture(event.pointerId)
    }
  }
}
function pointerMove(event) {
  if (stroking) paint(event)
  if (dragging) {
    cast(event)
    const p = ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), new THREE.Vector3())
    if (p) emit('drag', { id: dragging, x: p.x, y: p.z })
  }
}
function pointerUp(event) {
  if (stroking) { stroking = false; emit('stroke-end') }
  else if (dragging) { emit('drag-end'); dragging = null }
  else if (down && Math.hypot(event.clientX - down.x, event.clientY - down.y) < 7 && props.room) {
    const hit = cast(event)
    if (hit) emit('pick', { id: hit.object.userData.id, x: hit.point.x, y: hit.point.z, z: Math.max(0, Math.ceil(hit.point.y)) })
  }
  down = null; if (controls) controls.enableRotate = props.tool === 'camera'
}
function resize() {
  if (!renderer || disposed) return
  const width = host.value.clientWidth, height = host.value.clientHeight, n = props.data?.gridSize || 256
  const extent = n * .78, aspect = width / Math.max(height, 1)
  camera.left = -extent * aspect; camera.right = extent * aspect; camera.top = extent; camera.bottom = -extent
  camera.updateProjectionMatrix(); renderer.setSize(width, height, false); draw()
}
watch(() => [props.room, props.assets, props.data, props.selected, props.invalidId, props.slice, props.sliceAxis, props.textureUrls], scheduleRebuild, { deep: true })
watch(() => props.data?.gridSize, () => { resize(); resetCamera() })
watch(() => props.tool, () => { if (controls) controls.enableRotate = props.tool === 'camera' })
onMounted(() => {
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false })
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5)); renderer.setClearColor('#f2eee5'); renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1
    scene = new THREE.Scene(); scene.add(new THREE.HemisphereLight('#fff7e5', '#8d9b83', 1.5))
    const sun = new THREE.DirectionalLight('#fff3dc', 2); sun.position.set(-100, 300, -100); scene.add(sun)
    camera = new THREE.OrthographicCamera(-200, 200, 200, -200, .1, 3000)
    controls = new OrbitControls(camera, renderer.domElement); controls.enableDamping = false; controls.enableRotate = props.tool === 'camera'
    controls.minPolarAngle = .3; controls.maxPolarAngle = Math.PI / 2 - .08; controls.minZoom = .25; controls.maxZoom = 10
    controls.addEventListener('change', draw); host.value.appendChild(renderer.domElement)
    const el = renderer.domElement
    el.addEventListener('pointerdown', pointerDown); el.addEventListener('pointermove', pointerMove); el.addEventListener('pointerup', pointerUp); el.addEventListener('pointercancel', pointerUp)
    el.addEventListener('webglcontextlost', (e) => { e.preventDefault(); failed.value = '三维画布已暂停，请刷新页面恢复；草稿仍保留。' })
    observer = new ResizeObserver(resize); observer.observe(host.value); resize(); resetCamera(); rebuild()
  } catch { failed.value = '此浏览器无法启动 WebGL。仍可浏览家具信息、留言与导出已有草稿。'; emit('error', failed.value) }
})
onBeforeUnmount(() => {
  disposed = true; cancelAnimationFrame(frame); cancelAnimationFrame(rebuilding); observer?.disconnect(); controls?.dispose()
  content?.traverse((o) => { if (o.geometry && o.geometry !== geometry) o.geometry.dispose(); if (o.material) (Array.isArray(o.material)?o.material:[o.material]).forEach((m)=>m.dispose()); if (o.isInstancedMesh) o.dispose() })
  materials.forEach((m) => m.dispose()); textures.forEach((t) => t.dispose()); geometry.dispose(); renderer?.dispose()
})
function pickAt(event) { const hit = cast(event); if (hit) emit('pick', {id:hit.object.userData.id,x:hit.point.x,y:hit.point.z,z:Math.max(0,Math.ceil(hit.point.y))}) }
defineExpose({ resetCamera, zoom, orbit, pickAt })
</script>

<template>
  <div class="house-scene-wrap" :class="{ compact }">
    <div ref="host" class="house-scene" role="img" :aria-label="data ? '体素家具编辑画布' : '等距房屋画布'" />
    <p v-if="failed" class="scene-failure" role="status">{{ failed }}</p>
    <div v-else class="scene-controls" aria-label="视角控制">
      <button @click="orbit(-Math.PI / 4)" aria-label="向左旋转视角">↶</button>
      <button @click="orbit(Math.PI / 4)" aria-label="向右旋转视角">↷</button>
      <button @click="zoom(1.25)" aria-label="放大">＋</button>
      <button @click="zoom(.8)" aria-label="缩小">−</button>
      <button @click="resetCamera">重置视角</button>
    </div>
  </div>
</template>

<style scoped>
.house-scene-wrap{position:relative;min-width:0;height:620px;background:#f2eee5;border-radius:14px;overflow:hidden}.house-scene{width:100%;height:100%;touch-action:none}.house-scene :deep(canvas){display:block;width:100%;height:100%}.scene-controls{position:absolute;bottom:14px;left:50%;transform:translateX(-50%);display:flex;gap:4px;padding:5px;border:1px solid #ddd5c6;border-radius:10px;background:#fffdf6ed;white-space:nowrap}.scene-controls button{min-width:36px;min-height:36px;border:0;background:transparent;border-radius:6px;color:#3b5245}.scene-controls button:hover{background:#e7eee4}.scene-failure{position:absolute;inset:30%;line-height:1.8}.compact{height:330px}@media(max-width:760px){.house-scene-wrap{height:440px}.compact{height:280px}}
</style>
