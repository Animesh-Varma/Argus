import os
import shutil

# The root directory where recordings are stored.
OUTPUT_DIR = "output"
# The directory to move discarded recordings to.
DISCARD_DIR = "discarded"
# The name of the final video file.
FINAL_VIDEO_FILENAME = "recording.mp4"

def cleanup_empty_recordings():
    """
    Scans the output directory for incomplete recordings and moves them
    to a 'discarded' directory.
    """
    print(f"Starting cleanup of '{OUTPUT_DIR}' directory...")
    
    # Ensure the main output and discarded directories exist.
    if not os.path.isdir(OUTPUT_DIR):
        print(f"Error: Output directory '{OUTPUT_DIR}' not found.")
        return
    os.makedirs(DISCARD_DIR, exist_ok=True)

    moved_count = 0
    # The structure is output/YYYY-MM-DD/HH-MM-SS_IP
    
    # Iterate through date-stamped folders (e.g., '''2025-10-13''')
    for date_folder in os.listdir(OUTPUT_DIR):
        date_folder_path = os.path.join(OUTPUT_DIR, date_folder)
        if not os.path.isdir(date_folder_path):
            continue

        # Iterate through individual recording folders (e.g., '''01-19-07_127.0.0.1''')
        for rec_folder in os.listdir(date_folder_path):
            rec_folder_path = os.path.join(date_folder_path, rec_folder)
            if not os.path.isdir(rec_folder_path):
                continue

            final_video_path = os.path.join(rec_folder_path, FINAL_VIDEO_FILENAME)

            # Check if the final video file exists.
            if not os.path.isfile(final_video_path):
                try:
                    # Construct the destination path, preserving the date folder structure.
                    dest_date_folder = os.path.join(DISCARD_DIR, date_folder)
                    os.makedirs(dest_date_folder, exist_ok=True)
                    
                    dest_path = os.path.join(dest_date_folder, rec_folder)

                    print(f"Moving incomplete recording to: {dest_path}")
                    shutil.move(rec_folder_path, dest_path)
                    moved_count += 1
                except OSError as e:
                    print(f"Error moving directory {rec_folder_path}: {e}")

    if moved_count > 0:
        print(f"\nCleanup complete. Moved {moved_count} incomplete recording folder(s).")
    else:
        print("\nCleanup complete. No incomplete recordings found.")

if __name__ == "__main__":
    cleanup_empty_recordings()