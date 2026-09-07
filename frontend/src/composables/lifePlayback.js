// Presentation only: never mutates saves, rewards, or conversation history.
export function createLifePlayback(emit, { schedule = setTimeout, cancel = clearTimeout, reducedMotion = () => false } = {}) {
  let timer, epoch = 0, queue = [], index = 0, chars = [], count = 0
  let state = { from: 'npc', text: '', typing: false, playing: false }
  const publish = patch => { state = { ...state, ...patch }; emit({ ...state }) }
  function stop() {
    epoch++; cancel(timer); queue = []
    publish({ text: '', typing: false, playing: false })
  }
  function later(fn, delay) {
    const own = epoch
    timer = schedule(() => { if (epoch === own) fn() }, delay)
  }
  function finishLine() {
    cancel(timer)
    count = chars.length
    publish({ text: chars.join(''), typing: false })
    if (index + 1 < queue.length) later(() => { index++; startLine() }, 900)
    else publish({ playing: false })
  }
  function tick() {
    if (reducedMotion()) return finishLine()
    count++
    publish({ text: chars.slice(0, count).join('') })
    if (count >= chars.length) finishLine()
    else later(tick, 38)
  }
  function startLine() {
    chars = Array.from(queue[index].text)
    count = 0
    publish({ from: queue[index].from, text: '', typing: true, playing: true })
    if (!chars.length || reducedMotion()) finishLine()
    else later(tick, 38)
  }
  function play(lines) {
    stop()
    queue = lines.map(line => ({ from: line.from, text: line.text }))
    index = 0
    if (queue.length) startLine()
  }
  function complete() {
    if (state.typing) finishLine()
    else if (state.playing && index + 1 < queue.length) {
      cancel(timer); index++; startLine()
    }
  }
  return { play, stop, complete }
}
