import httpx
import os
import asyncio
import json
from tqdm import tqdm
import shutil
import re
from datetime import datetime
import logging
import csv
from threading import Lock


# Logging only for debugging, not productive
log_file_path = "civit_image_downloader_log_1.1.txt"
logging.basicConfig(filename=log_file_path, level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


##########################################
# CivitAi API is fixed!#
# civit_image_downloader_1.1
##########################################

# API endpoint for retrieving image URLs
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

# Directory for image downloads
output_dir = "image_downloads"
os.makedirs(output_dir, exist_ok=True)

def create_option_folder(option_name, base_dir):
    option_dir = os.path.join(base_dir, option_name)
    os.makedirs(option_dir, exist_ok=True)
    return option_dir

allow_redownload = False

# Function to download an image from the provided URL
async def download_image(url, output_path, timeout_value, quality='SD'):
    global download_stats  # Make sure that download_stats is available globally.
    file_extension = ".png" if quality == 'HD' else ".jpeg"
    output_path_with_extension = re.sub(r'\.jpeg|\.png', file_extension, output_path, flags=re.IGNORECASE)
    if quality == 'HD':
        url = re.sub(r"width=\d{3,4}", "original=true", url)
    
    async with httpx.AsyncClient() as client:
        async with semaphore:
            try:
                
                response = await client.get(url, timeout=timeout_value, headers=headers)
                response.raise_for_status()  # Ensures that the HTTP request was successful
                total_size = int(response.headers.get('content-length', 0))
                progress_bar = tqdm(total=total_size, unit='B', unit_scale=True, desc=f"Downloading {output_path_with_extension}")

                with open(output_path_with_extension, "wb") as file:
                    for chunk in response.iter_bytes():
                        progress_bar.update(len(chunk))
                        file.write(chunk)
                progress_bar.close()
                download_stats["downloaded"].append(output_path_with_extension)  # Recording as successfully downloaded
                return True
            except Exception as e:
                reason = str(e)
                if isinstance(e, httpx.RequestError) or isinstance(e, httpx.ConnectError):
                    reason = "Network error while downloading the image. Please check your internet connection and try again"
                elif isinstance(e, httpx.HTTPStatusError):
                    reason = f"Error downloading the image. Server response: {e.response.status_code} Please try again later."
                elif isinstance(e, ConnectionResetError):
                    reason = "The connection to the server was closed unexpectedly. This could be a temporary network problem. Please try again later"
                download_stats["skipped"].append((url, reason))  # Recording of the skip reason
                print(f"An unexpected error has occurred. {reason}")
                return False


# Async function to write meta data to a text file. If no meta data is available, the URL to the image is written to the txt file
async def write_meta_data(meta, output_path, image_id, username):
    if not meta:
        output_path = output_path.replace(".txt", "_no_meta.txt")
        url = f"https://civitai.com/images/{image_id}?period=AllTime&periodMode=published&sort=Newest&view=feed&username={username}&withTags=false"
        with open(output_path, "w", encoding='utf-8') as file:
            file.write(f"No meta data available for this image.\nURL: {url}\n")
    else:
        with open(output_path, "w", encoding='utf-8') as file:
            for key, value in meta.items():
                file.write(f"{key}: {value}\n")


TRACKING_JSON_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "downloaded_images.json")

downloaded_images_lock = Lock()
tag_model_mapping_lock = Lock()


def load_downloaded_images():
    try:
        with open(TRACKING_JSON_FILE, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def check_if_image_downloaded(image_id, image_path, quality='SD'):
    with downloaded_images_lock:
        image_key = f"{image_id}_{quality}"
        if image_key in downloaded_images:
            existing_path = downloaded_images[image_key].get("path")
            if existing_path == image_path:
                return True
        return False


def mark_image_as_downloaded(image_id, image_path, quality='SD', tags=None, url=None):
    with downloaded_images_lock:
        image_key = f"{image_id}_{quality}"
        current_date = datetime.now().strftime("%Y-%m-%d - %H:%M")

        # Merge tags using a generator expression
        merged_tags = list(set(downloaded_images.get(image_key, {}).get("tags", [])) | set(tags or []))
        
        # Create a new entry for the image
        downloaded_images[image_key] = {
            "path": image_path,
            "quality": quality,
            "download_date": current_date,
            "tags": merged_tags,
            "url": url
        }
        json_data_string = json.dumps(downloaded_images[image_key], indent=4)
        with open(TRACKING_JSON_FILE, "w") as file:
            json.dump(downloaded_images, file, indent=4)


SOURCE_MISSING_MESSAGE_SHOWN = False
NEW_IMAGES_DOWNLOADED = False

# Customization of the manual_copy function
def manual_copy(src, dst):
    global SOURCE_MISSING_MESSAGE_SHOWN, NEW_IMAGES_DOWNLOADED
    # Check whether the source file exists
    if os.path.exists(src):
        try:
            shutil.copy2(src, dst) # Copies the file and retains the metadata
            NEW_IMAGES_DOWNLOADED = True
            return True, dst  # Returns True if the copy was successful
        except Exception as e:
            print(f"Error copying the file {src} to {dst}. Error: {e}")
            return False  # Returns False if an error has occurred
    else:
        if not SOURCE_MISSING_MESSAGE_SHOWN:
            print(f"Source file {src} does not exist. Copy skipped.")
            SOURCE_MISSING_MESSAGE_SHOWN = True
        return False # Also returns False if the source file does not exist


# Remove images and metadata files from the source directory.
def clear_source_directory(model_dir):
    files_to_remove = [f for f in os.listdir(model_dir) if f.endswith(('.jpeg', '.png')) or f.endswith('_meta.txt')]
    for file in files_to_remove:
        file_path = os.path.join(model_dir, file)
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Failed to remove file {file_path}. Error: {e}")



def clean_and_shorten_path(path, max_total_length=260, max_component_length=80):
    # Replace %20 with a space
    path = path.replace("%20", " ")
    path = path.replace("%2B", "+")
    # Replace non-permitted characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        path = path.replace(char, '_')

    # Remove control characters
    path = re.sub(r'[\x00-\x1f\x7f]', '', path)

    # Remove trailing spaces or dots
    path = path.rstrip('. ')

    # Separate the path into directory and file name
    dir_name, file_name = os.path.split(path)

    # Shorten the file name if necessary
    if len(file_name) > max_component_length:
        file_name = file_name[:max_component_length - 3] + "_"

    # Shorten the directory name if necessary
    if len(dir_name) > max_total_length - len(file_name):
        dir_name = dir_name[:max_total_length - len(file_name) - 3] + "_"

    # Reassemble the path
    shortened_path = os.path.join(dir_name, file_name)

    # Ensure that the total path does not exceed the maximum length
    if len(shortened_path) > max_total_length:
        excess_length = len(shortened_path) - max_total_length
        shortened_path = shortened_path[:-excess_length].rstrip('. ')

    return shortened_path



def move_to_invalid_meta(src, model_dir):
    invalid_meta_dir = os.path.join(model_dir, 'invalid_meta')
    os.makedirs(invalid_meta_dir, exist_ok=True)
    new_dst = os.path.join(invalid_meta_dir, os.path.basename(src))
    try:
        shutil.move(src, new_dst)
    except Exception as e:
        print(f"Error moving the file {src} to the 'invalid_meta' folder. Error: {e}")
    return new_dst

        

def sort_images_by_model_name(model_dir):
    global NEW_IMAGES_DOWNLOADED
    if os.path.exists(model_dir) and os.listdir(model_dir):
        # List all meta files in the directory
        meta_files = [f for f in os.listdir(model_dir) if f.endswith('_meta.txt')]
        
        # Treat files with and without valid metadata separately
        for meta_file in meta_files:
            model_name_found = False
            with open(os.path.join(model_dir, meta_file), 'r', encoding='utf-8') as file:
                for line in file:
                    if "Model:" in line:
                        model_name = line.split(":")[1].strip()
                        model_name_found = True
                        break
                    
            if model_name_found:
                model_name = clean_and_shorten_path(model_name)  # Clean the model name
                target_dir = os.path.join(model_dir, model_name)
                os.makedirs(target_dir, exist_ok=True)
                process_image_and_meta(model_dir, meta_file, target_dir, valid_meta=True)
            else:
                # If no model name was found or the metadata is invalid
                process_image_and_meta(model_dir, meta_file, model_dir, valid_meta=False)
        
        clear_source_directory(model_dir)
        # Set NEW_IMAGES_DOWNLOADED to True when new images have been successfully sorted
        if meta_files:
            NEW_IMAGES_DOWNLOADED = True

def process_image_and_meta(model_dir, meta_file, target_dir, valid_meta):
    base_name = meta_file.replace('_meta.txt', '')
    image_moved = False
    new_image_path = None

    # Try to find and move/copy the corresponding image
    for extension in ['.jpeg', '.png']:
        image_path = os.path.join(model_dir, base_name + extension)
        if os.path.exists(image_path):
            if valid_meta:
                # Attempts to copy the image if the metadata is valid
                new_image_path = manual_copy(image_path, os.path.join(target_dir, os.path.basename(image_path)))
            else:
                # Move the image to the invalid_meta folder if the metadata is invalid
                new_image_path = move_to_invalid_meta(image_path, model_dir)
            image_moved = True if new_image_path else False
            break

    if image_moved:
        new_meta_path = manual_copy(os.path.join(model_dir, meta_file), os.path.join(target_dir, os.path.basename(meta_file))) if valid_meta else move_to_invalid_meta(os.path.join(model_dir, meta_file), model_dir)
        return new_image_path, new_meta_path
    else:
        return None, None

    

visited_pages = set()


async def search_models_by_tag(tag, failed_search_requests=[]):
    base_url = f"https://civitai.com/api/v1/models?tag={tag}&nsfw=true"
    model_id = set()
    async with httpx.AsyncClient() as client:
        async with semaphore:
            while base_url:
                try:
                    response = await client.get(base_url, headers=headers)
                    if response.status_code == 200:
                        data = response.json()
                        items = data.get('items', [])
                        if items:  # If items list is not empty
                            for model in items:
                                model_id.add(model['id'])
                        else:  # If items list is empty
                            print(f"No models found for the tag '{tag}'.")
                            return model_id  # Return the empty set
                        metadata = data.get('metadata', {})
                        nextPage = metadata.get('nextPage', None)
                        base_url = nextPage if nextPage else None
                    else:
                        logger.error(f"Server response: {response.status_code} for URL: {base_url}")
                        print(f"Unexpected server response: {response.status_code}. Please try again later.")
                        failed_search_requests.append(base_url)
                        break
                except httpx.RequestError as e:
                    logger.exception(f"Request error occurred while fetching models for tag '{tag}': {e}")
                    print("A connection error occurred. Please check your internet connection and try again.")
                    failed_search_requests.append(base_url)
                    break
        return model_id


tag_model_mapping = {}

async def download_images_for_model_with_tag_check(model_ids, option_folder, timeout_value, quality='SD', tag_to_check=None, tag_dir_name=None, sanitized_tag_dir_name=None, disable_prompt_check=False, allow_redownload=2):
    global NEW_IMAGES_DOWNLOADED
    failed_urls = []
    images_without_meta = 0
    tasks = []

    if tag_to_check is None:
        tag_to_check = tag_dir_name

    for model_id in model_ids:
        url = f"{base_url}?modelId={str(model_id)}&nsfw=X"
        visited_pages = set()  # Reset the visited_pages set for each model

        while url:
            if url in visited_pages:
                print(f"URL {url} already visited. Ending loop.")
                break
            visited_pages.add(url)
            async with httpx.AsyncClient() as client:
                async with semaphore:
                    try:
                        response = await client.get(url, timeout=timeout_value, headers=headers)
                        if response.status_code == 200:
                            try:
                                data = response.json()
                            except json.JSONDecodeError as e:
                                print(f"Invalid JSON data: {str(e)}")
                                break
                            items = data.get('items', [])
                            # Create directory for model ID
                            model_name = "unknown_model"
                            if items and isinstance(items[0], dict):
                                model_name = items[0]["meta"].get("Model", "unknown_model") if isinstance(items[0].get("meta"), dict) else "unknown_model"

                            tag_dir = os.path.join(option_folder, sanitized_tag_dir_name)
                            os.makedirs(tag_dir, exist_ok=True)

                            with tag_model_mapping_lock:
                                if tag_dir_name not in tag_model_mapping:
                                    tag_model_mapping[tag_dir_name] = []
                                tag_model_mapping[tag_dir_name].append((model_id, model_name))
                            
                            model_dir = os.path.join(tag_dir, f"model_{(model_id)}")
                            os.makedirs(model_dir, exist_ok=True)


                            for item in items:
                                item_meta = item.get("meta") if item else None
                                prompt = item_meta.get("prompt", "").replace(" ", "_") if isinstance(item_meta, dict) else ""
                                if disable_prompt_check:
                                    # Download the image (no prompt check)
                                    image_id = item['id']
                                    image_url = item['url']
                                    image_extension = ".png" if quality == 'HD' else ".jpeg"
                                    image_path = os.path.join(model_dir, f"{image_id}{image_extension}")

                                    # Check if the image has already been downloaded
                                    if allow_redownload == 2 and check_if_image_downloaded(str(image_id), image_path, quality):
                                        continue

                                    task = download_image(image_url, image_path, timeout_value, quality)
                                    tasks.append(task)
                                else:
                                    tag_words = tag_to_check.lower().split("_")
                                    if all(word in prompt.lower() for word in tag_words):
                                        # Download the image (prompt check passed)
                                        image_id = item['id']
                                        image_url = item['url']
                                        image_extension = ".png" if quality == 'HD' else ".jpeg"
                                        image_path = os.path.join(model_dir, f"{image_id}{image_extension}")
                                
                                        # Check if the image has already been downloaded
                                        if allow_redownload == 2 and check_if_image_downloaded(str(image_id), image_path, quality):
                                            continue
                                        task = download_image(image_url, image_path, timeout_value, quality)
                                        tasks.append(task)
                                    else:
                                        continue

                            # This will run all download tasks asynchronously
                            download_results = await asyncio.gather(*tasks)
                            tasks = []  # Reset the tasks list after gathering the results

                            # Check the results and mark the downloaded images
                            for idx, download_success in enumerate(download_results):
                                image_id = items[idx]['id']
                                if download_success:
                                    NEW_IMAGES_DOWNLOADED = True
                                    image_path = os.path.join(model_dir, f"{image_id}{'.png' if quality == 'HD' else '.jpeg'}")
                                    tags = [tag_to_check] if tag_to_check else []
                                    mark_image_as_downloaded(str(image_id), image_path, quality, tags=tags, url=image_url)
                                else:
                                    logger.error(f"Failed to download image {image_id}")

                                meta_output_path = os.path.join(model_dir, f"{image_id}_meta.txt")
                                await write_meta_data(items[idx].get("meta"), meta_output_path, image_id, items[idx].get('username', 'unknown'))
                                if not items[idx].get("meta"):
                                    images_without_meta += 1
                            sort_images_by_model_name(model_dir)
                            metadata = data['metadata']
                            next_page = metadata.get('nextPage')
                            if next_page:
                                url = next_page
                                await asyncio.sleep(3)  # Add a delay between requests
                            else:
                                break
                    except httpx.TimeoutException as e:
                        print(f"Request timed out: {str(e)}")
                        failed_urls.append(url)  # Append the failed URL to the list
                        logging.info(f"URL hinzugefügt zu failed_urls: {url}")
                        continue
                    except httpx.HTTPError as e:
                        print(f"HTTP error occurred: {str(e)}")
                        failed_urls.append(url)  # Append the failed URL to the list
                        logging.info(f"URL hinzugefügt zu failed_urls: {url}")
                        continue
                    except Exception as e:
                        print(f"An error occurred: {str(e)}")
                        failed_urls.append(url)  # Append the failed URL to the list
                        logging.info(f"URL hinzugefügt zu failed_urls: {url}")
                        continue

    return tasks, failed_urls, images_without_meta, sanitized_tag_dir_name


def sort_images_by_tag(option_folder, tag_model_mapping):
    with tag_model_mapping_lock:
        for tag, model_ids in tag_model_mapping.items():
            sanitized_tag = tag.replace(" ", "_")
            tag_dir = os.path.join(option_folder, sanitized_tag)
            if not os.listdir(tag_dir):
                print(f"No images found for the tag: {tag}")


def write_summary_to_csv(tag, downloaded_images, option_folder, tag_model_mapping):
    with tag_model_mapping_lock:
        tag_dir = os.path.join(option_folder, tag.replace(" ", "_"))
        for model_info in tag_model_mapping.get(tag, []):
            model_id, model_name = model_info
            model_dir = os.path.join(tag_dir, f"model_{(model_id)}")
        
            # Check if the model directory exists
            if not os.path.exists(model_dir):
                print(f"The {model_dir} directory does not exist. Skip the creation of the CSV file.")
                continue
            csv_file = os.path.join(model_dir, f"{tag.replace(' ', '_')}_summary_{datetime.now().strftime('%Y%m%d')}.csv")
            with open(csv_file, "w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(["Current Tag", "Previously Downloaded Tag", "Image Path", "Download URL"])
                for image_id, image_info in downloaded_images.items():

                    # Here it is assumed that the "tags" are stored in the "downloaded_images" dictionary
                    if tag in image_info.get("tags", []):
                        for prev_tag in image_info.get("tags", []):
                            if prev_tag != tag:
                                relative_path = os.path.relpath(image_info["path"], model_dir)
                                writer.writerow([tag, prev_tag, relative_path, image_info["url"]])

failed_identifiers = []  # List for saving failed usernames and model IDs

async def is_valid_username(username):
    url = f"{base_url}?username={username.strip()}&nsfw=X"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            if response.status_code == 500:
                response_data = response.json()
                if 'error' in response_data and response_data['error'] == "User not found":
                    return False, "Username not found"
            return True, None
        except httpx.RequestError as e:
            return False, f"Network error: {e}"
        except json.JSONDecodeError as e:
            return False, f"Error decoding response: {e}"
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"


async def is_valid_model_id(identifier):
    url = f"{base_url}?modelId={str(identifier)}&nsfw=X"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            if response.status_code == 500:
                # If the modelId fails, try modelVersionId
                url = f"{base_url}?modelVersionId={str(identifier)}&nsfw=X"
                response = await client.get(url, headers=headers)
                if response.status_code == 500:
                    return False, f"Invalid input syntax for model ID or model version ID: {identifier}"
            elif response.status_code == 304:
                response_data = response.json()
                if not response_data['items']:
                    return False, f"No items found for model ID or model version ID: {identifier}"
            return True, None
        except httpx.RequestError as e:
            return False, f"Network error: {e}"
        except json.JSONDecodeError as e:
            return False, f"Error decoding response: {e}"
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"


async def is_valid_model_version_id(model_version_id):
    url = f"{base_url}?modelVersionId={str(model_version_id)}&nsfw=X"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            if response.status_code == 500:
                return False, f"Invalid input syntax for model version ID: {model_version_id}"
            elif response.status_code == 304:
                response_data = response.json()
                if not response_data['items']:
                    return False, f"No items found for model version ID: {model_version_id}"
            return True, None
        except httpx.RequestError as e:
            return False, f"Network error: {e}"
        except json.JSONDecodeError as e:
            return False, f"Error decoding response: {e}"
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"


async def download_images(identifier, option_folder, identifier_type, timeout_value, quality='SD', allow_redownload=2):
    global NEW_IMAGES_DOWNLOADED
    valid, error_message = True, None
    if identifier_type == 'username':
        valid, error_message = await is_valid_username(identifier)
    elif identifier_type == 'model':
        valid, error_message = await is_valid_model_id(identifier)
    elif identifier_type == 'modelVersion':
        valid, error_message = await is_valid_model_version_id(identifier)
    if not valid:
        print(f"Skipping: {error_message}")
        failed_identifiers.append((identifier_type, identifier))
        return [], 0
    if identifier_type == 'model':
        url = f"{base_url}?modelId={str(identifier)}&nsfw=X"
    elif identifier_type == 'modelVersion':
        url = f"{base_url}?modelVersionId={str(identifier)}&nsfw=X"
    elif identifier_type == 'username':
        url = f"{base_url}?username={identifier.strip()}&nsfw=X"
    else:
        raise ValueError("Invalid identifier_type. Should be 'model', 'modelVersion', or 'username'.")

    failed_urls = []
    images_without_meta = 0

    while url:
        if url in visited_pages:
            print(f"URL {url} already visited. Ending loop.")
            break
        visited_pages.add(url)     
        async with httpx.AsyncClient() as client:
            async with semaphore:
                try:
                    response = await client.get(url, timeout=timeout_value)
                    if response.status_code == 200:
                        try:
                            data = response.json()
                        except json.JSONDecodeError as e:
                            print(f"Invalid JSON data: {str(e)}")
                            break

                        items = data.get('items', [])

                        # Create directory for model ID, model version ID, or username
                        if identifier_type in ['model', 'modelVersion']:
                            model_name = "unknown_model"
                            if items and isinstance(items[0], dict):
                                model_name = items[0]["meta"].get("Model", "unknown_model") if isinstance(items[0].get("meta"), dict) else "unknown_model"
                            dir_name = os.path.join(option_folder, f"{identifier_type}_{identifier}")
                        elif identifier_type == 'username':
                            dir_name = os.path.join(option_folder, identifier.strip())

                        os.makedirs(dir_name, exist_ok=True)

                        tasks = []
                        for item in items:
                            image_id = item['id']
                            image_url = item['url']
                            image_extension = ".png" if quality == 'HD' else ".jpeg"
                            image_path = os.path.join(dir_name, f"{image_id}{image_extension}")

                            # Check if the image has already been downloaded
                            if allow_redownload == 2 and check_if_image_downloaded(str(image_id), image_path, quality):
                                continue

                            task = download_image(image_url, image_path, timeout_value, quality)
                            tasks.append(task)

                        # This will run all download tasks asynchronously
                        download_results = await asyncio.gather(*tasks)

                        # Check the results and mark the downloaded images
                        for idx, download_success in enumerate(download_results):
                            image_id = items[idx]['id']
                            if download_success:
                                NEW_IMAGES_DOWNLOADED = True
                                image_path = os.path.join(dir_name, f"{image_id}{'.png' if quality == 'HD' else '.jpeg'}")
                                mark_image_as_downloaded(str(image_id), image_path, quality)
                            
                            meta_output_path = os.path.join(dir_name, f"{image_id}_meta.txt")
                            await write_meta_data(items[idx].get("meta"), meta_output_path, image_id, items[idx].get('username', 'unknown'))
                            if not items[idx].get("meta"):
                                images_without_meta += 1
                        
                        metadata = data['metadata']
                        next_page = metadata.get('nextPage')

                        if next_page:
                            url = next_page
                            await asyncio.sleep(3)  # Add a delay between requests
                        else:
                            break
                except httpx.TimeoutException as e:
                    print(f"Request timed out: {str(e)}")
                    continue

    if identifier_type in ['model', 'modelVersion']:
        # Sorting the images by model name after downloading them
        sort_images_by_model_name(dir_name)
    elif identifier_type == 'username':
        sort_images_by_model_name(dir_name)

    return failed_urls, images_without_meta


def print_download_statistics():
    print("\n")
    print(f"Number of downloaded images: {len(download_stats['downloaded'])}")
    print(f"Number of skipped images: {len(download_stats['skipped'])}")

    if download_stats['skipped']:
        print("\nReasons for skipping images:")
        reasons = {}
        for _, reason in download_stats['skipped']:
            if reason in reasons:
                reasons[reason] += 1
            else:
                reasons[reason] = 1
        
        for reason, count in reasons.items():
            print(f"- {reason}: {count} times")

# Main async function
async def main():
    try:
        global downloaded_images
        downloaded_images = load_downloaded_images()

        # Universal user inputs for timeout and quality
        timeout_input = input("Enter timeout value (in seconds): ")
        if timeout_input.isdigit() and int(timeout_input) > 0:
            timeout_value = int(timeout_input)
        else:
            print("Invalid timeout value. Using default value of 60 seconds.")
            timeout_value = 60

        quality_choice = input("Choose image quality (1 for SD, 2 for HD): ")
        if quality_choice == '2':
            quality = 'HD'
        elif quality_choice == '1':
            quality = 'SD'
        else:
            print("Invalid quality choice. Using default quality SD.")
            quality = 'SD'

        allow_redownload_choice = input("Allow re-downloading of images already tracked (1 for Yes, 2 for No) [default: 2]: ")
        if allow_redownload_choice == '1':
            allow_redownload = 1
        elif allow_redownload_choice == '2' or allow_redownload_choice.strip() == '':
            allow_redownload = 2
        else:
            print("Invalid choice. Using default value (2 - No).")
            allow_redownload = 2

        failed_search_requests = []
        failed_urls = []
        images_without_meta = 0

        # Extended choice options including tag search and modelVersionId
        choice = input("Choose mode (1 for username, 2 for model ID, 3 for Model tag search, 4 for model version ID): ")
        tasks = []

        if choice == "3":
            tags_input = input("Enter tags (comma-separated): ")
            tags = [tag.strip().replace(" ", "_") for tag in tags_input.split(',')]
            disable_prompt_check = input("Disable prompt check? (y/n): ").lower() in ['y', 'yes']

            option_folder = create_option_folder('Model_Tag_Search', output_dir)

            for tag in tags:
                sanitized_tag_dir_name = tag.replace(" ", "_")
                model_ids = await search_models_by_tag(tag.replace("_", "%20"), failed_search_requests)
                tag_to_check = None if disable_prompt_check else tag
                tasks_for_tag, failed_urls_for_tag, images_without_meta_for_tag, sanitized_tag_dir_name_for_tag = await download_images_for_model_with_tag_check(model_ids, option_folder, timeout_value, quality, tag_to_check, tag, sanitized_tag_dir_name, disable_prompt_check, allow_redownload)
                tasks.extend(tasks_for_tag)
                failed_urls.extend(failed_urls_for_tag)
                images_without_meta += images_without_meta_for_tag

        elif choice == "1":
            usernames = input("Enter usernames (comma-separated): ").split(",")
            option_folder = create_option_folder('Username_Search', output_dir)
            tasks.extend([download_images(username.strip(), option_folder, 'username', timeout_value, quality, allow_redownload) for username in usernames])

        elif choice == "2":
            option_folder = create_option_folder('Model_ID_Search', output_dir)
            while True:
                model_ids_input = input("Enter model IDs (comma-separated): ")
                model_ids = model_ids_input.split(",")
                if all(model_id.strip().isdigit() for model_id in model_ids):
                    tasks.extend([download_images(model_id.strip(), option_folder, 'model', timeout_value, quality, allow_redownload) for model_id in model_ids])
                    break
                else:
                    print("Invalid input. Please enter only numeric model IDs.")

        elif choice == "4":
            option_folder = create_option_folder('Model_Version_ID_Search', output_dir)
            while True:
                model_version_ids_input = input("Enter model version IDs (comma-separated): ")
                model_version_ids = model_version_ids_input.split(",")
                if all(model_version_id.strip().isdigit() for model_version_id in model_version_ids):
                    tasks.extend([download_images(model_version_id.strip(), option_folder, 'modelVersion', timeout_value, quality, allow_redownload) for model_version_id in model_version_ids])
                    break
                else:
                    print("Invalid input. Please enter only numeric model version IDs.")
        else:
            print("Invalid choice!")
            return

        # Execute all collected tasks
        results = await asyncio.gather(*tasks)

        # Extract failed_urls and images_without_meta from the results
        failed_urls.extend([url for result in results for url in result[0]])
        images_without_meta += sum([count for result in results for count in result[1:]])

        # Sort images into tag-related folders
        sort_images_by_tag(option_folder, tag_model_mapping)

        for tag, model_ids in tag_model_mapping.items():
            write_summary_to_csv(tag, downloaded_images, option_folder, tag_model_mapping)

        if failed_urls:
            print("Retrying failed URLs...")
            for url in failed_urls:
                await download_image(url, option_folder, timeout_value=timeout_value, quality=quality)

        # Attempt to retry failed search requests
        if failed_search_requests:
            print("Retrying failed search requests...")
            for url in failed_search_requests:
                tag = url.split("tag=")[-1]
                await search_models_by_tag(tag, [])

        if images_without_meta > 0:
            print(f"{images_without_meta} images have no meta data.")

        print_download_statistics()

    except Exception as e:
        logger.exception(f"An unexpected error occurred: {str(e)}")
        raise

asyncio.run(main())

if failed_identifiers:
    print("Failed identifiers:")
    for id_type, id_value in failed_identifiers:
        print(f"{id_type}: {id_value}")

print("Image download completed.")
