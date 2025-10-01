"""
ABMI-Utils.py
Utility functions for BMI-Trainer project.
Core code written and designed by Mikito Ogino
All copyright and intellectual property belongs to Mikito Ogino
"""

# -*- coding: utf-8 -*-
import time
import numpy as np
from scipy.signal import iirfilter, filtfilt
import serial
import serial.tools.list_ports
import time
from pyOpenBCI import OpenBCICyton

from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds

# --- Constants ---
SERIES_R = 2200.0			# Series resistance (2.2 kΩ)
I_DRIVE = 6.0e-9			# Lead-off drive current (6 nA default)
MEAS_SEC = 2.0				# Measurement duration in seconds
SETTLE_SEC = 2.0			# Settling time after switching lead-off
BAND = (5, 50)				# Bandpass filter range (Hz)
CABLE_COLORS = ['gray', 'purple', 'blue', 'green', 'yellow', 'orange', 'red', 'brown']

def handle_sample(sample):
    pass  # placeholder

def connect_openbci():
    ports = serial.tools.list_ports.comports()
    board_port = None

    for port in ports:
        # Handle both named tuple / object and tuple cases
        device = getattr(port, "device", None) or port[0]  # port.device if exists, else port[0]
        desc = getattr(port, "description", "") or port[1]  # optional, for logging
        print(f"Checking port: {device} - Desc: {desc}")

        if "usbserial-DP04VZU5" in device or "ttyUSB" in device or "ttyACM" in device:
            board_port = device
            print(f"Found potential OpenBCI port: {board_port}")
            break

    if board_port is None:
        raise Exception("OpenBCI board not found. Please check the connection.")

    board = OpenBCICyton(port=board_port)
    
    # Run streaming in a background thread to avoid blocking
    import threading
    threading.Thread(target=board.start_stream, args=(handle_sample,), daemon=True).start()

    print(f"Connected to OpenBCI board at {board_port}")
    return board

def set_ads_to_impedance_on(board, ch: int):
	"""
	Configure ADS channel to impedance measurement mode.
	"""
	ads_cmd = f"x{ch}0"		# POWER_DOWN=0 (on)
	ads_cmd += "0"			# GAIN=0 (x1)
	ads_cmd += "0"			# INPUT=NORMAL
	ads_cmd += "1"			# BIAS include
	ads_cmd += "0"			# SRB2 disconnect
	ads_cmd += "0"			# SRB1 disconnect
	ads_cmd += "X"

	board.config_board(ads_cmd)
	time.sleep(0.02)

def reset_to_defaults(board: BoardShim):
	"""
	Reset all channels to Cyton default configuration.
	"""
	try:
		board.config_board("d")
		return True, "OK"
	except Exception as e:
		return False, f"ERR: {e}"
	time.sleep(0.05)

def calc_impedance_from_vrms(vrms_uV):
	"""
	Calculate impedance from Vrms (in microvolts).
	Z = (sqrt(2) * Vrms) / I_drive - R_series
	"""
	Vrms_V = float(vrms_uV) * 1e-6
	Z = (np.sqrt(2.0) * Vrms_V) / I_DRIVE
	Z -= SERIES_R
	return max(Z, 0.0)

def take_recent_1s(x_uV, fs):
	"""
	Take the most recent 1 second of data and compute RMS.
	"""
	n = int(fs * 1.0)
	seg = x_uV[-n:]
	return float(np.std(seg, ddof=0))	# μV

def bandpass_apply(x, fs):
	"""
	Apply a 4th-order Butterworth bandpass filter.
	"""
	b, a = iirfilter(4, [BAND[0]/(fs/2.0), BAND[1]/(fs/2.0)], btype='band', ftype='butter')
	return filtfilt(b, a, x)

def send_leadoff(board, ch, p_apply, n_apply):
	"""
	Send Cyton ASCII command to enable/disable lead-off.
	CHANNEL: '1'..'8'
	P/N: '0' (off) or '1' (on)
	Example: ch1 N-side ON → 'z101Z'
	"""
	cmd = f"z{ch}{p_apply}{n_apply}Z"
	board.config_board(cmd)
	time.sleep(0.02)

def check_impedance(channels=[1,2,3,4,5,6,7,8]):
	"""
	Check electrode impedance for selected channels.
	Returns a list of (channel, impedance in kΩ).
	"""
	port = "/dev/cu.usbserial-DP04WG3L"		# Update to match your device
	if not port:
		raise RuntimeError("Cyton serial port not found.")

	params = BrainFlowInputParams()
	params.serial_port = port
	board_id = BoardIds.CYTON_BOARD.value
	fs = BoardShim.get_sampling_rate(board_id)

	board = BoardShim(board_id, params)

	try:
		board.prepare_session()
		board.start_stream()

		z_list = []

		for ch in channels:
			set_ads_to_impedance_on(board, ch)

			# Enable lead-off (N-side ON)
			send_leadoff(board, ch, 0, 1)

			# Wait for settling
			time.sleep(SETTLE_SEC)

			# Clear buffer
			board.get_board_data()

			# Record data
			time.sleep(MEAS_SEC+0.2)
			data = board.get_board_data()

			# Extract channel data
			eeg_idxs = BoardShim.get_eeg_channels(board_id)
			row = eeg_idxs[ch - 1]

			x_uV = data[row, :]
			x_bp = bandpass_apply(x_uV, fs)
			uVrms = take_recent_1s(x_bp, fs)

			# Compute impedance in kΩ
			z_kohm = (calc_impedance_from_vrms(uVrms) / 1000.0) if np.isfinite(uVrms) else float('nan')
			print(f"CH{ch}({CABLE_COLORS[ch - 1]}): {z_kohm:.2f} kΩ")

			z_list.append((ch, z_kohm))

			# Disable lead-off
			send_leadoff(board, ch, 0, 0)

		board.stop_stream()
		reset_to_defaults(board)
		return z_list

	finally:
		try:
			board.release_session()
		except Exception:
			pass

if __name__ == "__main__":
	impedance_list = check_impedance(channels=[1,2,3,4,5,6,7,8])
	print("\n=== Summary ===")
	for ch, z in impedance_list:
		color = CABLE_COLORS[ch - 1] if 1 <= ch <= len(CABLE_COLORS) else 'black'
		print(f"CH{ch}({color}): {z:.2f} kΩ")