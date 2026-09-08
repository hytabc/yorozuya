// 站点活动内容包加载器（阶段 4b）。
// 游戏启动时经 API 拉取站长配置的活动 Pack 并注册为前端活动 Pack;
// 拉取失败(网络/权限/内容非法)时保留内置 Pack 兜底,游戏可继续。
import axios from 'axios'
import './builtin'
import {
  createLifePackFromContent, registerLifePack, setActiveLifePack, getActiveLifePack,
} from './registry'

export async function loadActiveLifePack() {
  const ownerToken = localStorage.getItem('wsw_token')
  const api = axios.create({
    baseURL: '/api', timeout: 15000,
    headers: { Authorization: `Bearer ${ownerToken}` },
  })
  try {
    const { data } = await api.get('/virtual-life/pack')
    if (localStorage.getItem('wsw_token') !== ownerToken) return getActiveLifePack()
    const pack = createLifePackFromContent({ id: data.id, version: data.version, content: data.content })
    registerLifePack(pack)
    setActiveLifePack(pack.id)
    return pack
  } catch {
    return getActiveLifePack()
  }
}
