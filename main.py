import streamlit as st
import gpxpy
from PIL import Image, ImageDraw, ImageEnhance
import io
import folium
from streamlit_folium import folium_static
import numpy as np
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
import tempfile


def calculate_bounding_box(coordinates):
    """Calculate the bounding box of the GPS coordinates."""
    min_lat = min(coord[0] for coord in coordinates)
    max_lat = max(coord[0] for coord in coordinates)
    min_lon = min(coord[1] for coord in coordinates)
    max_lon = max(coord[1] for coord in coordinates)
    return min_lat, max_lat, min_lon, max_lon

def scale_coordinates_with_aspect_ratio(lat, lon, min_lat, max_lat, min_lon, max_lon, img_width, img_height, margin):
    """Scale GPS coordinates to image coordinates while maintaining aspect ratio and applying margin."""
    # Calculate aspect ratios
    gps_width = max_lon - min_lon
    gps_height = max_lat - min_lat
    gps_aspect = gps_width / gps_height
    img_aspect = img_width / img_height

    # Apply margin
    effective_width = img_width * (1 - 2 * margin)
    effective_height = img_height * (1 - 2 * margin)

    if gps_aspect > img_aspect:
        # GPS data is wider, scale to fit width
        scale = effective_width / gps_width
        offset_x = img_width * margin
        offset_y = (img_height - (gps_height * scale)) / 2
    else:
        # GPS data is taller, scale to fit height
        scale = effective_height / gps_height
        offset_x = (img_width - (gps_width * scale)) / 2
        offset_y = img_height * margin

    x = ((lon - min_lon) * scale) + offset_x
    y = img_height - ((lat - min_lat) * scale) - offset_y

    return x, y

def draw_gpx_on_image(image, coordinates, circle_color, circle_size, dot_spacing, margin):
    """Draw GPX data points on the image."""
    draw = ImageDraw.Draw(image)
    
    min_lat, max_lat, min_lon, max_lon = calculate_bounding_box(coordinates)
    
    # Apply dot spacing
    coordinates = coordinates[::max(1, dot_spacing)]
    
    for lat, lon in coordinates:
        x, y = scale_coordinates_with_aspect_ratio(lat, lon, min_lat, max_lat, min_lon, max_lon, image.width, image.height, margin)
        draw.ellipse([x-circle_size, y-circle_size, x+circle_size, y+circle_size], fill=circle_color)
    
    return image

def darken_image(image, opacity):
    """Darken the image to increase contrast with the points."""
    darkened = Image.new('RGBA', image.size, (0, 0, 0, int(255 * opacity)))
    return Image.alpha_composite(image.convert('RGBA'), darkened)

@st.cache_data()
def get_map_image(coordinates, width, height):
    """Generate a map image using Folium and Selenium."""
    min_lat, max_lat, min_lon, max_lon = calculate_bounding_box(coordinates)
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2

    m = folium.Map(location=[center_lat, center_lon], zoom_start=12)
    folium.PolyLine(coordinates, color="red", weight=2.5, opacity=0.8).add_to(m)

    # Save map to a temporary file
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".html", delete=False) as tmp:
        m.save(tmp.name)
        tmp_name = tmp.name

    # Use Selenium to capture the map as an image
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(width, height)
    driver.get(f"file://{tmp_name}")
    time.sleep(2)  # Wait for the map to load
    driver.save_screenshot("map.png")
    driver.quit()

    return Image.open("map.png")

def resize_and_crop(image, target_width, target_height):
    """Resize and crop the image to match the target dimensions while maintaining aspect ratio."""
    # Calculate the aspect ratio
    aspect_ratio = image.width / image.height
    target_aspect_ratio = target_width / target_height

    if aspect_ratio > target_aspect_ratio:
        # Image is wider, crop the width
        new_width = int(target_height * aspect_ratio)
        image = image.resize((new_width, target_height), Image.LANCZOS)
        left = (image.width - target_width) // 2
        image = image.crop((left, 0, left + target_width, target_height))
    else:
        # Image is taller, crop the height
        new_height = int(target_width / aspect_ratio)
        image = image.resize((target_width, new_height), Image.LANCZOS)
        top = (image.height - target_height) // 2
        image = image.crop((0, top, target_width, top + target_height))

    return image

st.set_page_config(layout="wide")

st.write("# Strava Art")
st.write("### Download a GPX file from your Strava activity on the Strava desktop website ([docs](https://support.strava.com/hc/en-us/articles/216918437-Exporting-your-Data-and-Bulk-Export)) and combine it with an image!")
col1, col2 = st.columns([3,5])
col1.write("## File uploads")
col11, col12 = col1.columns([1,1])

gpx_file = col11.file_uploader("Upload a GPX file", type=["gpx"])

if gpx_file is not None:
    gpx = gpxpy.parse(gpx_file)
    coordinates = []
    for track in gpx.tracks:
        for segment in track.segments:
            segment_coords = [(point.latitude, point.longitude) for point in segment.points]
            coordinates.extend(segment_coords)
    


img_file = col12.file_uploader("Upload an image", type=["png", "jpg", "jpeg"])

col11.header("Customization")
# remake columns so the options are aligned
col11, col12 = col1.columns([1,1])

circle_color = col11.color_picker("Circle color", "#FF0000")
circle_size = col12.slider("Circle size", 1, 20, 3)
dot_spacing = col11.slider("Dot spacing", 1, 100, 36, help="Higher values will space out the dots more")
margin = col12.slider("Margin", 0.0, 0.25, 0.05, help="Margin around the edges of the image (as a fraction)")
background_opacity = col11.slider("Background darkening", 0.0, 1.0, 0.25, help="Opacity of the dark overlay (0 = no darkening, 1 = fully black)")
map_opacity = col12.slider("Map overlay opacity", 0.0, 1.0, 0.23, help="Opacity of the map overlay (0 = no map, 1 = full map)")
percentage_hide_on_either_end = col11.slider("Percentage to hide on either end", 0, 50, 10, help="Percentage of the image to hide on either end")

if img_file is not None and gpx_file is not None:
    original_image = Image.open(img_file).convert("RGBA")
    
    # shrink coordinates by percentage_hide_on_either_end on either end
    start_index = int(len(coordinates) * percentage_hide_on_either_end / 100)
    end_index = len(coordinates) - start_index
    coordinates = coordinates[start_index:end_index]
    # Generate map image
    map_image = get_map_image(coordinates, 1600, 1200)  # Fixed size for consistency
    
    # Resize and crop the original image to match the map image dimensions
    # resized_original = resize_and_crop(original_image, map_image.width, map_image.height)
    placeholder = col2.container()
    # resize map image to match original image dimensions
    with placeholder:
        with st.spinner("Processing..."):
            resized_map = resize_and_crop(map_image, original_image.width, original_image.height)
            
            # Blend map with resized original image
            # blended_image = Image.blend(resized_original, map_image.convert("RGBA"), map_opacity)
            blended_image = Image.blend(original_image, resized_map.convert("RGBA"), map_opacity)
            
            # Darken the blended image
            darkened_image = darken_image(blended_image, background_opacity)
            
            result_image = draw_gpx_on_image(darkened_image, coordinates, circle_color, circle_size, dot_spacing, margin)
            
            col2.image(result_image, use_column_width=True)