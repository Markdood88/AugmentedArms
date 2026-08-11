#!/bin/bash
set -e

CONF="$(dirname "$0")/usb-names.conf"
RULES="/etc/udev/rules.d/99-usb-serial-names.rules"

echo "# Auto-generated — do not edit" | sudo tee "$RULES" > /dev/null

while read -r V P S M NAME; do
	[[ -z "$V" || "$V" == \#* ]] && continue

	echo "SUBSYSTEM==\"tty\", \\
ENV{ID_VENDOR_ID}==\"$V\", \\
ENV{ID_MODEL_ID}==\"$P\", \\
ENV{ID_SERIAL_SHORT}==\"$S\", \\
ENV{ID_MODEL}==\"$M\", \\
SYMLINK+=\"$NAME\"" \
	| sed 's/=="\*"/!=""/g' \
	| sudo tee -a "$RULES" > /dev/null
done < "$CONF"

sudo udevadm control --reload-rules
sudo udevadm trigger