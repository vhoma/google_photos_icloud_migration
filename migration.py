import os
import shutil
import subprocess
import imghdr
import json
from datetime import datetime
from pathlib import Path

from logger import get_logger
logger = get_logger()

MEDIA_EXTS = {'.jpg', '.jpeg', '.png', '.heic', '.mov', '.mp4'}
JSON_SUFFIXES = [".supplemental-metadata.json", ".suppl.json"]


def rename_file(f_data, new_name):
    # rename media file
    orig_name = f_data['path'].name
    new_path = f_data['path'].with_name(new_name)
    f_data['path'] = f_data['path'].rename(new_path)

    # rename json file
    if f_data.get('json_path'):
        new_json_path = f_data['json_path'].with_name(
            f_data['json_path'].name.replace(orig_name, new_name)
        )
        f_data['json_path'] = f_data['json_path'].rename(new_json_path)

    logger.info(f"Renamed {f_data['path']} → {new_path.name}")


def fix_wrong_extension(f_data):
    f_path = f_data['path']
    kind = imghdr.what(f_path)
    if kind:
        expected_ext = f".{kind}"
        actual_ext = f_path.suffix.lower()
        if expected_ext != actual_ext:
            new_name = f_path.with_suffix(expected_ext)
            rename_file(f_data, new_name)


def scan_files(input_dir):
    media_files = {}
    json_files = {}

    # walk through all files
    for root, _, files in os.walk(input_dir):
        for file in files:
            path = Path(root) / file
            if path.suffix.lower() in MEDIA_EXTS:
                media_files[path.name] = {"path": path}
            else:
                for suffix in JSON_SUFFIXES:
                    if file.endswith(suffix):
                        base_name = file.replace(suffix, '')
                        json_files[base_name] = path
                        break

    # match json files with media files
    res = []
    for media_name in media_files:
        media_file_data = media_files[media_name]
        media_file_data["name"] = media_name
        if media_name in json_files:
            media_file_data["json_path"] = json_files[media_name]
        res.append(media_file_data)

    return res


def apply_json_metadata(media_path, json_path):
    if not json_path:
        raise Exception(f"No metadata to apply to {media_path}")

    # read metadata file
    with open(json_path, 'r') as f:
        metadata = json.load(f)
    photo_taken_time = int(metadata['photoTakenTime']['timestamp'])
    date_time_original = datetime.fromtimestamp(photo_taken_time).strftime("%Y:%m:%d %H:%M:%S")

    try:
        subprocess.run([
            "exiftool",
            f"-json={json_path}",
            f'-DateTimeOriginal="{date_time_original}"',
            "-overwrite_original",
            str(media_path)
        ], check=True)
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to update metadata for {media_path}: {e}")


def copy_to_output(f_data, output_dir):
    # copy media path
    dest_path = output_dir / f_data['path'].name
    if dest_path.exists():
        raise Exception(f"Destination path already exists: {dest_path}")
    shutil.copy2(f_data['path'], dest_path)

    # copy json path
    dest_json_path = output_dir / "metadata" / f_data["json_path"]
    if dest_json_path.exists():
        raise Exception(f"Destination JSON path already exists: {dest_path}")
    shutil.copy2(f_data['json_path'], dest_json_path)


def process_media_file(f_data, output_dir):
    fix_wrong_extension(f_data)
    apply_json_metadata(f_data['path'], f_data.get('json_path'))
    copy_to_output(f_data, output_dir)
    logger.info(f"Done with file {f_data['path']}")


def main(input_dir, output_dir):
    input_dir = Path(input_dir).resolve()
    output_dir = Path(output_dir).resolve()

    logger.info(f"Scanning folders under: {input_dir}\n")
    media_files = scan_files(input_dir)

    # process files one by one
    files_count = len(media_files)
    counter = 0
    for f_data in media_files:
        counter += 1
        logger.info(f"Processing {counter} of {files_count} files...")
        process_media_file(f_data, output_dir)


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        logger.info("Usage: python3 apply_metadata.py <input_dir> <output_dir>")
    else:
        main(sys.argv[1], sys.argv[2])
