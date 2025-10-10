import socket
import cv2
import numpy as np
import pyaudio
import struct
import os
import wave
import subprocess
import threading
import shutil
from datetime import datetime

# --- Configuration ---
STREAM_HOST = "0.0.0.0"
STREAM_PORT = 8000

# --- V2 Protocol Tags ---
TAG_V1_BATCH = 0x10

# --- Media Configuration ---
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 48000
VIDEO_FPS = 20.0
CHUNK = int(RATE / VIDEO_FPS)

def handle_client(conn, addr):
    print(f"Recording client connected from {addr}")
    conn.settimeout(120.0)  # 2-minute timeout

    p = None
    wave_file = None
    video_writer = None
    output_folder = ""
    video_path = ""
    audio_path = ""

    try:
        p = pyaudio.PyAudio()
        timestamp = datetime.now().strftime(f"recording_{addr[0]}_{addr[1]}_%Y-%m-%d_%H-%M-%S")
        output_folder = os.path.join("output", timestamp)
        os.makedirs(output_folder, exist_ok=True)

        audio_path = os.path.join(output_folder, "audio.wav")
        video_path = os.path.join(output_folder, "video.mp4")
        wave_file = wave.open(audio_path, 'wb')
        wave_file.setnchannels(CHANNELS)
        wave_file.setsampwidth(p.get_sample_size(FORMAT))
        wave_file.setframerate(RATE)

        data = b""
        header_size = 5 # Tag (1) + Length (4)

        while True:
            # Receive the batch header
            while len(data) < header_size:
                packet = conn.recv(4 * 1024)
                if not packet: break
                data += packet
            if not packet: break

            tag, length = struct.unpack('>BL', data[:header_size])
            data = data[header_size:]

            if tag != TAG_V1_BATCH:
                print(f"[{addr}] Expected V1 batch tag, but got {tag}. Closing connection.")
                break

            # Receive the entire batch payload
            payload = b''
            while len(payload) < length:
                payload += conn.recv(length - len(payload))
            
            # Unpack the batch
            num_frames = struct.unpack(">I", payload[:4])[0]
            payload = payload[4:]
            print(f"[{addr}] Received a batch of {num_frames} frames.")

            for i in range(num_frames):
                vid_len, aud_len = struct.unpack(">LL", payload[:16])
                payload = payload[16:]

                video_data = payload[:vid_len]
                audio_data = payload[vid_len : vid_len + aud_len]
                payload = payload[vid_len + aud_len:]

                if video_writer is None:
                    print(f"[{addr}] Starting recording to folder: {output_folder}")
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

                wave_file.writeframes(audio_data)

    except socket.timeout:
        print(f"Client {addr} timed out. Disconnecting.")
    except (BrokenPipeError, ConnectionResetError):
        print(f"Client {addr} disconnected.")
    except Exception as e:
        print(f"Error with client {addr}: {e}")
    finally:
        if wave_file: wave_file.close()
        if video_writer: video_writer.release()
        if p: p.terminate()
        conn.close()
        print(f"Connection with {addr} closed.")

        if video_writer is not None:
            print(f"[{addr}] Merging video and audio...")
            final_video_path = os.path.join(output_folder, "final_video.mp4")
            command = [
                'ffmpeg', '-y', '-i', video_path, '-i', audio_path,
                '-c:v', 'copy', '-c:a', 'aac', '-shortest', final_video_path
            ]
            try:
                subprocess.run(command, check=True, capture_output=True, text=True)
                print(f"[{addr}] Successfully merged to: {final_video_path}")
                os.remove(video_path)
                os.remove(audio_path)
            except FileNotFoundError:
                print(f"[{addr}] ERROR: ffmpeg not found.")
            except subprocess.CalledProcessError as e:
                print(f"[{addr}] Error during merging:\n{e.stderr}")
        elif os.path.exists(output_folder):
            print(f"[{addr}] No video frames received. Deleting empty directory.")
            shutil.rmtree(output_folder, ignore_errors=True)

def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((STREAM_HOST, STREAM_PORT))
    server_socket.listen(20)
    print(f"Recording server listening on {STREAM_HOST}:{STREAM_PORT}...")

    try:
        while True:
            conn, addr = server_socket.accept()
            client_thread = threading.Thread(target=handle_client, args=(conn, addr))
            client_thread.start()
    except KeyboardInterrupt:
        print("\nShutting down server.")
    finally:
        server_socket.close()
        print("Server shut down.")

if __name__ == "__main__":
    main()