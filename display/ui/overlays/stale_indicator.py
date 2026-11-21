"""Small blue clock overlay indicating that cached data is being displayed."""

STALE_ICON = (
    "01110",
    "10001",
    "10101",
    "10101",
    "10011",
    "10001",
    "01110",
)


def draw_stale_indicator(matrix):
    # Place the clock opposite the login padlock so both states remain visible.
    left, top = 0, matrix.height - 9
    for y in range(9):
        for x in range(7):
            px, py = left + x, top + y
            if 0 <= px < matrix.width and 0 <= py < matrix.height:
                lit = 1 <= x <= 5 and 1 <= y <= 7 and STALE_ICON[y - 1][x - 1] == "1"
                matrix.SetPixel(px, py, *((70, 170, 255) if lit else (0, 0, 0)))
