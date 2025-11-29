"""
ABMI-Utils.py
Utility functions for BMI-Trainer project.
Core code written and designed by Mikito Ogino
All copyright and intellectual property belongs to Mikito Ogino
"""

# -*- coding: utf-8 -*-
import time
import numpy as np
import serial
import serial.tools.list_ports
import time
import threading
import os
import csv
import random
import pygame
import shutil
import queue
import datetime

from pathlib import Path
from scipy.signal import iirfilter, filtfilt
from pyOpenBCI import OpenBCICyton
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds, BrainFlowError
from ftplib import FTP, error_perm, all_errors

# --- Constants ---
SERIES_R = 2200.0			# Series resistance (2.2 kΩ)
I_DRIVE = 6.0e-9			# Lead-off drive current (6 nA default)
MEAS_SEC = 2.0				# Measurement duration in seconds
SETTLE_SEC = 2.0			# Settling time after switching lead-off
BAND = (5, 50)				# Bandpass filter range (Hz)
ISI = 0.35 					# Inter-Stimulus Interval in seconds
SOUND_LENGTH = .15			# Duration of Audio

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

class SingleTrainingSequenceError(Exception):
	"""Raised when a single training sequence fails to start."""

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
  
		#Recording Vars
		self.recording = False
		self.stimulus_sound = 0
		self.sequence_id = 0
		self._record_thread = None
		self._record_stop_event = None
		self._record_file_path = None
		self._sample_queue = queue.Queue(maxsize=1000) #Queue holds up to 4 seconds of data
		self.minimum_recorded_rows = 5800 #20seconds x250, + 500for baseline x2

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
					num_samples = data.shape[1]
					for i in range(num_samples):
						timestamp = float(data[ts_idx, i]) if ts_idx is not None else time.time()
						eeg_values = np.array(data[eeg_idxs, i], copy=True)
						sample = {
							"timestamp": timestamp,
							"eeg": eeg_values,
							"label": self.stimulus_sound,
							"seq": self.sequence_id
						}
						if self.recording and self._record_stop_event and not self._record_stop_event.is_set():
							try:
								self._sample_queue.put_nowait(sample)
							except queue.Full:
								try:
									self._sample_queue.get_nowait()
								except queue.Empty:
									pass
								try:
									self._sample_queue.put_nowait(sample)
								except queue.Full:
									pass
				else:
					time.sleep(0.002)
					continue

				time.sleep(0.001)

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

	def start_recording(self, folder_path, filename=None):
		"""Start a recording worker that logs incoming EEG samples to CSV."""
		if not folder_path:
			raise ValueError('folder_path is required')

		if self.recording:
			print('[BCIBoard] Recording already in progress')
			return False

		folder = Path(folder_path).expanduser().resolve()
		folder.mkdir(parents=True, exist_ok=True)

		if filename:
			file_path = folder / filename
		else:
			timestamp_label = time.strftime('%Y%m%d_%H%M%S')
			file_path = folder / f'eeg_data_{timestamp_label}.csv'

		header = ['Timestamp', 'Ch1', 'Ch2', 'Ch3', 'Ch4', 'Ch5', 'Ch6', 'Ch7', 'Ch8', 'Label', 'Seq']

		stop_event = threading.Event()
		self._record_stop_event = stop_event
		self._record_file_path = str(file_path)
		self._sample_queue = queue.Queue(maxsize=1000)
		sample_queue = self._sample_queue

		def _record_worker():
			rows_written = 0
			should_delete = False
			try:
				with file_path.open('w', newline='') as csvfile:
					writer = csv.writer(csvfile)
					writer.writerow(header)
					while not stop_event.is_set() or not sample_queue.empty():
						if not self.connected or not self.streaming:
							should_delete = True
							stop_event.set()
							while not sample_queue.empty():
								try:
									sample_queue.get_nowait()
								except queue.Empty:
									break
							break

						try:
							sample = sample_queue.get(timeout=0.05)
						except queue.Empty:
							continue

						timestamp = sample.get('timestamp')
						if timestamp is None:
							timestamp = time.time()

						eeg_values = sample.get('eeg')
						if eeg_values is None:
							continue

						row = [float(timestamp)]
						eeg_array = np.asarray(eeg_values).flatten()
						row.extend(float(val) for val in eeg_array[:8])

						label = sample.get('label', '')
						seq = sample.get('seq', '')
						row.append(label if label is not None else '')
						row.append(seq if seq is not None else '')

						writer.writerow(row)
						rows_written += 1
						if rows_written % 50 == 0:
							csvfile.flush()
					csvfile.flush()
			except Exception as e:
				print(f'[BCIBoard] Recording error: {e}')
				should_delete = True
			finally:
				self.recording = False
				self._record_thread = None
				self._record_stop_event = None
				min_rows = getattr(self, "minimum_recorded_rows", None)
				if not should_delete and isinstance(min_rows, int) and min_rows > 0:
					if rows_written < min_rows:
						print(f"[BCIBoard] Recording discarded: only {rows_written} rows (minimum {min_rows}).")
						should_delete = True
				if self._record_file_path and should_delete:
					try:
						Path(self._record_file_path).unlink()
						print(f"[BCIBoard] Discarded incomplete recording: {self._record_file_path}")
					except Exception:
						pass
				self._record_file_path = None
				self._sample_queue = queue.Queue(maxsize=1000)

		self.recording = True
		thread = threading.Thread(target=_record_worker, daemon=True)
		self._record_thread = thread
		thread.start()
		print(f"[BCIBoard] Recording started: {file_path}")
		return str(file_path)

	def stop_recording(self, wait=True):
		"""Signal the recording worker to stop and close resources."""
		stop_event = self._record_stop_event
		if stop_event:
			stop_event.set()

		self.recording = False

		thread = self._record_thread
		if thread and thread.is_alive():
			if wait:
				thread.join(timeout=2.0)

		self._record_thread = None
		self._record_stop_event = None
		self._record_file_path = None
		self._sample_queue = queue.Queue(maxsize=1000)
		print('[BCIBoard] Recording stopped')

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

class CloudConnection:
	def __init__(self, host="ftp.yourdomain.com", user="yourusername", password="yourpassword", timeout=10):
		self.host = host
		self.user = user
		self.password = password
		self.timeout = timeout
		self.ftp = None
		
	def connect(self):
		try:
			self.ftp = FTP(self.host, timeout=self.timeout)
			self.ftp.login(self.user, self.password)
		except Exception as e:
			raise Exception(f"Failed to connect to cloud: {e}")
		return True
	
	def folder_exists(self, user_id):
		if self.ftp is None:
			self.connect()
		folder_path = ("/home/File-EXTERNAL/B2J" + user_id)
		try:
			self.ftp.cwd(folder_path)
			return True
		except error_perm:
			return False
		except Exception as e:
			print(f"Failed to check folder: {e}")
			return False
	
	def create_user_folder(self, user_id):
		if self.ftp is None:
			self.connect()
		try:
			self.ftp.mkd("/home/File-EXTERNAL/B2J" + user_id)
		except error_perm as e:
			raise Exception(f"Failed to create user folder: {e}")
		except Exception as e:
			raise Exception(f"Failed to create user folder: {e}")
		return True
	
	def count_files_in_folder(self, user_id):
		try:
			self.ftp.cwd(f"/home/File-EXTERNAL/B2J{user_id}/")
			return len(self.ftp.nlst())
		except Exception as e:
			raise Exception(f"Failed to count files in user folder: {e}")
		return 0
	
	def upload_all_files(self, remote_root, user_id, local_root="BMI Trainer Data"):
		if self.ftp is None:
			self.connect()

		base_path = Path(local_root)
		if not base_path.exists():
			raise FileNotFoundError(f"Local directory '{local_root}' does not exist.")

		session_dirs = [
			p for p in base_path.iterdir()
			if p.is_dir() and p.name.startswith(user_id)
		]
		
		if not session_dirs:
			print(f"No session folders found for user {user_id} in {local_root}")
			return 0
		
		remote_base = f"/home/File-EXTERNAL/B2J{remote_root}"
		try:
			self.ftp.cwd(remote_base)
		except error_perm:
			print(f"User folder {remote_base} does not exist, creating...")
			self.create_user_folder(user_id)
			self.ftp.cwd(remote_base)
		except Exception as e:
			print(f"Failed to change directory to {remote_base}: {e}")
			return 0

		files_uploaded = 0
		for session_dir in session_dirs:
			for file_path in session_dir.rglob("*"):
				if not file_path.is_file():
					continue
				flattened = "__".join([session_dir.name] + list(file_path.relative_to(session_dir).parts))
				try:
					with open(file_path, "rb") as fh:
						self.ftp.storbinary(f"STOR {flattened}", fh)
					files_uploaded += 1
				except Exception as err:
					print(f"Failed to upload {file_path}: {err}")
		return files_uploaded

	def download_all_files(self, remote_root, local_root):
		if self.ftp is None:
			self.connect()

		remote_base = f"/home/File-EXTERNAL/B2J{remote_root}"
		try:
			self.ftp.cwd(remote_base)
		except Exception as e:
			raise Exception(f"Failed to access remote folder '{remote_root}': {e}")

		local_path = Path(local_root)
		local_path.mkdir(parents=True, exist_ok=True)

		files_downloaded = 0
		try:
			for filename in self.ftp.nlst():
				local_file = local_path / filename
				with open(local_file, "wb") as f:
					self.ftp.retrbinary(f"RETR {filename}", f.write)
				files_downloaded += 1
		except Exception as e:
			raise Exception(f"Failed to download files from '{remote_root}': {e}")

		return files_downloaded

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

def play_single_sound(filepath="beep_left.wav", block=False):
	"""
	Play a .wav file. By default this is asynchronous; pass block=True to wait until completion.
	"""
	if not os.path.exists(filepath):
		print(f"[Sound] File not found: {filepath}")
		return

	def _play_audio():
		sound = pygame.mixer.Sound(filepath)
		channel = sound.play()
		if channel is not None:
			while channel.get_busy():
				time.sleep(0.01)
		else:
			time.sleep(sound.get_length())

	try:
		if block:
			_play_audio()
		else:
			threading.Thread(target=_play_audio, daemon=True).start()
	except Exception as e:
		print(f"[Sound] Failed to play sound: {e}")

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

def createModelFolder(base_path="Model/"):
	base_dir = os.path.abspath(base_path)
	if not os.path.isdir(base_dir):
		os.makedirs(base_dir, exist_ok=True)
	return base_dir

def createTestingFolder(base_path="Testing/"):
	base_dir = os.path.abspath(base_path)
	if not os.path.isdir(base_dir):
		os.makedirs(base_dir, exist_ok=True)
	return base_dir

def deleteEmptyFolders(base_path="BMI Trainer Data/"):
	"""Remove subdirectories under base_path that contain no files."""
	base_dir = Path(base_path).expanduser().resolve()
	if not base_dir.is_dir():
		return

	for entry in base_dir.iterdir():
		if not entry.is_dir():
			continue
		try:
			contains_files = any(child.is_file() for child in entry.rglob('*'))
			if not contains_files:
				shutil.rmtree(entry)
		except Exception:
			pass

def startSingleTrainingSequence(board, user_id, timestamp, lcr_value, base_path):
	"""
	Start a single training sequence on a background thread.

	Returns a tuple of (csv_path, worker_thread, cancel_event).
	"""
	if board is None:
		raise ValueError('board is required')

	if not getattr(board, 'connected', False):
		raise RuntimeError('BCIBoard is not connected')

	if not getattr(board, 'streaming', False):
		raise RuntimeError('BCIBoard is not streaming')

	if not isinstance(user_id, str):
		user_id = str(user_id)
	if len(user_id) != 9 or not user_id.isdigit():
		raise ValueError('user_id must be a 9-digit string')

	if lcr_value not in (0, 1, 2, 3):
		raise ValueError('lcr_value must be 0(testing), 1 (left), 2 (center), or 3 (right)')

	direction_map = {0: "testing", 1: "left", 2: "center", 3: "right"}
	direction = direction_map[lcr_value]

	base_dir = Path(base_path).expanduser().resolve()
	base_dir.mkdir(parents=True, exist_ok=True)

	if hasattr(timestamp, 'strftime'):
		timestamp_str = timestamp.strftime('%Y-%m-%d-%H-%M-%S')
	else:
		timestamp_str = str(timestamp)

	filename = f"{user_id}-{timestamp_str}-{lcr_value}.csv"

	instruction_path = f"Sounds/instruction_{direction}.wav"
	beep_path = f"Sounds/beep_{direction}.wav"
	instruction_starting = "Sounds/instruction_starting.wav"
 
	stimulus_sound, sequence_id = generateSequence()
	cancel_event = threading.Event()

	def _sequence_worker():
		try:
			
			if cancel_event.is_set():
				return

			play_single_sound(instruction_path, block=True) #First Instruction
			time.sleep(ISI)

			if cancel_event.is_set():
				return

			if lcr_value == 0: #Testing Mode< one of each beep.
				play_single_sound("Sounds/beep_left.wav", block=True)
				time.sleep(.5)
				play_single_sound("Sounds/beep_center.wav", block=True)
				time.sleep(.5)
				play_single_sound("Sounds/beep_right.wav", block=True)
				time.sleep(.5)
				
			else:
				for _ in range(3): #3 Beeps
					play_single_sound(beep_path, block=True)
					time.sleep(ISI)

			if cancel_event.is_set():
				return
   
			play_single_sound(instruction_starting, block=True) #Say Starting

			if cancel_event.is_set():
				return
   
			#Start Recording
			board.stimulus_sound = 0
			board.sequence_id = 0
			board.start_recording(base_path, filename=filename)
			time.sleep(2)
   
			start_time = time.time() + 0.1  # 少し余裕を持って開始
			for stim_idx, (sound, id) in enumerate(zip(stimulus_sound, sequence_id)):
				
				#Wait until the scheduled time only to play sound and update
				scheduled_time = start_time + stim_idx * (ISI + SOUND_LENGTH)
				while time.time() < scheduled_time:
					time.sleep(0.0005)
			  
				if cancel_event.is_set():
					break
 
				board.stimulus_sound = sound
				board.sequence_id = id
	
				if sound == 1:
					play_single_sound("Sounds/beep_left.wav", block=True)
				elif sound == 2:
					play_single_sound("Sounds/beep_center.wav", block=True)
				elif sound == 3:
					play_single_sound("Sounds/beep_right.wav", block=True)
				elif sound == 4:
					play_single_sound("Sounds/beep_silent.wav", block=True)
  
			if cancel_event.is_set():
				board.stop_recording()
				return
	
			board.stimulus_sound = 0
			board.sequence_id = 0
			time.sleep(2)

			board.stop_recording()
			
		except Exception as exc:
			print(f"[BCIBoard] Training sequence error: {exc}")
			raise SingleTrainingSequenceError(str(exc)) from exc
		finally:
			board.stimulus_sound = 0
			board.sequence_id = 0

	sequence_thread = threading.Thread(target=_sequence_worker, daemon=True)
	sequence_thread.start()

	return sequence_thread, cancel_event

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

def generateSequence():
	"""
	Generates non-repeating order of sounds to play (Left,Center,Right,Silent), and corresponding sequence id
	"""
	
	stimulation_sequence = []
	sequence_ids = []
	prev_stim = None
	
	#Modifiable
	numSequences=10
	playableIDs = [1,2,3,4]
	
	for set_idx in range(numSequences):
		stim_order = random.sample(playableIDs, len(playableIDs))
		while prev_stim is not None and stim_order[0] == prev_stim:
			stim_order = random.sample(playableIDs, len(playableIDs))
		prev_stim = stim_order[-1]
		stimulation_sequence.extend(stim_order)
		sequence_ids.extend([set_idx + 1] * len(stim_order))
		
	return stimulation_sequence, sequence_ids

def countRecordings(user_id, base_folder="BMI Trainer Data/"):
	"""Count left/center/right recordings for a user across session folders."""
	if not isinstance(user_id, str):
		user_id = str(user_id)
	if len(user_id) != 9 or not user_id.isdigit():
		raise ValueError("user_id must be a 9-digit string")

	base_dir = Path(base_folder).expanduser().resolve()
	if not base_dir.exists():
		return 0, 0, 0

	left = center = right = 0

	for session_dir in base_dir.iterdir():
		if not session_dir.is_dir():
			continue
		for csv_path in session_dir.glob(f"{user_id}-*.csv"):
			name = csv_path.name.rstrip().lower()
			if name.endswith('1.csv'):
				left += 1
			elif name.endswith('2.csv'):
				center += 1
			elif name.endswith('3.csv'):
				right += 1

	return left, center, right

def chooseNewLCRValue(counts, acceptable_span=5, max_per_class=333):
	"""
	Choose the next L/C/R value (1,2,3) to keep counts balanced.

	counts must be an iterable of three non-negative integers representing (left, center, right).
	If the spread between the minimum and maximum counts exceeds acceptable_span, the lowest count is chosen.
	Otherwise a random choice is made among classes that are still below max_per_class.
	"""
	try:
		left, center, right = counts
	except Exception as exc:
		raise ValueError("counts must be an iterable with three entries (left, center, right)") from exc

	for value in (left, center, right):
		if not isinstance(value, int) or value < 0:
			raise ValueError("All count values must be non-negative integers")

	class_counts = [left, center, right]

	eligible_indices = [idx for idx, count in enumerate(class_counts) if count < max_per_class]
	if not eligible_indices:
		raise ValueError("All class counts have reached the maximum allowed recordings")

	min_count = min(class_counts[idx] for idx in eligible_indices)
	max_count = max(class_counts[idx] for idx in eligible_indices)

	if max_count - min_count > acceptable_span:
		target_indices = [idx for idx in eligible_indices if class_counts[idx] == min_count]
	else:
		target_indices = eligible_indices

	chosen_index = random.choice(target_indices)
	return chosen_index + 1  # map 0->1 (left), 1->2 (center), 2->3 (right)

def deleteMostRecent(base_path="BMI Trainer Data/"):
	"""Delete the most recent recording (by timestamp) across all session folders."""
	base_dir = Path(base_path).expanduser().resolve()
	if not base_dir.exists():
		print(f"[deleteMostRecent] Base path not found: {base_dir}")
		return False

	most_recent_path = None
	most_recent_time = None

	for session_dir in base_dir.iterdir():
		if not session_dir.is_dir():
			continue
		for csv_path in session_dir.glob('*.csv'):
			name = csv_path.name
			parts = name.split('-')
			if len(parts) < 8:
				continue
			try:
				timestamp_str = '-'.join(parts[1:7])
				tstamp = datetime.datetime.strptime(timestamp_str, '%Y-%m-%d-%H-%M-%S')
			except Exception:
				continue

			if most_recent_time is None or tstamp > most_recent_time:
				most_recent_time = tstamp
				most_recent_path = csv_path

	if most_recent_path is None:
		print('[deleteMostRecent] No recordings found.')
		return False

	try:
		most_recent_path.unlink()
		print(f"[deleteMostRecent] Deleted most recent recording: {most_recent_path}")
		return True
	except Exception as exc:
		print(f"[deleteMostRecent] Failed to delete {most_recent_path}: {exc}")
		return False

def deleteTestingFiles(base_path="Testing/"):
	"""Delete all files under the testing directory."""
	base_dir = Path(base_path).expanduser().resolve()
	if not base_dir.exists():
		print(f"[deleteTestingFiles] Testing path not found: {base_dir}")
		return False

	deleted = False
	for item in base_dir.glob("*"):
		try:
			if item.is_file():
				item.unlink()
				deleted = True
			elif item.is_dir():
				shutil.rmtree(item)
				deleted = True
		except Exception as exc:
			print(f"[deleteTestingFiles] Failed to delete {item}: {exc}")
	return deleted

def labelTestingFile(test_file, session_folder, lcr_value):
	"""
	Rename a testing file by replacing the trailing class label with the provided lcr_value
	and move it into the given session folder.
	"""
	if lcr_value not in (1, 2, 3):
		raise ValueError("lcr_value must be 1 (Left), 2 (Center), or 3 (Right)")

	test_path = Path(test_file).expanduser().resolve()
	if not test_path.exists() or not test_path.is_file():
		raise FileNotFoundError(f"Testing file not found: {test_path}")

	session_dir = Path(session_folder).expanduser().resolve()
	session_dir.mkdir(parents=True, exist_ok=True)

	name_parts = test_path.stem.split('-')
	if not name_parts:
		raise ValueError(f"Unexpected testing filename format: {test_path.name}")

	name_parts[-1] = str(lcr_value)
	new_name = '-'.join(name_parts) + test_path.suffix
	target_path = session_dir / new_name

	shutil.move(str(test_path), str(target_path))
	return target_path
