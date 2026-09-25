// SPDX-License-Identifier: CERN-OHL-S-2.0
import { add, midpoint, distance, fitCircle, pairGeometry, tabAxisGeometry, status } from './geometry.mjs';

export function angleGuide(steps, index) {
  if (index < 1 || (index - 1) % 5 !== 4 || index >= steps.length) return null;
  const start = index - 4;
  return tabAxisGeometry(fitCircle(steps[start + 1]).c, fitCircle(steps[start + 3]).c, steps[index]);
}

export function drawOverlay(c, state, scale, { preview = true, labels = true, labelScale = scale } = {}) {
  const { steps, index, config, requirements, labelOffsets } = state;
  const hits = [];
  if (!config || index < 0) return hits;
  const px = v => v / scale;
  const line = (points, color, dash = []) => {
    c.strokeStyle = color; c.lineWidth = px(1.5); c.setLineDash(dash.map(px));
    c.beginPath(); points.forEach((p, i) => i ? c.lineTo(...p) : c.moveTo(...p)); c.stroke(); c.setLineDash([]);
  };
  const color = (value, req) => status([value], requirements[req]) === 'FUERA' ? '#ed644e' : '#64e2cd';
  const rulerScale = steps[0]?.length === 2 ? distance(...steps[0]) / config.mm : null;
  for (let i = 0; i <= Math.min(index, steps.length - 1); i++) {
    const ps = steps[i];
    if (!ps?.length) continue;
    const kind = (i - 1) % 5;
    let stroke = i === 0 ? '#ffffff' : kind === 4 ? '#ec9ddd' : kind % 2 === 0 ? '#f6b950' : '#58ded0';
    if (i === 0 || kind === 4) {
      if (ps.length === 2) {
        line(ps, stroke);
        if (i === 0) {
          const length = distance(...ps);
          if (length > 0) {
            const normal = [-(ps[1][1] - ps[0][1]) / length, (ps[1][0] - ps[0][0]) / length];
            c.font = `${px(11)}px sans-serif`; c.fillStyle = '#fff';
            for (const t of [0, .5, 1]) {
              const p = ps[0].map((v, k) => v + (ps[1][k] - v) * t);
              line([add(p, normal, -px(5)), add(p, normal, px(5))], '#fff');
              c.textAlign = t === 0 ? 'right' : t === 1 ? 'left' : 'center';
              c.fillText(`${config.mm * t} mm`, p[0] + px(t === 0 ? -6 : t === 1 ? 6 : 0), p[1] + px(t === .5 ? 22 : -12));
            }
            c.textAlign = 'left';
          }
        }
      }
    } else if (ps.length >= 3) {
      try {
        const f = fitCircle(ps);
        if (i < index && rulerScale) stroke = color(2 * f.r / rulerScale, kind % 2 ? 6 : kind === 0 ? 1 : 2);
        c.strokeStyle = stroke; c.lineWidth = px(1.6); c.setLineDash(i === index ? [px(5), px(4)] : []);
        c.beginPath(); c.arc(...f.c, f.r, 0, Math.PI * 2); c.stroke(); c.setLineDash([]);
        line([[f.c[0] - px(4), f.c[1]], [f.c[0] + px(4), f.c[1]]], stroke);
        line([[f.c[0], f.c[1] - px(4)], [f.c[0], f.c[1] + px(4)]], stroke);
      } catch { /* Incomplete/collinear points remain editable. */ }
    }
    if (preview && i === index) for (const p of ps) {
      c.beginPath(); c.arc(...p, px(5), 0, Math.PI * 2); c.fillStyle = '#fff'; c.fill();
      c.strokeStyle = '#17685b'; c.stroke();
    }
  }

  function annotation(key, text, anchor, position, stroke) {
    if (!labels) return;
    const p = add(position, labelOffsets[key] || [0, 0]);
    const font = 12 / labelScale, padding = 6 / labelScale;
    c.font = `500 ${font}px sans-serif`;
    const width = c.measureText(text).width + 2 * padding, height = font + 2 * padding;
    const rect = [p[0] - width / 2, p[1] - height / 2, width, height];
    line([anchor, p], stroke);
    c.fillStyle = '#fff'; c.fillRect(...rect); c.strokeStyle = stroke; c.lineWidth = 1 / labelScale; c.strokeRect(...rect);
    c.fillStyle = stroke === '#ed644e' ? '#a32920' : '#174d45'; c.textAlign = 'center'; c.textBaseline = 'middle';
    c.fillText(text, ...p); c.textAlign = 'left'; c.textBaseline = 'alphabetic';
    hits.push({ key, rect });
  }

  if (rulerScale) for (let i = 1; i + 4 < index; i += 5) {
    try {
      const pair = pairGeometry(steps.slice(i, i + 5), rulerScale), n = Math.floor((i - 1) / 5) + 1;
      const [a, , b] = pair.fits;
      const top = Math.min(a.c[1] - a.r, b.c[1] - b.r), bottom = Math.max(a.c[1] + a.r, b.c[1] + b.r);
      const gap = Math.max(a.r, b.r) * .28;
      for (const [side, l] of pair.lobes.entries()) {
        const x = l.outer.c[0], prefix = `P${n} L${side + 1}`;
        line(l.thicknessSegment, color(l.thickness, 5));
        annotation(`${prefix}-height`, `${prefix} · H ${l.height.toFixed(3)} mm`, add(l.outer.c, [0, -l.outer.r]), [x, top - gap * 3], color(l.height, side + 1));
        annotation(`${prefix}-copper`, `Cu Ø ${l.diameter.toFixed(3)} mm`, add(l.copper.c, [0, -l.copper.r]), [x, top - gap * 2], color(l.diameter, 6));
        annotation(`${prefix}-thickness`, `t mín. ${l.thickness.toFixed(3)} mm`, midpoint(...l.thicknessSegment), [x, top - gap], color(l.thickness, 5));
      }
      for (const [suffix, label, segment, k, position] of [
        ['width', 'Ancho', pair.widthSegment, 0, [midpoint(a.c, b.c)[0], bottom + gap * 3]],
        ['spacing', 'Centros Cu', pair.spacingSegment, 3, [midpoint(a.c, b.c)[0], bottom + gap * 2]],
        ['tab', 'Puente', pair.tab, 4, [midpoint(a.c, b.c)[0], bottom + gap]],
      ]) {
        line(segment, color(pair.row[k], k), k === 3 ? [4, 3] : []);
        annotation(`P${n}-${suffix}`, `P${n} · ${label} ${pair.row[k].toFixed(3)} mm`, midpoint(...segment), position, color(pair.row[k], k));
      }
    } catch { /* A correction may leave this pair temporarily incomplete. */ }
  }
  if (preview) {
    try {
      const g = angleGuide(steps, index);
      if (g) {
        const start = index - 4, a = fitCircle(steps[start + 1]).c, b = fitCircle(steps[start + 3]).c;
        const size = g.spacing * .38;
        line([a, b], '#b796fa', [6, 4]);
        line([add(g.anchor, g.normal, -size), add(g.anchor, g.normal, size)], '#58ded0', [2, 4]);
        line([add(g.anchor, g.axis, -size * .65), add(g.anchor, g.axis, size * .65)], '#b796fa', [2, 4]);
        if (g.direction) {
          const dot = g.axis.reduce((s, v, k) => s + v * g.direction[k], 0);
          const ref = g.axis.map(v => v * (dot < 0 ? -1 : 1)), radius = g.spacing * .065;
          if (90 - g.angle <= 1e-6) {
            line([add(g.anchor, ref, radius), add(add(g.anchor, ref, radius), g.direction, radius), add(g.anchor, g.direction, radius)], '#58ded0');
          } else {
            const begin = Math.atan2(ref[1], ref[0]);
            const turn = Math.atan2(ref[0] * g.direction[1] - ref[1] * g.direction[0], Math.abs(dot));
            line(Array.from({ length: 40 }, (_, i) => add(g.anchor, [Math.cos(begin + turn * i / 39), Math.sin(begin + turn * i / 39)], radius)), '#f6b950');
          }
        }
      }
    } catch { /* Degenerate reference is reported in the guide status. */ }
  }
  return hits;
}
