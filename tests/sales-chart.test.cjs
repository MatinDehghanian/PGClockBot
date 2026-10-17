'use strict';
const assert = require('assert');
const chart = require('../app/web/static/sales-chart.js');

assert.strictEqual(chart.compactToman(4820000), '4.82 میلیون');
assert.strictEqual(chart.compactToman(250000), '250 هزار');
assert.strictEqual(chart.compactToman(1000000), '1 میلیون');
assert.strictEqual(chart.compactToman(900), '900');
assert.strictEqual(chart.compactToman(0), '0');
assert.strictEqual(chart.fullToman(27420000), '27,420,000');

const scale = chart.niceScale(5800000);
assert.ok(scale.max >= 5800000 * 1.2, 'headroom above the peak');
assert.strictEqual(scale.max, scale.step * 3);
assert.ok(chart.niceScale(0).step > 0, 'empty data still has a scale');

// A monotone curve never goes above the highest or below the lowest control value.
const points = [[0, 100], [50, 20], [100, 20], [150, 90], [200, 10]];
const path = chart.monotonePath(points);
const numbers = path.match(/-?\d+(\.\d+)?/g).map(Number);
const ys = [];
for (let i = 1; i < numbers.length; i += 2) ys.push(numbers[i]);
assert.ok(Math.min(...ys) >= 10 - 1e-9 && Math.max(...ys) <= 100 + 1e-9, 'no overshoot');
assert.ok(path.startsWith('M0,100'));
assert.strictEqual(chart.monotonePath([]), '');
assert.strictEqual(chart.monotonePath([[5, 5]]), 'M5,5');
console.log('sales-chart ok');
