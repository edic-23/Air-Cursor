"""Scan for working cameras and report their index.

Run this AFTER starting GlideX (phone-as-webcam) to find which index to enter in
Air Cursor's Settings:

    .venv\\Scripts\\python find_camera.py
"""

import cv2

BACKENDS = [("DSHOW", cv2.CAP_DSHOW), ("MSMF", cv2.CAP_MSMF), ("ANY", cv2.CAP_ANY)]


def main():
    print("Scanning camera indices 0-5 across backends...\n")
    working = []
    for idx in range(6):
        for name, be in BACKENDS:
            cap = cv2.VideoCapture(idx, be)
            opened = cap.isOpened()
            ok = False
            shape = None
            if opened:
                ok, frame = cap.read()
                if ok and frame is not None:
                    shape = frame.shape
            cap.release()
            if ok:
                print(f"  index {idx} via {name:5s} -> WORKING, frame {shape}")
                working.append(idx)
                break  # this index works; no need to try other backends
        else:
            continue

    print()
    if working:
        print(f"Use Camera index = {working[0]} in Air Cursor Settings "
              f"(working indices: {sorted(set(working))}).")
    else:
        print("No working camera found. Is GlideX started and streaming video?")


if __name__ == "__main__":
    main()
