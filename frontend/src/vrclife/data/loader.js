/**
 * 浏览器端数据加载（fetch）。
 * 不 import 任何 JSON 文件；数据通过 fetch 从 public/vrclife-data/ 载入。
 */

/**
 * @param {string} [base]
 * @returns {Promise<{events:object[], byId:object, vocab:object, endings:object[], endingsRaw:object, archetypes:object[]}>}
 */
export async function loadVrclifeData(base = '/vrclife-data') {
  const fetchJson = async (name) => {
    const url = `${base}/${name}`;
    let res;
    try {
      res = await fetch(url);
    } catch (e) {
      throw new Error(`加载 ${name} 失败: ${e && e.message ? e.message : e}`);
    }
    if (!res.ok) throw new Error(`加载 ${name} 失败: HTTP ${res.status}`);
    try {
      return await res.json();
    } catch (e) {
      throw new Error(`解析 ${name} 失败: ${e && e.message ? e.message : e}`);
    }
  };

  const [eventsIndex, vocab, endingsRaw, archetypesRaw] = await Promise.all([
    fetchJson('events.index.json'),
    fetchJson('vocab.json'),
    fetchJson('endings.json'),
    fetchJson('archetypes.json'),
  ]);

  const events = eventsIndex.events || [];
  const byId = eventsIndex.byId || {};

  return {
    events,
    byId,
    vocab,
    endings: endingsRaw.endings || [],
    endingsRaw,
    archetypes: archetypesRaw.archetypes || [],
  };
}