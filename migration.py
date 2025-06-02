import os
import shutil
import subprocess
import imghdr
import json
import re
from datetime import datetime
from pathlib import Path

from logger import get_logger
logger = get_logger()

MEDIA_EXTS = {'.jpg', '.jpeg', '.png', '.heic', '.mov', '.mp4'}
JSON_SUFFIXES = [
    '.supplemental-metadata.json', 
    '.supplemental-metadat.json', 
    '.supplemental-metada.json', 
    '.supplemental-metad.json', 
    '.supplemental-meta.json', 
    '.supplemental-met.json', 
    '.supplemental-me.json', 
    '.supplemental-m.json', 
    '.supplemental-.json', 
    '.supplemental.json', 
    '.supplementa.json', 
    '.supplement.json', 
    '.supplemen.json', 
    '.suppleme.json', 
    '.supplem.json', 
    '.supple.json', 
    '.suppl.json',
    '.supp.json',
    '.sup.json',
    '.su.json',
    '.s.json',
    '..json',
    '.json',
]
DEFAULT_JSON_SUF = '.suppl.json',


def get_json_name_from_media_name(name):
    # option 1: /some/path/<media_name>.supplemental-metadata.json ; return <media_name>
    # option 2: /some/path/<media_name>.suppl.json ; return <media_name>
    # option 3: /some/path/<media_name>.supplemental-metadata(2).json ; return <media_name>(2).<ext>
    ugly_suffix_list = re.findall(r'[^()]*(\([0-9]+\))\..+', name)
    if ugly_suffix_list:
        ugly_suffix = ugly_suffix_list[0]
        clean_name = name.replace(ugly_suffix, "")
        return clean_name + f".suppl{ugly_suffix}.json"
    else:
        return name + DEFAULT_JSON_SUF


def rename_file(f_data, new_name):
    # rename media file
    new_path = f_data['path'].with_name(new_name)
    f_data['path'] = f_data['path'].rename(new_path)

    # rename json file
    if f_data.get('json_path'):
        new_json_path = f_data['json_path'].with_name(
            get_json_name_from_media_name(new_name)
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
            new_name = f_path.with_suffix(expected_ext).name
            rename_file(f_data, new_name)


def get_name_from_json_path(json_path):
    # will return original file name without extension suffix
    # option 1: /some/path/<media_name>.supplemental-metadata.json ; return <media_name>
    # option 2: /some/path/<media_name>.suppl.json ; return <media_name>
    # option 3: /some/path/<media_name>.supplemental-metadata(2).json ; return <media_name>(2)
    ugly_suffix_list = re.findall(r'[^()]*(\([0-9]+\)).json', str(json_path))
    if ugly_suffix_list:
        ugly_suffix = ugly_suffix_list[0]
        clean_name = json_path.name.replace(ugly_suffix, "")
        for suf in JSON_SUFFIXES:
            clean_name = clean_name.replace(suf, "")
        idx = clean_name.rfind('.')
        if idx != -1:
            return clean_name[:idx] + ugly_suffix
        else:
            return clean_name + ugly_suffix  # not found, append at end
    else:
        name = json_path.name
        for suf in JSON_SUFFIXES:
            name = name.replace(suf, "")
        return name[:name.rfind('.')]


def get_year_from_path(path):
    parent_name = path.parent.name
    find_year = re.findall(r'.*[^0-9]+([0-9]{4})', parent_name)
    if find_year:
        return find_year[0]
    else:
        return None


def scan_files(input_dir, output_dir):
    media_files = {}
    json_files = {}

    # walk through all files
    for root, _, files in os.walk(input_dir):
        for file in files:
            path = Path(root) / file
            year = get_year_from_path(path)
            if path.suffix.lower() in MEDIA_EXTS:
                if year not in media_files:
                    media_files[year] = {}
                if path.stem not in media_files[year]:
                    media_files[year][path.stem] = {"path": path}
                else:
                    # raise Exception(f"Duplicate media file for {path}")
                    duplicates_path = output_dir / "duplicates"
                    os.makedirs(duplicates_path, exist_ok=True)
                    shutil.copy2(path.with_name(f"{year}_{path.name}"), duplicates_path)

            elif path.suffix.lower() == ".json":
                media_name = get_name_from_json_path(path)
                if year not in json_files:
                    json_files[year] = {}
                if media_name not in json_files[year]:
                    json_files[year][media_name] = path
                else:
                    # raise Exception(f"Duplicate JSON file for {media_name}: {path}")
                    duplicates_path = output_dir / "duplicates" / "metadata"
                    os.makedirs(duplicates_path, exist_ok=True)
                    shutil.copy2(path.with_name(f"{year}_{path.name}"), duplicates_path)

    # match json files with media files
    res = []
    for year in media_files:
        for media_name in media_files[year]:
            media_file_data = media_files[media_name]
            media_name_match = media_file_data['path'].name[:46]
            try:
                media_file_data["json_path"] = json_files[year][media_name_match]
                del json_files[year][media_name]
            except KeyError:
                raise KeyError(f"No metadata to apply to {media_file_data['path']}")
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
    dest_json_path = output_dir / "metadata" / f_data["json_path"].name
    if dest_json_path.exists():
        raise Exception(f"Destination JSON path already exists: {dest_path}")
    logger.debug(f"copy json {f_data['json_path']} {dest_json_path}")
    shutil.copy2(f_data['json_path'], dest_json_path)


def process_media_file(f_data, output_dir):
    fix_wrong_extension(f_data)
    apply_json_metadata(f_data['path'], f_data.get('json_path'))
    copy_to_output(f_data, output_dir)
    logger.info(f"Done with file {f_data['path']}")


def main(input_dir, output_dir):
    input_dir = Path(input_dir).resolve()
    output_dir = Path(output_dir).resolve()
    os.makedirs(output_dir / "metadata", exist_ok=True)

    logger.info(f"Scanning folders under: {input_dir}\n")
    media_files = scan_files(input_dir, output_dir)

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
