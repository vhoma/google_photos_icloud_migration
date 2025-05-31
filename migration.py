import os
import shutil
import subprocess
import imghdr
import mimetypes
from pathlib import Path
from collections import defaultdict

MEDIA_EXTS = {'.jpg', '.jpeg', '.png', '.heic', '.mov', '.mp4'}
JSON_SUFFIXES = [".supplemental-metadata.json", ".suppl.json"]

def fix_wrong_extension(media_path):
    kind = imghdr.what(media_path)
    if kind:
        expected_ext = f".{kind}"
        actual_ext = media_path.suffix.lower()
        if expected_ext != actual_ext:
            new_path = media_path.with_suffix(expected_ext)
            media_path.rename(new_path)
            print(f"Renamed {media_path.name} → {new_path.name}")
            return new_path, True
    return media_path, False

def scan_files(input_dir):
    media_files = {}
    json_files = defaultdict(list)

    for root, _, files in os.walk(input_dir):
        for file in files:
            path = Path(root) / file
            if path.suffix.lower() in MEDIA_EXTS:
                media_files[path.name] = path
            else:
                for suffix in JSON_SUFFIXES:
                    if file.endswith(suffix):
                        base_name = file.replace(suffix, '')
                        json_files[base_name].append(path)
                        break

    return media_files, json_files

def apply_json_metadata(media_path, json_path):
    try:
        subprocess.run([
            "exiftool",
            f"-json={json_path}",
            "-overwrite_original",
            str(media_path)
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to update metadata for {media_path}: {e}")

def copy_to_output(media_path, output_dir):
    dest_path = output_dir / media_path.name

    # Handle name collisions
    counter = 1
    while dest_path.exists():
        stem = media_path.stem
        suffix = media_path.suffix
        dest_path = output_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    shutil.copy2(media_path, dest_path)

def main(input_dir, output_dir):
    input_dir = Path(input_dir).resolve()
    output_dir = Path(output_dir).resolve()
    print(f"Scanning folders under: {input_dir}\n")

    media_files, json_files = scan_files(input_dir)

    for name, media_path in media_files.items():
        json_path = None
        original_name = media_path.name
        media_path, renamed = fix_wrong_extension(media_path)
        name = media_path.name

        # If we renamed the media file, also rename the corresponding JSON if found
        if renamed:
            for suffix in JSON_SUFFIXES:
                json_old_name = original_name + suffix
                if json_old_name in json_files:
                    old_json_path = json_files[json_old_name][0]
                    new_json_path = old_json_path.with_name(name + suffix)
                    old_json_path.rename(new_json_path)
                    print(f"Renamed JSON {old_json_path.name} → {new_json_path.name}")

                    # Update index
                    json_files[name] = [new_json_path]
                    del json_files[json_old_name]
                    break

        if name in json_files:
            json_path = json_files[name][0]
            apply_json_metadata(media_path, json_path)
        else:
            print(f"No JSON metadata found for: {name}")


        copy_to_output(media_path, output_dir)

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python3 apply_metadata.py <input_dir> <output_dir>")
    else:
        main(sys.argv[1], sys.argv[2])
