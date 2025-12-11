# ui.py  (PySide6 version)

import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QFileDialog, QTextEdit, QLabel, QSplitter, QDialog
)
from PySide6.QtCore import Qt

from acquisition import run_acquisition, run_matrix_creation, run_scan_full
from frog_post import run_frog_post
from config import ACQ_DEFAULTS, FROG_DEFAULTS

from PySide6.QtCore import Signal
import matplotlib
matplotlib.use('Qt5Agg')  # or 'Qt6Agg' for PySide6
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas  # PyQt5
# or: from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas  # PySide6
from matplotlib.figure import Figure


class Logger:
    """Simple logger that writes to a QTextEdit."""
    def __init__(self, widget: QTextEdit):
        self.widget = widget

    def write(self, text):
        self.widget.moveCursor(self.widget.textCursor().End)
        self.widget.insertPlainText(str(text))
        self.widget.ensureCursorVisible()

    def flush(self):
        pass


class MainWindow(QWidget):
    
    plot_ready = Signal(object, object, object)  # fig, title, description
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Zaber FROG Controller (PyQt)")
        self.init_ui()
        self.plot_ready.connect(self.display_plot)  # Connect signal

    def init_ui(self):
        # ---------- Acquisition form ----------
        self.acq_save_dir = QLineEdit(ACQ_DEFAULTS["SAVE_DIR"])
        self.acq_port = QLineEdit(ACQ_DEFAULTS["PORT_NAME"])
        self.acq_baud = QLineEdit(str(ACQ_DEFAULTS["BAUD_RATE"]))
        self.acq_addr = QLineEdit(str(ACQ_DEFAULTS["DEVICE_ADDRESS"]))
        self.acq_step = QLineEdit(str(ACQ_DEFAULTS["STEP_SIZE_MM"]))
        self.acq_scan = QLineEdit(str(ACQ_DEFAULTS["SCAN_DISTANCE_MM"]))
        self.acq_int = QLineEdit(str(ACQ_DEFAULTS["SPEC_INT_TIME_MS"]))
        self.acq_travel = QLineEdit(str(ACQ_DEFAULTS["TOTAL_TRAVEL_RANGE"]))
        self.acq_mid = QLineEdit(str(ACQ_DEFAULTS["APPROX_MIDPOINT"]))
        self.acq_cwl = QLineEdit(str(ACQ_DEFAULTS["central_wavelength"]))
        self.acq_bw = QLineEdit(str(ACQ_DEFAULTS["bandwidth"]))
        self.acq_tmin = QLineEdit(str(ACQ_DEFAULTS["crop_time_range_fs"][0]))
        self.acq_tmax = QLineEdit(str(ACQ_DEFAULTS["crop_time_range_fs"][1]))

        acq_form = QFormLayout()
        btn_browse_acq = QPushButton("Browse...")
        btn_browse_acq.clicked.connect(self.browse_acq_folder)

        row = QHBoxLayout()
        row.addWidget(self.acq_save_dir)
        row.addWidget(btn_browse_acq)
        acq_form.addRow("Save directory", row)

        acq_form.addRow("Port name", self.acq_port)
        acq_form.addRow("Baud rate", self.acq_baud)
        acq_form.addRow("Device address", self.acq_addr)
        acq_form.addRow("Step size (mm)", self.acq_step)
        acq_form.addRow("Scan distance (mm)", self.acq_scan)
        acq_form.addRow("Spec int time (ms)", self.acq_int)
        acq_form.addRow("Total travel (mm)", self.acq_travel)
        acq_form.addRow("Approx midpoint (mm)", self.acq_mid)
        acq_form.addRow("Central λ (nm)", self.acq_cwl)
        acq_form.addRow("Bandwidth (nm)", self.acq_bw)

        row_t = QHBoxLayout()
        row_t.addWidget(self.acq_tmin)
        row_t.addWidget(self.acq_tmax)
        acq_form.addRow("Crop time fs min/max", row_t)

        btn_load_acq = QPushButton("Load Acq Defaults")
        btn_run_acq = QPushButton("Acquire Only")
        btn_run_mat = QPushButton("Matrix Only")
        btn_run_full = QPushButton("Acquire + Matrix")

        btn_load_acq.clicked.connect(self.load_acq_defaults)
        btn_run_acq.clicked.connect(self.handle_run_acq)
        btn_run_mat.clicked.connect(self.handle_run_matrix)
        btn_run_full.clicked.connect(self.handle_run_full)

        acq_buttons = QHBoxLayout()
        acq_buttons.addWidget(btn_load_acq)
        acq_buttons.addWidget(btn_run_acq)
        acq_buttons.addWidget(btn_run_mat)
        acq_buttons.addWidget(btn_run_full)

        acq_layout = QVBoxLayout()
        acq_layout.addWidget(QLabel("Acquisition + Matrix Parameters"))
        acq_layout.addLayout(acq_form)
        acq_layout.addLayout(acq_buttons)

        # ---------- FROG form ----------
        self.frog_folder = QLineEdit(FROG_DEFAULTS["FOLDER"])
        self.frog_filename = QLineEdit(FROG_DEFAULTS["FILENAME"])
        self.frog_pw = QLineEdit(str(FROG_DEFAULTS["APPROX_PULSE_WIDTH"]))
        self.frog_pad = QLineEdit(str(FROG_DEFAULTS["PADDING_THICKNESS"]))
        self.frog_dim = QLineEdit(str(FROG_DEFAULTS["TOTAL_DIMENSION"]))

        frog_form = QFormLayout()
        btn_browse_frog = QPushButton("Browse...")
        btn_browse_frog.clicked.connect(self.browse_frog_folder)

        rowf = QHBoxLayout()
        rowf.addWidget(self.frog_folder)
        rowf.addWidget(btn_browse_frog)
        frog_form.addRow("Folder", rowf)

        frog_form.addRow("NPZ filename", self.frog_filename)
        frog_form.addRow("Approx pulse width (fs)", self.frog_pw)
        frog_form.addRow("Padding fraction", self.frog_pad)
        frog_form.addRow("Total dimension", self.frog_dim)

        btn_load_frog = QPushButton("Load FROG Defaults")
        btn_run_frog = QPushButton("Run FROG Post-Proc")

        btn_load_frog.clicked.connect(self.load_frog_defaults)
        btn_run_frog.clicked.connect(self.handle_run_frog)

        frog_buttons = QHBoxLayout()
        frog_buttons.addWidget(btn_load_frog)
        frog_buttons.addWidget(btn_run_frog)

        frog_layout = QVBoxLayout()
        frog_layout.addWidget(QLabel("FROG Post-Processing"))
        frog_layout.addLayout(frog_form)
        frog_layout.addLayout(frog_buttons)

        # ---------- Splitter + log ----------
        left = QWidget()
        left.setLayout(acq_layout)
        right = QWidget()
        right.setLayout(frog_layout)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)

        main_layout = QVBoxLayout()
        main_layout.addWidget(splitter)
        main_layout.addWidget(QLabel("Log / Output:"))
        main_layout.addWidget(self.log_output)

        self.setLayout(main_layout)

        # Redirect prints to the text box
        sys.stdout = Logger(self.log_output)

    # ---------- helpers for params ----------

    def load_acq_defaults(self):
        self.acq_save_dir.setText(ACQ_DEFAULTS["SAVE_DIR"])
        self.acq_port.setText(ACQ_DEFAULTS["PORT_NAME"])
        self.acq_baud.setText(str(ACQ_DEFAULTS["BAUD_RATE"]))
        self.acq_addr.setText(str(ACQ_DEFAULTS["DEVICE_ADDRESS"]))
        self.acq_step.setText(str(ACQ_DEFAULTS["STEP_SIZE_MM"]))
        self.acq_scan.setText(str(ACQ_DEFAULTS["SCAN_DISTANCE_MM"]))
        self.acq_int.setText(str(ACQ_DEFAULTS["SPEC_INT_TIME_MS"]))
        self.acq_travel.setText(str(ACQ_DEFAULTS["TOTAL_TRAVEL_RANGE"]))
        self.acq_mid.setText(str(ACQ_DEFAULTS["APPROX_MIDPOINT"]))
        self.acq_cwl.setText(str(ACQ_DEFAULTS["central_wavelength"]))
        self.acq_bw.setText(str(ACQ_DEFAULTS["bandwidth"]))
        self.acq_tmin.setText(str(ACQ_DEFAULTS["crop_time_range_fs"][0]))
        self.acq_tmax.setText(str(ACQ_DEFAULTS["crop_time_range_fs"][1]))

    def load_frog_defaults(self):
        self.frog_folder.setText(FROG_DEFAULTS["FOLDER"])
        self.frog_filename.setText(FROG_DEFAULTS["FILENAME"])
        self.frog_pw.setText(str(FROG_DEFAULTS["APPROX_PULSE_WIDTH"]))
        self.frog_pad.setText(str(FROG_DEFAULTS["PADDING_THICKNESS"]))
        self.frog_dim.setText(str(FROG_DEFAULTS["TOTAL_DIMENSION"]))

    def browse_acq_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Save Directory", self.acq_save_dir.text())
        if folder:
            self.acq_save_dir.setText(folder)

    def browse_frog_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select FROG Folder", self.frog_folder.text())
        if folder:
            self.frog_folder.setText(folder)

    def gather_acq_params(self):
        return {
            "SAVE_DIR": self.acq_save_dir.text(),
            "PORT_NAME": self.acq_port.text(),
            "BAUD_RATE": int(self.acq_baud.text()),
            "DEVICE_ADDRESS": int(self.acq_addr.text()),
            "STEP_SIZE_MM": float(self.acq_step.text()),
            "SCAN_DISTANCE_MM": float(self.acq_scan.text()),
            "SPEC_INT_TIME_MS": int(self.acq_int.text()),
            "TOTAL_TRAVEL_RANGE": float(self.acq_travel.text()),
            "APPROX_MIDPOINT": float(self.acq_mid.text()),
            "central_wavelength": float(self.acq_cwl.text()),
            "bandwidth": float(self.acq_bw.text()),
            "crop_time_range_fs": [
                float(self.acq_tmin.text()),
                float(self.acq_tmax.text()),
            ],
        }

    def gather_frog_params(self):
        return {
            "FOLDER": self.frog_folder.text(),
            "FILENAME": self.frog_filename.text(),
            "APPROX_PULSE_WIDTH": float(self.frog_pw.text()),
            "PADDING_THICKNESS": float(self.frog_pad.text()),
            "TOTAL_DIMENSION": int(self.frog_dim.text()),
        }

    # ---------- button handlers ----------

    def handle_run_acq(self):
        print("\n=== Running Acquisition Only ===")
        try:
            params = self.gather_acq_params()
            run_acquisition(params)
        except Exception as e:
            print(f"Error during acquisition: {e}")

    def handle_run_matrix(self):
        print("\n=== Running Matrix Creation Only ===")
        try:
            params = self.gather_acq_params()
            run_matrix_creation(params)
        except Exception as e:
            print(f"Error during matrix creation: {e}")

    def handle_run_full(self):
        print("\n=== Running Acquisition + Matrix ===")
        try:
            params = self.gather_acq_params()
            run_scan_full(params)
        except Exception as e:
            print(f"Error during acquisition + matrix: {e}")

    def handle_run_frog(self):
        print("\n=== Running FROG Post-Processing ===")
        try:
            params = self.gather_frog_params()
            params['window'] = self  # Pass window reference for signals
            run_frog_post(params)
        except Exception as e:
            print(f"Error during FROG post-processing: {e}")
            
    def display_plot(self, fig, title, description):
        """Display matplotlib figure in UI."""
        # Create scrollable plot area
        canvas = FigureCanvas(fig)
        dialog = PlotDialog(fig, title, description, self)
        dialog.exec()

class PlotDialog(QDialog):
    def __init__(self, fig, title, description, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(800, 600)
        
        layout = QVBoxLayout()
        
        # Plot canvas
        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)
        
        # Description label
        label = QLabel(description)
        label.setWordWrap(True)
        layout.addWidget(label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("Save PNG")
        btn_close = QPushButton("Close")
        btn_save.clicked.connect(self.save_plot)
        btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
        self.canvas = canvas
        self.fig = fig
        
    def save_plot(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save Plot", "", "PNG (*.png)")
        if filename:
            self.fig.savefig(filename, dpi=150, bbox_inches='tight')


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(1200, 700)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
