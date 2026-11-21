"""Small amber padlock overlay indicating that a Peloton login is needed."""

LOGIN_ICON = (
    "01110",
    "10001",
    "10001",
    "11111",
    "11011",
    "11011",
    "11111",
)


def draw_login_indicator(matrix):
    # One black pixel of padding keeps the symbol readable over any screen.
    left, top = matrix.width - 7, matrix.height - 9
    for y in range(9):
        for x in range(7):
            px, py = left + x, top + y
            if 0 <= px < matrix.width and 0 <= py < matrix.height:
                lit = 1 <= x <= 5 and 1 <= y <= 7 and LOGIN_ICON[y - 1][x - 1] == "1"
                matrix.SetPixel(px, py, *( (255, 160, 0) if lit else (0, 0, 0)))
