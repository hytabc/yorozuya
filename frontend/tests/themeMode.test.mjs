import test from 'node:test'
import assert from 'node:assert/strict'
import {
  MODE_SOURCES,
  NIGHT_END_HOUR,
  NIGHT_START_HOUR,
  isNightTime,
  isValidModeSource,
  nextModeChangeIn,
  resolveMode,
} from '../src/composables/themeMode.js'

// 固定本地时间，避免测试跟随运行时的时区/当前时刻漂移
function at(hour, minute = 0) {
  return new Date(2026, 8, 21, hour, minute, 0)
}

test('夜间区间是 21:00（含）到次日 06:00（不含）', () => {
  assert.equal(NIGHT_START_HOUR, 21)
  assert.equal(NIGHT_END_HOUR, 6)

  assert.equal(isNightTime(at(20, 59)), false, '20:59 还是日间')
  assert.equal(isNightTime(at(21, 0)), true, '21:00 整点进入夜间')
  assert.equal(isNightTime(at(23, 59)), true)
  assert.equal(isNightTime(at(0, 0)), true, '跨过午夜仍然是夜间')
  assert.equal(isNightTime(at(5, 59)), true)
  assert.equal(isNightTime(at(6, 0)), false, '06:00 整点回到日间')
  assert.equal(isNightTime(at(12, 0)), false)
})

test('一天 24 小时里只有 21-23 与 0-5 属于夜间', () => {
  const nightHours = []
  for (let hour = 0; hour < 24; hour += 1) {
    if (isNightTime(at(hour))) nightHours.push(hour)
  }
  assert.deepEqual(nightHours, [0, 1, 2, 3, 4, 5, 21, 22, 23])
})

test('auto 档按时间推导，system 档按系统偏好，day/night 档直接生效', () => {
  assert.equal(resolveMode('auto', { date: at(22) }), 'night')
  assert.equal(resolveMode('auto', { date: at(10) }), 'day')

  assert.equal(resolveMode('system', { systemPrefersDark: true }), 'night')
  assert.equal(resolveMode('system', { systemPrefersDark: false }), 'day')
  // 跟随系统时不看时间
  assert.equal(resolveMode('system', { date: at(22), systemPrefersDark: false }), 'day')

  // 手动固定的档位不受时间与系统影响
  assert.equal(resolveMode('day', { date: at(22), systemPrefersDark: true }), 'day')
  assert.equal(resolveMode('night', { date: at(10), systemPrefersDark: false }), 'night')
})

test('未知档位回落到按时间判定', () => {
  assert.equal(resolveMode('nonsense', { date: at(22) }), 'night')
  assert.equal(resolveMode(undefined, { date: at(10) }), 'day')
})

test('档位表覆盖四种来源，且只接受表内的值', () => {
  assert.deepEqual(MODE_SOURCES.map((item) => item.id), ['auto', 'system', 'day', 'night'])
  assert.equal(isValidModeSource('auto'), true)
  assert.equal(isValidModeSource('night'), true)
  assert.equal(isValidModeSource('dark'), false)
  assert.equal(isValidModeSource(null), false)
  assert.equal(isValidModeSource(''), false)
})

test('下一次昼夜边界：白天指向当天 21:00，夜间指向次日 06:00', () => {
  const minutes = (ms) => Math.round(ms / 60000)

  // 10:00 → 当天 21:00，还有 11 小时
  assert.equal(minutes(nextModeChangeIn(at(10, 0))), 11 * 60)
  // 20:59 → 还有 1 分钟
  assert.equal(minutes(nextModeChangeIn(at(20, 59))), 1)
  // 21:00 整点刚进夜间 → 次日 06:00，还有 9 小时
  assert.equal(minutes(nextModeChangeIn(at(21, 0))), 9 * 60)
  // 23:30 → 次日 06:00，还有 6.5 小时
  assert.equal(minutes(nextModeChangeIn(at(23, 30))), 6 * 60 + 30)
  // 05:59 → 当天 06:00，还有 1 分钟
  assert.equal(minutes(nextModeChangeIn(at(5, 59))), 1)
  // 06:00 → 当天 21:00，还有 15 小时
  assert.equal(minutes(nextModeChangeIn(at(6, 0))), 15 * 60)
})

test('下一次昼夜边界的落点始终在整点，且严格晚于当前时刻', () => {
  for (let hour = 0; hour < 24; hour += 1) {
    for (const minute of [0, 30, 59]) {
      const now = at(hour, minute)
      const target = new Date(now.getTime() + nextModeChangeIn(now))
      assert.ok(target.getTime() > now.getTime(), `${hour}:${minute} 应指向未来`)
      assert.equal(target.getMinutes(), 0)
      assert.equal(target.getSeconds(), 0)
      assert.ok(
        target.getHours() === NIGHT_START_HOUR || target.getHours() === NIGHT_END_HOUR,
        `${hour}:${minute} 的边界应是 21:00 或 06:00，实际 ${target.getHours()}:00`,
      )
      // 边界另一侧的明暗应当翻转
      const after = new Date(target.getTime() + 1000)
      assert.notEqual(isNightTime(after), isNightTime(now))
    }
  }
})
