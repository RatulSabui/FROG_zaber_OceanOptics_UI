# Zaber FROG Controller

Automated FROG trace acquisition and processing using Zaber stage + Ocean Insight spectrometer.

## Devices used

1. **Ocean Optics HR4000 Spectrometer** → for capturing the spectrum. Connects to PC via USB A to B connector. 
2. **Zaber T-LA13A actuator coupled to a TSB60M stage** → for changing the delay value on the non-collinear SHG FROG setup

## Workflow
1. **Command line start** → Install all the dependencies and run ui.py
2. **Acquire spectra** → Save CSVs  
3. **Build matrix** → `full_spectrum_data.npz` + diagnostic plots  
4. **FROG post-process** → `frog_trace.frg` + analysis plots

## Code Structure

### `acquisition.py`
**Hardware control + matrix building**

- `run_acquisition(params)`  
  Stage homing → scan → save individual spectra as CSVs (`spectrum_001_0.1234fs_*.csv`)

- `process_spectra(...)`  
  Load CSVs → sort by delay → build intensity matrix → crop → save:  
  - `full_intensity_matrix.npy`  
  - `full_spectrum_data.npz` (wavelengths, delays, distances)  
  - `colormap_delay.png`, `colormap_distance.png`

- `run_matrix_creation(params)`  
  Standalone matrix builder (no hardware)

- `run_scan_full(params)`  
  Convenience: acquisition + matrix

### `frog_post.py`
**FROG trace preparation for retrieval software**

- `run_frog_post(params)`  
  Loads `full_spectrum_data.npz` → centers/crops/linearizes/pads → saves `output/frog_trace.frg` + 5 diagnostic plots:  
  - `centered_matrix.png`  
  - `cropped_matrix.png`  
  - `amp_matrix.png`  
  - `central_row_vs_delay.png`  
  - `central_column_vs_wavelength.png`

### `config.py`
**Default parameters**

- `ACQ_DEFAULTS` → acquisition + matrix params (ports, scan range, crop settings)  
- `FROG_DEFAULTS` → post-processing params (padding, matrix size)

### `ui.py`
**PySide6 graphical interface**

- **Left panel**: Acquisition parameters + buttons  
  - "Load Acq Defaults" | "Acquire Only" | "Matrix Only" | "Acquire + Matrix"

- **Right panel**: FROG parameters + "Run FROG Post-Proc"

- **Bottom**: Live log/output capturing all `print()` statements

## Usage


# Install deps
pip install numpy pandas matplotlib scipy zaber_motion seabreeze PySide6

# Run GUI
python ui.py


**Prerequisites**: Zaber Motion Library + SeaBreeze drivers installed on target PC.

Zaber motion driver is easily available. But one much remember that we here are using legacy Binary communication protocols. There are newer ascii communication protocols but they are not compatible with the stage that we have used in our device.

Seabreeze or the ocean view deivers are not readily available online so Zadig has tro be used to install the relevant drivers.

