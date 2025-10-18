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
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds, BrainFlowError
import os
import random
import pygame

# --- Constants ---
SERIES_R = 2200.0			# Series resistance (2.2 kΩ)
I_DRIVE = 6.0e-9			# Lead-off drive current (6 nA default)
MEAS_SEC = 2.0				# Measurement duration in seconds
SETTLE_SEC = 2.0			# Settling time after switching lead-off
BAND = (5, 50)				# Bandpass filter range (Hz)

# Hand-coded color table for cable impedance display
# Each color is defined as RGB tuple (0-255 range)
CABLE_COLORS_RGB = [
    (120, 120, 120),  # Channel 1: Gray
    (129, 37, 186),    # Channel 2: Purple  
    (19, 26, 120),      # Channel 3: Blue
    (24, 168, 101),      # Channel 4: Green
    (196, 187, 16),    # Channel 5: Yellow
    (219, 120, 13),    # Channel 6: Orange
    (196, 0, 0),      # Channel 7: Red
    (107, 54, 29)     # Channel 8: Brown
]

# Legacy string color names for backward compatibility
CABLE_COLORS = ['gray', 'purple', 'blue', 'green', 'yellow', 'orange', 'red', 'brown']

class BCIBoard:
	def __init__(self, port="/dev/ttyUSB0"):
		self.port = port
		self.board = None
		self.board_id = BoardIds.CYTON_BOARD.value
		self.fs = BoardShim.get_sampling_rate(self.board_id)
		self.channels = list(range(1, 9))  # default 8 channels
		self.connected = False
		self.streaming = False
		self._last_data_time = None
		self._stream_thread = None

	def connect(self):
		BoardShim.disable_board_logger()
		params = BrainFlowInputParams()
		params.serial_port = self.port
		self.board = BoardShim(self.board_id, params)

		try:
			self.board.prepare_session()
			self.board.start_stream()
			print(f"Connected to OpenBCI board at {self.port}")
			self.connected = True
			self._last_data_time = None
			self.streaming = False
			return True

		except Exception as e:
			print(f"Failed to connect to OpenBCI board at {self.port}: {e}")
			try:
				self.board.release_session()
			except Exception:
				pass
			self.board = None
			self.connected = False
			self.streaming = False
			self._last_data_time = None
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
		self.connected = False
		self.streaming = False
		self._last_data_time = None
		self._stream_thread = None

	def _refresh_stream_state(self, stale_timeout=1.5, probe=False):
		if not self.streaming:
			return False

		if not self.board:
			self.streaming = False
			self.connected = False
			self._last_data_time = None
			return False

		if probe:
			try:
				data = self.board.get_current_board_data(1)
				if data.size > 0:
					self._last_data_time = time.time()
			except BrainFlowError as e:
				print(f"[BCIBoard] Streaming probe failed: {e}")
				self.streaming = False
				self.connected = False
				self._last_data_time = None
				return False
			except Exception as e:
				print(f"[BCIBoard] Unexpected streaming probe error: {e}")
				self.streaming = False
				self.connected = False
				self._last_data_time = None
				return False

		if self._last_data_time is None:
			self._last_data_time = time.time()

		if time.time() - self._last_data_time > stale_timeout:
			print(f"[BCIBoard] No data received for {stale_timeout} s; marking board disconnected.")
			self.streaming = False
			self.connected = False
			self._last_data_time = None
			return False

		return True

	def stream(self, callback=None):
		if not self.board or not self.connected:
			print("[BCIBoard] Cannot start streaming: board not connected")
			return False

		if self.streaming:
			print("[BCIBoard] Streaming already in progress")
			return True

		self.streaming = True
		self._last_data_time = None

		eeg_idxs = BoardShim.get_eeg_channels(self.board_id)
		try:
			ts_idx = BoardShim.get_timestamp_channel(self.board_id)
		except Exception:
			ts_idx = None

		def _worker():
			stale_timeout = 1.5
			while self.streaming and self.board:
				if not self._refresh_stream_state(stale_timeout=stale_timeout):
					break

				try:
					data = self.board.get_board_data()
				except BrainFlowError as e:
					print(f"[BCIBoard] Stream error: {e}")
					self.connected = False
					self.streaming = False
					self._last_data_time = None
					break
				except Exception as e:
					print(f"[BCIBoard] Unexpected stream error: {e}")
					self.connected = False
					self.streaming = False
					self._last_data_time = None
					break

				if data.size > 0:
					self._last_data_time = time.time()
					if callback:
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
				else:
					time.sleep(0.05)
					continue

				time.sleep(0.01)

			self.streaming = False
			if not self.connected:
				self._last_data_time = None
			self._stream_thread = None

		self._stream_thread = threading.Thread(target=_worker, daemon=True)
		self._stream_thread.start()
		print(f"[BCIBoard] Started streaming from board at {self.port}")
		return True

	def stop_stream(self, wait=True, clear_last_time=True):
		"""Stop the worker thread and optionally clear timing state while staying connected."""
		self.streaming = False
		thread = self._stream_thread
		if thread and thread.is_alive():
			if wait:
				thread.join(timeout=1.0)
		self._stream_thread = None
		if clear_last_time:
			self._last_data_time = None

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

# ---- Mark implemented functions ---- #

def play_single_sound(filepath="beep_left.wav"):
	"""
	Play a .wav file asynchronously (non-blocking) using pygame.
	"""
	if not os.path.exists(filepath):
		print(f"[Sound] File not found: {filepath}")
		return

	def _play():
		try:
			sound = pygame.mixer.Sound(filepath)
			sound.play()  # non-blocking
		except Exception as e:
			print(f"[Sound] Failed to play sound: {e}")

	threading.Thread(target=_play, daemon=True).start()

def createSessionFolder(user_id, timestamp, base_path="BMI Trainer Data/"):
	'''Create a session folder named '<user_id>-YYYY-MM-DD-HH-MM' inside base_path.'''
	if not isinstance(user_id, str):
		user_id = str(user_id)
	if len(user_id) != 9 or not user_id.isdigit():
		raise ValueError('user_id must be a 9-digit string')

	if hasattr(timestamp, 'strftime'):
		timestamp_str = timestamp.strftime('%Y-%m-%d-%H-%M')
	else:
		timestamp_str = str(timestamp)

	folder_name = f"{user_id}-{timestamp_str}"
	base_dir = os.path.abspath(base_path)
	os.makedirs(base_dir, exist_ok=True)
	full_path = os.path.join(base_dir, folder_name)
	if not os.path.isdir(full_path):
		os.makedirs(full_path)
	return full_path

def deleteEmptyFolders(base_path="BMI Trainer Data/"):
	"""Remove subdirectories under base_path that contain no files."""
	base_dir = os.path.abspath(base_path)
	if not os.path.isdir(base_dir):
		return

	for entry in os.scandir(base_dir):
		if not entry.is_dir():
			continue
		try:
			if not any(Path(entry.path).iterdir()):
				Path(entry.path).rmdir()
		except Exception:
			pass

def getUserID(filepath="BMI Trainer Data/UserID.txt"):
	"""
	Check if the given file exists. If not, create it and save a 9-digit UserID.
	Returns the UserID (as a string).
	"""
	if not os.path.exists(filepath):
		user_id = str(random.randint(100000000, 999999999))
		with open(filepath, "w") as f:
			f.write(user_id)
		print(f"[UserID] Created new file '{filepath}' with ID {user_id}")
	else:
		with open(filepath, "r") as f:
			user_id = f.read().strip()
		if not user_id.isdigit() or len(user_id) != 9:
			user_id = str(random.randint(100000000, 999999999))
			with open(filepath, "w") as f:
				f.write(user_id)
			print(f"[UserID] Invalid file content, generated new ID {user_id}")
		else:
			print(f"[UserID] Found existing ID {user_id}")
	
	return user_id
