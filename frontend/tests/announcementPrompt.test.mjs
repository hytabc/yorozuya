import test from 'node:test'
import assert from 'node:assert/strict'
import { announcementSeenKey, markAnnouncementsSeen, unseenAnnouncements } from '../src/composables/announcementPrompt.js'

function memoryStorage(initial = {}) {
  const values = new Map(Object.entries(initial))
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  }
}

const announcements = [
  { id: 1, updated_at: '2026-09-08T10:00:00', created_at: '2026-09-08T09:00:00' },
  { id: 2, updated_at: '2026-09-08T11:00:00', created_at: '2026-09-08T11:00:00' },
]

test('guests see every active announcement on every visit', () => {
  const storage = memoryStorage()
  assert.deepEqual(unseenAnnouncements(announcements, null, storage), announcements)
  assert.equal(markAnnouncementsSeen(announcements, null, storage), false)
  assert.deepEqual(unseenAnnouncements(announcements, null, storage), announcements)
})

test('seen announcement versions are isolated by account and update independently', () => {
  const storage = memoryStorage()
  assert.equal(announcementSeenKey(12), 'wsw_seen_announcements_12')
  assert.deepEqual(unseenAnnouncements(announcements, 12, storage), announcements)
  assert.equal(markAnnouncementsSeen(announcements, 12, storage), true)
  assert.deepEqual(unseenAnnouncements(announcements, 12, storage), [])
  assert.deepEqual(unseenAnnouncements(announcements, 13, storage), announcements)

  const updated = announcements.map((item) => item.id === 2
    ? { ...item, updated_at: '2026-09-08T12:00:00' }
    : item)
  assert.deepEqual(unseenAnnouncements(updated, 12, storage), [updated[1]])
})

test('invalid or unavailable stored state defaults to showing announcements', () => {
  const invalidStorage = memoryStorage({ [announcementSeenKey(7)]: '{invalid' })
  assert.deepEqual(unseenAnnouncements(announcements, 7, invalidStorage), announcements)
  assert.equal(announcementSeenKey('token-value'), null)
  assert.deepEqual(unseenAnnouncements([], 7, invalidStorage), [])
})
