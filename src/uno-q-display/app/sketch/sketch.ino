// SPDX-License-Identifier: GPL-2.0-or-later

#include <Arduino_LED_Matrix.h>
#include <Arduino_RouterBridge.h>
#include <vector>

namespace {
constexpr size_t kRows = 8;
constexpr size_t kColumns = 13;
constexpr size_t kFrameSize = kRows * kColumns;
constexpr uint8_t BRIGHT = 4;
constexpr uint8_t DIM = 2;
constexpr uint8_t OFF = 0;
constexpr uint8_t LIT = BRIGHT;
static_assert(DIM < BRIGHT, "dim level must be lower than normal brightness");

Arduino_LED_Matrix matrix;

// Show branding immediately after the MCU starts. The Linux service replaces
// this frame when it has connected to the Arduino Router and obtained node
// state from Asterisk.
uint8_t frame[kFrameSize] = {
	OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF,
	OFF, LIT, OFF, OFF, OFF, LIT, LIT, OFF, LIT, OFF, LIT, LIT, OFF,
	LIT, OFF, LIT, OFF, LIT, OFF, OFF, OFF, LIT, OFF, OFF, LIT, OFF,
	LIT, LIT, LIT, OFF, OFF, LIT, OFF, OFF, LIT, OFF, LIT, LIT, OFF,
	LIT, OFF, LIT, OFF, OFF, OFF, LIT, OFF, LIT, OFF, OFF, OFF, OFF,
	LIT, OFF, LIT, OFF, LIT, LIT, OFF, OFF, LIT, LIT, LIT, OFF, OFF,
	OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF,
	OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF,
};

void draw(std::vector<uint8_t> new_frame)
{
	const size_t length = min(new_frame.size(), kFrameSize);
	memcpy(frame, new_frame.data(), length);
	if (length < kFrameSize) {
		memset(frame + length, 0, kFrameSize - length);
	}
}
} // namespace

void setup()
{
	matrix.begin();
	matrix.setGrayscaleBits(3);
	matrix.clear();

	Bridge.begin();
	Bridge.provide("draw", draw);
}

void loop()
{
	matrix.draw(frame);
	delay(10);
}
