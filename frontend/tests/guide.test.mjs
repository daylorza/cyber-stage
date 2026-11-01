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

test('mobile quick actions keep Reserve visible and expose extra room actions', async () => {
  const { mobileActions } = await import('../src/components/live/guideLogic.ts');
  assert.deepEqual(mobileActions('modern-luxury', 1, false), ['Price', 'Amenities', 'Reserve it']);
  assert.deepEqual(mobileActions('modern-luxury', 2, false), ['Price', 'More', 'Reserve it']);
  assert.deepEqual(mobileActions('modern-luxury', 2, true), ['Amenities', 'Next room', 'Reserve it']);
  assert.deepEqual(mobileActions('coastal', 2, false), ['Price', 'More', 'Reserve it']);
});

test('guide text hides citations, URLs and markdown and deduplicates the concept disclaimer', async () => {
  const { cleanGuideText } = await import('../src/components/live/guideLogic.ts');
  const text = cleanGuideText('**Cyberpunk** [fact:title] [o_f01_1] https://example.com/a\nNote: Cyberpunk concept · AI-imagined, not a verified depiction of the property.\nCyberpunk concept · AI-imagined, not a verified depiction of the property.');
  assert.equal(text, 'Cyberpunk\nCyberpunk concept · AI-imagined, not a verified depiction of the property.');
});

test('guide text makes a style recommendation generic without hiding a chosen style', async () => {
  const { cleanGuideText } = await import('../src/components/live/guideLogic.ts');
  assert.equal(cleanGuideText('I cannot help with shopping. Want me to switch this room to Coastal?'), 'I cannot help with shopping.\nWould you like to see the next style?');
  assert.equal(cleanGuideText('Now showing Coastal in the living room.'), 'Now showing Coastal in the living room.');
});
