# 房屋预置素材

首版包含 24 类、120 款体素家具，30 款墙地面纹理及六套配色。五个示例布置覆盖客厅、卧室、书房、厨房和卫浴。

## 来源与许可

所有入库的家具体素、缩略图及纹理均由本项目的 `backend/scripts/build_house_assets.py` 原创生成，不包含游戏拆包素材、外站图片或第三方编辑器源代码。

| 来源 | 用途 | 许可记录 |
| --- | --- | --- |
| 本项目程序化造型与纹理 | 实际发布的全部预置素材 | 本项目原创；源文件及生成脚本随仓库维护 |
| [Kenney Furniture Kit](https://kenney.nl/assets/furniture-kit) | 低多边形家具比例与分类参考 | 官方页面标注 CC0，140 个素材；本版未直接导入模型 |
| [nimadez/voxel-builder](https://github.com/nimadez/voxel-builder) | 网格绘制、色组及体素编辑的功能参考 | GPL-3.0；本版未复制或嵌入其代码 |
| Three.js | 渲染引擎与 OrbitControls | MIT，随 npm 依赖保留其 LICENSE |

后续引入外部素材时，应在本表补充具体文件、来源 URL、许可文件及变更说明。素材应在构建时本地化，禁止依赖运行时外站热链。

## 重建

从仓库根目录运行：

```sh
backend/.venv/bin/python backend/scripts/build_house_assets.py
```

生成位置：

- `backend/app/house_catalog.json`：体素数据、材料部位、风格、配色和示例布局。
- `frontend/public/house/thumbnails/`：120 张相同等距视角的 PNG 家具缩略图。
- `frontend/public/house/textures/`：30 张 128×128 PNG 纹理。

每件家具是一套独立几何结构，换色不算新款。生成后的数据由测试校验坐标、色板、几何唯一性及缩略图存在性。

初始化只补充缺失的官方家具，不覆盖数据库中既有版本或审核状态。未来更新官方模型时应分配新的不可变版本，并保留旧房间引用的版本。

## 配色约定

色组使用 `wood/fabric/metal/accent/ceramic/screen/leaf/glass` 等材质语义。默认提供奶油原木、北欧鼠尾草、暖灰现代、胡桃复古、雾蓝海盐、低饱和莓粉。

屏幕、玻璃等固定细节不参与一键改色。其他部位支持单独调整；房屋仅存当前实例的 `paletteOverrides`，不回写公共模板。
