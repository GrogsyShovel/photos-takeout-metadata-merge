# Photos Takeout Metadata Merge

This tool restores original timestamps and GPS data to photos and videos exported from Google Takeout. It reads each photo/video’s adjacent JSON sidecar, copies the media to a normalized output path, and writes metadata losslessly using ExifTool.

Inspired by [google-metadata-matcher](https://github.com/Greegko/google-metadata-matcher) which was inspired by [GooglePhotosMatcher](https://github.com/anderbggo/GooglePhotosMatcher).

***

## Features

*   **Lossless metadata writes with ExifTool**:
    *   Images: `DateTimeOriginal`, `CreateDate`, `ModifyDate`, `GPSLatitude`, `GPSLongitude`, `GPSAltitude`.
    *   Videos (QuickTime/MP4): same core date tags; uses `-api QuickTimeUTC=1` for proper UTC handling.
    *   Filesystem timestamps: `FileCreateDate` and `FileModifyDate` copied from `CreateDate`.

*   **Smart JSON matching**  
    Finds the correct photo/video even when JSON names are irregular:
    *   `.supplemental-metadata.json`, `.suppl.json`, `.supp.json`, numbered `(...).json`.
    *   JSON basenames with extra dots or trailing dots (`IMG_3063..json`).
    *   JSON basenames that lack a media extension (e.g., `IMG_3063.json`).
    *   Compound stems (e.g., `IMG_3063.h.json` → `IMG_3063.h.jpeg`).

*   **Normalization**  
    Copies media to output with corrected names:
    *   Fix wrong/missing extensions (`.png` mislabeled but actually JPEG).
    *   Collapse duplicate/misaligned extensions (`.heic.jpeg` → `.jpg`, `.heic.heic` → `.heic`).
    *   Add extensions to extensionless Live Photo videos (`IMG_0052` → `IMG_0052.mov` or `.mp4`).

***

## Requirements

*   **Python 3.8+**
*   **ExifTool** installed and on your system `PATH`:
    *   macOS: `brew install exiftool`
    *   Linux (Debian/Ubuntu): `sudo apt install libimage-exiftool-perl`
    *   Windows: download ExifTool and rename `exiftool(-k).exe` → `exiftool.exe`, then add to `PATH`.

> No additional Python packages required.

***

## Installation

1.  Place the three files in a folder:
    *   `aux_functions.py`
    *   `process_folder.py`
    *   `merge_metadata.py`

2.  Ensure ExifTool is installed and accessible from your terminal.

***

## Quick Start

```bash
python merge_metadata.py "/path/to/Google Photos" "/path/to/output" --edited_word edited
```

*   `source_folder`: the root of your unzipped Google Takeout (e.g., `Google Photos`).
*   `output_folder`: destination for normalized copies with restored metadata.
*   `--edited_word`: the localized/actual suffix Google uses for edited photos (default: `edited`; use `EDITED` if your export uses uppercase).

**What you’ll see:**

*   A progress bar.
*   A summary:
    *   `Success: N` — files successfully processed.
    *   `Failed: M` — files that couldn’t be matched or written.
    *   `Live videos linked: K` — paired Live Photo videos updated.

***

## Program Flow

1.  **Discover sidecars**: Recursively finds all `*.json` (excluding a literal `metadata.json` or `shared_album_comments.json`).
2.  **Match JSON with media**: Robust resolver builds candidates across common media extensions, supports edited/duplicate naming, case-insensitive fallback, and a final prefix scan + header sniff.
3.  **Normalize output name**: Based on the media’s actual header, chooses the correct extension and collapses chained/misaligned extensions.
4.  **Copy**: Copies the original file to the normalized output path.
5.  **Write metadata losslessly**: Calls ExifTool to update EXIF/QuickTime tags and filesystem dates.
6.  **Live Photo linking**: For image JSONs, finds the partner MOV/MP4 by stem, copies to normalized output, and writes matching dates/GPS.

***

## Normalization Rules

*   **Content-first**: Detects actual type by file header, not the filename.
*   **Extensions** (in match order):
    *   JPEG: `.jpg`
    *   PNG: `.png`
    *   TIFF: `.tif`
    *   HEIC: `.heic`
    *   Videos: `.mov` or `.mp4` (QuickTime/ISO-BMFF brands determine this)
*   **Duplicates**: Avoids collisions by appending `(1)`, etc. when necessary.

***

## Live Photo Linking

*   When an image is processed, the program looks for the companion video in the same folder:
    *   Exact stem with no extension: `IMG_0052`
    *   Or `IMG_0052.mov/.mp4/.m4v` (case-insensitive).
*   It confirms the match by header sniffing (MOV/MP4), then:
    *   Copies the video to normalized output (e.g., `IMG_0052.mov`).
    *   Writes the same timestamp/GPS to the video (lossless).

***

## Supported Formats

**Photos**: JPEG/JPG, PNG, TIFF/TIF, HEIC  
**Videos**: MOV/MP4 (and M4V for detection) \[including Apple Live Photos\]

***

## Options & Customization

*   `--edited_word <word>`  
    Customize the edited suffix. Common variants include `edited`, `EDITED`, localized words, or other app-specific markers.

***

## FAQ

**Q: Is this truly lossless?**  
A: Yes. ExifTool writes metadata blocks/atoms and file timestamps. No image/audio re-encoding occurs.

**Q: Does this change my source files?**  
A: No. The program copies to `output_folder` with normalized names and writes metadata there.

**Q: Why do some JSONs not match anything?**  
A: Takeout occasionally produces irregular sidecar names or splits media across folders. The matcher handles many cases; feel free to share examples if you find new patterns.

***

## Contributing

*   Found another odd naming convention? Open an issue or send a sample name pattern and desired match.
*   PRs welcome.

***

## Yes,

This project was written mostly by AI. Thanks, AI.
