import time
import RPi.GPIO as GPIO
import pygame
import threading

# Setup GPIO only once
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

class PiezoSensor:
	def __init__(self, pin, cooldown=0.2):
		self.pin = pin
		GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
		self.prev_state = GPIO.LOW
		self.last_press_time = 0
		self.cooldown = cooldown  # in seconds

	def is_pressed(self):
		"""Returns True if currently pressed"""
		return GPIO.input(self.pin) == GPIO.LOW

	def was_pressed(self):
		"""Returns True only once when state changes from LOW to HIGH and cooldown passed"""
		current = GPIO.input(self.pin)
		now = time.time()
		pressed = (
			current == GPIO.LOW and
			self.prev_state == GPIO.HIGH and
			(now - self.last_press_time) >= self.cooldown
		)
		self.prev_state = current
		if pressed:
			self.last_press_time = now
		return pressed

class Speaker:
	def __init__(self, volume=1.0):
		self.channel = pygame.mixer.Channel(0)
		self.queue = []
		self.playing = False
		self._lock = threading.Lock()
		self._running = True
		self.volume = volume  # volume float 0.0 to 1.0
		self._thread = threading.Thread(target=self._update_loop, daemon=True)
		self._thread.start()
		self.current_playing_audio = -1
		self.trigger_index = None

	def play_single(self, filename, volume=None):
		with self._lock:
			sound = pygame.mixer.Sound(filename)
			sound.set_volume(volume if volume is not None else self.volume)
			self.channel.play(sound)
			self.playing = True

	def play_overlap(self, filename, volume=None):
		with self._lock:
			sound = pygame.mixer.Sound(filename)
			sound.set_volume(volume if volume is not None else self.volume)
			channel = pygame.mixer.find_channel()
			if channel is not None:
				channel.play(sound)
			else:
				print("No free channel to play sound!")

	def play_sequence(self, filenames, volume=None):
		with self._lock:
			if not self.playing:
				self.queue = list(filenames)
				self.current_playing_audio = -1
				self.trigger_index = None
				self._play_next(volume) 

	def _play_next(self, volume=None):
		if self.queue:
			filename = self.queue.pop(0)
			sound = pygame.mixer.Sound(filename)
			sound.set_volume(volume if volume is not None else self.volume)
			self.channel.play(sound)
			self.playing = True
			self.current_playing_audio += 1
		else:
			self.playing = False

	def _update_loop(self):
		while self._running:
			with self._lock:
				if self.playing and not self.channel.get_busy():
					self._play_next()
			time.sleep(0.05)

	def trigger_record_index(self):
		with self._lock:
			if self.playing and self.channel.get_busy():
				self.trigger_index = self.current_playing_audio

	def stop(self):
		with self._lock:
			if self.channel:
				self.channel.stop()
			self.queue.clear()
			self.playing = False

	def shutdown(self):
		self._running = False
		self._thread.join()
