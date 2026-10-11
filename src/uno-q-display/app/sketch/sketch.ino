// SPDX-License-Identifier: GPL-2.0-or-later

#include <Arduino_LED_Matrix.h>
#include <Arduino_RouterBridge.h>
#include <vector>

namespace {
constexpr size_t kRows = 8;
constexpr size_t kColumns = 13;
constexpr size_t kFrameSize = kRows * kColumns;

Arduino_LED_Matrix matrix;

// Show branding immediately after the MCU starts. The Linux service replaces
// this frame when it has connected to the Arduino Router and obtained node
// state from Asterisk.
uint8_t frame[kFrameSize] = {
	0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
	0, 6, 0, 0, 0, 6, 6, 0, 6, 0, 6, 6, 0,
	6, 0, 6, 0, 6, 0, 0, 0, 6, 0, 0, 6, 0,
	6, 6, 6, 0, 0, 6, 0, 0, 6, 0, 6, 6, 0,
	6, 0, 6, 0, 0, 0, 6, 0, 6, 0, 0, 0, 0,
	6, 0, 6, 0, 6, 6, 0, 0, 6, 6, 6, 0, 0,
	0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
	0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
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
