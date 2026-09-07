import test from 'node:test'
import assert from 'node:assert/strict'
import { LIFE_TUTORIAL_STEPS, lifeTutorialKey, spotlightRect } from '../src/composables/lifeTutorialSteps.js'

test('tutorial covers modules with stable editable ids and safe actions only', () => {
  const ids = LIFE_TUTORIAL_STEPS.map(s => s.id)
  assert.equal(new Set(ids).size, ids.length)
  for (const id of ['character','room','roster','talk','choices','actions','history','worlds','rooms','profile','add-friend','friends','diary','saving','next-day','finish']) assert.ok(ids.includes(id))
  for (const step of LIFE_TUTORIAL_STEPS) { assert.ok(step.text && step.target); if (step.action) assert.ok(['roster','demo','history','worlds'].includes(step.action)) }
})
test('completion keys separated by account, reject missing identity', () => {
  assert.notEqual(lifeTutorialKey(1),lifeTutorialKey(2))
  assert.equal(lifeTutorialKey('1'),lifeTutorialKey(1))
  for (const id of [null,undefined,0,'token-secret','',-1]) assert.equal(lifeTutorialKey(id),null)
})
test('spotlight clamps edges and rejects hidden/offscreen targets', () => {
  assert.deepEqual(spotlightRect({left:-10,top:10,right:30,bottom:50,width:40,height:40},100,100),{left:0,top:4,width:36,height:52})
  assert.equal(spotlightRect(null,100,100),null)
  assert.equal(spotlightRect({left:0,right:20,top:110,bottom:130,width:20,height:20},100,100),null)
  assert.equal(spotlightRect({left:0,right:0,top:0,bottom:0,width:0,height:0},100,100),null)
})
