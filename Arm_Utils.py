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
