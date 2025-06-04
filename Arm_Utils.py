import time
import os
import csv
import threading
import logging
from dynamixel_sdk import *

class RoboticArm:
    # -----------------------------------------------------------------------
    # Dynamixel control constants
    # -----------------------------------------------------------------------
    TORQUE_ENABLE = 1
    TORQUE_DISABLE = 0
    PROTOCOL_VERSION = 2.0
    BAUDRATE = 115200
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
                    for dxl_id in self.dxl_ids:
                        dxl_comm_result, dxl_error = self.packetHandler.write1ByteTxRx(
                            self.portHandler, dxl_id, self.OP_MODE_ADDR,
                            self.EXTENDED_POSITION_CONTROL_MODE)
                        if dxl_comm_result != self.COMM_SUCCESS or dxl_error != 0:
                            logging.error(f"{self.device_name} ID {dxl_id}: "
                                          "Failed to set operating mode.")
                            continue
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
    
    #----Positions
    
    #----Torque Status Helpers
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
    
    #----Torque Functions        
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
    
    #----Recording Functions
    def start_record(self, frequency=30, filename='NewMovement.csv', duration=None):
        with self.lock:
            if not self.port_is_open:
                logging.warning(f"{self.device_name}: Port not open.")
                return
            interval = 1.0 / frequency
            directory = os.path.join("Recorded_movements", self.device_name)
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
            # Remove '.csv' for voice filename
            filename = filename[:-4]
            self.voice_thread = threading.Thread(
                target=self.get_recommend_action_voice,
                args=(filename, filename))
            self.voice_thread.start()
    
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
    
    #----Routines      
    def emergency_stop(self):
        self.set_is_stop(True)
        self.enable_torque(True)