import test from 'node:test'
import assert from 'node:assert/strict'
import { createDwellTracker } from '../src/analyticsDwell.js'

function fakeClock(start = 0) {
  let value = start
  return {
    now: () => value,
    advance: (seconds) => { value += seconds * 1000 },
  }
}

test('entering a new page settles the previous one in whole seconds', () => {
  const clock = fakeClock()
  const tracker = createDwellTracker({ now: clock.now })

  assert.equal(tracker.enter('hall'), null)
  clock.advance(12)
  assert.deepEqual(tracker.enter('sugar'), { page: 'hall', seconds: 12 })
  clock.advance(3)
  assert.deepEqual(tracker.finish(), { page: 'sugar', seconds: 3 })
})

test('time spent hidden is not counted (pause flushes, resume keeps the page)', () => {
  const clock = fakeClock()
  const tracker = createDwellTracker({ now: clock.now })

  tracker.enter('maps')
  clock.advance(20)
  assert.deepEqual(tracker.pause(), { page: 'maps', seconds: 20 })
  // 后台待很久，恢复后不应把这段时间算进去。
  clock.advance(600)
  assert.equal(tracker.counting, false)
  tracker.resume()
  clock.advance(5)
  assert.deepEqual(tracker.finish(), { page: 'maps', seconds: 5 })
})

test('finish is idempotent so pagehide + beforeunload do not double count', () => {
  const clock = fakeClock()
  const tracker = createDwellTracker({ now: clock.now })

  tracker.enter('board')
  clock.advance(8)
  assert.deepEqual(tracker.finish(), { page: 'board', seconds: 8 })
  assert.equal(tracker.finish(), null)
  assert.equal(tracker.page, null)
})

test('sub-second visits and empty targets produce no record', () => {
  const clock = fakeClock()
  const tracker = createDwellTracker({ now: clock.now })

  tracker.enter('stories')
  clock.advance(0.4)
  assert.equal(tracker.finish(), null)
  // 无 analyticsKey 的页面（null）不启动计时。
  assert.equal(tracker.enter(null), null)
  clock.advance(30)
  assert.equal(tracker.finish(), null)
})

test('a long-lived tab is capped at maxSeconds per settlement', () => {
  const clock = fakeClock()
  const tracker = createDwellTracker({ now: clock.now, maxSeconds: 600 })

  tracker.enter('frost')
  clock.advance(5000)
  assert.deepEqual(tracker.finish(), { page: 'frost', seconds: 600 })
})

test('paused page is not re-counted when navigating away', () => {
  const clock = fakeClock()
  const tracker = createDwellTracker({ now: clock.now })

  tracker.enter('life')
  clock.advance(15)
  assert.deepEqual(tracker.pause(), { page: 'life', seconds: 15 })
  clock.advance(120)
  // 已暂停：切到新页面时不会再补发一次停留。
  assert.equal(tracker.enter('hall'), null)
})
