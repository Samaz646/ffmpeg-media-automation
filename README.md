# FFmpeg Media Automation

## Overview
This script automates video processing with `ffmpeg` and `ffprobe`.

It monitors an input folder, analyzes video and audio streams, and decides whether a file can be moved directly to the output directory or needs transcoding first.

The script is designed as a queue-based processing loop for controlled media workflows.

---

## Features

- Automatic video stream analysis using `ffprobe`
- Conditional transcoding based on codec, resolution, and field order
- Deinterlacing for interlaced sources
- Upscaling to target width when required
- Audio conversion to AC3 when needed
- Loudness normalization for non-AC3 audio tracks
- Queue-style processing (one file at a time)
- Low-priority ffmpeg execution
- Daily log files
- Separate input, temp, and output directories

---

## How It Works

For each file in the input directory, the script:

1. checks whether the file is currently free for processing
2. moves it to a temporary working directory
3. analyzes video and audio streams with `ffprobe`
4. checks whether the file is already compatible
5. either:
   - moves the file directly to the output directory, or
   - transcodes it to MP4 using `ffmpeg`
6. cleans up temporary files

The script processes files sequentially and waits between checks.

---

## Requirements

- Windows
- Python 3.x
- `ffmpeg`
- `ffprobe`
- `psutil`

---

## Configuration

Main settings in the script:

```python
BASE_DIR = r"C:\media-automation"
CHECK_INTERVAL = 60
TARGET_WIDTH = 1920
CRF = "25"
PRESET = "slow"
AUDIO_BITRATE = "160k"
