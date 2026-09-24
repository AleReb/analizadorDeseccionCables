# SPDX-License-Identifier: CERN-OHL-S-2.0
import tkinter as tk
from types import SimpleNamespace
import numpy as np
from PIL import Image
from matplotlib.backend_bases import MouseEvent
from measure_wire_cross_section_v5_1 import WireMeasurementApp

def main():
    root = tk.Tk()
    root.withdraw()
    app = WireMeasurementApp(root)
    app.image = Image.new('RGB', (800, 600), 'white')
    app.image_array = np.asarray(app.image)
    app.pair_count_var.set(3)
    app.points_per_circle_var.set(4)
    app.start_measurement()

    def complete():
        step = app.steps[app.step_index]
        if step['kind'] == 'ruler':
            points = [[10,10], [110,10]]
        elif step['kind'] == 'tab':
            points = [[100,100], [110,100]]
        else:
            center = np.array([150 + (step['lobe'] % 2) * 170, 150 + step['pair'] * 150])
            radius = 70 if step['kind'] == 'outer' else 30
            points = [center + radius * np.array([np.cos(t),np.sin(t)]) for t in np.linspace(0,2*np.pi,4,endpoint=False)]
        app.current_points = [np.array(p,dtype=float) for p in points]
        app.complete_current_step()

    for _ in range(6): complete()
    assert app.step_index == 6 and app.pair_results[0] is not None
    app.canvas.draw()
    key = 'PAIR0_WIDTH'
    a = app.live_annotations[key]
    box = a.get_bbox_patch().get_window_extent()
    event = MouseEvent('button_press_event', app.canvas, *box.get_points().mean(axis=0), button=1)
    app.on_mouse_click(event)
    assert app.label_drag is not None
    app.on_mouse_move(SimpleNamespace(x=event.x+40,y=event.y+20))
    app.on_mouse_release(event)
    assert not app.current_points
    position = a.get_position()
    complete()
    assert app.live_annotations[key].get_position() == position
    app.undo_last_closure()
    assert app.step_index == 6 and len(app.current_points) == 3 and app.lobes[2] is None
    assert app.pair_results[0] is not None
    complete()
    while app.step_index >= 0: complete()
    assert app.summary_rows is not None
    app.undo_point()
    assert app.step_index == len(app.steps)-1 and len(app.current_points) == 1
    assert app.pair_results[-1] is None and app.summary_rows is None
    complete()
    assert app.summary_rows is not None
    while app.step_history: app.undo_last_closure()
    assert app.step_index == 0 and app.pixels_per_mm is None and len(app.current_points)==1
    root.deiconify()
    root.update()
    height_before = app.canvas.get_tk_widget().winfo_height()
    app.toggle_results()
    root.update()
    assert app.canvas.get_tk_widget().winfo_height() > height_before
    app.toggle_results()
    root.update()
    root.destroy()
    print('PASS: three-pair workflow, live label dragging and position persistence, undo circles/final closure/calibration, expanded image viewport')


if __name__ == "__main__":
    main()
