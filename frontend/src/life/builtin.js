// 内置内容包登记处：import 本模块即完成全部内置 Pack 的注册。
// 后续新增的 Pack 在此追加一行注册即可；活动 Pack 由站长配置(阶段 4)。
import { registerLifePack } from './registry'
import { defaultLifePack } from './content/defaultPack'

registerLifePack(defaultLifePack)
