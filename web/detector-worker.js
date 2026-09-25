// SPDX-License-Identifier: CERN-OHL-S-2.0
let runtime;
self.onmessage=async({data})=>{try{
 if(!runtime){importScripts('https://cdn.jsdelivr.net/pyodide/v0.28.1/full/pyodide.js');runtime=await loadPyodide();await runtime.loadPackage(['numpy','opencv-python']);const response=await fetch('automatic_measurement.py');if(!response.ok)throw Error('No se pudo cargar el detector.');runtime.FS.writeFile('automatic_measurement.py',await response.text());}
 runtime.globals.set('rgba_bytes',new Uint8Array(data.pixels));runtime.globals.set('image_width',data.width);runtime.globals.set('image_height',data.height);runtime.globals.set('pair_count',data.count);
 const result=await runtime.runPythonAsync(`
import json, numpy as np
from automatic_measurement import detect_pairs
rgb = np.asarray(rgba_bytes.to_py(), dtype=np.uint8).reshape(image_height, image_width, 4)[:, :, :3].copy()
pairs = detect_pairs(rgb, pair_count)
proposals = []
for pair in pairs:
    for lobe in pair['lobes']:
        for key in ('outer', 'conductor'):
            points = lobe[key]
            indices = np.linspace(0, len(points)-1, 8, dtype=int)
            proposals.append(points[indices].tolist())
    proposals.append(pair['tab'].tolist())
del rgb
json.dumps(proposals)
`);runtime.globals.delete('rgba_bytes');self.postMessage({proposals:JSON.parse(result)});
 }catch(error){self.postMessage({error:String(error.message||error)});}};
