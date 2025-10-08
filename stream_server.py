import socket
import cv2
import numpy as np
import pyaudio
import struct
import os
import sys
import threading

# Server configuration
STREAM_HOST = "0.0.0.0"
STREAM_PORT = 8000

# Audio/Video configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 48000
VIDEO_FPS = 20.0
CHUNK = int(RATE / VIDEO_FPS)

def list_audio_devices(p):
    print("Available audio output devices:")
    for i in range(p.get_device_count()):
        dev = p.get_device_info_by_index(i)
        if dev['maxOutputChannels'] > 0:
            print(f"  Index {dev['index']}: {dev['name']}")

def handle_client(conn, addr, device_index):
    print(f"Streaming client connected from {addr}")
    conn.settimeout(120.0)  # Set 2-minute timeout for client inactivity

    p = None
    audio_stream = None

    try:
        p = pyaudio.PyAudio()
        print(f"[{addr}] Attempting to start audio stream...")
        try:
            audio_stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True,
                                  frames_per_buffer=CHUNK, output_device_index=device_index)
            print(f"[{addr}] Audio stream opened successfully on device index {device_index}.")
        except Exception as e:
            print(f"[{addr}] Failed to open audio stream: {e}")

        data = b""
        header_size = struct.calcsize(">LL")

        while True:
            while len(data) < header_size:
                packet = conn.recv(4 * 1024)
                if not packet: break
                data += packet
            if not packet: break

            packed_header = data[:header_size]
            data = data[header_size:]
            video_len, audio_len = struct.unpack(">LL", packed_header)

            while len(data) < video_len + audio_len:
                data += conn.recv(4 * 1024)

            video_data = data[:video_len]
            audio_frame_data = data[video_len:video_len + audio_len]
            data = data[video_len + audio_len:]

            nparr = np.frombuffer(video_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            window_name = f'Video from {addr}'
            if frame is not None:
                cv2.imshow(window_name, frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            
            if audio_stream:
                audio_stream.write(audio_frame_data)

    except socket.timeout:
        print(f"Client {addr} timed out after 120 seconds of inactivity. Disconnecting.")
    except (BrokenPipeError, ConnectionResetError):
        print(f"Client {addr} disconnected.")
    except Exception as e:
        print(f"Error with client {addr}: {e}")
    finally:
        # Close all resources
        if audio_stream:
            audio_stream.stop_stream()
            audio_stream.close()
        if p:
            p.terminate()
        conn.close()
        cv2.destroyWindow(f'Video from {addr}')
        print(f"Connection with {addr} closed.")

def main():
    p = pyaudio.PyAudio()
    list_audio_devices(p)
    device_index = -1
    try:
        device_index = int(input("Enter the index of the audio device to use for all streams: "))
    except ValueError:
        print("Invalid input. Exiting.")
        p.terminate()
        return
    p.terminate()

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((STREAM_HOST, STREAM_PORT))
    server_socket.listen(20)
    print(f"Streaming server listening on {STREAM_HOST}:{STREAM_PORT}...")

    try:
        while True:
            conn, addr = server_socket.accept()
            client_thread = threading.Thread(target=handle_client, args=(conn, addr, device_index))
            client_thread.start()
    except KeyboardInterrupt:
        print("\nShutting down server.")
    finally:
        server_socket.close()
        cv2.destroyAllWindows()
        print("Server shut down.")

if __name__ == "__main__":
    main()
