# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Run in a desktop session: python test_automatic_measurement.py."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tkinter as tk

import numpy as np
from PIL import Image, ImageDraw
from matplotlib.backend_bases import MouseEvent

from automatic_measurement import DetectionError, detect_pairs
from measure_wire_cross_section_v5_1 import WireMeasurementApp


def synthetic_image(count=2):
    image = Image.new("RGB", (900, 140+280*count), (170, 170, 170))
    draw = ImageDraw.Draw(image)
    for y in range(210, 210+280*count, 280):
        draw.rectangle((290, y-18, 510, y+18), fill=(190, 190, 20))
        for x, color in ((290, (20, 180, 60)), (510, (210, 210, 20))):
            draw.ellipse((x-90, y-90, x+90, y+90), fill=color)
            draw.ellipse((x-36, y-36, x+36, y+36), fill=(160, 85, 65))
    return image


def main():
    synthetic = synthetic_image()
    proposals = detect_pairs(synthetic, 2)
    assert len(proposals) == 2
    for row, pair in enumerate(proposals):
        for column, lobe in enumerate(pair['lobes']):
            expected = [290+220*column, 210+280*row]
            assert np.linalg.norm(lobe['center']-expected) < 3
            assert abs(lobe['radius']-90) < 3
            assert np.linalg.norm(lobe['conductor_center']-expected) < 5
            assert abs(lobe['conductor_radius']-36) < 4
        assert abs(np.linalg.norm(pair['tab'][1]-pair['tab'][0])-36) < 4
    try:
        detect_pairs(Image.new('RGB', (500, 500), 'white'), 2)
        raise AssertionError('Blank images must not produce measurements')
    except DetectionError:
        pass
    for count in (1, 3):
        assert len(detect_pairs(synthetic_image(count), count)) == count
    scaled = detect_pairs(synthetic.resize((1800, 1400)), 2)
    assert np.linalg.norm(scaled[0]['lobes'][0]['center']-[580, 420]) < 6

    root = tk.Tk()
    root.withdraw()
    app = WireMeasurementApp(root)
    app.image = synthetic
    app.image_array = np.asarray(synthetic)
    app.start_automatic_measurement()
    app.canvas.draw()

    def click(point):
        event = MouseEvent('button_press_event', app.canvas,
                           *app.ax.transData.transform(point), button=1)
        app.on_mouse_click(event)
        return event

    click([100, 100])
    click([200, 100])
    assert app.step_index == 0 and app.pending_review
    assert any(getattr(a, 'get_text', lambda: '')() == '0.500 mm'
               for a in app.preview_artists)
    app.session_setup['scale_length'] = .5
    app.draw_current_points()
    assert any(getattr(a, 'get_text', lambda: '')() == '0.250 mm'
               for a in app.preview_artists)
    app.session_setup['scale_length'] = 1.
    app.draw_current_points()
    app.canvas.draw()
    click([200, 100])
    assert app.point_drag == 1
    app.on_mouse_move(SimpleNamespace(inaxes=app.ax, xdata=220., ydata=100.))
    app.on_mouse_release(None)
    with patch('measure_wire_cross_section_v5_1.messagebox.showwarning') as warning:
        app.complete_current_step()
        warning.assert_not_called()
    assert abs(app.pixels_per_mm-120) < 1e-6
    assert app.step_index == 1 and app.pending_review
    # A manual replacement must not reinsert the discarded automatic points.
    proposed = [p.copy() for p in app.current_points]
    app.redraw_step_manually()
    assert app.current_points == [] and not app.pending_review and 1 not in app.auto_proposals
    app.current_points = proposed
    app.draw_current_points()

    # Set-up entries cannot silently change a calibrated measurement.
    app.scale_length_var.set('2.0')
    app.pair_count_var.set(7)
    assert app.get_scale_length_mm() == 1.0 and app.get_pair_count() == 2
    app.canvas.draw()
    point = app.current_points[0].copy()
    click(point)
    assert app.point_drag == 0
    app.on_mouse_move(SimpleNamespace(inaxes=app.ax, xdata=point[0]+2, ydata=point[1]))
    app.on_mouse_release(None)
    assert app.current_points[0][0] == point[0]+2
    while app.step_index >= 0:
        assert app.pending_review
        app.complete_current_step()
    assert app.summary_rows is not None
    before = app.pair_results[0]['width_mm']
    app.edit_step_combo.current(0)
    app.edit_selected_step()
    assert app.step_index == 0 and app.pending_review and app.summary_rows is None
    # Recalibrate to twice as many pixels/mm, reusing accepted geometry.
    app.current_points[1] = app.current_points[0]+[240, 0]
    while app.step_index >= 0:
        app.complete_current_step()
    assert np.isclose(app.pair_results[0]['width_mm'], before/2)
    report = app.create_report_figure()
    assert any(t.get_text() == '0.500 mm' for t in report.axes[1].texts)
    report.clear()

    # Real fixtures exercise overlays/texture and pairing, not calibrated accuracy.
    for path in Path('.').glob('WhatsApp*.jpeg'):
        image = Image.open(path).convert('RGB')
        pairs = detect_pairs(image, 2)
        assert len(pairs) == 2
        app.image = image
        app.image_array = np.asarray(image)
        app.pair_count_var.set(2)
        app.scale_length_var.set('1.0')
        app.start_automatic_measurement()
        app.current_points = [np.array([50., 50.]), np.array([170., 50.])]
        with patch('measure_wire_cross_section_v5_1.messagebox.showwarning') as warning:
            app.complete_current_step()
            warning.assert_not_called()
        while app.step_index >= 0:
            assert app.pending_review
            app.complete_current_step()
        assert app.summary_rows is not None
        # Diagnostics are explicitly uncalibrated: the ruler here is synthetic.
        Path('outputs').mkdir(exist_ok=True)
        app.ax.set_title('DETECTION CHECK ONLY - synthetic calibration', color='red')
        app.figure.savefig(Path('outputs') / f'detection-{path.stem}.png', dpi=120)
    app.image = Image.new('RGB', (500, 500), 'white')
    app.image_array = np.asarray(app.image)
    app.start_automatic_measurement()
    app.current_points = [np.array([50., 50.]), np.array([150., 50.])]
    with patch('measure_wire_cross_section_v5_1.messagebox.showwarning') as warning:
        app.complete_current_step()
        warning.assert_called_once()
    assert app.pixels_per_mm == 100 and app.step_index == 1
    assert app.current_points == [] and not app.auto_proposals and app.summary_rows is None
    root.destroy()
    print('PASS: synthetic geometry, rejected blank, ruler midpoint and dragging, '
          'automatic proposals, editable points, recalibration, report and both photo fixtures')


if __name__ == '__main__':
    main()
