# config.py
"""
Default configuration dictionaries for the Zaber FROG application.
These are just starting values; the GUI will load and let you edit them.
"""

# Defaults for acquisition + matrix creation
ACQ_DEFAULTS = {
    "SAVE_DIR": "D:/allCodes/zaber_FROG/trial_data11",
    "PORT_NAME": "COM3",
    "BAUD_RATE": 9600,
    "DEVICE_ADDRESS": 2,
    "STEP_SIZE_MM": 0.0001,
    "SCAN_DISTANCE_MM": 0.250,
    "SPEC_INT_TIME_MS": 300,
    "TOTAL_TRAVEL_RANGE": 28.0,
    "APPROX_MIDPOINT": 14.78,
    # matrix / post-proc (first stage)
    "central_wavelength": 519.0,
    "bandwidth": 80.0,
    "crop_time_range_fs": [-150.0, 150.0],
}

# If you ever want slightly different defaults when doing
# matrix-only runs, you can override here; for now reuse ACQ.
MATRIX_DEFAULTS = {
    "SAVE_DIR": ACQ_DEFAULTS["SAVE_DIR"],
    "central_wavelength": ACQ_DEFAULTS["central_wavelength"],
    "bandwidth": ACQ_DEFAULTS["bandwidth"],
    "crop_time_range_fs": ACQ_DEFAULTS["crop_time_range_fs"],
}

# Defaults for FROG post-processing on full_spectrum_data.npz
FROG_DEFAULTS = {
    "FOLDER": "D:/allCodes/zaber_FROG/trial_data11",
    "FILENAME": "full_spectrum_data.npz",
    "APPROX_PULSE_WIDTH": 400.0,   # fs
    "PADDING_THICKNESS": 0.05,     # 5%
    "TOTAL_DIMENSION": 512,
}
