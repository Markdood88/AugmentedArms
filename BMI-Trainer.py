import argparse

from Scene_Utils import BMITrainer

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="BMI Trainer")
	parser.add_argument("--bmi-udp-host", default=None, help="UDP destination IP/hostname (default: BMI_UDP_HOST or 127.0.0.1)")
	parser.add_argument("--bmi-udp-port", type=int, default=None, help="UDP destination port (default: BMI_UDP_PORT or 21623)")
	args = parser.parse_args()
	app = BMITrainer(bmi_udp_host=args.bmi_udp_host, bmi_udp_port=args.bmi_udp_port)
	app.main_loop()
