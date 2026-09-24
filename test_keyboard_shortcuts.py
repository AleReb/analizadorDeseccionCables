# SPDX-License-Identifier: CERN-OHL-S-2.0
import tkinter as tk
from unittest.mock import patch

import numpy as np
from PIL import Image

from measure_wire_cross_section_v5_1 import WireMeasurementApp


def main():
    root = tk.Tk()
    app = WireMeasurementApp(root)
    root.update()
    app.image = Image.new('RGB', (800, 600), 'white')
    app.image_array = np.asarray(app.image)
    app.start_measurement()
    app.current_points = [np.array([100., 100.]), np.array([200., 100.])]
    app.draw_current_points()

    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    name = next(w for w in descendants(root) if w.winfo_class() == 'TEntry'
                and str(w.cget('textvariable')) == str(app.output_name_var))

    def key(widget, sequence):
        widget.focus_force()
        root.update()
        widget.event_generate(sequence)
        root.update()

    app.output_name_var.set('sample')
    name.icursor(tk.END)
    key(name, '<BackSpace>')
    assert app.output_name_var.get() == 'sampl'
    assert app.step_index == 0 and len(app.current_points) == 2
    key(name, '<space>')
    assert app.output_name_var.get() == 'sampl '
    assert app.step_index == 0
    with patch.object(app, 'cancel_measurement') as cancel:
        app._bind_shortcuts()
        key(name, '<Escape>')
        cancel.assert_not_called()
    app._bind_shortcuts()

    canvas = app.canvas.get_tk_widget()
    key(canvas, '<space>')
    assert app.step_index == 1 and len(app.step_history) == 1
    key(canvas, '<space>')  # Incomplete step must not advance.
    assert app.step_index == 1
    app.output_name_var.set('new report')
    name.icursor(tk.END)
    for _ in range(5):
        key(name, '<BackSpace>')
    assert app.step_index == 1 and len(app.step_history) == 1
    assert app.pixels_per_mm == 100
    key(name, '<Control-z>')
    assert len(app.step_history) == 1
    key(canvas, '<BackSpace>')
    assert app.step_index == 0 and len(app.current_points) == 1
    root.destroy()
    print('PASS: space accepts only ready steps; name editing preserves points, history and calibration')


if __name__ == '__main__':
    main()
