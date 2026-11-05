"""
B2J User Simulation

Stand-in for B2J-User_2x.py that needs no BCI board. Tap/click (or use the keyboard)
to "think" Left / Center / Right and the app replays what B2J-User_2x.py would put on
the wire for that trial, over either the M5 serial port or UDP:

  1. LED all off        S,Ch1-0 ... S,Ch8-0
  2. Recording          E,<frame> streamed for the whole recording
                          - 2 s of baseline ("dead") frames, label 0
                          - then (NUM_SEQUENCES + 1) sets x 4 stimuli, same timing as
                            ABMI_Utils_2x.startSingleTrainingSequence
                          <frame> is str() of [timestamp, ch1..ch8, label, seq], the same
                          list B2J-User_2x.py sends from board._last_data_frame
  3. Predicting         ~2 s pause (the model "thinking")
  4. Prediction LEDs    S,ChN-3 for the chosen side, 1 s, then S,ChN-1
     + prediction sound
  5. Triggering         waits for the center button / E, then sends T,<1|2|3>
                        and LED all off, then returns to idle

Serial uses the same bytes as B2J-User_2x.py (115200 baud, UTF-8, newline terminated).
Like the real app, the latest frame is re-sent as fast as possible with no pacing; the
simulator keeps the port open so it is at least as fast as the real app (the serial
link is the only limit). The achieved E-message rate is printed after each recording.

UDP: the trigger is the BMI Trainer format, the bare ASCII text "BMI: 1" / "BMI: 2" /
"BMI: 3" (Left / Center / Right) sent when you press the trigger, which is what
ALS-User.py listens for (port 21623). During recording the E,<frame> lines are also
flooded over UDP, unpaced (no newline, one per datagram), to stress the receiver.
No S, or T, lines are sent over UDP.

Controls
  Mode screen : Left/Right + Enter, or tap an option
  UDP screen  : type IP / port, Tab or click to switch field, Enter or Start to begin
  Main screen : Left/Right/Down arrows (or 1/2/3, or tap) start a trial,
                E (or tap the center button) sends the trigger, Esc quits
"""

import os
import random
import socket
import sys
import threading
import time

import pygame
import serial
from serial.tools import list_ports

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NOTO_FONT = os.path.join(BASE_DIR, "Font", "NotoSansJP-Bold.otf")
SOUND_DIR = os.path.join(BASE_DIR, "Sounds")

# ---- Timing / protocol constants (mirrors ABMI_Utils / ABMI_Utils_2x / B2J-User_2x) ----
M5_BAUD = 115200
SAMPLE_RATE = 250            # Hz, BCI board sample rate
ISI = 0.35                   # Inter-stimulus interval (s)
SOUND_LENGTH = 0.15          # Stimulus length (s)
NUM_SEQUENCES = 5            # 2x model: 5 sets + 1 bonus set
DEAD_SECONDS = 2.0           # Baseline recorded before the first stimulus
START_OFFSET = 0.1           # Gap between baseline end and first stimulus
END_PAD = 0.05               # Tail after the last stimulus
THINK_SECONDS = 2.0          # Fake "model is predicting" pause
DEFAULT_UDP_PORT = 21623

# ---- Screen ----
RENDER_W, RENDER_H = 480, 320

white = (217, 217, 217)
grey = (90, 90, 90)
dark_grey = (35, 35, 35)
black = (0, 0, 0)
cool_blue = (74, 198, 255)
soft_red = (250, 61, 55)
mint_green = (54, 217, 62)
warning_orange = (255, 190, 120)

SOUND_MAP = {
	1: os.path.join(SOUND_DIR, "prediction_left.wav"),
	2: os.path.join(SOUND_DIR, "prediction_center.wav"),
	3: os.path.join(SOUND_DIR, "prediction_right.wav"),
}
CHOICE_NAMES = {1: "LEFT", 2: "CENTER", 3: "RIGHT"}
LED_CHANNELS = {1: [1, 4, 7], 2: [2, 5], 3: [3, 6, 8]}

mixer_ready = False


# =============================================================================
# Transports
# =============================================================================
def pick_m5_port():
	"""Same selection rule as B2J-User_2x.py / ALS-User.py."""
	for p in list_ports.comports():
		text = f"{p.description} {p.manufacturer} {p.product}".lower()
		if "ftdi" in text:
			continue
		return p.device
	return None


class Transport:
	label = ""
	min_interval = 0.0       # Minimum seconds between two E frames

	def send(self, message, quiet=False):
		raise NotImplementedError

	def close(self):
		pass


class SerialTransport(Transport):
	"""Same bytes as sendToM5() in B2J-User_2x.py (UTF-8 line + newline, 115200 baud).

	B2J-User_2x.py opens and closes the port for every message. Here the port is opened
	once and kept open (keep_open=True), so the send rate is limited only by the serial
	link, which makes the simulator at least as fast as the real app. Pass
	keep_open=False to open/close per message like the original."""

	def __init__(self, port, baud=M5_BAUD, keep_open=True):
		self.port = port
		self.baud = baud
		self.keep_open = keep_open
		self.label = f"SERIAL {port}"
		self._lock = threading.Lock()
		self._ser = None
		self._last_error_print = 0.0

	def _write(self, data):
		if not self.keep_open:
			with serial.Serial(self.port, self.baud, timeout=1) as ser:
				ser.write(data)
				ser.flush()
			return
		if self._ser is None or not self._ser.is_open:
			self._ser = serial.Serial(self.port, self.baud, timeout=1)
		self._ser.write(data)
		self._ser.flush()

	def close(self):
		with self._lock:
			if self._ser is not None:
				try:
					self._ser.close()
				except Exception:
					pass
				self._ser = None

	def send(self, message, quiet=False):
		if not self.port:
			print("[ERROR] No serial port selected")
			return
		if not message:
			return

		message = message.strip() + "\n"
		with self._lock:
			try:
				self._write(message.encode("utf-8"))
				if not quiet:
					print(f"[TX M5] {message.strip()}")
			except (serial.SerialException, OSError) as e:
				if self._ser is not None:
					try:
						self._ser.close()
					except Exception:
						pass
					self._ser = None   # reopen on the next message
				now = time.monotonic()
				if now - self._last_error_print > 1.0:
					self._last_error_print = now
					print(f"[ERROR] Serial error: {e}")


class UdpTransport(Transport):
	"""BMI Trainer's UDP protocol: bare 'BMI: <1|2|3>' datagrams (ASCII, no newline)."""

	def __init__(self, host, port):
		self.host = host
		self.port = port
		self.label = f"UDP {host}:{port}"
		self.min_interval = 0.0   # unpaced, like serial: flood E frames as fast as possible
		self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		self._last_error_print = 0.0

	def send(self, message, quiet=False):
		if not message:
			return

		message = message.strip()
		try:
			self._sock.sendto(message.encode("ascii"), (self.host, self.port))
			if not quiet:
				print(f"[TX UDP {self.host}:{self.port}] {message}")
		except OSError as e:
			now = time.monotonic()
			if now - self._last_error_print > 1.0:
				self._last_error_print = now
				print(f"[ERROR] UDP send failed: {e}")

	def close(self):
		self._sock.close()


# =============================================================================
# Simulation (protocol side - no pygame display needed)
# =============================================================================
def generate_sequence(num_sequences=NUM_SEQUENCES):
	"""Same logic as ABMI_Utils_2x.generateSequence (non-repeating L/C/R/Silent sets,
	plus one bonus set when num_sequences < 10)."""
	stimulation_sequence = []
	sequence_ids = []
	prev_stim = None
	playable_ids = [1, 2, 3, 4]

	for set_idx in range(num_sequences + 1):
		stim_order = random.sample(playable_ids, len(playable_ids))
		while prev_stim is not None and stim_order[0] == prev_stim:
			stim_order = random.sample(playable_ids, len(playable_ids))
		prev_stim = stim_order[-1]
		stimulation_sequence.extend(stim_order)
		sequence_ids.extend([set_idx + 1] * len(stim_order))

	return stimulation_sequence, sequence_ids


def play_sound(filepath):
	"""Non-blocking, like ABMI_Utils.play_single_sound."""
	if not mixer_ready:
		return
	if not os.path.exists(filepath):
		print(f"[Sound] File not found: {filepath}")
		return

	def _play():
		try:
			pygame.mixer.Sound(filepath).play()
		except Exception as e:
			print(f"[Sound] Failed to play sound: {e}")

	threading.Thread(target=_play, daemon=True).start()


class Simulator:
	def __init__(self, transport):
		self.transport = transport
		# UDP sends the E,<frame> data stream plus the BMI trigger message; the LED
		# lines (S,) and T, are serial-only.
		self.bmi_udp = isinstance(transport, UdpTransport)
		self.state = "idle"          # idle / recording / predicting / triggering / sending
		self.prediction = None
		self.progress = 0.0          # 0..1 through the recording
		self.cancel = threading.Event()

		self._frame_lock = threading.Lock()
		self._latest_frame = None    # plays the role of board._last_data_frame
		self._stream_stop = threading.Event()
		self._sent = 0

	# ---- LED commands (copied from B2J-User_2x.py) ----
	def _send_single_command(self, ch, val):
		self.transport.send(f"S,Ch{ch}-{val}")

	def send_led_command(self, ch, val):
		if self.bmi_udp:
			return
		if ch == 9:
			for i in range(1, 9):
				self._send_single_command(i, val)
				time.sleep(0.01)
		else:
			self._send_single_command(ch, val)

	def send_led_all_off(self):
		self.send_led_command(9, 0)

	def send_led_pattern(self, choice):
		if self.bmi_udp:
			return
		channels = LED_CHANNELS[choice]
		for ch in channels:
			self.send_led_command(ch, 3)
		time.sleep(1)
		for ch in channels:
			self.send_led_command(ch, 1)

	# ---- E,<frame> sender: repeatedly sends the most recent frame, like handleRecording() ----
	def _stream_loop(self):
		next_t = time.monotonic()
		while not self._stream_stop.is_set():
			with self._frame_lock:
				frame = self._latest_frame

			if frame is not None:
				self.transport.send(f"E,{frame}", quiet=True)
				self._sent += 1
				if self._sent % 250 == 1:
					print(f"[TX E #{self._sent}] E,{frame}")

			interval = self.transport.min_interval
			if interval:
				next_t += interval
				delay = next_t - time.monotonic()
				if delay > 0:
					time.sleep(delay)
				else:
					next_t = time.monotonic()
			else:
				time.sleep(0)

	def _make_frame(self, label, seq):
		eeg = [random.gauss(0.0, 10.0) for _ in range(8)]   # dummy EEG, ~10 uV noise
		return [time.time()] + eeg + [label, seq]

	def _record_dummy_data(self):
		stimuli, seq_ids = generate_sequence()
		stim_start = DEAD_SECONDS + START_OFFSET
		stim_period = ISI + SOUND_LENGTH
		last_idx = len(stimuli) - 1
		# Real sequence ends right after the last beep plays, plus a short tail
		duration = stim_start + last_idx * stim_period + SOUND_LENGTH + END_PAD

		self._sent = 0
		self._stream_stop.clear()
		streamer = threading.Thread(target=self._stream_loop, daemon=True)
		streamer.start()

		t0 = time.monotonic()
		i = 0
		try:
			while not self.cancel.is_set():
				elapsed = i / SAMPLE_RATE
				if elapsed >= duration:
					break

				if elapsed < stim_start:
					label, seq = 0, 0
				else:
					k = int((elapsed - stim_start) / stim_period)
					if k > last_idx or (k == last_idx and elapsed - stim_start - k * stim_period >= SOUND_LENGTH):
						label, seq = 0, 0
					else:
						label, seq = stimuli[k], seq_ids[k]

				frame = self._make_frame(label, seq)
				with self._frame_lock:
					self._latest_frame = frame

				self.progress = min(elapsed / duration, 1.0)
				i += 1

				delay = t0 + i / SAMPLE_RATE - time.monotonic()
				if delay > 0:
					time.sleep(delay)
		finally:
			self._stream_stop.set()
			streamer.join(timeout=3)
			with self._frame_lock:
				self._latest_frame = None

		took = time.monotonic() - t0
		print(f"[SIM] Recording done: {i} samples generated, {self._sent} E messages sent "
			  f"in {took:.1f}s ({self._sent / took:.0f}/s)")

	def run_trial(self, choice):
		"""Everything B2J-User_2x does between a start press and the 'triggering' prompt."""
		try:
			self.state = "recording"
			self.progress = 0.0
			self.send_led_all_off()
			self._record_dummy_data()
			if self.cancel.is_set():
				return

			self.state = "predicting"
			time.sleep(THINK_SECONDS)
			if self.cancel.is_set():
				return

			self.prediction = choice
			self.send_led_pattern(choice)
			play_sound(SOUND_MAP[choice])
			self.state = "triggering"
		except Exception as e:
			print(f"[ERROR] Simulation failed: {e}")
			self.state = "idle"

	def run_trigger(self):
		"""handleTriggering(): play the prediction sound, send T,<n>, LEDs off, back to idle."""
		try:
			play_sound(SOUND_MAP[self.prediction])
			if self.bmi_udp:
				self.transport.send(f"BMI: {self.prediction}")
			else:
				self.transport.send(f"T,{self.prediction}")
			self.send_led_all_off()
		finally:
			self.prediction = None
			self.state = "idle"

	def start_trial(self, choice):
		if self.state != "idle":
			return
		self.state = "recording"
		threading.Thread(target=self.run_trial, args=(choice,), daemon=True).start()

	def press_trigger(self):
		if self.state != "triggering":
			return
		self.state = "sending"
		threading.Thread(target=self.run_trigger, daemon=True).start()


# =============================================================================
# UI
# =============================================================================
def draw_text(surface, font, text, color, center=None, topleft=None):
	surf = font.render(text, True, color)
	rect = surf.get_rect()
	if center is not None:
		rect.center = center
	elif topleft is not None:
		rect.topleft = topleft
	surface.blit(surf, rect)
	return rect


class App:
	def __init__(self):
		os.environ.setdefault("SDL_VIDEO_WINDOW_POS", "0,0")
		pygame.init()
		global mixer_ready
		try:
			pygame.mixer.init()
			mixer_ready = True
		except pygame.error as e:
			print(f"[WARN] Audio unavailable: {e}")

		# Fullscreen at the display's native size (like ALS-User.py). The UI is drawn on a
		# 480x320 surface, then scaled up (keeping aspect ratio, centered) for display.
		info = pygame.display.Info()
		self.display = pygame.display.set_mode((info.current_w, info.current_h), pygame.FULLSCREEN)
		pygame.display.set_caption("B2J User Simulation")
		self.screen = pygame.Surface((RENDER_W, RENDER_H))
		self.scale = min(info.current_w / RENDER_W, info.current_h / RENDER_H)
		self.view_size = (int(RENDER_W * self.scale), int(RENDER_H * self.scale))
		self.view_offset = ((info.current_w - self.view_size[0]) // 2,
							(info.current_h - self.view_size[1]) // 2)
		pygame.key.set_repeat(400, 40)
		self.clock = pygame.time.Clock()

		self.font_big = pygame.font.Font(NOTO_FONT, 40)
		self.font_mid = pygame.font.Font(NOTO_FONT, 26)
		self.font_small = pygame.font.Font(NOTO_FONT, 18)
		self.font_tiny = pygame.font.Font(NOTO_FONT, 14)

		self.screen_name = "mode"      # mode / udp / main
		self.mode_index = 0            # 0 = serial, 1 = udp
		self.mode_message = ""
		self.m5_port = pick_m5_port()
		if self.m5_port is None:
			print("[ERROR] No M5 serial port found")
		else:
			print(f"[OK] M5 port found: {self.m5_port}")

		self.udp_fields = [os.environ.get("BMI_UDP_HOST", "127.0.0.1"),
						   os.environ.get("BMI_UDP_PORT", str(DEFAULT_UDP_PORT))]
		self.udp_active = 0
		self.udp_message = ""

		self.sim = None
		self.running = True

		# Layout
		self.mode_rects = [pygame.Rect(40, 110, 180, 110), pygame.Rect(260, 110, 180, 110)]
		self.udp_rects = [pygame.Rect(150, 80, 300, 44), pygame.Rect(150, 140, 300, 44)]
		self.udp_start_rect = pygame.Rect(170, 230, 140, 50)
		bw, bh, gap = 140, 70, 10
		x0 = (RENDER_W - (3 * bw + 2 * gap)) // 2
		self.button_rects = [pygame.Rect(x0 + i * (bw + gap), 215, bw, bh) for i in range(3)]

	# ---- mode screen ----
	def choose_mode(self, index):
		self.mode_index = index
		if index == 0:
			self.m5_port = pick_m5_port()
			if self.m5_port is None:
				self.mode_message = "No M5 serial port found"
				print("[ERROR] No M5 serial port found")
				return
			self.mode_message = ""
			self.start_sim(SerialTransport(self.m5_port))
		else:
			self.mode_message = ""
			self.udp_message = ""
			self.screen_name = "udp"

	def handle_mode_event(self, event):
		if event.type == pygame.KEYDOWN:
			if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
				self.mode_index = 1 - self.mode_index
			elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
				self.choose_mode(self.mode_index)
			elif event.key == pygame.K_ESCAPE:
				self.running = False
		elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
			for i, rect in enumerate(self.mode_rects):
				if rect.collidepoint(event.pos):
					self.choose_mode(i)

	def draw_mode(self):
		s = self.screen
		s.fill(black)
		draw_text(s, self.font_mid, "B2J User Simulation", white, center=(RENDER_W // 2, 40))
		draw_text(s, self.font_small, "Select connection", grey, center=(RENDER_W // 2, 80))

		for i, (rect, name) in enumerate(zip(self.mode_rects, ("SERIAL", "UDP"))):
			selected = (i == self.mode_index)
			pygame.draw.rect(s, dark_grey, rect, border_radius=14)
			pygame.draw.rect(s, cool_blue if selected else grey, rect, width=4 if selected else 2, border_radius=14)
			draw_text(s, self.font_big, name, cool_blue if selected else white, center=(rect.centerx, rect.centery - 8))
			if i == 0:
				sub = self.m5_port if self.m5_port else "no M5 found"
				draw_text(s, self.font_tiny, sub, grey if self.m5_port else soft_red,
						  center=(rect.centerx, rect.bottom - 18))
			else:
				draw_text(s, self.font_tiny, "ip + port", grey, center=(rect.centerx, rect.bottom - 18))

		if self.mode_message:
			draw_text(s, self.font_small, self.mode_message, soft_red, center=(RENDER_W // 2, 250))
		draw_text(s, self.font_tiny, "Left / Right + Enter, or tap     Esc: quit", grey,
				  center=(RENDER_W // 2, RENDER_H - 20))

	# ---- udp screen ----
	def confirm_udp(self):
		host = self.udp_fields[0].strip()
		port_text = self.udp_fields[1].strip()
		if not host:
			self.udp_message = "Enter an IP / host"
			self.udp_active = 0
			return
		if not port_text.isdigit() or not (1 <= int(port_text) <= 65535):
			self.udp_message = "Port must be 1-65535"
			self.udp_active = 1
			return
		try:
			socket.gethostbyname(host)
		except OSError:
			self.udp_message = "Cannot resolve host"
			self.udp_active = 0
			return
		self.udp_message = ""
		self.start_sim(UdpTransport(host, int(port_text)))

	def handle_udp_event(self, event):
		if event.type == pygame.KEYDOWN:
			if event.key == pygame.K_ESCAPE:
				self.screen_name = "mode"
			elif event.key in (pygame.K_TAB, pygame.K_UP, pygame.K_DOWN):
				self.udp_active = 1 - self.udp_active
			elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
				if self.udp_active == 0:
					self.udp_active = 1
				else:
					self.confirm_udp()
			elif event.key == pygame.K_BACKSPACE:
				self.udp_fields[self.udp_active] = self.udp_fields[self.udp_active][:-1]
			elif event.unicode and event.unicode.isprintable():
				ch = event.unicode
				if self.udp_active == 1 and not ch.isdigit():
					return
				if len(self.udp_fields[self.udp_active]) < 40:
					self.udp_fields[self.udp_active] += ch
		elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
			for i, rect in enumerate(self.udp_rects):
				if rect.collidepoint(event.pos):
					self.udp_active = i
			if self.udp_start_rect.collidepoint(event.pos):
				self.confirm_udp()

	def draw_udp(self):
		s = self.screen
		s.fill(black)
		draw_text(s, self.font_mid, "UDP destination", white, center=(RENDER_W // 2, 36))

		for i, (rect, name) in enumerate(zip(self.udp_rects, ("IP / Host", "Port"))):
			active = (i == self.udp_active)
			draw_text(s, self.font_small, name, white, topleft=(20, rect.y + 8))
			pygame.draw.rect(s, dark_grey, rect, border_radius=8)
			pygame.draw.rect(s, cool_blue if active else grey, rect, width=3 if active else 2, border_radius=8)
			text = self.udp_fields[i]
			if active and (pygame.time.get_ticks() // 500) % 2 == 0:
				text += "|"
			draw_text(s, self.font_small, text, white, topleft=(rect.x + 10, rect.y + 8))

		pygame.draw.rect(s, dark_grey, self.udp_start_rect, border_radius=12)
		pygame.draw.rect(s, mint_green, self.udp_start_rect, width=3, border_radius=12)
		draw_text(s, self.font_mid, "Start", mint_green, center=self.udp_start_rect.center)

		if self.udp_message:
			draw_text(s, self.font_small, self.udp_message, soft_red, center=(RENDER_W // 2, 205))
		draw_text(s, self.font_tiny, "Tab: switch field   Enter: next / start   Esc: back", grey,
				  center=(RENDER_W // 2, RENDER_H - 20))

	# ---- main screen ----
	def start_sim(self, transport):
		self.sim = Simulator(transport)
		self.screen_name = "main"
		print(f"[SIM] Using {transport.label}")

	def handle_main_event(self, event):
		sim = self.sim
		if event.type == pygame.KEYDOWN:
			if event.key == pygame.K_ESCAPE:
				self.running = False
			elif event.key in (pygame.K_LEFT, pygame.K_1, pygame.K_KP1):
				sim.start_trial(1)
			elif event.key in (pygame.K_DOWN, pygame.K_UP, pygame.K_2, pygame.K_KP2):
				sim.start_trial(2)
			elif event.key in (pygame.K_RIGHT, pygame.K_3, pygame.K_KP3):
				sim.start_trial(3)
			elif event.key == pygame.K_e:
				sim.press_trigger()
		elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
			for i, rect in enumerate(self.button_rects):
				if rect.collidepoint(event.pos):
					if sim.state == "triggering" and i == 1:
						sim.press_trigger()
					else:
						sim.start_trial(i + 1)

	def draw_main(self):
		s = self.screen
		sim = self.sim
		s.fill(black)

		draw_text(s, self.font_small, "B2J User 2x  (SIM)", white, center=(RENDER_W // 2, 22))
		draw_text(s, self.font_tiny, sim.transport.label, grey, center=(RENDER_W // 2, 46))

		state = sim.state
		if state == "triggering":
			choice = CHOICE_NAMES.get(sim.prediction, "?")
			draw_text(s, self.font_big, choice, mint_green, center=(RENDER_W // 2, 105))
			draw_text(s, self.font_small, "Press E to send trigger", white, center=(RENDER_W // 2, 160))
			draw_text(s, self.font_tiny, "(or tap the center button)", grey, center=(RENDER_W // 2, 186))
		else:
			draw_text(s, self.font_big, state.upper(), white, center=(RENDER_W // 2, 105))
			if state == "recording":
				bar = pygame.Rect(90, 150, 300, 12)
				pygame.draw.rect(s, dark_grey, bar, border_radius=6)
				fill = bar.copy()
				fill.width = int(bar.width * sim.progress)
				pygame.draw.rect(s, cool_blue, fill, border_radius=6)
			elif state == "idle":
				draw_text(s, self.font_tiny, "Choose Left / Center / Right", grey, center=(RENDER_W // 2, 160))

		for i, (rect, name) in enumerate(zip(self.button_rects, ("LEFT", "CENTER", "RIGHT"))):
			is_trigger = (state == "triggering" and i == 1)
			enabled = (state == "idle") or is_trigger
			color = mint_green if is_trigger else (cool_blue if enabled else grey)
			pygame.draw.rect(s, dark_grey, rect, border_radius=14)
			pygame.draw.rect(s, color, rect, width=3, border_radius=14)
			draw_text(s, self.font_small, "TRIGGER" if is_trigger else name, color, center=rect.center)

		draw_text(s, self.font_tiny, "Arrows / 1 2 3: choose    E: trigger    Esc: quit", grey,
				  center=(RENDER_W // 2, RENDER_H - 12))

	# ---- display ----
	def present(self):
		self.display.fill(black)
		if self.view_size == (RENDER_W, RENDER_H):
			self.display.blit(self.screen, self.view_offset)
		else:
			self.display.blit(pygame.transform.smoothscale(self.screen, self.view_size), self.view_offset)
		pygame.display.flip()

	def to_logical(self, event):
		"""Map a mouse event from display coordinates to the 480x320 UI surface."""
		if event.type == pygame.MOUSEBUTTONDOWN:
			x = int((event.pos[0] - self.view_offset[0]) / self.scale)
			y = int((event.pos[1] - self.view_offset[1]) / self.scale)
			return pygame.event.Event(event.type, pos=(x, y), button=event.button)
		return event

	# ---- loop ----
	def run(self):
		handlers = {"mode": self.handle_mode_event, "udp": self.handle_udp_event, "main": self.handle_main_event}
		drawers = {"mode": self.draw_mode, "udp": self.draw_udp, "main": self.draw_main}

		while self.running:
			for event in pygame.event.get():
				if event.type == pygame.QUIT:
					self.running = False
				else:
					handlers[self.screen_name](self.to_logical(event))

			drawers[self.screen_name]()
			self.present()
			self.clock.tick(30)

		if self.sim is not None:
			self.sim.cancel.set()
			self.sim.transport.close()
		pygame.quit()


if __name__ == "__main__":
	App().run()
	sys.exit(0)
