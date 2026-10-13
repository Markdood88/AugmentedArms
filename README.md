Augmented Arms application on Rasp Pi 5 for Muto Arm animation recording and playback, using audio-tap trigger system (Piezo sensor)

BMI Trainer application on Rasp Pi 5 for ALS Patients (or anyone really) to record brainwave activity via OpenBCI board, and train a local model for audio-stimuli based selection activity.

BMI Trainer model testing can send each predicted direction to the live animation receiver over UDP. The receiver-compatible messages are `BMI: 1` (left), `BMI: 2` (center), and `BMI: 3` (right). The default destination is `127.0.0.1:21623`.

Configure the destination with command-line options:

```bash
python3 BMI-Trainer.py --bmi-udp-host 192.168.1.50 --bmi-udp-port 21623
```

The same settings can be supplied with `BMI_UDP_HOST` and `BMI_UDP_PORT` environment variables. The UDP message is sent immediately after prediction and before the prediction audio starts.

TODO:
  -Remove local recordings after upload?
  -Japanese Language switch for Trainer Scenes
