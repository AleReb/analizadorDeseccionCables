# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Regression: the Tk canvas, renderer and axes must use the same viewport."""
import tkinter as tk
from types import SimpleNamespace
from pathlib import Path

import numpy as np
from PIL import Image
from matplotlib.backend_bases import MouseEvent

from measure_wire_cross_section_v5_1 import WireMeasurementApp


def main():
    root = tk.Tk()
    app = WireMeasurementApp(root)
    # Simulate motions explicitly; real desktop cursor events must not alter the test.
    app.canvas.get_tk_widget().unbind('<Motion>')
    root.geometry('1500x900')
    root.update()
    path = next(Path('.').glob('WhatsApp*.jpeg'))
    app.image = Image.open(path).convert('RGB')
    app.image_array = np.asarray(app.image)
    app.start_measurement()
    root.update()

    def flush():
        root.update()
        app.canvas.draw()

    def check_viewport():
        flush()
        widget = app.canvas.get_tk_widget()
        size = np.array([widget.winfo_width(), widget.winfo_height()])
        np.testing.assert_allclose(app.figure.bbox.size, size, atol=1)
        np.testing.assert_allclose(app.ax.bbox.size, size*.99, atol=2)
        # Circles must remain circular after each resize or zoom.
        origin, x, y = app.ax.transData.transform([[0, 0], [10, 0], [0, 10]])
        assert np.isclose(np.linalg.norm(x-origin), np.linalg.norm(y-origin))
        return size

    initial_size = check_viewport()
    assert app.zoom_var.get() == 100
    initial_width = np.diff(app.ax.get_xlim())[0]
    app.set_image_zoom(200)
    check_viewport()
    assert np.isclose(np.diff(app.ax.get_xlim())[0], initial_width/2)
    assert app.zoom_text_var.get() == '200%'
    center_before = [np.mean(app.ax.get_xlim()), np.mean(app.ax.get_ylim())]
    pixels_per_unit = app.ax.bbox.width/np.diff(app.ax.get_xlim())[0]

    app.toggle_results()
    larger_size = check_viewport()
    assert larger_size[1] > initial_size[1]
    np.testing.assert_allclose(center_before, [np.mean(app.ax.get_xlim()), np.mean(app.ax.get_ylim())])
    assert np.isclose(app.ax.bbox.width/np.diff(app.ax.get_xlim())[0], pixels_per_unit)
    app.toggle_results()
    check_viewport()

    app.view_panes.sashpos(0, 65)
    check_viewport()
    root.geometry('1200x780')
    check_viewport()
    root.geometry('1500x900')
    check_viewport()
    app.fill_image_to_view()
    check_viewport()
    h, w = app.image_array.shape[:2]
    assert np.diff(app.ax.get_xlim())[0] <= w+1
    assert abs(np.diff(app.ax.get_ylim())[0]) <= h+1
    app.fit_image_to_view()
    check_viewport()
    assert np.diff(app.ax.get_xlim())[0] >= w-1
    assert abs(np.diff(app.ax.get_ylim())[0]) >= h-1

    # A wheel zoom preserves the image coordinate under the pointer.
    point = np.array([480., 640.])
    before_pixel = app.ax.transData.transform(point)
    before_zoom = app.zoom_var.get()
    app.on_scroll(SimpleNamespace(inaxes=app.ax, xdata=point[0], ydata=point[1], button='up'))
    check_viewport()
    np.testing.assert_allclose(app.ax.transData.transform(point), before_pixel, atol=1e-7)
    assert np.isclose(app.zoom_var.get(), before_zoom*1.25)

    # Mouse coordinates remain correct with the new, larger renderer.
    event = MouseEvent('button_press_event', app.canvas, *app.ax.transData.transform(point), button=1)
    app.on_mouse_click(event)
    np.testing.assert_allclose(app.current_points[0], point, atol=1e-7)
    app.redraw_completed_geometry()
    app.draw_current_points()
    check_viewport()

    # Panning uses display displacement, avoiding feedback from changed data limits.
    start = app.ax.transData.transform(point)
    event = MouseEvent('button_press_event', app.canvas, *start, button=2)
    app.on_mouse_click(event)
    for dx in (20, 40):
        move = MouseEvent('motion_notify_event', app.canvas, event.x+dx, event.y, button=2)
        app.on_mouse_move(move)
        check_viewport()
        np.testing.assert_allclose(app.ax.transData.transform(point)[0], start[0]+dx, atol=1)
    pending_frame = None
    for dx in range(41, 81):
        move = MouseEvent('motion_notify_event', app.canvas, event.x+dx, event.y, button=2)
        app.on_mouse_move(move)
        if pending_frame is None:
            pending_frame = app._pan_draw_after_id
        assert pending_frame == app._pan_draw_after_id
    app.on_mouse_release(event)
    assert app._pan_draw_after_id is None
    check_viewport()
    np.testing.assert_allclose(app.ax.transData.transform(point)[0], start[0]+80, atol=1)
    root.destroy()
    print('PASS: renderer resize, full viewport, real zoom, table toggle, fit/fill, '
          'aspect ratio, cursor zoom, point placement and panning')


if __name__ == '__main__':
    main()
