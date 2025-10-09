import socket
import cv2
import pyaudio
import struct
import time

# Client configuration
SERVER_HOST = "211.ip.gl.ply.gg"
STREAM_PORT = 40815

# Audio/Video configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 48000
FPS = 20.0
CHUNK = int(RATE / FPS)
JPEG_QUALITY = 92


def initialize_camera_best_quality(camera_index=0):
    """
    Initialize camera with the best available resolution.
    Tries resolutions in descending order: 1080p -> 720p -> 480p
    """
    cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        raise RuntimeError(f"Failed to open camera {camera_index}")

    # Resolution priorities (width, height, name)
    resolutions = [
        (1920, 1080, "1080p"),
        (1280, 720, "720p"),
        (640, 480, "480p"),
    ]

    best_resolution = None

    for width, height, name in resolutions:
        # Try to set the resolution
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        # Verify what was actually set
        actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Check if we got the requested resolution (with some tolerance)
        if abs(actual_width - width) <= 10 and abs(actual_height - height) <= 10:
            best_resolution = (actual_width, actual_height, name)
            print(f"✓ Camera set to {name}: {actual_width}x{actual_height}")
            break
        else:
            print(f"✗ {name} ({width}x{height}) not supported, got {actual_width}x{actual_height}")

    if best_resolution is None:
        # Use whatever the camera defaulted to
        actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"Using camera default: {actual_width}x{actual_height}")
        best_resolution = (actual_width, actual_height, "default")

    # Try to set optimal FPS
    fps_options = [30, 25, 20, 15]
    for fps in fps_options:
        cap.set(cv2.CAP_PROP_FPS, fps)
        actual_fps = cap.get(cv2.CAP_PROP_FPS)
        if abs(actual_fps - fps) < 2:
            print(f"✓ FPS set to {fps}")
            break
    else:
        actual_fps = cap.get(cv2.CAP_PROP_FPS)
        print(f"Using default FPS: {actual_fps}")

    # Optional: Enable autofocus and auto-exposure if supported
    cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)

    return cap, best_resolution


def main():
    while True:
        client_socket = None
        cap = None
        audio_stream = None
        p = None

        try:
            print(f"Attempting to connect to {SERVER_HOST}:{STREAM_PORT}...")
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((SERVER_HOST, STREAM_PORT))
            print("Connection successful. Starting stream.")

            # Initialize camera with best available quality
            cap, resolution_info = initialize_camera_best_quality(0)
            actual_width, actual_height, res_name = resolution_info

            print(f"Streaming at {res_name}: {actual_width}x{actual_height}")

            p = pyaudio.PyAudio()
            audio_stream = p.open(format=FORMAT, channels=CHANNELS,
                                  rate=RATE, input=True,
                                  frames_per_buffer=CHUNK)

            frame_time = 1.0 / FPS
            frame_count = 0

            while True:
                start_time = time.time()

                ret, frame = cap.read()
                if not ret:
                    print("Failed to grab frame from camera.")
                    break

                # Encode with higher quality
                result, frame_encoded = cv2.imencode(
                    '.jpg', frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
                )

                if not result:
                    print("Failed to encode frame.")
                    continue

                video_data = frame_encoded.tobytes()
                audio_data = audio_stream.read(CHUNK, exception_on_overflow=False)

                video_len = len(video_data)
                audio_len = len(audio_data)
                header = struct.pack(">LL", video_len, audio_len)

                try:
                    client_socket.sendall(header + video_data + audio_data)
                except (BrokenPipeError, ConnectionResetError):
                    print("Connection lost during send.")
                    break

                frame_count += 1
                if frame_count % 100 == 0:
                    print(f"Frames sent: {frame_count}, Frame size: {video_len / 1024:.1f} KB")

                elapsed_time = time.time() - start_time
                sleep_time = frame_time - elapsed_time
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except (BrokenPipeError, ConnectionResetError):
            print("Server connection lost.")
        except ConnectionRefusedError:
            print("Connection refused. Server may be down or busy.")
        except KeyboardInterrupt:
            print("\nStopping client.")
            break
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
        finally:
            if cap:
                cap.release()
            if audio_stream:
                audio_stream.stop_stream()
                audio_stream.close()
            if p:
                p.terminate()
            if client_socket:
                client_socket.close()

            print("Client resources released. Reconnecting in 5 minutes...")
            try:
                time.sleep(300)
            except KeyboardInterrupt:
                print("\nStopping client during wait.")
                break

if __name__ == "__main__":
    main()
