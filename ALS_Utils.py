import time
import RPi.GPIO as GPIO
import pygame

# Setup GPIO only once
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

class PiezoSensor:
	def __init__(self, pin, cooldown=0.2):
		self.pin = pin
		GPIO.setup(self.pin, GPIO.IN)
		self.prev_state = GPIO.LOW
		self.last_press_time = 0
		self.cooldown = cooldown  # in seconds

	def is_pressed(self):
		"""Returns True if currently pressed"""
		return GPIO.input(self.pin) == GPIO.HIGH

	def was_pressed(self):
		"""Returns True only once when state changes from LOW to HIGH and cooldown passed"""
		current = GPIO.input(self.pin)
		now = time.time()
		pressed = (
			current == GPIO.HIGH and
			self.prev_state == GPIO.LOW and
			(now - self.last_press_time) >= self.cooldown
		)
		self.prev_state = current
		if pressed:
			self.last_press_time = now
		return pressed

class Speaker:
	def __init__(self):
		pygame.mixer.init()
		self.channel = None

	def play(self, filename):
		sound = pygame.mixer.Sound(filename)
		self.channel = sound.play()

	def is_playing(self):
		return self.channel is not None and self.channel.get_busy()

	def stop(self):
		if self.channel:
			self.channel.stop()
