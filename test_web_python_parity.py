# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Compare browser calculations with actual desktop formulas on rotated pairs."""
import json
import subprocess
import numpy as np
from measure_wire_cross_section_v5_1 import (
    WireMeasurementApp, fit_circle, minimum_thickness_mm,
)


def main():
    for angle in (0, 27, 90, 147):
        t = np.radians(angle)
        rotation = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
        steps = [[[0, 0], [100, 0]]]
        app = WireMeasurementApp.__new__(WireMeasurementApp)
        app.lobes, app.tabs = [], []
        app.pixels_per_mm = 200.
        expected = [[] for _ in range(7)]
        for pair in range(2):
            for side in range(2):
                center = np.array([300 + side*330, 250+pair*400])
                outside = center + [5, -3]
                inside = center + [side*12, 0]
                lobe = {}
                for prefix, c, radius in [('outer', outside, 145), ('conductor', inside, 60)]:
                    pts = np.array([c + radius*np.array([np.cos(a), np.sin(a)])
                                    for a in np.linspace(0, 2*np.pi, 8, endpoint=False)]) @ rotation.T
                    steps.append(pts.tolist())
                    fitted, r, _ = fit_circle(pts)
                    lobe[prefix+'_center'] = fitted
                    lobe[prefix+'_radius'] = r
                lobe['outer_diameter_mm'] = 2*lobe['outer_radius']/app.pixels_per_mm
                lobe['conductor_diameter_mm'] = 2*lobe['conductor_radius']/app.pixels_per_mm
                lobe['minimum_thickness_mm'] = minimum_thickness_mm(
                    lobe['outer_center'], lobe['outer_radius'],
                    lobe['conductor_center'], lobe['conductor_radius'], app.pixels_per_mm)
                app.lobes.append(lobe)
            tab = np.array([[450, 220+pair*400], [465, 280+pair*400]]) @ rotation.T
            steps.append(tab.tolist())
            app.tabs.append(tab)
            row = app.calculate_pair_result(pair)
            for i, key in enumerate(('width_mm', 'height_1_mm', 'height_2_mm', 'conductor_spacing_mm', 'tab_mm')):
                expected[i].append(row[key])
        expected[5] = [l['minimum_thickness_mm'] for l in app.lobes]
        expected[6] = [l['conductor_diameter_mm'] for l in app.lobes]
        script = """import {measurements} from './web/geometry.mjs';
let raw='';for await(const chunk of process.stdin)raw+=chunk;
console.log(JSON.stringify(measurements(JSON.parse(raw),.5).values));"""
        actual = json.loads(subprocess.check_output(
            ['node', '--input-type=module', '-e', script], input=json.dumps(steps), text=True))
        for js_values, python_values in zip(actual, expected):
            assert np.allclose(js_values, python_values, atol=1e-9), (angle, js_values, python_values)
    print('PASS: browser/desktop parity for all seven dimensions, two eccentric pairs and four rotations')


if __name__ == '__main__':
    main()
