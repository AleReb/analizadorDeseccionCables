# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Run in a desktop session: copper reference and live tab-angle guide."""
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
import numpy as np
from PIL import Image, ImageDraw
from measure_wire_cross_section_v5_1 import WireMeasurementApp, tab_axis_geometry


def main():
    for degrees in (0, 27, 90, 147, 270):
        t = np.radians(degrees)
        rotation = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
        centers = np.array([[-100, 0], [100, 0]]) @ rotation.T + [400, 300]
        for ps, expected in (([[0, -20], [0, 20]], 90),
                             ([[0, 0], [20, 20]], 45), ([[0, 0], [20, 0]], 0)):
            points = np.array(ps) @ rotation.T + [400, 300]
            for ca, cb in (centers, centers[::-1]):
                for ps in (points, points[::-1]):
                    g = tab_axis_geometry(ca, cb, ps)
                    assert abs(g['angle']-expected) < 1e-5
                    assert abs(np.dot(g['axis'], g['normal'])) < 1e-12
        assert tab_axis_geometry(*centers, [])['angle'] is None
        assert tab_axis_geometry(*centers, [[1, 1], [1, 1]])['angle'] is None
    try:
        tab_axis_geometry([1, 1], [1, 1], [])
        raise AssertionError('Coincident centers must not have an angle')
    except ValueError:
        pass
    root = tk.Tk()
    root.withdraw()
    app = WireMeasurementApp(root)
    image = Image.new('RGB', (800, 600), '#253239')
    painter = ImageDraw.Draw(image)
    centers = [np.array([250., 235.]), np.array([550., 365.])]
    axis = centers[1]-centers[0]
    axis /= np.linalg.norm(axis)
    normal = np.array([-axis[1], axis[0]])
    painter.polygon([tuple(p) for p in (centers[0]-normal*20, centers[1]-normal*20,
                                       centers[1]+normal*20, centers[0]+normal*20)], fill='#bec84f')
    for center, color in zip(centers, ('#66af73', '#d3be56')):
        x, y = center
        painter.ellipse((x-100, y-100, x+100, y+100), fill=color)
        painter.ellipse((x-40, y-40, x+40, y+40), fill='#ba8257')
    app.image = image
    app.image_array = np.asarray(image)
    app.pair_count_var.set(1)
    app.points_per_circle_var.set(8)
    app.start_measurement()
    app.current_points = [np.array([10., 10.]), np.array([110., 10.])]
    app.complete_current_step()
    for center in centers:
        for radius in (100, 40):
            app.current_points = [center + radius*np.array([np.cos(t), np.sin(t)])
                                  for t in np.linspace(0, 2*np.pi, 8, endpoint=False)]
            app.complete_current_step()
    assert app.steps[app.step_index]['kind'] == 'tab'
    def angle_text():
        return next(a.get_text() for a in app.preview_artists if hasattr(a, 'get_text'))
    assert '90° guide' in angle_text()
    # The reference must ignore eccentric outer insulation centers.
    app.lobes[0]['outer_center'] += [30, -15]
    midpoint = np.mean(centers, axis=0)
    app.current_points = [midpoint-20*normal, midpoint+20*normal]
    original = np.array(app.current_points)
    app.draw_current_points()
    assert '90.00°' in angle_text()
    assert np.array_equal(original, app.current_points)
    artist_count = len(app.preview_artists)
    axes_count = len(app.ax.lines)
    for _ in range(10):
        app.draw_current_points()
    assert len(app.preview_artists) == artist_count and len(app.ax.lines) == axes_count
    app.point_drag = 1
    endpoint = original[1] + 20*axis
    app.on_mouse_move(SimpleNamespace(inaxes=app.ax, xdata=endpoint[0], ydata=endpoint[1]))
    assert '63.43°' in angle_text() and '26.57°' in angle_text()
    app.point_drag = None
    app.canvas.draw()
    Path('outputs').mkdir(exist_ok=True)
    app.figure.savefig('outputs/tab-angle-guide.png', dpi=120)
    app.complete_current_step()
    assert not app.preview_artists
    assert abs(app.pair_results[0]['tab_mm']-np.sqrt(40**2+20**2)/app.pixels_per_mm) < 1e-10
    app.undo_point()
    assert app.steps[app.step_index]['kind'] == 'tab' and '90° guide' in angle_text()
    root.destroy()
    print('PASS: rotated copper reference, live angle, unchanged distance and preview cleanup')


if __name__ == '__main__':
    main()
