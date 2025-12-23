#!/usr/bin/env python3

from RadarProcessor import RadarProcessor
from PIL import ImageTk
import tkinter as tk
from tkinter import ttk
import threading
import time

radar = None  # Global radar processor instance
root = None
canvas = None

def update_image_in_gui():
    global root
    global canvas
    """Update the displayed image in the GUI (thread-safe)"""
    try:
        new_pil_image = radar.create_smooth_heatmap_grid(sigma=1.5)
        photo = ImageTk.PhotoImage(new_pil_image)
        
        canvas.create_image(0, 0, anchor=tk.NW, image=photo)
        
        # Store references to prevent garbage collection
        root.photo = photo
        root.current_pil_image = new_pil_image
    except Exception as e:
        print(f"Error updating GUI: {e}")

def auto_update_loop():
    """Background thread for checking and updating when new radar data is available"""
    while True:
        time.sleep(60)
        
        # If still running after 60 seconds, check for new data
        has_new_data, server_modified = radar.check_for_new_data()
        if has_new_data:
            try:
                # Load fresh data from server with timestamp info
                if radar.load_and_process_data(use_local=False, server_modified=server_modified):
                    # Schedule image generation in main thread to avoid matplotlib threading issues
                    root.after(0, update_image_in_gui)
                else:
                    print("Failed to fetch new radar data")
            except Exception as e:
                print(f"Error updating radar data: {e}")
        else:
            print("No new radar data, continuing to monitor...")

def main():
    global radar
    global root
    global canvas
    
    # Create radar processor
    radar = RadarProcessor(
        satellite_source='esri_topo',
        zoom_level=11,
        center_lon=8.862,      # Heimsheim
        center_lat=48.806,
        image_width_pixels=512,
        image_height_pixels=512,
        cities={
                    'Heimsheim': (8.862, 48.806, 'red'),
                    'Leonberg': (9.014, 48.798, 'green'),
                    'Rutesheim': (8.947, 48.808, 'green'),
                    'Renningen': (8.934, 48.765, 'green'),
                    'Weissach': (8.929, 48.847, 'green'),
                    'Friolzheim': (8.835, 48.836, 'green'),
                    'Wiernsheim': (8.851, 48.891, 'green'),
                    'Liebenzell': (8.732, 48.771, 'green'),
                    'Calw': (8.739, 48.715, 'green'),
                    'Weil der Stadt': (8.871, 48.750, 'green'),
                    'Böblingen': (9.011, 48.686, 'green'),
                    'Hochdorf': (9.002, 48.886, 'green'),
                    'Pforzheim': (8.704, 48.891, 'green'),
                    'Sindelfingen': (9.005, 48.709, 'green'),
               }
        )
    
    # Show GUI
    root = tk.Tk()
    
    # Create canvas for image with exact PIL image size
    canvas = tk.Canvas(root, bg='black', width=512, height=512)
    canvas.pack()
    
    # Generate initial image
    radar.load_and_process_data(use_local=False)
    update_image_in_gui()
    
    # Start auto-update thread
    update_thread = threading.Thread(target=auto_update_loop, daemon=True)
    update_thread.start()
    
    root.mainloop()
    
if __name__ == "__main__":
    main()