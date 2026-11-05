# 糖霜世界扩展实施清单

## ✅ 阶段一：文件部署（立即可做）

### 1. 替换强化版关卡
```bash
# 备份原文件
cp frontend/src/frost/data/levels/5-1.json frontend/src/frost/data/levels/5-1.json.backup

# 替换为强化版
cp frontend/src/frost/data/levels/5-1-enhanced.json frontend/src/frost/data/levels/5-1.json
```

### 2. 添加新关卡文件
将以下文件移至 `frontend/src/frost/data/levels/`：
- [x] `3-4.json` （悠的独立关卡）
- [x] `6-1.json` （十五个人的房间）
- [x] `6-2.json` （六十人的大群）
- [x] `6-3.json` （社群崩溃的那天）
- [x] `7-1.json` （唯一在线的人）
- [x] `7-2.json` （声音之外的距离）
- [x] `7-3.json` （最后在线 217 天前）
- [x] `8-1.json` （接替）
- [x] `8-2.json` （把世界交给你）
- [x] `8-3.json` （今晚你依然会登入吗）

### 3. 更新配套文件

#### A. `index.json`
需要添加：
- 第6、7、8章的章节信息
- 10个新关卡的元数据
- 更新 totals 统计

#### B. `characters.json`
新增角色条目：
```json
{
  "id": "Kai",
  "name": "凯",
  "vrcId": "Kai_VRC",
  "role": "7-1 需要陪伴的人",
  "age": 22,
  "occupation": "学生",
  "color": "#9DB8C4",
  "bg": "#F0F4F6",
  "shape": "pentagon",
  "personality": "疲惫、依赖虚拟世界、害怕安静",
  "loginHabit": "几乎一直在线（16小时+）",
  "motivation": "逃避现实的寂静",
  "fear": "摘下头显后的空虚",
  "catchphrase": "「再待一会就好。」",
  "secret": "现实里的房间已经好几个月没打扫了",
  "arc": ["无限逃避", "接受边界", "学会下线"],
  "insightFragmentId": "frag_7_1_10"
},
{
  "id": "Tao",
  "name": "小桃",
  "vrcId": "Tao_Peach",
  "role": "7-2 寻找身份认同的人",
  "age": 20,
  "occupation": "大学生",
  "color": "#FFAEC9",
  "bg": "#FFF0F5",
  "shape": "heart",
  "personality": "温柔、害怕被拒绝、用Avatar表达真实自我",
  "loginHabit": "晚上为主，喜欢社交World",
  "motivation": "在这里做真正想成为的自己",
  "fear": "坦白后被拉黑",
  "catchphrase": "「这里的我，才是真的我。」",
  "secret": "现实是男生，用女声+女性Avatar，这不是欺骗，是选择",
  "arc": ["隐藏真相", "鼓起勇气坦白", "被理解"],
  "insightFragmentId": "frag_7_2_10"
},
{
  "id": "Xing",
  "name": "星",
  "vrcId": "Xing_Star",
  "role": "7-3 已消失的朋友（只存在于回忆）",
  "age": null,
  "occupation": "未知",
  "color": "#D3D3D3",
  "bg": "#F8F8F8",
  "shape": "none",
  "personality": "温暖、可靠、但最后消失了",
  "loginHabit": "最后在线 217 天前",
  "motivation": "未知",
  "fear": "未知",
  "catchphrase": "「有点累了，先下了。」",
  "secret": "栞永远不会知道他为什么没有回来",
  "arc": ["—"],
  "insightFragmentId": null
}
```

#### C. `global-endings.json`
更新权重计算公式，加入新章节：
```json
{
  "variables": {
    "levelScore": {
      "source": "judgeChain(chain, level_8_3).score",
      "weight": 0.35,
      "normalize": "score / 100",
      "description": "终章（8-3）序列的归一化得分"
    },
    "goodCount": {
      "source": "save.endingsSeen 中 type === 'good' 的数量",
      "weight": 0.2,
      "normalize": "min(count, 15) / 15",
      "description": "全作达成的修复结局数（提升到15个上限）"
    },
    "trueCount": {
      "source": "save.endingsSeen 中 type === 'true' 的数量",
      "weight": 0.2,
      "normalize": "min(count, 18) / 18",
      "description": "全作达成的真相结局数（提升到18个上限）"
    },
    "bondMean": {
      "source": "mean(bond.Mio, bond.Shiori, bond.Rin, bond.Yu, bond.Kai, bond.Tao)",
      "weight": 0.25,
      "normalize": "(bondMean + 100) / 200",
      "description": "六名主要角色的羁绊值均值"
    }
  },
  "formula": "GlobalScore = 100 * ( 0.35*levelScore + 0.2*goodCount + 0.2*trueCount + 0.25*bondMean )",
  "overrides": [
    {
      "endingId": "global_give_away",
      "priority": 100,
      "condition": "level_8_2 达成 true 结局「随便逛逛」，且全局中「放手类」结局数 >= 5",
      "releaseEndingIds": ["3_2_true", "4_2_true", "7_3_true", "8_2_true"],
      "minReleaseCount": 4
    }
  ]
}
```

---

## ✅ 阶段二：前端适配

### 1. 更新常量文件 `frontend/src/constants.js`

#### 角色显示名
```javascript
export const ROLE_LABELS = {
  // ... 原有
  'Kai': '凯',
  'Tao': '小桃',
  'Xing': '星',
}

export const CHARACTER_COLORS = {
  // ... 原有
  'Kai': '#9DB8C4',
  'Tao': '#FFAEC9',
  'Xing': '#D3D3D3',
}
```

### 2. 章节标题（如果有章节选择界面）
```javascript
export const CHAPTER_THEMES = {
  6: { title: '社群', theme: '归属、透明与崩溃' },
  7: { title: '边缘', theme: '陪伴边界、身份与消失' },
  8: { title: '回声', theme: '传承、放手与选择' },
}
```

### 3. 内容警告（如果需要）
```javascript
export const CONTENT_WARNINGS = {
  '7-1': '本关涉及抑郁与过度依赖主题',
  '7-2': '本关涉及性别认同主题',
  '7-3': '本关涉及失去与消失主题',
}
```

---

## ✅ 阶段三：测试验证

### 1. 运行关卡校验器
```bash
cd frontend
node scripts/verify-frost.mjs
```

预期输出：
```
━━ 3-4 我是不是多余的 ━━
  数据自检通过｜排列 XXX｜混沌 XX (XX.X%)

━━ 6-1 十五个人的房间 ━━
  数据自检通过｜排列 XXX｜混沌 XX (XX.X%)

...

━━ 8-3 今晚你依然会登入吗 ━━
  数据自检通过｜排列 XXX｜混沌 XX (XX.X%)

全部 24 关校验通过。
```

### 2. 手动测试关键关卡

#### 优先测试列表：
1. **3-4**：悠的视角是否与3-1呼应
2. **5-1强化版**：红色碎片是否正常工作
3. **7-1**：边界设立的时机是否影响结局
4. **7-2**：接纳与怀疑的顺序逻辑
5. **8-3**：最终章的情感落点

### 3. 检查蝴蝶效应解锁
确认以下蝴蝶碎片能正常解锁：
- 3-4:A → frag_3_4_09
- 6-1:A → frag_6_1_10
- 7-1:A → frag_7_1_10
- 7-2:A → frag_7_2_10
- 8-1:A → frag_8_1_10
- 8-2:A → frag_8_2_10
- 8-3:A → frag_8_3_11

---

## ✅ 阶段四：美术与音效（可选）

### 1. 新角色头像/配色
- **凯**：疲惫感、灰蓝色调、简约Avatar
- **小桃**：粉色系、温柔、可爱风格
- **星**：灰度化、模糊处理（象征消失）

### 2. 章节BGM建议
- **第6章**：轻快但带点空洞感（社群的表面热闹）
- **第7章**：沉重、缓慢、留白较多（边缘主题）
- **第8章**：温暖、递进、回归主题曲变奏

### 3. 视觉元素
- 7-3关卡：好友列表界面的「最后在线 XXX 天前」特效
- 8-3关卡：登入界面的特写镜头

---

## ✅ 阶段五：文案润色（如时间允许）

### 需要二次打磨的文本：
1. **6-3 bittersweet结局**：「有些连接，只能存在于那个特定的时空」可以更诗意
2. **7-3 chaos结局**：提示文本可以更引导性
3. **8-2 bad结局**：「那些站过的人，再也找不到回去的路了」过于直白

### 建议改进方向：
- 用更多意象化表达
- 避免「学会了」这种教科书式总结
- 让玩家自己领悟，而不是直接告诉

---

## ✅ 阶段六：性能优化

### 1. 关卡懒加载
确认新增9关也使用动态import：
```javascript
// frontend/src/frost/composables/useFrostGame.js
const level = await import(`../data/levels/${levelId}.json`)
```

### 2. 存档兼容性
新增关卡后，确保旧存档能平滑迁移：
```javascript
// 如果旧存档没有6-8章的记录，自动初始化
if (!save.unlockedLevels.includes('6-1')) {
  // 检查是否已通关5-3，如果是，解锁6-1
}
```

---

## ✅ 阶段七：文档更新

### 1. 玩家可见文档
- [ ] 更新游戏介绍：「15关」→「24关」
- [ ] 更新预期游玩时长：「5-8小时」→「10-15小时」
- [ ] 添加内容警告说明

### 2. 开发文档
- [ ] 更新 `AGENTS.md` 中的糖霜世界部分
- [ ] 添加新角色到设计文档
- [ ] 更新关卡设计规范（如有）

---

## 🎯 快速部署命令集

```bash
# 1. 进入项目目录
cd /Users/hytabc/PythonProject/yorozuya

# 2. 备份原关卡
cp frontend/src/frost/data/levels/5-1.json frontend/src/frost/data/levels/5-1.json.backup

# 3. 部署所有新文件（假设已在正确位置）
# 手动将创建的10个JSON文件移至 frontend/src/frost/data/levels/

# 4. 运行校验
cd frontend
node scripts/verify-frost.mjs

# 5. 如果校验通过，启动开发服务器测试
npm run dev

# 6. 访问 /frost 路由，测试新关卡
```

---

## ⚠️ 注意事项

### 1. 内容分级
- 第7章包含成熟主题，考虑添加「建议16+」标注
- 7-1（抑郁）和7-3（消失）可能触发敏感玩家，提供跳过选项

### 2. 平衡性调整
- 新增9关后，全局结局的触发条件可能需要微调
- 建议通关数据收集后调整阈值

### 3. 本地化
- 如需支持其他语言，新增文本量约+60%
- 优先翻译：关卡标题、结局标题、核心对话

### 4. 存档版本
- 建议给存档添加版本号：`frostSaveVersion: 2`
- 旧版本存档遇到新关卡时，提示「新章节已解锁」

---

## 📊 上线检查清单

- [ ] 所有24关通过穷举校验
- [ ] 每个结局至少手动测试一次
- [ ] 所有蝴蝶碎片能正常解锁
- [ ] 全局结局触发条件正确
- [ ] 新角色信息显示正常
- [ ] 章节过渡流畅
- [ ] 没有文本溢出/显示错误
- [ ] 音效/BGM正常切换（如有）
- [ ] 移动端适配正常
- [ ] 存档读写正常
- [ ] 性能无明显下降

---

## 🚀 渐进式上线策略

### 方案A：一次性上线
- 优点：完整体验，玩家可以一口气通关
- 缺点：测试压力大，bug集中爆发

### 方案B：分章节上线
```
第一批：强化版5-1 + 3-4（补完第3章）
第二批：第6章（社群）
第三批：第7章（边缘）+ 内容警告
第四批：第8章（回声）+ 全局结局更新
```
- 优点：渐进测试，玩家保持期待
- 缺点：剧情割裂，第8章需要等待

### 推荐：方案A
理由：糖霜世界是单机体验，完整性 > 渐进式上线

---

## 📞 如遇问题

### 常见问题排查

#### Q1: 校验器报错「结局 XXX 不可达」
- 检查约束权重是否加起来 >= threshold
- 确认 anti 约束没有完全封死可达路径
- 尝试手动排列，找到可达组合

#### Q2: 蝴蝶碎片不解锁
- 检查 `requires` 条件是否正确
- 确认 `unlockedBy` 与 `endingType` 匹配
- 查看控制台是否有JS错误

#### Q3: 新角色信息不显示
- 确认 `characters.json` 格式正确
- 检查前端是否正确读取并渲染
- 清除浏览器缓存后重试

#### Q4: 存档损坏
- 提供存档修复工具（重置特定章节）
- 添加存档导出/导入功能
- 考虑云存档（如接入后端）

---

**最后**：所有新关卡JSON文件已创建完毕，位于你的工作目录。按照本清单逐步部署即可。祝上线顺利！🎉
