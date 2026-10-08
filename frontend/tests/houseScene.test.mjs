import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import * as THREE from 'three'
import { normalizedVoxels, MATERIALS } from '../src/house/engine.js'

// Exercise real Three.js geometry, projection and ray picking without a GPU.
// Only the renderer, DOM surface and Vue lifecycle are replaced.
function mountScene(overrides={}) {
  const events=[],captures=new Set(),frames=new Map(),unmount=[],mounted=[]
  const canvas={getBoundingClientRect:()=>({left:0,top:0,width:900,height:620}),addEventListener(){},
    setPointerCapture:(id)=>captures.add(id),hasPointerCapture:(id)=>captures.has(id),releasePointerCapture:(id)=>captures.delete(id)}
  const host={clientWidth:900,clientHeight:620,appendChild(){}}
  let frameId=0,firstRef=true
  const previous=new Map()
  const globals={requestAnimationFrame:(fn)=>{frames.set(++frameId,fn);return frameId},cancelAnimationFrame:(id)=>frames.delete(id),
    devicePixelRatio:1,ResizeObserver:class {observe(){}disconnect(){}},window:{addEventListener(){},removeEventListener(){}}}
  for(const [key,value] of Object.entries(globals)){previous.set(key,{exists:Object.hasOwn(globalThis,key),value:globalThis[key]});globalThis[key]=value}
  class Renderer {
    domElement=canvas
    setPixelRatio(){}setClearColor(){}setSize(){}dispose(){}
    render(scene,camera){scene.updateMatrixWorld(true);camera.updateMatrixWorld(true)}
  }
  class Controls {
    target=new THREE.Vector3();enabled=true
    constructor(camera){this.camera=camera}
    update(){this.camera.lookAt(this.target);this.camera.updateMatrixWorld(true)}
    addEventListener(){}dispose(){}
  }
  const data={gridSize:16,mount:'floor',palette:[{key:'wood',label:'木材',color:'#b58b63',editable:true}],voxels:[[0,0,0,0],[1,0,0,0]]}
  const placement={id:'chair',versionId:'v1',position:{x:100,y:100,z:10},rotation:0,paletteOverrides:{}}
  const props={assets:{v1:{data}},room:{floor:{color:'#eeeeee'},wall:{color:'#ffffff'},placements:[placement]},
    selected:'chair',tool:'move',textureUrls:{},slice:-1,sliceAxis:2,readonly:false,...overrides}
  const source=fs.readFileSync(new URL('../src/house/VoxelScene.vue',import.meta.url),'utf8').split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm,'')
  const make=new Function('THREE','OrbitControls','normalizedVoxels','MATERIALS','onMounted','onBeforeUnmount','ref','watch','defineProps','defineEmits','defineExpose',
    `${source};return {pointerDown,pointerMove,pointerUp,cancelInteraction,keyDown,nudge,rebuild,get camera(){return camera},get controls(){return controls},get handles(){return handles},get meshes(){return meshes},get failed(){return failed.value}}`)
  const scene=make({...THREE,WebGLRenderer:Renderer},Controls,normalizedVoxels,MATERIALS,
    (fn)=>mounted.push(fn),(fn)=>unmount.push(fn),(value)=>({value:value===undefined && firstRef?(firstRef=false,host):value}),()=>{},()=>props,
    ()=>((type,value)=>events.push({type,value})),()=>{})
  for(const fn of mounted)fn()
  function flush(){while(frames.size){const pending=[...frames.values()];frames.clear();for(const fn of pending)fn()}}
  flush();assert.equal(scene.failed,'')
  function event(point,id=1){const p=point.clone().project(scene.camera);return {clientX:(p.x+1)*450,clientY:(1-p.y)*310,pointerId:id,pointerType:id===7?'touch':'mouse',button:0}}
  function close(){for(const fn of unmount)fn();for(const [key,old] of previous){if(old.exists)globalThis[key]=old.value;else delete globalThis[key]}}
  return {scene,props,events,event,close,captures,flush}
}

test('X/Y/Z箭头按屏幕投影移动对应逻辑轴，鼠标与触控暂停相机后恢复',()=>{
  for(const axis of ['x','y','z']) {
    const fixture=mountScene()
    try {
      const {scene,event,events,captures}=fixture,handle=scene.handles.find((h)=>h.userData.axis===axis)
      const direction=new THREE.Vector3(axis==='x'?1:0,axis==='z'?1:0,axis==='y'?1:0)
      const start=handle.userData.origin.clone().addScaledVector(direction,23)
      const down=event(start,axis==='z'?7:1)
      scene.pointerDown(down)
      assert.equal(scene.controls.enabled,false);assert(captures.has(down.pointerId))
      scene.pointerMove(event(start.clone().addScaledVector(direction,5),down.pointerId))
      const drag=events.find((e)=>e.type==='drag')
      assert(drag,`轴 ${axis} 没有产生拖动`)
      assert.deepEqual(drag.value.position,{x:100,y:100,z:10,[axis]:({x:100,y:100,z:10})[axis]+5})
      scene.pointerUp(event(start.clone().addScaledVector(direction,5),down.pointerId))
      assert.equal(events.filter((e)=>e.type==='drag-end').length,1)
      assert.equal(scene.controls.enabled,true);assert.equal(captures.size,0)
    }finally{fixture.close()}
  }
})

test('Esc、pointercancel和失焦取消拖动，不提交位置',()=>{
  for(const cancel of ['escape','pointercancel','blur']) {
    const f=mountScene()
    try {
      const handle=f.scene.handles.find((h)=>h.userData.axis==='z'),direction=new THREE.Vector3(0,1,0)
      const start=handle.userData.origin.clone().addScaledVector(direction,23),down=f.event(start)
      f.scene.pointerDown(down);f.scene.pointerMove(f.event(start.clone().addScaledVector(direction,4)))
      if(cancel==='escape')f.scene.keyDown({key:'Escape'})
      else f.scene.cancelInteraction(cancel==='pointercancel'?down:undefined)
      f.scene.pointerUp(down)
      assert.equal(f.events.filter((e)=>e.type==='drag-cancel').length,1)
      assert.equal(f.events.filter((e)=>e.type==='drag-end').length,0)
      assert.equal(f.scene.controls.enabled,true);assert.equal(f.captures.size,0)
      assert.deepEqual(f.props.room.placements[0].position,{x:100,y:100,z:10})
    }finally{f.close()}
  }
})

test('参观模式没有三轴编辑控件，也不发送位置变化',()=>{
  const f=mountScene({readonly:true})
  try {
    assert.equal(f.scene.handles.length,0);assert.equal(f.scene.controls.enableRotate,true)
    const e=f.event(new THREE.Vector3(101,10.5,100.5))
    f.scene.pointerDown(e);f.scene.pointerMove({...e,clientX:e.clientX+40});f.scene.pointerUp(e);f.scene.nudge('z',1)
    assert.equal(f.events.length,0)
  }finally{f.close()}
})

test('失焦未收到旧pointerup时仍可开始新的触控拖动',()=>{
  const f=mountScene()
  try {
    const handle=f.scene.handles.find((h)=>h.userData.axis==='z'),start=handle.userData.origin.clone().add(new THREE.Vector3(0,23,0))
    f.scene.pointerDown(f.event(start,1));f.scene.cancelInteraction()
    f.scene.pointerDown(f.event(start,7));assert.equal(f.scene.controls.enabled,false);assert(f.captures.has(7))
    f.scene.pointerMove(f.event(start.clone().add(new THREE.Vector3(0,3,0)),7))
    assert.equal(f.events.find((e)=>e.type==='drag').value.position.z,13)
    f.scene.pointerUp(f.event(start,7));assert.equal(f.scene.controls.enabled,true)
  }finally{f.close()}
})

test('三维预览按八种材质批量渲染颜色并保留玻璃和发光属性',()=>{
  const data={gridSize:16,mount:'floor',palette:MATERIALS.map((m,i)=>({key:`m${i}`,label:m.label,material:m.id,color:`#${(i+1).toString(16).padStart(6,'0')}`,editable:true})),voxels:MATERIALS.map((_,i)=>[i,0,0,i])}
  const before=JSON.stringify(data),f=mountScene({data,room:null,selected:null})
  try {
    assert.equal(f.scene.meshes.length,8)
    assert.equal(f.scene.meshes.find((m)=>m.material.transparent).material.opacity,.45)
    assert.equal(f.scene.meshes.find((m)=>m.material.emissiveIntensity).material.emissiveIntensity,.8)
    for(const mesh of f.scene.meshes){assert(mesh.isInstancedMesh);assert(mesh.instanceColor)}
    assert.equal(JSON.stringify(data),before)
  }finally{f.close()}
})

test('8192块家具只渲染可见表面，实例缩放与逻辑占用一致',()=>{
  const data={gridSize:32,mount:'floor',palette:[{key:'wood',label:'木材',material:'wood',color:'#b58b63',editable:true}],
    voxels:Array.from({length:8192},(_,i)=>[i%32,Math.floor(i/32)%32,Math.floor(i/1024),0])}
  const f=mountScene({assets:{v1:{data}},room:{floor:{color:'#eeeeee'},wall:{color:'#ffffff'},placements:[{id:'chair',versionId:'v1',position:{x:100,y:100,z:10},rotation:0,scale:.5,paletteOverrides:{}}]}})
  try {
    assert.equal(f.scene.meshes.reduce((sum,m)=>sum+m.count,0),2792)
    const matrix=new THREE.Matrix4(),position=new THREE.Vector3(),rotation=new THREE.Quaternion(),scale=new THREE.Vector3()
    f.scene.meshes[0].getMatrixAt(0,matrix);matrix.decompose(position,rotation,scale)
    assert.deepEqual(scale.toArray(),[.5,.5,.5])
  }finally{f.close()}
})
