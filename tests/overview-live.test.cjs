'use strict';
const assert = require('node:assert/strict');
const path = require('node:path');
const live = require(path.join(__dirname, '..', 'app', 'web', 'static', 'overview-live.js'));

assert.equal(live.fmtPct(41.6), '42٪');
assert.equal(live.fmtPct(140), '100٪');
assert.equal(live.fmtPct(null), '—');
assert.equal(live.fmtPct(NaN), '—');
assert.equal(live.clampPct(-5), 0);

assert.equal(live.memHint({ memory_ratio_text: '2 / 4 GB' }), '2 / 4 GB');
assert.equal(live.memHint({ memory_used_text: '2', memory_total_text: '4 GB' }), '2 / 4 GB');
assert.equal(live.memHint({}), null);

assert.equal(live.partsText({ num: '1.5', unit: 'GB' }), '1.5 GB');
assert.equal(live.partsText({ num: 0 }), '0');
assert.equal(live.partsText(null), '—');

let buf = [];
for (let i = 0; i < live.SAMPLES + 5; i += 1) buf = live.pushSample(buf, i, live.SAMPLES);
assert.equal(buf.length, live.SAMPLES, 'the ring buffer stays bounded');
assert.equal(buf[buf.length - 1], live.SAMPLES + 4);
assert.deepEqual(live.pushSample([], 'x', 3), [0], 'non-numbers become zero');

assert.equal(live.sparkPoints([], 10, 300, 60), '');
assert.equal(live.sparkPoints([1, 2], 0, 300, 60), '', 'no peak, no line');
const pts = live.sparkPoints([0, 10], 10, 300, 60).split(' ');
assert.equal(pts.length, 2);
assert.equal(pts[1], '300.0,1.0', 'newest sample at the right edge, peak at the top');

assert.equal(live.badgeClass('ok'), 'badge connected');
assert.equal(live.badgeClass('<x>'), 'badge neutral');
console.log('overview-live ok');
