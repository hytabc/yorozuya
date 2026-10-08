<script setup>
import { nextTick, ref, watch } from 'vue'
const props=defineProps({ownerId:Number})
const dialog=ref()
const key=()=>`wsw-house-help-v2-${props.ownerId}`
function open(){dialog.value?.showModal()}
function close(){dialog.value?.close();if(props.ownerId)try{localStorage.setItem(key(),'seen')}catch{/* Help remains available in memory-only browsers. */}}
watch(()=>props.ownerId,async(id)=>{if(!id)return;await nextTick();try{if(localStorage.getItem(key()))return}catch{/* Show once for this mount. */}open()},{immediate:true})
</script>
<template>
  <button class="button secondary small" @click="open">操作帮助</button>
  <dialog ref="dialog" class="house-help" aria-labelledby="house-help-title" @cancel.prevent="close" @click="($event.target===dialog) && close()">
    <h2 id="house-help-title">布置小屋操作教程</h2>
    <ol>
      <li><strong>旋转视角：</strong>切换到“视角”后左键或单指拖动；也可使用画布下方的左右旋转按钮。</li>
      <li><strong>平移与缩放：</strong>右键拖动或双指平移；滚轮、双指捏合或“＋ / −”缩放。“重置视角”回到初始位置。</li>
      <li><strong>选择与摆放：</strong>点击家具库中的模型，再点击房间放置；点击已摆放的家具可选择它。</li>
      <li><strong>三轴移动：</strong>切换“移动”，拖动红色 X、绿色 Y 或蓝色 Z 箭头。X/Y 在地面，Z 为高度。也可拖家具在地面移动，或用轴向加减按钮和属性数值精调。无效位置标红，松开恢复；Esc 可取消拖动。</li>
      <li><strong>旋转与缩放：</strong>属性面板可每次旋转90°，并选择50%、100%或200%的大小；重叠或越界操作会被阻止。</li>
      <li><strong>家具工坊：</strong>选材质与颜色组合后逐块拼搭，用涂刷替换、吸管取样、切片编辑内部；支持撤销与重做。可添加最多64种组合，制作最多8192块积木。</li>
      <li><strong>保存与发布：</strong>房屋自动保存为私人草稿，家具点击“保存家具”存到账号。开放参观或发布家具后，继续编辑不会改变公开版本；点击“更新展示 / 更新分享”才会发布新版本。</li>
      <li><strong>收藏与参观：</strong>收藏喜欢的家具，或复制到自己的家具库后改造；“参观”中可进入房主开放的小屋，只能浏览视角。</li>
    </ol>
    <button class="button" autofocus @click="close">知道了，开始布置</button>
  </dialog>
</template>
<style scoped>
.house-help{width:min(640px,calc(100% - 32px));max-height:85vh;overflow:auto;border:1px solid var(--line);border-radius:16px;padding:24px;background:var(--paper);color:var(--ink)}.house-help::backdrop{background:#17251d88}.house-help h2{font-size:21px;margin:0 0 18px}.house-help ol{padding-left:22px;line-height:1.9;font-size:13px}.house-help li{margin-bottom:12px}.house-help>button{margin-top:8px}
</style>
