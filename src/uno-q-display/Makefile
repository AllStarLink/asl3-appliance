.PHONY: help check-uno-q deploy status logs

help:
	@echo "ASL3 Arduino UNO Q display"
	@echo "  make deploy  Install or update the app and display service"
	@echo "  make status  Show display service status"
	@echo "  make logs    Show display service logs"

check-uno-q:
	@if ! tr '\0' '\n' < /proc/device-tree/compatible 2>/dev/null | grep -Fxq 'arduino,imola'; then \
		echo "error: expected an Arduino UNO Q" >&2; \
		exit 1; \
	fi

deploy: check-uno-q
	sudo install -d -m 0755 /usr/share/asl3-appliance/uno-q-display/app
	sudo cp -a app/. /usr/share/asl3-appliance/uno-q-display/app/
	sudo install -D -m 0755 linux/asl3-uno-q-app /usr/libexec/asl3/asl3-uno-q-app
	sudo install -D -m 0755 linux/asl3-uno-q-display /usr/libexec/asl3/asl3-uno-q-display
	sudo install -d -m 0755 /usr/lib/python3/dist-packages/asl3_uno_q_display
	sudo install -m 0644 linux/asl3_uno_q_display/*.py /usr/lib/python3/dist-packages/asl3_uno_q_display/
	sudo install -D -m 0644 linux/asl3-uno-q-app.service /etc/systemd/system/asl3-uno-q-app.service
	sudo install -D -m 0644 linux/asl3-uno-q-display.service /etc/systemd/system/asl3-uno-q-display.service
	sudo systemctl daemon-reload
	sudo systemctl enable asl3-uno-q-app.service asl3-uno-q-display.service
	sudo systemctl restart asl3-uno-q-app.service
	sudo systemctl restart asl3-uno-q-display.service

status: check-uno-q
	systemctl --no-pager --full status asl3-uno-q-app.service asl3-uno-q-display.service

logs: check-uno-q
	journalctl --no-pager -u asl3-uno-q-app.service -u asl3-uno-q-display.service -n 100
