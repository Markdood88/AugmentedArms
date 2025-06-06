import pygame
import sys
import random
import math
import threading
import Arm_Utils
from dynamixel_sdk import *

def match_lists(expected, actual):
	return [1 if val in actual else 0 for val in expected]

def detect_arm_ports():

	global expected_ports

	right_arm = expected_ports[0]
	left_arm = expected_ports[1]


	for port in expected_ports:
		handler = PortHandler(port)
		if handler.openPort():
			handler.setBaudRate(BAUDRATE)
			packetHandler = PacketHandler(PROTOCOL_VERSION)
			# Check if motor ID 1 (right) or ID 11 (left) responds
			model, result, error = packetHandler.ping(handler, 1)
			if result == COMM_SUCCESS:
				right_arm = port
			else:
				model, result, error = packetHandler.ping(handler, 11)
				if result == COMM_SUCCESS:
					left_arm = port
			handler.closePort()

	return right_arm, left_arm

def ping_arm(index):

	def worker():
		global RightArm, LeftArm, right_arm_motors_alive, left_arm_motors_alive
		
		if index == 0: #Right Arm 1-9
			successful_ids = RightArm.ping_motors()
			right_arm_motors_alive = match_lists(right_arm_expected_motors, successful_ids)
		if index == 1:  #Left Arm 11-18
			successful_ids = LeftArm.ping_motors()
			left_arm_motors_alive = match_lists(left_arm_expected_motors, successful_ids)

	threading.Thread(target=worker, daemon=True).start()

def draw_language_selection():
	render_surface.fill(black)

	font = pygame.font.Font("/home/b2j/Desktop/AugmentedArms/Font/NotoSansJP-Bold.otf", 23)
	bigfont = pygame.font.Font("/home/b2j/Desktop/AugmentedArms/Font/NotoSansJP-Bold.otf", 40)
	smallfont = pygame.font.Font("/home/b2j/Desktop/AugmentedArms/Font/NotoSansJP-Bold.otf", 16)

	# Warning if controller not connected
	if pygame.joystick.get_count() == 0:
		warning_text = "WARNING: CONTROLLER NOT DETECTED"
		warning_surface = smallfont.render(warning_text, True, soft_red)
		warning_rect = warning_surface.get_rect(center=(render_surface.get_width() // 2, 35))
		render_surface.blit(warning_surface, warning_rect)

	# Prompt
	prompt = "Select Language / 言語を選択してください"
	prompt_surface = font.render(prompt, True, white)
	prompt_rect = prompt_surface.get_rect(center=(render_surface.get_width() // 2, render_surface.get_height() // 3 - 30))
	render_surface.blit(prompt_surface, prompt_rect)

	# Languages
	for i, lang in enumerate(languages):
		color = cool_blue if i == selected_lang_index else white
		lang_surface = bigfont.render(lang, True, color)
		offset_x = -100 if i == 0 else 100
		lang_rect = lang_surface.get_rect(center=(render_surface.get_width() // 2 + offset_x, render_surface.get_height() // 2))
		render_surface.blit(lang_surface, lang_rect)

	# Confirm text
	confirm_text = "Press Z to confirm / 決定するにはZを押してください"
	confirm_surface = smallfont.render(confirm_text, True, white)
	confirm_rect = confirm_surface.get_rect(center=(render_surface.get_width() // 2, render_surface.get_height() - 80))
	render_surface.blit(confirm_surface, confirm_rect)

	# Draw to screen
	screen.blit(render_surface, (0, 0))
	pygame.draw.rect(screen, cool_blue, render_surface.get_rect(topleft=(0, 0)), 1)
	pygame.display.flip()

def draw_motor_readings(index):
	render_surface.fill(black)
	
	# Fonts
	font_path = "/home/b2j/Desktop/AugmentedArms/Font/NotoSansJP-Bold.otf"
	title_font = pygame.font.Font(font_path, 20)
	status_font = pygame.font.Font(font_path, 16)
	instruction_font = pygame.font.Font(font_path, 13)
	notice_font = pygame.font.Font(font_path, 18)
	controls_font = pygame.font.Font(font_path, 30)

	# Ping for motor alive values
	ping_arm(index)

	# Margins and positions
	left_margin = 15
	top_margin = 15
	text_spacing = 5
	port = ''
	if index == 0:
		port = RIGHTARM_PORT_NAME
	elif index == 1:	
		port = LEFTARM_PORT_NAME

	# Text blocks based on language
	if language == "en":
		status_text = f"{motor_readings[index]} Port: {port}"
		instructions = (
			f"If the value above is not: {expected_ports[index]}\n"
			"Please power off, and unplug the arms.\n"
			"Re-plug the arms correctly, and restart."
		)
		notice = (
			"You should see 9 white circles\n"
			"on the right side of the screen.\n"
			"If you see solid Red X, please\n"
			"let the support team know."
		)
		controls = "Z: NEXT\nX: BACK"
	else:
		status_text = f"{motor_readings_jp[index]}のポート: {port}"
		instructions = (
			f"上記の値が{expected_ports[index]}を示さない場合は、\n"
			"電源をオフにし、アームを抜いて、\n"
			"正しいポートに接続し、再起動してください。"
		)
		notice = (
			"画面右側に白い円が\n"
			"9個表示されているはずです。\n"
			"赤いXが表示されている場合は、\n"
			"サポートチームにご連絡ください。"
		)
		controls = "Z: 次へ\nX: 戻る"

	# Draw status line
	status_surf = status_font.render(status_text, True, white)
	render_surface.blit(status_surf, (left_margin, top_margin))

	# Draw instruction text
	lines = instructions.split("\n")
	for i, line in enumerate(lines):
		line_surf = instruction_font.render(line, True, warning_orange)
		y = top_margin + 35 + i * (instruction_font.get_height() + text_spacing)
		render_surface.blit(line_surf, (left_margin, y))

	# Draw notice text
	notice_lines = notice.split("\n")
	notice_start_y = top_margin + 35 + len(lines) * (instruction_font.get_height() + text_spacing) + 10
	for i, line in enumerate(notice_lines):
		line_surf = notice_font.render(line, True, white)
		y = notice_start_y + i * (notice_font.get_height() + text_spacing)
		render_surface.blit(line_surf, (left_margin + 5, y))

	# Draw controls (bottom right)
	controls_lines = controls.split("\n")
	controls_x = 325
	controls_y = top_margin + 10
	for i, line in enumerate(controls_lines):
		line_surf = controls_font.render(line, True, white)
		y = controls_y + i * (controls_font.get_height() + text_spacing)
		render_surface.blit(line_surf, (controls_x, y))

	# Draw 3x3 grid of connection circles (right side)
	circle_radius = 20
	gap = 10
	matrix_size = 3
	grid_x = render_surface.get_width() - (circle_radius * 2 * matrix_size + gap * (matrix_size - 1) + 10)
	grid_y = 160

	if index == 0:
		motor_status = right_arm_motors_alive
	elif index == 1:
		motor_status = left_arm_motors_alive

	for row in range(matrix_size):
		for col in range(matrix_size):
			idx = row * matrix_size + col
			if idx >= len(motor_status):
				continue  # skip if index is out of bounds

			cx = grid_x + col * (circle_radius * 2 + gap)
			cy = grid_y + row * (circle_radius * 2 + gap)
			num = idx + 1 + (current_motor_reading * 10)

			if motor_status[idx] == 1:
				pygame.draw.circle(render_surface, white, (cx, cy), circle_radius, 1)
				num_surf = title_font.render(str(num), True, white)
				num_rect = num_surf.get_rect(center=(cx, cy))
				render_surface.blit(num_surf, num_rect)
			else:
				pygame.draw.line(render_surface, soft_red, (cx - circle_radius, cy - circle_radius), (cx + circle_radius, cy + circle_radius), 5)
				pygame.draw.line(render_surface, soft_red, (cx + circle_radius, cy - circle_radius), (cx - circle_radius, cy + circle_radius), 5)

	# Final blits and outlines
	screen.blit(render_surface, (0, 0))
	if not joystick_connected:
		screen.blit(controller_disconnected_icon_scaled, controller_icon_pos)

	pygame.draw.rect(screen, cool_blue, render_surface.get_rect(topleft=(0, 0)), 1)
	pygame.display.flip()

def draw_lock_release():
	render_surface.fill(black)

	# Fonts
	font_path = "/home/b2j/Desktop/AugmentedArms/Font/NotoSansJP-Bold.otf"
	message_font = pygame.font.Font(font_path, 30)
	controls_font = pygame.font.Font(font_path, 30)
	button_font = pygame.font.Font(font_path, 40)
	warning_font = pygame.font.Font(font_path, 18)

	# Text by language
	if language == "en":
		message = "Please test both\nLock and Release"
		controls = "Z: NEXT\nX: BACK"
		lock_text = "LOCK"
		release_text = "RELEASE"
		warning_text = "In case of failure, please contact support"
	
	else:
		message = "ロックと解除を\nテストしてください"
		controls = "Z: 次へ\nX: 戻る"
		lock_text = "ロック"
		release_text = "解除"
		warning_text = "不具合時はサポートへ連絡ください"
	

	# Render top-left message (multi-line)
	message_lines = message.split("\n")
	for i, line in enumerate(message_lines):
		line_surf = message_font.render(line, True, white)
		render_surface.blit(line_surf, (30, 25 + i * (message_font.get_height() + 5)))

	# Render controls (top right)
	controls_lines = controls.split("\n")
	controls_x = 325
	controls_y = 25
	for i, line in enumerate(controls_lines):
		line_surf = controls_font.render(line, True, white)
		y = controls_y + i * (controls_font.get_height() + 5)
		render_surface.blit(line_surf, (controls_x, y))

	# Safe button check
	l_held = False
	r_held = False
	if joystick_connected and joystick:
		try:
			l_held = joystick.get_button(8) == 1
			r_held = joystick.get_button(9) == 1
		except pygame.error:
			l_held = False
			r_held = False
   
   	# Keyboard input
	keys = pygame.key.get_pressed()
	if keys[pygame.K_l]:
		l_held = True
	if keys[pygame.K_r]:
		r_held = True

	# Colors depending on button state
	lock_pill_color = green if l_held else red  # green if held else red
	release_pill_color = green if r_held else red

	lock_text_color = light_green if l_held else white
	release_text_color = light_green if r_held else white

	# Render LOCK and RELEASE text centered horizontally, below message and controls
	mid_y = 125
	lock_surf = button_font.render(lock_text, True, lock_text_color)
	release_surf = button_font.render(release_text, True, release_text_color)

	# Calculate positions
	screen_width = render_surface.get_width()
	spacing = 100
	center_x = screen_width // 2
	shift_amount = 20 if language == "en" else 0
	lock_x = (center_x - spacing) - shift_amount
	release_x = (center_x + spacing) - shift_amount

	render_surface.blit(lock_surf, (lock_x - lock_surf.get_width()//2, mid_y))
	render_surface.blit(release_surf, (release_x - release_surf.get_width()//2, mid_y))

	# Draw red pill-shaped capsules under the LOCK and RELEASE text
	capsule_width, capsule_height = 100, 50
	text_color = white

	def draw_pill(surface, x, y, w, h, color, text):
		radius = h // 2
		# pill shape: 2 circles connected by a rect
		pygame.draw.circle(surface, color, (x + radius, y + radius), radius)
		pygame.draw.circle(surface, color, (x + w - radius, y + radius), radius)
		pygame.draw.rect(surface, color, (x + radius, y, w - 2*radius, h))
		# draw text centered in pill
		text_surf = button_font.render(text, True, text_color)
		text_rect = text_surf.get_rect(center=(x + w//2, -2 + y + h//2))
		surface.blit(text_surf, text_rect)

	pill_y = mid_y + lock_surf.get_height() + 15
	draw_pill(render_surface, lock_x - capsule_width//2, pill_y, capsule_width, capsule_height, lock_pill_color, "L")
	draw_pill(render_surface, release_x - capsule_width//2, pill_y, capsule_width, capsule_height, release_pill_color, "R")

	# Final warning message at the bottom
	warning_surf = warning_font.render(warning_text, True, white)
	warning_rect = warning_surf.get_rect(center=(render_surface.get_width() // 2, render_surface.get_height() - 35))
	render_surface.blit(warning_surf, warning_rect)

	# Final blits and outline
	screen.blit(render_surface, (0, 0))
	if not joystick_connected:
		screen.blit(controller_disconnected_icon_scaled, controller_icon_pos)

	pygame.draw.rect(screen, cool_blue, render_surface.get_rect(topleft=(0, 0)), 1)
	pygame.display.flip()

def draw_recording_stage():
	global recording_states
	render_surface.fill(black)

	# Fonts
	font_path = "/home/b2j/Desktop/AugmentedArms/Font/NotoSansJP-Bold.otf"
	title_font = pygame.font.Font(font_path, 30)
	label_font = pygame.font.Font(font_path, 22)
	status_font = pygame.font.Font(font_path, 25)
	letter_font = pygame.font.Font(font_path, 36)
 
   	# Keyboard input
	keys = pygame.key.get_pressed()
	if keys[pygame.K_1]:
		recording_states[0] = not recording_states[0]
		pygame.time.wait(200)
	if keys[pygame.K_2]:
		recording_states[1] = not recording_states[1]
		pygame.time.wait(200)
	if keys[pygame.K_3]:
		recording_states[2] = not recording_states[2]
		pygame.time.wait(200)

	# Text by language
	if language == "en":
		title_text = "Record Today's Animations"
		press_texts = ["Press X to", "Press Y to", "Press Z to"]
		status_texts = ["STOP" if toggle else "START" for toggle in recording_states]
		playback_labels = ["Playback 1", "Playback 2", "Playback 3"]
	else:
		title_text = "今日のアニメーションを記録"
		press_texts = ["X を押すと", "Y を押すと", "Z を押すと"]
		status_texts = ["停止" if toggle else "開始" for toggle in recording_states]
		playback_labels = ["再生 1", "再生 2", "再生 3"]

	# Top Title
	title_surf = title_font.render(title_text, True, white)
	title_rect = title_surf.get_rect(center=(render_surface.get_width() // 2, 40))
	render_surface.blit(title_surf, title_rect)

	# Setup for columns
	center_x = render_surface.get_width() // 2
	section_spacing = 140
	base_y = 90

	for i in range(3):
		section_x = center_x + (i - 1) * section_spacing

		# "Press X/Y/Z to"
		press_surf = label_font.render(press_texts[i], True, white)
		press_rect = press_surf.get_rect(center=(section_x, base_y))
		render_surface.blit(press_surf, press_rect)

		# "START"/"STOP"
		status_surf = status_font.render(status_texts[i], True, red if status_texts[i] in ["START", "開始"] else green)
		status_rect = status_surf.get_rect(center=(section_x, base_y + 40))
		render_surface.blit(status_surf, status_rect)

		# "Playback 1/2/3"
		playback_surf = label_font.render(playback_labels[i], True, white)
		playback_rect = playback_surf.get_rect(center=(section_x, base_y + 90))
		render_surface.blit(playback_surf, playback_rect)

		# Circle with letter A/B/C and color Green/Blue/Yellow
		circle_y = base_y + 150
		colors = [mint_green, yellow, dark_blue]
		letters = ["A", "B", "C"]
		pygame.draw.circle(render_surface, colors[i], (section_x, circle_y), 25)
		letter_surf = letter_font.render(letters[i], True, black)
		letter_rect = letter_surf.get_rect(center=(section_x, circle_y-2))
		render_surface.blit(letter_surf, letter_rect)

	# Final display
	screen.blit(render_surface, (0, 0))
	if not joystick_connected:
		screen.blit(controller_disconnected_icon_scaled, controller_icon_pos)
  
	pygame.draw.rect(screen, cool_blue, render_surface.get_rect(topleft=(0, 0)), 1)
	pygame.display.flip()

#----VARIABLES

# Developer Mode
DEVELOPER_MODE = True

# Scene Vars
SCENE_LANGUAGE_SELECT = "language_select"
SCENE_MOTOR_READINGS = "motor_readings"
SCENE_LOCK_RELEASE = "lock_release"
SCENE_RECORDING_STAGE = "recording_stage"
current_scene = SCENE_LOCK_RELEASE

# Language Vars
language = "en"
languages = ["English", "日本語"]
selected_lang_index = 0
motor_readings = ["Right Arm", "Left Arm"]
motor_readings_jp = ["右アーム", "左アーム"]
expected_ports = ["/dev/ttyUSB1", "/dev/ttyUSB0"] #Right First, Left Second
current_motor_reading = 0

# Dynamixel Vars
RIGHTARM_PORT_NAME = ''
LEFTARM_PORT_NAME = ''
BAUDRATE = 115200
PROTOCOL_VERSION = 2.0

# Arm connections && Motor Status
RightArm = None
LeftArm = None
right_arm_expected_motors = [1,2,3,4,5,6,7,8,9] #9 Motors
left_arm_expected_motors = [11,12,13,14,15,16,17,18] #8 Motors
right_arm_motors_alive = [0,0,0,0,0,0,0,0,0] #9 Values
left_arm_motors_alive = [0,0,0,0,0,0,0,0] #8 Values

# Joystick Setup
joystick = None
joystick_connected = False
AXIS_THRESHOLD = 0.8  #DPad minimum change

# Colors
white = (217,217,217)
blue = (23,100,255)
dark_blue = (2,43,245)
cool_blue = (74,198,255)
warning_orange = (255,190,120)
soft_red = (250,61,55)
red = (200,0,0)
black = (0,0,0)
light_green = (82,255,128)
green = (0,200,0)
mint_green = (62,173,112)
yellow = (252,243,71)

#Recording States
recording_states = [False, False, False]

#----Start of Code

# Initialize Arms and packetHandlers
if not DEVELOPER_MODE:
	RIGHTARM_PORT_NAME, LEFTARM_PORT_NAME = detect_arm_ports()
	RightArm = Arm_Utils.RoboticArm(RIGHTARM_PORT_NAME, [1,2,3,4,5,6,7,8,9]) #9 Motors
	LeftArm = Arm_Utils.RoboticArm(LEFTARM_PORT_NAME, [11,12,13,14,15,16,17,18]) #8 Motors
	RightArm.open_port()
	LeftArm.open_port()

# Initialize Pygame
pygame.init()

#Create Display
info = pygame.display.Info()
screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.FULLSCREEN)
pygame.display.set_caption("Augmented Arms")
clock = pygame.time.Clock()
render_surface = pygame.Surface((480, 320))

#Init Joysticks
if pygame.joystick.get_count() > 0:
	joystick = pygame.joystick.Joystick(0)
	joystick.init()
	joystick_connected = True

#Icons
controller_disconnected_icon = pygame.image.load("/home/b2j/Desktop/AugmentedArms/Icons/controllerdisconnected.png").convert_alpha()
controller_disconnected_icon_scaled = pygame.transform.scale(controller_disconnected_icon, (45, 45))
controller_icon_pos = (10, render_surface.get_height() - 55)

# ---- MAIN LOOP ----
while True:
	for event in pygame.event.get():
		# Always allow quitting
		if event.type == pygame.QUIT:
			pygame.quit()
			sys.exit()
		elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
			pygame.quit()
			sys.exit()
		elif event.type == pygame.JOYDEVICEADDED:
			joystick = pygame.joystick.Joystick(event.device_index)
			joystick.init()
			joystick_connected = True
		elif event.type == pygame.JOYDEVICEREMOVED:
			joystick_connected = False
			joystick = None

		# Developer Language Toggle
		if DEVELOPER_MODE and event.type == pygame.KEYDOWN and event.key == pygame.K_j:
			if language == "en":
				language = "jp"
			else:
				language = "en"

		# --- Scene-specific input handling ---
		if current_scene == SCENE_LANGUAGE_SELECT:
			if event.type == pygame.KEYDOWN:
				if event.key == pygame.K_LEFT:
					selected_lang_index = (selected_lang_index - 1) % len(languages)
				elif event.key == pygame.K_RIGHT:
					selected_lang_index = (selected_lang_index + 1) % len(languages)
				elif event.key == pygame.K_RETURN:
					language = "en" if selected_lang_index == 0 else "jp"
					current_scene = SCENE_MOTOR_READINGS

			elif event.type == pygame.JOYAXISMOTION and event.axis == 0:
				if event.value < -AXIS_THRESHOLD:
					selected_lang_index = (selected_lang_index - 1) % len(languages)
				elif event.value > AXIS_THRESHOLD:
					selected_lang_index = (selected_lang_index + 1) % len(languages)

			elif event.type == pygame.JOYBUTTONDOWN and event.button == 6:  # Z button
				language = "en" if selected_lang_index == 0 else "jp"
				current_scene = SCENE_MOTOR_READINGS

		elif current_scene == SCENE_MOTOR_READINGS:
			if event.type == pygame.KEYDOWN:
				if event.key == pygame.K_LEFT:
					if current_motor_reading == 0:
						current_scene = SCENE_LANGUAGE_SELECT
					else:
						current_motor_reading -= 1
				elif event.key == pygame.K_RIGHT:
					if current_motor_reading == 0:
						current_motor_reading = 1  # Move to left arm
					elif current_motor_reading == 1:
						current_scene = SCENE_LOCK_RELEASE  # Go to lock release

			elif event.type == pygame.JOYBUTTONDOWN:
				if event.button == 6:  # Z button
					if current_motor_reading == 0:
						current_motor_reading = 1
					elif current_motor_reading == 1:
						current_scene = SCENE_LOCK_RELEASE
				elif event.button == 3:  # X button
					if current_motor_reading == 1:
						current_motor_reading = 0
					elif current_motor_reading == 0:
						current_scene = SCENE_LANGUAGE_SELECT

		elif current_scene == SCENE_LOCK_RELEASE:
			if event.type == pygame.KEYDOWN:
				if event.key == pygame.K_LEFT:
					current_scene = SCENE_MOTOR_READINGS
					current_motor_reading = 1
				elif event.key == pygame.K_RIGHT:
					current_scene = SCENE_RECORDING_STAGE

			elif event.type == pygame.JOYBUTTONDOWN:
				if event.button == 3:  # X button
					current_scene = SCENE_MOTOR_READINGS
					current_motor_reading = 1
				elif event.button == 6:  # Z button
					current_scene = SCENE_RECORDING_STAGE

		elif current_scene == SCENE_RECORDING_STAGE:
			if event.type == pygame.KEYDOWN:
				if event.key == pygame.K_LEFT:
					current_scene = SCENE_LOCK_RELEASE
			elif event.type == pygame.JOYBUTTONDOWN:
				if event.button == 3:  # X button
					current_scene = SCENE_LOCK_RELEASE

	# --- Scene drawing ---
	if current_scene == SCENE_LANGUAGE_SELECT:
		draw_language_selection()
	elif current_scene == SCENE_MOTOR_READINGS:
		draw_motor_readings(current_motor_reading)
	elif current_scene == SCENE_LOCK_RELEASE:
		draw_lock_release()
	elif current_scene == SCENE_RECORDING_STAGE:
		draw_recording_stage()

	clock.tick(30)
