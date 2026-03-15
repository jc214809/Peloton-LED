# python peloton_matrix_display.py
# Example: python3 peloton_matrix_display.py prepared.png --rows 32 --cols 64 --chain 1 --brightness 70
#
# This script loads an image (already prepared at the matrix resolution) and shows it.

import argparse
from PIL import Image
from rgbmatrix import RGBMatrix, RGBMatrixOptions

def main():
    p = argparse.ArgumentParser()
    p.add_argument("image", help="Image path (should be same size as matrix)")
    p.add_argument("--rows", type=int, default=32, help="Matrix rows (e.g. 32 or 64)")
    p.add_argument("--cols", type=int, default=64, help="Matrix cols per chain (e.g. 64)")
    p.add_argument("--chain", type=int, default=1, help="Chain length")
    p.add_argument("--parallel", type=int, default=1, help="Parallel chains")
    p.add_argument("--gpio-slowdown", type=int, default=2, help="GPIO slowdown (tweak for Pi model)")
    p.add_argument("--brightness", type=int, default=80, help="Brightness (0-100)")
    p.add_argument("--pwm-bits", type=int, default=11, help="PWM bits (default can be 11)")
    p.add_argument("--rgb-mapping", default="adafruit-hat", help="Hardware mapping (e.g. adafruit-hat, regular)")
    args = p.parse_args()

    options = RGBMatrixOptions()
    options.rows = args.rows
    options.cols = args.cols
    options.chain_length = args.chain
    options.parallel = args.parallel
    options.gpio_slowdown = args.gpio_slowdown
    options.brightness = args.brightness
    options.pwm_bits = args.pwm_bits
    # Mapping: depends on HAT/driver version; try 'adafruit-hat' or omit
    options.hardware_mapping = args.rgb_mapping

    matrix = RGBMatrix(options=options)

    img = Image.open(args.image).convert("RGB")
    # Safety: if image mismatched size, resize to matrix
    if img.size != (args.cols * args.chain, args.rows * args.parallel):
        img = img.resize((args.cols * args.chain, args.rows * args.parallel), Image.LANCZOS)

    matrix.SetImage(img)

    try:
        print("Image shown. Press Ctrl-C to exit.")
        while True:
            pass
    except KeyboardInterrupt:
        matrix.Clear()

if __name__ == "__main__":
    main()