import time
import os
import csv
import threading
import logging
from dynamixel_sdk import *

class RoboticArm:
	#-----------------------------------------------------------------------
	#----Dynamixel control constants
	#-----------------------------------------------------------------------
	TORQUE_ENABLE = 1
	TORQUE_DISABLE = 0
	PROTOCOL_VERSION = 2.0
	BAUDRATE = 1000000
	ADDR_PRO_TORQUE_ENABLE = 64
	ADDR_PRO_PRESENT_POSITION = 132
	ADDR_PRO_PRESENT_POSITION_LEN = 4
	ADDR_PRO_GOAL_POSITION = 116
	ADDR_PRO_GOAL_POSITION_LEN = 4
	ADDR_PRO_PROFILE_ACCELERATION = 108
	ADDR_PRO_PROFILE_ACCELERATION_LEN = 4
	ADDR_PRO_PROFILE_VELOCITY = 112
	ADDR_PRO_PROFILE_VELOCITY_LEN = 4
	OP_MODE_ADDR = 11
	EXTENDED_POSITION_CONTROL_MODE = 4
	ADDR_PRO_HARDWARE_ERROR_STATUS = 70  # Hardware-error status address
	# MAX_POSITION = 50000
	# MIN_POSITION = 0

	# Communication-result constants
	COMM_SUCCESS = 0
	COMM_TX_FAIL = -1001
	COMM_RX_TIMEOUT = -1000

	#SPLINE ARMS
	LIGHT_FINGER_DXL_ID = 10
	ADDR_INDIRECT_DATA1 = 224

	def __init__(self, device_name, dxl_ids, is_admin=False):
		self.device_name = device_name
		self.dxl_ids = dxl_ids
		self.portHandler = PortHandler(self.device_name)
		self.packetHandler = PacketHandler(self.PROTOCOL_VERSION)
		self.file = None
		self.recording = False
		self.is_stop = False
		self.condition = threading.Condition()
		self.is_admin = is_admin
		self.task_running = False
		self.ping_thread_running = False
		self.current_positions = {}
		self.lock = threading.RLock()
		self.task_done_event = threading.Event()
		self.task_done_event.set()
		self.port_is_open = False
		self.overload_timers = {dxl_id: 0 for dxl_id in self.dxl_ids}
		self.torque_enabled = {}     # Cache of motor-torque states
		self.faulty_motors = []      # Motors with hardware errors
		self.stop_event = threading.Event()  # Control flag for threads
		self.default_speed = 300     # Default Profile Velocity / Acceleration
		self.realtime_increments = {}  # motor_id -> increment
		self.realtime_positions  = {}  # motor_id -> cumulative goal
		self.last_positions = {}       # motor_id -> last goal sent
		self.realtime_thread = None
		self.realtime_thread_stop_event = threading.Event()
		self.updated_motor_ids = []
	
	def open_port(self):
		with self.lock:
			if self.portHandler.openPort():
				logging.info(f"{self.device_name}: Port opened successfully.")
				if self.portHandler.setBaudRate(self.BAUDRATE):
					logging.info(f"{self.device_name}: Baud rate set.")

					successful_motors = 0  # Track how many motors responded

					for dxl_id in self.dxl_ids:
						dxl_comm_result, dxl_error = self.packetHandler.write1ByteTxRx(
							self.portHandler, dxl_id, self.OP_MODE_ADDR,
							self.EXTENDED_POSITION_CONTROL_MODE)

						if dxl_comm_result == self.COMM_SUCCESS and dxl_error == 0:
							successful_motors += 1

						if dxl_comm_result != self.COMM_SUCCESS or dxl_error != 0:
							logging.error(f"{self.device_name} ID {dxl_id}: "
										  "Failed to set operating mode.")
							continue

					# Driver connected, but no motors
					if successful_motors == 0:
						logging.error(f"{self.device_name}: No motors responded. Closing port.")
						self.portHandler.closePort()
						return False

					self.port_is_open = True
					# Initialize torque-status cache
					self.update_torque_status()
					return True
				else:
					logging.error(f"{self.device_name}: Failed to set baud rate.")
					self.portHandler.closePort()
					return False
			else:
				logging.error(f"{self.device_name}: Failed to open port.")
				return False

	def close_port(self):
		with self.lock:
			if self.port_is_open:
				self.enable_torque(False)
				self.portHandler.closePort()
				self.port_is_open = False
				logging.info(f"{self.device_name}: Port closed.")

	def ping_motors(self):
		with self.lock:
			if not self.port_is_open:
				logging.warning(f"{self.device_name}: Port not open.")
				return []
			successful_ids = []
			for dxl_id in self.dxl_ids:
				try:
					dxl_model_number, dxl_comm_result, dxl_error = self.packetHandler.ping(self.portHandler, dxl_id)
					if dxl_comm_result == self.COMM_SUCCESS:
						logging.info(f"{self.device_name} ID {dxl_id}: Ping successful.")
						successful_ids.append(dxl_id)
					else:
						logging.warning(f"{self.device_name} ID {dxl_id}: Ping failed: "
										f"{self.packetHandler.getTxRxResult(dxl_comm_result)}")
				except Exception as e:
					logging.error(f"{self.device_name} ID {dxl_id}: Exception during ping: {e}")
			return successful_ids
	
	#-----------------------------------------------------------------------
	#----Positions Functions
	#-----------------------------------------------------------------------
	def hold_current_position(self):
		"""Freeze the arm at its current pose."""
		self.task_running = False
		self.task_done_event.set()
		self.stop_event.set()
		present_positions = self.get_current_positions()
		groupSyncWrite = GroupSyncWrite(
			self.portHandler, self.packetHandler,
			self.ADDR_PRO_GOAL_POSITION,
			self.ADDR_PRO_GOAL_POSITION_LEN)

		with self.lock:
			for dxl_id in self.dxl_ids:
				position_value = present_positions.get(dxl_id, None)
				if position_value is None:
					logging.error(f"{self.device_name} ID {dxl_id}: Could not get position.")
					continue
				param_goal_position = [
					DXL_LOBYTE(DXL_LOWORD(position_value)),
					DXL_HIBYTE(DXL_LOWORD(position_value)),
					DXL_LOBYTE(DXL_HIWORD(position_value)),
					DXL_HIBYTE(DXL_HIWORD(position_value))
				]
				groupSyncWrite.addParam(dxl_id, param_goal_position)
			print("Holding current position")
			dxl_comm_result = groupSyncWrite.txPacket()
			if dxl_comm_result != self.COMM_SUCCESS:
				logging.error(f"{self.device_name}: Failed to hold pose: "
							  f"{self.packetHandler.getTxRxResult(dxl_comm_result)}")
			else:
				logging.info(f"{self.device_name}: Pose locked.")

	def get_current_positions(self):
		if not self.port_is_open:
			logging.warning(f"{self.device_name}: Port not open.")
			return self.current_positions
		try:
			with self.lock:
				groupSyncRead = GroupSyncRead(
					self.portHandler, self.packetHandler,
					self.ADDR_PRO_PRESENT_POSITION,
					self.ADDR_PRO_PRESENT_POSITION_LEN)
				for dxl_id in self.dxl_ids:
					groupSyncRead.addParam(dxl_id)
				dxl_comm_result = groupSyncRead.txRxPacket()
				if dxl_comm_result != self.COMM_SUCCESS:
					logging.error(f"{self.device_name}: Failed to read positions: "
								  f"{self.packetHandler.getTxRxResult(dxl_comm_result)}")
					return self.current_positions
				for dxl_id in self.dxl_ids:
					if not groupSyncRead.isAvailable(
							dxl_id,
							self.ADDR_PRO_PRESENT_POSITION,
							self.ADDR_PRO_PRESENT_POSITION_LEN):
						logging.error(f"{self.device_name} ID {dxl_id}: Data not available.")
						continue
					position = groupSyncRead.getData(
						dxl_id, self.ADDR_PRO_PRESENT_POSITION,
						self.ADDR_PRO_PRESENT_POSITION_LEN)
					if position is not None:
						self.current_positions[dxl_id] = position
					else:
						logging.error(f"{self.device_name} ID {dxl_id}: Failed to get data.")
				groupSyncRead.clearParam()
		except Exception as e:
			logging.exception(f"{self.device_name}: Exception in get_current_positions: {e}")
		return self.current_positions

	#-----------------------------------------------------------------------
	#----Torque Status Helpers
	#-----------------------------------------------------------------------
	def update_torque_status(self):
		"""Refresh torque-enabled cache for all motors."""
		for dxl_id in self.dxl_ids:
			torque_enabled, dxl_comm_result, dxl_error = \
				self.packetHandler.read1ByteTxRx(
					self.portHandler, dxl_id,
					self.ADDR_PRO_TORQUE_ENABLE)
			if dxl_comm_result == self.COMM_SUCCESS and dxl_error == 0:
				self.torque_enabled[dxl_id] = \
					(torque_enabled == self.TORQUE_ENABLE)
			else:
				self.torque_enabled[dxl_id] = None
	
	def set_is_stop(self, is_stop):
		with self.condition:
			self.is_stop = is_stop
			self.condition.notify_all()

	#-----------------------------------------------------------------------	
	#----Torque Functions
	#-----------------------------------------------------------------------
	def enable_all_motor_torque(self, enable):
		with self.lock:
			if not self.port_is_open:
				logging.warning(f"{self.device_name}: Port not open.")
				return
			for dxl_id in self.dxl_ids:
				self.enable_single_motor_torque(dxl_id, enable)
	
	def enable_single_motor_torque(self, dxl_id, enable):
		with self.lock:
			if self.torque_enabled.get(dxl_id) == enable:
				return  # No state change
			torque_status = self.TORQUE_ENABLE if enable else self.TORQUE_DISABLE
			dxl_comm_result, dxl_error = self.packetHandler.write1ByteTxRx(
				self.portHandler, dxl_id,
				self.ADDR_PRO_TORQUE_ENABLE, torque_status)
			if dxl_comm_result != self.COMM_SUCCESS:
				logging.error(f"{self.device_name} ID {dxl_id}: "
							  f"Torque change failed: "
							  f"{self.packetHandler.getTxRxResult(dxl_comm_result)}")
			elif dxl_error != 0:
				logging.error(f"{self.device_name} ID {dxl_id}: "
							  f"Torque change error: "
							  f"{self.packetHandler.getRxPacketError(dxl_error)}")
			else:
				self.torque_enabled[dxl_id] = enable
				status = "enabled" if enable else "disabled"
				logging.info(f"{self.device_name} ID {dxl_id}: Torque {status}.")
	
	#-----------------------------------------------------------------------
	#----Direct motor control helpers
	#-----------------------------------------------------------------------
	def set_motor_position(self, motor_id, speed, position):
		"""Set Profile Velocity and Goal Position for a single motor."""
		with self.lock:
			if not self.port_is_open:
				logging.warning(f"{self.device_name}: Port not open.")
				return
			if motor_id not in self.dxl_ids:
				logging.warning(f"{self.device_name}: Motor ID {motor_id} not found.")
				return
			self.enable_motor_torque(motor_id, True)

			# Profile Acceleration & Velocity
			self.packetHandler.write4ByteTxRx(
				self.portHandler, motor_id,
				self.ADDR_PRO_PROFILE_ACCELERATION, speed)
			self.packetHandler.write4ByteTxRx(
				self.portHandler, motor_id,
				self.ADDR_PRO_PROFILE_VELOCITY, speed)

			# Goal Position
			position_value = int(position)
			self.packetHandler.write4ByteTxRx(
				self.portHandler, motor_id,
				self.ADDR_PRO_GOAL_POSITION, position_value)

	def is_motor_at_position(self, motor_id, target_position, threshold=100):
		"""Return True if motor is within threshold of target."""
		current_position = self.get_current_positions().get(motor_id, None)
		if current_position is None:
			logging.warning(f"{self.device_name} ID {motor_id}: Cannot read position.")
			return False
		position_diff = abs(current_position - target_position)
		logging.info(f"{self.device_name} ID {motor_id}: "
					 f"Current {current_position}, Target {target_position}, Δ {position_diff}")
		return position_diff <= threshold

	def is_action_completed(self):
		return not self.task_running

	#-----------------------------------------------------------------------
	#----Recording Functions
	#-----------------------------------------------------------------------
	def start_record(self, frequency=30, filename='NewMovement.csv', duration=None):
		with self.lock:
			if not self.port_is_open:
				logging.warning(f"{self.device_name}: Port not open.")
				return
			interval = 1.0 / frequency
			directory = os.path.join(os.getcwd(), "Recorded_movements")

			# Save to ./Recorded_movements/
			if not os.path.exists(directory):
				os.makedirs(directory)
				logging.debug(f"{self.device_name}: Created directory {directory}.")

			filepath = os.path.join(directory, filename)
			try:
				self.file = open(filepath, mode='w', newline='')
				self.writer = csv.writer(self.file)
				logging.info(f"{self.device_name}: Recording started.")
			except PermissionError as e:
				logging.error(f"{self.device_name}: Cannot open file: {e}")
				return

			self.recording = True
			self.stop_event.clear()
			self.interval = interval
			self.duration = duration
			self.record_thread = threading.Thread(target=self.update_positions_during_recording)
			self.record_thread.start()
	
	def update_positions_during_recording(self):
		start_time = time.time()
		cached_positions = []
		try:
			while not self.stop_event.is_set():
				current_time = time.time()
				next_time = current_time + self.interval
				if self.duration is not None and (current_time - start_time) >= self.duration:
					break
				positions = self.get_current_positions()
				if positions:
					cached_positions.append(
						[positions.get(dxl_id, 0) for dxl_id in self.dxl_ids])
				else:
					logging.warning(f"{self.device_name}: No positions read, skipping.")
				sleep_time = next_time - time.time()
				if sleep_time > 0:
					self.stop_event.wait(timeout=sleep_time)
		except Exception as e:
			logging.exception(f"{self.device_name}: Exception in update_positions: {e}")
		finally:
			# Flush cached data to CSV
			if cached_positions:
				try:
					if self.file is None:
						directory = os.path.join("Recorded_movements", self.device_name)
						if not os.path.exists(directory):
							os.makedirs(directory)
						filepath = os.path.join(directory, 'NewMovement.csv')
						self.file = open(filepath, mode='w', newline='')
						self.writer = csv.writer(self.file)
					self.writer.writerows(cached_positions)
					logging.info(f"{self.device_name}: Cached data written.")
				except Exception as e:
					logging.error(f"{self.device_name}: Error writing cached data: {e}")
				finally:
					if self.file:
						self.file.close()
						self.file = None
						logging.info(f"{self.device_name}: Recording finished.")
	
	def end_record(self):
		self.recording = False
		self.stop_event.set()
		logging.info(f"{self.device_name}: Recording stopped.")
	
	#-----------------------------------------------------------------------
	#----Playback Functions
	#-----------------------------------------------------------------------
	def play_positions(self, csv_filename, frequency=30):

		with self.lock:
			if not self.port_is_open:
				logging.warning(f"{self.device_name}: Port not open.")
				return
			if self.task_running:
				logging.warning(f"{self.device_name}: Task already running.")
				return
			self.task_running = True
			self.task_done_event.clear()

			#If right arm, turn light on
			if (self.device_name == '/dev/ttyUSB1'):
				self.right_arm_light(state=True)

			self.playback_thread = threading.Thread(
				target=self.play_positions_worker_thread,
				args=(csv_filename, frequency))
			self.playback_thread.start()

	def play_positions_worker_thread(self, csv_filename, frequency):
		try:
			csv_filepath = os.path.join(os.path.join(os.getcwd(), "Recorded_movements", csv_filename))
			print("Playing: " + csv_filename)
			if not os.path.exists(csv_filepath):
				logging.error(f"{self.device_name}: File not found.")
				return

			# Enable Movement
			self.set_is_stop(False)
			self.enable_all_motor_torque(True)

			# Reset overload timers
			self.overload_timers = {dxl_id: 0 for dxl_id in self.dxl_ids}

			groupSyncWrite = GroupSyncWrite(
				self.portHandler, self.packetHandler,
				self.ADDR_PRO_GOAL_POSITION,
				self.ADDR_PRO_GOAL_POSITION_LEN)
			with open(csv_filepath, mode='r') as file:
				reader = list(csv.reader(file))
				desired_interval = 1.0 / frequency
				start_time = time.time()
				frame_count = 0
				total_frames = len(reader)
				while frame_count < total_frames:
					with self.condition:
						if self.is_stop:
							logging.info(f"{self.device_name}: Movement stopped.")
							break

					target_time = start_time + frame_count * desired_interval
					current_time = time.time()
					sleep_time = target_time - current_time
					if sleep_time > 0:
						time.sleep(sleep_time)
					else:
						logging.warning(f"{self.device_name}: Frame {frame_count} is late.")
					row = reader[frame_count]
					frame_count += 1

					with self.lock:
						groupSyncWrite.clearParam()
						for i, position in enumerate(row):
							dxl_id = self.dxl_ids[i]
							if dxl_id in self.faulty_motors:
								continue
							position_value = int(position)
							param_goal_position = [
								DXL_LOBYTE(DXL_LOWORD(position_value)),
								DXL_HIBYTE(DXL_LOWORD(position_value)),
								DXL_LOBYTE(DXL_HIWORD(position_value)),
								DXL_HIBYTE(DXL_HIWORD(position_value))]
							groupSyncWrite.addParam(dxl_id, param_goal_position)
							self.current_positions[dxl_id] = position_value
						dxl_comm_result = groupSyncWrite.txPacket()
						if dxl_comm_result != self.COMM_SUCCESS:
							logging.error(f"{self.device_name}: Failed to send positions: "
										  f"{self.packetHandler.getTxRxResult(dxl_comm_result)}")
				logging.info(f"{self.device_name}: Playback completed.")
		except Exception as e:
			logging.exception(f"{self.device_name}: Exception in play_positions_thread: {e}")
		finally:
				
			#If right arm, turn light off
			if (self.device_name == '/dev/ttyUSB1'):
				self.right_arm_light(state=False)

			self.task_running = False
			self.task_done_event.set()

	def right_arm_light(self, state: bool):
		
		# Write 0xFF (255) to Indirect Data 1
		value = 0x00
		if state==True:
			value = 0xFF

		dxl_comm_result, dxl_error = self.packetHandler.write1ByteTxRx(
			self.portHandler, self.LIGHT_FINGER_DXL_ID, self.ADDR_INDIRECT_DATA1, value
		)

		if dxl_error != 0:
			print(self.packetHandler.getRxPacketError(dxl_error))
		
	#-----------------------------------------------------------------------
	#----File utilities
	#-----------------------------------------------------------------------
	def delete_recorded_file(self, filename):
		file_path = os.path.join("Recorded_movements", self.device_name, filename + ".csv")
		if os.path.exists(file_path):
			os.remove(file_path)
			logging.info(f"{self.device_name}: Deleted {file_path}.")
		else:
			logging.warning(f"{self.device_name}: {file_path} does not exist.")

	def rename_recorded_file(self, old_filename, new_filename):
		old_file_path = os.path.join("Recorded_movements", self.device_name, old_filename + ".csv")
		new_file_path = os.path.join("Recorded_movements", self.device_name, new_filename + ".csv")
		if os.path.exists(old_file_path):
			os.rename(old_file_path, new_file_path)
			logging.info(f"{self.device_name}: Renamed file to {new_file_path}.")
		else:
			logging.warning(f"{self.device_name}: {old_file_path} does not exist.")
  
	#-----------------------------------------------------------------------
	#----One-shot realtime command (XYZ list -> motors 1..n)
	#-----------------------------------------------------------------------
	def play_realtime(self, motor_positions):
		groupSyncWrite = GroupSyncWrite(
			self.portHandler, self.packetHandler,
			self.ADDR_PRO_GOAL_POSITION,
			self.ADDR_PRO_GOAL_POSITION_LEN)
		groupSyncWrite.clearParam()
		for i, position in enumerate(motor_positions):
			position_value = int(position)
			param_goal_position = [
				DXL_LOBYTE(DXL_LOWORD(position_value)),
				DXL_HIBYTE(DXL_LOWORD(position_value)),
				DXL_LOBYTE(DXL_HIWORD(position_value)),
				DXL_HIBYTE(DXL_HIWORD(position_value))]
			groupSyncWrite.addParam(self.dxl_ids[i], param_goal_position)
		groupSyncWrite.txPacket()

	#-----------------------------------------------------------------------
	#----Routines   
	#-----------------------------------------------------------------------   
	def emergency_stop(self): 
		self.set_is_stop(True)
		self.enable_all_motor_torque(True)
		
	def release_arm(self):
		self.set_is_stop(True)
		self.enable_all_motor_torque(False)
