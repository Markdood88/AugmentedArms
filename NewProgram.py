import pygame
import sys
import random

pygame.init()
info = pygame.display.Info()
#screen = pygame.display.set_mode((480, 320), pygame.FULLSCREEN)
screen = pygame.display.set_mode((480,320))
pygame.display.set_caption("Augmented Arms")
clock = pygame.time.Clock()

#Scene Vars
SCENE_LANGUAGE_SELECT = "language_select"
SCENE_MOTOR_READINGS = "motor_readings"

#Language Vars
language = "en"
selecting_language = True
languages = ["English", "日本語"]
selected_lang_index = 0

current_scene = SCENE_LANGUAGE_SELECT
motor_readings = ["Right Arm", "Left Arm"]
motor_readings_jp = ["右アーム", "左アーム"]
current_motor_reading = 0

#Colors
white = (217,217,217)
blue = (0,0,255)
cool_blue = (74,198,255)
warning_orange = (255,190,120)
soft_red = (250,61,55)
black = (0,0,0)

#Right Arm connections
right_arm_connections = [
    [1, 1, 1],
    [1, 1, 1],
    [1, 1, 1]
]

def draw_language_selection():
    screen.fill(black)

    font = pygame.font.Font("/home/b2j/Desktop/AugmentedArms/Font/NotoSansJP-Bold.otf",23)
    bigfont = pygame.font.Font("/home/b2j/Desktop/AugmentedArms/Font/NotoSansJP-Bold.otf",40)

    prompt = "Select Language / 言語を選択してください"
    prompt_surface = font.render(prompt, True, white)
    prompt_rect = prompt_surface.get_rect(center=(screen.get_width() // 2, screen.get_height() // 3))
    screen.blit(prompt_surface, prompt_rect)

    for i, lang in enumerate(languages):
        color = cool_blue if i == selected_lang_index else white
        lang_surface = bigfont.render(lang, True, color)
        offset_x = -100 if i == 0 else 100
        lang_rect = lang_surface.get_rect(center=(screen.get_width() // 2 + offset_x, screen.get_height() // 2 + 30))
        screen.blit(lang_surface, lang_rect)

    pygame.display.flip()

def draw_motor_readings(index):
    screen.fill(black)
    font = pygame.font.Font("/home/b2j/Desktop/AugmentedArms/Font/NotoSansJP-Bold.otf", 20)

    for i in range(0,3):
        for j in range(0,3):
            randNum = random.uniform(0,1)
            if randNum > .001:
                right_arm_connections[i][j] = 1
            else:
                right_arm_connections[i][j] = 0

    # Left side layout
    left_margin = 15
    top_margin = 15

    # Port and arm number based on index
    port = f"COM{index + 1}"

    if language == "en":
        status_text = f"{motor_readings[index]} Connection Status: {port}"
        instructions = (
            f"In case the value above does not indicate: {port}\n"
            "Please turn off the power, then unplug the arms.\n"
            "Re-plug the arms into correct ports, and restart."
        )
        notice = (
            "You should see 9 white circles\n"
            "on the right side of the screen.\n"
            "If you see any Red X, please\n" 
            "let the support team know."
        )
    else:  # Japanese translation
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
    
    # Render Status
    status_font = pygame.font.Font("/home/b2j/Desktop/AugmentedArms/Font/NotoSansJP-Bold.otf", 16)
    status_surf = status_font.render(status_text, True, white)
    screen.blit(status_surf, (left_margin, top_margin))

    # Render instructions line by line
    instruction_font = pygame.font.Font("/home/b2j/Desktop/AugmentedArms/Font/NotoSansJP-Bold.otf", 14)
    lines = instructions.split("\n")
    line_height = instruction_font.get_height()
    for i, line in enumerate(lines):
        line_surf = instruction_font.render(line, True, warning_orange)
        screen.blit(line_surf, (left_margin, top_margin + 40 + i * (line_height + 5)))
    
    #Render Notice line by line
    notice_font = pygame.font.Font("/home/b2j/Desktop/AugmentedArms/Font/NotoSansJP-Bold.otf", 18)
    notice_lines = notice.split("\n")
    notice_start_y = top_margin + 40 + len(lines) * (line_height + 4) + 20
    for i, line in enumerate(notice_lines):
        line_surf = notice_font.render(line, True, white)
        screen.blit(line_surf, (left_margin + 5, notice_start_y + i * (notice_font.get_height() + 5)))

    # ---- Right Side Circle Matrix ----
    # Parameters for circle layout
    circle_radius = 20  # Radius of the circles
    gap = 10  # Space between circles
    matrix_size = 3  # 3x3 matrix of circles
    matrix_start_x = screen.get_width() - (circle_radius * 2 * matrix_size + gap * (matrix_size - 1) + 10)
    matrix_start_y = 170  # Start below the top margin

    # Loop through the 3x3 grid to draw the circles and numbers
    for row in range(matrix_size):
        for col in range(matrix_size):
            # Calculate the position of each circle
            circle_center_x = matrix_start_x + col * (circle_radius * 2 + gap)
            circle_center_y = matrix_start_y + row * (circle_radius * 2 + gap)

            # Number to display (1-9 for Arm 1, 10-18 for Arm 2)
            number = row * matrix_size + col + 1 + (current_motor_reading*9)

             # Draw the circle based on the value in the right_arm_connections matrix
            if right_arm_connections[row][col] == 1:  # White circle
                # Draw hollow circle with thick white outline
                pygame.draw.circle(screen, white, (circle_center_x, circle_center_y), circle_radius, 1)  # thick outline
                # Draw the number in the center of the circle (white text)
                number_text = font.render(str(number), True, white)
                number_rect = number_text.get_rect(center=(circle_center_x, circle_center_y))
                screen.blit(number_text, number_rect)
            else:  # Red X (no circle drawn)
                # Draw a red X over the position (no circle, just X)
                pygame.draw.line(screen, soft_red, (circle_center_x - circle_radius, circle_center_y - circle_radius), 
                                (circle_center_x + circle_radius, circle_center_y + circle_radius), 5)
                pygame.draw.line(screen, soft_red, (circle_center_x + circle_radius, circle_center_y - circle_radius), 
                                (circle_center_x - circle_radius, circle_center_y + circle_radius), 5)

    pygame.display.flip()


####---------------- MAIN LOOP ----------------####

#Select language first
while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                pygame.quit()
                sys.exit()

            if current_scene == SCENE_LANGUAGE_SELECT:
                if event.key == pygame.K_LEFT:
                    selected_lang_index = (selected_lang_index - 1) % len(languages)
                elif event.key == pygame.K_RIGHT:
                    selected_lang_index = (selected_lang_index + 1) % len(languages)
                elif event.key == pygame.K_RETURN:
                    language = "en" if selected_lang_index == 0 else "jp"
                    current_scene = SCENE_MOTOR_READINGS  # Switch to motor readings scene
            
            elif current_scene == SCENE_MOTOR_READINGS:
                if event.key == pygame.K_LEFT:
                    if current_motor_reading == 0:  # If it's the first motor reading, go back to language select
                        current_scene = SCENE_LANGUAGE_SELECT
                    else:
                        current_motor_reading = (current_motor_reading - 1) % len(motor_readings)
                
                elif event.key == pygame.K_RIGHT:
                    current_motor_reading = (current_motor_reading + 1) % len(motor_readings)

    # Draw the appropriate scene based on the current scene
    if current_scene == SCENE_LANGUAGE_SELECT:
        draw_language_selection()
    elif current_scene == SCENE_MOTOR_READINGS:
        draw_motor_readings(current_motor_reading)
    
    clock.tick(30)  # Maintain 30 FPS
