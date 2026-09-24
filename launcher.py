# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Desktop entry point and packaged runtime smoke test."""
import sys
from pathlib import Path


def smoke_test(destination):
    import json
    import tkinter as tk
    import numpy as np
    from PIL import Image, ImageDraw
    from automatic_measurement import detect_pairs
    from measure_wire_cross_section_v5_1 import WireMeasurementApp, __version__

    image = Image.new('RGB', (900, 700), (170, 170, 170))
    draw = ImageDraw.Draw(image)
    draw.rectangle((290, 192, 510, 228), fill=(190, 190, 20))
    for x, color in ((290, (20, 180, 60)), (510, (210, 210, 20))):
        draw.ellipse((x-90, 120, x+90, 300), fill=color)
        draw.ellipse((x-36, 174, x+36, 246), fill=(160, 85, 65))
    assert len(detect_pairs(image, 1)) == 1
    root = tk.Tk()
    root.withdraw()
    try:
        app = WireMeasurementApp(root)
        app.image = image
        app.image_array = np.asarray(image)
        app.pair_count_var.set(1)
        app.start_automatic_measurement()
        app.current_points = [np.array([10., 10.]), np.array([110., 10.])]
        app.complete_current_step()
        while app.step_index >= 0:
            assert app.pending_review, 'Missing automatic proposal'
            app.complete_current_step()
        assert app.summary_rows is not None
        report = app.create_report_figure()
        output = Path(destination).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        report.savefig(output.with_suffix('.png'))
        report.savefig(output.with_suffix('.pdf'))
        report.clear()
        output.write_text(json.dumps(dict(status='ok', version=__version__,
                                          platform=sys.platform, frozen=bool(getattr(sys, 'frozen', False)))),
                          encoding='utf-8')
    finally:
        root.destroy()


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--smoke-test':
        try:
            smoke_test(sys.argv[2])
        except Exception:
            import traceback
            Path(sys.argv[2]).with_suffix('.error.txt').write_text(traceback.format_exc(), encoding='utf-8')
            sys.exit(1)
    else:
        from measure_wire_cross_section_v5_1 import main
        main()
