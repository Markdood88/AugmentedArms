import pygame
import sys
import socket
import time
import math

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
light_yellow = (255,246,120)
green = (0,200,0)
mint_green = (54,217,62)
dark_green = (2,140,0)
dark_yellow = (201,185,0)

def draw_text_wrapped(surface, text, font, color, x, y, max_width, line_spacing=5):
	"""
	Draws multi-line text (handles '\n' or wraps long lines) on the given surface.
	Returns the total height used.
	"""
	lines = []
	for paragraph in text.split("\n"):
		words = paragraph.split(" ")
		current_line = ""
		for word in words:
			test_line = current_line + (" " if current_line else "") + word
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
				self.app.quit()  # or switch to next scene

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
		draw_text_wrapped(surface, msg_jp, self.font_jp, black, x=40, y=180, max_width=400)
  
		# Draw spinner if checking or retrying
		if self.status in ["checking", "fail"]:
			num_lines = 12
			for i in range(num_lines):
				angle_deg = (360 / num_lines) * i + self.spinner_angle
				angle_rad = math.radians(angle_deg)
				x = self.spinner_center[0] + self.spinner_radius * math.cos(angle_rad)
				y = self.spinner_center[1] + self.spinner_radius * math.sin(angle_rad)
				pygame.draw.circle(surface, black, (int(x), int(y)), 3)
  
# --- Main App Class ---
class BMITrainer:
	def __init__(self):
		# Initialize Pygame
		pygame.init()

		# Display
		info = pygame.display.Info()
		self.screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.FULLSCREEN)
		pygame.display.set_caption("BMI Trainer")
		self.render_surface = pygame.Surface((480, 320))
		self.clock = pygame.time.Clock()
		self.running = True

		# Scenes
		self.scenes = {
			"welcome": WelcomeScene(self),
			"wifi_check": WiFiCheckScene(self),
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
			self.current_scene.draw(self.render_surface)
			scaled_surface = pygame.transform.scale(self.render_surface, self.screen.get_size())
			self.screen.blit(scaled_surface, (0, 0))
			pygame.display.flip()
			self.clock.tick(60)

	def quit(self):
		pygame.quit()
		sys.exit()