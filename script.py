import requests
import logging

from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin
from PIL import Image
import io
import shutil
from urllib.parse import urlparse, urljoin
import time
import json
import urllib.request
from urllib.error import HTTPError, URLError

import xml.etree.ElementTree as ET


def load_urls_to_scrape(file_path):
    try:
        with open(file_path, 'r') as file:
            return json.load(file)
    except Exception as e:
        print(f"Error loading URLs from file: {e}")
        return []



def fetch_sitemap(sitemap_url):
    try:
        response = requests.get(sitemap_url)
        response.raise_for_status()
        return response.content
    except Exception as e:
        print(f"Error fetching sitemap: {e}")
        return None

def parse_sitemap(sitemap_content):
    try:
        sitemap_urls = set()
        root = ET.fromstring(sitemap_content)
        for url in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}url'):
            loc = url.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc').text
            sitemap_urls.add(loc)
        return sitemap_urls
    except Exception as e:
        print(f"Error parsing sitemap: {e}")
        return set()
    
def save_asset_mapping():
    with open("asset_mapping.json", "w") as file:
        json.dump(asset_mapping, file, indent=4)


# Base directory
base_dir = "seointense"
os.makedirs(base_dir, exist_ok=True)

# Asset directories
asset_folders = ['css', 'js', 'img', 'json', 'fonts']
for folder in asset_folders:
    os.makedirs(os.path.join(base_dir, folder), exist_ok=True)

asset_mapping = {}
asset_counter = {'img': 1, 'script': 1, 'other': 1, 'css':1, 'js':1}

excluded_domains = ['ajax.googleapis.com', 'd3e54v103j8qbb.cloudfront.net',
                    'cdn.jsdelivr.net', 'cdnjs.cloudflare.com']
included_domains = ['assets-global.website-files.com']


def download_file(url, tag_name):
    global asset_counter, asset_mapping

    # Skip non-http URLs and localhost URLs
    if not url.startswith(('http://', 'https://')) or "localhost" in url or "127.0.0.1" in url or url.startswith(('tel:', 'mailto:')):
        print(f"Skipping URL: {url}")
        return None, None

    # Exclude external JS files
    excluded_domains = ['cdnjs.cloudflare.com', 'ajax.googleapis.com',
                        'cdn.jsdelivr.net', 'd3e54v103j8qbb.cloudfront.net']
    if any(domain in url for domain in excluded_domains):
        print(f"Skipping external JavaScript file: {url}")
        return None, None

    # Direct JavaScript files to 'js' folder
    if tag_name == 'script' or url.split('?')[0].split('.')[-1].lower() == 'js':
        tag_name = 'js'
        js_folder = os.path.join(base_dir, 'js')
        os.makedirs(js_folder, exist_ok=True)

    # Check if the asset has already been processed
    if url in asset_mapping:
        print(f"Asset already processed: {url}")
        return asset_mapping[url]

    try:
        # Checking and creating the folder
        folder = os.path.join(base_dir, tag_name)
        if not os.path.exists(folder):
            print(f"Creating folder: {folder}")
            os.makedirs(folder, exist_ok=True)

        # Extracting file extension
        try:
            file_extension = url.split('?')[0].split('.')[-1].lower()
            print(f"Extracted file extension: {file_extension} for URL: {url}")
        except Exception as ext_error:
            print(f"Error extracting file extension: {ext_error}, URL: {url}")
            return None, None

        simplified_name = f"{tag_name}-{asset_counter[tag_name]}.{file_extension}"

        asset_counter[tag_name] += 1
        path = os.path.join(folder, simplified_name)
        print(f"Generated path: {path}")

        if os.path.exists(path):
            print(f"File already exists: {path}")
            asset_mapping[url] = (simplified_name, path)
            return simplified_name, path

        # Set up request with a user agent
        request = urllib.request.Request(url)

        # Try downloading with requests
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()

            # Check response headers
            print(f"Response headers: {response.headers}")

            # Write file with explicit UTF-8 encoding
            with open(path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            print(f"Successfully downloaded and saved: {path}")
        except Exception as e:
            print(f"Error downloading with requests: {e}, URL: {url}")
            return None, None

        
        asset_mapping[url] = (simplified_name, path)
        return simplified_name, path

    except Exception as e:
        print(f"General error in download_file: {e}, URL: {url}")
        return None, None


def scrape_page(page_url, visited_urls=None):
    try:
        if visited_urls is None:
            visited_urls = set()

        if page_url in visited_urls:
            print(f"Already visited URL: {page_url}")
            return
        visited_urls.add(page_url)

        try:
            response = requests.get(page_url)
            if response.status_code != 200:
                print(
                    f"Failed to retrieve {page_url}: Status code {response.status_code}")
                return
        except requests.exceptions.RequestException as e:
            print(f"Request error for {page_url}: {e}")
            time.sleep(5)  # Wait 5 seconds before retrying
            return scrape_page(page_url, visited_urls)

        soup = BeautifulSoup(response.content, 'html.parser')
        folder = determine_folder(page_url, base_dir)
        # Determine depth for relative path calculation
        depth = len(os.path.relpath(folder, base_dir).split(os.sep)) - 1
        relative_prefix = "../" * depth if depth > 0 else ""
        print(relative_prefix, folder)
        modify_html(soup)
        process_and_save_assets(soup, folder, base_dir)
        save_html_file(soup, page_url, folder)
        crawl_additional_urls(soup, page_url, visited_urls)

    except Exception as e:
        print(f"Error in scrape_page: {e}, URL: {page_url}")


def determine_folder(page_url, base_dir):
    parsed_url = urlparse(page_url)
    path_segments = parsed_url.path.strip('/').split('/')

    # Use the base directory for the root or a core page
    if not path_segments or len(path_segments) == 1:
        return base_dir

    # Create a directory for non-core pages
    folder_path = os.path.join(base_dir, *path_segments[:-1])
    os.makedirs(folder_path, exist_ok=True)
    return folder_path


def process_and_save_assets(soup, parent_folder, base_dir):
    asset_types = {
        'css': 'link[rel="stylesheet"][href]',
        # Changed from 'script' to 'js' to match folder name
        'js': 'script[src]',
        'img': 'img[src]',
        'json': 'div[data-src$=".json"]'
    }

    for asset_type, selector in asset_types.items():
        for asset in soup.select(selector):
            try:
                url = asset.get('src') or asset.get(
                    'href') or asset.get('data-src')
                if url and url.startswith('http'):
                    simplified_name, local_path = download_file(
                        url, asset_type)
                    if simplified_name and local_path:
                        # Check if the parent folder is the base directory itself
                        is_core_page = (parent_folder == base_dir)

                        # Calculate the relative path
                        if is_core_page:
                            relative_path = os.path.join(
                                asset_type, simplified_name)
                        else:
                            depth = len(os.path.relpath(
                                parent_folder, base_dir).split(os.sep))
                            relative_prefix = "../" * depth
                            relative_path = os.path.join(
                                relative_prefix, asset_type, simplified_name)

                        if asset_type in ['js', 'css']:
                            asset['href' if asset_type ==
                                  'css' else 'src'] = relative_path
                        elif asset_type == 'img':
                            asset['src'] = relative_path
                        elif asset_type == 'json':
                            asset['data-src'] = relative_path
            except Exception as e:
                print(f"Error processing {asset_type}: {e}, URL: {url}")


def save_html_file(soup, page_url, parent_folder):
    parsed_url = urlparse(page_url)
    filename = parsed_url.path.strip('/').split('/')[-1]
    # Ensure filename ends with .html
    if not filename.endswith('.html'):
        filename = f"{filename}.html" if filename else "index.html"

    # Determine depth for relative path calculation
    depth = len(os.path.relpath(parent_folder, base_dir).split(os.sep)) - 1
    relative_prefix = "../" * depth if depth > 0 else ""

    filepath = os.path.join(parent_folder, filename)
    with open(filepath, 'w', encoding='utf-8') as file:
        process_and_save_assets(soup, parent_folder, relative_prefix)
        file.write(soup.prettify())


def modify_html(soup):
    try:
        # Check and remove 'data-wf-domain' attribute from <html> if it exists
        if soup.html and 'data-wf-domain' in soup.html.attrs:
            soup.html.attrs.pop('data-wf-domain', None)

        # Update href attribute for all <link> tags with 'hreflang'
        for link in soup.find_all('link', hreflang=True):
            link['href'] = 'https://www.seointense.com'

        # Decompose specific <meta> tags
        for meta in soup.find_all('meta', attrs={'name': 'generator', 'content': 'Webflow'}):
            meta.decompose()

        # Changing links for other metas specific <meta> tags
        # for meta in soup.find_all('meta', attrs={'property': 'twitter:image'}):
        #     meta[content]

        # Decompose specific <link> tags
        for link in soup.find_all('link', href=lambda x: x and 'fonts.googleapis.com' in x or 'fonts.gstatic.com' in x):
            link.decompose()

        # Remove script tags with localhost URLs
        for script in soup.find_all('script', src=lambda x: x and ('localhost' in x or '127.0.0.1' in x)):
            script.decompose()

        # Add new link tags for fonts
        # for font_file in os.listdir(font_folder):
        #     if font_file.endswith(('.ttf', '.woff', '.woff2')):
        #         font_path = os.path.join('fonts', font_file)
        #         new_link_tag = soup.new_tag(
        #             'link', href=font_path, rel='stylesheet')
        #         soup.head.append(
        #             new_link_tag) if soup.head else soup.append(new_link_tag)
    except Exception as e:
        logging.error(f"Error modifying HTML: {e}")



def crawl_additional_urls(soup, base_url, visited_urls):
    for link in soup.find_all('a', href=True):
        href = link.get('href')
        if href and not href.startswith('http'):
            full_url = urljoin(base_url, href)
            if full_url not in visited_urls:
                scrape_page(full_url, visited_urls)


def clear_directory(directory, exclude=None):
    exclude = exclude or []
    for item in os.listdir(directory):
        if item in exclude:
            continue
        item_path = os.path.join(directory, item)
        try:
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.unlink(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
        except Exception as e:
            print(f'Failed to delete {item_path}. Reason: {e}')


def compare_with_sitemap(visited_urls, sitemap_urls):
    missed_urls = sitemap_urls - visited_urls
    return missed_urls



if __name__ == "__main__":

    try:
        # Load existing asset mapping if it exists
        if os.path.exists("asset_mapping.json"):
            with open("asset_mapping.json", "r") as file:
                asset_mapping = json.load(file)
        else:
            asset_mapping = {}
        clear_directory(base_dir, exclude=['img', 'fonts'])
        visited_urls = set()
        scrape_page("https://seo-intense-final.webflow.io/", visited_urls)

        urls_to_scrape = load_urls_to_scrape("urls_to_scrape.json")
        for url in urls_to_scrape:
            if url not in visited_urls:
                scrape_page(url, visited_urls)


        # Save the asset mapping at the end
        save_asset_mapping()
    except Exception as e:
        print(f"Error in main block: {e}")
