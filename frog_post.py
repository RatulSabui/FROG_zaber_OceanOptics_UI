# frog_post.py

import os
import numpy as np
import matplotlib.pyplot as plt
from scipy.fft import fft, ifft, fftshift, ifftshift
from scipy.interpolate import RegularGridInterpolator, interp1d
from scipy.signal import find_peaks
from scipy.ndimage import uniform_filter1d, maximum_filter1d


# ===================== I/O & BASIC HELPERS =====================

def read_npz_file(filename):
    npzfile = np.load(filename)
    intensity_matrix = npzfile['intensity_matrix']
    wavelengths = npzfile['wavelengths']
    delays_fs = npzfile['delays_fs']
    distances = npzfile['distances']
    return intensity_matrix, wavelengths, delays_fs, distances


def calculate_equal_square_padding(target_size, padding_fraction):
    """
    Calculate original square matrix size and equal padding thickness on all four sides.

    target_size: final size after padding (e.g. 512)
    padding_fraction: fraction of target size used as total padding (e.g. 0.1 for 10%)
    """
    total_padding = round(target_size * padding_fraction)
    total_padding_adjusted = 4 * round(total_padding / 4)
    original_size = target_size - total_padding_adjusted
    pad_each_side = total_padding_adjusted // 4
    return original_size, pad_each_side


def plot_and_save_intensity_colormesh(delays, wavelengths, counts_matrix, save_path,
                                      title="Intensity Colormesh", cmap='viridis',
                                      x_range=None, y_range=None):
    """
    Plot the counts matrix as a colormesh image and save it as a PNG file without displaying it.
    """
    plt.figure(figsize=(8, 6))

    delay_edges = np.linspace(delays[0], delays[-1], len(delays) + 1)
    wavelength_edges = np.linspace(wavelengths[0], wavelengths[-1], len(wavelengths) + 1)

    mesh = plt.pcolormesh(delay_edges, wavelength_edges, counts_matrix, shading='auto', cmap=cmap)

    plt.xlabel('Delay')
    plt.ylabel('Wavelength')
    plt.title(title)
    plt.colorbar(mesh, label='Counts')

    if x_range is not None:
        plt.xlim(x_range)
    if y_range is not None:
        plt.ylim(y_range)

    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()


# ===================== CENTERING & CROPPING =====================

def center_delay_axis_by_peak(counts_matrix, delay_array):
    """
    Shift delay axis so the peak column (max summed counts) is at zero.
    """
    column_sums = counts_matrix.sum(axis=0)
    peak_col_index = np.argmax(column_sums)
    peak_delay = delay_array[peak_col_index]
    new_delay_array = delay_array - peak_delay
    return new_delay_array, peak_delay, peak_col_index


def crop_matrix_by_delay_range(centered_delay_array, intensity_matrix, selection_range):
    """
    Keep only columns where |delay| <= selection_range.
    """
    mask = np.abs(centered_delay_array) <= selection_range
    cropped_delays = centered_delay_array[mask]
    cropped_matrix = intensity_matrix[:, mask]
    return cropped_delays, cropped_matrix


def crop_matrix_to_square_by_max_row_sum(intensity_matrix, y_axis_array):
    """
    Crop matrix & y-axis to a square based on row with maximum row-sum.
    """
    num_cols = intensity_matrix.shape[1]
    row_sums = intensity_matrix.sum(axis=1)
    max_row_idx = np.argmax(row_sums)

    half_size = num_cols // 2
    start_row = max(0, max_row_idx - half_size)
    end_row = start_row + num_cols

    if end_row > intensity_matrix.shape[0]:
        end_row = intensity_matrix.shape[0]
        start_row = max(0, end_row - num_cols)

    cropped_matrix = intensity_matrix[start_row:end_row, :]
    cropped_y_axis = y_axis_array[start_row:end_row]

    return cropped_y_axis, cropped_matrix


def get_matrix_properties(x_axis_array, y_axis_array):
    """
    Basic properties and calibrations from axes.
    """
    width = len(x_axis_array)
    height = len(y_axis_array)

    if width > 1:
        temporal_calibration = (x_axis_array[-1] - x_axis_array[0]) / (width - 1)
    else:
        temporal_calibration = 0.0

    if height > 1:
        spectral_calibration = (y_axis_array[-1] - y_axis_array[0]) / (height - 1)
    else:
        spectral_calibration = 0.0

    central_idx = height // 2
    central_wavelength = y_axis_array[central_idx]

    return width, height, temporal_calibration, spectral_calibration, central_wavelength


# ===================== BACKGROUND, LINEARIZATION, BINNING =====================

def background_subtract(Isig, freq_sub=0, delay_sub=0):
    """
    Subtract background along frequency (rows) and/or delay (cols).
    """
    A = Isig.copy()

    if freq_sub != 0:
        min_freq = np.min(A, axis=1, keepdims=True)
        A = A - freq_sub * min_freq

    if delay_sub != 0:
        min_delay = np.min(A, axis=0, keepdims=True)
        A = A - delay_sub * min_delay

    return A


def enforce_nonnegativity(Isig):
    """
    Clip negative values to zero.
    """
    return np.clip(Isig, 0, None)


def bin_to_uniform_grid(Isig, Tau, Lam, N_tau_out, N_lam_out):
    """
    Interpolate Isig onto uniform delay and wavelength axes.
    """
    Tau_new = np.linspace(Tau.min(), Tau.max(), N_tau_out)
    Lam_new = np.linspace(Lam.min(), Lam.max(), N_lam_out)

    Tau_grid, Lam_grid = np.meshgrid(Tau_new, Lam_new)

    interp_func = RegularGridInterpolator((Lam, Tau), Isig, bounds_error=False, fill_value=0)
    points = np.array([Lam_grid.ravel(), Tau_grid.ravel()]).T
    Isig_binned = interp_func(points).reshape(N_lam_out, N_tau_out)

    return Isig_binned, Tau_new, Lam_new


def wavelength_to_frequency(Lam, Isig, c=299792458):
    """
    Convert wavelength axis (nm) to frequency (Hz), reordering matrix accordingly.
    """
    Lam_m = Lam * 1e-9
    freq = c / Lam_m
    freq = freq[::-1]
    Isig_freq = Isig[::-1, :]
    return freq, Isig_freq


def next_power_of_two(n):
    return 1 << (n - 1).bit_length()


def pad_matrix_and_extend_axes(matrix, freq, delay, extra_x=0, extra_y=0, enforce_power_of_two=True):
    """
    Pad 2D matrix and extend freq/delay axes by linear extrapolation.
    """
    x, y = matrix.shape
    target_x = x + extra_x
    target_y = y + extra_y

    if enforce_power_of_two:
        target_x = next_power_of_two(target_x)
        target_y = next_power_of_two(target_y)

    pad_x = target_x - x
    pad_y = target_y - y

    pad_left = pad_x // 2
    pad_right = pad_x - pad_left
    pad_top = pad_y // 2
    pad_bottom = pad_y - pad_top

    padded_matrix = np.pad(
        matrix,
        pad_width=((pad_left, pad_right), (pad_top, pad_bottom)),
        mode='constant',
        constant_values=0
    )

    freq_spacing_start = freq[1] - freq[0]
    freq_spacing_end = freq[-1] - freq[-2]
    freq_extended_start = freq[0] - np.arange(pad_left, 0, -1) * freq_spacing_start
    freq_extended_end = freq[-1] + np.arange(1, pad_right + 1) * freq_spacing_end
    freq_extended = np.concatenate((freq_extended_start, freq, freq_extended_end))

    delay_spacing_start = delay[1] - delay[0]
    delay_spacing_end = delay[-1] - delay[-2]
    delay_extended_start = delay[0] - np.arange(pad_top, 0, -1) * delay_spacing_start
    delay_extended_end = delay[-1] + np.arange(1, pad_bottom + 1) * delay_spacing_end
    delay_extended = np.concatenate((delay_extended_start, delay, delay_extended_end))

    return padded_matrix, freq_extended, delay_extended


def intensity_to_amplitude(intensity_matrix):
    """
    Convert intensity to amplitude by sqrt, enforcing nonnegativity.
    """
    intensity_nonneg = np.clip(intensity_matrix, 0, None)
    amplitude_matrix = np.sqrt(intensity_nonneg)
    return amplitude_matrix


def linearize_intensity_wavelength(wavelengths, intensity_matrix):
    """
    Re-interpolate intensity to a linearly spaced wavelength grid.
    """
    linear_wavelengths = np.linspace(wavelengths.min(), wavelengths.max(), len(wavelengths))
    interp_func = interp1d(wavelengths, intensity_matrix, axis=0,
                           kind='linear', bounds_error=False, fill_value=0)
    linear_intensity = interp_func(linear_wavelengths)
    return linear_wavelengths, linear_intensity


# ===================== OUTPUT FORMATS & DIAGNOSTICS =====================

def save_to_frg(filename, intensity_matrix, temporal_calibration, central_wavelength, spectral_calibration):
    """
    Save FROG trace intensity to .frg format.
    """
    height, width = intensity_matrix.shape
    with open(filename, 'w') as f:
        header_line = f"{width}\t{height}\t{temporal_calibration}\t{spectral_calibration}\t{central_wavelength}\n"
        f.write(header_line)
        for row in intensity_matrix:
            row_str = '\t'.join(f"{val:.6e}" for val in row)
            f.write(row_str + '\n')


def plot_central_slices(delay_array, wavelength_array, intensity_matrix, save_dir):
    """
    Plot central row (vs delay) and central column (vs wavelength).
    """
    central_row_idx = intensity_matrix.shape[0] // 2
    central_row_intensity = intensity_matrix[central_row_idx, :]

    plt.figure()
    plt.plot(delay_array, central_row_intensity, '-b')
    plt.xlabel('Delay')
    plt.ylabel('Intensity')
    plt.title('Central Row Intensity vs Delay')
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(f'{save_dir}/central_row_vs_delay.png')
    plt.close()

    central_col_idx = intensity_matrix.shape[1] // 2
    central_col_intensity = intensity_matrix[:, central_col_idx]

    plt.figure()
    plt.plot(wavelength_array, central_col_intensity, '-r')
    plt.xlabel('Wavelength')
    plt.ylabel('Intensity')
    plt.title('Central Column Intensity vs Wavelength')
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(f'{save_dir}/central_column_vs_wavelength.png')
    plt.close()


# ===================== HIGH-LEVEL API =====================

def run_frog_post(params: dict):
    """
    Full FROG post-processing pipeline starting from full_spectrum_data.npz.

    Expected params keys:
        FOLDER: folder containing the npz
        FILENAME: name of npz file (e.g. 'full_spectrum_data.npz')
        APPROX_PULSE_WIDTH: in same delay units as delays_fs (typically fs)
        PADDING_THICKNESS: fractional padding (e.g. 0.05 for 5%)
        TOTAL_DIMENSION: target dimension (e.g. 512)
    """
    folder = params["FOLDER"]
    filename = params["FILENAME"]
    approx_pulse_width = params["APPROX_PULSE_WIDTH"]
    padding_thickness = params["PADDING_THICKNESS"]
    total_dimension = params["TOTAL_DIMENSION"]

    if 'window' in params:
        global window
        window = params['window']

    save_path = os.path.join(folder, "output")
    if not os.path.exists(save_path):
        os.makedirs(save_path)

    file_path = os.path.join(folder, filename)

    orig_size, pad_side = calculate_equal_square_padding(total_dimension, padding_thickness)

    intensity_matrix, wavelengths, delay_array, distances = read_npz_file(file_path)
    print("Intensity matrix shape:", intensity_matrix.shape)
    print("Initial Wavelength array length:", len(wavelengths))
    print("Initial Delays array length:", len(delay_array))

    # 1) Center delay axis
    centered_delay_array, peak_delay, peak_col_idx = center_delay_axis_by_peak(
        intensity_matrix, np.array(delay_array)
    )

    centered_op = os.path.join(save_path, 'centered_matrix.png')
    plot_and_save_intensity_colormesh(centered_delay_array, wavelengths,
                                      intensity_matrix, centered_op,
                                      title="Intensity (Peak Centered)", cmap='viridis')

    # 2) Background subtract + nonnegativity
    Isig_temp = background_subtract(intensity_matrix, freq_sub=1.0, delay_sub=1.0)
    intensity_matrix = enforce_nonnegativity(Isig_temp)

    # 3) Linearize wavelength axis
    wavelengths, intensity_matrix = linearize_intensity_wavelength(wavelengths, intensity_matrix)

    # 4) Crop by delay range
    cropped_delays, cropped_matrix = crop_matrix_by_delay_range(
        centered_delay_array, intensity_matrix, selection_range=approx_pulse_width
    )

    # 5) Crop to square around max row
    cropped_wavelengths, cropped_matrix = crop_matrix_to_square_by_max_row_sum(
        cropped_matrix, wavelengths
    )

    width, height, temp_calib, spec_calib, center_wl = get_matrix_properties(
        cropped_delays, cropped_wavelengths
    )
    print("After Cropping.")
    print(f"Width (x-axis length): {width}")
    print(f"Height (y-axis length): {height}")
    print(f"Temporal calibration: {temp_calib}")
    print(f"Spectral calibration: {spec_calib}")
    print(f"Central wavelength: {center_wl}")

    cropped_op = os.path.join(save_path, 'cropped_matrix.png')
    plot_and_save_intensity_colormesh(cropped_delays, cropped_wavelengths,
                                      cropped_matrix, cropped_op,
                                      title="Intensity (Cropped)", cmap='viridis')


    print("Generating cropped matrix plot...")
    fig_cropped = plt.figure(figsize=(8, 6))
    delay_edges = np.linspace(cropped_delays[0], cropped_delays[-1], len(cropped_delays) + 1)
    wave_edges = np.linspace(cropped_wavelengths[0], cropped_wavelengths[-1], len(cropped_wavelengths) + 1)
    plt.pcolormesh(delay_edges, wave_edges, cropped_matrix, shading='auto', cmap='viridis')
    plt.colorbar(label='Intensity')
    plt.xlabel('Delay (fs)')
    plt.ylabel('Wavelength (nm)')
    plt.title('Cropped Matrix')
    window.plot_ready.emit(fig_cropped, "Cropped Matrix", "Intensity map after delay and wavelength cropping")
    plt.close(fig_cropped)

    # 6) Bin to uniform grid
    matrix_uniform, delay_uniform, wavelength_uniform = bin_to_uniform_grid(
        cropped_matrix, cropped_delays, cropped_wavelengths, orig_size, orig_size
    )

    # 7) Convert to frequency axis
    freq, Isig_freq = wavelength_to_frequency(wavelength_uniform, matrix_uniform)

    # 8) Pad to power-of-two
    padded_mat, freq_ext, delay_ext = pad_matrix_and_extend_axes(
        Isig_freq, freq, delay_uniform,
        extra_x=pad_side, extra_y=pad_side,
        enforce_power_of_two=True
    )

    # 9) Intensity → amplitude (optional, here we just compute it)
    amp_matrix = intensity_to_amplitude(padded_mat)

    amp_mat_op = os.path.join(save_path, 'amp_matrix.png')
    plot_and_save_intensity_colormesh(delay_ext, freq_ext,
                                      padded_mat, amp_mat_op,
                                      title="Intensity (Padded)", cmap='viridis')

    # 10) Save .frg
    frg_file_path = os.path.join(save_path, 'frog_trace.frg')
    save_to_frg(frg_file_path, padded_mat, temp_calib, center_wl, spec_calib)

    # 11) Linecuts
    plot_central_slices(delay_ext, freq_ext, padded_mat, save_path)

    print("Generating linecut plots...")
    fig_linecuts = plt.figure(figsize=(12, 5))

    # Central row
    plt.subplot(1, 2, 1)
    plt.plot(delay_ext, padded_mat[height//2, :], '-b')
    plt.xlabel('Delay (fs)')
    plt.ylabel('Intensity')
    plt.title('Central Row vs Delay')
    plt.grid(True)

    # Central column  
    plt.subplot(1, 2, 2)
    plt.plot(freq_ext, padded_mat[:, width//2], '-r')
    plt.xlabel('Frequency (Hz)')
    plt.ylabel('Intensity')
    plt.title('Central Column vs Frequency')
    plt.grid(True)

    plt.tight_layout()
    window.plot_ready.emit(fig_linecuts, "Central Linecuts", 
                        "Central row (intensity vs delay) and central column (intensity vs frequency)")
    plt.close(fig_linecuts)

    width, height, temp_calib2, spec_calib2, center_wl2 = get_matrix_properties(
        delay_ext, freq_ext
    )
    print("After Saving to frg.")
    print(f"Width (x-axis length): {width}")
    print(f"Height (y-axis length): {height}")
    print(f"Temporal calibration: {temp_calib2}")
    print(f"Spectral calibration: {spec_calib2}")
    print(f"Central wavelength: {center_wl2}")


# Optional CLI test
if __name__ == "__main__":
    params = {
        "FOLDER": "D:/allCodes/zaber_FROG/trial_data8",
        "FILENAME": "full_spectrum_data.npz",
        "APPROX_PULSE_WIDTH": 400,      # fs
        "PADDING_THICKNESS": 0.05,      # 5%
        "TOTAL_DIMENSION": 512,
    }
    run_frog_post(params)
