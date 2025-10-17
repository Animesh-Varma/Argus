import os
import subprocess
import re
import sys

OUTPUT_DIR = 'output'

def find_available_dates():
    """Scans the output directory to find unique dates from recording folder names."""
    if not os.path.isdir(OUTPUT_DIR):
        return []
    
    # Regex to find YYYY-MM-DD in the folder name
    date_pattern = re.compile(r'_(\d{4}-\d{2}-\d{2})_')
    dates = set()
    
    for folder_name in os.listdir(OUTPUT_DIR):
        match = date_pattern.search(folder_name)
        if match:
            dates.add(match.group(1))
            
    return sorted(list(dates), reverse=True)

def find_videos_for_date(selected_date):
    """Finds all final_video.mp4 files for a given date, sorted chronologically."""
    video_files = []
    for folder_name in sorted(os.listdir(OUTPUT_DIR)):
        if selected_date in folder_name:
            video_path = os.path.join(OUTPUT_DIR, folder_name, 'final_video.mp4')
            if os.path.exists(video_path):
                video_files.append(os.path.abspath(video_path))
    return video_files

def main():
    """Main function to drive the CLI for merging videos."""
    available_dates = find_available_dates()
    if not available_dates:
        print(f"No recordings found in the '{OUTPUT_DIR}' directory.")
        return

    print("Available dates for merging:")
    for i, date in enumerate(available_dates):
        print(f"  {i + 1}: {date}")

    try:
        choice = int(input("\nEnter the number for the date you want to merge: "))
        if not (1 <= choice <= len(available_dates)):
            raise ValueError()
        selected_date = available_dates[choice - 1]
    except (ValueError, IndexError):
        print("Invalid choice. Please run the script again and enter a valid number.")
        return

    print(f"\nFinding all recordings for {selected_date}...")
    video_files = find_videos_for_date(selected_date)

    if not video_files:
        print(f"No completed video files found for {selected_date}.")
        return

    print(f"Found {len(video_files)} video(s) to merge.")

    # Create a temporary file list for ffmpeg
    list_filename = f"file_list_{selected_date}.txt"
    with open(list_filename, 'w') as f:
        for video_file in video_files:
            f.write(f"file '{video_file}'\n")

    output_filename = f"merged_{selected_date}.mp4"
    print(f"\nMerging videos into '{output_filename}'...")

    # Construct and run the ffmpeg command
    command = [
        'ffmpeg',
        '-f', 'concat',
        '-safe', '0',
        '-i', list_filename,
        '-c', 'copy',
        output_filename
    ]

    try:
        # Use capture_output to hide ffmpeg's verbose output unless there's an error
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        print("\nMerge successful!")
        print(f"Output file: {os.path.abspath(output_filename)}")
    except FileNotFoundError:
        print("\nERROR: ffmpeg command not found. Please ensure FFmpeg is installed and in your system's PATH.")
    except subprocess.CalledProcessError as e:
        print("\nAn error occurred during the ffmpeg merging process.")
        print("-------------------- FFMPEG ERROR ---------------------")
        print(e.stderr)
        print("-----------------------------------------------------")
    finally:
        # Clean up the temporary file list
        if os.path.exists(list_filename):
            os.remove(list_filename)

if __name__ == "__main__":
    main()
