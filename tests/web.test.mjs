import {test} from 'node:test';
import assert from 'node:assert/strict';
import {fitCircle,measurements,status} from '../web/geometry.mjs';
import {tabAxisGeometry, pairGeometry} from '../web/geometry.mjs';
const circle=(x,y,r)=>Array.from({length:8},(_,i)=>[x+r*Math.cos(i*Math.PI/4),y+r*Math.sin(i*Math.PI/4)]);
test('circle fit is translation invariant and rejects collinear points',()=>{const f=fitCircle(circle(10000,22000,60));assert.ok(Math.abs(f.r-60)<1e-8);assert.ok(f.rmse<1e-8);assert.throws(()=>fitCircle([[0,0],[1,1],[2,2]]));});
test('calibrated eccentric pair, width projection and recalibration',()=>{const steps=[[[0,0],[100,0]],circle(340,325,145),circle(350,325,60),circle(680,325,145),circle(680,325,60),[[500,295],[500,355]]];const r=measurements(steps,.5);assert.equal(r.scale,200);assert.ok(Math.abs(r.values[0][0]-3.15)<1e-9);assert.ok(Math.abs(r.values[5][0]-.375)<1e-9);assert.ok(Math.abs(r.values[3][0]-1.65)<1e-9);assert.ok(Math.abs(measurements(steps,1).values[0][0]-6.3)<1e-9);});
test('limits evaluate every observation, including nominal boundaries',()=>{assert.equal(status([.594,.606],['d','nominal',.6,.006]),'OK');assert.equal(status([.59,.61],['d','nominal',.6,.006]),'FUERA');assert.equal(status([.3],['t','max',.3]),'OK');});
test('zero calibration and out of insulation conductors rejected',()=>{const s=[[[0,0],[0,0]],circle(0,0,50),circle(0,0,60),circle(150,0,80),circle(150,0,30),[[70,0],[70,10]]];assert.throws(()=>measurements(s,1));s[0][1]=[100,0];assert.throws(()=>measurements(s,1),/fuera/);});

test('thickness summary includes both lobes and not just the smaller one', () => {
 const s = [[[0,0],[100,0]],circle(0,0,100),circle(10,0,30),circle(250,0,100),circle(250,0,30),[[125,-15],[125,15]]];
 const r = measurements(s,1);
 assert.equal(r.values[5].length,2);
 assert.ok(Math.abs(Math.min(...r.values[5])-.6)<1e-10);
 assert.ok(Math.abs(Math.max(...r.values[5])-.7)<1e-10);
 assert.ok(Math.abs(r.values[5].reduce((a,b)=>a+b)/2-.65)<1e-10);
 const p = pairGeometry(s.slice(1),100);
 assert.deepEqual(p.row,r.pairs[0]);
 assert.ok(Math.abs(p.lobes[0].thickness-.6)<1e-10);
});

test('copper-axis angle is rotation and endpoint order invariant', () => {
 for (const degrees of [0,27,90,147,270]) {
  const t=degrees*Math.PI/180;
  const rotate=([x,y])=>[400+x*Math.cos(t)-y*Math.sin(t),300+x*Math.sin(t)+y*Math.cos(t)];
  const centers=[[-100,0],[100,0]].map(rotate);
  for(const [ps,angle] of [[[[0,-20],[0,20]],90],[[[0,0],[20,20]],45],[[[0,0],[20,0]],0]]) {
   const points=ps.map(rotate);
   for(const cs of [centers,[...centers].reverse()]) for(const p of [points,[...points].reverse()]) {
    assert.ok(Math.abs(tabAxisGeometry(...cs,p).angle-angle)<1e-5);
   }
  }
 }
 assert.equal(tabAxisGeometry([0,0],[10,0],[[1,1],[1,1]]).angle,null);
 assert.throws(()=>tabAxisGeometry([1,1],[1,1]));
});
