import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRadarSelection } from '../src/pages/inventoryRadar.ts';

test('radar waits for scrolling to stop and selects the property currently hovered', async () => {
  const selected = [];
  let hovered = 'first';
  const radar = createRadarSelection((id) => selected.push(id), () => hovered, 20);
  radar.hover('first');
  radar.scroll();
  radar.hover('second');
  hovered = 'third';
  assert.deepEqual(selected, ['first']);
  await new Promise((resolve) => setTimeout(resolve, 40));
  assert.deepEqual(selected, ['first', 'third']);
  radar.dispose();
});
