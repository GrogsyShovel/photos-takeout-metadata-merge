
import os
from aux_functions import (
    progress_bar,
    search_media,
    extract_metadata,
    apply_metadata_and_fs_times,
    copy_media_to_output,
    sniff_type,
    find_live_video_partner,
)

EXCLUDE_JSON_BASE = {"metadata", "shared_album_comments"}


def get_sidecars(folder: str, edited_word: str):
    pairs = []
    for entry in os.scandir(folder):
        if entry.is_dir():
            pairs += get_sidecars(entry.path, edited_word)
        elif entry.is_file():
            base, ext = os.path.splitext(entry.name)
            if ext.lower() == ".json" and base not in EXCLUDE_JSON_BASE:
                media = search_media(folder, base, edited_word)
                pairs.append((entry.path, media))
    return pairs


def process_folder(root_folder: str, edited_word: str, out_folder: str):
    sidecars = get_sidecars(root_folder, edited_word)
    print("Total JSON sidecars:", len(sidecars))

    success = 0
    failed = 0
    linked_live = 0
    seen_live = set()

    for json_path, media_path in progress_bar(sidecars, prefix='Processing', suffix='done.'):
        if not media_path:
            print(f"\nMissing media for: {json_path}")
            failed += 1
            continue

        # Copy original bytes to normalized OUTPUT name
        out_media = copy_media_to_output(root_folder, out_folder, media_path)
        
        # Extract data
        meta = extract_metadata(json_path)

        # Lossless write + always set filesystem timestamps
        rc, log = apply_metadata_and_fs_times(out_media, meta)
        if rc != 0:
            # We won't stop processing just because the ExifTool write failed
            # (filesystem times were still set via fallback when possible).
            print(f"\nExifTool write failed for: {out_media}\n{log}")
        else:
            success += 1


        # If current item is an IMAGE, try to link a Live Photo video partner
        kind = sniff_type(media_path)
        if kind and kind[0] not in ("mov", "mp4"):
            # derive base stem from the original media filename
            stem, _ = os.path.splitext(os.path.basename(media_path))
            folder = os.path.dirname(media_path)
            live_path = find_live_video_partner(folder, stem)
            if live_path and live_path not in seen_live:
                # copy to normalized output and write date/gps using same meta
                out_live = copy_media_to_output(root_folder, out_folder, live_path)
                rc2, log2 = apply_metadata_and_fs_times(out_live, meta)
                if rc2 != 0:
                    print(f"\nLive video write failed for: {out_live}\n{log2}")
                else:
                    linked_live += 1
                    seen_live.add(live_path)


    print("\nLossless metadata merge complete.")
    print("Success:", success)
    print("Failed:", failed)
    print("Live videos linked:", linked_live)
