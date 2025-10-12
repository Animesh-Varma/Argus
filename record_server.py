import socket
import cv2
import numpy as np
import struct
import os
import wave
import subprocess
import threading
import shutil
from datetime import datetime

# Server configuration
STREAM_HOST = "0.0.0.0"
STREAM_PORT = 8000

# Audio/Video configuration
CHANNELS = 1
RATE = 48000
VIDEO_FPS = 20.0
CHUNK = int(RATE / VIDEO_FPS)

def handle_client(conn, addr):
    print(f"Recording client connected from {addr}")
    conn.settimeout(120.0)  # Set 2-minute timeout for client inactivity

    now = datetime.now()
    wave_file = None
    video_writer = None
    output_folder = ""
    video_path = ""
    audio_path = ""

    try:
        date_folder = os.path.join("output", now.strftime("%Y-%m-%d"))
        recording_folder_name = now.strftime(f"%H-%M-%S_{addr[0]}")
        output_folder = os.path.join(date_folder, recording_folder_name)
        os.makedirs(output_folder, exist_ok=True)

        audio_path = os.path.join(output_folder, "audio.wav")
        video_path = os.path.join(output_folder, "video.ts")
        wave_file = wave.open(audio_path, 'wb')
        wave_file.setnchannels(CHANNELS)
        wave_file.setsampwidth(2) # Hardcoded for 16-bit audio
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

            if video_writer is None:
                print(f"[{addr}] Starting recording to folder: {output_folder}")
                nparr = np.frombuffer(video_data, np.uint8)
                first_frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if first_frame is not None:
                    height, width, _ = first_frame.shape
                    fourcc = cv2.VideoWriter_fourcc(*'H264')
                    video_writer = cv2.VideoWriter(video_path, fourcc, VIDEO_FPS, (width, height))
                    video_writer.write(first_frame)
            else:
                nparr = np.frombuffer(video_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if frame is not None:
                    video_writer.write(frame)

            wave_file.writeframes(audio_frame_data)

    except socket.timeout:
        print(f"Client {addr} timed out after 120 seconds of inactivity. Disconnecting.")
    except (BrokenPipeError, ConnectionResetError):
        print(f"Client {addr} disconnected.")
    except Exception as e:
        print(f"Error with client {addr}: {e}")
    finally:
        # Close all resources
        if wave_file:
            wave_file.close()
        if video_writer:
            video_writer.release()
        conn.close()
        print(f"Connection with {addr} closed.")

        # --- Automated Merging & Cleanup ---
        if video_writer is not None:
            print(f"[{addr}] Recording finished. Merging video and audio...")
            final_video_path = os.path.join(output_folder, "recording.mp4")
            command = [
                'ffmpeg', '-y',
                '-r', str(VIDEO_FPS),  # Treat input as constant frame rate
                '-i', video_path,
                '-i', audio_path,
                '-c:v', 'libx264',    # Re-encode video with H.264
                '-pix_fmt', 'yuv420p', # Standard pixel format for compatibility
                '-c:a', 'aac',
                '-shortest', final_video_path
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
        elif os.path.exists(output_folder):
            print(f"[{addr}] No video frames received. Deleting empty recording directory: {output_folder}")
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
