import socket
import cv2
import numpy as np
import pyaudio
import struct
import os
import sys
import wave
import subprocess
import threading
from datetime import datetime

# Streaming server configuration
STREAM_HOST = "0.0.0.0"
STREAM_PORT = 8000

# Audio/Video configuration
FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 48000
VIDEO_FPS = 20.0
CHUNK = int(RATE / VIDEO_FPS)

def list_audio_devices(p):
    print("Available audio output devices:")
    for i in range(p.get_device_count()):
        dev = p.get_device_info_by_index(i)
        if dev['maxOutputChannels'] > 0:
            print(f"  Index {dev['index']}: {dev['name']}")

def handle_client(conn, addr, mode, device_index):
    print(f"Streaming client connected from {addr}")

    p = None
    audio_stream = None
    wave_file = None
    video_writer = None
    output_folder = ""
    video_path = ""
    audio_path = ""

    try:
        if mode == 'stream':
            p = pyaudio.PyAudio()
            print(f"[{addr}] Attempting to start audio stream...")
            try:
                audio_stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True,
                                      frames_per_buffer=CHUNK, output_device_index=device_index)
                print(f"[{addr}] Audio stream opened successfully on device index {device_index}.")
            except Exception as e:
                print(f"[{addr}] Failed to open audio stream: {e}")
        else:  # record mode
            p = pyaudio.PyAudio()
            timestamp = datetime.now().strftime(f"recording_{addr[0]}_{addr[1]}_%Y-%m-%d_%H-%M-%S")
            output_folder = os.path.join("output", timestamp)
            os.makedirs(output_folder, exist_ok=True)
            print(f"[{addr}] Recording to folder: {output_folder}")

            audio_path = os.path.join(output_folder, "audio.wav")
            video_path = os.path.join(output_folder, "video.mp4")
            wave_file = wave.open(audio_path, 'wb')
            wave_file.setnchannels(CHANNELS)
            wave_file.setsampwidth(p.get_sample_size(FORMAT))
            wave_file.setframerate(RATE)

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

            if mode == 'stream':
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

            else:  # record mode
                if video_writer is None:
                    nparr = np.frombuffer(video_data, np.uint8)
                    first_frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if first_frame is not None:
                        height, width, _ = first_frame.shape
                        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                        video_writer = cv2.VideoWriter(video_path, fourcc, VIDEO_FPS, (width, height))
                        video_writer.write(first_frame)
                else:
                    nparr = np.frombuffer(video_data, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if frame is not None:
                        video_writer.write(frame)

                wave_file.writeframes(audio_frame_data)

    except (BrokenPipeError, ConnectionResetError):
        print(f"Client {addr} disconnected.")
    except Exception as e:
        print(f"Error with client {addr}: {e}")
    finally:
        if audio_stream:
            audio_stream.stop_stream()
            audio_stream.close()
        if wave_file:
            wave_file.close()
        if video_writer:
            video_writer.release()
        if p:
            p.terminate()
        conn.close()
        cv2.destroyWindow(f'Video from {addr}')
        print(f"Connection with {addr} closed.")

        if mode == 'record' and video_path and audio_path and os.path.exists(video_path) and os.path.exists(audio_path):
            print(f"[{addr}] Recording finished. Merging video and audio...")
            final_video_path = os.path.join(output_folder, "final_video.mp4")
            command = [
                'ffmpeg', '-y', '-i', video_path, '-i', audio_path,
                '-c:v', 'copy', '-c:a', 'aac', final_video_path
            ]
            try:
                subprocess.run(command, check=True, capture_output=True, text=True)
                print(f"[{addr}] Successfully merged to: {final_video_path}")
                os.remove(video_path)
                os.remove(audio_path)
            except FileNotFoundError:
                print(f"[{addr}] ERROR: ffmpeg not found. Please install FFmpeg.")
            except subprocess.CalledProcessError as e:
                print(f"[{addr}] Error during merging:\n{e.stderr}")

def main():
    mode = ''
    while mode not in ['stream', 'record']:
        mode = input("Enter mode ('stream' or 'record'): ").lower()

    device_index = -1
    if mode == 'stream':
        p = pyaudio.PyAudio()
        list_audio_devices(p)
        try:
            device_index = int(input("Enter the index of the audio device to use for all streams: "))
        except ValueError:
            print("Invalid input. Exiting.")
            p.terminate()
            return
        p.terminate()

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((STREAM_HOST, STREAM_PORT))
    server_socket.listen(5)  # Allow up to 5 pending connections
    print(f"Server listening on {STREAM_HOST}:{STREAM_PORT} in {mode} mode...")

    try:
        while True:
            conn, addr = server_socket.accept()
            client_thread = threading.Thread(target=handle_client, args=(conn, addr, mode, device_index))
            client_thread.start()
    except KeyboardInterrupt:
        print("\nShutting down server.")
    finally:
        server_socket.close()
        cv2.destroyAllWindows()
        print("Server shut down.")

if __name__ == "__main__":
    main()
