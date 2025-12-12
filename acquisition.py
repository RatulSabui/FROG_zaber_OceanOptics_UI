# acquisition.py

import os
import time
import csv
import glob
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import scipy.constants as const

# --- ZABER imports ---
from zaber_motion import Library, Units, LogOutputMode
from zaber_motion.binary import Connection

# --- SEABREEZE imports ---
import seabreeze
seabreeze.use('pyseabreeze')
from seabreeze.spectrometers import Spectrometer


# ===================== UTILS =====================

def ensure_dir(path: str):
    if not os.path.exists(path):
        os.makedirs(path)


def save_spectrum(filename, wavelengths, intensities):
    """Save a single spectrum to CSV."""
    with open(filename, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Wavelength (nm)", "Intensity (a.u.)"])
        writer.writerows(zip(wavelengths, intensities))


def calc_dist_from_time(pulse_width=400):
    """Calculate distance from pulse width (fs → mm)."""
    dist = pulse_width * const.femto * const.c / const.milli
    return dist


def calc_time_from_dist(dist=2):
    """Calculate time (fs) from distance (mm)."""
    time = dist * const.milli / const.c / const.femto
    return time


# ===================== MATRIX CREATION (from CSVs) =====================

def process_spectra(data_dir, central_wavelength, bandwidth, crop_time_range_fs, output_dir):
    """
    Loads CSV spectra files with headers, constructs intensity matrix, crops, saves as numpy and images.
    Creates 2 plots: one with delay (fs) x-axis and another with distance (mm).
    """
    os.makedirs(output_dir, exist_ok=True)
    print("Now processing the csv files.")

    crop_wavelength_range = [central_wavelength - bandwidth / 2, central_wavelength + bandwidth / 2]
    csv_files = sorted(glob.glob(os.path.join(data_dir, "*.csv")))

    if not csv_files:
        print("No CSV files found in data_dir, cannot build matrix.")
        return

    delays = []
    all_intensities = []

    # Iterate over files and collect delays and sorted intensities
    for fname in csv_files:
        base = os.path.basename(fname)
        parts = base.split("_")
        delay_str = parts[2].replace("fs", "")
        delay_fs = float(delay_str)
        delays.append(delay_fs)

        df = pd.read_csv(fname)
        # Sort the data by wavelength column explicitly
        df_sorted = df.sort_values("Wavelength (nm)").reset_index(drop=True)
        all_intensities.append(df_sorted["Intensity (a.u.)"].values)

    delays = np.array(delays)
    distances_sorted = np.array([calc_dist_from_time(d) for d in delays])

    # Use the sorted wavelength axis from the first file
    df_first = pd.read_csv(csv_files[0])
    wavelengths = np.sort(df_first["Wavelength (nm)"].values)

    # Stack columns (each file is one column)
    intensity_matrix = np.column_stack(all_intensities)

    # Sort columns and delay/distances arrays by the delay values
    sorted_indices = np.argsort(delays)
    delays_sorted = delays[sorted_indices]
    distances_sorted = distances_sorted[sorted_indices]
    intensity_matrix = intensity_matrix[:, sorted_indices]

    # Save full data
    np.save(os.path.join(output_dir, "full_intensity_matrix.npy"), intensity_matrix)
    np.save(os.path.join(output_dir, "axes.npy"), {"wavelengths": wavelengths, "delays_fs": delays_sorted})
    np.savez_compressed(
        os.path.join(output_dir, "full_spectrum_data.npz"),
        intensity_matrix=intensity_matrix,
        wavelengths=wavelengths,
        delays_fs=delays_sorted,
        distances=distances_sorted,
    )

    # Crop wavelength
    wave_mask = (wavelengths >= crop_wavelength_range[0]) & (wavelengths <= crop_wavelength_range[1])
    cropped_waves = wavelengths[wave_mask]
    cropped_matrix = intensity_matrix[wave_mask, :]

    # Crop delay/time range
    time_mask = (delays_sorted >= crop_time_range_fs[0]) & (delays_sorted <= crop_time_range_fs[1])
    cropped_delays = delays_sorted[time_mask]
    cropped_distances = distances_sorted[time_mask]
    cropped_matrix = cropped_matrix[:, time_mask]

    np.save(os.path.join(output_dir, "cropped_intensity_matrix.npy"), cropped_matrix)

    # Plot 1: delay (fs) vs wavelength
    plt.figure(figsize=(8, 6))
    plt.pcolormesh(cropped_delays, cropped_waves, cropped_matrix, shading="auto")
    plt.colorbar(label="Intensity (a.u.)")
    plt.xlabel("Delay (fs)")
    plt.ylabel("Wavelength (nm)")
    plt.title("Cropped Intensity Map - Time Domain")
    plt.savefig(os.path.join(output_dir, "colormap_delay.png"))
    plt.close()

    # Plot 2: distance vs wavelength
    plt.figure(figsize=(8, 6))
    plt.pcolormesh(cropped_distances, cropped_waves, cropped_matrix, shading="auto")
    plt.colorbar(label="Intensity (a.u.)")
    plt.xlabel("Distance (mm)")
    plt.ylabel("Wavelength (nm)")
    plt.title("Cropped Intensity Map - Distance Domain")
    plt.savefig(os.path.join(output_dir, "colormap_distance.png"))
    plt.close()

    print("Matrix creation and plots complete.")


def run_matrix_creation(params: dict):
    """
    Builds the intensity matrix and plots from existing CSVs in SAVE_DIR.
    No hardware access.
    """
    SAVE_DIR = params["SAVE_DIR"]
    central_wavelength = params["central_wavelength"]
    bandwidth = params["bandwidth"]
    crop_time_range_fs = params["crop_time_range_fs"]

    print("=== Matrix creation from existing CSVs ===")
    process_spectra(
        data_dir=SAVE_DIR,
        central_wavelength=central_wavelength,
        bandwidth=bandwidth,
        crop_time_range_fs=crop_time_range_fs,
        output_dir=SAVE_DIR,
    )


# ===================== ACQUISITION (hardware → CSVs) =====================

_ACQ_STOP_REQUESTED = False

def reset_acquisition_stop_flag():
    global _ACQ_STOP_REQUESTED
    _ACQ_STOP_REQUESTED = False

def request_acquisition_stop():
    global _ACQ_STOP_REQUESTED
    _ACQ_STOP_REQUESTED = False  # or True if you implement checking in the loop


def run_acquisition(params: dict):
    """
    Connects to stage & spectrometer, scans, saves spectra CSVs into SAVE_DIR.
    Does NOT build the matrix.
    """
    
    print("Acquisition params:", params)
    
    SAVE_DIR = params["SAVE_DIR"]
    PORT_NAME = params["PORT_NAME"]
    BAUD_RATE = params["BAUD_RATE"]
    DEVICE_ADDRESS = params["DEVICE_ADDRESS"]
    STEP_SIZE_MM = params["STEP_SIZE_MM"]
    SCAN_DISTANCE_MM = params["SCAN_DISTANCE_MM"]
    SPEC_INT_TIME_MS = params["SPEC_INT_TIME_MS"]
    TOTAL_TRAVEL_RANGE = params["TOTAL_TRAVEL_RANGE"]
    APPROX_MIDPOINT = params["APPROX_MIDPOINT"]

    print("=== Stage + Spectrometer Acquisition Only ===\n")
    ensure_dir(SAVE_DIR)

    # --------------------- INIT STAGE ---------------------
    print("Connecting to Zaber stage...")
    Library.set_log_output(LogOutputMode.OFF)
    try:
        connection = Connection.open_serial_port(PORT_NAME, baud_rate=BAUD_RATE)
        device = connection.get_device(DEVICE_ADDRESS)
    except Exception as e:
        print(f"Could not connect to stage: {e}")
        return

    print("Stage connected.\n")
    device_identity = device.identify()
    print(device_identity)

    # --------------------- INIT SPECTROMETER ---------------------
    try:
        spec = Spectrometer.from_first_available()
    except Exception as e:
        print(f"Could not connect to spectrometer: {e}")
        connection.close()
        return

    print(f"Spectrometer connected: {spec.model}, SN: {spec.serial_number}")
    spec.integration_time_micros(SPEC_INT_TIME_MS * 1000)

    # --------------------- FIND MIDPOINT ---------------------
    print("\nHoming stage...")
    device.home()
    device.wait_until_idle()
    time.sleep(0.5)

    travel_range = TOTAL_TRAVEL_RANGE
    midpoint = APPROX_MIDPOINT
    midpoint_delay = calc_time_from_dist(midpoint)

    print(f"Assumed total travel range: {travel_range:.2f} mm")
    print(f"Moving to midpoint: {midpoint:.2f} mm\n")

    device.move_absolute(midpoint, Units.LENGTH_MILLIMETRES)
    device.wait_until_idle()
    time.sleep(0.2)

    # --------------------- SCAN SETUP ---------------------
    start_pos = midpoint - SCAN_DISTANCE_MM / 2
    end_pos = midpoint + SCAN_DISTANCE_MM / 2
    num_steps = int(SCAN_DISTANCE_MM / STEP_SIZE_MM) + 1

    print(f"DEBUG: start_pos={start_pos}, end_pos={end_pos}, "
          f"steps={num_steps}, step={STEP_SIZE_MM}, scan={SCAN_DISTANCE_MM}")

    print(f"Scanning from {start_pos:.2f} mm to {end_pos:.2f} mm in {num_steps} steps.")
    ensure_dir(SAVE_DIR)

    wavelengths = spec.wavelengths()

    # --------------------- SCAN LOOP ---------------------
    for i, pos in enumerate(np.linspace(start_pos, end_pos, num_steps)):
        print(f"\n[{i+1}/{num_steps}] Moving to {pos:.3f} mm ...")
        device.move_absolute(pos, Units.LENGTH_MILLIMETRES)
        device.wait_until_idle()
        time.sleep(0.1)

        intensities = spec.intensities()
        time.sleep(SPEC_INT_TIME_MS / 1000)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        delay = calc_time_from_dist(pos) - midpoint_delay
        filename = os.path.join(SAVE_DIR, f"spectrum_{i+1:03d}_{delay:.4f}fs_{timestamp}.csv")
        save_spectrum(filename, wavelengths, intensities)
        print(f"Saved: {os.path.basename(filename)}")
        time.sleep(0.2)

    print("\nScan complete. Returning to midpoint...")
    device.move_absolute(midpoint, Units.LENGTH_MILLIMETRES)
    device.wait_until_idle()
    connection.close()

    # --------------------- LOG ACQUISITION PARAMETERS ---------------------
    logFile = os.path.join(SAVE_DIR, "run_parameters_acq.txt")
    with open(logFile, "w") as f:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"Acquisition Parameters - {now}\n")
        f.write("=" * 60 + "\n")
        f.write(f"SAVE_DIR = {SAVE_DIR}\n")
        f.write(f"PORT_NAME = {PORT_NAME}\n")
        f.write(f"BAUD_RATE = {BAUD_RATE}\n")
        f.write(f"DEVICE_ADDRESS = {DEVICE_ADDRESS}\n")
        f.write(f"STEP_SIZE_MM = {STEP_SIZE_MM}\n")
        f.write(f"SCAN_DISTANCE_MM = {SCAN_DISTANCE_MM}\n")
        f.write(f"SPEC_INT_TIME_MS = {SPEC_INT_TIME_MS}\n")
        f.write(f"TOTAL_TRAVEL_RANGE = {TOTAL_TRAVEL_RANGE}\n")
        f.write(f"APPROX_MIDPOINT = {APPROX_MIDPOINT}\n")
        f.write("=" * 60 + "\n")

    print("Acquisition done.")

# ===================== STAGE UTILITIES (MANUAL CONTROL) =====================

def _open_stage(params):
    """
    Internal helper: open connection and return (connection, device).
    Caller must close connection when done.
    """
    PORT_NAME = params["PORT_NAME"]
    BAUD_RATE = params["BAUD_RATE"]
    DEVICE_ADDRESS = params["DEVICE_ADDRESS"]

    Library.set_log_output(LogOutputMode.OFF)
    connection = Connection.open_serial_port(PORT_NAME, baud_rate=BAUD_RATE)
    device = connection.get_device(DEVICE_ADDRESS)
    device_identity = device.identify()
    print(device_identity)
    return connection, device


def stage_home(params):
    """
    Home the stage and wait until idle.
    """
    print("Stage: homing...")
    try:
        connection, device = _open_stage(params)
    except Exception as e:
        print(f"Stage: could not connect for home(): {e}")
        return

    try:
        device.home()
        device.wait_until_idle()
        pos = device.get_position(Units.LENGTH_MILLIMETRES)
        print(f"Stage: homed, current position = {pos:.4f} mm")
    except Exception as e:
        print(f"Stage: error during home(): {e}")
    finally:
        connection.close()


def stage_get_status(params):
    """
    Query current position and state (busy/parked).
    """
    print("Stage: querying status...")
    try:
        connection, device = _open_stage(params)
    except Exception as e:
        print(f"Stage: could not connect for status(): {e}")
        return None

    try:
        pos = device.get_position(Units.LENGTH_MILLIMETRES)
        busy = device.is_busy()
        parked = False
        try:
            parked = device.is_parked()
        except Exception:
            # Older firmware may not support is_parked
            parked = False

        state = []
        if busy:
            state.append("MOVING")
        else:
            state.append("IDLE")
        if parked:
            state.append("PARKED")

        state_str = ", ".join(state)
        print(f"Stage: position = {pos:.4f} mm, state = {state_str}")
        return {"position_mm": pos, "is_busy": busy, "is_parked": parked}
    except Exception as e:
        print(f"Stage: error during status(): {e}")
        return None
    finally:
        connection.close()


def stage_move_absolute(params, pos_mm):
    """
    Move stage to an absolute position in mm and wait until idle.
    """
    print(f"Stage: moving to absolute position {pos_mm:.4f} mm...")
    try:
        connection, device = _open_stage(params)
    except Exception as e:
        print(f"Stage: could not connect for move_absolute(): {e}")
        return

    try:
        device.move_absolute(pos_mm, Units.LENGTH_MILLIMETRES)
        device.wait_until_idle()
        pos = device.get_position(Units.LENGTH_MILLIMETRES)
        print(f"Stage: move complete, current position = {pos:.4f} mm")
    except Exception as e:
        print(f"Stage: error during move_absolute(): {e}")
    finally:
        connection.close()


def stage_jog(params, delta_mm):
    """
    Move stage by a relative amount delta_mm (can be positive or negative).
    """
    print(f"Stage: jogging by {delta_mm:+.4f} mm...")
    try:
        connection, device = _open_stage(params)
    except Exception as e:
        print(f"Stage: could not connect for jog(): {e}")
        return

    try:
        device.move_relative(delta_mm, Units.LENGTH_MILLIMETRES)
        device.wait_until_idle()
        pos = device.get_position(Units.LENGTH_MILLIMETRES)
        print(f"Stage: jog complete, current position = {pos:.4f} mm")
    except Exception as e:
        print(f"Stage: error during jog(): {e}")
    finally:
        connection.close()


def stage_go_midpoint(params):
    """
    Move to configured midpoint (APPROX_MIDPOINT in mm).
    """
    midpoint = float(params["APPROX_MIDPOINT"])
    print(f"Stage: moving to midpoint {midpoint:.4f} mm...")
    stage_move_absolute(params, midpoint)


def stage_go_scan_start(params):
    """
    Move to start of scan range: midpoint - SCAN_DISTANCE_MM/2.
    """
    midpoint = float(params["APPROX_MIDPOINT"])
    scan = float(params["SCAN_DISTANCE_MM"])
    start_pos = midpoint - scan / 2.0
    print(f"Stage: moving to scan START at {start_pos:.4f} mm...")
    stage_move_absolute(params, start_pos)


def stage_go_scan_end(params):
    """
    Move to end of scan range: midpoint + SCAN_DISTANCE_MM/2.
    """
    midpoint = float(params["APPROX_MIDPOINT"])
    scan = float(params["SCAN_DISTANCE_MM"])
    end_pos = midpoint + scan / 2.0
    print(f"Stage: moving to scan END at {end_pos:.4f} mm...")
    stage_move_absolute(params, end_pos)


def stage_stop(params):
    """
    Stop ongoing movement (if any).
    """
    print("Stage: stop requested...")
    try:
        connection, device = _open_stage(params)
    except Exception as e:
        print(f"Stage: could not connect for stop(): {e}")
        return

    try:
        device.stop(Units.LENGTH_MILLIMETRES)
        device.wait_until_idle()
        pos = device.get_position(Units.LENGTH_MILLIMETRES)
        print(f"Stage: stopped, current position = {pos:.4f} mm")
    except Exception as e:
        print(f"Stage: error during stop(): {e}")
    finally:
        connection.close()

# ===================== CONVENIENCE: ACQ + MATRIX =====================

def run_scan_full(params: dict):
    """
    Convenience: acquisition (CSVs) + matrix creation in one go.
    """
    run_acquisition(params)
    run_matrix_creation(params)


# ===================== OPTIONAL CLI TEST =====================

if __name__ == "__main__":
    # Example parameters for quick testing
    params = {
        "SAVE_DIR": "D:/allCodes/zaber_FROG/trial_data11",
        "PORT_NAME": "COM3",
        "BAUD_RATE": 9600,
        "DEVICE_ADDRESS": 2,
        "STEP_SIZE_MM": 0.0001,
        "SCAN_DISTANCE_MM": 0.250,
        "SPEC_INT_TIME_MS": 300,
        "TOTAL_TRAVEL_RANGE": 28,
        "APPROX_MIDPOINT": 14.78,
        "central_wavelength": 519.0,
        "bandwidth": 80,
        "crop_time_range_fs": [-150, 150],
    }

    # Choose what to test:
    # run_acquisition(params)
    # run_matrix_creation(params)
    run_scan_full(params)
