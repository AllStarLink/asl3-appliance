# SPDX-License-Identifier: GPL-2.0-or-later

"""Frame construction for the UNO Q's 8x13 LED matrix."""

ROWS = 8
COLUMNS = 13
BRIGHT = 4
DIM = 3
UNAVAILABLE_PAGE_SECONDS = 2.0
BRAND_SECONDS = 3.0
SCROLL_STEP_SECONDS = 0.15
CHAR_WIDTH = 4
NARROW_CHAR_WIDTH = 2
TEXT_TOP = 1

# Letters and digits use 4x6 cells; spaces and colons use 2x6 cells.
SCROLL_FONT = {
    " ": ( "00",  "00",  "00",  "00",  "00"),
    ",": ("000", "000", "000", "010", "100"),
    ":": ( "00",  "10",  "00",  "10",  "00"),
    "0": ("010", "101", "101", "101", "010"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("110", "001", "010", "100", "111"),
    "3": ("110", "001", "010", "001", "110"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "110", "001", "110"),
    "6": ("011", "100", "110", "101", "010"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("010", "101", "010", "101", "010"),
    "9": ("010", "101", "011", "001", "110"),
    "L": ("100", "100", "100", "100", "111"),
    "N": ("101", "111", "111", "111", "101"),
    "d": ("001", "011", "101", "101", "011"),
    "e": ("000", "010", "111", "100", "011"),
    "i": ("010", "000", "010", "010", "010"),
    "k": ("100", "101", "110", "101", "101"),
    "n": ("000", "110", "101", "101", "101"),
    "o": ("000", "010", "101", "101", "010"),
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
    """Hold ASL³, then scroll the local node and any linked nodes."""
    numbers = (primary, *links)
    if any(not number.isascii() or not number.isdigit() for number in numbers):
        raise ValueError("node numbers must contain only digits")

    node_text = f" Node:{primary} "
    link_text = f"Link:{','.join(links)} " if links else ""
    text = node_text + link_text
    cell_widths = [NARROW_CHAR_WIDTH if character in " :" else CHAR_WIDTH for character in text]
    brightness = BRIGHT if links else DIM
    # Stop once the trailing space is fully on screen, leaving the last digit visible.
    scroll_steps = sum(cell_widths) - COLUMNS + 1
    cycle_seconds = BRAND_SECONDS + scroll_steps * SCROLL_STEP_SECONDS
    position = elapsed % cycle_seconds
    if position < BRAND_SECONDS:
        return asl3()

    step = int((position - BRAND_SECONDS) / SCROLL_STEP_SECONDS)
    frame = [[0] * COLUMNS for _ in range(ROWS)]
    cursor_x = -step
    for character, cell_width in zip(text, cell_widths):
        glyph = SCROLL_FONT[character]
        start_x = cursor_x
        cursor_x += cell_width
        if start_x >= COLUMNS or start_x + len(glyph[0]) <= 0:
            continue
        for y, row in enumerate(glyph, start=TEXT_TOP):
            for offset, value in enumerate(row):
                x = start_x + offset
                if value == "1" and 0 <= x < COLUMNS:
                    frame[y][x] = brightness
    return bytes(pixel for row in frame for pixel in row)


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
