```markdown
# Civit Image Downloader

## Overview

The **Civit Image Downloader** is a Python-based tool designed to download images from CivitAi using their API. This tool provides several functionalities, including the ability to search for images by username, model ID, model version ID, or model tags. It also offers options for image quality, timeout settings, and whether to re-download already tracked images.

### New GUI Feature

This tool now includes a simple graphical user interface (GUI) built with **Tkinter**. The GUI allows users to input their search parameters and start the download process without needing to interact with the command line. The GUI simplifies the use of the downloader by providing clear input fields and options for the user.

## Installation

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/yourusername/civit-image-downloader.git
   cd civit-image-downloader
   ```

2. **Install Dependencies:**
   Ensure you have the required Python packages installed:
   ```bash
   pip install httpx tqdm tk
   ```

3. **Run the GUI:**
   Simply run the Python script to start the GUI:
   ```bash
   python civit_image_downloader.py
   ```

## Features

### 1. **GUI Interface**

The GUI includes the following features:

- **Timeout (seconds):** Input field to set the timeout duration for each request.
- **Image Quality:** Dropdown menu to select between SD (Standard Definition) and HD (High Definition).
- **Allow Redownload:** Checkbox to toggle whether to re-download images that have already been tracked.
- **Mode Selection:** Dropdown to choose the search mode: username, model ID, model tag search, or model version ID.
- **Input Field:** Input area for usernames, model IDs, tags, or model version IDs, depending on the selected mode.
- **Start Download Button:** Initiates the download process based on the provided inputs.

### 2. **Command-Line Interface (CLI) (Deprecated)**

While the tool now includes a GUI, the underlying functionalities of the command-line interface (CLI) are still accessible within the script. The CLI mode has been deprecated in favor of the GUI but remains functional for advanced users or integration into other systems.

### 3. **Image Downloading**

- **Search by Username:** Downloads images associated with a specific CivitAi username.
- **Search by Model ID:** Downloads images associated with a specific model ID.
- **Search by Model Version ID:** Downloads images associated with a specific model version ID.
- **Search by Tags:** Downloads images based on tags. The tool checks prompts against the specified tags.

### 4. **Logging and Error Handling**

The tool logs errors and progress in a log file (`civit_image_downloader_log_1.1.txt`). Errors during downloads, such as network issues, are logged and handled gracefully.

### 5. **Metadata Handling**

- **Metadata Extraction:** Extracts and saves metadata for each downloaded image.
- **Image Sorting:** Automatically sorts images into folders based on the associated model or tag.

## Usage

### Running with the GUI

1. **Start the GUI:**
   ```bash
   python civit_image_downloader.py
   ```

2. **Fill in the Parameters:**
   - Set the timeout duration.
   - Choose image quality (SD or HD).
   - Toggle the option to allow redownloads.
   - Select the search mode (username, model ID, etc.).
   - Enter the relevant inputs (e.g., usernames, model IDs).

3. **Start Download:**
   - Click the "Start Download" button to initiate the download process. The status and results will be displayed within the GUI.

### CLI (Advanced Users)

For users who prefer the command line, the script can still be run as before, with manual input prompts guiding the user through the process.

```bash
python civit_image_downloader.py
```

## Contributing

If you'd like to contribute to this project, feel free to fork the repository and submit a pull request. Contributions are always welcome!

## License

This project is licensed under the MIT License. See the LICENSE file for details.

```
