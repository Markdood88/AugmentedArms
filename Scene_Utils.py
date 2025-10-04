import os
import pygame
import sys
import socket
import time
import math
import threading
import numpy as np

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
warning_orange = (255,190,120)
soft_red = (250,61,55)
red = (200,0,0)
black = (0,0,0)
light_green = (82,255,128)
light_yellow = (220,200,80)
green = (0,200,0)
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
		text_rect_en = text_surface_en.get_rect(center=(240, 120))
		surface.blit(text_surface_en, text_rect_en)

		# Japanese text (bottom)
		text_surface_jp = self.font_jp.render("BMIトレーナーへようこそ", True, black)
		text_rect_jp = text_surface_jp.get_rect(center=(240, 200))
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
			if self.check_internet():
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
		draw_text_wrapped(surface, msg_en, self.font_en, black, x=40, y=80, max_width=400)
		draw_text_wrapped(surface, msg_jp, self.font_jp, black, x=40, y=180, max_width=400, lang="jp")
  
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
			# Automatically move to ImpedanceCheckScene
			self.app.switch_scene("impedance_check")


	def _try_connect(self):
		try:
			self.board = ABMI_Utils.BCIBoard(port="/dev/ttyUSB0")
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
		draw_text_wrapped(surface, msg_en, self.font_en, black, x=40, y=80, max_width=400)
		draw_text_wrapped(surface, msg_jp, self.font_jp, black, x=40, y=180, max_width=420, lang="jp")
		
		# Draw spinner if checking
		if self.status == "checking":
			num_lines = 12
			for i in range(num_lines):
				angle_deg = (360 / num_lines) * i + self.spinner_angle
				angle_rad = math.radians(angle_deg)
				x = self.spinner_center[0] + self.spinner_radius * math.cos(angle_rad)
				y = self.spinner_center[1] + self.spinner_radius * math.sin(angle_rad)
				pygame.draw.circle(surface, black, (int(x), int(y)), 3)

# --- Impedance Check Scene ---
class ImpedanceCheckScene(Scene):
	def __init__(self, app):
		super().__init__(app)
		self.font_en = pygame.font.Font(notoFont, 24)
		self.font_jp = pygame.font.Font(notoFont, 24)
		self.status = "waiting"  # "waiting", "checking", "done"
		self.results = None
		self.current_channel = 0
		self.cable_colors_rgb = ABMI_Utils.CABLE_COLORS_RGB
		self.spinner_angle = 0
		self.spinner_radius = 15
		self.spinner_center = (40, 280)  # bottom-left spinner
		self.spinner_speed = -5
		self.board = None

	def handle_events(self, event):
		pass  # no interaction during checking

	def start_impedance_check(self):
		self.status = "checking"        # immediately show the wheel
		threading.Thread(target=self._impedance_worker, daemon=True).start()

	def _impedance_worker(self):
		self.status = "checking"
		self.results = []

		if not hasattr(self.app, "bciboard") or self.app.bciboard is None:
			# Should already exist, but fallback
			self.app.bciboard = ABMI_Utils.BCIBoard(port="/dev/ttyUSB0")
			try:
				self.app.bciboard.connect()
			except Exception as e:
				self.results = str(e)
				self.status = "done"
				return

		for ch, color_rgb in enumerate(self.cable_colors_rgb, start=1):
			self.current_channel = ch
			try:
				# check_impedance expects a list of channels
				impedance_result = self.app.bciboard.check_impedance([ch])
				self.results.extend(impedance_result)
			except Exception as e:
				self.results.append((ch, float("nan")))

		self.status = "done"
		self.current_channel = len(self.cable_colors_rgb)  # ensure last color shows
		
		# Store results in main app for access by other scenes
		self.app.impedance_results = self.results

	def update(self):
		if self.status == "waiting":
			self.start_impedance_check()  # will set status to "checking"
		elif self.status == "checking":
			self.spinner_angle = (self.spinner_angle + self.spinner_speed) % 360
		elif self.status == "done":
			# Switch to results scene immediately
			self.app.switch_scene("impedance_results")

	def draw(self, surface):
		surface.fill(white)

		# --- Left side texts ---
		x_text = 40
		y_text = 80
		# Checking cable connection
		draw_text_wrapped(surface, "Checking cable connection...", self.font_en, black, x=x_text, y=y_text, max_width=200)
		draw_text_wrapped(surface, "ケーブル接続を確認中...", self.font_jp, black, x=x_text, y=y_text+90, max_width=300, lang="jp")

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
		color_idx = max(0, self.current_channel - 1)
		if self.status == "waiting":
			cable_color_rgb = (0, 0, 0)  # Black for waiting
		else:
			cable_color_rgb = self.cable_colors_rgb[color_idx] if color_idx < len(self.cable_colors_rgb) else (128, 128, 128)
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

# --- Impedance Results Scene ---
class ImpedanceResultsScene(Scene):
	def __init__(self, app):
		super().__init__(app)
		self.font_en = pygame.font.Font(notoFont, 16)
		self.font_jp = pygame.font.Font(notoFont, 14)
		self.font_large = pygame.font.Font(notoFont, 20)
		
		# Color names mapping
		self.color_names = ["Gray", "Purple", "Blue", "Green", "Yellow", "Orange", "Red", "Brown"]
		
		# Results will be set when switching to this scene
		self.results = []

	def handle_events(self, event):
		if event.type == pygame.KEYDOWN or event.type == pygame.MOUSEBUTTONDOWN:
			# Go back to main menu or next scene
			pass  # Add navigation logic as needed

	def update(self):
		pass

	def draw(self, surface):
		surface.fill(white)
		
		# Get results from main app
		results = self.app.impedance_results
		
		# Title
		title_en = "Results"
		title_jp = "結果"
		title_surface_en = self.font_large.render(title_en, True, black)
		title_surface_jp = self.font_large.render(title_jp, True, black)
		
		title_rect_en = title_surface_en.get_rect(center=(220, 35))
		surface.blit(title_surface_en, title_rect_en)
		
		# Japanese title to the right of English
		title_rect_jp = title_surface_jp.get_rect(center=(300, 35))
		surface.blit(title_surface_jp, title_rect_jp)
		
		# Column headers
		header_y = 55
		col1_x = 50   # Cable color name
		col2_x = 180  # Impedance value
		col3_x = 320  # Pass/Fail
		
		# Headers
		header_font = pygame.font.Font(notoFont, 14)
		header1 = header_font.render("Cable", True, black)
		header2 = header_font.render("Impedance (kΩ)", True, black)
		header3 = header_font.render("Status", True, black)
		
		surface.blit(header1, (col1_x, header_y))
		surface.blit(header2, (col2_x, header_y))
		surface.blit(header3, (col3_x, header_y))
		
		# Draw results for each channel
		row_height = 22
		start_y = header_y + 20
		
		for i, (channel, impedance) in enumerate(results):
			row_y = start_y + (i * row_height)
			
			# Skip if we don't have results for this channel
			if i >= len(self.color_names):
				break
			
			# Column 1: Cable color name
			color_name = self.color_names[i]
			color_surface = self.font_en.render(color_name, True, black)
			surface.blit(color_surface, (col1_x, row_y))
			
			# Column 2: Impedance value with color coding
			if not np.isnan(impedance):
				impedance_text = f"{impedance:.1f}"
				
				# Color coding based on impedance value
				if impedance < 50:
					value_color = green
				elif impedance < 100:
					value_color = warning_orange
				else:
					value_color = red
					
				impedance_surface = self.font_en.render(impedance_text, True, value_color)
				surface.blit(impedance_surface, (col2_x, row_y))
			else:
				# Handle NaN values
				impedance_surface = self.font_en.render("N/A", True, black)
				surface.blit(impedance_surface, (col2_x, row_y))
			
			# Column 3: Pass/Fail status
			if not np.isnan(impedance):
				if impedance < 100:
					status_en = "PASS"
					status_jp = "合格"
					status_color = green
				else:
					status_en = "FAIL"
					status_jp = "不合格"
					status_color = red
			else:
				status_en = "N/A"
				status_jp = "N/A"
				status_color = black
			
			# Draw English status
			status_surface_en = self.font_en.render(status_en, True, status_color)
			surface.blit(status_surface_en, (col3_x, row_y))
			
			# Draw Japanese status to the right
			status_surface_jp = self.font_jp.render(status_jp, True, status_color)
			surface.blit(status_surface_jp, (col3_x + 60, row_y))
		
		# Check if any status is FAIL and show warning at bottom
		has_fail = False
		for channel, impedance in results:
			if not np.isnan(impedance) and impedance >= 100:
				has_fail = True
				break
		
		if has_fail:
			# Warning message at bottom
			warning_en = "Cable connection is weak, please fix and restart"
			warning_jp = "ケーブル接続が弱いです、修正して再起動してください"
			warning_surface_en = self.font_en.render(warning_en, True, red)
			warning_surface_jp = self.font_jp.render(warning_jp, True, red)
			
			surface.blit(warning_surface_en, (50, 260))
			surface.blit(warning_surface_jp, (50, 280))

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

		# global BCIBoard object
		self.bciboard = None
		# Impedance check results
		self.impedance_results = []

		# Scenes
		self.scenes = {
			"welcome": WelcomeScene(self),
			"wifi_check": WiFiCheckScene(self),
			"bci_connect": BCIConnectScene(self),
			"impedance_check": ImpedanceCheckScene(self),
			"impedance_results": ImpedanceResultsScene(self),
		}
		self.current_scene = self.scenes["welcome"]

	def switch_scene(self, scene_name):
		self.current_scene = self.scenes[scene_name]

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
