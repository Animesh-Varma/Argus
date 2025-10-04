import socket
import threading
import cv2
import pyaudio
import struct

# Streaming server configuration
STREAM_HOST = "0.0.0.0"
STREAM_PORT = 8000

# Audio configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024

def main():
    """Starts the streaming server."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((STREAM_HOST, STREAM_PORT))
    server_socket.listen(1)
    print(f"Streaming server listening on {STREAM_HOST}:{STREAM_PORT}...")

    conn, addr = server_socket.accept()
    print(f"Streaming client connected from {addr}")

    audio_stream = pyaudio.PyAudio().open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True, frames_per_buffer=CHUNK)

    data = b""
    payload_size = struct.calcsize(">L")

    try:
        while True:
            while len(data) < payload_size:
                packet = conn.recv(4 * 1024)
                if not packet:
                    break
                data += packet
            
            if not data:
                break

            packed_msg_size = data[:payload_size]
            data = data[payload_size:]
            msg_size = struct.unpack(">L", packed_msg_size)[0]

            while len(data) < msg_size:
                data += conn.recv(4 * 1024)

            frame_data = data[:msg_size]
            data = data[msg_size:]

            # Extract video and audio data
            video_data = frame_data[:-CHUNK]
            audio_frame_data = frame_data[-CHUNK:]

            # Display video
            frame = cv2.imdecode(cv2.imdecode(video_data, 1), 1)
            cv2.imshow('Video', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            # Play audio
            audio_stream.write(audio_frame_data)

    except (BrokenPipeError, ConnectionResetError):
        print("Client disconnected.")
    except KeyboardInterrupt:
        print("Stopping server.")
    except Exception as e:
        print(f"Streaming error: {e}")
    finally:
        audio_stream.stop_stream()
        audio_stream.close()
        pyaudio.PyAudio().terminate()
        conn.close()
        server_socket.close()
        cv2.destroyAllWindows()
        print("Streaming stopped.")

if __name__ == "__main__":
    main()