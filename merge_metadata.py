
import os
import argparse
from process_folder import process_folder

parser = argparse.ArgumentParser(description='Lossless Google Takeout metadata merger (ExifTool) with built-in output normalization + Live Photo linking')
parser.add_argument('source_folder', help='Root folder of Google Photos Takeout')
parser.add_argument('output_folder', help='Destination folder for normalized media with embedded metadata')
parser.add_argument('-w', '--edited_word', default='edited', help="Google Photos 'edited' suffix (default: edited)")
args = parser.parse_args()

if not os.path.exists(args.source_folder):
    print("Source folder doesn't exist")
    raise SystemExit(1)

os.makedirs(args.output_folder, exist_ok=True)

process_folder(args.source_folder, args.edited_word, args.output_folder)
