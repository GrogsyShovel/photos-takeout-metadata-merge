
import os
import re
import json
import shutil
import subprocess
from datetime import datetime
from typing import Optional, List, Tuple

# ------------------------------------------------------------
# ASCII-only, single-line progress bar (no ANSI escape codes)
# ------------------------------------------------------------


def progress_bar(iterable, prefix='', suffix='', decimals=1, length=40, fill='█'):
    items = list(iterable)
    total = len(items)
    def render(i):
        if total == 0:
            percent = f"{100:.{decimals}f}"
            filled = length
        else:
            percent = f"{(100 * i / float(total)):.{decimals}f}"
            filled = int(length * i // total)
        bar = fill * filled + '-' * (length - filled)
        print(f"\r{prefix} [{bar}] {percent}% {suffix}", end='', flush=True)
    render(0)
    for i, item in enumerate(items, 1):
        yield item
        render(i)
    print()


# ------------------------------------------------------------
# Google Takeout JSON helpers
# ------------------------------------------------------------

# Catch more Takeout sidecar variants: supplemental-metadata, suppl, supp, and stray counters
SIDE_SUFFIX_RE = re.compile(
    r"\.(supplemental\-metadata|supp\-metadata|suppl|supp)(\(\d+\))?$",
    re.IGNORECASE
)

def sanitize_json_title(base: str) -> str:
    """
    Make the JSON base safer for matching:
      - strip Takeout sidecar suffixes (.supplemental-metadata / .suppl / .supp)
      - collapse multiple dots
      - strip trailing dots
      - keep only ASCII-safe punctuation (handled by fix_title)
    """
    s = strip_json_suffix(fix_title(base))
    s = re.sub(r"\.+", ".", s)   # collapse ".." -> "."
    s = s.rstrip(".")            # remove trailing dot(s)
    return s

def strip_json_suffix(base: str) -> str:
    return SIDE_SUFFIX_RE.sub('', base)

# ------------------------------------------------------------
# Magic sniffers (hex-safe)
# ------------------------------------------------------------
PNG_SIG   = bytes.fromhex("89504e470d0a1a0a")
TIFF_LE   = bytes.fromhex("49492a00")  
TIFF_BE   = bytes.fromhex("4d4d002a")  
FTYP      = b"ftyp"
JPEG_SOI  = bytes.fromhex("ffd8")
ISO_BRANDS_HEIC = {b"heic", b"heix", b"heif", b"mif1"}
ISO_BRANDS_MOV  = {b"qt  ", b"pnot"}
ISO_BRANDS_MP4  = {b"isom", b"mp41", b"mp42", b"avc1"}


def sniff_type(path: str) -> Optional[Tuple[str, str]]:
    try:
        with open(path, 'rb') as f:
            header = f.read(32)
    except Exception:
        return None
    if not header:
        return None
    if header[:2] == JPEG_SOI:
        return ("jpeg", "jpg")
    if header[:8] == PNG_SIG:
        return ("png", "png")
    if header[:4] in (TIFF_LE, TIFF_BE):
        return ("tiff", "tif")
    if len(header) >= 12 and header[4:8] == FTYP:
        brand = header[8:12]
        if brand in ISO_BRANDS_HEIC:
            return ("heic", "heic")
        if brand in ISO_BRANDS_MOV:
            return ("mov", "mov")
        return ("mp4", "mp4")
    return None

# ------------------------------------------------------------
# Filename normalization helpers
# ------------------------------------------------------------

def collapse_extensions(name: str) -> Tuple[str, str]:
    base = name
    last_ext = ''
    while True:
        b, e = os.path.splitext(base)
        if e:
            base = b
            last_ext = e
            continue
        break
    return base, last_ext

def fix_title(title: str) -> str:
    cleaned = str(title)
    for ch in ["%","<",">","=",":","?","¿","*","#","&","{","}","\n","@","!","+","\n","\"","'"]:
        cleaned = cleaned.replace(ch, "")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned

# ------------------------------------------------------------
# Media resolver (JSON -> actual file)
# ------------------------------------------------------------

def search_media(path: str, title: str, edited_word: str) -> Optional[str]:
    """
    Robust resolver for weird JSON basenames:
      - normalizes the title
      - tries common media extensions (jpeg/jpg/heic/png/tiff; optionally mov/mp4/m4v)
      - supports edited suffix patterns and (n) duplicates
      - case-insensitive matching fallback
      - final prefix scan + header sniff
    """
    title = sanitize_json_title(title)

    # Split, but DO NOT trust this "ext" as the real media ext
    file_name, json_ext = os.path.splitext(title)

    # Known media extensions to try (you can drop videos if you only care about photos)
    media_exts = ["heic", "jpg", "jpeg", "png", "tif", "tiff", "mov", "mp4", "m4v"]

    # Build candidate names across all media_exts
    candidates: List[str] = []
    def add_variants(stem: str, ext: str):
        dotext = "." + ext
        candidates.extend([
            stem + dotext,                          # plain
            f"{stem}-{edited_word}{dotext}",        # -edited
            f"{stem}-{edited_word.upper()}{dotext}",# -EDITED
            f"{stem} - {edited_word}{dotext}",      # " - edited"
            f"{stem} ({edited_word}){dotext}",      # " (edited)"
            f"{stem}(1){dotext}",                   # duplicate (1)
            f"{stem} (1){dotext}",                  # " (1)"
        ])
        for n in range(2, 21):
            candidates.append(f"{stem}({n}){dotext}")
            candidates.append(f"{stem} ({n}){dotext}")

    # First: exact "stem" from sanitized title
    for ext in media_exts:
        add_variants(file_name, ext)

    # Also try the raw sanitized title as a whole + ext list if the stem itself includes a sub-ext (e.g., "...IMG_3063.h")
    # This catches cases like "....IMG_3063.h.json" → "...IMG_3063.h.jpeg"
    if json_ext and json_ext[1:].lower() not in media_exts:
        for ext in media_exts:
            add_variants(title, ext)

    # Fast path: exact case on disk
    for cand in candidates:
        fp = os.path.join(path, cand)
        if os.path.exists(fp):
            return fp

    # Case-insensitive map of directory files
    try:
        entries = {e.name.casefold(): e.path for e in os.scandir(path) if e.is_file()}
    except FileNotFoundError:
        return None

    for cand in candidates:
        p = entries.get(cand.casefold())
        if p:
            return p

    # Fallback: prefix scan + header sniff (handles missing-ext JSON like "...97.json")
    base_cf = file_name.casefold()
    for e in os.scandir(path):
        if not e.is_file():
            continue
        name_cf = e.name.casefold()
        if name_cf.startswith(base_cf):
            t = sniff_type(e.path)
            if t and t[0] in ("jpeg", "png", "tiff", "heic", "mov", "mp4"):
                return e.path

    # Not found
    return None

# ------------------------------------------------------------
# Live Photo partner finder (image -> video)
# ------------------------------------------------------------

def find_live_video_partner(folder: str, image_basestem: str) -> Optional[str]:
    """
    Try to locate a Live Photo video partner next to an image.
    We consider:
      - extensionless file with the same stem (e.g., 'IMG_0052')
      - typical video extensions: .mov/.MOV/.mp4/.MP4/.m4v
    We confirm by sniffing the header.
    Returns the absolute path to the partner video, or None.
    """
    candidates = [
        os.path.join(folder, image_basestem),
        os.path.join(folder, image_basestem + ".mov"),
        os.path.join(folder, image_basestem + ".MOV"),
        os.path.join(folder, image_basestem + ".mp4"),
        os.path.join(folder, image_basestem + ".MP4"),
        os.path.join(folder, image_basestem + ".m4v"),
    ]
    for c in candidates:
        if os.path.exists(c):
            t = sniff_type(c)
            if t and t[0] in ("mov", "mp4"):
                return c
    # Fallback: scan directory for files that start with stem
    try:
        for e in os.scandir(folder):
            if not e.is_file():
                continue
            name = e.name
            if name == image_basestem or name.startswith(image_basestem + "."):
                t = sniff_type(e.path)
                if t and t[0] in ("mov", "mp4"):
                    return e.path
    except FileNotFoundError:
        pass
    return None

# ------------------------------------------------------------
# ExifTool writing (lossless)
# ------------------------------------------------------------

def extract_metadata(json_path: str) -> dict:
    with open(json_path, encoding='utf-8') as f:
        j = json.load(f)
    ts = None
    if isinstance(j.get('photoTakenTime'), dict) and j['photoTakenTime'].get('timestamp'):
        try:
            ts = int(j['photoTakenTime']['timestamp'])
        except Exception:
            ts = None
    if ts is None and isinstance(j.get('creationTime'), dict) and j['creationTime'].get('timestamp'):
        try:
            ts = int(j['creationTime']['timestamp'])
        except Exception:
            ts = None
    geo = j.get('geoData', {}) or {}
    lat = geo.get('latitude')
    lon = geo.get('longitude')
    alt = geo.get('altitude')
    return {
        'timestamp': ts,
        'latitude': lat,
        'longitude': lon,
        'altitude': alt,
    }

def fmt_ts(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime('%Y:%m:%d %H:%M:%S')

def build_exiftool_args(target_path: str, meta: dict) -> List[str]:
    ts = meta.get('timestamp')
    lat = meta.get('latitude')
    lon = meta.get('longitude')
    alt = meta.get('altitude')
    args: List[str] = ["-overwrite_original"]
    if ts:
        dt = fmt_ts(ts)
        args += [
            f"-DateTimeOriginal={dt}",
            f"-CreateDate={dt}",
            f"-ModifyDate={dt}",
            "-P",
            "-FileCreateDate<CreateDate",
            "-FileModifyDate<ModifyDate",
        ]
    def valid_num(x):
        try:
            return x is not None and str(x) != ''
        except Exception:
            return False
    if valid_num(lat) and valid_num(lon):
        args += [f"-GPSLatitude={lat}", f"-GPSLongitude={lon}"]
    if valid_num(alt):
        args += [f"-GPSAltitude={alt}"]
    kind = sniff_type(target_path)
    if kind and kind[0] in ("mov", "mp4"):
        args = ["-api", "QuickTimeUTC=1"] + args
    return args


def run_exiftool(args: List[str], target: str) -> Tuple[int, str]:
    cmd = ["exiftool"] + args + [target]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
        return p.returncode, (p.stdout + p.stderr)
    except FileNotFoundError:
        return 127, "exiftool not found. Install it and ensure it's in PATH."


# ------------------------------------------------------------
# Filesystem timestamp setter (safe fallback)
# ------------------------------------------------------------
def set_fs_times_fallback(path: str, timestamp: int) -> None:
    """
    Fallback to set filesystem Modified/Access times via os.utime.
    Note: true 'Created' time is platform-dependent; ExifTool sets it when possible.
    """
    try:
        dt = datetime.fromtimestamp(timestamp)
        mod = dt.timestamp()
        # atime = mod as well (to keep them aligned)
        os.utime(path, (mod, mod))
    except Exception:
        pass

# ------------------------------------------------------------
# Apply metadata + filesystem timestamps (one-stop)
# ------------------------------------------------------------
def apply_metadata_and_fs_times(target_path: str, meta: dict) -> Tuple[int, str]:
    """
    1) Build and run ExifTool write (lossless).
    2) Ensure filesystem timestamps match the photo/video timestamp.
       - ExifTool args already include FileCreateDate/FileModifyDate.
       - If ExifTool fails or the tag isn't applied, we still set via os.utime fallback.
    Returns: (rc, combined_log)
    """
    args = build_exiftool_args(target_path, meta)
    rc, log = run_exiftool(args, target_path)

    # Always set filesystem timestamps if we have a JSON timestamp
    ts = meta.get("timestamp")
    if ts:
        # Even if ExifTool succeeded, keep a fallback write to be extra-safe on PNG/edge cases
        set_fs_times_fallback(target_path, ts)

    return rc, log


# ------------------------------------------------------------
# Output-only normalization and copy
# ------------------------------------------------------------

def compute_normalized_output(root_folder: str, out_folder: str, media_path: str) -> str:
    src_dir = os.path.dirname(media_path)
    rel_dir = os.path.relpath(src_dir, root_folder)
    base_name = os.path.basename(media_path)
    base, last_ext = collapse_extensions(base_name)
    sniff = sniff_type(media_path)
    if sniff:
        _, target_ext = sniff
    else:
        target_ext = last_ext[1:].lower() if last_ext else ''
    desired_name = f"{base}.{target_ext}" if target_ext else base
    out_dir = os.path.join(out_folder, rel_dir)
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, desired_name)
    if os.path.exists(dst):
        stem, ext = os.path.splitext(desired_name)
        n = 1
        candidate = os.path.join(out_dir, f"{stem}({n}){ext}")
        while os.path.exists(candidate):
            n += 1
            candidate = os.path.join(out_dir, f"{stem}({n}){ext}")
        dst = candidate
    return dst


def copy_media_to_output(root_folder: str, out_folder: str, media_path: str) -> str:
    dst = compute_normalized_output(root_folder, out_folder, media_path)
    if not os.path.exists(dst):
        shutil.copy2(media_path, dst)
    return dst
