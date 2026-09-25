// SPDX-License-Identifier: CERN-OHL-S-2.0
export const distance=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
export function fitCircle(points){
 if(points.length<3)throw Error('Marca al menos tres puntos.');
 const mean=[0,1].map(k=>points.reduce((s,p)=>s+p[k],0)/points.length);
 const rows=points.map(p=>[2*(p[0]-mean[0]),2*(p[1]-mean[1]),1,(p[0]-mean[0])**2+(p[1]-mean[1])**2]);
 const m=Array.from({length:3},(_,i)=>Array.from({length:4},(_,j)=>rows.reduce((s,r)=>s+r[i]*r[j],0)));
 for(let i=0;i<3;i++){let pivot=i;for(let k=i+1;k<3;k++)if(Math.abs(m[k][i])>Math.abs(m[pivot][i]))pivot=k;[m[i],m[pivot]]=[m[pivot],m[i]];if(Math.abs(m[i][i])<1e-9)throw Error('Los puntos están alineados. Distribúyelos alrededor del contorno.');const d=m[i][i];for(let j=i;j<4;j++)m[i][j]/=d;for(let k=0;k<3;k++)if(k!==i){const f=m[k][i];for(let j=i;j<4;j++)m[k][j]-=f*m[i][j];}}
 const c=[m[0][3]+mean[0],m[1][3]+mean[1]],r=Math.sqrt(m[2][3]+m[0][3]**2+m[1][3]**2);if(!Number.isFinite(r)||r<=0)throw Error('No se puede ajustar este círculo.');return {c,r,rmse:Math.sqrt(points.reduce((s,p)=>s+(distance(p,c)-r)**2,0)/points.length)};
}
export const definitions=[['Ancho','none',0,0],['Altura 1','nominal',1.45,.05],['Altura 2','nominal',1.45,.05],['Separación de conductores','nominal',1.7,.1],['Puente','max',.3,0],['Espesor mínimo','min',.35,0],['Diámetro de conductor','nominal',.6,.006]];
export function measurements(steps,mm){
 const scale=distance(...steps[0])/mm;if(!Number.isFinite(scale)||scale<=0)throw Error('La regla debe tener una longitud mayor que cero.');
 const values=definitions.map(()=>[]),pairs=[];
 for(let i=1;i<steps.length;i+=5){const [a,b,c,d]=steps.slice(i,i+4).map(fitCircle);const length=distance(b.c,d.c);if(length<1e-8)throw Error('Los centros de los conductores coinciden. Revisa los contornos.');const axis=d.c.map((v,k)=>(v-b.c[k])/length);const pa=a.c.reduce((s,v,k)=>s+v*axis[k],0),pc=c.c.reduce((s,v,k)=>s+v*axis[k],0);const thickness=[a.r-b.r-distance(a.c,b.c),c.r-d.r-distance(c.c,d.c)];if(Math.min(...thickness)<0)throw Error('Un conductor queda fuera del aislamiento. Corrige sus contornos.');const row=[(Math.max(pa+a.r,pc+c.r)-Math.min(pa-a.r,pc-c.r))/scale,2*a.r/scale,2*c.r/scale,length/scale,distance(...steps[i+4])/scale,Math.min(...thickness)/scale,[2*b.r/scale,2*d.r/scale]];row.forEach((v,k)=>values[k].push(...(Array.isArray(v)?v:[v])));pairs.push(row);}
 return {values,pairs,scale};
}
export function status(values,req){if(req[1]==='none')return '—';return values.every(v=>req[1]==='min'?v>=req[2]-1e-10:req[1]==='max'?v<=req[2]+1e-10:Math.abs(v-req[2])<=req[3]+1e-10)?'OK':'FUERA';}
