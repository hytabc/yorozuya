<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { normalizedVoxels, MATERIALS } from './engine'

const props = defineProps({ room: Object, assets: { type: Object, default: () => ({}) }, selected: String,
  data: Object, invalidId: String, tool: { type: String, default: 'camera' }, sliceAxis: { type: Number, default: 2 }, slice: { type: Number, default: -1 },
  textureUrls: { type: Object, default: () => ({}) }, readonly: Boolean, compact: Boolean })
const emit = defineEmits(['pick', 'voxel', 'stroke-start', 'stroke-end', 'drag', 'drag-end', 'drag-cancel', 'error'])
const host = ref(), failed = ref('')
let renderer, scene, camera, controls, observer, frame, disposed = false, content, floor, down, dragging, stroking = false, axisDrag, floorDrag
const ray = new THREE.Raycaster(), pointer = new THREE.Vector2(), geometry = new THREE.BoxGeometry(1, 1, 1)
const materials = new Set(), textures = new Map(), pickables = [], meshes = [], cube = new THREE.Object3D()
const handles = [], pointers = new Set()
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
function addVoxels(data, position, rotation, ident, overrides = {}, editor = false, scale = 1) {
  const points = editor ? data.voxels : normalizedVoxels(data, rotation, scale)
  const cells = new Set(points.map((p) => p.slice(0, 3).join(',')))
  const visible = points.filter(([x, y, z]) => {
    if (editor && props.slice >= 0 && [x, y, z][props.sliceAxis] > props.slice) return false
    return [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]].some(([a, b, c]) => !cells.has([x + a*scale, y + b*scale, z + c*scale].join(',')) || editor && props.slice >= 0 && [x + a, y + b, z + c][props.sliceAxis] > props.slice)
  })
  const palette = data.palette.map((s) => new THREE.Color(ident === props.invalidId ? '#cf5360' : s.editable && overrides[s.key] || s.color))
  const groups = new Map()
  for (const p of visible) {
    const slot=data.palette[p[3]], key=slot.material==='emissive'?`emissive:${palette[p[3]].getHexString()}`:slot.material || 'legacy'
    if(!groups.has(key))groups.set(key,{slot,points:[]})
    groups.get(key).points.push(p)
  }
  for (const {slot,points:group} of groups.values()) {
    const profile=MATERIALS.find((m)=>m.id===slot.material)
    const m=profile?new THREE.MeshStandardMaterial({color:'#ffffff',roughness:profile.roughness,metalness:profile.metalness || 0,
      transparent:profile.transparent || false,opacity:profile.opacity ?? 1,depthWrite:profile.depthWrite ?? true,
      emissive:slot.material==='emissive'?palette[data.palette.indexOf(slot)]:0,emissiveIntensity:profile.emissiveIntensity || 0}):material({color:'#ffffff'})
    materials.add(m)
    for (let offset = 0; offset < group.length; offset += 16384) {
    const batch = group.slice(offset, offset + 16384)
    const mesh = new THREE.InstancedMesh(geometry, m, batch.length)
    batch.forEach(([x, y, z, c], i) => {
      cube.scale.setScalar(scale);cube.position.set(x + scale/2 + position.x, z + scale/2 + position.z, y + scale/2 + position.y); cube.updateMatrix()
      mesh.setMatrixAt(i, cube.matrix); mesh.setColorAt(i, palette[c] || new THREE.Color('#cbbba5'))
    })
    mesh.instanceMatrix.needsUpdate = true; if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
    mesh.computeBoundingSphere(); mesh.computeBoundingBox(); mesh.userData = { id: ident, points: batch, position }
    content.add(mesh); meshes.push(mesh); pickables.push(mesh)
    }
  }
  if (ident && props.selected === ident && points.length) {
    const box = new THREE.Box3()
    for (const [x, y, z] of points) { box.expandByPoint(mapping([x + position.x, y + position.y, z + position.z])); box.expandByPoint(mapping([x + scale + position.x, y + scale + position.y, z + scale + position.z])) }
    const helper = new THREE.Box3Helper(box, '#358462'); content.add(helper)
    if(!props.readonly && props.tool==='move') {
      const center=box.getCenter(new THREE.Vector3()),length=26/camera.zoom
      for(const [axis,direction,color] of [['x',new THREE.Vector3(1,0,0),'#c94e4e'],['y',new THREE.Vector3(0,0,1),'#4f9370'],['z',new THREE.Vector3(0,1,0),'#4c78c3']]) {
        const arrow=new THREE.ArrowHelper(direction,center,length,color,8/camera.zoom,5/camera.zoom)
        arrow.userData={axis,id:ident,origin:center.clone(),position:{...position}}
        arrow.traverse((o)=>{o.renderOrder=10;if(o.material){o.material.depthTest=false;o.material.depthWrite=false}})
        content.add(arrow);handles.push(arrow)
      }
    }
  }
}
function rebuild() {
  if (!scene || disposed) return
  if (content) {
    scene.remove(content)
    content.traverse((o) => { if (o.geometry && o.geometry !== geometry) o.geometry.dispose(); if (o.material) (Array.isArray(o.material)?o.material:[o.material]).forEach((m)=>m.dispose()); if (o.isInstancedMesh) o.dispose() })
  }
  materials.forEach((m) => m.dispose()); materials.clear(); meshes.length = pickables.length = handles.length = 0
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
      if (asset) addVoxels(asset.data, p.position, p.rotation, p.id, p.paletteOverrides, false, p.scale ?? 1)
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
  pointers.add(event.pointerId)
  if(pointers.size>1){cancelInteraction();return}
  if (event.button !== 0 || props.readonly) return
  down = { x: event.clientX, y: event.clientY, id: event.pointerId }
  if (props.data && props.tool !== 'camera') {
    controls.enabled = false; stroking = true; lastVoxel = ''; emit('stroke-start'); paint(event)
    renderer.domElement.setPointerCapture(event.pointerId)
  } else if (props.room && props.tool === 'move') {
    cast(event);ray.params.Line.threshold=3/camera.zoom
    let handle=ray.intersectObjects(handles,true)[0]?.object
    while(handle && !handle.userData.axis)handle=handle.parent
    if(handle?.userData.axis){
      const {axis,id,origin,position}=handle.userData
      const rect=renderer.domElement.getBoundingClientRect(),direction=mapping([axis==='x'?1:0,axis==='y'?1:0,axis==='z'?1:0])
      const a=origin.clone().project(camera),b=origin.clone().addScaledVector(direction,20).project(camera)
      axisDrag={axis,position,id,pointerId:event.pointerId,x:event.clientX,y:event.clientY,dx:(b.x-a.x)*rect.width/2,dy:-(b.y-a.y)*rect.height/2}
      controls.enabled=false;renderer.domElement.setPointerCapture(event.pointerId);return
    }
    const hit = cast(event)
    if (hit?.object.userData.id) {
      dragging = hit.object.userData.id; controls.enabled = false
      const placement=props.room.placements.find((p)=>p.id===dragging)
      floorDrag={position:{...placement.position},x:hit.point.x,y:hit.point.z,height:hit.point.y}
      emit('pick', { id: dragging }); renderer.domElement.setPointerCapture(event.pointerId)
    }
  }
}
function pointerMove(event) {
  if(down && event.pointerId!==down.id)return
  if (stroking) paint(event)
  if(axisDrag){
    const a=axisDrag,norm=a.dx*a.dx+a.dy*a.dy
    if(norm>1){const delta=Math.round(((event.clientX-a.x)*a.dx+(event.clientY-a.y)*a.dy)/norm*20);emit('drag',{id:a.id,position:{...a.position,[a.axis]:a.position[a.axis]+delta}})}
    return
  }
  if (dragging) {
    cast(event)
    const p = ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), -floorDrag.height), new THREE.Vector3())
    if (p) emit('drag', { id: dragging, position:{...floorDrag.position,x:Math.round(floorDrag.position.x+p.x-floorDrag.x),y:Math.round(floorDrag.position.y+p.z-floorDrag.y)} })
  }
}
function pointerUp(event) {
  pointers.delete(event.pointerId)
  if(down && event.pointerId!==down.id)return
  if (stroking) { stroking = false; emit('stroke-end') }
  else if (dragging || axisDrag) { emit('drag-end'); dragging = null;axisDrag=null;floorDrag=null }
  else if (down && Math.hypot(event.clientX - down.x, event.clientY - down.y) < 7 && props.room) {
    const hit = cast(event)
    if (hit) emit('pick', { id: hit.object.userData.id, x: hit.point.x, y: hit.point.z, z: Math.max(0, Math.ceil(hit.point.y)) })
  }
  if(renderer.domElement.hasPointerCapture(event.pointerId))renderer.domElement.releasePointerCapture(event.pointerId)
  down = null; if (controls) {controls.enabled=true;controls.enableRotate = props.readonly || props.tool === 'camera'}
}
function cancelInteraction(event) {
  pointers.clear()
  if(dragging || axisDrag)emit('drag-cancel')
  if(stroking)emit('stroke-end')
  if(down && renderer?.domElement.hasPointerCapture(down.id))renderer.domElement.releasePointerCapture(down.id)
  down=null;dragging=null;axisDrag=null;floorDrag=null;stroking=false
  if(controls){controls.enabled=true;controls.enableRotate=props.readonly || props.tool==='camera'}
}
function keyDown(event){if(event.key==='Escape')cancelInteraction()}
function nudge(axis,delta){
  const p=props.room?.placements.find((p)=>p.id===props.selected)
  if(!p || props.readonly)return
  emit('drag',{id:p.id,position:{...p.position,[axis]:p.position[axis]+delta}});emit('drag-end')
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
watch(() => [props.tool,props.readonly], () => { cancelInteraction();if (controls) controls.enableRotate = props.readonly || props.tool === 'camera' })
onMounted(() => {
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false })
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5)); renderer.setClearColor('#f2eee5'); renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1
    scene = new THREE.Scene(); scene.add(new THREE.HemisphereLight('#fff7e5', '#8d9b83', 1.5))
    const sun = new THREE.DirectionalLight('#fff3dc', 2); sun.position.set(-100, 300, -100); scene.add(sun)
    camera = new THREE.OrthographicCamera(-200, 200, 200, -200, .1, 3000)
    const el = renderer.domElement
    // Capture edit gestures before OrbitControls sees them, including touch.
    el.addEventListener('pointerdown',pointerDown,{capture:true})
    controls = new OrbitControls(camera, el); controls.enableDamping = false; controls.enableRotate = props.readonly || props.tool === 'camera'
    controls.minPolarAngle = .3; controls.maxPolarAngle = Math.PI / 2 - .08; controls.minZoom = .25; controls.maxZoom = 10
    controls.addEventListener('change', draw); host.value.appendChild(renderer.domElement)
    el.addEventListener('pointermove', pointerMove); el.addEventListener('pointerup', pointerUp); el.addEventListener('pointercancel', cancelInteraction)
    window.addEventListener('keydown',keyDown);window.addEventListener('blur',cancelInteraction)
    el.addEventListener('webglcontextlost', (e) => { e.preventDefault(); failed.value = '三维画布已暂停，请刷新页面恢复；草稿仍保留。' })
    observer = new ResizeObserver(resize); observer.observe(host.value); resize(); resetCamera(); rebuild()
  } catch { failed.value = '此浏览器无法启动 WebGL。仍可浏览家具信息、留言与导出已有草稿。'; emit('error', failed.value) }
})
onBeforeUnmount(() => {
  cancelInteraction();window.removeEventListener('keydown',keyDown);window.removeEventListener('blur',cancelInteraction)
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
    <div v-if="!readonly && selected && tool==='move'" class="axis-controls" aria-label="三轴移动控件">
      <span>沿箭头拖动 · Esc 取消</span><div v-for="axis in ['x','y','z']" :key="axis"><button :aria-label="`${axis.toUpperCase()}轴减一格`" @click="nudge(axis,-1)">−</button><strong>{{axis.toUpperCase()}}</strong><button :aria-label="`${axis.toUpperCase()}轴加一格`" @click="nudge(axis,1)">＋</button></div>
    </div>
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

<style scoped>
.axis-controls{position:absolute;top:12px;left:12px;background:#fffdf6ed;border:1px solid #ddd5c6;border-radius:8px;padding:8px;display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:11px;color:#3b5245}.axis-controls>div{display:flex;align-items:center;gap:5px}.axis-controls button{min-width:32px;min-height:34px;background:transparent;border:1px solid #ddd5c6;border-radius:5px;color:inherit}.axis-controls>span{width:100%}
</style>
