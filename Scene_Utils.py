import os
import pygame
import sys
import socket
import time
import math
import threading
import numpy as np
import datetime

#Audio BMI Code by MIKITO OGINO
import ABMI_Utils

# Font Path
notoFont = "/home/b2j/Desktop/AugmentedArms/Font/NotoSansJP-Bold.otf"

# Colors
white = (217,217,217)
blue = (23,100,255)
dark_blue = (21,19,186)
cool_blue = (74,198,255)
light_blue = (54,106,217)
warning_orange = (214,162,17)
soft_red = (250,61,55)
light_red = (255,143,133)
red = (200,0,0)
black = (0,0,0)
light_green = (82,255,128)
light_yellow = (220,200,80)
green = (0,200,0)
soft_green = (152,250,132)
mint_green = (54,217,62)
dark_green = (2,140,0)
dark_yellow = (201,185,0)

def draw_text_wrapped(surface, text, font, color, x, y, max_width, line_spacing=5, lang="en"):
	lines = []
	for paragraph in text.split("\n"):
		if lang == "jp":
			words = list(paragraph)  # treat each character as a word
		else:
			words = paragraph.split(" ")
		current_line = ""
		for word in words:
			test_line = current_line + word if lang == "jp" else current_line + (" " if current_line else "") + word
			if font.size(test_line)[0] <= max_width:
				current_line = test_line
			else:
				lines.append(current_line)
				current_line = word
		if current_line:
			lines.append(current_line)

	# Render all lines
	y_offset = y
	for line in lines:
		line_surface = font.render(line, True, color)
		line_rect = line_surface.get_rect(topleft=(x, y_offset))
		surface.blit(line_surface, line_rect)
		y_offset += line_surface.get_height() + line_spacing

	return y_offset - y  # total height drawn

# --- Base Scene Class ---
class Scene:
	def __init__(self, app):
		self.app = app

	def handle_events(self, event):
		pass

	def update(self):
		pass

	def draw(self, surface):
		pass

	def on_enter(self):
		pass

# --- Welcome Scene ---
class WelcomeScene(Scene):
	def __init__(self, app):
		super().__init__(app)
		self.font_en = pygame.font.Font(notoFont, 36)  # English
		self.font_jp = pygame.font.Font(notoFont, 36)  # Japanese

	def handle_events(self, event):
		if event.type == pygame.KEYDOWN or event.type == pygame.MOUSEBUTTONDOWN:
			self.app.switch_scene("wifi_check")  # go to wifi_check
	def draw(self, surface):
		surface.fill(white)

		# English text (top)
		text_surface_en = self.font_en.render("Welcome to BMI Trainer", True, black)
		text_rect_en = text_surface_en.get_rect(center=(240, 110))
		surface.blit(text_surface_en, text_rect_en)

		# Japanese text (bottom)
		text_surface_jp = self.font_jp.render("BMIトレーナーへようこそ", True, black)
		text_rect_jp = text_surface_jp.get_rect(center=(240, 190))
		surface.blit(text_surface_jp, text_rect_jp)

# --- Main Menu Scene (placeholder) ---
class WiFiCheckScene(Scene):
	def __init__(self, app):
		super().__init__(app)
		self.font_en = pygame.font.Font(notoFont, 22)
		self.font_jp = pygame.font.Font(notoFont, 22)
		self.status = "checking"  # "checking", "success", or "fail"
		self.last_check_time = 0
		self.retry_interval = 3  # seconds between retry attempts
  
		# Spinner setup
		self.spinner_angle = 0
		self.spinner_radius = 20
		self.spinner_center = (440, 280)  # adjust as needed
		self.spinner_speed = -2  # degrees per frame

	def handle_events(self, event):
		if event.type == pygame.KEYDOWN or event.type == pygame.MOUSEBUTTONDOWN:
			if self.status == "success":
				self.app.switch_scene("bci_connect")  # go to bci_connect

	def check_internet(self, host="8.8.8.8", port=53, timeout=2):
		try:
			socket.setdefaulttimeout(timeout)
			s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			s.connect((host, port))
			s.close()
			return True
		except Exception:
			return False

	def update(self):
		current_time = time.time()
  
		# Rotate spinner continuously
		self.spinner_angle = (self.spinner_angle + self.spinner_speed) % 360
  
		# Only retry if not already successful AND retry interval has passed
		if self.status != "success" and current_time - self.last_check_time > self.retry_interval:
			self.last_check_time = current_time
			self.status = "checking"  # show checking message first
			pygame.display.flip()     # force draw immediately
			
			# Developer mode override - skip internet check
			if self.app.developer_mode:
				self.status = "success"
			elif self.check_internet():
				self.status = "success"
			else:
				self.status = "fail"

	def draw(self, surface):
		surface.fill(white)

		if self.status == "checking":
			msg_en = "Checking internet connection,\nplease wait..."
			msg_jp = "インターネット接続を確認中です、\nしばらくお待ちください"
		elif self.status == "success":
			msg_en = "Internet connection is successful,\nyou may continue."
			msg_jp = "インターネット接続に成功しました、\n続行できます"
		else:  # fail
			msg_en = "Internet connection failed,\nretrying..."
			msg_jp = "インターネット接続に失敗しました、\n再試行中です..."

		# Draw English and Japanese text
		draw_text_wrapped(surface, msg_en, self.font_en, black, x=40, y=70, max_width=400)
		draw_text_wrapped(surface, msg_jp, self.font_jp, black, x=40, y=170, max_width=400, lang="jp")
  
		# Draw spinner if checking or retrying
		if self.status in ["checking", "fail"]:
			num_lines = 12
			for i in range(num_lines):
				angle_deg = (360 / num_lines) * i + self.spinner_angle
				angle_rad = math.radians(angle_deg)
				x = self.spinner_center[0] + self.spinner_radius * math.cos(angle_rad)
				y = self.spinner_center[1] + self.spinner_radius * math.sin(angle_rad)
				pygame.draw.circle(surface, black, (int(x), int(y)), 3)

# --- BCI Connection Check Scene ---
class BCIConnectScene(Scene):
	def __init__(self, app):
		super().__init__(app)
		self.font_en = pygame.font.Font(notoFont, 22)
		self.font_jp = pygame.font.Font(notoFont, 22)
		self.status = "checking"  # "checking", "connected", "wait_cables", "failed"
		self.last_check_time = 0
		self.retry_interval = 3  # seconds between retries
		self.retry_count = 0
		self.max_retries = 8
		self.board = None

		# Spinner setup
		self.spinner_angle = 0
		self.spinner_radius = 20
		self.spinner_center = (440, 280)
		self.spinner_speed = -2  # degrees per frame

		# Timer for showing "connected" message
		self.connected_time = None

	def handle_events(self, event):
		pass  # no interaction for now

	def update(self):
		current_time = time.time()
		self.spinner_angle = (self.spinner_angle + self.spinner_speed) % 360

		if self.status == "checking" and current_time - self.last_check_time > self.retry_interval:
			self.last_check_time = current_time
			threading.Thread(target=self._try_connect, daemon=True).start()

		if self.status == "connected" and current_time - self.connected_time >= 1:
			if self.app.developer_mode:
				self.app.switch_scene("trainer") #SKIP IMPEDANCE
			else:
				self.app.switch_scene("impedance_check_gray")# Automatically move to first cable check (Gray)

	def _try_connect(self):
		
		# Developer mode override - skip actual BCI connection
		if self.app.developer_mode and self.app.dev_skip_bci_connect:
			self.status = "connected"
			self.connected_time = time.time()
			self.retry_count = 0
			# Create a mock board object for developer mode
			self.app.bciboard = None  # Will be handled by other scenes
			return
			
		try:
			self.board = ABMI_Utils.BCIBoard(port="/dev/bci_dongle")
			success = self.board.connect()
			if success:
				self.status = "connected"
				self.connected_time = time.time()
				self.retry_count = 0
				# Make the board globally accessible to other scenes
				self.app.bciboard = self.board
			else:
				raise RuntimeError("Connection failed")
			
		except Exception as e:
			self.retry_count += 1
			if self.retry_count >= self.max_retries:
				print("Connection Failed")
				self.status = "failed"
			else:
				print("Connection Failed, Retrying...")
				self.status = "checking"

	def draw(self, surface):
		surface.fill(white)

		if self.status == "checking":
			msg_en = "Checking for board connection, please wait..."
			msg_jp = "ボード接続を確認中です、\nしばらくお待ちください..."
		elif self.status == "connected":
			msg_en = "BCI Device Connected"
			msg_jp = "BCIデバイスが接続されました"
		elif self.status == "failed":
			msg_en = "Failed to connect to BCI Device\nPlease try again or contact support"
			msg_jp = "BCIデバイスの接続に失敗しました\n再試行するかサポートに連絡してください"
		else:
			msg_en = ""
			msg_jp = ""

		# Draw English and Japanese text
		draw_text_wrapped(surface, msg_en, self.font_en, black, x=40, y=70, max_width=400)
		draw_text_wrapped(surface, msg_jp, self.font_jp, black, x=40, y=170, max_width=420, lang="jp")
		
		# Draw spinner if checking
		if self.status == "checking":
			num_lines = 12
			for i in range(num_lines):
				angle_deg = (360 / num_lines) * i + self.spinner_angle
				angle_rad = math.radians(angle_deg)
				x = self.spinner_center[0] + self.spinner_radius * math.cos(angle_rad)
				y = self.spinner_center[1] + self.spinner_radius * math.sin(angle_rad)
				pygame.draw.circle(surface, black, (int(x), int(y)), 3)

# --- Impedance Check Single Scene (for individual cables) ---
class ImpedanceCheckSingleScene(Scene):
	def __init__(self, app, cable_index, cable_name, cable_color_rgb):
		super().__init__(app)
		self.font_en = pygame.font.Font(notoFont, 24)
		self.font_jp = pygame.font.Font(notoFont, 24)
		self.status = "waiting"  # "waiting", "checking", "done"
		self.result = None
		self.cable_index = cable_index  # 0-based index
		self.cable_name = cable_name    # e.g., "Gray", "Purple", etc.
		self.cable_color_rgb = cable_color_rgb
		
		# Spinner setup
		self.spinner_angle = 0
		self.spinner_radius = 15
		self.spinner_center = (240, 260)  # bottom-left spinner
		self.spinner_speed = -5
		
		# Developer mode simulation timing
		self.dev_sim_start_time = None
		self.dev_sim_duration = 1.0  # seconds

	def handle_events(self, event):
		pass  # no interaction during checking

	def reset(self):
		self.status = "waiting"
		self.result = None
		self.dev_sim_start_time = None

	def start_impedance_check(self):
		self.status = "checking"
		if self.app.developer_mode:
			# Start non-blocking simulation timing
			self.dev_sim_start_time = time.time()
			# Precompute simulated result for this cable
			simulated_impedances = [40.8, 59.23, 40.0, 25.5, 75.2, 12.5, 85.7, 45.3]
			self.result = simulated_impedances[self.cable_index]
		else:
			threading.Thread(target=self._impedance_worker, daemon=True).start()

	def _impedance_worker(self):
		self.status = "checking"
		
		# Developer mode handled in update() non-blockingly
		if self.app.developer_mode:
			return
			
		# Normal mode - check actual board
		if not hasattr(self.app, "bciboard") or self.app.bciboard is None:
			self.result = float("nan")
			self.status = "done"
			return

		try:
			# check_impedance expects a list of channels (1-based)
			channel_num = self.cable_index + 1
			impedance_result = self.app.bciboard.check_impedance([channel_num])
			self.result = impedance_result[0][1] if impedance_result else float("nan")
		except Exception as e:
			self.result = float("nan")

		self.status = "done"

	def update(self):
     
		if self.status == "waiting":
			self.start_impedance_check()
		elif self.status == "checking":
			self.spinner_angle = (self.spinner_angle + self.spinner_speed) % 360
			# Drive developer-mode non-blocking simulation timing
			if self.app.developer_mode and self.dev_sim_start_time is not None:
				elapsed = time.time() - self.dev_sim_start_time
				if elapsed >= self.dev_sim_duration:
					self.status = "done"
		elif self.status == "done":
			# Store result
			self.app.current_cable_result = (self.cable_index, self.cable_name, self.result)

			# Preload and prepare results scene before showing
			results_scene = self.app.scenes["impedance_results_single"]
			results_scene.cable_index = self.cable_index
			results_scene.cable_name = self.cable_name
			results_scene.impedance_value = self.result
			results_scene.retry_needed = (
				np.isnan(self.result) or self.result >= 100
			)

			# Now switch after it's fully ready
			self.app.switch_scene("impedance_results_single")

	def draw(self, surface):
		surface.fill(white)

		# --- Left side texts ---
		x_text = 30
		y_text = 60
		# Checking specific cable connection
		cable_msg_en = f"Checking {self.cable_name} cable connection..."
		cable_msg_jp = f"{self.cable_name}ケーブル接続を確認中..."
		draw_text_wrapped(surface, cable_msg_en, self.font_en, black, x=x_text, y=y_text, max_width=300)
		draw_text_wrapped(surface, cable_msg_jp, self.font_jp, black, x=x_text, y=y_text+90, max_width=200, lang="jp")

		# Spinner (only while checking)
		if self.status == "checking":
			num_lines = 12
			for i in range(num_lines):
				angle_deg = (360 / num_lines) * i + self.spinner_angle
				angle_rad = math.radians(angle_deg)
				x = self.spinner_center[0] + self.spinner_radius * math.cos(angle_rad)
				y = self.spinner_center[1] + self.spinner_radius * math.sin(angle_rad)
				pygame.draw.circle(surface, black, (int(x), int(y)), 3)

		# --- Right side cable square ---
		square_size = 120
		x_square = 320
		y_square = 90
		if self.status == "waiting":
			cable_color_rgb = (0, 0, 0)  # Black for waiting
		else:
			cable_color_rgb = self.cable_color_rgb
		border_thickness = 4

		# Draw border
		pygame.draw.rect(surface, black, (x_square, y_square, square_size, square_size), border_thickness)
		# Fill inside
		pygame.draw.rect(
			surface,
			cable_color_rgb,
			(
				x_square + border_thickness,
				y_square + border_thickness,
				square_size - 2 * border_thickness,
				square_size - 2 * border_thickness
			)
		)

# --- Impedance Results Single Scene (for individual cables) ---
class ImpedanceResultsSingleScene(Scene):
	def __init__(self, app):
		super().__init__(app)
		self.font_en = pygame.font.Font(notoFont, 20)
		self.font_jp = pygame.font.Font(notoFont, 18)
		self.font_large = pygame.font.Font(notoFont, 24)
		
		# Results will be set when switching to this scene
		self.cable_index = None
		self.cable_name = None
		self.impedance_value = None
		self.retry_needed = False

	def _advance_to_next_cable(self):
		"""Switch to the next cable scene or trainer when complete."""
		if self.cable_index is None:
			return

		next_index = self.cable_index + 1
		if next_index < len(ABMI_Utils.CABLE_COLORS):
			next_cable_name = ABMI_Utils.CABLE_COLORS[next_index]
			self.app.switch_scene(f"impedance_check_{next_cable_name}")
		else:
			self.app.switch_scene("trainer")

	def handle_events(self, event):
		if event.type == pygame.KEYDOWN and event.key == pygame.K_b and self.retry_needed:
			print(f"Bypassing retry for {self.cable_name}, moving to next cable.")
			self._advance_to_next_cable()
			return

		if event.type == pygame.KEYDOWN or event.type == pygame.MOUSEBUTTONDOWN:
			if self.retry_needed:
				scene_key = f"impedance_check_{self.cable_name.lower()}"
				print(f"Retrying impedance check for {self.cable_name}...")

				# Reset the status so the check starts over
				cable_scene = self.app.scenes[scene_key]
				cable_scene.status = "waiting"
				cable_scene.result = None
				cable_scene.dev_sim_start_time = None  # if in developer mode

				self.app.switch_scene(scene_key)
				return

			self._advance_to_next_cable()

	def update(self):
		if hasattr(self.app, 'current_cable_result'):
			self.cable_index, self.cable_name, self.impedance_value = self.app.current_cable_result

	def draw(self, surface):
		surface.fill(white)
		
		if self.cable_name is None:
			return
		
		if not np.isnan(self.impedance_value):
			# Determine color and retry flag
			if self.impedance_value < 50:
				value_color = green
				status_text, status_jp = "EXCELLENT", "優秀"
				self.retry_needed = False
			elif self.impedance_value < 100:
				value_color = warning_orange
				status_text, status_jp = "GOOD", "良好"
				self.retry_needed = False
			else:
				value_color = red
				status_text, status_jp = "POOR", "不良"
				self.retry_needed = True
		else:
			value_color = red
			status_text, status_jp = "ERROR", "接続エラー"
			self.retry_needed = True

		# Shift all text upward if retry needed
		y_offset = -30 if self.retry_needed else 0

		# Titles
		title_en = f"{self.cable_name} Cable Result"
		title_jp = f"{self.cable_name}ケーブル結果"
		title_surface_en = self.font_large.render(title_en, True, black)
		title_surface_jp = self.font_large.render(title_jp, True, black)
		surface.blit(title_surface_en, title_surface_en.get_rect(center=(240, 80 + y_offset)))
		surface.blit(title_surface_jp, title_surface_jp.get_rect(center=(240, 120 + y_offset)))

		# Impedance text (skip if NaN handled below)
		if not np.isnan(self.impedance_value):
			imp_text = f"{self.impedance_value:.1f} kΩ"
			imp_surface = self.font_large.render(imp_text, True, value_color)
			surface.blit(imp_surface, imp_surface.get_rect(center=(240, 170 + y_offset)))

			status_surface_en = self.font_en.render(status_text, True, value_color)
			status_surface_jp = self.font_jp.render(status_jp, True, value_color)
			surface.blit(status_surface_en, status_surface_en.get_rect(center=(240, 200 + y_offset)))
			surface.blit(status_surface_jp, status_surface_jp.get_rect(center=(240, 230 + y_offset)))
		else:
			err_en = self.font_large.render("CONNECTION ERROR", True, red)
			err_jp = self.font_jp.render("接続エラー", True, red)
			surface.blit(err_en, err_en.get_rect(center=(240, 180 + y_offset)))
			surface.blit(err_jp, err_jp.get_rect(center=(240, 210 + y_offset)))

		# Retry message
		if self.retry_needed:
			msg_en = "Please fix the cable connection and retry."
			msg_jp = "ケーブルの接続を直して、再試行してください。"
			msg_surface_en = self.font_en.render(msg_en, True, black)
			msg_surface_jp = self.font_jp.render(msg_jp, True, black)
			surface.blit(msg_surface_en, msg_surface_en.get_rect(center=(240, 280 + y_offset)))
			surface.blit(msg_surface_jp, msg_surface_jp.get_rect(center=(240, 310 + y_offset)))

# --- Trainer Scene ---
class TrainerScene(Scene):
	def __init__(self, app):
		super().__init__(app)
		self.app = app
		self.app.user_id = ABMI_Utils.getUserID("BMI Trainer Data/UserID.txt")
		ABMI_Utils.deleteEmptyFolders(base_path="BMI Trainer Data/") #Delete empty folders before creating a Session Folder
		self.app.session_Folder = ABMI_Utils.createSessionFolder(self.app.user_id, datetime.datetime.now(), base_path="BMI Trainer Data/")
		self.app.model_Folder = ABMI_Utils.createModelFolder(base_path="Model/")
		self.app.testing_Folder = ABMI_Utils.createTestingFolder(base_path="Testing/")
		self.buttons = []

		# Button Creation
		self.add_button("Train BMI", 10, 15, 200, 90, self.train_bmi, font_size=28, color=soft_green)
		self.add_button("Delete Recent", 10, 115, 200, 90, self.delete_recent, font_size=24, color=light_red)
		self.add_button("Check Impedance", 10, 215, 200, 90, self.check_impedance, font_size=20, color=cool_blue)
		self.add_button("Left", 220, 215, 80, 90, self.audio_left, font_size=20, color=white)
		self.add_button("Center", 305, 215, 80, 90, self.audio_center, font_size=20, color=white)
		self.add_button("Right", 390, 215, 80, 90, self.audio_right, font_size=20, color=white)
		self.add_button("Continue →", 255, 100, 180, 70, self.continue_upload, font_size=24, color=warning_orange)

		#Font for labels like "Test Audio"
		self.label_font = pygame.font.Font(notoFont, 24)
		self.userid_font = pygame.font.Font(notoFont, 22)

	def add_button(self, text, x, y, w, h, callback, font_size=28, color=white):
		button = {
			"rect": pygame.Rect(x, y, w, h),
			"text": text,
			"callback": callback,
			"font": pygame.font.Font(notoFont, font_size),
			"color": color
		}
		self.buttons.append(button)

	def train_bmi(self):
		print("Train BMI clicked! Switching to CollectDataSingleScene...")
		self.app.switch_scene("collect_data_single")

	def delete_recent(self):
		ABMI_Utils.deleteMostRecent(base_path="BMI Trainer Data/")
		self.app.refresh_lcr_count()

	def check_impedance(self):
		print("Restarting impedance check sequence...")

		# --- Reset impedance data ---
		self.app.impedance_results = []
		self.app.current_cable_result = None

		# --- Reset each ImpedanceCheckSingleScene state ---
		for scene_name, scene_obj in self.app.scenes.items():
			if isinstance(scene_obj, ImpedanceCheckSingleScene):
				scene_obj.reset()

		# --- Jump to first impedance check scene ---
		first_cable = ABMI_Utils.CABLE_COLORS[0]
		scene_name = f"impedance_check_{first_cable}"
		if scene_name in self.app.scenes:
			self.app.switch_scene(scene_name)
		else:
			print(f"Scene '{scene_name}' not found!")

	def continue_upload(self):
		self.app.switch_scene("upload_to_cloud")

	def audio_left(self):
		ABMI_Utils.play_single_sound('Sounds/beep_left.wav')

	def audio_center(self):
		ABMI_Utils.play_single_sound('Sounds/beep_center.wav')

	def audio_right(self):
		ABMI_Utils.play_single_sound('Sounds/beep_right.wav')

	def handle_events(self, event):
		if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
			mx, my = event.pos
			for btn in self.buttons:
				if btn["rect"].collidepoint(mx, my):
					btn["callback"]()

	def update(self):
		if self.app.developer_mode:
			return
		elif not self.app.bciboard.connected:
			self.app.switch_scene("emergency")
		pass

	def draw(self, surface):
		surface.fill(white)

		# --- Draw "Test Audio" label ---
		label_surface = self.label_font.render("Test Audio", True, black)
		label_rect = label_surface.get_rect(center=(345, 195))  # center above audio buttons
		surface.blit(label_surface, label_rect)

		# --- Draw User ID (top right) ---
		user_text = f"User ID: {self.app.user_id}"
		user_surface = self.userid_font.render(user_text, True, black)
		user_rect = user_surface.get_rect(topright=(surface.get_width() - 30, 10))
		surface.blit(user_surface, user_rect)

		# --- Draw User LCR Count ---
		left_count, center_count, right_count = (self.app.recording_lcr_counts
			if getattr(self.app, "recording_lcr_counts", None)
			else (0, 0, 0))
		lcr_text = f"L: {left_count}   C: {center_count}   R: {right_count}"
		lcr_surface = self.userid_font.render(lcr_text, True, black)
		lcr_rect = lcr_surface.get_rect(topright=(surface.get_width() - 30, user_rect.bottom + 8))
		surface.blit(lcr_surface, lcr_rect)

		# --- Draw buttons ---
		for btn in self.buttons:
			pygame.draw.rect(surface, btn["color"], btn["rect"])
			pygame.draw.rect(surface, black, btn["rect"], 3)  # border
			text_surface = btn["font"].render(btn["text"], True, black)
			text_rect = text_surface.get_rect(center=btn["rect"].center)
			surface.blit(text_surface, text_rect)

# --- Upload To Cloud Scene ---
class UploadToCloudScene(Scene):
	def __init__(self, app):
		super().__init__(app)
		self.app = app
		self.title_font = pygame.font.Font(notoFont, 28)
		self.count_font = pygame.font.Font(notoFont, 24)
		self.status_font = pygame.font.Font(notoFont, 20)
		self.buttons = []
		self.cloudConnection = None
		self.isConnected = False
		self.cloudDataCount = 0
		self.status_message = ""
		self.uploading = False
		self.upload_thread = None

		# Spinner config (matches other scenes)
		self.spinner_angle = 0
		self.spinner_radius = 18
		self.spinner_center = (self.app.render_w - 40, self.app.render_h - 40)
		self.spinner_speed = -2

		self.add_button("← Trainer", 15, 150, 140, 70, self.go_back, font_size=22, color=cool_blue)
		self.add_button("Upload", 170, 140, 120, 90, self.upload_action, font_size=26, color=soft_green)
		self.add_button("Download →", 305, 150, 160, 70, self.go_download, font_size=22, color=warning_orange)

	def add_button(self, text, x, y, w, h, callback, font_size=28, color=white):
		button = {
			"rect": pygame.Rect(x, y, w, h),
			"text": text,
			"callback": callback,
			"font": pygame.font.Font(notoFont, font_size),
			"color": color
		}
		self.buttons.append(button)

	def on_enter(self):
		self.status_message = ""
		self.uploading = False
		if not self.cloudConnection:
			try:
				self.cloudConnection = ABMI_Utils.CloudConnection(self.app.cloud_ip, self.app.cloud_user, self.app.cloud_password)
				self.cloudConnection.connect()
				self.isConnected = True
			except Exception as err:
				print(f"Cloud connection failed: {err}")
				self.cloudConnection = None
				self.isConnected = False
		if self.cloudConnection:
			try:
				if not self.cloudConnection.folder_exists("/Training_Data/" + self.app.user_id):
					print('User Folder not found, creating user folder for ' + str(self.app.user_id))
					self.cloudConnection.create_user_folder("/Training_Data/" + self.app.user_id)
				self.cloudDataCount = self.cloudConnection.count_files_in_folder("/Training_Data/" + self.app.user_id)
				self.status_message = ""
			except Exception as err:
				print(f"Failed to refresh cloud data count: {err}")
				self.status_message = "Failed to load cloud count"
				self.cloudDataCount = 0

	def go_back(self):
		self.app.switch_scene("trainer")

	def upload_action(self):
		print("Uploading all files to cloud!")
		if not self.cloudConnection:
			self.status_message = "Not connected to cloud"
			return
		if self.uploading:
			return
		self.uploading = True
		self.status_message = "Uploading..."
		self.upload_thread = threading.Thread(target=self._run_upload, daemon=True)
		self.upload_thread.start()

	def _run_upload(self):
		try:
			files_uploaded = self.cloudConnection.upload_all_files(remote_root="/Training_Data/" + self.app.user_id, user_id=self.app.user_id, local_root="BMI Trainer Data")
			print(f"Uploaded {files_uploaded} files to cloud.")
			self.cloudDataCount = self.cloudConnection.count_files_in_folder("/Training_Data/" + self.app.user_id)
			self.status_message = "Upload complete!" if files_uploaded else "No files to upload"
		except Exception as err:
			print(f"Upload failed: {err}")
			self.status_message = "Upload failed"
		finally:
			self.uploading = False

	def go_download(self):
		self.app.switch_scene("download_from_cloud")

	def handle_events(self, event):
		if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
			mx, my = event.pos
			for btn in self.buttons:
				if btn["rect"].collidepoint(mx, my):
					btn["callback"]()

	def update(self):
		if self.uploading:
			self.spinner_angle = (self.spinner_angle + self.spinner_speed) % 360

	def draw(self, surface):
		surface.fill(white)
		
		title_surface = self.title_font.render("Upload To Cloud", True, black)
		title_rect = title_surface.get_rect(center=(surface.get_width() // 2, 60))
		surface.blit(title_surface, title_rect)
  
		count_surface = self.count_font.render(f"Data Count: {self.cloudDataCount}", True, black)
		count_rect = count_surface.get_rect(center=(surface.get_width() // 2, 100))
		surface.blit(count_surface, count_rect)

		status_surface = self.status_font.render(self.status_message, True, black)
		status_rect = status_surface.get_rect(center=(surface.get_width() // 2, surface.get_height() - 30))
		surface.blit(status_surface, status_rect)

		if self.uploading:
			num_lines = 12
			for i in range(num_lines):
				angle_deg = (360 / num_lines) * i + self.spinner_angle
				angle_rad = math.radians(angle_deg)
				x = self.spinner_center[0] + self.spinner_radius * math.cos(angle_rad)
				y = self.spinner_center[1] + self.spinner_radius * math.sin(angle_rad)
				pygame.draw.circle(surface, black, (int(x), int(y)), 3)

		for btn in self.buttons:
			pygame.draw.rect(surface, btn["color"], btn["rect"])
			pygame.draw.rect(surface, black, btn["rect"], 3)
			text_surface = btn["font"].render(btn["text"], True, black)
			text_rect = text_surface.get_rect(center=btn["rect"].center)
			surface.blit(text_surface, text_rect)

# --- Download From Cloud Scene ---
class DownloadFromCloudScene(Scene):
	def __init__(self, app):
		super().__init__(app)
		self.app = app
		self.title_font = pygame.font.Font(notoFont, 28)
		self.status_font = pygame.font.Font(notoFont, 24)
		self.message_font = pygame.font.Font(notoFont, 20)
		self.buttons = []
		self.cloudConnection = None
		self.model_available = False
		self.availability_message = "Checking..."
		self.bottom_message = ""
		self.downloading = False
		self.download_thread = None

		self.spinner_angle = 0
		self.spinner_radius = 18
		self.spinner_center = (self.app.render_w - 40, self.app.render_h - 40)
		self.spinner_speed = -2

		self.add_button("← Upload", 15, 150, 140, 70, self.go_upload, font_size=22, color=cool_blue)
		self.add_button("Download", 170, 140, 140, 90, self.download_action, font_size=24, color=soft_green)
		self.add_button("Test →", 325, 150, 140, 70, self.go_test, font_size=22, color=warning_orange)

	def add_button(self, text, x, y, w, h, callback, font_size=28, color=white):
		button = {
			"rect": pygame.Rect(x, y, w, h),
			"text": text,
			"callback": callback,
			"font": pygame.font.Font(notoFont, font_size),
			"color": color
		}
		self.buttons.append(button)

	def ensure_connection(self):
		if not self.cloudConnection:
			try:
				self.cloudConnection = ABMI_Utils.CloudConnection(self.app.cloud_ip, self.app.cloud_user, self.app.cloud_password)
				self.cloudConnection.connect()
			except Exception as err:
				print(f"Cloud connection failed: {err}")
				self.cloudConnection = None

	def on_enter(self):
		self.bottom_message = ""
		self.downloading = False
		self.ensure_connection()
		if not self.cloudConnection:
			self.availability_message = "Unable to connect"
			self.model_available = False
			return
		try:
			count = self.cloudConnection.count_files_in_folder("/Models/" + self.app.user_id)
			self.model_available = count > 0
			self.availability_message = "Model Available" if self.model_available else "No Model Available"
		except Exception as err:
			print(f"Failed to query cloud data: {err}")
			self.availability_message = "Failed to load"
			self.model_available = False

	def go_upload(self):
		self.app.switch_scene("upload_to_cloud")

	def download_action(self):
		if not self.cloudConnection:
			self.bottom_message = "Not connected to cloud"
			return
		if self.downloading:
			return
		self.downloading = True
		self.bottom_message = "Downloading..."
		self.download_thread = threading.Thread(target=self._run_download, daemon=True)
		self.download_thread.start()

	def _run_download(self):
		try:
			# Placeholder for future download logic
			self.cloudConnection.download_all_files(remote_root="/Models/" + self.app.user_id, local_root="Model/")
			self.bottom_message = "Download Complete"
			print("Successfully downloaded model from cloud.")
		except Exception as err:
			print(f"Download failed: {err}")
			self.bottom_message = "Download failed"
		finally:
			self.downloading = False

	def go_test(self):
		self.app.switch_scene("model_test")

	def handle_events(self, event):
		if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
			mx, my = event.pos
			for btn in self.buttons:
				if btn["rect"].collidepoint(mx, my):
					btn["callback"]()

	def update(self):
		if self.downloading:
			self.spinner_angle = (self.spinner_angle + self.spinner_speed) % 360

	def draw(self, surface):
		surface.fill(white)
		title_surface = self.title_font.render("Download From Cloud", True, black)
		title_rect = title_surface.get_rect(center=(surface.get_width() // 2, 60))
		surface.blit(title_surface, title_rect)

		status_surface = self.status_font.render(self.availability_message, True, black)
		status_rect = status_surface.get_rect(center=(surface.get_width() // 2, 100))
		surface.blit(status_surface, status_rect)

		for btn in self.buttons:
			pygame.draw.rect(surface, btn["color"], btn["rect"])
			pygame.draw.rect(surface, black, btn["rect"], 3)
			text_surface = btn["font"].render(btn["text"], True, black)
			text_rect = text_surface.get_rect(center=btn["rect"].center)
			surface.blit(text_surface, text_rect)

		bottom_surface = self.message_font.render(self.bottom_message, True, black)
		bottom_rect = bottom_surface.get_rect(center=(surface.get_width() // 2, surface.get_height() - 30))
		surface.blit(bottom_surface, bottom_rect)

		if self.downloading:
			num_lines = 12
			for i in range(num_lines):
				angle_deg = (360 / num_lines) * i + self.spinner_angle
				angle_rad = math.radians(angle_deg)
				x = self.spinner_center[0] + self.spinner_radius * math.cos(angle_rad)
				y = self.spinner_center[1] + self.spinner_radius * math.sin(angle_rad)
				pygame.draw.circle(surface, black, (int(x), int(y)), 3)

# --- Model Test Scene ---
class ModelTestScene(Scene):
	def __init__(self, app):
		super().__init__(app)
		self.app = app
		self.title_font = pygame.font.Font(notoFont, 28)
		self.status_font = pygame.font.Font(notoFont, 22)
		self.buttons = []
		self.state = "idle"  # idle, collecting, confirm, label
		self.bottom_message = ""
		self.prediction_message = ""
		self.is_collecting = False
		self.sequence_thread = None
		self.sequence_stop_event = None
		self.latest_test_file = None
		self.predicted_lcr = None
		self.awaiting_result = False

		self.spinner_angle = 0
		self.spinner_radius = 18
		self.spinner_center = (self.app.render_w - 40, self.app.render_h - 40)
		self.spinner_speed = -2

		self.configure_buttons()

	def add_button(self, text, x, y, w, h, callback, font_size=28, color=white):
		button = {
			"rect": pygame.Rect(x, y, w, h),
			"text": text,
			"callback": callback,
			"font": pygame.font.Font(notoFont, font_size),
			"color": color
		}
		self.buttons.append(button)

	def configure_buttons(self):
		self.buttons = []
		if self.state == "idle":
			self.add_button("← Download", 25, 160, 170, 70, self.go_back, font_size=22, color=cool_blue)
			self.add_button("Begin", 210, 145, 160, 100, self.begin_action, font_size=30, color=soft_green)
		elif self.state == "collecting":
			self.add_button("Cancel", 165, 160, 150, 70, self.cancel_action, font_size=26, color=light_red)
		elif self.state == "confirm":
			self.add_button("No", 60, 170, 140, 80, self.discard_action, font_size=26, color=light_red)
			self.add_button("Yes", 260, 170, 160, 80, self.save_action, font_size=26, color=soft_green)
		elif self.state == "label":
			self.add_button("Left", 20, 165, 130, 80, lambda: self.label_action(1), font_size=24, color=white)
			self.add_button("Center", 175, 165, 130, 80, lambda: self.label_action(2), font_size=24, color=white)
			self.add_button("Right", 330, 165, 130, 80, lambda: self.label_action(3), font_size=24, color=white)

	def set_state(self, new_state):
		self.state = new_state
		if new_state == "idle":
			self.is_collecting = False
			self.sequence_thread = None
			self.sequence_stop_event = None
			self.predicted_lcr = None
			self.awaiting_result = False
			if not self.bottom_message.startswith("Saved"):
				self.bottom_message = ""
		elif new_state == "collecting":
			self.is_collecting = True
			self.bottom_message = "Collecting data"
		elif new_state == "confirm":
			self.is_collecting = False
			self.bottom_message = ""
		elif new_state == "label":
			self.is_collecting = False
			self.bottom_message = ""
		self.configure_buttons()

	def go_back(self):
		if self.state == "collecting":
			return
		self.app.switch_scene("download_from_cloud")

	def begin_action(self):
		if self.state != "idle" or self.is_collecting:
			return
		board = getattr(self.app, "bciboard", None)
		if board is None:
			self.bottom_message = "No BCIBoard available"
			return
		if not getattr(board, "connected", False):
			self.bottom_message = "Board not connected"
			return
		if not getattr(board, "streaming", False):
			try:
				board.stream()
			except Exception as err:
				print(f"Failed to start board stream: {err}")
				self.bottom_message = "Stream failed"
				return

		timestamp = datetime.datetime.now()
		lcr_choice = 0
		if hasattr(timestamp, 'strftime'):
			timestamp_str = timestamp.strftime('%Y-%m-%d-%H-%M-%S')
		else:
			timestamp_str = str(timestamp)
		self.latest_test_file = os.path.join(self.app.testing_Folder, f"{self.app.user_id}-{timestamp_str}-{lcr_choice}.csv")

		try:
			self.sequence_thread, self.sequence_stop_event = ABMI_Utils.startSingleTrainingSequence(
				board, self.app.user_id, timestamp, lcr_choice, self.app.testing_Folder
			)
			self.awaiting_result = True
			self.set_state("collecting")

			def _wait_and_predict():
				self.sequence_thread.join()
				if not self.awaiting_result:
					return
				self.sequence_thread = None
				self.sequence_stop_event = None
				if not self.latest_test_file:
					self.bottom_message = "No test result found"
				else:
					try:
						result = ABMI_Utils.useModelToPredict(self.latest_test_file, self.app.model_Folder)
						if isinstance(result, np.ndarray):
							result = int(result[0])
						self.predicted_lcr = result
						if result == -1:
							self.prediction_message = "Prediction failed"
							ABMI_Utils.play_single_sound("Sounds/prediction_unknown.wav")
						else:
							label_map = {1: "Left", 2: "Center", 3: "Right"}
							self.prediction_message = f"Model predicted: {label_map.get(result, 'Unknown')}"
							sound_map = {
								1: "Sounds/prediction_left.wav",
								2: "Sounds/prediction_center.wav",
								3: "Sounds/prediction_right.wav"
							}
							ABMI_Utils.play_single_sound(sound_map.get(result, "Sounds/prediction_unknown.wav"))
					except Exception as err:
						print(f"Model prediction failed: {err}")
						self.prediction_message = "Prediction error"
						self.predicted_lcr = -1
						ABMI_Utils.play_single_sound("Sounds/prediction_unknown.wav")
				self.awaiting_result = False
				self.set_state("confirm")

			threading.Thread(target=_wait_and_predict, daemon=True).start()
		except Exception as err:
			print(f"Model test failed to start: {err}")
			self.sequence_thread = None
			self.sequence_stop_event = None
			self.latest_test_file = None
			self.awaiting_result = False
			self.bottom_message = "Test failed to start"

	def cancel_action(self):
		if self.sequence_stop_event:
			self.sequence_stop_event.set()
		self.set_state("idle")
		self.bottom_message = "Test cancelled"

	def discard_action(self):
		ABMI_Utils.deleteTestingFiles(base_path=self.app.testing_Folder)
		self.latest_test_file = None
		self.awaiting_result = False
		self.set_state("idle")
		self.bottom_message = "Data discarded"

	def save_action(self):
		self.set_state("label")

	def label_action(self, lcr_value):
		if not self.latest_test_file:
			self.bottom_message = "No test file to save"
			self.set_state("idle")
			return

		label_map = {1: "Left", 2: "Center", 3: "Right"}
		label_text = label_map.get(lcr_value, "Unknown")
		try:
			ABMI_Utils.labelTestingFile(self.latest_test_file, self.app.session_Folder, lcr_value)
			self.bottom_message = f"Saved: {label_text}"
		except Exception as err:
			print(f"Failed to label testing file: {err}")
			self.bottom_message = "Save failed"
		self.latest_test_file = None
		self.awaiting_result = False
		self.set_state("idle")

	def handle_events(self, event):
		if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
			mx, my = event.pos
			for btn in self.buttons:
				if btn["rect"].collidepoint(mx, my):
					btn["callback"]()

	def update(self):
		if self.is_collecting:
			self.spinner_angle = (self.spinner_angle + self.spinner_speed) % 360
		if self.sequence_thread and not self.sequence_thread.is_alive():
			self.sequence_thread = None
			self.sequence_stop_event = None
			self.is_collecting = False

	def draw(self, surface):
		surface.fill(white)
		if self.state == "confirm":
			title = "Would you like to save this data?"
		elif self.state == "label":
			title = "Please label this data"
		else:
			title = "Test Current Model"

		title_surface = self.title_font.render(title, True, black)
		title_rect = title_surface.get_rect(center=(surface.get_width() // 2, 60))
		surface.blit(title_surface, title_rect)

		if self.state == "confirm":
			description = self.prediction_message
		elif self.state == "label":
			description = "Which direction did you choose?"
		else:
			description = "Successful tests can be saved."
		desc_surface = self.status_font.render(description, True, black)
		desc_rect = desc_surface.get_rect(center=(surface.get_width() // 2, 110))
		surface.blit(desc_surface, desc_rect)

		for btn in self.buttons:
			pygame.draw.rect(surface, btn["color"], btn["rect"])
			pygame.draw.rect(surface, black, btn["rect"], 3)
			text_surface = btn["font"].render(btn["text"], True, black)
			text_rect = text_surface.get_rect(center=btn["rect"].center)
			surface.blit(text_surface, text_rect)

		bottom_surface = self.status_font.render(self.bottom_message, True, black)
		bottom_rect = bottom_surface.get_rect(center=(surface.get_width() // 2, surface.get_height() - 30))
		surface.blit(bottom_surface, bottom_rect)

		if self.is_collecting:
			num_lines = 12
			for i in range(num_lines):
				angle_deg = (360 / num_lines) * i + self.spinner_angle
				angle_rad = math.radians(angle_deg)
				x = self.spinner_center[0] + self.spinner_radius * math.cos(angle_rad)
				y = self.spinner_center[1] + self.spinner_radius * math.sin(angle_rad)
				pygame.draw.circle(surface, black, (int(x), int(y)), 3)

# --- Single Collection ---
class CollectDataSingleScene(Scene):
	def __init__(self, app):
		super().__init__(app)
		self.app = app
		self.font_en = pygame.font.Font(notoFont, 20)
		self.font_jp = pygame.font.Font(notoFont, 20)
		self.message_en = "Collecting training data, in case of problem, please press Cancel..."
		self.message_jp = "データ収集中。問題があればキャンセルを押してください..."
		self.buttons = []
		self.sequence_thread = None
		self.sequence_stop_event = None

		# Spinner setup
		self.spinner_angle = 0
		self.spinner_radius = 20
		self.spinner_center = (480 - 50, 320 - 50)  # bottom right
		self.spinner_speed = -2  # degrees per frame

		# --- Cancel Button ---
		self.add_button("Cancel", 165, 220, 150, 70, self.cancel_action, font_size=26, color=light_red)

	def add_button(self, text, x, y, w, h, callback, font_size=28, color=white):
		button = {
			"rect": pygame.Rect(x, y, w, h),
			"text": text,
			"callback": callback,
			"font": pygame.font.Font(notoFont, font_size),
			"color": color
		}
		self.buttons.append(button)

	def cancel_action(self):
		print("Cancel pressed — returning to Trainer Scene")
		
		self.sequence_stop_event.set()
  
		'''board = getattr(self.app, "bciboard", None)
		if board and getattr(board, "recording", False):
			try:
				board.stop_recording()
			except Exception:
				pass'''

	def emergency_cancel(self):
		if self.sequence_stop_event:
			self.sequence_stop_event.set()
		self.sequence_thread = None
		self.app.switch_scene("trainer")

	def handle_events(self, event):
		if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
			mx, my = event.pos
			for btn in self.buttons:
				if btn["rect"].collidepoint(mx, my):
					btn["callback"]()

	def update(self):
		# Rotate spinner continuously
		self.spinner_angle = (self.spinner_angle + self.spinner_speed) % 360

		#Get Board
		board = getattr(self.app, "bciboard", None)

		#Critical problem
		if board is None:
			print("No BCIBoard instance available")
			self.emergency_cancel()
			return
		if not getattr(board, "connected", False):
			print("Board Not Connected")
			self.emergency_cancel()
			return

		#Make it stream
		if not getattr(board, "streaming", False):
			board.stream()

		if not self.sequence_thread:
			timestamp = datetime.datetime.now()
			lcr_choice = ABMI_Utils.chooseNewLCRValue(self.app.recording_lcr_counts)
			self.sequence_thread, self.sequence_stop_event = ABMI_Utils.startSingleTrainingSequence(board, self.app.user_id, timestamp, lcr_choice, self.app.session_Folder)

		if self.sequence_thread:
			if not self.sequence_thread.is_alive():
				self.sequence_thread = None
				self.app.switch_scene("trainer")

	def draw(self, surface):
		surface.fill(white)

		# --- Messages (wrapped) ---
		max_width = surface.get_width() - 120
		start_y = 40

		y_after_en = draw_text_wrapped(surface, self.message_en, self.font_en, black, 50, start_y, max_width, 8, 'en')
		y_after_jp = draw_text_wrapped(surface, self.message_jp, self.font_jp, black, 50, start_y + y_after_en + 5, max_width, 8, 'jp')

		# --- Buttons ---
		for btn in self.buttons:
			pygame.draw.rect(surface, btn['color'], btn['rect'])
			pygame.draw.rect(surface, black, btn['rect'], 3)
			text_surface = btn['font'].render(btn['text'], True, black)
			text_rect = text_surface.get_rect(center=btn['rect'].center)
			surface.blit(text_surface, text_rect)

		# Draw spinner
		num_lines = 12
		for i in range(num_lines):
			angle_deg = (360 / num_lines) * i + self.spinner_angle
			angle_rad = math.radians(angle_deg)
			x = self.spinner_center[0] + self.spinner_radius * math.cos(angle_rad)
			y = self.spinner_center[1] + self.spinner_radius * math.sin(angle_rad)
			pygame.draw.circle(surface, black, (int(x), int(y)), 3)

# --- Emergency Board Disconnected ---
class EmergencyDisconnectedScene(Scene):
	def __init__(self, app):
		super().__init__(app)
		self.app = app
		self.font_en = pygame.font.Font(notoFont, 22)
		self.font_jp = pygame.font.Font(notoFont, 22)
		self.buttons = []
		self.add_button("Reconnect", 150, 220, 180, 70, self.reconnect_action, font_size=26, color=light_green)

	def add_button(self, text, x, y, w, h, callback, font_size=28, color=white):
		button = {
			"rect": pygame.Rect(x, y, w, h),
			"text": text,
			"callback": callback,
			"font": pygame.font.Font(notoFont, font_size),
			"color": color
		}
		self.buttons.append(button)

	def reconnect_action(self):
		print("Reconnect pressed")
		self.app.bciboard.connect()

	def handle_events(self, event):
		if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
			mx, my = event.pos
			for btn in self.buttons:
				if btn["rect"].collidepoint(mx, my):
					btn["callback"]()

	def update(self):
		if self.app.bciboard.connected:	
			self.app.switch_scene("trainer")
		pass

	def draw(self, surface):
		surface.fill(white)

		en_text = "Emergency: BCIBoard connection is lost!"
		jp_text = "緊急: BCIボードの接続が失われました!"

		en_surface = self.font_en.render(en_text, True, red)
		en_rect = en_surface.get_rect(center=(surface.get_width() // 2, 100))
		surface.blit(en_surface, en_rect)

		jp_surface = self.font_jp.render(jp_text, True, red)
		jp_rect = jp_surface.get_rect(center=(surface.get_width() // 2, en_rect.bottom + 40))
		surface.blit(jp_surface, jp_rect)

		for btn in self.buttons:
			pygame.draw.rect(surface, btn["color"], btn["rect"])
			pygame.draw.rect(surface, black, btn["rect"], 3)
			text_surface = btn["font"].render(btn["text"], True, black)
			text_rect = text_surface.get_rect(center=btn["rect"].center)
			surface.blit(text_surface, text_rect)

# --- Main App Class ---
class BMITrainer:
	def __init__(self):
		# Initialize Pygame
		pygame.init()

		# Force window position (top-left corner)
		os.environ['SDL_VIDEO_WINDOW_POS'] = "0,0"

		# Open fixed 480x320 window
		self.render_w, self.render_h = 480, 320
		self.screen = pygame.display.set_mode((self.render_w, self.render_h), pygame.NOFRAME)
		pygame.display.set_caption("BMI Trainer")

		self.clock = pygame.time.Clock()
		self.running = True

		# Developer mode flags
		self.developer_mode = False
		self.dev_start_scene = "bci_connect"
		self.dev_skip_bci_connect = False

		self.bciboard = None
		self.impedance_results = []
		self.current_cable_result = None
		self.user_id = None
		self.session_Folder = None
		self.model_Folder = None
		self.testing_Folder = None
		self.recording_lcr_counts = None
  
		#TCP credentials
		self.cloud_ip = "131.113.139.72"
		self.cloud_user = "ext_guest"
		self.cloud_password = "GuestMoonshot01"

		# Scenes
		self.scenes = {
			"welcome": WelcomeScene(self),
			"wifi_check": WiFiCheckScene(self),
			"bci_connect": BCIConnectScene(self),
			"impedance_results_single": ImpedanceResultsSingleScene(self),
			"trainer": TrainerScene(self),
			"upload_to_cloud": UploadToCloudScene(self),
			"download_from_cloud": DownloadFromCloudScene(self),
			"model_test": ModelTestScene(self),
			"collect_data_single": CollectDataSingleScene(self),
			"emergency": EmergencyDisconnectedScene(self)
		}
		
		# Add individual cable check scenes from canonical list in ABMI_Utils
		for i, (name_lc, color) in enumerate(zip(ABMI_Utils.CABLE_COLORS, ABMI_Utils.CABLE_COLORS_RGB)):
			name_title = name_lc.title()
			scene_name = f"impedance_check_{name_lc}"
			self.scenes[scene_name] = ImpedanceCheckSingleScene(self, i, name_title, color)
		self.current_scene = self.scenes["welcome"]

		# Set starting scene
		if self.developer_mode and self.dev_start_scene in self.scenes:
			self.current_scene = self.scenes[self.dev_start_scene]
		else:
			self.current_scene = self.scenes["welcome"]

	def switch_scene(self, scene_name):
		if scene_name in self.scenes:
			if scene_name == 'trainer':
				self.refresh_lcr_count()
			self.current_scene = self.scenes[scene_name]
			if hasattr(self.current_scene, 'on_enter'):
				self.current_scene.on_enter()
			if hasattr(self.current_scene, 'refresh_lcr_count'):
				try:
					self.current_scene.refresh_lcr_count()
				except Exception:
					pass
   
	def refresh_lcr_count(self):
		self.recording_lcr_counts = ABMI_Utils.countRecordings(self.user_id, base_folder="BMI Trainer Data/")

	def handle_events(self):
		for event in pygame.event.get():
			if event.type == pygame.QUIT:
				self.quit()
			elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
				self.quit()
			self.current_scene.handle_events(event)

	def main_loop(self):
		while self.running:
			self.handle_events()
			self.current_scene.update()
			self.current_scene.draw(self.screen)
			pygame.display.flip()
			self.clock.tick(60)

	def quit(self):
		pygame.quit()
		sys.exit()
