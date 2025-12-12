# ui.py  (PySide6 version)

import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QFileDialog, QTextEdit, QLabel, QSplitter, QDialog
)
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QTextCursor
from acquisition import (
    run_acquisition, run_matrix_creation, run_scan_full,
    stage_home, stage_get_status, stage_move_absolute,
    stage_jog, stage_go_midpoint, stage_go_scan_start,
    stage_go_scan_end, stage_stop,
    # request_acquisition_stop,   # uncomment when you implement stop
)

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
        cursor = self.widget.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.widget.setTextCursor(cursor)
        self.widget.insertPlainText(str(text))
        self.widget.ensureCursorVisible()


    def flush(self):
        pass


class AcquisitionWorker(QObject):
    finished = Signal()
    error = Signal(str)

    def __init__(self, params, run_func):
        super().__init__()
        self.params = params
        self.run_func = run_func

    def run(self):
        try:
            self.run_func(self.params)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


class MainWindow(QWidget):
    
    plot_ready = Signal(object, object, object)  # fig, title, description
    
    def __init__(self):
        super().__init__()
        self.acq_thread = None
        self.acq_worker = None
        self.full_thread = None
        self.full_worker = None
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
        
                # ---------- Stage control panel ----------
        self.stage_abs_pos = QLineEdit("0.0")      # absolute target [mm]
        self.stage_jog_step = QLineEdit("0.05")    # jog step [mm]

        self.stage_status_label = QLabel("Position: n/a, State: n/a")
        self.stage_status_label.setStyleSheet("color: blue;")

        stage_form = QFormLayout()
        stage_form.addRow("Abs. position (mm)", self.stage_abs_pos)
        stage_form.addRow("Jog step (mm)", self.stage_jog_step)

        btn_home = QPushButton("Home")
        btn_start = QPushButton("Go Start")
        btn_mid = QPushButton("Go Midpoint")
        btn_end = QPushButton("Go End")
        btn_jog_minus = QPushButton("Jog -")
        btn_jog_plus = QPushButton("Jog +")
        btn_stop = QPushButton("Stop")
        btn_status = QPushButton("Get Status")
        btn_goto = QPushButton("Go To Abs Pos")

        btn_home.clicked.connect(self.handle_stage_home)
        btn_start.clicked.connect(self.handle_stage_start)
        btn_mid.clicked.connect(self.handle_stage_mid)
        btn_end.clicked.connect(self.handle_stage_end)
        btn_jog_minus.clicked.connect(self.handle_stage_jog_minus)
        btn_jog_plus.clicked.connect(self.handle_stage_jog_plus)
        btn_stop.clicked.connect(self.handle_stage_stop)
        btn_status.clicked.connect(self.handle_stage_status)
        btn_goto.clicked.connect(self.handle_stage_goto)

        stage_buttons_row1 = QHBoxLayout()
        stage_buttons_row1.addWidget(btn_home)
        stage_buttons_row1.addWidget(btn_start)
        stage_buttons_row1.addWidget(btn_mid)
        stage_buttons_row1.addWidget(btn_end)
        stage_buttons_row1.addWidget(btn_goto)

        stage_buttons_row2 = QHBoxLayout()
        stage_buttons_row2.addWidget(btn_jog_minus)
        stage_buttons_row2.addWidget(btn_jog_plus)
        stage_buttons_row2.addWidget(btn_stop)
        stage_buttons_row2.addWidget(btn_status)

        stage_layout = QVBoxLayout()
        stage_layout.addWidget(QLabel("Stage Control"))
        stage_layout.addLayout(stage_form)
        stage_layout.addLayout(stage_buttons_row1)
        stage_layout.addLayout(stage_buttons_row2)
        stage_layout.addWidget(self.stage_status_label)

        # Append stage control below acquisition
        acq_layout.addSpacing(10)
        acq_layout.addLayout(stage_layout)


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
        """
        print("\n=== Running Acquisition Only ===")
        try:
            params = self.gather_acq_params()
            run_acquisition(params)
        except Exception as e:
            print(f"Error during acquisition: {e}")
        """
        print("\n=== Running Acquisition Only (threaded) ===")
        try:
            params = self.gather_acq_params()
        except Exception as e:
            print(f"Error gathering acquisition params: {e}")
            return

        # Disable acquisition buttons during run (optional)
        # e.g., self.some_acq_button.setEnabled(False)

        self.acq_thread = QThread()
        self.acq_worker = AcquisitionWorker(params, run_acquisition)
        self.acq_worker.moveToThread(self.acq_thread)

        self.acq_thread.started.connect(self.acq_worker.run)
        self.acq_worker.finished.connect(self.acq_thread.quit)
        self.acq_worker.finished.connect(self.acq_worker.deleteLater)
        self.acq_thread.finished.connect(self.acq_thread.deleteLater)

        self.acq_worker.error.connect(lambda msg: print(f"Acquisition error: {msg}"))
        self.acq_worker.finished.connect(self.on_acq_finished)

        self.acq_thread.start()
        
    def on_acq_finished(self):
        print("=== Acquisition finished ===")
        # Re-enable buttons if you disabled them
        # self.some_acq_button.setEnabled(True)

    def handle_run_matrix(self):
        print("\n=== Running Matrix Creation Only ===")
        try:
            params = self.gather_acq_params()
            run_matrix_creation(params)
        except Exception as e:
            print(f"Error during matrix creation: {e}")

    def handle_run_full(self):
        """
        print("\n=== Running Acquisition + Matrix ===")
        try:
            params = self.gather_acq_params()
            run_scan_full(params)
        except Exception as e:
            print(f"Error during acquisition + matrix: {e}")
        """
        print("\n=== Running Acquisition + Matrix (threaded) ===")
        try:
            params = self.gather_acq_params()
        except Exception as e:
            print(f"Error gathering acquisition params: {e}")
            return

        self.full_thread = QThread()
        self.full_worker = AcquisitionWorker(params, run_scan_full)
        self.full_worker.moveToThread(self.full_thread)

        self.full_thread.started.connect(self.full_worker.run)
        self.full_worker.finished.connect(self.full_thread.quit)
        self.full_worker.finished.connect(self.full_worker.deleteLater)
        self.full_thread.finished.connect(self.full_thread.deleteLater)

        self.full_worker.error.connect(lambda msg: print(f"Acq+Matrix error: {msg}"))
        self.full_worker.finished.connect(self.on_full_finished)

        self.full_thread.start()

    def on_full_finished(self):
        print("=== Acquisition + Matrix finished ===")

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


    ## for manual stage movement
    
        # ---------- Stage handlers ----------

    def handle_stage_home(self):
        print("\n=== Stage: Home ===")
        try:
            params = self.gather_acq_params()
            stage_home(params)
            self.handle_stage_status()
        except Exception as e:
            print(f"Stage home error: {e}")

    def handle_stage_start(self):
        print("\n=== Stage: Go to Scan START ===")
        try:
            params = self.gather_acq_params()
            stage_go_scan_start(params)
            self.handle_stage_status()
        except Exception as e:
            print(f"Stage start error: {e}")

    def handle_stage_mid(self):
        print("\n=== Stage: Go to MIDPOINT ===")
        try:
            params = self.gather_acq_params()
            stage_go_midpoint(params)
            self.handle_stage_status()
        except Exception as e:
            print(f"Stage midpoint error: {e}")

    def handle_stage_end(self):
        print("\n=== Stage: Go to Scan END ===")
        try:
            params = self.gather_acq_params()
            stage_go_scan_end(params)
            self.handle_stage_status()
        except Exception as e:
            print(f"Stage end error: {e}")

    def handle_stage_goto(self):
        print("\n=== Stage: Go To Absolute Position ===")
        try:
            params = self.gather_acq_params()
            pos = float(self.stage_abs_pos.text())
            stage_move_absolute(params, pos)
            self.handle_stage_status()
        except Exception as e:
            print(f"Stage goto error: {e}")


    def handle_stage_jog_minus(self):
        print("\n=== Stage: Jog - ===")
        try:
            params = self.gather_acq_params()
            step = float(self.stage_jog_step.text())
            stage_jog(params, -step)
            self.handle_stage_status()
        except Exception as e:
            print(f"Stage jog- error: {e}")

    def handle_stage_jog_plus(self):
        print("\n=== Stage: Jog + ===")
        try:
            params = self.gather_acq_params()
            step = float(self.stage_jog_step.text())
            stage_jog(params, step)
            self.handle_stage_status()
        except Exception as e:
            print(f"Stage jog+ error: {e}")

    def handle_stage_stop(self):
        print("\n=== Stage: Stop ===")
        try:
            params = self.gather_acq_params()
            stage_stop(params)
            self.handle_stage_status()
        except Exception as e:
            print(f"Stage stop error: {e}")

    def handle_stage_status(self):
        print("\n=== Stage: Get Status ===")
        try:
            params = self.gather_acq_params()
            status = stage_get_status(params)
            if status is not None:
                pos = status["position_mm"]
                busy = status["is_busy"]
                parked = status["is_parked"]
                state_parts = []
                state_parts.append("MOVING" if busy else "IDLE")
                if parked:
                    state_parts.append("PARKED")
                state_str = ", ".join(state_parts)
                self.stage_status_label.setText(
                    f"Position: {pos:.4f} mm, State: {state_str}"
                )
        except Exception as e:
            print(f"Stage status error: {e}")


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
