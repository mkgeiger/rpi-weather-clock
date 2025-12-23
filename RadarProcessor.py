#!/usr/bin/env python3

"""
RadarProcessor class for DWD radar data processing and visualization
Requires pyproj for accurate coordinate transformations
"""
import requests
import h5py
import numpy as np
import os
import io
import math
import gc
from PIL import Image

# Use non-GUI backend to avoid display errors on headless systems / Pi
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, LinearSegmentedColormap, BoundaryNorm

# ---------- RadarProcessor class ----------
class RadarProcessor:
    def __init__(self, satellite_source='simple', zoom_level=11,
                 center_lon=8.862, center_lat=48.806,
                 image_width_pixels=512, image_height_pixels=512,
                 cities=None):
        """Initialize the radar processor with configurable parameters
        
        Requires pyproj for accurate coordinate transformations.
        """
        
        # Define available background map types and tile sources
        self.background_types = {
            'simple': 'Simple light background',
            'grid': 'Light background with coordinate grid',
            'topographic': 'Simulated topographic style',
            'osm': 'OpenStreetMap tiles',
            'esri_satellite': 'Esri satellite map',
            'esri_topo': 'Esri topographic map',
            'esri_street': 'Esri street map'
        }
        
        # Store configuration parameters
        self.satellite_source = satellite_source  # Background map type to use
        self.zoom_level = max(8, min(12, zoom_level))  # Clamp zoom level to reasonable range (8-12)
        
        # Geographic center point and output image dimensions
        self.center_lon = float(center_lon)  # Center longitude in decimal degrees
        self.center_lat = float(center_lat)  # Center latitude in decimal degrees
        self.image_width_pixels = int(image_width_pixels)   # Output image width
        self.image_height_pixels = int(image_height_pixels) # Output image height
        
        # Geographic bounds calculated from center and dimensions
        self.area_bounds = None  # Will be set by _calculate_area_bounds()
        
        # Radar data storage (loaded from HDF5 files)
        self.raw_data = None     # Original radar data from file (before scaling)
        self.scaled_data = None  # Processed radar data (dBZ values)
        self.lons = None         # Longitude coordinates for each radar pixel
        self.lats = None         # Latitude coordinates for each radar pixel
        
        # Crop offset tracking for area-of-interest optimization
        self.crop_row_offset = 0
        self.crop_col_offset = 0
        self.full_rows = 0
        self.full_cols = 0
        
        # Coordinate system attributes for compatibility with original pyproj version
        self.radar_crs = None      # Coordinate reference system (stored but not used)
        self.transformer = None    # Coordinate transformer (stored but not used)
        
        # City markers configuration - supports both (lon,lat) and (lon,lat,color) formats
        self.cities = cities if cities is not None else {}  # Dictionary of city locations
        
        # Tile caching system for faster map background loading
        self.tile_cache_dir = "tilecache"  # Directory to store downloaded map tiles
        os.makedirs(self.tile_cache_dir, exist_ok=True)  # Create cache directory if needed
        
        # Data freshness tracking for automatic updates
        self.last_modified = None  # Timestamp of last radar data update
        
        # Calculate geographic area bounds from center point and image dimensions
        self._calculate_area_bounds()

    def _calculate_required_radar_bounds(self, projdef, ll_lon, ll_lat, xscale, yscale, rows, cols):
        """Calculate the minimum radar pixel bounds needed to cover the area of interest.
        
        This allows us to crop the radar data before coordinate transformation,
        dramatically reducing memory usage while preserving full quality in the AOI.
        
        Returns:
            tuple: (row_start, row_end, col_start, col_end) pixel bounds
        """
        from pyproj import CRS, Transformer
        
        # Get area of interest bounds with a safety buffer
        lon_min, lon_max, lat_min, lat_max = self.area_bounds
        buffer_degrees = 0.1  # 0.1 degree buffer (~11km) for safety
        lon_min_buf = lon_min - buffer_degrees
        lon_max_buf = lon_max + buffer_degrees  
        lat_min_buf = lat_min - buffer_degrees
        lat_max_buf = lat_max + buffer_degrees
        
        try:
            # Create coordinate transformers
            radar_crs = CRS.from_proj4(projdef)
            wgs84_crs = CRS.from_epsg(4326)
            reverse_transformer = Transformer.from_crs(wgs84_crs, radar_crs, always_xy=True)
            
            # Transform AOI corners to radar projection coordinates
            grid_origin_x, grid_origin_y = reverse_transformer.transform(ll_lon, ll_lat)
            
            # Transform AOI bounds to projection coordinates
            corner_coords = [
                (lon_min_buf, lat_min_buf),  # Bottom-left
                (lon_max_buf, lat_min_buf),  # Bottom-right
                (lon_min_buf, lat_max_buf),  # Top-left
                (lon_max_buf, lat_max_buf)   # Top-right
            ]
            
            proj_xs, proj_ys = [], []
            for lon, lat in corner_coords:
                proj_x, proj_y = reverse_transformer.transform(lon, lat)
                proj_xs.append(proj_x)
                proj_ys.append(proj_y)
            
            # Convert projection coordinates to pixel indices
            # Pixel centers: x = origin_x + (col + 0.5) * xscale
            # Solving for col: col = (x - origin_x) / xscale - 0.5
            proj_x_min, proj_x_max = min(proj_xs), max(proj_xs)
            proj_y_min, proj_y_max = min(proj_ys), max(proj_ys)
            
            col_min = int((proj_x_min - grid_origin_x) / xscale - 0.5)
            col_max = int((proj_x_max - grid_origin_x) / xscale + 0.5)
            
            # Y coordinates are flipped: y = origin_y + (rows - 1 - row + 0.5) * yscale
            # Solving for row: row = rows - 1 - (y - origin_y) / yscale + 0.5
            row_min = int(rows - 1 - (proj_y_max - grid_origin_y) / yscale + 0.5)
            row_max = int(rows - 1 - (proj_y_min - grid_origin_y) / yscale + 0.5)
            
            # Clamp to valid radar grid bounds
            col_min = max(0, col_min)
            col_max = min(cols - 1, col_max)
            row_min = max(0, row_min)
            row_max = min(rows - 1, row_max)
            
            # Ensure we have at least some data
            if col_max <= col_min or row_max <= row_min:
                print(f"Warning: AOI bounds too small, using safety fallback")
                # Use a minimum 200x200 pixel area around the center
                center_row, center_col = rows // 2, cols // 2
                row_min = max(0, center_row - 100)
                row_max = min(rows - 1, center_row + 100)
                col_min = max(0, center_col - 100)
                col_max = min(cols - 1, center_col + 100)
            
            crop_rows = row_max - row_min + 1
            crop_cols = col_max - col_min + 1
            original_pixels = rows * cols
            cropped_pixels = crop_rows * crop_cols
            reduction_factor = original_pixels / cropped_pixels
            
            #print(f"Radar crop: [{row_min}:{row_max+1}, {col_min}:{col_max+1}] = {crop_rows}x{crop_cols}")
            #print(f"Memory reduction: {reduction_factor:.1f}x ({original_pixels:,} -> {cropped_pixels:,} pixels)")
            
            return row_min, row_max + 1, col_min, col_max + 1  # Return as slice bounds
            
        except Exception as e:
            print(f"Error calculating radar bounds: {e}")
            # Fallback to full grid
            return 0, rows, 0, cols

    def _log_memory_usage(self, stage=""):
        """Log current memory usage for debugging purposes.
        
        This method provides memory usage information during radar data processing.
        Can be safely called without any external dependencies.
        """
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / (1024 * 1024)
            print(f"Memory usage {stage}: {memory_mb:.1f} MB")
        except ImportError:
            # psutil not available, use simpler approach or skip logging
            pass

    def _gaussian_blur_numpy(self, data, sigma=1.5):
        """Apply Gaussian blur to smooth radar data using NumPy-only implementation.
        
        Uses separable kernel approach: blur horizontally first, then vertically.
        This is more efficient than 2D convolution for Gaussian kernels.
        """
        if sigma <= 0:
            return data  # No blurring needed
        
        # Create 1D Gaussian kernel - use float16 for memory efficiency
        radius = int(3 * sigma)  # Kernel extends to 3 standard deviations
        x = np.arange(-radius, radius + 1, dtype=np.float16)  # Symmetric range around zero
        kernel = np.exp(-(x ** 2) / (2 * sigma ** 2))  # Gaussian formula
        kernel = (kernel / kernel.sum()).astype(np.float16)  # Normalize to sum = 1
        
        # Ensure data is float16 for consistent processing, clamping to valid range
        data_clamped = np.clip(data, -65500, 65500)
        data_f16 = data_clamped.astype(np.float16)
        
        # Apply horizontal blur (convolve each row)
        temp = np.apply_along_axis(
            lambda m: np.convolve(m, kernel, mode='same'),  # Same size output
            axis=1,  # Apply to each row (horizontal direction)
            arr=data_f16
        ).astype(np.float16)
        
        # Apply vertical blur (convolve each column)
        result = np.apply_along_axis(
            lambda m: np.convolve(m, kernel, mode='same'),  # Same size output
            axis=0,  # Apply to each column (vertical direction)
            arr=temp
        ).astype(np.float16)
        
        return result

    def _calculate_area_bounds(self):
        """Calculate geographic bounds (lon/lat) from center point and image dimensions.
        
        Uses zoom level to determine scale, then calculates the geographic area
        that will be covered by the requested image size in pixels.
        """
        # Base scale reference: zoom 10 covers ~39km per 256px tile at equator
        base_km_per_tile = 39.0  # Kilometers per tile at zoom level 10
        tile_size_px = 256       # Standard tile size in pixels
        
        # Adjust for latitude (Earth is not flat - distance varies with latitude)
        cos_lat = np.cos(np.radians(self.center_lat))  # Correction factor for longitude
        base_km_per_tile_at_lat = base_km_per_tile * cos_lat  # Actual km/tile at this latitude
        
        # Calculate scale factor based on zoom level difference from reference (zoom 10)
        scale_factor = 2 ** (10 - self.zoom_level)  # Higher zoom = smaller area
        km_per_px = (base_km_per_tile_at_lat * scale_factor) / tile_size_px  # km per pixel
        
        # Calculate total area coverage in kilometers
        total_width_km = self.image_width_pixels * km_per_px   # Image width in km
        total_height_km = self.image_height_pixels * km_per_px # Image height in km
        
        # Convert from kilometers to degrees (approximate conversion)
        # 1 degree latitude ≈ 111 km everywhere
        # 1 degree longitude ≈ 111 km * cos(latitude)
        half_width_deg = (total_width_km / 2) / (111.0 * cos_lat)  # Half-width in degrees
        half_height_deg = (total_height_km / 2) / 111.0             # Half-height in degrees
        
        # Calculate geographic bounds around center point
        lon_min = self.center_lon - half_width_deg  # Western boundary
        lon_max = self.center_lon + half_width_deg  # Eastern boundary
        lat_min = self.center_lat - half_height_deg # Southern boundary
        lat_max = self.center_lat + half_height_deg # Northern boundary
        
        # Store as tuple: (west, east, south, north)
        self.area_bounds = (lon_min, lon_max, lat_min, lat_max)

    def download_hdf5_data(self, use_local=True):
        """Download HDF5 radar data from DWD or use local file.
        
        This method handles dual data source capability:
        1. Local file mode: Load radar data from local HDF5 file for testing/offline use
        2. Online mode: Download latest radar data from DWD OpenData service
        
        Args:
            use_local: If True, try local file first; if False, download from server
            
        Returns:
            bytes: Raw HDF5 data, or None if failed to load/download
        """
        if use_local:
            # Local file mode - load from disk for testing or offline operation
            local_filename = "composite_hx_test.hd5"  # Expected local file name
            
            if os.path.exists(local_filename):
                try:
                    # Read entire file into memory as binary data
                    with open(local_filename, "rb") as f:
                        data = f.read()
                    
                    # Validate that file contains actual data (not empty)
                    if len(data) == 0:
                        print(f"Local file {local_filename} is empty")
                        return None
                    
                    print(f"Loaded local radar data from {local_filename} ({len(data)} bytes)")
                    return data
                    
                except (IOError, OSError) as e:
                    # File system errors (permissions, disk issues, etc.)
                    print(f"Error reading local file {local_filename}: {e}")
                    return None
            else:
                # Local file not found - this is normal for first run
                print(f"Local file {local_filename} not found")
                return None
        else:
            # Online mode - download latest data from DWD OpenData service
            url = "https://opendata.dwd.de/weather/radar/composite/hx/composite_hx_LATEST-hd5"
            #print(f"Downloading HDF5 radar data from: {url}")  # Debug output
            
            try:
                # Request radar data with generous timeout (files can be large ~2-4MB)
                r = requests.get(url, timeout=60)
                r.raise_for_status()  # Raise exception for HTTP error codes
                
                # Validate that server returned actual data (not empty response)
                if len(r.content) == 0:
                    print("Server returned empty radar data file")
                    return None
                
                #print(f"Successfully downloaded HDF5 data ({len(r.content)} bytes)")
                return r.content  # Return raw binary data
                
            except requests.exceptions.RequestException as e:
                # Network errors, timeouts, HTTP errors, etc.
                print(f"Error downloading radar data: {e}")
                return None
            except Exception as e:
                # Catch-all for unexpected errors during download
                print(f"Unexpected error during radar data download: {e}")
                return None

    def load_and_process_data(self, use_local=True, server_modified=None):
        """Load and process HDF5 radar data from file or server.
        
        This method handles the complete workflow:
        1. Download/load raw HDF5 data
        2. Parse radar data and metadata
        3. Apply scaling to convert to dBZ values
        4. Setup coordinate transformation
        
        Args:
            use_local: If True, try local file first before downloading
            server_modified: Timestamp of server data for caching
            
        Returns:
            bool: True if data loaded successfully, False otherwise
        """
        # Step 1: Get raw HDF5 data (from file or download)
        hdf5_data = self.download_hdf5_data(use_local)
        if hdf5_data is None:
            return False  # Failed to get data
        
        # Update timestamp if provided (for cache management)
        if server_modified is not None:
            self.last_modified = server_modified
        
        # Step 2: Create in-memory file object for HDF5 parsing
        try:
            memory_file = io.BytesIO(hdf5_data)  # Convert bytes to file-like object
        except Exception as e:
            print(f"Error creating memory file from data: {e}")
            return False
        
        # Step 3: Parse HDF5 structure and extract metadata first (for area calculation)
        try:
            with h5py.File(memory_file, "r") as f:
                # Extract geographic reference information and grid info FIRST
                ll_lon = f["/where"].attrs["LL_lon"]  # Lower-left longitude
                ll_lat = f["/where"].attrs["LL_lat"]  # Lower-left latitude
                projdef = f["/where"].attrs["projdef"] # Projection definition string
                
                # Convert bytes to string if needed
                if isinstance(projdef, bytes):
                    projdef = projdef.decode('utf-8')
                
                # Extract grid spacing (pixel size in meters)
                try:
                    xscale = float(f["/where"].attrs["xscale"])  # Pixel width in meters
                    yscale = float(f["/where"].attrs["yscale"])  # Pixel height in meters
                except KeyError:
                    # Use default 250m resolution if not specified
                    xscale = yscale = 250.0
                    print("Using default grid scale: 250m x 250m")
                
                # Get full grid dimensions for area calculation
                full_shape = f["/dataset1/data1/data"].shape
                rows, cols = full_shape
                
                # Calculate required radar bounds for area of interest
                row_start, row_end, col_start, col_end = self._calculate_required_radar_bounds(
                    projdef, ll_lon, ll_lat, xscale, yscale, rows, cols
                )
                
                # Load ONLY the required subset of radar data (massive memory savings!)
                #print(f"Loading cropped radar data: [{row_start}:{row_end}, {col_start}:{col_end}]")
                self.raw_data = f["/dataset1/data1/data"][row_start:row_end, col_start:col_end]
                #print(f"Cropped data shape: {self.raw_data.shape} (vs {full_shape} full)")
                
                # Store crop offset for coordinate adjustment
                self.crop_row_offset = row_start
                self.crop_col_offset = col_start
                
                # Extract scaling parameters to convert raw values to dBZ
                gain = f["/dataset1/data1/what"].attrs["gain"]       # Scaling factor
                offset = f["/dataset1/data1/what"].attrs["offset"]   # Offset value
                nodata = f["/dataset1/data1/what"].attrs["nodata"]   # No-data marker
                undetect = f["/dataset1/data1/what"].attrs["undetect"] # Below detection threshold
                
        except Exception as e:
            print(f"Error reading HDF5 file: {e}")
            print("The file might be corrupted or in an unexpected format")
            return False
        
        # Get cropped radar data dimensions
        rows, cols = self.raw_data.shape  # Cropped dimensions, much smaller than full grid
        
        # Step 4: Apply scaling to convert raw values to meteorological units (dBZ)
        # Use float32 for better precision, then convert to float16 for storage
        # This avoids precision issues that can vary between platforms/NumPy versions
        scaled_f32 = self.raw_data.astype(np.float32) * np.float32(gain) + np.float32(offset)
        
        # Mark special values before final conversion
        scaled_f32[self.raw_data == undetect] = -32.0   # Below radar detection threshold
        scaled_f32[self.raw_data == nodata] = np.nan    # No data available (NaN)
        
        # Convert to float16 only after proper scaling and special value handling
        # This ensures consistent behavior across different platforms/NumPy versions
        self.scaled_data = scaled_f32.astype(np.float16)
        
        # Step 5: Setup coordinate transformation from radar grid to lat/lon
        try:
            # Store full grid dimensions for coordinate calculations
            self.full_rows = full_shape[0]
            self.full_cols = full_shape[1]
            
            self.setup_projection(projdef, float(ll_lon), float(ll_lat), 
                                float(xscale), float(yscale), rows, cols)
            return True  # Success
        except Exception as e:
            print(f"Error setting up coordinate projection: {e}")
            return False

    def setup_projection(self, projdef, ll_lon, ll_lat, xscale, yscale, rows, cols):
        """Setup coordinate transformation from radar grid to geographic coordinates.
        
        This method converts the radar's projected coordinate system (usually stereographic)
        to latitude/longitude coordinates for each pixel in the radar grid using pyproj.
        
        Args:
            projdef: PROJ.4 projection definition string
            ll_lon: Lower-left corner longitude
            ll_lat: Lower-left corner latitude  
            xscale: Pixel width in meters
            yscale: Pixel height in meters
            rows: Number of radar grid rows
            cols: Number of radar grid columns
        """
        # Store projection info for compatibility
        self.radar_crs = projdef
        self.transformer = None
        
        # Use pyproj for accurate coordinate transformation
        from pyproj import CRS, Transformer
        
        # Create coordinate reference systems
        radar_crs = CRS.from_proj4(projdef)  # Radar's projection (usually stereographic)
        wgs84_crs = CRS.from_epsg(4326)      # Standard lat/lon (WGS84)
        
        # Create bidirectional coordinate transformers
        transformer = Transformer.from_crs(radar_crs, wgs84_crs, always_xy=True)
        reverse_transformer = Transformer.from_crs(wgs84_crs, radar_crs, always_xy=True)
        
        # Calculate projected coordinates of the grid origin (lower-left corner)
        grid_origin_x, grid_origin_y = reverse_transformer.transform(ll_lon, ll_lat)
        
        # Create coordinate grids for CROPPED radar pixels only
        # Adjust for crop offset to maintain correct geographic positioning
        #self._log_memory_usage("before coordinate grid creation")
        
        # Create coordinate grids as float32 for good precision and memory efficiency  
        # Add crop offsets to maintain correct geographic positioning
        col_indices = np.arange(cols) + self.crop_col_offset
        row_indices = np.arange(rows) + self.crop_row_offset
        
        x_proj_1d = (grid_origin_x + (col_indices + 0.5) * xscale).astype(np.float32)
        y_proj_1d = (grid_origin_y + (self.full_rows - 1 - row_indices + 0.5) * yscale).astype(np.float32)
        
        # Create meshgrids as float32 (pyproj needs reasonable precision)
        x_proj_grid, y_proj_grid = np.meshgrid(x_proj_1d, y_proj_1d)
        x_proj_grid = x_proj_grid.astype(np.float32)
        y_proj_grid = y_proj_grid.astype(np.float32)
        del x_proj_1d, y_proj_1d  # Free memory immediately
        #self._log_memory_usage("after meshgrid creation")
        
        # Transform coordinates using pyproj
        lons_temp, lats_temp = transformer.transform(x_proj_grid, y_proj_grid)
        del x_proj_grid, y_proj_grid  # Free large arrays immediately
        #self._log_memory_usage("after coordinate transformation")
        
        # Clamp and convert to float32 for geographic precision
        np.clip(lons_temp, -180.0, 180.0, out=lons_temp)
        np.clip(lats_temp, -90.0, 90.0, out=lats_temp) 
        self.lons = lons_temp.astype(np.float32)
        self.lats = lats_temp.astype(np.float32)
        del lons_temp, lats_temp  # Free temporary arrays
        
        gc.collect()  # Force garbage collection
        #self._log_memory_usage("after coordinate optimization")

    def check_for_new_data(self):
        """Check if new radar data is available on DWD server using efficient HEAD request.
        
        Uses HTTP HEAD request to check file modification time without downloading
        the entire file. This is much more efficient than downloading to check freshness.
        
        Returns:
            tuple: (bool: has_new_data, datetime: server_timestamp)
                  - has_new_data: True if server has newer data than our cache
                  - server_timestamp: Last-Modified time from server, or None if unavailable
        """
        url = "https://opendata.dwd.de/weather/radar/composite/hx/composite_hx_LATEST-hd5"
        
        try:
            # Send HEAD request - gets headers only, not file content (much faster)
            response = requests.head(url, timeout=30)
            response.raise_for_status()  # Raise exception for HTTP error codes (404, 500, etc.)
            
            # Extract Last-Modified timestamp from HTTP headers
            last_modified_str = response.headers.get('Last-Modified')
            
            if last_modified_str:
                # Parse RFC 2822 date format used in HTTP headers
                from email.utils import parsedate_to_datetime
                server_modified = parsedate_to_datetime(last_modified_str)
                
                # Compare with our cached timestamp to determine if update needed
                if self.last_modified is None or server_modified > self.last_modified:
                    # Either we have no data yet, or server has newer data
                    #print(f"New radar data available (server: {server_modified})")
                    return True, server_modified
                else:
                    # Our cached data is current - no update needed
                    #print(f"Radar data is current (last check: {self.last_modified})")
                    return False, server_modified
            else:
                # Server doesn't provide Last-Modified header - assume data might be new
                print("Server doesn't provide Last-Modified header, assuming new data")
                return True, None
                
        except requests.exceptions.RequestException as e:
            # Network errors, timeouts, server errors, etc.
            print(f"Error checking for new radar data: {e}")
            return False, None  # Assume no new data on network errors
            
        except Exception as e:
            # Catch-all for unexpected errors (parsing, etc.)
            print(f"Unexpected error checking for new radar data: {e}")
            return False, None

    def get_area_cities(self):
        """Filter cities to only those visible within the current map area bounds.
        
        Implements two-pass filtering:
        1. Exact bounds check - cities within the visible map area
        2. Buffer zone check - cities just outside that might still be relevant
        
        Supports backward compatibility with both city data formats:
        - Legacy format: {"CityName": (longitude, latitude)}
        - Enhanced format: {"CityName": (longitude, latitude, color)}
        
        Returns:
            dict: Filtered cities in format {"CityName": (lon, lat, color)}
        """
        # Extract current map boundaries
        lon_min, lon_max, lat_min, lat_max = self.area_bounds
        
        area_cities = {}  # Will store cities visible in current map area
        
        # First pass: Find cities exactly within map bounds
        for city, city_data in self.cities.items():
            # Parse city data format for backward compatibility
            if len(city_data) == 2:
                # Legacy format: (longitude, latitude)
                lon, lat = city_data
                color = 'red'  # Default marker color for legacy format
            else:
                # Enhanced format: (longitude, latitude, color)
                lon, lat, color = city_data
            
            # Check if city coordinates fall within current map view
            if lon_min <= lon <= lon_max and lat_min <= lat <= lat_max:
                # City is visible - add to results with standardized format
                area_cities[city] = (lon, lat, color)
            
        # Second pass: Check buffer zone for cities just outside view
        # This ensures cities near map edges are still shown (improves user experience)
        buffer = 0.5  # Degrees of latitude/longitude buffer around map edges
        
        for city, city_data in self.cities.items():
            # Skip cities already found in first pass
            if city not in area_cities:
                # Parse city data format again (same logic as above)
                if len(city_data) == 2:
                    lon, lat = city_data
                    color = 'red'  # Default color
                else:
                    lon, lat, color = city_data
                
                # Check if city is within buffered bounds
                if (lon_min - buffer <= lon <= lon_max + buffer and
                        lat_min - buffer <= lat <= lat_max + buffer):
                    # City is in buffer zone - add to results
                    area_cities[city] = (lon, lat, color)
                    
        return area_cities  # Dictionary of cities visible in current map area

    def _deg2num(self, lat_deg, lon_deg, zoom):
        """Convert geographic coordinates (latitude/longitude) to tile numbers.
        
        This implements the standard Web Mercator projection used by most map tile services
        (Google Maps, OpenStreetMap, etc.). The conversion follows these steps:
        1. Longitude: Linear mapping from [-180,+180] to tile X coordinates
        2. Latitude: Mercator projection to handle Earth's spherical geometry
        
        The Mercator projection handles the fact that lines of longitude converge at
        the poles, ensuring that rectangular tiles maintain consistent angular coverage.
        
        Args:
            lat_deg: Latitude in decimal degrees [-85.05, +85.05]
            lon_deg: Longitude in decimal degrees [-180, +180]
            zoom: Zoom level [0-20] where 0=whole world, 20=maximum detail
            
        Returns:
            tuple: (x_tile, y_tile) - Integer tile coordinates at specified zoom level
        """
        # Convert latitude to radians for trigonometric calculations
        lat_rad = math.radians(lat_deg)
        
        # Calculate total number of tiles at this zoom level
        # Each zoom level doubles the resolution: 2^0=1 tile, 2^1=4 tiles, etc.
        n = 2.0 ** zoom
        
        # Longitude to X tile coordinate (simple linear mapping)
        # Longitude range [-180,+180] maps to tile range [0, n-1]
        x = int((lon_deg + 180.0) / 360.0 * n)
        
        # Latitude to Y tile coordinate (Mercator projection)
        # This complex formula handles Earth's spherical geometry:
        # - math.tan(lat_rad): Convert to slope at this latitude
        # - math.asinh(): Inverse hyperbolic sine (Mercator projection core)
        # - Normalization to [0,1] range, then scale to [0, n-1]
        y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
        
        return (x, y)  # Return tile coordinates as integers

    def _get_tile_cache_path(self, x, y, z, tile_source):
        """Generate file path for cached map tile.
        
        Args:
            x, y: Tile coordinates
            z: Zoom level
            tile_source: Map source (osm, esri_topo, etc.)
            
        Returns:
            str: Full path to cache file
        """
        cache_filename = f"{tile_source}_{z}_{x}_{y}.png"  # Unique filename per tile
        return os.path.join(self.tile_cache_dir, cache_filename)

    def _load_cached_tile(self, x, y, z, tile_source):
        """Load map tile from cache if it exists.
        
        Args:
            x, y: Tile coordinates  
            z: Zoom level
            tile_source: Map source
            
        Returns:
            PIL.Image: Cached tile image, or None if not cached
        """
        cache_path = self._get_tile_cache_path(x, y, z, tile_source)
        
        if os.path.exists(cache_path):
            try:
                # Load image from cache file
                tile_img = Image.open(cache_path).convert("RGB")
                #print(f"Loaded cached tile {x},{y},{z}")  # Debug output (commented)
                return tile_img
            except Exception as e:
                print(f"Failed to load cached tile {cache_path}: {e}")
                # Remove corrupted cache file so it will be re-downloaded
                try:
                    os.remove(cache_path)
                except:
                    pass  # Ignore removal errors
        return None  # Not in cache or failed to load

    def _save_tile_to_cache(self, tile_img, x, y, z, tile_source):
        """Save downloaded map tile to local cache for future reuse.
        
        Implements persistent tile caching to dramatically improve performance:
        - Avoids repeated downloads of the same map tiles
        - Reduces network bandwidth usage
        - Provides offline capability for previously viewed areas
        - Speeds up map rendering by ~10-50x for cached tiles
        
        Args:
            tile_img: PIL Image object containing the downloaded tile
            x, y: Tile coordinates at specified zoom level  
            z: Zoom level
            tile_source: Map source identifier (osm, esri_topo, etc.)
        """
        # Generate unique cache file path for this specific tile
        cache_path = self._get_tile_cache_path(x, y, z, tile_source)
        
        try:
            # Save tile as PNG to preserve quality while maintaining reasonable file size
            # PNG is lossless and supports transparency (important for overlay maps)
            tile_img.save(cache_path, "PNG")
            print(f"Cached tile {x},{y},{z} to {cache_path}")  # Success notification
            
        except Exception as e:
            # File system errors: permissions, disk full, invalid path, etc.
            # Non-critical error - caching failure doesn't break functionality
            print(f"Failed to cache tile {cache_path}: {e}")
            # Note: We don't re-raise the exception because caching is optional
            # The application should continue working even if caching fails

    def _download_tile(self, x, y, z, tile_source='osm'):
        """Download a single map tile from the specified tile service with caching.
        
        Implements intelligent caching strategy:
        1. Check cache first - return immediately if tile exists locally
        2. Download from appropriate tile service if not cached
        3. Save to cache for future requests
        4. Handle various tile service URL formats and error conditions
        
        Args:
            x, y: Tile coordinates at zoom level z
            z: Zoom level (higher = more detail)
            tile_source: Map service ('osm', 'esri_satellite', 'esri_topo', 'esri_street')
            
        Returns:
            PIL.Image: RGB tile image (256x256 pixels), or None if download failed
        """
        # Step 1: Check if tile is already cached locally
        cached_tile = self._load_cached_tile(x, y, z, tile_source)
        if cached_tile is not None:
            # Cache hit - return immediately without network request
            return cached_tile
        
        # Step 2: Cache miss - need to download from tile service
        # Build appropriate URL based on tile service provider
        if tile_source == 'osm':
            # OpenStreetMap - free, community-maintained maps
            url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        elif tile_source == 'esri_satellite':
            # Esri World Imagery - satellite/aerial photos
            # Note: Y coordinate comes before X in Esri services
            url = f"https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
        elif tile_source == 'esri_topo':
            # Esri Topographic Map - detailed topographic features
            url = f"https://services.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}"
        elif tile_source == 'esri_street':
            # Esri Street Map - detailed street and city maps
            url = f"https://services.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"
        else:
            # Unknown tile source - cannot proceed
            print(f"Unknown tile source: {tile_source}")
            return None
        
        try:
            # Step 3: Download tile with proper headers to avoid blocking
            headers = {
                # Use realistic browser User-Agent to avoid bot detection
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)'
            }
            #print(f"Downloading tile: {url}")  # Debug output (commented)
            
            # Request tile with reasonable timeout (balance speed vs reliability)
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                # Successfully downloaded - convert response to PIL Image
                tile_img = Image.open(io.BytesIO(response.content)).convert("RGB")
                #print(f"Successfully downloaded tile {x},{y},{z}")  # Debug
                
                # Step 4: Save to cache for future requests
                self._save_tile_to_cache(tile_img, x, y, z, tile_source)
                
                return tile_img  # Return the downloaded tile
                
            else:
                # HTTP error codes (404 = tile not found, 429 = rate limited, etc.)
                print(f"HTTP {response.status_code} for tile {x},{y},{z} from {tile_source}")
                return None
                
        except Exception as e:
            # Network errors, timeouts, invalid responses, etc.
            print(f"Failed to download tile {x},{y},{z} from {tile_source}: {e}")
            return None

    def _create_tile_background(self, ax, tile_source='osm'):
        """Create map background by downloading and stitching multiple tiles.
        
        This method implements the complete tile-based mapping pipeline:
        1. Calculate appropriate zoom level based on area size
        2. Determine which tiles are needed to cover the geographic area
        3. Download all required tiles (with caching)
        4. Stitch tiles into a single background image
        5. Apply proper geographic coordinate transformation
        
        The process handles various error conditions gracefully, including
        network failures, missing tiles, and coordinate edge cases.
        
        Args:
            ax: Matplotlib axes object to draw the background on
            tile_source: Map service ('osm', 'esri_satellite', 'esri_topo', etc.)
        """
        # Extract geographic boundaries of current map view
        lon_min, lon_max, lat_min, lat_max = self.area_bounds
        
        #print(f"Creating tile background with source: {tile_source}")  # Debug
        #print(f"Area bounds: {lon_min:.4f}, {lon_max:.4f}, {lat_min:.4f}, {lat_max:.4f}")
        
        # Step 1: Calculate appropriate zoom level based on area coverage
        # Higher zoom = more detail but more tiles needed (balance detail vs performance)
        lat_range = lat_max - lat_min  # Latitude span in degrees
        lon_range = lon_max - lon_min  # Longitude span in degrees
        area_size = max(lat_range, lon_range)  # Use larger dimension for zoom calculation
        
        # Zoom level selection based on area size (empirically optimized)
        if area_size > 1.0:      # Large areas (>1° span): country/state level
            zoom = 8
        elif area_size > 0.5:    # Medium areas (0.5-1° span): city level
            zoom = 9
        elif area_size > 0.25:   # Small areas (0.25-0.5° span): neighborhood level
            zoom = 10
        elif area_size > 0.125:  # Very small areas (0.125-0.25° span): district level
            zoom = 11
        else:                    # Tiny areas (<0.125° span): street level
            zoom = 12
        
        #print(f"Using zoom level: {zoom} (area size: {area_size:.4f}°)")  # Debug
        
        # Step 2: Calculate tile coordinate range needed to cover the area
        # Convert geographic bounds to tile coordinates
        min_x, max_y = self._deg2num(lat_min, lon_min, zoom)  # Bottom-left tile
        max_x, min_y = self._deg2num(lat_max, lon_max, zoom)  # Top-right tile
        # Note: Y coordinates are inverted in tile systems (0 = north pole)
        
        #print(f"Tile range: x={min_x}-{max_x}, y={min_y}-{max_y}")  # Debug
        
        # Step 3: Download all required tiles and handle failures gracefully
        tiles = []  # 2D array of tile images: tiles[row][col]
        successful_downloads = 0  # Track download success rate
        total_tiles = (max_x - min_x + 1) * (max_y - min_y + 1)  # Total tiles needed
        
        # Download tiles row by row (top to bottom in geographic terms)
        for y in range(min_y, max_y + 1):  # Tile Y coordinates (north to south)
            row_tiles = []  # Tiles for current row
            
            # Download tiles column by column (left to right)
            for x in range(min_x, max_x + 1):  # Tile X coordinates (west to east)
                tile = self._download_tile(x, y, zoom, tile_source)
                
                if tile:
                    # Successfully downloaded - add to row
                    row_tiles.append(tile)
                    successful_downloads += 1
                else:
                    # Download failed - create fallback tile to maintain grid structure
                    fallback_tile = Image.new('RGB', (256, 256), '#e8f4e8')  # Light green
                    row_tiles.append(fallback_tile)
                    print(f"Using fallback tile for {x},{y} (download failed)")
                    
            # Add completed row to tile grid
            if row_tiles:
                tiles.append(row_tiles)
        
        #print(f"Downloaded {successful_downloads}/{total_tiles} tiles successfully")  # Debug
        
        # Step 4: Handle complete download failure
        if successful_downloads == 0:
            print("Failed to download any tiles, falling back to simple background")
            self._create_simple_background(ax, 'simple')  # Use offline background
            return
        
        # Step 5: Stitch individual tiles into single background image
        tile_width = 256   # Standard tile size (pixels)
        tile_height = 256  # Standard tile size (pixels)
        total_width = len(tiles[0]) * tile_width    # Total stitched width
        total_height = len(tiles) * tile_height     # Total stitched height
        
        #print(f"Stitching {len(tiles[0])}x{len(tiles)} tiles into {total_width}x{total_height} image")
        
        # Create empty canvas for stitched image
        stitched = Image.new('RGB', (total_width, total_height))
        
        # Paste each tile at correct position in stitched image
        for row_idx, row in enumerate(tiles):
            for col_idx, tile in enumerate(row):
                # Calculate pixel position for this tile
                x_pos = col_idx * tile_width   # Left edge of tile
                y_pos = row_idx * tile_height  # Top edge of tile
                
                # Paste tile at calculated position
                stitched.paste(tile, (x_pos, y_pos))
        
        # Step 6: Calculate geographic extent of stitched image
        # Convert tile boundaries back to lat/lon for matplotlib
        def num2deg(x, y, z):
            """Convert tile coordinates back to lat/lon (inverse of _deg2num)."""
            n = 2.0 ** z
            # Longitude: linear conversion from tile X to degrees
            lon_deg = x / n * 360.0 - 180.0
            # Latitude: inverse Mercator projection from tile Y to degrees
            lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
            lat_deg = math.degrees(lat_rad)
            return lat_deg, lon_deg
        
        # Calculate actual geographic extent of the stitched tile mosaic
        # Add 1 to get tile boundaries (not centers)
        tile_lat_min, tile_lon_min = num2deg(min_x, max_y + 1, zoom)      # Bottom-left
        tile_lat_max, tile_lon_max = num2deg(max_x + 1, min_y, zoom)      # Top-right
        
        # Step 7: Display stitched background in matplotlib with proper coordinates
        ax.imshow(np.array(stitched),
                  extent=[tile_lon_min, tile_lon_max, tile_lat_min, tile_lat_max],  # Geographic bounds
                  aspect='auto',         # Allow non-square aspect ratio
                  origin='upper',        # Image origin at top-left (standard for maps)
                  interpolation='bilinear')  # Smooth scaling if needed
        
        # Set figure background to white (clean appearance)
        ax.figure.patch.set_facecolor('white')

    def _create_simple_background(self, ax, background_type):
        """Create offline map backgrounds without requiring external tile downloads.
        
        This provides fallback capability when network is unavailable or tile
        services are not working. Generates different background styles using
        only matplotlib drawing primitives - no external dependencies.
        
        Available background types:
        - 'simple': Clean light gray background
        - 'grid': Coordinate grid overlay for navigation
        - 'topographic': Simulated terrain using mathematical functions
        - default: Neutral gray background
        
        Args:
            ax: Matplotlib axes object to draw background on
            background_type: Style of background to generate
        """
        # Get current map boundaries for coordinate-aware backgrounds
        lon_min, lon_max, lat_min, lat_max = self.area_bounds
        
        if background_type == 'simple':
            # Clean, minimalist background - light gray
            # Good for focusing attention on radar data overlay
            ax.set_facecolor('#f5f5f5')  # Very light gray axes background
            ax.figure.patch.set_facecolor('#f5f5f5')  # Match figure background
        
        elif background_type == 'grid':
            # Coordinate grid background for navigation and reference
            # Helps users orient themselves geographically
            ax.set_facecolor('#f8f8f8')  # Slightly lighter than simple
            ax.figure.patch.set_facecolor('#f8f8f8')
            
            # Calculate grid spacing based on map area size
            # Larger areas get coarser grids to avoid clutter
            lon_step = (lon_max - lon_min) / 10  # 10 longitude divisions
            lat_step = (lat_max - lat_min) / 10  # 10 latitude divisions
            
            # Draw vertical grid lines (longitude)
            for lon in np.arange(lon_min, lon_max + lon_step, lon_step):
                ax.axvline(lon, color='lightgray', linewidth=0.5, alpha=0.7)
            
            # Draw horizontal grid lines (latitude)
            for lat in np.arange(lat_min, lat_max + lat_step, lat_step):
                ax.axhline(lat, color='lightgray', linewidth=0.5, alpha=0.7)
        
        elif background_type == 'topographic':
            # Simulated topographic background using mathematical terrain generation
            # Creates visual depth without real elevation data
            ax.set_facecolor('#e8f4e8')  # Light green base (suggests terrain)
            ax.figure.patch.set_facecolor('#e8f4e8')
            
            # Calculate coordinate ranges for mathematical terrain generation
            lon_range = lon_max - lon_min  # Total longitude span
            lat_range = lat_max - lat_min  # Total latitude span
            
            # Create coordinate grids for terrain calculation
            x = np.linspace(lon_min, lon_max, 20)  # 20x20 grid resolution
            y = np.linspace(lat_min, lat_max, 20)
            X, Y = np.meshgrid(x, y)
            
            # Generate pseudo-elevation using sinusoidal functions
            # Combines multiple frequency components for realistic terrain appearance
            Z = (np.sin((X - lon_min) / lon_range * 4 * np.pi) *      # Primary terrain waves
                 np.cos((Y - lat_min) / lat_range * 3 * np.pi) * 0.3 +  # Cross-directional waves
                 np.sin((X - lon_min) / lon_range * 7 * np.pi) * 0.1)   # Fine detail overlay
            
            # Draw terrain contours with earth-tone colors
            ax.contourf(X, Y, Z, levels=15,  # 15 elevation levels
                       colors=['#d4e6d4', '#e0f0e0', '#ecf5ec'],  # Green terrain colors
                       alpha=0.3)  # Subtle transparency
            
        else:
            # Default background for unknown types - neutral gray
            ax.set_facecolor('#f0f0f0')  # Standard gray background
            ax.figure.patch.set_facecolor('#f0f0f0')  # Match figure background

    def create_smooth_heatmap_grid(self, satellite_source=None, sigma=2.0):
        """Generate complete radar visualization with background map and smooth weather overlay.
        
        This is the main visualization method that combines all components:
        1. Create properly sized matplotlib figure for exact pixel output
        2. Generate background map (tiles or simple graphics)
        3. Process and overlay radar data with meteorological color scheme
        4. Add city markers with customizable colors
        5. Export as PIL image with precise dimensions
        
        The method handles missing data gracefully and provides fallbacks for
        network issues, coordinate problems, and other edge cases.
        
        Args:
            satellite_source: Background type ('osm', 'esri_satellite', 'simple', etc.)
            sigma: Gaussian blur sigma for radar smoothing (higher = smoother)
            
        Returns:
            PIL.Image: Complete weather radar map as RGBA image
        """
        # Use instance default if no specific background requested
        if satellite_source is None:
            satellite_source = self.satellite_source
        
        # Extract geographic boundaries for current view
        lon_min, lon_max, lat_min, lat_max = self.area_bounds
        
        # Step 1: Create matplotlib figure with exact pixel dimensions
        # Calculate figure size to achieve precise output dimensions
        base_dpi = 100  # Use 100 DPI for predictable pixel-to-inch conversion
        fig_width = self.image_width_pixels / base_dpi    # Width in inches
        fig_height = self.image_height_pixels / base_dpi  # Height in inches
        
        # Create figure and axes with calculated dimensions
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        
        # Set geographic coordinate system on axes
        ax.set_xlim(lon_min, lon_max)  # Longitude range (west to east)
        ax.set_ylim(lat_min, lat_max)  # Latitude range (south to north)
        ax.set_aspect('equal', adjustable='box')  # Maintain geographic aspect ratio
        
        # Step 2: Create background map layer
        if satellite_source in ['osm', 'esri_satellite', 'esri_topo', 'esri_street']:
            # Online tile-based backgrounds - download and stitch map tiles
            self._create_tile_background(ax, satellite_source)
        else:
            # Offline backgrounds - generate using matplotlib primitives
            self._create_simple_background(ax, satellite_source)
        
        # Step 3: Add radar data overlay (if available)
        # Check that we have all required radar data components
        if hasattr(self, 'scaled_data') and self.scaled_data is not None and \
           self.lons is not None and self.lats is not None:
            
            # Find radar pixels that fall within current map view
            mask = ((self.lons >= lon_min) & (self.lons <= lon_max) &
                    (self.lats >= lat_min) & (self.lats <= lat_max))
            
            if np.any(mask):  # At least some radar data in view
                # Extract bounding box of radar data in current view
                rows_in_area, cols_in_area = np.where(mask)
                row_min, row_max = rows_in_area.min(), rows_in_area.max()
                col_min, col_max = cols_in_area.min(), cols_in_area.max()
                
                # Extract subset of radar data covering the map area
                data_subset = self.scaled_data[row_min:row_max + 1, col_min:col_max + 1]
                
                # Extract corresponding coordinate subsets for proper geographic positioning
                lons_subset = self.lons[row_min:row_max + 1, col_min:col_max + 1]
                lats_subset = self.lats[row_min:row_max + 1, col_min:col_max + 1]
                
                # Step 3a: Clean and prepare radar data for visualization
                valid_data = data_subset.copy()
                valid_data[np.isnan(valid_data)] = -50      # Replace NaN with low value
                valid_data[valid_data < -10] = -50          # Remove noise below detection
                
                # Step 3b: Apply Gaussian smoothing to reduce pixelated appearance
                smoothed_data = self._gaussian_blur_numpy(valid_data, sigma=sigma)
                
                # Step 3c: Mask very low values to make them transparent
                smoothed_data = np.ma.masked_where(smoothed_data < -30, smoothed_data)
                
                # Define geographic extent using actual radar data boundaries (not map view)
                # This ensures radar data is positioned at its correct geographic location
                radar_lon_min = lons_subset.min()
                radar_lon_max = lons_subset.max()
                radar_lat_min = lats_subset.min()
                radar_lat_max = lats_subset.max()
                extent = [radar_lon_min, radar_lon_max, radar_lat_min, radar_lat_max]
                
                # Step 3d: Define meteorological color scheme (dBZ reflectivity scale)
                # Standard weather radar colors from light blue (weak) to magenta (extreme)
                dBZ_boundaries = [0, 1, 5.5, 10, 14.5, 19, 23.5, 28, 32.5, 37, 41.5, 46, 50.5, 55, 60, 65, 75, 85]
                dBZ_colors = [
                    '#99ffff00',  # 0-1 dBZ: Transparent (very light precipitation)
                    '#99ffff',    # 1-5.5 dBZ: Light blue (drizzle)
                    '#33ffff',    # 5.5-10 dBZ: Cyan (light rain)
                    '#00caca',    # 10-14.5 dBZ: Teal (light-moderate rain)
                    '#009934',    # 14.5-19 dBZ: Green (moderate rain)
                    '#4dbf1a',    # 19-23.5 dBZ: Light green (moderate-heavy rain)
                    '#99cc00',    # 23.5-28 dBZ: Yellow-green (heavy rain)
                    '#cce600',    # 28-32.5 dBZ: Yellow (very heavy rain)
                    '#ffff00',    # 32.5-37 dBZ: Bright yellow (intense rain)
                    '#ffc400',    # 37-41.5 dBZ: Orange-yellow (very intense)
                    '#ff8900',    # 41.5-46 dBZ: Orange (severe rain/small hail)
                    '#ff0000',    # 46-50.5 dBZ: Red (severe weather)
                    '#b40000',    # 50.5-55 dBZ: Dark red (large hail)
                    '#4848ff',    # 55-60 dBZ: Blue (very large hail)
                    '#0000ca',    # 60-65 dBZ: Dark blue (giant hail)
                    '#990099',    # 65-75 dBZ: Purple (extreme hail)
                    '#ff33ff'     # 75+ dBZ: Magenta (tornado/extreme weather)
                ]
                
                # Create matplotlib colormap from our custom colors
                dBZ_cmap = ListedColormap(dBZ_colors)
                norm = BoundaryNorm(dBZ_boundaries, dBZ_cmap.N, clip=True)
                
                # Step 3e: Render radar data overlay with proper transparency
                im = ax.imshow(
                    smoothed_data,
                    cmap=dBZ_cmap,          # Meteorological color scheme
                    norm=norm,              # Boundary-based color mapping
                    alpha=0.7,              # Semi-transparent overlay
                    extent=extent,          # Geographic coordinates
                    origin='upper',         # Standard image orientation
                    aspect='auto',          # Allow non-square pixels
                    interpolation='bilinear' # Smooth scaling
                )
        else:
            # No radar data available - background only
            print("No radar data available - showing background map only")
        
        # Step 4: Add city markers with customizable colors
        area_cities = self.get_area_cities()  # Get cities in current view
        
        for city, (lon, lat, color) in area_cities.items():
            # Double-check that city is within view (safety check)
            if lon_min <= lon <= lon_max and lat_min <= lat <= lat_max:
                # Draw city marker circle with custom color and black border
                ax.plot(lon, lat, 'o', markersize=10,
                        markerfacecolor=color,      # User-configurable color
                        markeredgecolor='black',    # Black border for visibility
                        markeredgewidth=1)          # 1-pixel border width
                
                # Add city name label with readable styling
                ax.text(lon, lat + 0.005, city,    # Slight vertical offset
                        fontsize=6,                 # Small but readable
                        fontweight='bold',          # Bold for better contrast
                        color='white',              # White text
                        ha='center', va='bottom',   # Center horizontally, bottom vertically
                        bbox=dict(boxstyle="round,pad=0.3",  # Rounded background box
                                 facecolor='black',          # Black background
                                 alpha=0.8))                 # Semi-transparent
        
        # Step 5: Clean up axes appearance for map display
        ax.set_xticks([])    # Remove longitude tick marks
        ax.set_yticks([])    # Remove latitude tick marks
        ax.axis('off')       # Hide axis lines and labels
        
        # Ensure coordinate limits are exactly as specified
        ax.set_xlim(lon_min, lon_max)
        ax.set_ylim(lat_min, lat_max)
        
        # Remove all padding around the plot area
        plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
        
        # Step 6: Export figure as PIL image with exact dimensions
        buf = io.BytesIO()  # In-memory buffer for image data
        
        plt.savefig(buf, format='png',           # PNG format for quality
                    dpi=base_dpi,                # Match our DPI calculation
                    bbox_inches='tight',         # Tight bounding box
                    pad_inches=0,                # No padding
                    facecolor=fig.get_facecolor(), # Preserve background color
                    transparent=False)           # Solid background
        
        # Convert matplotlib output to PIL Image
        buf.seek(0)  # Reset buffer position to beginning
        pil_image = Image.open(buf).convert("RGBA")  # RGBA for transparency support
        
        # Clean up matplotlib resources
        plt.close()
        
        return pil_image  # Return final radar map image
