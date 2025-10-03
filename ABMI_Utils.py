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
import threading
from pyOpenBCI import OpenBCICyton
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds

# --- Constants ---
SERIES_R = 2200.0			# Series resistance (2.2 kΩ)
I_DRIVE = 6.0e-9			# Lead-off drive current (6 nA default)
MEAS_SEC = 2.0				# Measurement duration in seconds
SETTLE_SEC = 2.0			# Settling time after switching lead-off
BAND = (5, 50)				# Bandpass filter range (Hz)
CABLE_COLORS = ['gray', 'purple', 'blue', 'green', 'yellow', 'orange', 'red', 'brown']

class BCIBoard:
	def __init__(self, port="/dev/ttyUSB0"):
		self.port = port
		self.board = None
		self.board_id = BoardIds.CYTON_BOARD.value
		self.fs = BoardShim.get_sampling_rate(self.board_id)
		self.channels = list(range(1, 9))  # default 8 channels

	def connect(self):
		BoardShim.disable_board_logger()
		params = BrainFlowInputParams()
		params.serial_port = self.port
		self.board = BoardShim(self.board_id, params)

		try:
			self.board.prepare_session()
			self.board.start_stream()
			print(f"Connected to OpenBCI board at {self.port}")
			return True

		except Exception as e:
			print(f"Failed to connect to OpenBCI board at {self.port}: {e}")
			try:
				self.board.release_session()
			except Exception:
				pass
			self.board = None
			return False

	def disconnect(self):
		if self.board:
			try:
				self.board.stop_stream()
				self.board.release_session()
				print(f"[BCIBoard] Disconnected from board at {self.port}")
			except Exception:
				pass
			self.board = None

	def stream(self, callback=None):
		if not self.board:
			print("[BCIBoard] Cannot start streaming: board not connected")
			return

		eeg_idxs = BoardShim.get_eeg_channels(self.board_id)
		try:
			ts_idx = BoardShim.get_timestamp_channel(self.board_id)
		except Exception:
			ts_idx = None

		def _worker():
			while True:
				data = self.board.get_board_data()
				if data.size > 0 and callback:
					num_samples = data.shape[1]
					for i in range(num_samples):
						sample = {
							"timestamp": float(data[ts_idx, i]) if ts_idx is not None else None,
							"eeg": data[eeg_idxs, i]
						}
						try:
							callback(sample)
						except Exception:
							pass
				time.sleep(0.01)

		threading.Thread(target=_worker, daemon=True).start()
		print(f"[BCIBoard] Started streaming from board at {self.port}")

	def check_impedance(self, channels=None):
		channels = channels or self.channels
		results = []

		if not self.board:
			print("Board not connected. Cannot check impedance.")
			return results

		print("Starting impedance check...")

		for ch in channels:
			color = CABLE_COLORS[ch - 1] if 1 <= ch <= len(CABLE_COLORS) else "black"
			print(f"Measuring CH{ch} ({color})...")

			try:
				set_ads_to_impedance_on(self.board, ch)
				send_leadoff(self.board, ch, 0, 1)  # enable lead-off
				time.sleep(SETTLE_SEC)

				self.board.get_board_data()  # clear buffer
				time.sleep(MEAS_SEC + 0.2)
				data = self.board.get_board_data()

				row = BoardShim.get_eeg_channels(self.board_id)[ch - 1]
				x_uV = data[row, :]
				x_bp = bandpass_apply(x_uV, self.fs)
				uVrms = take_recent_1s(x_bp, self.fs)
				z_kohm = calc_impedance_from_vrms(uVrms) / 1000.0

				results.append((ch, z_kohm))
				print(f"CH{ch} ({color}): {z_kohm:.2f} kΩ")

			except Exception as e:
				results.append((ch, float('nan')))
				print(f"Failed to measure CH{ch}: {e}")

			finally:
				try:
					send_leadoff(self.board, ch, 0, 0)  # disable lead-off
				except Exception:
					pass

		print("Impedance check complete.")
		return results

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

'''
if __name__ == "__main__":
	impedance_list = check_impedance(channels=[1,2,3,4,5,6,7,8])
	print("\n=== Summary ===")
	for ch, z in impedance_list:
		color = CABLE_COLORS[ch - 1] if 1 <= ch <= len(CABLE_COLORS) else 'black'
		print(f"CH{ch}({color}): {z:.2f} kΩ")
'''
