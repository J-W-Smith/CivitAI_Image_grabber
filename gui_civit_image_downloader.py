import httpx
import os
import asyncio
import json
import tkinter as tk
from tkinter import ttk, messagebox
from tqdm import tqdm
import re
from datetime import datetime
import logging
import csv
from threading import Lock

# Logging setup
log_file_path = "civit_image_downloader_log_1.1.txt"
logging.basicConfig(filename=log_file_path, level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants and global variables
base_url = "https://civitai.com/api/v1/images"
headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Content-Type": "application/json"
}
semaphore = asyncio.Semaphore(10)
download_stats = {
    "downloaded": [],
    "skipped": [],
}
output_dir = "image_downloads"
os.makedirs(output_dir, exist_ok=True)
allow_redownload = False
downloaded_images_lock = Lock()
tag_model_mapping_lock = Lock()
TRACKING_JSON_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "downloaded_images.json")
downloaded_images = {}

# GUI Setup
def start_gui():
    root = tk.Tk()
    root.title("Civit Image Downloader")

    # Create frames for input fields and buttons
    frame = ttk.Frame(root, padding="10")
    frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    # Timeout input
    ttk.Label(frame, text="Timeout (seconds):").grid(row=0, column=0, sticky=tk.W)
    timeout_var = tk.StringVar(value="60")
    ttk.Entry(frame, textvariable=timeout_var).grid(row=0, column=1, sticky=tk.W)

    # Quality selection
    ttk.Label(frame, text="Image Quality:").grid(row=1, column=0, sticky=tk.W)
    quality_var = tk.StringVar(value="SD")
    ttk.Combobox(frame, textvariable=quality_var, values=["SD", "HD"]).grid(row=1, column=1, sticky=tk.W)

    # Re-download option
    allow_redownload_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(frame, text="Allow Redownload", variable=allow_redownload_var).grid(row=2, column=1, sticky=tk.W)

    # Mode selection
    ttk.Label(frame, text="Mode:").grid(row=3, column=0, sticky=tk.W)
    mode_var = tk.StringVar(value="username")
    ttk.Combobox(frame, textvariable=mode_var, values=["username", "model ID", "Model tag search", "model version ID"]).grid(row=3, column=1, sticky=tk.W)

    # Input field for usernames, model IDs, etc.
    ttk.Label(frame, text="Input:").grid(row=4, column=0, sticky=tk.W)
    input_var = tk.StringVar()
    ttk.Entry(frame, textvariable=input_var, width=40).grid(row=4, column=1, sticky=tk.W)

    # Start button
    def start_download():
        asyncio.run(start_download_process(timeout_var, quality_var, allow_redownload_var, mode_var, input_var))

    ttk.Button(frame, text="Start Download", command=start_download).grid(row=5, column=1, sticky=tk.W)

    # Status text
    status_var = tk.StringVar(value="Status: Ready")
    ttk.Label(frame, textvariable=status_var).grid(row=6, column=0, columnspan=2, sticky=tk.W)

    root.mainloop()

# Functions adapted from the original script
def load_downloaded_images():
    try:
        with open(TRACKING_JSON_FILE, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Example function tied to the GUI that starts the download process
async def start_download_process(timeout_var, quality_var, allow_redownload_var, mode_var, input_var):
    global downloaded_images
    downloaded_images = load_downloaded_images()

    timeout_value = int(timeout_var.get())
    quality = quality_var.get()
    allow_redownload = 1 if allow_redownload_var.get() else 2

    mode = mode_var.get()
    input_data = input_var.get().split(",")

    tasks = []
    if mode == "username":
        option_folder = create_option_folder('Username_Search', output_dir)
        tasks.extend([download_images(username.strip(), option_folder, 'username', timeout_value, quality, allow_redownload) for username in input_data])
    elif mode == "model ID":
        option_folder = create_option_folder('Model_ID_Search', output_dir)
        tasks.extend([download_images(model_id.strip(), option_folder, 'model', timeout_value, quality, allow_redownload) for model_id in input_data])
    elif mode == "Model tag search":
        option_folder = create_option_folder('Model_Tag_Search', output_dir)
        tags = [tag.strip().replace(" ", "_") for tag in input_data]
        disable_prompt_check = False  # You could add an option to toggle this in the GUI
        for tag in tags:
            sanitized_tag_dir_name = tag.replace(" ", "_")
            model_ids = await search_models_by_tag(tag.replace("_", "%20"), [])
            tasks_for_tag, _, _, _ = await download_images_for_model_with_tag_check(model_ids, option_folder, timeout_value, quality, tag, tag, sanitized_tag_dir_name, disable_prompt_check, allow_redownload)
            tasks.extend(tasks_for_tag)
    elif mode == "model version ID":
        option_folder = create_option_folder('Model_Version_ID_Search', output_dir)
        tasks.extend([download_images(model_version_id.strip(), option_folder, 'modelVersion', timeout_value, quality, allow_redownload) for model_version_id in input_data])

    results = await asyncio.gather(*tasks)
    messagebox.showinfo("Info", "Download process completed.")

def create_option_folder(option_name, base_dir):
    option_dir = os.path.join(base_dir, option_name)
    os.makedirs(option_dir, exist_ok=True)
    return option_dir

# Add the rest of your functions here as needed, adapted for asyncio and Tkinter.

# Run the GUI
start_gui()
