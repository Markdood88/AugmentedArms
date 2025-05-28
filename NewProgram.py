import pygame
import sys
import random
import math
from dynamixel_sdk import *

# Dynamixel Vars
LEFTARM_NAME = '/dev/ttyUSB0'
RIGHTARM_NAME = '/dev/ttyUSB1'
BAUDRATE = 115200
PROTOCOL_VERSION = 2.0

# Initialize ports and packetHandler
rightArmPort = PortHandler(RIGHTARM_NAME)
leftArmPort = PortHandler(LEFTARM_NAME)
packetHandler = PacketHandler(PROTOCOL_VERSION) # For sending messages

rightArmPort.openPort()
leftArmPort.openPort()
rightArmPort.setBaudRate(BAUDRATE)
leftArmPort.setBaudRate(BAUDRATE)

# Pygame to Render
pygame.init()

# Joystick Setup
joystick = None
joystick_connected = False
if pygame.joystick.get_count() > 0:
	joystick = pygame.joystick.Joystick(0)
	joystick.init()
	joystick_connected = True
AXIS_THRESHOLD = 0.8  # adjust if needed

info = pygame.display.Info()
screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.FULLSCREEN)
pygame.display.set_caption("Augmented Arms")
clock = pygame.time.Clock()

# Surface for drawing visuals (480x320)
render_surface = pygame.Surface((480, 320))

# Scene Vars
SCENE_LANGUAGE_SELECT = "language_select"
SCENE_MOTOR_READINGS = "motor_readings"

# Language Vars
language = "en"
selecting_language = True
languages = ["English", "日本語"]
selected_lang_index = 0

current_scene = SCENE_LANGUAGE_SELECT
motor_readings = ["Right Arm", "Left Arm"]
motor_readings_jp = ["右アーム", "左アーム"]
current_motor_reading = 0

# Colors
white = (217,217,217)
blue = (0,0,255)
cool_blue = (74,198,255)
warning_orange = (255,190,120)
soft_red = (250,61,55)
black = (0,0,0)
light_green = (82,255,128)

#Icons
controller_disconnected_icon = pygame.image.load("/home/b2j/Desktop/AugmentedArms/Icons/controllerdisconnected.png").convert_alpha()
controller_disconnected_icon_scaled = pygame.transform.scale(controller_disconnected_icon, (45, 45))
controller_icon_pos = (10, render_surface.get_height() - 55)

# Arm connections
right_arm_connections = [
	[1, 1, 1],
	[1, 1, 1],
	[1, 1, 1]
]

left_arm_connections = [
	[1, 1, 1],
	[1, 1, 1],
	[1, 1, 1]
]

def ping_arm(index):
	global rightArmPort, leftArmPort, packetHandler
	
	if index == 0: #Right Arm
		for i in range(1, 10):
			model_number, result, error = packetHandler.ping(rightArmPort, i)
			if result == COMM_SUCCESS and error == 0:
				right_arm_connections[math.floor((i-1)/3)][(i-1)%3] = 1
			else:
				right_arm_connections[math.floor((i-1)/3)][(i-1)%3] = 0
	if index == 1:  #Left Arm
		for i in range(10, 18):
			model_number, result, error = packetHandler.ping(leftArmPort, i)
			if result == COMM_SUCCESS and error == 0:
				left_arm_connections[math.floor((i-10)/3)][(i-10)%3] = 1
			else:
				left_arm_connections[math.floor((i-10)/3)][(i-10)%3] = 0
	

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

	# Randomize connection data for testing
	'''for i in range(3):
		for j in range(3):
			right_arm_connections[i][j] = 1 if random.uniform(0, 1) > 0.001 else 0'''

	# Live Arm Ping
	ping_arm(index)

	# Margins and positions
	left_margin = 15
	top_margin = 15
	text_spacing = 5
	port = f"COM{index + 1}"

	# Text blocks based on language
	if language == "en":
		status_text = f"{motor_readings[index]} Connection Status: {port}"
		instructions = (
			f"If the value above does not show: {port}\n"
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
		status_text = f"{motor_readings_jp[index]}の接続状態: {port}"
		instructions = (
			f"上記の値が{port}を示さない場合は、\n"
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

	for row in range(matrix_size):
		for col in range(matrix_size):
			cx = grid_x + col * (circle_radius * 2 + gap)
			cy = grid_y + row * (circle_radius * 2 + gap)
			num = row * matrix_size + col + 1 + (current_motor_reading * 9)

			if right_arm_connections[row][col] == 1:
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

	pygame.draw.rect(screen, white, render_surface.get_rect(topleft=(0, 0)), 1)
	pygame.display.flip()

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

		# --- Scene-specific input handling ---
		if current_scene == SCENE_LANGUAGE_SELECT:
			# Keyboard input
			if event.type == pygame.KEYDOWN:
				if event.key == pygame.K_LEFT:
					selected_lang_index = (selected_lang_index - 1) % len(languages)
				elif event.key == pygame.K_RIGHT:
					selected_lang_index = (selected_lang_index + 1) % len(languages)
				elif event.key == pygame.K_RETURN:
					language = "en" if selected_lang_index == 0 else "jp"
					current_scene = SCENE_MOTOR_READINGS

			# Gamepad axis (D-pad)
			elif event.type == pygame.JOYAXISMOTION and event.axis == 0:
				if event.value < -AXIS_THRESHOLD:
					selected_lang_index = (selected_lang_index - 1) % len(languages)
				elif event.value > AXIS_THRESHOLD:
					selected_lang_index = (selected_lang_index + 1) % len(languages)

			# Gamepad button
			elif event.type == pygame.JOYBUTTONDOWN and event.button == 6:  # Z button
				language = "en" if selected_lang_index == 0 else "jp"
				current_scene = SCENE_MOTOR_READINGS

		elif current_scene == SCENE_MOTOR_READINGS:
			# Keyboard input
			if event.type == pygame.KEYDOWN:
				if event.key == pygame.K_LEFT:
					if current_motor_reading == 0:
						current_scene = SCENE_LANGUAGE_SELECT
					else:
						current_motor_reading -= 1
				elif event.key == pygame.K_RIGHT:
					if current_motor_reading < len(motor_readings) - 1:
						current_motor_reading += 1
	  
			# Gamepad button
			elif event.type == pygame.JOYBUTTONDOWN:
				if event.button == 6:  # Z button
					if current_motor_reading == 0:
						current_motor_reading = 1  # Go to second motor reading
				elif event.button == 3:  # X button
					if current_motor_reading == 1:
						current_motor_reading = 0  # Back to first motor reading
					elif current_motor_reading == 0:
						current_scene = SCENE_LANGUAGE_SELECT  # Back to language select

	# --- Scene drawing ---
	if current_scene == SCENE_LANGUAGE_SELECT:
		draw_language_selection()
	elif current_scene == SCENE_MOTOR_READINGS:
		draw_motor_readings(current_motor_reading)

	clock.tick(30)

