APP_NAME := asl3-node-display
APP_DIR := app
MANAGED_APP_DIR := /home/arduino/ArduinoApps/$(APP_NAME)
BUILD_DIR := build
STAGE_DIR := $(BUILD_DIR)/$(APP_NAME)
ARCHIVE := $(BUILD_DIR)/$(APP_NAME).zip
UNO_Q_MODEL := Arduino UnoQ

.PHONY: help check-uno-q archive import sync-app deploy clear-default install-service update-service service-status service-logs reinstall start logs clean

help:
	@echo "ASL3 Arduino UNO Q display"
	@echo
	@echo "  make check-uno-q  Verify that this system is an Arduino UNO Q"
	@echo "  make archive      Build the Arduino App import archive"
	@echo "  make import       Build and import the Arduino App"
	@echo "  make deploy       Update and restart the imported Arduino App"
	@echo "  make clear-default  Preserve the factory display until Linux starts"
	@echo "  make install-service  Install and start the Linux display service"
	@echo "  make update-service   Update and restart only the Linux display service"
	@echo "  make service-status   Show Linux display service status"
	@echo "  make service-logs     Show Linux display service logs"
	@echo "  make reinstall    Replace and start the imported Arduino App"
	@echo "  make start        Start the imported Arduino App"
	@echo "  make logs         Show all available Arduino App logs"
	@echo "  make clean        Remove generated files"

check-uno-q:
	@model="$$(tr -d '\0' < /proc/device-tree/model 2>/dev/null)"; \
	if [ "$$model" != "$(UNO_Q_MODEL)" ]; then \
		echo "error: expected '$(UNO_Q_MODEL)', found '$${model:-unknown}'" >&2; \
		exit 1; \
	fi
	@echo "Detected $(UNO_Q_MODEL)"

archive:
	rm -rf "$(STAGE_DIR)" "$(ARCHIVE)"
	install -d "$(STAGE_DIR)"
	cp -a "$(APP_DIR)/." "$(STAGE_DIR)/"
	cd "$(BUILD_DIR)" && zip -qr "$(APP_NAME).zip" "$(APP_NAME)"
	@echo "Created $(ARCHIVE)"

import: check-uno-q archive
	arduino-app-cli app import "$(abspath $(ARCHIVE))"

sync-app: check-uno-q
	@test -d "$(MANAGED_APP_DIR)" || { \
		echo "error: import the app before deploying updates" >&2; \
		exit 1; \
	}
	cp -a "$(APP_DIR)/." "$(MANAGED_APP_DIR)/"

deploy: sync-app
	arduino-app-cli app restart "user:$(APP_NAME)" --verbose

clear-default: check-uno-q
	sudo rm -f /var/lib/arduino-app-cli/default.app

install-service: check-uno-q
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

update-service: check-uno-q
	sudo install -d -m 0755 /usr/share/asl3-appliance/uno-q-display/app
	sudo cp -a app/. /usr/share/asl3-appliance/uno-q-display/app/
	sudo install -D -m 0755 linux/asl3-uno-q-app /usr/libexec/asl3/asl3-uno-q-app
	sudo install -D -m 0755 linux/asl3-uno-q-display /usr/libexec/asl3/asl3-uno-q-display
	sudo install -d -m 0755 /usr/lib/python3/dist-packages/asl3_uno_q_display
	sudo install -m 0644 linux/asl3_uno_q_display/*.py /usr/lib/python3/dist-packages/asl3_uno_q_display/
	sudo systemctl restart asl3-uno-q-display.service

service-status: check-uno-q
	systemctl --no-pager --full status asl3-uno-q-display.service

service-logs: check-uno-q
	journalctl --no-pager -u asl3-uno-q-display.service -n 100

reinstall: check-uno-q archive
	arduino-app-cli app destroy "user:$(APP_NAME)"
	arduino-app-cli app import "$(abspath $(ARCHIVE))"
	arduino-app-cli app start "user:$(APP_NAME)" --verbose

start: check-uno-q
	arduino-app-cli app start "user:$(APP_NAME)" --verbose

logs: check-uno-q
	arduino-app-cli app logs "user:$(APP_NAME)" --all

clean:
	rm -rf "$(BUILD_DIR)"
