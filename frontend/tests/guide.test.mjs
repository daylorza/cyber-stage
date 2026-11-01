import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isOriginalRequest, matchImageStyle } from '../src/components/live/guideLogic.ts';

test('original requests are handled locally without matching unrelated words', () => {
  assert.equal(isOriginalRequest('Show me the original room'), true);
  assert.equal(isOriginalRequest('Show me Coastal'), false);
});
test('prepared image maps to its style, including encoded paths', () => {
  const styles = { '2142': { image: 'a/blue room.jpg', available: true }, coastal: { image: 'coastal.jpg', available: true } };
  assert.equal(matchImageStyle(styles, '/api/media/a/blue%20room.jpg'), '2142');
  assert.equal(matchImageStyle(styles, '/api/media/other.jpg'), null);
});

test('avatar animation prioritizes a pending reply and a style-change nod', async () => {
  const { avatarState } = await import('../src/components/live/guideLogic.ts');
  assert.equal(avatarState(true, true, true), 'thinking');
  assert.equal(avatarState(false, true, true), 'nod');
  assert.equal(avatarState(false, false, true), 'speaking');
  assert.equal(avatarState(false, false, false), 'idle');
});
