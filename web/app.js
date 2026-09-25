// SPDX-License-Identifier: CERN-OHL-S-2.0
import {distance, fitCircle, definitions, measurements, pairGeometry, status} from './geometry.mjs';
import {drawOverlay, angleGuide} from './drawing.mjs';

const $ = id => document.getElementById(id), canvas = $('canvas'), ctx = canvas.getContext('2d');
let photo = null, steps = [], index = -1, config = null, result = null;
let zoom = 1, offset = [0, 0], drag = null, worker = null, busy = false, automatic = false;
let labelOffsets = {}, labelHits = [], viewMode = 'fit', viewSize = null, cancelDetection = null;
const reqs = definitions.map(r => [...r]);
const names = ['Aislamiento · lado 1', 'Conductor · lado 1', 'Aislamiento · lado 2', 'Conductor · lado 2', 'Puente central'];
const name = i => i === 0 ? 'Calibración de la regla' : `Par ${Math.floor((i - 1) / 5) + 1} · ${names[(i - 1) % 5]}`;
const needed = i => i === 0 || (i - 1) % 5 === 4 ? 2 : config.points;
const fmt = v => v.toFixed(3);
const reqText = r => r[1] === 'none' ? 'Sin requisito' : r[1] === 'nominal' ? `${fmt(r[2])} ± ${fmt(r[3])}` : `${r[1] === 'min' ? '≥' : '≤'} ${fmt(r[2])}`;
const state = () => ({steps, index, config, requirements: reqs, labelOffsets});
const outputName = () => ($('outputname').value.trim().replace(/[<>:"/\\|?*\x00-\x1f]/g, '_') || 'seccion-informe');
function message(text) { $('instruction').textContent = text; }
function controls() {
  const active = index >= 0 && index < steps.length;
  $('accept').disabled = busy || !active || steps[index].length < needed(index);
  $('undo').disabled = busy || index < 0;
  $('undo-step').disabled = busy || index <= 0;
  $('redraw').disabled = busy || !active;
  $('cancel').disabled = !busy;
  for (const id of ['start', 'auto', 'file', 'demo']) $(id).disabled = busy || (!photo && ['start', 'auto'].includes(id));
  $('edit').disabled = busy || index < 0;
  $('steps').disabled = busy || index < 0;
  for (const id of ['csv', 'png', 'jpg', 'pdf']) $(id).disabled = !result || busy;
  $('progress').textContent = busy ? 'DÉTECCIÓN EN CURSO · PUEDES CANCELAR' : index < 0 ? 'LISTO PARA COMENZAR' : active ? `PASO ${index + 1} DE ${steps.length} · ${steps[index].length} / ${needed(index)} PUNTOS` : 'MEDICIÓN COMPLETA';
}
function instruction() {
  controls();
  if (index >= 0 && index < steps.length) {
    const detail = steps[index].length >= needed(index) ? 'Revisa y arrastra los puntos; luego acepta el paso.' : index === 0 ? `Marca los extremos del tramo de ${config.mm} mm.` : (index - 1) % 5 === 4 ? 'Marca los extremos del puente. Usa el eje del cobre y la guía perpendicular.' : 'Distribuye los puntos alrededor del contorno indicado.';
    message(`${name(index)}. ${detail}`);
  }
}
function baseZoom() { return photo ? Math.min(canvas.clientWidth / photo.width, canvas.clientHeight / photo.height) * .94 : 1; }
function fit(fill = false) {
  if (!photo) return;
  viewMode = fill ? 'fill' : 'fit';
  zoom = fill ? Math.max(canvas.clientWidth / photo.width, canvas.clientHeight / photo.height) : baseZoom();
  offset = [(canvas.clientWidth - photo.width * zoom) / 2, (canvas.clientHeight - photo.height * zoom) / 2];
  draw();
}
function resize() {
  const previous = viewSize;
  viewSize = [canvas.clientWidth, canvas.clientHeight];
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(viewSize[0] * dpr); canvas.height = Math.round(viewSize[1] * dpr);
  if (photo && ($('autofit').checked || !previous)) fit(viewMode === 'fill');
  else {
    if (previous) offset = offset.map((v, k) => v + (viewSize[k] - previous[k]) / 2);
    draw();
  }
}
new ResizeObserver(resize).observe($('viewport'));
function draw() {
  const dpr = window.devicePixelRatio || 1;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight);
  $('angle-status').hidden = true;
  if (!photo) return;
  ctx.translate(...offset); ctx.scale(zoom, zoom); ctx.drawImage(photo, 0, 0);
  labelHits = drawOverlay(ctx, state(), zoom, {labels: $('labels').checked});
  const percentage = Math.round(zoom / baseZoom() * 100);
  $('zoomvalue').textContent = `${percentage}%`; $('zoomrange').value = percentage;
  try {
    const guide = angleGuide(steps, index);
    if (guide) {
      $('angle-status').hidden = false;
      $('angle-status').classList.toggle('aligned', guide.angle !== null && 90 - guide.angle < 1e-6);
      $('angle-status').textContent = guide.angle === null ? 'Eje del cobre: morado · Perpendicular: verde\nMarca dos extremos distintos para ver el ángulo.' : `Ángulo con el eje Cu: ${guide.angle.toFixed(2)}° · Desviación de 90°: ${(90 - guide.angle).toFixed(2)}°\nArrastra los extremos para alinearlos con la guía verde.`;
    }
  } catch (error) { $('angle-status').hidden = false; $('angle-status').textContent = error.message; }
}
function clearResults(note) { result = null; $('results').replaceChildren(); $('details').replaceChildren(); $('resultnote').textContent = note; }
function loadImage(src, label) {
  const next = new Image();
  next.onload = () => {
    photo = next; steps = []; index = -1; config = null; labelOffsets = {}; drag = null;
    clearResults('Los resultados aparecerán al completar y aceptar todos los pasos.');
    $('empty').hidden = true; $('filename').textContent = label;
    $('viewtitle').textContent = `${next.width} × ${next.height} PX`;
    $('steps').replaceChildren(new Option('Primero inicia una medición'));
    $('outputname').value = label.replace(/\.[^.]+$/, '').slice(0, 80) + '-informe';
    fit(); controls(); message('Imagen lista. Configura la regla y elige un modo de medición.');
    if (src.startsWith('blob:')) URL.revokeObjectURL(src);
  };
  next.onerror = () => { message('No se pudo abrir la imagen. Prueba con PNG o JPG.'); if (src.startsWith('blob:')) URL.revokeObjectURL(src); };
  next.src = src;
}
function replaceImage(src, label) {
  if (index >= 0 && !confirm('¿Abrir otra imagen y descartar la medición actual?')) { if (src.startsWith('blob:')) URL.revokeObjectURL(src); return; }
  loadImage(src, label);
}
$('file').onchange = e => { const f = e.target.files[0]; if (f) replaceImage(URL.createObjectURL(f), f.name); e.target.value = ''; };

function start(auto) {
  if (!photo || busy) return;
  const count = Number($('pairs').value), points = Number($('points').value), mm = Number($('ruler').value);
  if (!Number.isInteger(count) || count < 1 || count > 12 || !Number.isInteger(points) || points < 3 || points > 32 || !Number.isFinite(mm) || mm <= 0) { message('Revisa la configuración: 1–12 pares, 3–32 puntos y una regla positiva.'); return; }
  if (index >= 0 && !confirm('¿Reiniciar la medición? Se borrarán los puntos actuales.')) return;
  config = {count, points, mm}; automatic = auto; index = 0; labelOffsets = {};
  steps = Array.from({length: 1 + count * 5}, () => []);
  clearResults('Medición en curso. Acepta todos los pasos para obtener resultados.');
  updateOptions(); instruction(); draw(); canvas.focus();
}
$('start').onclick = () => start(false); $('auto').onclick = () => start(true);
function updateOptions() {
  $('steps').replaceChildren(...steps.map((_, i) => new Option(name(i), i)));
  $('steps').value = Math.min(index, steps.length - 1);
  for (const opt of $('steps').options) opt.disabled = Number(opt.value) > index;
}
function detect() {
  busy = true; controls(); message('Cargando el motor automático y analizando la imagen. La primera carga puede tardar unos minutos.');
  worker = new Worker('detector-worker.js');
  const source = document.createElement('canvas'), ratio = Math.min(1, 1280 / Math.max(photo.width, photo.height));
  source.width = Math.round(photo.width * ratio); source.height = Math.round(photo.height * ratio);
  const c = source.getContext('2d'); c.drawImage(photo, 0, 0, source.width, source.height);
  const data = c.getImageData(0, 0, source.width, source.height);
  let finished = false;
  const timeout = setTimeout(() => finish({error: 'Se agotó el tiempo de carga.'}), 240000);
  function finish(data) {
    if (finished) return; finished = true;
    clearTimeout(timeout); worker.terminate(); worker = null; busy = false; cancelDetection = null;
    if (data.proposals) {
      steps.splice(1, steps.length - 1, ...data.proposals.map(ps => ps.map(p => [p[0] * photo.width / source.width, p[1] * photo.height / source.height])));
      instruction();
    } else { instruction(); message(`${data.error || 'No se pudieron detectar todos los contornos.'} La regla se conserva; continúa manualmente.`); }
    draw();
  }
  cancelDetection = () => finish({error: 'Detección cancelada.'});
  worker.onmessage = e => finish(e.data);
  worker.onerror = () => finish({error: 'No se pudo cargar el motor. Comprueba la conexión.'});
  worker.postMessage({pixels: data.data.buffer, width: source.width, height: source.height, count: config.count, points: config.points}, [data.data.buffer]);
}
$('cancel').onclick = () => cancelDetection?.();
function accept() {
  if ($('accept').disabled || drag) return;
  try {
    const p = steps[index];
    if (index === 0 || (index - 1) % 5 === 4) { if (distance(...p) < 1e-6) throw Error('Los extremos deben ser distintos.'); }
    else fitCircle(p);
    if (index === steps.length - 1) measurements(steps, config.mm);
    index++; updateOptions();
    if (index === steps.length) { renderResults(); message('Medición completa. Arrastra las etiquetas para ordenar el informe, o corrige un paso.'); }
    else instruction();
    draw();
    if (index === 1 && automatic) { automatic = false; detect(); }
  } catch (e) { message(e.message); }
}
$('accept').onclick = accept;
function invalidate() { clearResults('Revisión en curso: vuelve a aceptar los pasos para recalcular.'); }
$('edit').onclick = () => { index = Number($('steps').value); invalidate(); updateOptions(); instruction(); draw(); };
function undoClosure() {
  if (busy || index <= 0) return;
  if (index < steps.length) steps[index] = [];
  index--; steps[index].pop();
  invalidate(); updateOptions(); instruction(); draw();
}
function undo() {
  if (busy || index < 0) return;
  if (index === steps.length || !steps[index].length) { undoClosure(); return; }
  steps[index].pop(); invalidate(); updateOptions(); instruction(); draw();
}
$('undo').onclick = undo; $('undo-step').onclick = undoClosure;
$('redraw').onclick = () => { steps[index] = []; instruction(); draw(); };
function point(e) { const r = canvas.getBoundingClientRect(); return [(e.clientX - r.left - offset[0]) / zoom, (e.clientY - r.top - offset[1]) / zoom]; }
canvas.onpointerdown = e => {
  if (!photo || busy) return;
  canvas.focus(); canvas.setPointerCapture(e.pointerId);
  const p = point(e);
  if (e.shiftKey || e.button === 1) { drag = {pan: true, x: e.clientX, y: e.clientY, offset: [...offset]}; viewMode = 'manual'; return; }
  if (e.button !== 0) return;
  const active = index >= 0 && index < steps.length;
  const found = active ? steps[index].findIndex(q => distance(p, q) < 10 / zoom) : -1;
  if (found >= 0) drag = {point: found};
  else {
    const hit = [...labelHits].reverse().find(({rect: [x, y, w, h]}) => p[0] >= x && p[0] <= x + w && p[1] >= y && p[1] <= y + h);
    if (hit) { drag = {label: hit.key, start: p, offset: [...(labelOffsets[hit.key] || [0, 0])]}; return; }
    if (active && steps[index].length < needed(index) && p[0] >= 0 && p[1] >= 0 && p[0] <= photo.width && p[1] <= photo.height) {
      steps[index].push(p); drag = {point: steps[index].length - 1};
    }
  }
  instruction(); draw();
};
canvas.onpointermove = e => {
  if (!drag) return;
  if (drag.pan) offset = [drag.offset[0] + e.clientX - drag.x, drag.offset[1] + e.clientY - drag.y];
  else if (drag.label) labelOffsets[drag.label] = point(e).map((v, k) => drag.offset[k] + v - drag.start[k]);
  else steps[index][drag.point] = point(e).map((v, k) => Math.max(0, Math.min(v, k === 0 ? photo.width : photo.height)));
  draw();
};
canvas.onpointerup = canvas.onpointercancel = canvas.onlostpointercapture = () => { drag = null; };
canvas.oncontextmenu = e => { e.preventDefault(); undo(); };
function magnify(f, x = canvas.clientWidth / 2, y = canvas.clientHeight / 2) {
  if (!photo) return;
  const next = Math.max(baseZoom() * .25, Math.min(baseZoom() * 16, zoom * f));
  offset = [x - (x - offset[0]) * next / zoom, y - (y - offset[1]) * next / zoom]; zoom = next; viewMode = 'manual'; draw();
}
canvas.addEventListener('wheel', e => { e.preventDefault(); const r = canvas.getBoundingClientRect(); magnify(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top); }, {passive: false});
$('zoomin').onclick = () => magnify(1.25); $('zoomout').onclick = () => magnify(.8);
$('fit').onclick = () => fit(); $('fill').onclick = () => fit(true);
$('zoomrange').oninput = e => magnify(baseZoom() * Number(e.target.value) / 100 / zoom);
$('labels').onchange = draw; $('resetlabels').onclick = () => { labelOffsets = {}; draw(); };
$('toggle-results').onclick = () => {
  const hidden = !$('resultspanel').hidden; $('resultspanel').hidden = hidden;
  $('toggle-results').textContent = hidden ? 'Mostrar resultados' : 'Ocultar resultados';
  $('toggle-results').setAttribute('aria-expanded', String(!hidden));
  document.querySelector('.workspace').classList.toggle('focus-results-hidden', hidden);
};
canvas.onkeydown = e => {
  if (e.code === 'Space') { e.preventDefault(); accept(); }
  else if (e.ctrlKey && e.key.toLowerCase() === 'z') { e.preventDefault(); undoClosure(); }
  else if (e.key === 'Backspace') { e.preventDefault(); undo(); }
  else if (e.key.toLowerCase() === 'f') fit();
  else if (e.key === 'Escape') { if (busy) cancelDetection?.(); else { drag = null; message('Arrastre cancelado. Puedes seguir revisando los puntos.'); } }
};
document.addEventListener('keydown', e => {
  if (/INPUT|SELECT|TEXTAREA/.test(e.target.tagName)) return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'o') { e.preventDefault(); if (!busy) $('file').click(); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); if (result && !busy) $('png').click(); }
});

for (const r of reqs) {
  const label = document.createElement('label'); label.textContent = `${r[0]} (mm)`;
  const select = document.createElement('select');
  for (const [v, t] of [['none', 'Sin requisito'], ['nominal', 'Nominal ± tolerancia'], ['min', 'Mínimo'], ['max', 'Máximo']]) select.add(new Option(t, v));
  select.value = r[1];
  const row = document.createElement('div'); row.className = 'fields';
  const val = document.createElement('input'), tol = document.createElement('input');
  for (const input of [val, tol]) { input.type = 'number'; input.min = '0'; input.step = '.001'; }
  val.value = r[2]; tol.value = r[3]; val.setAttribute('aria-label', `${r[0]} valor`); tol.setAttribute('aria-label', `${r[0]} tolerancia`);
  function change() {
    if (!Number.isFinite(val.valueAsNumber) || val.valueAsNumber < 0 || !Number.isFinite(tol.valueAsNumber) || tol.valueAsNumber < 0) { message('Las tolerancias deben ser números positivos o cero.'); return; }
    r[1] = select.value; r[2] = val.valueAsNumber; r[3] = tol.valueAsNumber;
    val.disabled = r[1] === 'none'; tol.disabled = r[1] !== 'nominal';
    if (result) renderResults(); draw();
  }
  select.onchange = val.onchange = tol.onchange = change;
  row.append(val, tol); label.append(select, row); $('requirements').append(label); change();
}
function appendRow(parent, values, classes = []) {
  const tr = document.createElement('tr');
  values.forEach((value, i) => { const td = document.createElement('td'); td.textContent = value; td.className = classes[i] || ''; tr.append(td); });
  parent.append(tr);
}
function details() {
  return result ? result.pairs.map((_, i) => pairGeometry(steps.slice(1 + 5 * i, 6 + 5 * i), result.scale)) : [];
}
function renderResults() {
  result = measurements(steps, config.mm); $('results').replaceChildren(); $('details').replaceChildren();
  for (const [i, values] of result.values.entries()) {
    const check = status(values, reqs[i]);
    appendRow($('results'), [definitions[i][0], fmt(Math.min(...values)), fmt(Math.max(...values)), fmt(values.reduce((a, b) => a + b) / values.length), reqText(reqs[i]), check], ['', '', '', '', '', check === 'FUERA' ? 'fail' : 'ok']);
  }
  details().forEach((pair, i) => pair.lobes.forEach((l, side) => appendRow($('details'),
    [`P${i + 1} / L${side + 1}`, fmt(l.height), fmt(l.diameter), fmt(l.thickness), fmt(l.outer.rmse), fmt(l.copper.rmse), `${pair.angle.toFixed(2)}°`],
    ['', status([l.height], reqs[side + 1]) === 'FUERA' ? 'fail' : 'ok', status([l.diameter], reqs[6]) === 'FUERA' ? 'fail' : 'ok', status([l.thickness], reqs[5]) === 'FUERA' ? 'fail' : 'ok'])));
  $('resultnote').textContent = `${config.count} par(es) · ${fmt(result.scale)} px/mm · Estados por valor individual · RMSE: error del ajuste circular, no incertidumbre metrológica.`;
  controls();
}
function download(blob, filename) {
  const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$('csv').onclick = () => {
  const rows = [['Analizador de sección de cables · Web 1.1'], ['Regla (mm)', config.mm], ['Escala (px/mm)', result.scale], ['Puntos por círculo', config.points], [], ['Medida', 'Mínimo', 'Máximo', 'Media', 'Requisito', 'Estado']];
  result.values.forEach((v, i) => rows.push([definitions[i][0], Math.min(...v), Math.max(...v), v.reduce((a, b) => a + b) / v.length, reqText(reqs[i]), status(v, reqs[i])]));
  rows.push([], ['Par', ...definitions.slice(0, 6).map(r => r[0]), 'Diámetro conductor 1', 'Diámetro conductor 2']);
  result.pairs.forEach((r, i) => rows.push([i + 1, ...r.slice(0, 6), ...r[6]]));
  rows.push([], ['Par', 'Lado', 'Altura (mm)', 'Cu diámetro (mm)', 'Espesor mínimo (mm)', 'RMSE exterior (px)', 'RMSE cobre (px)', 'Ángulo puente (°)']);
  details().forEach((p, i) => p.lobes.forEach((l, j) => rows.push([i + 1, j + 1, l.height, l.diameter, l.thickness, l.outer.rmse, l.copper.rmse, p.angle])));
  rows.push([], ['Puntos originales (px)'], ['Paso', 'Punto', 'X', 'Y']);
  steps.forEach((ps, i) => ps.forEach((p, j) => rows.push([name(i), j + 1, ...p])));
  download(new Blob(['\ufeff' + rows.map(r => r.map(v => '"' + String(v).replaceAll('"', '""') + '"').join(';')).join('\r\n')], {type: 'text/csv;charset=utf-8'}), outputName() + '.csv');
};
function reportCanvas() {
  // Include every moved label, even outside the photo; export ignores viewport zoom.
  const report = document.createElement('canvas'), c = report.getContext('2d');
  const nominalScale = Math.min(1400 / photo.width, 1100 / photo.height);
  const labels = drawOverlay(c, state(), nominalScale, {preview: false, labels: true});
  const minX = Math.min(0, ...labels.map(h => h.rect[0])), minY = Math.min(0, ...labels.map(h => h.rect[1]));
  const maxX = Math.max(photo.width, ...labels.map(h => h.rect[0] + h.rect[2])), maxY = Math.max(photo.height, ...labels.map(h => h.rect[1] + h.rect[3]));
  const scale = Math.min(1400 / (maxX - minX), 1100 / (maxY - minY)), imageHeight = (maxY - minY) * scale;
  const detailRows = details().flatMap((p, i) => p.lobes.map((l, j) => [`P${i + 1} / L${j + 1}`, fmt(l.height), fmt(l.diameter), fmt(l.thickness), fmt(l.outer.rmse), fmt(l.copper.rmse), p.angle.toFixed(2) + '°']));
  report.width = 1500; report.height = Math.ceil(imageHeight + 565 + detailRows.length * 30);
  c.fillStyle = '#fff'; c.fillRect(0, 0, report.width, report.height);
  c.fillStyle = '#183236'; c.font = 'bold 30px sans-serif'; c.fillText('SECCIÓN · Informe dimensional', 50, 48);
  c.font = '17px sans-serif'; c.fillText(`${config.count} par(es) · Regla ${config.mm} mm · ${fmt(result.scale)} px/mm · ${new Date().toLocaleDateString('es-CL')}`, 50, 80);
  c.save(); c.translate(50 - minX * scale, 110 - minY * scale); c.scale(scale, scale);
  c.drawImage(photo, 0, 0); drawOverlay(c, state(), scale, {preview: false, labels: true, labelScale: nominalScale}); c.restore();
  let y = imageHeight + 155;
  function row(values, xs, bold = false) { c.font = `${bold ? 'bold ' : ''}16px sans-serif`; c.fillStyle = '#183236'; values.forEach((t, i) => c.fillText(t, xs[i], y)); y += 30; }
  const xs = [50, 440, 610, 780, 950, 1310];
  row(['Medida (mm)', 'Mín.', 'Máx.', 'Media', 'Requisito', 'Estado'], xs, true);
  result.values.forEach((v, i) => row([definitions[i][0], fmt(Math.min(...v)), fmt(Math.max(...v)), fmt(v.reduce((a, b) => a + b) / v.length), reqText(reqs[i]), status(v, reqs[i])], xs));
  y += 25;
  const dx = [50, 235, 420, 610, 810, 1035, 1280];
  row(['Par / lado', 'Altura (mm)', 'Cu Ø (mm)', 't mín. (mm)', 'RMSE ext. (px)', 'RMSE Cu (px)', 'Ángulo puente'], dx, true);
  detailRows.forEach(r => row(r, dx));
  y += 20; c.font = '14px sans-serif';
  c.fillText('Cotas calculadas mediante ajustes circulares. Revisar escala y contornos. El RMSE no representa incertidumbre metrológica.', 50, y);
  c.fillText('Ángulo del puente respecto al eje de los centros de cobre. Los estados evalúan cada valor individual.', 50, y + 25);
  return report;
}
function exportImage(type, extension) {
  try { reportCanvas().toBlob(blob => { if (blob) download(blob, outputName() + extension); else message('No se pudo generar el informe.'); }, type, .95); }
  catch (e) { message(`No se pudo generar el informe: ${e.message}`); }
}
$('png').onclick = () => exportImage('image/png', '.png');
$('jpg').onclick = () => exportImage('image/jpeg', '.jpg');
$('pdf').onclick = async () => {
  try {
    const image = new Image(); image.src = reportCanvas().toDataURL('image/png'); await image.decode();
    $('print-report').replaceChildren(image); window.print();
  } catch (e) { message(`No se pudo preparar el informe: ${e.message}`); }
};
controls();

$("demo").onclick = () => {
  const c = document.createElement("canvas");
  c.width = 1100;
  c.height = 650;
  const x = c.getContext("2d");
  x.fillStyle = "#202c30";
  x.fillRect(0, 0, c.width, c.height);
  x.fillStyle = "#85aa51";
  x.fillRect(320, 295, 340, 60);
  for (const [cx, color] of [
    [340, "#71ad60"],
    [680, "#d6c456"],
  ]) {
    x.beginPath();
    x.arc(cx, 325, 145, 0, 7);
    x.fillStyle = color;
    x.fill();
    x.beginPath();
    x.arc(cx, 325, 60, 0, 7);
    x.fillStyle = "#bd865a";
    x.fill();
    x.strokeStyle = "#e3b78d";
    x.lineWidth = 1.5;
    for (let i = 0; i < 18; i++) {
      const a = i * 2.4,
        r = 48 * Math.sqrt(i / 18);
      x.beginPath();
      x.arc(cx + Math.cos(a) * r, 325 + Math.sin(a) * r, 9, 0, 7);
      x.stroke();
    }
  }
  x.fillStyle = "#fff";
  x.fillRect(100, 550, 100, 4);
  x.font = "18px sans-serif";
  x.fillText("0,5 mm", 110, 587);
  x.fillText("MUESTRA SINTÉTICA · 200 px/mm", 100, 80);
  $("pairs").value = 1;
  $("ruler").value = 0.5;
  replaceImage(c.toDataURL(), "Ejemplo sintético · escala de 0,5 mm");
};