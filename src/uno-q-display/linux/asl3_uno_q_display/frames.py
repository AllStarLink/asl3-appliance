# SPDX-License-Identifier: GPL-2.0-or-later

"""Frame construction for the UNO Q's 8x13 LED matrix."""

ROWS = 8
COLUMNS = 13
BRIGHT = 6
DIM = 2
UNAVAILABLE_PAGE_SECONDS = 2.0

FONT_3X3 = {
    "0": ("111", "101", "111"),
    "1": ("010", "010", "010"),
    "2": ("110", "010", "011"),
    "3": ("110", "011", "110"),
    "4": ("101", "111", "001"),
    "5": ("111", "110", "011"),
    "6": ("100", "111", "111"),
    "7": ("111", "001", "001"),
    "8": ("111", "111", "111"),
    "9": ("111", "111", "001"),
}

def asl3() -> bytes:
    """Return the approved ASL mark with a small superscript 3."""
    frame = [[0] * COLUMNS for _ in range(ROWS)]
    glyphs = {
        "A": ("010", "101", "111", "101", "101"),
        "S": ("011", "100", "010", "001", "110"),
        "L": ("100", "100", "100", "100", "111"),
    }

    for x, character in ((0, "A"), (4, "S"), (8, "L")):
        for y, row in enumerate(glyphs[character], start=1):
            for offset, value in enumerate(row):
                if value == "1":
                    frame[y][x + offset] = BRIGHT

    for y, row in enumerate(("11", "01", "11"), start=1):
        for offset, value in enumerate(row):
            if value == "1":
                frame[y][10 + offset] = BRIGHT

    return bytes(pixel for row in frame for pixel in row)


def receive() -> bytes:
    """Return an RX label with a downward caret."""
    return _status_label("R", down=True)


def transmit() -> bytes:
    """Return a TX label with an upward caret."""
    return _status_label("T", down=False)


def broken_line() -> bytes:
    """Return a centered connection line interrupted by a five-pixel slash."""
    rows = (
        "0000000010000",
        "0000000100000",
        "1111101011111",
        "0000010000000",
        "0000100000000",
    )
    return _centered_icon(rows)


def unavailable_sequence(elapsed: float) -> bytes:
    """Alternate branding and the AMI-unavailable symbol."""
    pages = (asl3(), broken_line())
    index = int(elapsed / UNAVAILABLE_PAGE_SECONDS) % len(pages)
    return pages[index]


def idle_sequence(primary: str, links: tuple[str, ...], elapsed: float) -> bytes:
    """Select the current branding, primary-node, or linked-node page."""
    pages = [(1.0, asl3()), (2.0, node_number(primary))]
    pages.extend((2.0, node_number(link, DIM, index)) for index, link in enumerate(links, 1))
    position = elapsed % sum(duration for duration, _frame in pages)
    for duration, frame in pages:
        if position < duration:
            return frame
        position -= duration
    return pages[0][1]


def _status_label(first: str, down: bool) -> bytes:
    glyphs = {
        "R": ("110", "101", "110", "101", "101"),
        "T": ("111", "010", "010", "010", "010"),
        "X": ("101", "101", "010", "101", "101"),
    }
    frame = [[0] * COLUMNS for _ in range(ROWS)]
    for x, character in ((0, first), (4, "X")):
        for y, row in enumerate(glyphs[character], start=1):
            for offset, value in enumerate(row):
                if value == "1":
                    frame[y][x + offset] = BRIGHT

    caret = ("101", "010") if down else ("010", "101")
    start_y = 4 if down else 1
    for y, row in enumerate(caret, start=start_y):
        for offset, value in enumerate(row):
            if value == "1":
                frame[y][9 + offset] = BRIGHT
    return bytes(pixel for row in frame for pixel in row)


def _centered_icon(rows: tuple[str, ...]) -> bytes:
    frame = [[0] * COLUMNS for _ in range(ROWS)]
    start_x = (COLUMNS - len(rows[0])) // 2
    start_y = (ROWS - len(rows)) // 2
    for y, row in enumerate(rows, start=start_y):
        for offset, value in enumerate(row):
            if value == "1":
                frame[y][start_x + offset] = BRIGHT
    return bytes(pixel for row in frame for pixel in row)


def node_number(number: str, brightness: int = BRIGHT, indicator_count: int = 0) -> bytes:
    """Render a node number as two stable rows of up to three digits."""
    if not number.isdigit() or not 1 <= len(number) <= 6:
        raise ValueError("node number must contain one to six digits")
    if not 1 <= brightness <= BRIGHT:
        raise ValueError(f"brightness must be between 1 and {BRIGHT}")
    if indicator_count < 0:
        raise ValueError("indicator count cannot be negative")

    frame = [[0] * COLUMNS for _ in range(ROWS)]

    def draw_digits(digits: str, start_x: int, start_y: int) -> None:
        for index, character in enumerate(digits):
            for y, row in enumerate(FONT_3X3[character], start=start_y):
                for offset, value in enumerate(row):
                    if value == "1":
                        frame[y][start_x + index * 4 + offset] = brightness

    draw_digits(number[:3], start_x=0, start_y=0)
    if len(number) > 3:
        draw_digits(number[3:], start_x=2, start_y=4)

    for x in range(min(indicator_count, COLUMNS)):
        frame[ROWS - 1][x] = brightness
    return bytes(pixel for row in frame for pixel in row)
