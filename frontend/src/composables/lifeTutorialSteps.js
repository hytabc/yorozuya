// EDITABLE XIAOBAI TUTORIAL TEMPLATE. Change title/text freely; keep stable ids.
// target: DOM selector; prepare: presentation-only view; action: safe target click.
// Tutorial intercepts target clicks: it never calls reward/travel/save/day handlers.
export const LIFE_TUTORIAL_VERSION = 1
export const lifeTutorialKey = userId => Number.isSafeInteger(Number(userId)) && Number(userId) > 0 ? `wsw:life:tutorial:v${LIFE_TUTORIAL_VERSION}:user:${Number(userId)}` : null
export const LIFE_TUTORIAL_STEPS = [
  { id:'welcome',title:'小白来带路',text:'欢迎来到虚拟人生！我是小白。这是一份可以随时修改文案的新手指引。跟着亮起来的位置走一遍吧，不会消耗进度。',target:'.life-header' },
  { id:'character',title:'你的角色',text:'这里是角色标签、心情、精力、社交和探索属性。上方是游戏天数；一天不是现实中的一天哦。',target:'.char-panel' },
  { id:'room',title:'世界与房间',text:'同一地图有不同房间。这里只会遇见同房间的人，人数包含你与模拟访客。',target:'.location-tag' },
  { id:'roster',title:'展开房间人物',text:'点击亮起的人数按钮展开头像。头像用于交谈，旁边的“资料”用于认识对方；没有人物时可以先探索其他房间。',target:'.population-toggle',action:'roster' },
  { id:'talk',title:'交谈的样子',text:'这是教学示意，不是真实聊天。你在左，对方在右；文字逐字出现，点击气泡可以显示全文。',target:'.tutorial-demo',prepare:'demo',action:'demo' },
  { id:'choices',title:'选择回应',text:'对话选项影响属性与好感。真正选择后会记录完整回复与手记；教学不会替你选择，也不会领取奖励。',target:'.tutorial-demo',prepare:'demo' },
  { id:'actions',title:'动作与每日奖励',text:'动作有摸摸头 +2、戳戳脸 +1、亲亲 +3。每位人物、每种动作每个游戏日首次奖励；亲亲需要好感达到30。换房间不能重领奖励。',target:'.tutorial-demo',prepare:'demo' },
  { id:'history',title:'独立对话历史',text:'点击卷轴可查看各人物历史，不同人物不会混在一起。这里不会新增任何对话。',target:'.history-icon-btn',action:'history' },
  { id:'worlds',title:'开始探索',text:'点击世界探索先看地图，再选择房间。不会直接传送到好友身边。',target:'[data-life-guide="worlds"]',action:'worlds' },
  { id:'rooms',title:'房间的加入条件',text:'可以加入有人、非私密且未满员的房间。不提供新建。此处只展示列表，指引不会替你加入或切换位置。',target:'.drawer-body',prepare:'rooms' },
  { id:'profile',title:'先查看人物资料',text:'场景里的“资料”会打开介绍、状态、所在房间以及好感进度。这里演示一位人物，不会改变当前交谈对象。',target:'.profile-body',prepare:'profile' },
  { id:'add-friend',title:'不是见面就成为好友',text:'必须真正回复或做动作至少一次，而且好感达到10，才能主动申请。只听开场白不算。满足条件后模拟人物接受；本教学不会帮你添加。',target:'.profile-affection',prepare:'profile' },
  { id:'friends',title:'好友与跟随',text:'好友列表只显示已添加的人。点头像查看详情，绿灯才可跟随，而且房间仍须有人、非私密且未满。空列表是正常的。',target:'.drawer-body',prepare:'friends' },
  { id:'diary',title:'人生手记',text:'这里保留你的互动记录，换房间和进入下一天不会清掉历史。',target:'.drawer-body',prepare:'diary' },
  { id:'saving',title:'确认存档同步',text:'有效操作后约0.7秒自动保存，也可手动存档。看到“已同步”再刷新最稳妥；失败或冲突会提示。存档按账号独立，这份指引不写入游戏进度。',target:'.save-status' },
  { id:'next-day',title:'开启新的一天',text:'“下一天”恢复精力，并重置当天对话与动作首次奖励资格，不删除历史。教学只介绍，不会推进天数。',target:'.life-footer' },
  { id:'finish',title:'准备好出发啦',text:'返回按钮会离开页面；设置目前尚未开放。以后可点“新手指引”重看。完成或跳过仅记录此账号在本浏览器看过指引，不影响服务器存档。',target:'.header-actions' },
]
export function spotlightRect(rect, width, height) {
  if (!rect || rect.width <= 0 || rect.height <= 0 || rect.bottom <= 0 || rect.top >= height || rect.right <= 0 || rect.left >= width) return null
  const left = Math.max(0, rect.left - 6), top = Math.max(0, rect.top - 6)
  return { left, top, width: Math.max(0, Math.min(width, rect.right + 6) - left), height: Math.max(0, Math.min(height, rect.bottom + 6) - top) }
}
