# SPDX-License-Identifier: CERN-OHL-S-2.0
# Modified 2026-09-24: editable automatic proposals, ruler verification and measurement review.
import csv
import math
from copy import deepcopy
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib
matplotlib.use("TkAgg", force=True)

import numpy as np
from PIL import Image

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.patches import Circle


# ============================================================
# DEFAULTS
# ============================================================

__version__ = "5.3.1"

DEFAULT_REQUIREMENTS = {
    "Width (mm)": ("none",),
    "Height 1 (mm)": ("nominal_tol", 1.45, 0.05),
    "Height 2 (mm)": ("nominal_tol", 1.45, 0.05),
    "Conductor spacing (mm)": ("nominal_tol", 1.70, 0.10),
    "Tab (mm)": ("max", 0.30),
    "Minimum thickness (mm)": ("min", 0.35),
    "Conductor diameter (mm)": ("nominal_tol", 0.60, 0.006),
}

SUMMARY_ORDER = [
    "Width (mm)",
    "Height 1 (mm)",
    "Height 2 (mm)",
    "Conductor spacing (mm)",
    "Tab (mm)",
    "Minimum thickness (mm)",
    "Conductor diameter (mm)",
]


# ============================================================
# GEOMETRY / REQUIREMENTS
# ============================================================

def fit_circle(points):
    points = np.asarray(points, dtype=float)
    x = points[:, 0]
    y = points[:, 1]

    matrix = np.column_stack((2.0 * x, 2.0 * y, np.ones_like(x)))
    vector = x**2 + y**2

    solution, _, _, _ = np.linalg.lstsq(matrix, vector, rcond=None)
    center_x, center_y, constant = solution
    radius = math.sqrt(max(0.0, constant + center_x**2 + center_y**2))
    center = np.array([center_x, center_y], dtype=float)

    distances = np.linalg.norm(points - center, axis=1)
    rmse_px = float(np.sqrt(np.mean((distances - radius) ** 2)))

    return center, float(radius), rmse_px


def distance_pixels(point_a, point_b):
    return float(np.linalg.norm(np.asarray(point_b) - np.asarray(point_a)))


def distance_mm(point_a, point_b, pixels_per_mm):
    return distance_pixels(point_a, point_b) / pixels_per_mm


def minimum_thickness_mm(
    outer_center,
    outer_radius,
    conductor_center,
    conductor_radius,
    pixels_per_mm,
):
    eccentricity_px = float(
        np.linalg.norm(np.asarray(outer_center) - np.asarray(conductor_center))
    )
    thickness_px = outer_radius - conductor_radius - eccentricity_px
    return float(thickness_px / pixels_per_mm)


def projected_pair_width_mm(
    outer_center_a,
    outer_radius_a,
    outer_center_b,
    outer_radius_b,
    axis,
    pixels_per_mm,
):
    axis = np.asarray(axis, dtype=float)
    axis_norm = np.linalg.norm(axis)

    if axis_norm <= 0:
        return float("nan")

    axis = axis / axis_norm

    projection_a = float(np.dot(outer_center_a, axis))
    projection_b = float(np.dot(outer_center_b, axis))

    minimum_projection = min(
        projection_a - outer_radius_a,
        projection_b - outer_radius_b,
    )
    maximum_projection = max(
        projection_a + outer_radius_a,
        projection_b + outer_radius_b,
    )

    return float((maximum_projection - minimum_projection) / pixels_per_mm)


def format_requirement(requirement):
    if requirement is None:
        return "-"

    kind = requirement[0]

    if kind == "none":
        return "-"
    if kind == "nominal_tol":
        nominal = float(requirement[1])
        tolerance = float(requirement[2])
        return f"{nominal:.3f} ± {tolerance:.3f}"
    if kind == "min":
        return f"≥ {float(requirement[1]):.3f}"
    if kind == "max":
        return f"≤ {float(requirement[1]):.3f}"

    return str(requirement)


def check_requirement(value, requirement):
    if requirement is None:
        return "N/A"

    if value is None or not np.isfinite(value):
        return "N/A"

    kind = requirement[0]

    if kind == "none":
        return "N/A"

    if kind == "nominal_tol":
        nominal = float(requirement[1])
        tolerance = float(requirement[2])
        return "OK" if nominal - tolerance <= value <= nominal + tolerance else "FAIL"

    if kind == "min":
        return "OK" if value >= float(requirement[1]) else "FAIL"

    if kind == "max":
        return "OK" if value <= float(requirement[1]) else "FAIL"

    return "N/A"


def safe_stats(values):
    clean = [float(v) for v in values if v is not None and np.isfinite(v)]
    if not clean:
        return float("nan"), float("nan"), float("nan")
    return min(clean), max(clean), float(np.mean(clean))


def status_color(status):
    return "red" if status == "FAIL" else "black"


# ============================================================
# REQUIREMENTS DIALOG
# ============================================================

class RequirementsDialog(tk.Toplevel):
    def __init__(self, master, requirements):
        super().__init__(master)
        self.title("Edit Requirements")
        self.transient(master)
        self.grab_set()
        self.resizable(True, True)

        self.result = None
        self.rows = {}

        main = ttk.Frame(self, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(main)
        header.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(
            header,
            text="Edit requirement mode and values. Use 'none' to disable a requirement.",
        ).pack(side=tk.LEFT)

        grid = ttk.Frame(main)
        grid.pack(fill=tk.BOTH, expand=True)

        labels = ["Dimension", "Mode", "Value 1", "Value 2"]
        widths = [24, 14, 14, 14]

        for col, (label, width) in enumerate(zip(labels, widths)):
            ttk.Label(grid, text=label, width=width, anchor="center").grid(
                row=0, column=col, padx=4, pady=4, sticky="ew"
            )

        for row_idx, dimension in enumerate(SUMMARY_ORDER, start=1):
            ttk.Label(grid, text=dimension).grid(
                row=row_idx, column=0, padx=4, pady=4, sticky="w"
            )

            current = requirements.get(dimension, ("none",))
            mode_var = tk.StringVar(value=current[0])

            combo = ttk.Combobox(
                grid,
                textvariable=mode_var,
                values=["none", "nominal_tol", "min", "max"],
                state="readonly",
                width=12,
            )
            combo.grid(row=row_idx, column=1, padx=4, pady=4, sticky="ew")

            value1_var = tk.StringVar()
            value2_var = tk.StringVar()

            if current[0] == "nominal_tol":
                value1_var.set(str(current[1]))
                value2_var.set(str(current[2]))
            elif current[0] in ("min", "max"):
                value1_var.set(str(current[1]))
                value2_var.set("")
            else:
                value1_var.set("")
                value2_var.set("")

            entry1 = ttk.Entry(grid, textvariable=value1_var, width=14)
            entry2 = ttk.Entry(grid, textvariable=value2_var, width=14)

            entry1.grid(row=row_idx, column=2, padx=4, pady=4, sticky="ew")
            entry2.grid(row=row_idx, column=3, padx=4, pady=4, sticky="ew")

            self.rows[dimension] = {
                "mode_var": mode_var,
                "value1_var": value1_var,
                "value2_var": value2_var,
            }

        buttons = ttk.Frame(main)
        buttons.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(buttons, text="Reset Defaults", command=self.reset_defaults).pack(
            side=tk.LEFT
        )
        ttk.Button(buttons, text="Cancel", command=self.on_cancel).pack(
            side=tk.RIGHT, padx=(4, 0)
        )
        ttk.Button(buttons, text="Apply", command=self.on_apply).pack(side=tk.RIGHT)

        self.bind("<Return>", lambda event: self.on_apply())
        self.bind("<Escape>", lambda event: self.on_cancel())

    def reset_defaults(self):
        for dimension, requirement in DEFAULT_REQUIREMENTS.items():
            row = self.rows[dimension]
            row["mode_var"].set(requirement[0])

            if requirement[0] == "nominal_tol":
                row["value1_var"].set(str(requirement[1]))
                row["value2_var"].set(str(requirement[2]))
            elif requirement[0] in ("min", "max"):
                row["value1_var"].set(str(requirement[1]))
                row["value2_var"].set("")
            else:
                row["value1_var"].set("")
                row["value2_var"].set("")

    def on_cancel(self):
        self.result = None
        self.destroy()

    def on_apply(self):
        parsed = {}

        try:
            for dimension in SUMMARY_ORDER:
                row = self.rows[dimension]
                mode = row["mode_var"].get()

                if mode == "none":
                    parsed[dimension] = ("none",)
                    continue

                value1 = float(row["value1_var"].get().replace(",", "."))
                if mode == "nominal_tol":
                    value2 = float(row["value2_var"].get().replace(",", "."))
                    parsed[dimension] = ("nominal_tol", value1, value2)
                elif mode == "min":
                    parsed[dimension] = ("min", value1)
                elif mode == "max":
                    parsed[dimension] = ("max", value1)
                else:
                    raise ValueError(f"Unsupported mode: {mode}")

        except Exception as exc:
            messagebox.showerror(
                "Invalid Requirement",
                f"Please review the values.\n\n{exc}",
                parent=self,
            )
            return

        self.result = parsed
        self.destroy()


# ============================================================
# APPLICATION
# ============================================================

class WireMeasurementApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"M35 Wire Cross-Section Measurement - v{__version__}")
        self.root.geometry("1520x930")
        self.root.minsize(1120, 760)

        self.image_path = None
        self.image = None
        self.image_array = None

        self.requirements = deepcopy(DEFAULT_REQUIREMENTS)

        self.step_history = []
        self.label_drag = None
        self.point_drag = None
        self.pending_review = False
        self.auto_requested = False
        self.auto_proposals = {}
        self.accepted_points = {}
        self.session_setup = None
        self.steps = []
        self.step_index = -1
        self.current_points = []

        self.ruler_points = None
        self.pixels_per_mm = None
        self.mm_per_pixel = None

        self.lobes = []
        self.tabs = []
        self.pair_results = []
        self.summary_rows = None

        self.preview_artists = []
        self.result_artists = []

        self.live_annotations = {}
        self.annotation_offsets = {}

        self.is_panning = False
        self.pan_start_xy = None
        self.pan_start_xlim = None
        self.pan_start_ylim = None

        self.auto_fit_var = tk.BooleanVar(value=False)
        self._resize_after_id = None

        self.scale_length_var = tk.StringVar(value="1.000")
        self.points_per_circle_var = tk.IntVar(value=8)
        self.pair_count_var = tk.IntVar(value=2)
        self.output_name_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Open an image to begin.")
        self.calibration_var = tk.StringVar(value="Calibration: not set")

        self._build_ui()
        self._bind_shortcuts()

    # --------------------------------------------------------
    # UI
    # --------------------------------------------------------

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=8)
        main.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(main)
        controls.pack(fill=tk.X, pady=(0, 6))

        ttk.Button(controls, text="Open Image", command=self.open_image).pack(
            side=tk.LEFT, padx=(0, 4)
        )

        self.start_button = ttk.Button(
            controls,
            text="Start / Restart Measurement",
            command=self.start_measurement,
            state=tk.DISABLED,
        )
        self.start_button.pack(side=tk.LEFT, padx=4)

        self.undo_button = ttk.Button(
            controls,
            text="Undo Point",
            command=self.undo_point,
            state=tk.DISABLED,
        )
        self.undo_button.pack(side=tk.LEFT, padx=4)

        self.fit_button = ttk.Button(
            controls,
            text="Fit to Window",
            command=self.fit_image_to_view,
            state=tk.DISABLED,
        )
        self.fit_button.pack(side=tk.LEFT, padx=4)

        ttk.Checkbutton(
            controls,
            text="Auto Fit on Resize",
            variable=self.auto_fit_var,
        ).pack(side=tk.LEFT, padx=(2, 6))

        self.save_button = ttk.Button(
            controls,
            text="Save Report",
            command=self.save_report,
            state=tk.DISABLED,
        )
        self.save_button.pack(side=tk.LEFT, padx=4)

        self.csv_button = ttk.Button(
            controls,
            text="Export CSV",
            command=self.export_csv,
            state=tk.DISABLED,
        )
        self.csv_button.pack(side=tk.LEFT, padx=4)

        ttk.Button(
            controls,
            text="Edit Requirements",
            command=self.edit_requirements,
        ).pack(side=tk.LEFT, padx=(8, 4))

        ttk.Separator(controls, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=8
        )

        ttk.Label(controls, text="Pairs:").pack(side=tk.LEFT)
        ttk.Spinbox(
            controls,
            from_=1,
            to=12,
            increment=1,
            width=5,
            textvariable=self.pair_count_var,
        ).pack(side=tk.LEFT, padx=(4, 10))

        ttk.Label(controls, text="Ruler length (mm):").pack(side=tk.LEFT)
        ttk.Entry(
            controls,
            textvariable=self.scale_length_var,
            width=8,
        ).pack(side=tk.LEFT, padx=(4, 10))

        ttk.Label(controls, text="Circle points:").pack(side=tk.LEFT)
        ttk.Spinbox(
            controls,
            from_=4,
            to=20,
            increment=1,
            width=5,
            textvariable=self.points_per_circle_var,
        ).pack(side=tk.LEFT, padx=(4, 8))

        ttk.Label(controls, text="Output name:").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Entry(
            controls,
            textvariable=self.output_name_var,
            width=18,
        ).pack(side=tk.LEFT, padx=(4, 8))

        ttk.Label(controls, textvariable=self.calibration_var).pack(
            side=tk.RIGHT, padx=(10, 0)
        )

        view_controls = ttk.Frame(main)
        view_controls.pack(fill=tk.X, pady=(0, 6))
        self.undo_step_button = ttk.Button(
            view_controls, text="Undo Last Closure", command=self.undo_last_closure,
            state=tk.DISABLED,
        )
        self.undo_step_button.pack(side=tk.LEFT, padx=(0, 16))
        self.auto_button = ttk.Button(view_controls, text="Auto Measure",
                                      command=self.start_automatic_measurement)
        self.auto_button.pack(side=tk.LEFT, padx=4)
        self.accept_button = ttk.Button(view_controls, text="Accept Step",
                                        command=self.complete_current_step, state=tk.DISABLED)
        self.accept_button.pack(side=tk.LEFT, padx=4)
        self.manual_step_button = ttk.Button(view_controls, text="Redraw Step",
                                             command=self.redraw_step_manually, state=tk.DISABLED)
        self.manual_step_button.pack(side=tk.LEFT, padx=4)
        ttk.Label(view_controls, text="Image area:").pack(side=tk.LEFT)
        self.image_area_var = tk.DoubleVar(value=75)
        ttk.Scale(view_controls, from_=40, to=95, variable=self.image_area_var,
                  command=self.resize_image_area).pack(side=tk.LEFT, fill=tk.X, expand=True)

        review_controls = ttk.Frame(main)
        review_controls.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(review_controls, text="Correct measurement:").pack(side=tk.LEFT)
        self.edit_step_combo = ttk.Combobox(review_controls, state="readonly", width=65)
        self.edit_step_combo.pack(side=tk.LEFT, padx=4)
        self.edit_step_button = ttk.Button(review_controls, text="Edit Selected",
                                           command=self.edit_selected_step, state=tk.DISABLED)
        self.edit_step_button.pack(side=tk.LEFT, padx=4)
        ttk.Label(review_controls, text="Drag control points, then Accept Step. Ruler midpoint = half the entered length.").pack(side=tk.LEFT, padx=8)

        self.view_panes = ttk.Panedwindow(main, orient=tk.VERTICAL)
        self.view_panes.pack(fill=tk.BOTH, expand=True)
        table_frame = ttk.LabelFrame(self.view_panes, text="Dimensional Results")
        self.view_panes.add(table_frame, weight=0)

        columns = ("dimension", "min", "max", "average", "requirement", "status")
        self.results_tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=7,
        )

        headings = {
            "dimension": "Dimension",
            "min": "Min",
            "max": "Max",
            "average": "Average",
            "requirement": "Requirement",
            "status": "Status",
        }

        widths = {
            "dimension": 220,
            "min": 105,
            "max": 105,
            "average": 105,
            "requirement": 170,
            "status": 80,
        }

        for column in columns:
            self.results_tree.heading(column, text=headings[column])
            self.results_tree.column(column, width=widths[column], anchor=tk.CENTER)

        self.results_tree.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._populate_empty_table()

        # Status line
        image_panel = ttk.Frame(self.view_panes)
        self.view_panes.add(image_panel, weight=1)
        status_frame = ttk.Frame(image_panel)
        status_frame.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(
            status_frame,
            textvariable=self.status_var,
            anchor=tk.W,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Label(
            status_frame,
            text="Wheel: zoom | Middle/Shift+Left: move | F: fit | Left: point | Right: undo | Labels: drag | Ctrl+Z: undo closure",
            anchor=tk.E,
        ).pack(side=tk.RIGHT)

        # Matplotlib area
        canvas_frame = ttk.Frame(image_panel)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.figure = Figure(figsize=(10, 7), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.ax.axis("off")

        self.canvas = FigureCanvasTkAgg(self.figure, master=canvas_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.toolbar = NavigationToolbar2Tk(
            self.canvas,
            canvas_frame,
            pack_toolbar=False,
        )
        self.toolbar.update()
        self.toolbar.pack(fill=tk.X)

        self.canvas.mpl_connect("button_press_event", self.on_mouse_click)
        self.canvas.mpl_connect("button_release_event", self.on_mouse_release)
        self.canvas.mpl_connect("scroll_event", self.on_scroll)
        self.canvas.mpl_connect("motion_notify_event", self.on_mouse_move)

        self.canvas.get_tk_widget().bind("<Configure>", self.on_canvas_resize)

    def resize_image_area(self, value):
        height = self.view_panes.winfo_height()
        if height > 1:
            self.view_panes.sashpos(0, int(height * (1 - float(value) / 100)))

    def _bind_shortcuts(self):
        self.root.bind("<Control-z>", lambda event: self.undo_last_closure())
        self.root.bind("<Control-o>", lambda event: self.open_image())
        self.root.bind("<Control-s>", lambda event: self.save_report())
        self.root.bind("<BackSpace>", lambda event: self.undo_point())
        self.root.bind("<Escape>", lambda event: self.cancel_measurement())
        self.root.bind("<f>", lambda event: self.fit_image_to_view())
        self.root.bind("<F>", lambda event: self.fit_image_to_view())

    def _populate_empty_table(self):
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

        for name in SUMMARY_ORDER:
            self.results_tree.insert(
                "",
                tk.END,
                values=(
                    name,
                    "-",
                    "-",
                    "-",
                    format_requirement(self.requirements[name]),
                    "-",
                ),
            )

    def edit_requirements(self):
        dialog = RequirementsDialog(self.root, deepcopy(self.requirements))
        self.root.wait_window(dialog)

        if dialog.result is not None:
            self.requirements = dialog.result
            if self.summary_rows is None:
                self._populate_empty_table()
            else:
                self.calculate_results()
                self.populate_results_table()
                self.redraw_completed_geometry(show_labels=True)
            self.status_var.set("Requirements updated.")

    def get_output_base_name(self):
        """
        Return a filesystem-safe base name for PNG/PDF/JPG and CSV exports.

        If the user does not change the field, the image filename (without its
        extension) is used automatically.
        """
        name = self.output_name_var.get().strip()

        if not name:
            if self.image_path:
                name = self.image_path.stem
            else:
                name = "wire_measurement"

        invalid_characters = '<>:"/\\|?*'
        for character in invalid_characters:
            name = name.replace(character, "_")

        name = name.rstrip(". ")

        if not name:
            name = "wire_measurement"

        return name

    # --------------------------------------------------------
    # FILES
    # --------------------------------------------------------

    def open_image(self):
        filename = filedialog.askopenfilename(
            title="Open wire cross-section image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"),
                ("All files", "*.*"),
            ],
        )

        if not filename:
            return

        try:
            pil_image = Image.open(filename).convert("RGB")
        except Exception as exc:
            messagebox.showerror("Open Image", f"Could not open image:\n{exc}")
            return

        self.image_path = Path(filename)
        self.image = pil_image
        self.image_array = np.asarray(pil_image)

        # Default export name = original image filename without extension.
        # The user can edit this field at any time.
        self.output_name_var.set(self.image_path.stem)

        self.reset_measurement_state()
        self.show_image()

        self.start_button.config(state=tk.NORMAL)
        self.fit_button.config(state=tk.NORMAL)
        self.status_var.set(
            f"Loaded: {self.image_path.name}. Set Pairs and Requirements, then press Start."
        )

    def save_report(self):
        if self.summary_rows is None or self.image is None:
            messagebox.showinfo("Save Report", "Complete a measurement first.")
            return

        initial_name = f"{self.get_output_base_name()}.png"

        filename = filedialog.asksaveasfilename(
            title="Save annotated report",
            defaultextension=".png",
            initialfile=initial_name,
            filetypes=[
                ("PNG image", "*.png"),
                ("JPEG image", "*.jpg"),
                ("PDF document", "*.pdf"),
            ],
        )

        if not filename:
            return

        try:
            report_figure = self.create_report_figure()
            report_figure.savefig(filename, dpi=220, bbox_inches="tight")
            report_figure.clear()
            self.status_var.set(f"Report saved: {filename}")
        except Exception as exc:
            messagebox.showerror("Save Report", f"Could not save report:\n{exc}")

    def export_csv(self):
        if self.summary_rows is None:
            messagebox.showinfo("Export CSV", "Complete a measurement first.")
            return

        initial_name = f"{self.get_output_base_name()}.csv"

        filename = filedialog.asksaveasfilename(
            title="Export measurements to CSV",
            defaultextension=".csv",
            initialfile=initial_name,
            filetypes=[("CSV file", "*.csv")],
        )

        if not filename:
            return

        try:
            with open(filename, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)

                writer.writerow(["SETUP"])
                writer.writerow(["Pairs", self.get_pair_count()])
                writer.writerow(["Circle points", self.get_points_per_circle()])
                writer.writerow(["Ruler length (mm)", self.get_scale_length_mm()])
                writer.writerow(["Pixels per mm", self.pixels_per_mm])
                writer.writerow(["mm per pixel", self.mm_per_pixel])

                writer.writerow([])
                writer.writerow(["REQUIREMENTS"])
                writer.writerow(["Dimension", "Mode", "Value 1", "Value 2"])
                for dimension in SUMMARY_ORDER:
                    req = self.requirements[dimension]
                    if req[0] == "nominal_tol":
                        writer.writerow([dimension, req[0], req[1], req[2]])
                    elif req[0] in ("min", "max"):
                        writer.writerow([dimension, req[0], req[1], ""])
                    else:
                        writer.writerow([dimension, req[0], "", ""])

                writer.writerow([])
                writer.writerow(["SUMMARY"])
                writer.writerow(
                    ["Dimension", "Min", "Max", "Average", "Requirement", "Status"]
                )

                for row in self.summary_rows:
                    writer.writerow(
                        [
                            row["dimension"],
                            row["min"],
                            row["max"],
                            row["average"],
                            row["requirement"],
                            row["status"],
                        ]
                    )

                writer.writerow([])
                writer.writerow(["LOBE DETAILS"])
                writer.writerow(
                    [
                        "Pair",
                        "Side",
                        "Outer diameter (mm)",
                        "Conductor diameter (mm)",
                        "Minimum thickness (mm)",
                        "Outer fit RMSE (px)",
                        "Conductor fit RMSE (px)",
                    ]
                )

                for pair_index in range(self.get_pair_count()):
                    for side in range(2):
                        lobe = self.lobes[2 * pair_index + side]
                        writer.writerow(
                            [
                                pair_index + 1,
                                side + 1,
                                lobe["outer_diameter_mm"],
                                lobe["conductor_diameter_mm"],
                                lobe["minimum_thickness_mm"],
                                lobe["outer_rmse_px"],
                                lobe["conductor_rmse_px"],
                            ]
                        )

                writer.writerow([])
                writer.writerow(["PAIR DETAILS"])
                writer.writerow(
                    [
                        "Pair",
                        "Width (mm)",
                        "Height 1 (mm)",
                        "Height 2 (mm)",
                        "Conductor spacing (mm)",
                        "Tab (mm)",
                    ]
                )

                for pair in self.pair_results:
                    if pair is None:
                        continue

                    writer.writerow(
                        [
                            pair["name"],
                            pair["width_mm"],
                            pair["height_1_mm"],
                            pair["height_2_mm"],
                            pair["conductor_spacing_mm"],
                            pair["tab_mm"],
                        ]
                    )

            self.status_var.set(f"CSV exported: {filename}")
        except Exception as exc:
            messagebox.showerror("Export CSV", f"Could not export CSV:\n{exc}")

    # --------------------------------------------------------
    # WORKFLOW
    # --------------------------------------------------------

    def get_pair_count(self):
        if self.session_setup is not None:
            return self.session_setup["pairs"]
        value = int(self.pair_count_var.get())
        if value < 1:
            raise ValueError("Pairs must be at least 1.")
        return value

    def get_points_per_circle(self):
        if self.session_setup is not None:
            return self.session_setup["circle_points"]
        value = int(self.points_per_circle_var.get())
        if value < 4:
            raise ValueError("Circle points must be at least 4.")
        return value

    def _build_steps(self):
        pair_count = self.get_pair_count()
        count = self.get_points_per_circle()

        steps = [
            {
                "kind": "ruler",
                "label": "Calibration: click the two endpoints of the ruler",
                "count": 2,
            }
        ]

        for pair_index in range(pair_count):
            pair_name = f"Pair {pair_index + 1}"

            steps.extend(
                [
                    {
                        "kind": "outer",
                        "lobe": 2 * pair_index,
                        "pair": pair_index,
                        "side": 1,
                        "label": f"{pair_name} - Side 1: click points around the OUTER insulation boundary",
                        "count": count,
                    },
                    {
                        "kind": "conductor",
                        "lobe": 2 * pair_index,
                        "pair": pair_index,
                        "side": 1,
                        "label": f"{pair_name} - Side 1: click points around the COPPER conductor boundary",
                        "count": count,
                    },
                    {
                        "kind": "outer",
                        "lobe": 2 * pair_index + 1,
                        "pair": pair_index,
                        "side": 2,
                        "label": f"{pair_name} - Side 2: click points around the OUTER insulation boundary",
                        "count": count,
                    },
                    {
                        "kind": "conductor",
                        "lobe": 2 * pair_index + 1,
                        "pair": pair_index,
                        "side": 2,
                        "label": f"{pair_name} - Side 2: click points around the COPPER conductor boundary",
                        "count": count,
                    },
                    {
                        "kind": "tab",
                        "pair": pair_index,
                        "label": f"{pair_name}: click the two endpoints of the CENTRAL TAB thickness",
                        "count": 2,
                    },
                ]
            )

        self.steps = steps

    def start_measurement(self):
        if self.image is None:
            messagebox.showinfo("Measurement", "Open an image first.")
            return

        try:
            scale_length = float(self.scale_length_var.get().replace(",", "."))
            pair_count = int(self.pair_count_var.get())
            points_per_circle = int(self.points_per_circle_var.get())
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror("Invalid Setup", str(exc))
            return

        if not np.isfinite(scale_length) or scale_length <= 0:
            messagebox.showerror("Invalid Scale", "Ruler length must be greater than zero.")
            return
        if pair_count <= 0:
            messagebox.showerror("Invalid Pair Count", "Pairs must be at least 1.")
            return
        if points_per_circle < 4:
            messagebox.showerror("Invalid Point Count", "Circle points must be at least 4.")
            return

        self.reset_measurement_state(keep_image=True)
        self.session_setup = dict(pairs=pair_count, circle_points=points_per_circle,
                                  scale_length=scale_length)

        self.lobes = [None for _ in range(2 * pair_count)]
        self.tabs = [None for _ in range(pair_count)]
        self.pair_results = [None for _ in range(pair_count)]

        self._build_steps()

        self.step_index = 0
        self.undo_button.config(state=tk.NORMAL)
        self.save_button.config(state=tk.DISABLED)
        self.csv_button.config(state=tk.DISABLED)

        self.show_image()
        self.update_step_status()
        return True

    def cancel_measurement(self):
        if self.step_index >= 0:
            self.step_index = -1
            self.current_points = []
            self.pending_review = False
            self.point_drag = None
            self.auto_requested = False
            self.accept_button.config(state=tk.DISABLED)
            self.manual_step_button.config(state=tk.DISABLED)
            self.clear_preview_artists()
            self.status_var.set("Measurement cancelled. Existing completed results are unchanged.")
            self.canvas.draw_idle()

    def reset_measurement_state(self, keep_image=False):
        self.step_history = []
        self.label_drag = None
        self.point_drag = None
        self.pending_review = False
        self.auto_requested = False
        self.auto_proposals = {}
        self.accepted_points = {}
        self.session_setup = None
        self.accept_button.config(state=tk.DISABLED)
        self.manual_step_button.config(state=tk.DISABLED)
        self.edit_step_button.config(state=tk.DISABLED)
        self.edit_step_combo.config(values=())
        self.edit_step_combo.set("")
        self.steps = []
        self.step_index = -1
        self.current_points = []

        self.ruler_points = None
        self.pixels_per_mm = None
        self.mm_per_pixel = None

        self.lobes = []
        self.tabs = []
        self.pair_results = []
        self.summary_rows = None

        self.is_panning = False
        self.pan_start_xy = None
        self.pan_start_xlim = None
        self.pan_start_ylim = None

        if self._resize_after_id is not None:
            try:
                self.root.after_cancel(self._resize_after_id)
            except Exception:
                pass
            self._resize_after_id = None

        self.clear_preview_artists()
        self.clear_result_artists()
        self.annotation_offsets = {}

        self.calibration_var.set("Calibration: not set")
        self._populate_empty_table()

        self.undo_button.config(state=tk.DISABLED)
        self.undo_step_button.config(state=tk.DISABLED)
        self.save_button.config(state=tk.DISABLED)
        self.csv_button.config(state=tk.DISABLED)

        if not keep_image:
            self.start_button.config(state=tk.DISABLED)
            self.fit_button.config(state=tk.DISABLED)

    def get_scale_length_mm(self):
        if self.session_setup is not None:
            return self.session_setup["scale_length"]
        try:
            return float(self.scale_length_var.get().replace(",", "."))
        except ValueError as exc:
            raise ValueError("Ruler length must be a valid number.") from exc

    def update_step_status(self):
        if self.step_index < 0 or self.step_index >= len(self.steps):
            return

        step = self.steps[self.step_index]
        needed = step["count"]
        current = len(self.current_points)

        self.status_var.set(
            f"Step {self.step_index + 1}/{len(self.steps)} — "
            f"{step['label']} — points {current}/{needed}"
            + (" — Drag points to adjust, then Accept Step." if self.pending_review else "")
            + (" Verify the conductor boundary: reflections/cavities can affect detection."
               if self.pending_review and step["kind"] == "conductor"
               and self.step_index in self.auto_proposals else "")
        )

    # --------------------------------------------------------
    # INTERACTION
    # --------------------------------------------------------

    def start_automatic_measurement(self):
        if self.start_measurement():
            self.auto_requested = True
            self.status_var.set("Automatic mode: mark the ruler endpoints, check the midpoint and Accept Step.")

    def create_auto_proposals(self):
        self.auto_requested = False
        self.status_var.set("Detecting green/yellow pairs...")
        self.root.update_idletasks()
        try:
            from automatic_measurement import detect_pairs
            pairs = detect_pairs(self.image_array, self.get_pair_count())
            proposals = {}
            for index, step in enumerate(self.steps[1:], start=1):
                pair = pairs[step["pair"]]
                if step["kind"] == "tab":
                    points = pair["tab"]
                else:
                    points = pair["lobes"][step["side"]-1][step["kind"]]
                    indices = np.linspace(0, len(points)-1, step["count"], dtype=int)
                    points = points[indices]
                proposals[index] = np.asarray(points, dtype=float).copy()
            self.auto_proposals = proposals
        except Exception as exc:
            messagebox.showwarning(
                "Automatic detection",
                f"Automatic detection could not prepare all contours.\n{exc}\n\n"
                "Calibration is preserved. Continue marking the contours manually.",
            )

    def prepare_current_step(self):
        if self.step_index in self.auto_proposals:
            self.current_points = [p.copy() for p in self.auto_proposals[self.step_index]]
        self.draw_current_points()
        self.update_step_status()

    def draw_current_points(self):
        self.clear_preview_artists()
        if self.step_index < 0:
            return
        step = self.steps[self.step_index]
        self.pending_review = len(self.current_points) >= step["count"]
        self.accept_button.config(state=tk.NORMAL if self.pending_review else tk.DISABLED)
        self.manual_step_button.config(state=tk.NORMAL)
        if self.current_points:
            points = np.asarray(self.current_points)
            self.preview_artists.extend(self.ax.plot(points[:, 0], points[:, 1], "o",
                                                     ms=6, mec="#006b7a", mfc="white", zorder=10))
            if step["kind"] in ("ruler", "tab") and len(points) == 2:
                self.preview_artists.extend(self.ax.plot(points[:, 0], points[:, 1],
                                                         color="#006b7a", linewidth=1.8))
                if step["kind"] == "ruler":
                    self.preview_artists.extend(self.draw_ruler_ticks(self.ax, points))
            elif step["kind"] in ("outer", "conductor") and len(points) >= 3:
                center, radius, _ = fit_circle(points)
                circle = Circle(center, radius, fill=False, ec="#006b7a", ls="--", lw=1.5)
                self.ax.add_patch(circle)
                self.preview_artists.append(circle)
        self.canvas.draw_idle()

    def draw_ruler_ticks(self, axes, points):
        points = np.asarray(points, dtype=float)
        vector = points[1]-points[0]
        length = np.linalg.norm(vector)
        if length <= 0:
            return []
        normal = np.array([-vector[1], vector[0]]) / length
        tick_size = length*.035
        artists = []
        for fraction in (0., .5, 1.):
            point = points[0]+fraction*vector
            ends = np.array([point-normal*tick_size, point+normal*tick_size])
            artists.extend(axes.plot(ends[:, 0], ends[:, 1], color="#00758a", lw=1.8))
            artists.append(axes.annotate(
                f"{fraction*self.get_scale_length_mm():.3f} mm", xy=point,
                xytext=(0, 15 if fraction == .5 else -16), textcoords="offset points",
                ha=("center" if fraction == .5 else
                    ("right" if (fraction == 0) == (vector[0] >= 0) else "left")), fontsize=8,
                color="#00758a", bbox=dict(fc="white", ec="none", alpha=.85),
                annotation_clip=False,
            ))
        return artists

    def redraw_step_manually(self):
        if self.step_index < 0:
            return
        self.auto_proposals.pop(self.step_index, None)
        self.current_points = []
        self.point_drag = None
        self.draw_current_points()
        self.update_step_status()

    def update_edit_steps(self):
        values = [f"{i+1}: {self.steps[i]['label']}" for i in range(len(self.step_history))]
        self.edit_step_combo.config(values=values)
        self.edit_step_button.config(state=tk.NORMAL if values else tk.DISABLED)
        if values:
            self.edit_step_combo.current(len(values)-1)
        else:
            self.edit_step_combo.set("")

    def edit_selected_step(self):
        index = self.edit_step_combo.current()
        if not 0 <= index < len(self.step_history):
            return
        # Reuse accepted pixel coordinates downstream; measurements are recalculated.
        for i, points in self.accepted_points.items():
            if i >= index:
                self.auto_proposals[i] = points.copy()
        snapshot = deepcopy(self.step_history[index])
        self.step_history = self.step_history[:index]
        for name, value in snapshot.items():
            setattr(self, name, value)
        self.point_drag = self.label_drag = None
        self.auto_requested = False
        self.summary_rows = None
        self.save_button.config(state=tk.DISABLED)
        self.csv_button.config(state=tk.DISABLED)
        self.undo_button.config(state=tk.NORMAL)
        self.undo_step_button.config(state=tk.NORMAL if self.step_history else tk.DISABLED)
        self._populate_empty_table()
        if self.pixels_per_mm is None:
            self.calibration_var.set("Calibration: review ruler")
        self.clear_preview_artists()
        self.redraw_completed_geometry(show_labels=False)
        self.update_edit_steps()
        self.draw_current_points()
        self.update_step_status()

    def on_mouse_click(self, event):
        if getattr(self.toolbar, "mode", ""):
            return

        if event.button == 1 and not event.key and self.current_points:
            pixels = self.ax.transData.transform(np.asarray(self.current_points))
            distances = np.linalg.norm(pixels-[event.x, event.y], axis=1)
            if np.min(distances) <= 9:
                self.point_drag = int(np.argmin(distances))
                return
        # Test label boxes before collecting points, even outside the image axes.
        if event.button == 1 and not event.key:
            for key, annotation in reversed(list(self.live_annotations.items())):
                if annotation.get_bbox_patch().contains(event)[0]:
                    self.label_drag = (key, annotation, event.x, event.y,
                                       annotation.get_position())
                    return
        if event.inaxes != self.ax:
            return

        shift_left = (
            event.button == 1
            and isinstance(event.key, str)
            and "shift" in event.key.lower()
        )

        if event.button == 2 or shift_left:
            if event.xdata is None or event.ydata is None:
                return

            self.auto_fit_var.set(False)
            self.is_panning = True
            self.pan_start_xy = (event.xdata, event.ydata)
            self.pan_start_xlim = self.ax.get_xlim()
            self.pan_start_ylim = self.ax.get_ylim()
            return

        if event.button == 3:
            self.undo_point()
            return

        if self.step_index < 0:
            return

        if event.button != 1:
            return

        if event.xdata is None or event.ydata is None:
            return

        if self.pending_review:
            return

        point = np.array([event.xdata, event.ydata], dtype=float)
        self.current_points.append(point)
        self.draw_current_points()
        self.update_step_status()

    def on_mouse_release(self, event):
        self.point_drag = None
        if self.label_drag is not None:
            self.capture_annotation_offsets()
            self.label_drag = None
        if self.is_panning:
            self.is_panning = False
            self.pan_start_xy = None
            self.pan_start_xlim = None
            self.pan_start_ylim = None

    def undo_last_closure(self):
        if not self.step_history:
            return
        snapshot = self.step_history.pop()
        self.clear_preview_artists()
        self.label_drag = None
        self.point_drag = None
        for name, value in snapshot.items():
            setattr(self, name, value)
        self.summary_rows = None
        self.save_button.config(state=tk.DISABLED)
        self.csv_button.config(state=tk.DISABLED)
        self.undo_button.config(state=tk.NORMAL)
        self.undo_step_button.config(state=tk.NORMAL if self.step_history else tk.DISABLED)
        self._populate_empty_table()
        if self.pixels_per_mm is None:
            self.calibration_var.set("Calibration: not set")
        self.redraw_completed_geometry(show_labels=False)
        self.update_edit_steps()
        # Reopen the step just before its closing point so it can be corrected.
        self.undo_point()

    def undo_point(self):
        if not self.current_points:
            self.undo_last_closure()
            return

        self.current_points.pop()

        self.point_drag = None
        self.draw_current_points()
        self.update_step_status()

    def on_scroll(self, event):
        if self.image is None or event.inaxes != self.ax:
            return

        self.auto_fit_var.set(False)

        if event.xdata is None or event.ydata is None:
            return

        base_scale = 1.25

        x_min, x_max = self.ax.get_xlim()
        y_min, y_max = self.ax.get_ylim()

        if event.button == "up":
            scale_factor = 1.0 / base_scale
        elif event.button == "down":
            scale_factor = base_scale
        else:
            return

        new_width = (x_max - x_min) * scale_factor
        new_height = (y_max - y_min) * scale_factor

        rel_x = (x_max - event.xdata) / (x_max - x_min)
        rel_y = (y_max - event.ydata) / (y_max - y_min)

        self.ax.set_xlim(
            [
                event.xdata - new_width * (1 - rel_x),
                event.xdata + new_width * rel_x,
            ]
        )
        self.ax.set_ylim(
            [
                event.ydata - new_height * (1 - rel_y),
                event.ydata + new_height * rel_y,
            ]
        )

        self.canvas.draw_idle()

    def on_mouse_move(self, event):
        if self.point_drag is not None:
            if event.inaxes == self.ax and event.xdata is not None and event.ydata is not None:
                self.current_points[self.point_drag] = np.array([event.xdata, event.ydata])
                self.draw_current_points()
                self.update_step_status()
            return
        if self.label_drag is not None:
            key, annotation, start_x, start_y, offset = self.label_drag
            factor = 72.0 / self.figure.dpi
            position = (offset[0] + (event.x - start_x) * factor,
                        offset[1] + (event.y - start_y) * factor)
            annotation.set_position(position)
            self.annotation_offsets[key] = position
            self.canvas.draw_idle()
            return
        if self.image is None or event.inaxes != self.ax:
            return

        if event.xdata is None or event.ydata is None:
            return

        if self.is_panning and self.pan_start_xy is not None:
            start_x, start_y = self.pan_start_xy
            delta_x = event.xdata - start_x
            delta_y = event.ydata - start_y

            x0, x1 = self.pan_start_xlim
            y0, y1 = self.pan_start_ylim

            self.ax.set_xlim(x0 - delta_x, x1 - delta_x)
            self.ax.set_ylim(y0 - delta_y, y1 - delta_y)
            self.canvas.draw_idle()
            return

        if self.step_index >= 0 and not self.pending_review:
            step = self.steps[self.step_index]
            self.status_var.set(
                f"Step {self.step_index + 1}/{len(self.steps)} — {step['label']} — "
                f"points {len(self.current_points)}/{step['count']} — "
                f"x={event.xdata:.1f}, y={event.ydata:.1f} px"
            )

    def on_canvas_resize(self, event):
        if self.image_array is None:
            return

        if self._resize_after_id is not None:
            try:
                self.root.after_cancel(self._resize_after_id)
            except Exception:
                pass

        if self.auto_fit_var.get():
            self._resize_after_id = self.root.after(
                120,
                self.fit_image_to_view,
            )
        else:
            self.canvas.draw_idle()

    # --------------------------------------------------------
    # STEP PROCESSING
    # --------------------------------------------------------

    def complete_current_step(self):
        if self.step_index < 0 or len(self.current_points) < self.steps[self.step_index]["count"]:
            return
        step = self.steps[self.step_index]
        points = np.asarray(self.current_points, dtype=float)
        snapshot = {name: deepcopy(getattr(self, name)) for name in (
            "step_index", "current_points", "ruler_points", "pixels_per_mm",
            "mm_per_pixel", "lobes", "tabs", "pair_results",
        )}

        try:
            if not np.all(np.isfinite(points)):
                raise ValueError("All control points must have finite coordinates.")
            if step["kind"] in ("outer", "conductor"):
                matrix = np.column_stack((points, np.ones(len(points))))
                if np.linalg.matrix_rank(matrix) < 3:
                    raise ValueError("Circle points must not all lie on one straight line.")
            if step["kind"] == "ruler":
                self.process_ruler(points)
            elif step["kind"] == "outer":
                self.process_outer_circle(step["lobe"], points)
            elif step["kind"] == "conductor":
                self.process_conductor_circle(step["lobe"], points)
            elif step["kind"] == "tab":
                self.process_tab(step["pair"], points)
        except Exception as exc:
            for name, value in snapshot.items():
                setattr(self, name, value)
            messagebox.showerror("Measurement Error", str(exc))
            return

        self.step_history.append(snapshot)
        self.accepted_points[self.step_index] = points.copy()
        self.undo_step_button.config(state=tk.NORMAL)
        self.current_points = []
        self.pending_review = False
        self.point_drag = None
        self.accept_button.config(state=tk.DISABLED)
        self.clear_preview_artists()

        self.step_index += 1
        self.update_edit_steps()

        if self.step_index >= len(self.steps):
            self.finish_measurement()
            return

        self.redraw_completed_geometry(show_labels=False)
        if step["kind"] == "ruler" and self.auto_requested:
            self.create_auto_proposals()
        self.prepare_current_step()

    def process_ruler(self, points):
        ruler_pixels = distance_pixels(points[0], points[1])

        if ruler_pixels <= 0:
            raise ValueError("The two ruler points must be different.")

        scale_length_mm = self.get_scale_length_mm()

        self.ruler_points = points.copy()
        self.pixels_per_mm = ruler_pixels / scale_length_mm
        self.mm_per_pixel = 1.0 / self.pixels_per_mm

        self.calibration_var.set(
            f"Calibration: {self.pixels_per_mm:.2f} px/mm | "
            f"{self.mm_per_pixel * 1000.0:.2f} µm/px"
        )

    def process_outer_circle(self, lobe_index, points):
        center, radius, rmse_px = fit_circle(points)

        if self.lobes[lobe_index] is None:
            self.lobes[lobe_index] = {}

        self.lobes[lobe_index].update(
            {
                "outer_points": points.copy(),
                "outer_center": center,
                "outer_radius": radius,
                "outer_rmse_px": rmse_px,
            }
        )

    def process_conductor_circle(self, lobe_index, points):
        if self.pixels_per_mm is None:
            raise RuntimeError("Calibration must be completed first.")

        lobe = self.lobes[lobe_index]

        if not lobe or "outer_center" not in lobe:
            raise RuntimeError("Outer circle is missing for this lobe.")

        center, radius, rmse_px = fit_circle(points)

        lobe.update(
            {
                "conductor_points": points.copy(),
                "conductor_center": center,
                "conductor_radius": radius,
                "conductor_rmse_px": rmse_px,
            }
        )

        lobe["outer_diameter_mm"] = 2.0 * lobe["outer_radius"] / self.pixels_per_mm
        lobe["conductor_diameter_mm"] = 2.0 * radius / self.pixels_per_mm
        lobe["minimum_thickness_mm"] = minimum_thickness_mm(
            lobe["outer_center"],
            lobe["outer_radius"],
            center,
            radius,
            self.pixels_per_mm,
        )

    def process_tab(self, pair_index, points):
        self.tabs[pair_index] = points.copy()
        self.pair_results[pair_index] = self.calculate_pair_result(pair_index)

    def calculate_pair_result(self, pair_index):
        index_a = 2 * pair_index
        index_b = 2 * pair_index + 1

        lobe_a = self.lobes[index_a]
        lobe_b = self.lobes[index_b]
        tab_points = self.tabs[pair_index]

        if (
            lobe_a is None
            or lobe_b is None
            or "conductor_center" not in lobe_a
            or "conductor_center" not in lobe_b
            or tab_points is None
        ):
            raise RuntimeError(f"Pair {pair_index + 1} is not complete yet.")

        axis = lobe_b["conductor_center"] - lobe_a["conductor_center"]
        spacing_mm = float(np.linalg.norm(axis) / self.pixels_per_mm)

        width_mm = projected_pair_width_mm(
            lobe_a["outer_center"],
            lobe_a["outer_radius"],
            lobe_b["outer_center"],
            lobe_b["outer_radius"],
            axis,
            self.pixels_per_mm,
        )

        tab_mm = distance_mm(
            tab_points[0],
            tab_points[1],
            self.pixels_per_mm,
        )

        return {
            "name": f"Pair {pair_index + 1}",
            "index_a": index_a,
            "index_b": index_b,
            "width_mm": width_mm,
            "height_1_mm": lobe_a["outer_diameter_mm"],
            "height_2_mm": lobe_b["outer_diameter_mm"],
            "conductor_spacing_mm": spacing_mm,
            "tab_mm": tab_mm,
            "tab_points": tab_points.copy(),
        }

    # --------------------------------------------------------
    # RESULTS
    # --------------------------------------------------------

    def finish_measurement(self):
        self.step_index = -1
        self.pending_review = False
        self.accept_button.config(state=tk.DISABLED)
        self.manual_step_button.config(state=tk.DISABLED)
        self.undo_button.config(state=tk.NORMAL)
        self.undo_step_button.config(state=tk.NORMAL)

        self.calculate_results()
        self.populate_results_table()
        self.redraw_completed_geometry(show_labels=True)

        self.save_button.config(state=tk.NORMAL)
        self.csv_button.config(state=tk.NORMAL)

        fit_rmse_values = []
        for lobe in self.lobes:
            fit_rmse_values.extend(
                [lobe["outer_rmse_px"], lobe["conductor_rmse_px"]]
            )

        average_rmse = float(np.mean(fit_rmse_values))

        self.status_var.set(
            f"Measurement complete. Average circle-fit RMSE: {average_rmse:.2f} px. "
            "Review the overlays, drag labels if needed, then save the report or export CSV."
        )

        self.canvas.draw_idle()

    def calculate_results(self):
        if any(lobe is None for lobe in self.lobes):
            raise RuntimeError("Not all lobes were measured.")

        for pair_index in range(self.get_pair_count()):
            if self.pair_results[pair_index] is None:
                self.pair_results[pair_index] = self.calculate_pair_result(pair_index)

        width_values = []
        height1_values = []
        height2_values = []
        spacing_values = []
        tab_values = []
        min_thickness_values = []
        conductor_diameter_values = []

        for pair in self.pair_results:
            if pair is None:
                continue
            width_values.append(pair["width_mm"])
            height1_values.append(pair["height_1_mm"])
            height2_values.append(pair["height_2_mm"])
            spacing_values.append(pair["conductor_spacing_mm"])
            tab_values.append(pair["tab_mm"])

        for lobe in self.lobes:
            min_thickness_values.append(lobe["minimum_thickness_mm"])
            conductor_diameter_values.append(lobe["conductor_diameter_mm"])

        value_groups = {
            "Width (mm)": width_values,
            "Height 1 (mm)": height1_values,
            "Height 2 (mm)": height2_values,
            "Conductor spacing (mm)": spacing_values,
            "Tab (mm)": tab_values,
            "Minimum thickness (mm)": min_thickness_values,
            "Conductor diameter (mm)": conductor_diameter_values,
        }

        rows = []

        for dimension in SUMMARY_ORDER:
            minimum, maximum, average = safe_stats(value_groups[dimension])
            requirement = self.requirements[dimension]

            if requirement[0] == "none":
                status = "N/A"
            else:
                individual_status = [
                    check_requirement(value, requirement)
                    for value in value_groups[dimension]
                ]
                status = "OK" if all(item == "OK" for item in individual_status) else "FAIL"

            rows.append(
                {
                    "dimension": dimension,
                    "min": minimum,
                    "max": maximum,
                    "average": average,
                    "requirement": format_requirement(requirement),
                    "status": status,
                }
            )

        self.summary_rows = rows

    def populate_results_table(self):
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

        self.results_tree.tag_configure("ok", foreground="black")
        self.results_tree.tag_configure("fail", foreground="red")
        self.results_tree.tag_configure("na", foreground="black")

        for row in self.summary_rows:
            tag = "fail" if row["status"] == "FAIL" else (
                "ok" if row["status"] == "OK" else "na"
            )

            self.results_tree.insert(
                "",
                tk.END,
                values=(
                    row["dimension"],
                    f"{row['min']:.3f}",
                    f"{row['max']:.3f}",
                    f"{row['average']:.3f}",
                    row["requirement"],
                    row["status"],
                ),
                tags=(tag,),
            )

    # --------------------------------------------------------
    # DRAWING / REPORT
    # --------------------------------------------------------

    def show_image(self):
        self.ax.clear()
        self.ax.imshow(
            self.image_array,
            origin="upper",
            interpolation="nearest",
            aspect="equal",
        )
        self.ax.axis("off")
        self.ax.set_position([0.005, 0.005, 0.99, 0.99])
        self.fit_image_to_view()

    def fit_image_to_view(self):
        if self.image_array is None:
            return

        image_height, image_width = self.image_array.shape[:2]

        widget = self.canvas.get_tk_widget()
        canvas_width = max(widget.winfo_width(), 2)
        canvas_height = max(widget.winfo_height(), 2)

        image_aspect = image_width / image_height
        canvas_aspect = canvas_width / canvas_height

        center_x = (image_width - 1) / 2.0
        center_y = (image_height - 1) / 2.0

        if canvas_aspect >= image_aspect:
            visible_height = image_height
            visible_width = visible_height * canvas_aspect
        else:
            visible_width = image_width
            visible_height = visible_width / canvas_aspect

        x_min = center_x - visible_width / 2.0
        x_max = center_x + visible_width / 2.0
        y_min = center_y - visible_height / 2.0
        y_max = center_y + visible_height / 2.0

        self.ax.set_xlim(x_min, x_max)
        self.ax.set_ylim(y_max, y_min)
        self.ax.set_aspect("equal", adjustable="box")
        self.canvas.draw_idle()

    def clear_preview_artists(self):
        for artist in self.preview_artists:
            try:
                artist.remove()
            except Exception:
                pass
        self.preview_artists = []

    def capture_annotation_offsets(self):
        for key, annotation in self.live_annotations.items():
            try:
                position = annotation.get_position()
                self.annotation_offsets[key] = (
                    float(position[0]),
                    float(position[1]),
                )
            except Exception:
                pass

    def clear_result_artists(self):
        self.capture_annotation_offsets()

        for artist in self.result_artists:
            try:
                artist.remove()
            except Exception:
                pass

        self.result_artists = []
        self.live_annotations = {}

    def minimum_thickness_segment(self, lobe):
        outer_center = np.asarray(lobe["outer_center"], dtype=float)
        conductor_center = np.asarray(lobe["conductor_center"], dtype=float)

        vector = conductor_center - outer_center
        norm = np.linalg.norm(vector)

        if norm <= 1e-12:
            unit = np.array([1.0, 0.0])
        else:
            unit = vector / norm

        conductor_edge = conductor_center + unit * float(lobe["conductor_radius"])
        outer_edge = outer_center + unit * float(lobe["outer_radius"])

        return conductor_edge, outer_edge

    def pair_width_segment(self, pair):
        lobe_a = self.lobes[pair["index_a"]]
        lobe_b = self.lobes[pair["index_b"]]

        center_a = np.asarray(lobe_a["outer_center"], dtype=float)
        center_b = np.asarray(lobe_b["outer_center"], dtype=float)

        axis = (
            np.asarray(lobe_b["conductor_center"], dtype=float)
            - np.asarray(lobe_a["conductor_center"], dtype=float)
        )
        axis_norm = np.linalg.norm(axis)

        if axis_norm <= 1e-12:
            axis = np.array([1.0, 0.0])
        else:
            axis = axis / axis_norm

        candidates_min = [
            (
                float(np.dot(center_a, axis) - lobe_a["outer_radius"]),
                center_a - axis * lobe_a["outer_radius"],
            ),
            (
                float(np.dot(center_b, axis) - lobe_b["outer_radius"]),
                center_b - axis * lobe_b["outer_radius"],
            ),
        ]

        candidates_max = [
            (
                float(np.dot(center_a, axis) + lobe_a["outer_radius"]),
                center_a + axis * lobe_a["outer_radius"],
            ),
            (
                float(np.dot(center_b, axis) + lobe_b["outer_radius"]),
                center_b + axis * lobe_b["outer_radius"],
            ),
        ]

        point_min = min(candidates_min, key=lambda item: item[0])[1]
        point_max = max(candidates_max, key=lambda item: item[0])[1]

        return point_min, point_max

    def add_live_annotation(
        self,
        key,
        text,
        anchor,
        status,
        default_offset,
    ):
        color = status_color(status)
        offset = self.annotation_offsets.get(key, default_offset)

        annotation = self.ax.annotate(
            text,
            xy=(float(anchor[0]), float(anchor[1])),
            xycoords="data",
            xytext=offset,
            textcoords="offset points",
            ha="center",
            va="center",
            fontsize=8,
            color=color,
            bbox=dict(
                boxstyle="round,pad=0.28",
                fc="white",
                ec=color,
                lw=1.2,
                alpha=0.92,
            ),
            arrowprops=dict(
                arrowstyle="-",
                color=color,
                lw=1.0,
                shrinkA=2,
                shrinkB=2,
            ),
            annotation_clip=False,
        )

        self.result_artists.append(annotation)
        self.live_annotations[key] = annotation

    def redraw_completed_geometry(self, show_labels=False):
        if self.image_array is None:
            return

        current_xlim = self.ax.get_xlim()
        current_ylim = self.ax.get_ylim()

        self.capture_annotation_offsets()
        self.result_artists = []
        self.live_annotations = {}

        self.ax.clear()
        self.ax.imshow(
            self.image_array,
            origin="upper",
            interpolation="nearest",
            aspect="equal",
        )
        self.ax.axis("off")
        self.ax.set_position([0.005, 0.005, 0.99, 0.99])


        if self.ruler_points is not None:
            ruler_line = self.ax.plot(
                self.ruler_points[:, 0],
                self.ruler_points[:, 1],
                linewidth=1.5,
                color="black",
            )[0]
            self.result_artists.append(ruler_line)
            self.result_artists.extend(self.draw_ruler_ticks(self.ax, self.ruler_points))

            ruler_mid = np.mean(self.ruler_points, axis=0)
            self.add_live_annotation(
                "RULER",
                f"Scale = {self.get_scale_length_mm():.3f} mm",
                ruler_mid,
                "OK",
                (0, -28),
            )

        pair_count = self.get_pair_count()

        for pair_index in range(pair_count):
            complete_pair = self.pair_results[pair_index] is not None

            for side in range(2):
                lobe_index = 2 * pair_index + side
                lobe = self.lobes[lobe_index]

                if not lobe:
                    continue
                if "outer_center" not in lobe:
                    continue

                side_number = side + 1
                height_requirement_key = "Height 1 (mm)" if side == 0 else "Height 2 (mm)"

                if "outer_diameter_mm" in lobe:
                    outer_status = check_requirement(
                        lobe["outer_diameter_mm"],
                        self.requirements[height_requirement_key],
                    )
                else:
                    outer_status = "N/A"

                outer_circle = Circle(
                    lobe["outer_center"],
                    lobe["outer_radius"],
                    fill=False,
                    linewidth=1.5,
                    edgecolor=status_color(outer_status),
                )
                self.ax.add_patch(outer_circle)
                self.result_artists.append(outer_circle)

                if "conductor_center" not in lobe:
                    continue

                conductor_status = check_requirement(
                    lobe["conductor_diameter_mm"],
                    self.requirements["Conductor diameter (mm)"],
                )

                conductor_circle = Circle(
                    lobe["conductor_center"],
                    lobe["conductor_radius"],
                    fill=False,
                    linewidth=1.5,
                    edgecolor=status_color(conductor_status),
                )
                self.ax.add_patch(conductor_circle)
                self.result_artists.append(conductor_circle)

                thickness_status = check_requirement(
                    lobe["minimum_thickness_mm"],
                    self.requirements["Minimum thickness (mm)"],
                )

                thickness_start, thickness_end = self.minimum_thickness_segment(lobe)
                thickness_line = self.ax.plot(
                    [thickness_start[0], thickness_end[0]],
                    [thickness_start[1], thickness_end[1]],
                    linewidth=1.8,
                    color=status_color(thickness_status),
                )[0]
                self.result_artists.append(thickness_line)

                if not (show_labels or complete_pair):
                    continue

                outer_center = np.asarray(lobe["outer_center"], dtype=float)
                conductor_center = np.asarray(lobe["conductor_center"], dtype=float)

                # distribute labels by side and pair parity
                above = (pair_index % 2 == 0)
                if side == 0:
                    base_x = -100
                else:
                    base_x = 100
                if above:
                    offsets = [(base_x, -65), (base_x, -15), (base_x, 35)]
                else:
                    offsets = [(base_x, 35), (base_x, -15), (base_x, -65)]

                outer_anchor = outer_center + np.array([0.0, -float(lobe["outer_radius"])])
                copper_anchor = conductor_center + np.array([0.0, -float(lobe["conductor_radius"])])
                thickness_anchor = (thickness_start + thickness_end) / 2.0

                self.add_live_annotation(
                    f"L{lobe_index + 1}_HEIGHT",
                    f"H{side_number} = {lobe['outer_diameter_mm']:.3f} mm",
                    outer_anchor,
                    outer_status,
                    offsets[0],
                )

                self.add_live_annotation(
                    f"L{lobe_index + 1}_COPPER",
                    f"Cu = {lobe['conductor_diameter_mm']:.3f} mm",
                    copper_anchor,
                    conductor_status,
                    offsets[1],
                )

                self.add_live_annotation(
                    f"L{lobe_index + 1}_TMIN",
                    f"tmin = {lobe['minimum_thickness_mm']:.3f} mm",
                    thickness_anchor,
                    thickness_status,
                    offsets[2],
                )

        for pair_index, pair in enumerate(self.pair_results):
            if pair is None:
                continue

            lobe_a = self.lobes[pair["index_a"]]
            lobe_b = self.lobes[pair["index_b"]]

            conductor_a = np.asarray(lobe_a["conductor_center"], dtype=float)
            conductor_b = np.asarray(lobe_b["conductor_center"], dtype=float)

            spacing_status = check_requirement(
                pair["conductor_spacing_mm"],
                self.requirements["Conductor spacing (mm)"],
            )
            spacing_line = self.ax.plot(
                [conductor_a[0], conductor_b[0]],
                [conductor_a[1], conductor_b[1]],
                linewidth=1.7,
                color=status_color(spacing_status),
            )[0]
            self.result_artists.append(spacing_line)

            spacing_anchor = (conductor_a + conductor_b) / 2.0

            width_start, width_end = self.pair_width_segment(pair)
            width_line = self.ax.plot(
                [width_start[0], width_end[0]],
                [width_start[1], width_end[1]],
                linewidth=1.4,
                color="black",
            )[0]
            self.result_artists.append(width_line)
            width_anchor = (width_start + width_end) / 2.0

            tab_points = np.asarray(pair["tab_points"], dtype=float)
            tab_status = check_requirement(
                pair["tab_mm"],
                self.requirements["Tab (mm)"],
            )
            tab_line = self.ax.plot(
                tab_points[:, 0],
                tab_points[:, 1],
                linewidth=2.0,
                color=status_color(tab_status),
            )[0]
            self.result_artists.append(tab_line)
            tab_anchor = np.mean(tab_points, axis=0)

            above = (pair_index % 2 == 0)
            if above:
                width_offset = (0, -120)
                spacing_offset = (0, -82)
                tab_offset = (0, 78)
            else:
                width_offset = (0, 120)
                spacing_offset = (0, 82)
                tab_offset = (0, -78)

            self.add_live_annotation(
                f"PAIR{pair_index}_WIDTH",
                f"{pair['name']} Width = {pair['width_mm']:.3f} mm",
                width_anchor,
                "N/A",
                width_offset,
            )

            self.add_live_annotation(
                f"PAIR{pair_index}_SPACING",
                f"{pair['name']} Spacing = {pair['conductor_spacing_mm']:.3f} mm",
                spacing_anchor,
                spacing_status,
                spacing_offset,
            )

            self.add_live_annotation(
                f"PAIR{pair_index}_TAB",
                f"{pair['name']} Tab = {pair['tab_mm']:.3f} mm",
                tab_anchor,
                tab_status,
                tab_offset,
            )

        self.ax.set_xlim(current_xlim)
        self.ax.set_ylim(current_ylim)
        self.canvas.draw_idle()

    def create_report_figure(self):
        self.capture_annotation_offsets()

        report = Figure(figsize=(13, 13), dpi=100)
        grid = report.add_gridspec(2, 1, height_ratios=[1.8, 5.4])

        table_ax = report.add_subplot(grid[0])
        image_ax = report.add_subplot(grid[1])

        table_ax.axis("off")

        column_labels = [
            "Dimension",
            "Min",
            "Max",
            "Average",
            "Requirement",
            "Status",
        ]

        cell_text = []
        for row in self.summary_rows:
            cell_text.append(
                [
                    row["dimension"],
                    f"{row['min']:.3f}",
                    f"{row['max']:.3f}",
                    f"{row['average']:.3f}",
                    row["requirement"],
                    row["status"],
                ]
            )

        table = table_ax.table(
            cellText=cell_text,
            colLabels=column_labels,
            cellLoc="center",
            loc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(8.5)
        table.scale(1.0, 1.45)

        for row_index, row in enumerate(self.summary_rows, start=1):
            color = status_color(row["status"])
            for column_index in range(len(column_labels)):
                table[(row_index, column_index)].get_text().set_color(color)

        table_ax.set_title(
            "Wire Dimensional Analysis",
            fontsize=13,
            pad=8,
        )

        calibration_text = (
            f"Pairs: {self.get_pair_count()} | "
            f"Calibration: {self.pixels_per_mm:.2f} px/mm | "
            f"Resolution: {self.mm_per_pixel * 1000.0:.2f} µm/px"
        )

        table_ax.text(
            0.5,
            0.02,
            calibration_text,
            transform=table_ax.transAxes,
            ha="center",
            va="bottom",
            fontsize=9,
            color="black",
        )

        image_ax.imshow(
            self.image_array,
            origin="upper",
            interpolation="nearest",
            aspect="equal",
        )
        image_ax.axis("off")

        image_height, image_width = self.image_array.shape[:2]
        margin_x = image_width * 0.22
        margin_y = image_height * 0.16

        image_ax.set_xlim(-margin_x, image_width + margin_x)
        image_ax.set_ylim(image_height + margin_y, -margin_y)

        def report_annotation(key, label, anchor, status, default_offset):
            offset = self.annotation_offsets.get(key, default_offset)
            color = status_color(status)

            image_ax.annotate(
                label,
                xy=(float(anchor[0]), float(anchor[1])),
                xycoords="data",
                xytext=offset,
                textcoords="offset points",
                ha="center",
                va="center",
                fontsize=8,
                color=color,
                bbox=dict(
                    boxstyle="round,pad=0.28",
                    fc="white",
                    ec=color,
                    lw=1.2,
                    alpha=0.94,
                ),
                arrowprops=dict(
                    arrowstyle="-",
                    color=color,
                    lw=1.0,
                    shrinkA=2,
                    shrinkB=2,
                ),
                annotation_clip=False,
            )

        if self.ruler_points is not None:
            image_ax.plot(
                self.ruler_points[:, 0],
                self.ruler_points[:, 1],
                linewidth=1.5,
                color="black",
            )
            self.draw_ruler_ticks(image_ax, self.ruler_points)
            report_annotation(
                "RULER",
                f"Scale = {self.get_scale_length_mm():.3f} mm",
                np.mean(self.ruler_points, axis=0),
                "OK",
                (0, -28),
            )

        pair_count = self.get_pair_count()

        for pair_index in range(pair_count):
            for side in range(2):
                lobe_index = 2 * pair_index + side
                lobe = self.lobes[lobe_index]

                side_number = side + 1
                height_requirement_key = "Height 1 (mm)" if side == 0 else "Height 2 (mm)"

                height_status = check_requirement(
                    lobe["outer_diameter_mm"],
                    self.requirements[height_requirement_key],
                )
                conductor_status = check_requirement(
                    lobe["conductor_diameter_mm"],
                    self.requirements["Conductor diameter (mm)"],
                )
                thickness_status = check_requirement(
                    lobe["minimum_thickness_mm"],
                    self.requirements["Minimum thickness (mm)"],
                )

                image_ax.add_patch(
                    Circle(
                        lobe["outer_center"],
                        lobe["outer_radius"],
                        fill=False,
                        linewidth=1.5,
                        edgecolor=status_color(height_status),
                    )
                )

                image_ax.add_patch(
                    Circle(
                        lobe["conductor_center"],
                        lobe["conductor_radius"],
                        fill=False,
                        linewidth=1.5,
                        edgecolor=status_color(conductor_status),
                    )
                )

                thickness_start, thickness_end = self.minimum_thickness_segment(lobe)
                image_ax.plot(
                    [thickness_start[0], thickness_end[0]],
                    [thickness_start[1], thickness_end[1]],
                    linewidth=1.8,
                    color=status_color(thickness_status),
                )

                above = (pair_index % 2 == 0)
                if side == 0:
                    base_x = -100
                else:
                    base_x = 100
                if above:
                    offsets = [(base_x, -65), (base_x, -15), (base_x, 35)]
                else:
                    offsets = [(base_x, 35), (base_x, -15), (base_x, -65)]

                outer_center = np.asarray(lobe["outer_center"], dtype=float)
                conductor_center = np.asarray(lobe["conductor_center"], dtype=float)

                outer_anchor = outer_center + np.array([0.0, -float(lobe["outer_radius"])])
                copper_anchor = conductor_center + np.array([0.0, -float(lobe["conductor_radius"])])
                thickness_anchor = (thickness_start + thickness_end) / 2.0

                report_annotation(
                    f"L{lobe_index + 1}_HEIGHT",
                    f"H{side_number} = {lobe['outer_diameter_mm']:.3f} mm",
                    outer_anchor,
                    height_status,
                    offsets[0],
                )

                report_annotation(
                    f"L{lobe_index + 1}_COPPER",
                    f"Cu = {lobe['conductor_diameter_mm']:.3f} mm",
                    copper_anchor,
                    conductor_status,
                    offsets[1],
                )

                report_annotation(
                    f"L{lobe_index + 1}_TMIN",
                    f"tmin = {lobe['minimum_thickness_mm']:.3f} mm",
                    thickness_anchor,
                    thickness_status,
                    offsets[2],
                )

        for pair_index, pair in enumerate(self.pair_results):
            lobe_a = self.lobes[pair["index_a"]]
            lobe_b = self.lobes[pair["index_b"]]

            conductor_a = np.asarray(lobe_a["conductor_center"], dtype=float)
            conductor_b = np.asarray(lobe_b["conductor_center"], dtype=float)

            spacing_status = check_requirement(
                pair["conductor_spacing_mm"],
                self.requirements["Conductor spacing (mm)"],
            )

            image_ax.plot(
                [conductor_a[0], conductor_b[0]],
                [conductor_a[1], conductor_b[1]],
                linewidth=1.7,
                color=status_color(spacing_status),
            )

            spacing_anchor = (conductor_a + conductor_b) / 2.0

            width_start, width_end = self.pair_width_segment(pair)
            image_ax.plot(
                [width_start[0], width_end[0]],
                [width_start[1], width_end[1]],
                linewidth=1.4,
                color="black",
            )
            width_anchor = (width_start + width_end) / 2.0

            tab_points = np.asarray(pair["tab_points"], dtype=float)
            tab_status = check_requirement(
                pair["tab_mm"],
                self.requirements["Tab (mm)"],
            )

            image_ax.plot(
                tab_points[:, 0],
                tab_points[:, 1],
                linewidth=2.0,
                color=status_color(tab_status),
            )
            tab_anchor = np.mean(tab_points, axis=0)

            above = (pair_index % 2 == 0)
            if above:
                width_offset = (0, -120)
                spacing_offset = (0, -82)
                tab_offset = (0, 78)
            else:
                width_offset = (0, 120)
                spacing_offset = (0, 82)
                tab_offset = (0, -78)

            report_annotation(
                f"PAIR{pair_index}_WIDTH",
                f"{pair['name']} Width = {pair['width_mm']:.3f} mm",
                width_anchor,
                "N/A",
                width_offset,
            )
            report_annotation(
                f"PAIR{pair_index}_SPACING",
                f"{pair['name']} Spacing = {pair['conductor_spacing_mm']:.3f} mm",
                spacing_anchor,
                spacing_status,
                spacing_offset,
            )
            report_annotation(
                f"PAIR{pair_index}_TAB",
                f"{pair['name']} Tab = {pair['tab_mm']:.3f} mm",
                tab_anchor,
                tab_status,
                tab_offset,
            )

        if self.image_path:
            image_ax.set_title(self.image_path.name, fontsize=10, color="black")

        report.tight_layout()
        return report


# ============================================================
# MAIN
# ============================================================

def main():
    root = tk.Tk()
    app = WireMeasurementApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
