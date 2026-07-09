"""
ABMI_Utils_2x.py

B2J "2x" 用ユーティリティ。ABMI_Utils.py の共通部品（BCIBoard, play_single_sound,
ISI, SOUND_LENGTH 等）はそのまま再利用し、以下の 3 関数だけを差し替える。

  1. generateSequence()          : 刺激シーケンスを 10 → 5 セットに変更。
                                   さらに末尾の 2 秒インターバルの代わりに
                                   ボーナス 1 セット（6 セット目）を追加する。
                                   AuditoryBCI_Mac/main.py の MODEL_TYPE="new"
                                   （set_num=5）の play_stimuli と同じ挙動。
  2. startSingleTrainingSequence(): 上記 generateSequence を使い、刺激再生後の
                                   time.sleep(2) を短縮（ボーナスセットが
                                   末尾区間を埋めるため）。
  3. useModelToPredict()         : model.py(SVM) ではなく model_2x.py
                                   （two-band LDA, model_2x.pkl）で予測する。

B2J-User_2x.py から呼び出される。B2J-User.py / ABMI_Utils.py は変更しない。
"""

import os
import time
import random
import threading

import joblib
import numpy as np
import pandas as pd

import ABMI_Utils
import model_2x

# 予測の診断ログを出すか（原因切り分け用）。本番で静かにしたいときは False。
DEBUG = True

# ABMI_Utils 側の共通定数・関数を別名で参照（変更しない）
ISI = ABMI_Utils.ISI
SOUND_LENGTH = ABMI_Utils.SOUND_LENGTH
play_single_sound = ABMI_Utils.play_single_sound
SingleTrainingSequenceError = ABMI_Utils.SingleTrainingSequenceError

# 1 試行あたりの刺激セット数（10 → 5）
NUM_SEQUENCES = 5


def generateSequence(num_sequences=NUM_SEQUENCES):
	"""
	Left/Center/Right/Silent の非反復順を num_sequences セット分生成する。

	num_sequences < 10 の場合は、末尾の無音インターバルの代わりに
	ボーナス 1 セットを追加する（最後の本番セットの刺激にも十分な
	解析窓を確保するため）。これは AuditoryBCI_Mac/main.py の
	play_stimuli(set_num<10) と同じロジック。
	"""
	stimulation_sequence = []
	sequence_ids = []
	prev_stim = None

	playableIDs = [1, 2, 3, 4]

	for set_idx in range(num_sequences):
		stim_order = random.sample(playableIDs, len(playableIDs))
		while prev_stim is not None and stim_order[0] == prev_stim:
			stim_order = random.sample(playableIDs, len(playableIDs))
		prev_stim = stim_order[-1]
		stimulation_sequence.extend(stim_order)
		sequence_ids.extend([set_idx + 1] * len(stim_order))

	# 末尾 2 秒インターバルを 1 シーケンス（ボーナスセット）に置き換える
	if num_sequences < 10:
		bonus_order = random.sample(playableIDs, len(playableIDs))
		while prev_stim is not None and bonus_order[0] == prev_stim:
			bonus_order = random.sample(playableIDs, len(playableIDs))
		stimulation_sequence.extend(bonus_order)
		sequence_ids.extend([num_sequences + 1] * len(bonus_order))

	return stimulation_sequence, sequence_ids


def startSingleTrainingSequence(board, user_id, timestamp, lcr_value, base_path):
	"""
	単一トレーニングシーケンスをバックグラウンドスレッドで開始する。

	ABMI_Utils.startSingleTrainingSequence と同一だが、
	  - generateSequence は本モジュールの 5(+1) セット版を使用
	  - 刺激再生後の末尾インターバル time.sleep(2) を 0.05 秒に短縮
	    （末尾区間はボーナスセットが埋めるため）

	Returns a tuple of (worker_thread, cancel_event).
	"""
	if board is None:
		raise ValueError('board is required')

	if not getattr(board, 'connected', False):
		raise RuntimeError('BCIBoard is not connected')

	if not getattr(board, 'streaming', False):
		raise RuntimeError('BCIBoard is not streaming')

	if not isinstance(user_id, str):
		user_id = str(user_id)
	if len(user_id) != 9 or not user_id.isdigit():
		raise ValueError('user_id must be a 9-digit string')

	if lcr_value not in (0, 1, 2, 3, 4):
		raise ValueError('lcr_value must be 0 (testing), 1 (left), 2 (center), 3 (right), 4 (live)')

	direction_map = {0: "testing", 1: "left", 2: "center", 3: "right", 4: "live"}
	direction = direction_map[lcr_value]

	base_dir = ABMI_Utils.Path(base_path).expanduser().resolve()
	base_dir.mkdir(parents=True, exist_ok=True)

	if hasattr(timestamp, 'strftime'):
		timestamp_str = timestamp.strftime('%Y-%m-%d-%H-%M-%S')
	else:
		timestamp_str = str(timestamp)

	filename = f"{user_id}-{timestamp_str}-{lcr_value}.csv"

	instruction_path = f"Sounds/instruction_{direction}.wav"
	beep_path = f"Sounds/beep_{direction}.wav"
	instruction_starting = "Sounds/instruction_starting.wav"

	stimulus_sound, sequence_id = generateSequence()
	cancel_event = threading.Event()

	def _sequence_worker():
		try:

			if cancel_event.is_set():
				return

			play_single_sound(instruction_path, block=True)  # First Instruction
			time.sleep(ISI)

			if cancel_event.is_set():
				return

			if lcr_value == 0 or lcr_value == 4:  # Testing Mode, one of each beep.
				play_single_sound("Sounds/beep_left.wav", block=True)
				time.sleep(.5)
				play_single_sound("Sounds/beep_center.wav", block=True)
				time.sleep(.5)
				play_single_sound("Sounds/beep_right.wav", block=True)
				time.sleep(.5)

			else:
				for _ in range(3):  # 3 Beeps
					play_single_sound(beep_path, block=True)
					time.sleep(ISI)

			if cancel_event.is_set():
				return

			if lcr_value == 4:
					instruction_starting = "Sounds/begin.mp3"
			else:
				instruction_starting = "Sounds/instruction_starting.wav"

			play_single_sound(instruction_starting, block=True)  # Say Starting

			if cancel_event.is_set():
				return

			# Start Recording
			board.stimulus_sound = 0
			board.sequence_id = 0
			board.start_recording(base_path, filename=filename)
			time.sleep(2)

			start_time = time.time() + 0.1  # 少し余裕を持って開始
			for stim_idx, (sound, id) in enumerate(zip(stimulus_sound, sequence_id)):

				# Wait until the scheduled time only to play sound and update
				scheduled_time = start_time + stim_idx * (ISI + SOUND_LENGTH)
				while time.time() < scheduled_time:
					time.sleep(0.0005)

				if cancel_event.is_set():
					break

				board.stimulus_sound = sound
				board.sequence_id = id

				if sound == 1:
					play_single_sound("Sounds/beep_left.wav", block=True)
				elif sound == 2:
					play_single_sound("Sounds/beep_center.wav", block=True)
				elif sound == 3:
					play_single_sound("Sounds/beep_right.wav", block=True)
				elif sound == 4:
					play_single_sound("Sounds/beep_silent.wav", block=True)

			if cancel_event.is_set():
				board.stop_recording()
				return

			board.stimulus_sound = 0
			board.sequence_id = 0
			# 末尾 2 秒インターバルはボーナスセットで置き換え済みのため短縮
			time.sleep(0.05)

			board.stop_recording()

		except Exception as exc:
			print(f"[BCIBoard] Training sequence error: {exc}")
			raise SingleTrainingSequenceError(str(exc)) from exc
		finally:
			board.stimulus_sound = 0
			board.sequence_id = 0

	sequence_thread = threading.Thread(target=_sequence_worker, daemon=True)
	sequence_thread.start()

	return sequence_thread, cancel_event


def _diagnose_recording(test_file_path):
	"""
	予測失敗の原因切り分け用に、録音 CSV を model_2x と同じ手順で
	段階的にチェックして print する。どの段階で破綻したかを特定できる。
	"""
	print(f"[DIAG] file: {test_file_path}")

	if not os.path.exists(test_file_path):
		print("[DIAG] -> ファイルが存在しません")
		return

	try:
		df = pd.read_csv(test_file_path)
	except Exception as e:
		print(f"[DIAG] -> CSV 読み込み失敗: {e}")
		return

	data = df.values
	n = data.shape[0]
	print(f"[DIAG] rows={n} (約 {n / 250.0:.2f}s @250Hz), columns={list(df.columns)}")

	if data.shape[1] <= 9:
		print("[DIAG] -> 列数が不足。Label列(index9)が無い → 録音フォーマット異常")
		return

	stim = np.nan_to_num(data[:, 9], nan=0)
	onsets_all = np.where(np.diff(stim) != 0)[0] + 1
	onsets_nz = onsets_all[stim[onsets_all] != 0]

	SEQ = model_2x.SEQ
	WS = model_2x.WS
	onsets = onsets_nz[:4 * SEQ]

	print(f"[DIAG] オンセット: 全変化={len(onsets_all)}, 非ゼロ={len(onsets_nz)}, "
		  f"使用(先頭{4 * SEQ})={len(onsets)}")

	if len(onsets_nz) == 0:
		print("[DIAG] -> 刺激オンセットが0。Label列が全て0＝刺激ラベル未記録の可能性")
		return

	used_labels = stim[onsets].astype(int)
	uniq, cnt = np.unique(used_labels, return_counts=True)
	print(f"[DIAG] 使用オンセットのラベル分布: {dict(zip(uniq.tolist(), cnt.tolist()))}")

	with_window = np.array([int(o) for o in onsets if o + WS <= n], dtype=int)
	print(f"[DIAG] 1秒窓(={WS}サンプル)が後ろに確保できたオンセット: "
		  f"{len(with_window)}/{len(onsets)}")

	valid_labels = stim[with_window].astype(int) if len(with_window) else np.array([], dtype=int)
	per_label = {l: int(np.sum(valid_labels == l)) for l in (1, 2, 3)}
	print(f"[DIAG] L/C/R(1/2/3)の有効エポック数: {per_label}")

	missing = [l for l, c in per_label.items() if c == 0]
	if missing:
		print(f"[DIAG] -> ラベル {missing} の有効エポックが0 → 特徴量計算でKeyError/None")
	else:
		print("[DIAG] -> L/C/R 全てエポックあり。特徴抽出は成功する見込み")


def useModelToPredict(test_file_path, model_folder="Model/"):
	"""
	model_2x.py（two-band LDA）で予測する。

	ABMI_Utils.useModelToPredict が Model/model.pkl(SVM) を使うのに対し、
	こちらは Model/model_2x.pkl をロードし、model_2x.extract_features で
	特徴量を抽出して予測する。

	DEBUG=True のとき、各段階（モデル読込／特徴抽出／予測）の結果を print し、
	失敗時には _diagnose_recording で録音 CSV の内訳を出力する。
	"""
	model_path = os.path.join(model_folder, "model_2x.pkl")

	# 1) モデル読み込み
	try:
		clf = joblib.load(model_path)
	except Exception as e:
		print(f"[ERROR] 段階1: モデル読み込み失敗 ({model_path}): {e}")
		raise
	if DEBUG:
		print(f"[DIAG] 段階1 OK: モデル読込 {model_path}")

	# 2) 特徴抽出
	try:
		features = model_2x.extract_features(test_file_path)
	except Exception as e:
		print(f"[ERROR] 段階2: 特徴抽出で例外 ({type(e).__name__}): {e}")
		_diagnose_recording(test_file_path)
		raise

	if features is None:
		print("[ERROR] 段階2: 特徴抽出が None を返却（オンセット未検出 or 録音長不足）")
		_diagnose_recording(test_file_path)
		raise ValueError(f"Feature extraction failed for {test_file_path}")

	if DEBUG:
		print(f"[DIAG] 段階2 OK: 特徴ベクトル shape={features.shape}")

	# 3) 予測
	predictions = clf.predict(features.reshape(1, -1))
	result = int(predictions[0])
	print(f"[DIAG] 段階3 OK: prediction={result}")
	return result
