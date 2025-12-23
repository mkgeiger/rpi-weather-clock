#!/usr/bin/env python3

from tkinter import *
from tkinter import TclError
import math
import time
import os
import threading
import signal
import gc
import atexit
from PIL import Image, ImageTk, ImageDraw, ImageFont
import urllib.request
import io
from io import BytesIO
from datetime import datetime
import json
import requests
import paho.mqtt.client as mqtt
from RadarProcessor import RadarProcessor
#import RPi.GPIO as GPIO

script_dir = None
window = None
canvas = None

# Global radar processor instance
radar = None

# Shutdown flag for clean exit
shutdown_flag = False
mqtt_poll_count = 0
mqtt_last_poll_time = 0
mqtt_connected = False
mqtt_reconnect_count = 0
mqtt_last_successful_time = 0
mqtt_connection_stale_threshold = 30  # Consider connection stale after 30 seconds of no activity

# local settings
old_time = time.strftime('%H:%M:%S')
longitude = "8.863"
latitude  = "48.808"
timezone = "Europe/Berlin"
zoom = 11
radar_background = "esri_topo"

# mqtt settings
mqtt_user = "**********"
mqtt_password = "****************"
mqtt_broker_address = "192.168.1.10"
mqtt_port = 1883
mqtt_topic_pressure = "/outdoor/pressure"
mqtt_topic_outtemperature = "/outdoor/temperature"
mqtt_topic_outhumidity = "/outdoor/humidity"
mqtt_topic_intemperature = "/483fdaaaceba/temperature"
mqtt_topic_inhumidity = "/483fdaaaceba/humidity"
mqtt_topic_staticiaq = "/483fdaaaceba/staticiaq"
mqtt_topic_ppurchase = "/00d0935D9eb9/ppurchase"
mqtt_topic_pfeed = "/00d0935D9eb9/pfeed"
mqtt_topic_pconsume = "/00d0935D9eb9/pconsume"
mqtt_topic_pgenerate = "/00d0935D9eb9/pgenerate"
mqtt_topic_pdischarge = "/00d0935D9eb9/pdischarge"
mqtt_topic_pcharge = "/00d0935D9eb9/pcharge"
mqtt_topic_sbatcharge = "/00d0935D9eb9/sbatcharge"
mqtt_topic_eyield = "/00d0935D9eb9/eyield"
mqtt_topic_eabsorb = "/00d0935D9eb9/eabsorb"

# coordinates
big_day_weather_x = 512
big_day_weather_y = 160
day_weather_x    = 2
day_weather_y    = 512
weathermap_x     = 0
weathermap_y     = 0
clock_x          = 672
clock_y          =   0
intemperature_x  = 672
intemperature_y  = 320
inhumidity_x     = 672
inhumidity_y     = 352
outtemperature_x = 672
outtemperature_y = 160
outhumidity_x    = 512
outhumidity_y    = 288
pressure_x       = 672
pressure_y       = 288
staticiaq_x      = 512
staticiaq_y      = 0
pconsume_x       = 512
pconsume_y       = 416
pgenerate_x      = 512
pgenerate_y      = 448
pdischarge_x     = 512
pdischarge_y     = 480
ppurchase_x      = 672
ppurchase_y      = 416
pfeed_x          = 672
pfeed_y          = 448
pcharge_x        = 672
pcharge_y        = 480
eabsorb_x        = 832
eabsorb_y        = 416
eyield_x         = 832
eyield_y         = 448
sbatcharge_x     = 832
sbatcharge_y     = 480

# variables to hold measured values
mqtt_intemperature = "--.-"
dwd_intemperature = "--.-"
mqtt_inhumidity = "---.-"
dwd_inhumidity = "---.-"
mqtt_outtemperature = "--.-"
dwd_outtemperature = "--.-"
mqtt_outhumidity = "---.-"
dwd_outhumidity = "---.-"
mqtt_pressure = "----.-"
dwd_pressure = "----.-"
mqtt_staticiaq = "---.-"
mqtt_ppurchase = "-----"
mqtt_pfeed = "-----"
mqtt_pconsume = "-----"
mqtt_pgenerate = "-----"
mqtt_pdischarge = "-----"
mqtt_pcharge = "-----"
mqtt_eabsorb = "-----.-"
mqtt_eyield = "-----.-"
mqtt_sbatcharge = "--"

# Previous values to track changes and avoid unnecessary redraws
prev_intemperature = None
prev_inhumidity = None
prev_outtemperature = None
prev_outhumidity = None
prev_staticiaq = None
prev_ppurchase = None
prev_pfeed = None
prev_pconsume = None
prev_pgenerate = None
prev_pdischarge = None
prev_pcharge = None
prev_eabsorb = None
prev_eyield = None
prev_sbatcharge = None

# display settings
display_on_time = 3000  # 5min
display_onoff = "ON"

class circularlist(object):
    def __init__(self, size, data = []):
        """Initialization"""
        self.index = 0
        self.size = size
        self._data = list(data)[-size:]

    def append(self, value):
        """Append an element"""
        if len(self._data) == self.size:
            self._data[self.index] = value
        else:
            self._data.append(value)
        self.index = (self.index + 1) % self.size

    def length(self):
        return(len(self._data))

    def __getitem__(self, key):
        """Get element by index, relative to the current index"""
        if len(self._data) == self.size:
            return(self._data[(key + self.index) % self.size])
        else:
            return(self._data[key])

    def __repr__(self):
        """Return string representation"""
        return (self._data[self.index:] + self._data[:self.index]).__repr__() + ' (' + str(len(self._data))+'/{} items)'.format(self.size)

def calc_pressure_tendency(l, start_index, end_index):
    # define tendency by linear regression
    avr_x = sum([x for x in range(start_index, end_index)]) / (end_index - start_index)
    avr_y = sum([l[x] for x in range(start_index, end_index)]) / (end_index - start_index)
    m = sum([(x - avr_x) * (l[x] - avr_y) for x in range(start_index, end_index)]) / sum([(x - avr_x) * (x - avr_x) for x in range(start_index, end_index)])
    return (m)

def get_pressure_tendency_icon(t1, t2, t3):
    global script_dir

    # zone limit 0.1 hPa
    th =  0.1
    tl = -0.1

    if (t1 <= tl) and (t2 <= tl) and (t3 <= tl):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_7.png"))
    if (t1 <= tl) and (t2 <= tl) and (t3 > tl) and (t3 <= th):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_6.png"))
    if (t1 <= tl) and (t2 <= tl) and (t3 > th):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_5.png"))
    if (t1 <= tl) and (t2 > tl) and (t2 <= th) and (t3 <= tl):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_7.png"))
    if (t1 <= tl) and (t2 > tl) and (t2 <= th) and (t3 > tl) and (t3 <= th):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_4.png"))
    if (t1 <= tl) and (t2 > tl) and (t2 <= th) and (t3 > th):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_4.png"))
    if (t1 <= tl) and (t2 > th) and (t3 <= tl):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_7.png"))
    if (t1 <= tl) and (t2 > th) and (t3 > tl) and (t3 <= th):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_4.png"))
    if (t1 <= tl) and (t2 > th) and (t3 > th):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_3.png"))
    if (t1 > tl) and (t1 <= th) and (t2 <= tl) and (t3 <= tl):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_8.png"))
    if (t1 > tl) and (t1 <= th) and (t2 <= tl) and (t3 > tl) and (t3 <= th):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_4.png"))
    if (t1 > tl) and (t1 <= th) and (t2 <= tl) and (t3 > th):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_4.png"))
    if (t1 > tl) and (t1 <= th) and (t2 > tl) and (t2 <= th) and (t3 <= tl):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_4.png"))
    if (t1 > tl) and (t1 <= th) and (t2 > tl) and (t2 <= th) and (t3 > tl) and (t3 <= th):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_4.png"))
    if (t1 > tl) and (t1 <= th) and (t2 > tl) and (t2 <= th) and (t3 > th):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_4.png"))
    if (t1 > tl) and (t1 <= th) and (t2 > th) and (t3 <= tl):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_4.png"))
    if (t1 > tl) and (t1 <= th) and (t2 > th) and (t3 > tl) and (t3 <= th):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_4.png"))
    if (t1 > tl) and (t1 <= th) and (t2 > th) and (t3 > th):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_3.png"))
    if (t1 > th) and (t2 <= tl) and (t3 <= tl):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_8.png"))
    if (t1 > th) and (t2 <= tl) and (t3 > tl) and (t3 <= th):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_4.png"))
    if (t1 > th) and (t2 <= tl) and (t3 > th):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_2.png"))
    if (t1 > th) and (t2 > tl) and (t2 <= th) and (t3 <= tl):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_4.png"))
    if (t1 > th) and (t2 > tl) and (t2 <= th) and (t3 > tl) and (t3 <= th):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_4.png"))
    if (t1 > th) and (t2 > tl) and (t2 <= th) and (t3 > th):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_2.png"))
    if (t1 > th) and (t2 > th) and (t3 <= tl):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_0.png"))
    if (t1 > th) and (t2 > th) and (t3 > tl) and (t3 <= th):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_1.png"))
    if (t1 > th) and (t2 > th) and (t3 > th):
        icon_pre = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_2.png"))
    return (icon_pre)

def update_intemperature():
    global script_dir
    global prev_intemperature

    # Only update if value has changed
    if mqtt_intemperature == prev_intemperature:
        return
    prev_intemperature = mqtt_intemperature

    # Create a temporary image to draw on
    temp_image = Image.new("RGBA", (353, 31), (0, 0, 0, 0))
    draw = ImageDraw.Draw(temp_image)
    draw.rectangle((0, 0, 352, 30), fill="#202020")
    # Draw the text onto the temporary image
    font = ImageFont.truetype(os.path.join(script_dir, "arial.ttf"), 27)
    draw.text((4, 0), "Raumtemperatur: ", font=font, fill="#ffffff")
    draw.text((219, 0), mqtt_intemperature + " °C", font=font, fill="#ffff00")
    # Convert to PhotoImage and display on canvas
    photo_image = safe_create_photoimage(temp_image)
    if photo_image:
        canvas.delete('intemperature')
        canvas.create_image(intemperature_x + 1, intemperature_y + 1, anchor = NW, image = photo_image, tags=('intemperature'))
        # prevent garbage collection
        canvas.intemperature = photo_image
    temp_image.close()  # Close PIL image

def update_inhumidity():
    global script_dir
    global prev_inhumidity

    # Only update if value has changed
    if mqtt_inhumidity == prev_inhumidity:
        return
    prev_inhumidity = mqtt_inhumidity

    # Create a temporary image to draw on
    temp_image = Image.new("RGBA", (353, 31), (0, 0, 0, 0))
    draw = ImageDraw.Draw(temp_image)
    draw.rectangle((0, 0, 352, 30), fill="#202020")
    # Draw the text onto the temporary image
    font = ImageFont.truetype(os.path.join(script_dir, "arial.ttf"), 27)
    draw.text((4, 0), "Raumluftfeuchte: ", font=font, fill="#ffffff")
    draw.text((216, 0), mqtt_inhumidity + " %rF", font=font, fill="#ffff00")
    # Convert to PhotoImage and display on canvas
    photo_image = safe_create_photoimage(temp_image)
    if photo_image:
        canvas.delete('inhumidity')
        canvas.create_image(inhumidity_x + 1, inhumidity_y + 1, anchor = NW, image = photo_image, tags=('inhumidity'))
        # prevent garbage collection
        canvas.inhumidity = photo_image
    temp_image.close()  # Close PIL image

    # Create a temporary image to draw on
    temp_image = Image.new("RGBA", (353, 31), (0, 0, 0, 0))
    draw = ImageDraw.Draw(temp_image)
    draw.rectangle((0, 0, 352, 30), fill="#202020")
    # Convert to PhotoImage and display on canvas
    photo_image = safe_create_photoimage(temp_image)
    if photo_image:
        canvas.delete('inhumidity_empty')
        canvas.create_image(inhumidity_x + 1, inhumidity_y + 33, anchor = NW, image = photo_image, tags=('inhumidity_empty'))
        # prevent garbage collection
        canvas.inhumidity_empty = photo_image
    temp_image.close()  # Close PIL image

def update_outtemperature():
    global script_dir
    global prev_outtemperature

    # Only update if value has changed
    if mqtt_outtemperature == prev_outtemperature:
        return
    prev_outtemperature = mqtt_outtemperature

    # Create a temporary image to draw on
    temp_image = Image.new("RGBA", (353, 127), (0, 0, 0, 0))
    draw = ImageDraw.Draw(temp_image)
    draw.rectangle((0, 0, 352, 126), fill="#303030")
    # Paste the icon onto the temporary image
    icon = Image.open(os.path.join(script_dir, "Icons/temp.png")).convert("RGBA")
    temp_image.paste(icon, (5, 4), icon)
    # Draw the text onto the temporary image
    temp_font = ImageFont.truetype(os.path.join(script_dir, "arial.ttf"), 125)
    unit_font = ImageFont.truetype(os.path.join(script_dir, "arial.ttf"), 27)
    draw.text((34, -1), "°C", font=unit_font, fill="#ffffff")
    if (mqtt_outtemperature == "--.-"):
        color = "#ffffff"
    else:
        temperature = float(mqtt_outtemperature)

        if (temperature < -10):
            color = "#0080ff"
        elif ((temperature >= -10) and (temperature < -5)):
            color = "#3380ff"
        elif ((temperature >= -5) and (temperature < 0)):
            color = "#6680ff"
        elif ((temperature >= 0) and (temperature < 5)):
            color = "#9980ff"
        elif ((temperature >= 5) and (temperature < 10)):
            color = "#cc80ff"
        elif ((temperature >= 10) and (temperature < 15)):
            color = "#ff80cc"
        elif ((temperature >= 15) and (temperature < 20)):
            color = "#ff8099"
        elif ((temperature >= 20) and (temperature < 25)):
            color = "#ff8066"
        elif ((temperature >= 25) and (temperature < 30)):
            color = "#ff8033"
        else:
            color = "#ff8000"
    draw.text((53, 0), mqtt_outtemperature, font=temp_font, fill=color)

    # Convert to PhotoImage and display on canvas
    photo_image = safe_create_photoimage(temp_image)
    if photo_image:
        canvas.delete('outtemperature')
        canvas.create_image(outtemperature_x + 1, outtemperature_y + 1, anchor = NW, image = photo_image, tags=('outtemperature'))
        # prevent garbage collection
        canvas.outtemperature = photo_image
    temp_image.close()  # Close PIL image

def update_outhumidity():
    global script_dir
    global prev_outhumidity

    # Only update if value has changed
    if mqtt_outhumidity == prev_outhumidity:
        return
    prev_outhumidity = mqtt_outhumidity

    # Create a temporary image to draw on
    temp_image = Image.new("RGBA", (159, 127), (0, 0, 0, 0))
    draw = ImageDraw.Draw(temp_image)
    draw.rectangle((0, 0, 158, 126), fill="#202020")
    # Paste the icon onto the temporary image
    if (mqtt_outhumidity != "---.-"):
        level = int(float(mqtt_outhumidity) * 1.07)
        icon_hum_blue = Image.open(os.path.join(script_dir, "Icons/humidity_blue.png")).convert("RGBA").crop([0, 125 - 9 - level, 125, 125])
        temp_image.paste(icon_hum_blue, (16, 126 - 9 - level), icon_hum_blue)
        icon_hum_grey = Image.open(os.path.join(script_dir, "Icons/humidity_grey.png")).convert("RGBA").crop([0, 0, 125, 125 - 9 - level])
        temp_image.paste(icon_hum_grey, (16, 1), icon_hum_grey)
    else:
        icon_hum = Image.open(os.path.join(script_dir, "Icons/humidity_grey.png")).convert("RGBA")
        temp_image.paste(icon_hum, (16, 1), icon_hum)
    # Convert to PhotoImage and display on canvas
    photo_image = safe_create_photoimage(temp_image)
    if photo_image:
        canvas.delete('outhumidity')
        canvas.create_image(outhumidity_x + 1, outhumidity_y + 1, anchor = NW, image = photo_image, tags=('outhumidity'))
        # prevent garbage collection
        canvas.outhumidity = photo_image
    temp_image.close()  # Close PIL image

def update_staticiaq():
    global script_dir
    global prev_staticiaq

    # Only update if value has changed
    if mqtt_staticiaq == prev_staticiaq:
        return
    prev_staticiaq = mqtt_staticiaq

    # Create a temporary image to draw on
    temp_image = Image.new("RGBA", (159, 159), (0, 0, 0, 0))
    draw = ImageDraw.Draw(temp_image)
    draw.rectangle((0, 0, 158, 158), fill="#202020")
    # Paste the icon onto the temporary image
    if (mqtt_staticiaq != "---.-"):
        if (float(mqtt_staticiaq) < 100.0):
            icon = Image.open(os.path.join(script_dir, "Icons/IAQ_good.png")).convert("RGBA")
        elif (float(mqtt_staticiaq) >= 100.0) and (float(mqtt_staticiaq) <= 200.0):
            icon = Image.open(os.path.join(script_dir, "Icons/IAQ_medium.png")).convert("RGBA")
        else:
            icon = Image.open(os.path.join(script_dir, "Icons/IAQ_bad.png")).convert("RGBA")
    else:
        icon = Image.open(os.path.join(script_dir, "Icons/IAQ_good.png")).convert("RGBA")
    temp_image.paste(icon, (17, 17), icon)
    # Convert to PhotoImage and display on canvas
    photo_image = safe_create_photoimage(temp_image)
    if photo_image:
        canvas.delete('staticiaq')
        canvas.create_image(staticiaq_x + 1, staticiaq_y + 1, anchor = NW, image = photo_image, tags=('staticiaq'))
        # prevent garbage collection
        canvas.staticiaq = photo_image
    temp_image.close()  # Close PIL image

def update_pressure():
    global script_dir

    # Create a temporary image to draw on
    temp_image = Image.new("RGBA", (353, 31), (0, 0, 0, 0))
    draw = ImageDraw.Draw(temp_image)
    draw.rectangle((0, 0, 352, 30), fill="#202020")
    # Paste the icon onto the temporary image
    if (plist.length() == 18):
        tend1 = calc_pressure_tendency(plist, 0, 6)
        tend2 = calc_pressure_tendency(plist, 6, 12)
        tend3 = calc_pressure_tendency(plist, 12, 18)
        icon = get_pressure_tendency_icon(tend1, tend2, tend3)
    else:
        icon = Image.open(os.path.join(script_dir, "Icons/pressure_tendency_4.png")).convert("RGBA")
    temp_image.paste(icon, (290, 1), icon)
    # Draw the text onto the temporary image
    font = ImageFont.truetype(os.path.join(script_dir, "arial.ttf"), 27)
    draw.text((4, 0), "Luftdruck: ", font=font, fill="#ffffff")
    draw.text((130, 0), mqtt_pressure + " hPa", font=font, fill="#ffff00")
    # Convert to PhotoImage and display on canvas
    photo_image = safe_create_photoimage(temp_image)
    if photo_image:
        canvas.delete('pressure')
        canvas.create_image(pressure_x + 1, pressure_y + 1, anchor = NW, image = photo_image, tags=('pressure'))
        # prevent garbage collection
        canvas.pressure = photo_image
    temp_image.close()  # Close PIL image

def update_ppurchase():
    global script_dir
    global prev_ppurchase

    # Only update if value has changed
    if mqtt_ppurchase == prev_ppurchase:
        return
    prev_ppurchase = mqtt_ppurchase

    # Create a temporary image to draw on
    temp_image = Image.new("RGBA", (159, 31), (0, 0, 0, 0))
    draw = ImageDraw.Draw(temp_image)
    draw.rectangle((0, 0, 158, 30), fill="#303030")
    # Paste the icon onto the temporary image
    icon = Image.open(os.path.join(script_dir, "Icons/P_purchase.png")).convert("RGBA")
    temp_image.paste(icon, (0, 0), icon)
    # Draw the text onto the temporary image
    font = ImageFont.truetype(os.path.join(script_dir, "arial.ttf"), 27)
    draw.text((36, 0), mqtt_ppurchase.split(".")[0] + " W", font=font, fill="#ff0000")
    # Convert to PhotoImage and display on canvas
    photo_image = safe_create_photoimage(temp_image)
    if photo_image:
        canvas.delete('ppurchase')
        canvas.create_image(ppurchase_x + 1, ppurchase_y + 1, anchor = NW, image = photo_image, tags=('ppurchase'))
        # prevent garbage collection
        canvas.ppurchase = photo_image
    temp_image.close()  # Close PIL image

def update_pfeed():
    global script_dir
    global prev_pfeed

    # Only update if value has changed
    if mqtt_pfeed == prev_pfeed:
        return
    prev_pfeed = mqtt_pfeed

    # Create a temporary image to draw on
    temp_image = Image.new("RGBA", (159, 31), (0, 0, 0, 0))
    draw = ImageDraw.Draw(temp_image)
    draw.rectangle((0, 0, 158, 30), fill="#303030")
    # Paste the icon onto the temporary image
    icon = Image.open(os.path.join(script_dir, "Icons/P_feed.png")).convert("RGBA")
    temp_image.paste(icon, (0, 0), icon)
    # Draw the text onto the temporary image
    font = ImageFont.truetype(os.path.join(script_dir, "arial.ttf"), 27)
    draw.text((36, 0), mqtt_pfeed.split(".")[0] + " W", font=font, fill="#ffff00")
    # Convert to PhotoImage and display on canvas
    photo_image = safe_create_photoimage(temp_image)
    if photo_image:
        canvas.delete('pfeed')
        canvas.create_image(pfeed_x + 1, pfeed_y + 1, anchor = NW, image = photo_image, tags=('pfeed'))
        # prevent garbage collection
        canvas.pfeed = photo_image
    temp_image.close()  # Close PIL image

def update_pconsume():
    global script_dir
    global prev_pconsume

    # Only update if value has changed
    if mqtt_pconsume == prev_pconsume:
        return
    prev_pconsume = mqtt_pconsume

    # Create a temporary image to draw on
    temp_image = Image.new("RGBA", (159, 31), (0, 0, 0, 0))
    draw = ImageDraw.Draw(temp_image)
    draw.rectangle((0, 0, 158, 30), fill="#303030")
    # Paste the icon onto the temporary image
    icon = Image.open(os.path.join(script_dir, "Icons/P_consume.png")).convert("RGBA")
    temp_image.paste(icon, (0, 0), icon)
    # Draw the text onto the temporary image
    font = ImageFont.truetype(os.path.join(script_dir, "arial.ttf"), 27)
    draw.text((36, 0), mqtt_pconsume.split(".")[0] + " W", font=font, fill="#ffffff")
    # Convert to PhotoImage and display on canvas
    photo_image = safe_create_photoimage(temp_image)
    if photo_image:
        canvas.delete('pconsume')
        canvas.create_image(pconsume_x + 1, pconsume_y + 1, anchor = NW, image = photo_image, tags=('pconsume'))
        # prevent garbage collection
        canvas.ppconsume = photo_image
    temp_image.close()  # Close PIL image

def update_pgenerate():
    global script_dir
    global prev_pgenerate

    # Only update if value has changed
    if mqtt_pgenerate == prev_pgenerate:
        return
    prev_pgenerate = mqtt_pgenerate

    # Create a temporary image to draw on
    temp_image = Image.new("RGBA", (159, 31), (0, 0, 0, 0))
    draw = ImageDraw.Draw(temp_image)
    draw.rectangle((0, 0, 158, 30), fill="#303030")
    # Paste the icon onto the temporary image
    icon = Image.open(os.path.join(script_dir, "Icons/P_generate.png")).convert("RGBA")
    temp_image.paste(icon, (0, 0), icon)
    # Draw the text onto the temporary image
    font = ImageFont.truetype(os.path.join(script_dir, "arial.ttf"), 27)
    draw.text((36, 0), mqtt_pgenerate.split(".")[0] + " W", font=font, fill="#00ff00")
    # Convert to PhotoImage and display on canvas
    photo_image = safe_create_photoimage(temp_image)
    if photo_image:
        canvas.delete('pgenerate')
        canvas.create_image(pgenerate_x + 1, pgenerate_y + 1, anchor = NW, image = photo_image, tags=('pgenerate'))
        # prevent garbage collection
        canvas.ppgenerate = photo_image
    temp_image.close()  # Close PIL image

def update_pdischarge():
    global script_dir
    global prev_pdischarge

    # Only update if value has changed
    if mqtt_pdischarge == prev_pdischarge:
        return
    prev_pdischarge = mqtt_pdischarge

    # Create a temporary image to draw on
    temp_image = Image.new("RGBA", (159, 31), (0, 0, 0, 0))
    draw = ImageDraw.Draw(temp_image)
    draw.rectangle((0, 0, 158, 30), fill="#303030")
    # Paste the icon onto the temporary image
    icon = Image.open(os.path.join(script_dir, "Icons/P_batdischarge.png")).convert("RGBA")
    temp_image.paste(icon, (0, 0), icon)
    # Draw the text onto the temporary image
    font = ImageFont.truetype(os.path.join(script_dir, "arial.ttf"), 27)
    draw.text((36, 0), mqtt_pdischarge.split(".")[0] + " W", font=font, fill="#8080ff")
    # Convert to PhotoImage and display on canvas
    photo_image = safe_create_photoimage(temp_image)
    if photo_image:
        canvas.delete('pdischarge')
        canvas.create_image(pdischarge_x + 1, pdischarge_y + 1, anchor = NW, image = photo_image, tags=('pdischarge'))
        # prevent garbage collection
        canvas.ppdischarge = photo_image
    temp_image.close()  # Close PIL image

def update_pcharge():
    global script_dir
    global prev_pcharge

    # Only update if value has changed
    if mqtt_pcharge == prev_pcharge:
        return
    prev_pcharge = mqtt_pcharge

    # Create a temporary image to draw on
    temp_image = Image.new("RGBA", (159, 31), (0, 0, 0, 0))
    draw = ImageDraw.Draw(temp_image)
    draw.rectangle((0, 0, 158, 30), fill="#303030")
    # Paste the icon onto the temporary image
    icon = Image.open(os.path.join(script_dir, "Icons/P_batcharge.png")).convert("RGBA")
    temp_image.paste(icon, (0, 0), icon)
    # Draw the text onto the temporary image
    font = ImageFont.truetype(os.path.join(script_dir, "arial.ttf"), 27)
    draw.text((36, 0), mqtt_pcharge.split(".")[0] + " W", font=font, fill="#8080ff")
    # Convert to PhotoImage and display on canvas
    photo_image = safe_create_photoimage(temp_image)
    if photo_image:
        canvas.delete('pcharge')
        canvas.create_image(pcharge_x + 1, pcharge_y + 1, anchor = NW, image = photo_image, tags=('pcharge'))
        # prevent garbage collection
        canvas.ppcharge = photo_image
    temp_image.close()  # Close PIL image

def update_eabsorb():
    global script_dir
    global prev_eabsorb

    # Only update if value has changed
    if mqtt_eabsorb == prev_eabsorb:
        return
    prev_eabsorb = mqtt_eabsorb

    # Create a temporary image to draw on
    temp_image = Image.new("RGBA", (191, 31), (0, 0, 0, 0))
    draw = ImageDraw.Draw(temp_image)
    draw.rectangle((0, 0, 190, 30), fill="#303030")
    # Paste the icon onto the temporary image
    icon = Image.open(os.path.join(script_dir, "Icons/E_absorb.png")).convert("RGBA")
    temp_image.paste(icon, (0, 0), icon)
    # Draw the text onto the temporary image
    font = ImageFont.truetype(os.path.join(script_dir, "arial.ttf"), 27)
    draw.text((36, 0), mqtt_eabsorb.split(".")[0] + " kWh", font=font, fill="#ff0000")
    # Convert to PhotoImage and display on canvas
    photo_image = safe_create_photoimage(temp_image)
    if photo_image:
        canvas.delete('eabsorb')
        canvas.create_image(eabsorb_x + 1, eabsorb_y + 1, anchor = NW, image = photo_image, tags=('eabsorb'))
        # prevent garbage collection
        canvas.peabsorb = photo_image
    temp_image.close()  # Close PIL image

def update_eyield():
    global script_dir
    global prev_eyield

    # Only update if value has changed
    if mqtt_eyield == prev_eyield:
        return
    prev_eyield = mqtt_eyield

    # Create a temporary image to draw on
    temp_image = Image.new("RGBA", (191, 31), (0, 0, 0, 0))
    draw = ImageDraw.Draw(temp_image)
    draw.rectangle((0, 0, 190, 30), fill="#303030")
    # Paste the icon onto the temporary image
    icon = Image.open(os.path.join(script_dir, "Icons/E_yield.png")).convert("RGBA")
    temp_image.paste(icon, (0, 0), icon)
    # Draw the text onto the temporary image
    font = ImageFont.truetype(os.path.join(script_dir, "arial.ttf"), 27)
    draw.text((36, 0), mqtt_eyield.split(".")[0] + " kWh", font=font, fill="#ffff00")
    # Convert to PhotoImage and display on canvas
    photo_image = safe_create_photoimage(temp_image)
    if photo_image:
        canvas.delete('eyield')
        canvas.create_image(eyield_x + 1, eyield_y + 1, anchor = NW, image = photo_image, tags=('eyield'))
        # prevent garbage collection
        canvas.peyield = photo_image
    temp_image.close()  # Close PIL image

def update_sbatcharge():
    global script_dir
    global prev_sbatcharge

    # Only update if value has changed
    if mqtt_sbatcharge == prev_sbatcharge:
        return
    prev_sbatcharge = mqtt_sbatcharge

    # Create a temporary image to draw on
    temp_image = Image.new("RGBA", (191, 31), (0, 0, 0, 0))
    draw = ImageDraw.Draw(temp_image)
    draw.rectangle((0, 0, 190, 30), fill="#303030")
    # Paste the icon onto the temporary image
    icon = Image.open(os.path.join(script_dir, "Icons/S_batcharge.png")).convert("RGBA")
    temp_image.paste(icon, (0, 0), icon)
    # Draw the text onto the temporary image
    font = ImageFont.truetype(os.path.join(script_dir, "arial.ttf"), 27)
    draw.text((36, 0), mqtt_sbatcharge + " %", font=font, fill="#8080ff")
    # Convert to PhotoImage and display on canvas
    photo_image = safe_create_photoimage(temp_image)
    if photo_image:
        canvas.delete('sbatcharge')
        canvas.create_image(sbatcharge_x + 1, sbatcharge_y + 1, anchor = NW, image = photo_image, tags=('sbatcharge'))
        # prevent garbage collection
        canvas.psbatcharge = photo_image
    temp_image.close()  # Close PIL image

def on_message(client, userdata, message):
    global mqtt_intemperature
    global mqtt_inhumidity
    global mqtt_outtemperature
    global mqtt_outhumidity
    global mqtt_pressure
    global mqtt_staticiaq
    global mqtt_ppurchase
    global mqtt_pfeed
    global mqtt_pconsume
    global mqtt_pgenerate
    global mqtt_pdischarge
    global mqtt_pcharge
    global mqtt_eabsorb
    global mqtt_eyield
    global mqtt_sbatcharge

    msg = str(message.payload.decode("utf-8"))
    #print(f"MQTT message received - Topic: {message.topic}, Message: {msg}")
    
    def schedule_update(update_func):
        """Schedule GUI update in main thread to prevent threading issues"""
        try:
            if window and hasattr(window, 'winfo_exists') and window.winfo_exists():
                window.after(0, update_func)
        except (RuntimeError, TclError):
            pass
    
    if (message.topic == mqtt_topic_intemperature):
        mqtt_intemperature = msg
        schedule_update(update_intemperature)
    if (message.topic == mqtt_topic_inhumidity):
        mqtt_inhumidity = msg
        schedule_update(update_inhumidity)
    if (message.topic == mqtt_topic_outtemperature):
        mqtt_outtemperature = msg
        schedule_update(update_outtemperature)
    if (message.topic == mqtt_topic_outhumidity):
        mqtt_outhumidity = msg
        schedule_update(update_outhumidity)
    if (message.topic == mqtt_topic_pressure):
        mqtt_pressure = msg
        try:
           plist.append(float(mqtt_pressure))
        except:
           print("Pressure value has wrong format.")
        schedule_update(update_pressure)
    if (message.topic == mqtt_topic_staticiaq):
        mqtt_staticiaq = msg
        schedule_update(update_staticiaq)
    if (message.topic == mqtt_topic_ppurchase):
        mqtt_ppurchase = msg
        schedule_update(update_ppurchase)
    if (message.topic == mqtt_topic_pfeed):
        mqtt_pfeed = msg
        schedule_update(update_pfeed)
    if (message.topic == mqtt_topic_pconsume):
        mqtt_pconsume = msg
        schedule_update(update_pconsume)
    if (message.topic == mqtt_topic_pgenerate):
        mqtt_pgenerate = msg
        schedule_update(update_pgenerate)
    if (message.topic == mqtt_topic_pdischarge):
        mqtt_pdischarge = msg
        schedule_update(update_pdischarge)
    if (message.topic == mqtt_topic_pcharge):
        mqtt_pcharge = msg
        schedule_update(update_pcharge)
    if (message.topic == mqtt_topic_eabsorb):
        mqtt_eabsorb = msg
        schedule_update(update_eabsorb)
    if (message.topic == mqtt_topic_eyield):
        mqtt_eyield = msg
        schedule_update(update_eyield)
    if (message.topic == mqtt_topic_sbatcharge):
        mqtt_sbatcharge = msg
        schedule_update(update_sbatcharge)

def on_connect(client, userdata, flags, reason_code, properties):
    global mqtt_connected, mqtt_last_successful_time, mqtt_reconnect_count
    if reason_code.is_failure:
        print(f"MQTT connection failed with code {reason_code}")
        mqtt_connected = False
    else:
        print(f"MQTT connected successfully (rc={reason_code})")
        mqtt_connected = True
        mqtt_last_successful_time = time.time()
        mqtt_reconnect_count = 0  # Reset counter on successful connection
        # Subscribe to all topics
        topics = [
            mqtt_topic_intemperature, mqtt_topic_inhumidity,
            mqtt_topic_outtemperature, mqtt_topic_outhumidity,
            mqtt_topic_pressure, mqtt_topic_staticiaq,
            mqtt_topic_ppurchase, mqtt_topic_pfeed,
            mqtt_topic_pconsume, mqtt_topic_pgenerate,
            mqtt_topic_pdischarge, mqtt_topic_pcharge,
            mqtt_topic_eabsorb, mqtt_topic_eyield,
            mqtt_topic_sbatcharge
        ]
        for topic in topics:
            client.subscribe(topic)
        print(f"Total: {len(topics)} MQTT topics subscription attempts completed")

def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    global mqtt_connected, mqtt_reconnect_count
    mqtt_connected = False
    # Reset reconnection counter on disconnect to allow fresh attempts
    if reason_code != 0:
        print(f"MQTT unexpected disconnection (rc={reason_code}) - resetting reconnection counter")
        if reason_code == 5:  # MQTT_ERR_CONN_LOST - likely broker restart
            print("Disconnection appears to be due to broker restart or network loss")
        mqtt_reconnect_count = 0  # Reset counter for fresh attempts after unexpected disconnect
    else:
        print("MQTT disconnected normally")

def open_weather_icon(icon):
    global script_dir

    if (icon == "clear-day"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/clear-day.png")).convert("RGBA")
    elif (icon == "clear-night"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/clear-night.png")).convert("RGBA")
    elif (icon == "cloudy"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/cloudy.png")).convert("RGBA")
    elif (icon == "fog"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/fog.png")).convert("RGBA")
    elif (icon == "hail"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/hail.png")).convert("RGBA")
    elif (icon == "partly-cloudy-day"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/partly-cloudy-day.png")).convert("RGBA")
    elif (icon == "partly-cloudy-day-rain"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/partly-cloudy-day-rain.png")).convert("RGBA")
    elif (icon == "partly-cloudy-day-snow"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/partly-cloudy-day-snow.png")).convert("RGBA")
    elif (icon == "partly-cloudy-night"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/partly-cloudy-night.png")).convert("RGBA")
    elif (icon == "partly-cloudy-night-rain"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/partly-cloudy-night-rain.png")).convert("RGBA")
    elif (icon == "partly-cloudy-night-snow"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/partly-cloudy-night-snow.png")).convert("RGBA")
    elif (icon == "rain"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/rain.png")).convert("RGBA")
    elif (icon == "sleet"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/sleet.png")).convert("RGBA")
    elif (icon == "snow"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/snow.png")).convert("RGBA")
    elif (icon == "thunderstorm"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/thunderstorm.png")).convert("RGBA")
    elif (icon == "wind"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/wind.png")).convert("RGBA")
    else:
        weather_icon = None
    return weather_icon

def open_weather_icon_big(icon):
    global script_dir

    if (icon == "clear-day"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/clear-day-big.png")).convert("RGBA")
    elif (icon == "clear-night"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/clear-night-big.png")).convert("RGBA")
    elif (icon == "cloudy"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/cloudy-big.png")).convert("RGBA")
    elif (icon == "fog"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/fog-big.png")).convert("RGBA")
    elif (icon == "hail"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/hail-big.png")).convert("RGBA")
    elif (icon == "partly-cloudy-day"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/partly-cloudy-day-big.png")).convert("RGBA")
    elif (icon == "partly-cloudy-day-rain"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/partly-cloudy-day-rain-big.png")).convert("RGBA")
    elif (icon == "partly-cloudy-day-snow"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/partly-cloudy-day-snow-big.png")).convert("RGBA")
    elif (icon == "partly-cloudy-night"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/partly-cloudy-night-big.png")).convert("RGBA")
    elif (icon == "partly-cloudy-night-rain"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/partly-cloudy-night-rain-big.png")).convert("RGBA")
    elif (icon == "partly-cloudy-night-snow"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/partly-cloudy-night-snow-big.png")).convert("RGBA")
    elif (icon == "rain"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/rain-big.png")).convert("RGBA")
    elif (icon == "sleet"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/sleet-big.png")).convert("RGBA")
    elif (icon == "snow"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/snow-big.png")).convert("RGBA")
    elif (icon == "thunderstorm"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/thunderstorm-big.png")).convert("RGBA")
    elif (icon == "wind"):
        weather_icon = Image.open(os.path.join(script_dir, "Icons/wind-big.png")).convert("RGBA")
    else:
        weather_icon = None
    return weather_icon

def draw_weather(now_hour, first_hour, last_hour, start_pos, url):
    global script_dir

    x = start_pos
    try:
        Response = requests.get(url)
        WeatherData = Response.json()

        if (now_hour != -1):
            # Create a temporary image to draw on
            temp_image = Image.new("RGBA", (159, 127), (0, 0, 0, 0))
            draw = ImageDraw.Draw(temp_image)
            draw.rectangle((0, 0, 158, 126), fill="#303030")
            # Paste the icon onto the temporary image
            icon_now = str(WeatherData["weather"][now_hour]["icon"])
            icon = open_weather_icon_big(icon_now)
            if icon:
                temp_image.paste(icon, (16, 0), icon)
            # Convert to PhotoImage and display on canvas
            photo_image = safe_create_photoimage(temp_image)
            if photo_image:
                canvas.delete('now_weather')
                canvas.create_image(big_day_weather_x + 1, big_day_weather_y + 1, anchor = NW, image = photo_image, tags=('now_weather'))
                # prevent garbage collection
                canvas.now_weather = photo_image
            temp_image.close()  # Close PIL image

        for h in range(first_hour, last_hour+1, 4):
            icon_now = str(WeatherData["weather"][h]["icon"])
            cond = str(WeatherData["weather"][h]["condition"])
            temperature = str(WeatherData["weather"][h]["temperature"])
            pressure = str(WeatherData["weather"][h]["pressure_msl"])
            humidity = str(WeatherData["weather"][h]["relative_humidity"])
            precipitation = WeatherData["weather"][h]["precipitation"]
            if ((icon_now == "partly-cloudy-day" or icon_now == "partly-cloudy-night") and (cond == "rain" or cond == "snow")):
                icon_now = icon_now + '-' + cond;
            if (icon_now == "cloudy" and (cond == "rain" or cond == "snow") and precipitation > 0.2):
                icon_now = cond;

            # Create a temporary image to draw on
            temp_image = Image.new("RGBA", (170, 87), (0, 0, 0, 0))
            draw = ImageDraw.Draw(temp_image)
            draw.rectangle((0, 0, 169, 86), fill="#000000")
            # Paste the icon onto the temporary image
            icon = open_weather_icon(icon_now)
            if icon:
                temp_image.paste(icon, (0, 12), icon)
            # Draw the text onto the temporary image
            font = ImageFont.truetype(os.path.join(script_dir, "arial.ttf"), 27)
            font2 = ImageFont.truetype(os.path.join(script_dir, "arial.ttf"), 18)
            draw.text((66, 2), str(h) + ":00", font=font, fill="#ffffff")
            draw.text((66, 30), temperature + " °C", font=font2, fill="#ffff00")
            draw.text((66, 48), pressure + " hPa", font=font2, fill="#ffff00")
            draw.text((66, 66), humidity + " %rF", font=font2, fill="#ffff00")
            # Convert to PhotoImage and display on canvas
            photo_image = safe_create_photoimage(temp_image)
            if photo_image:
                canvas.delete('day_weather' + str(x))
                canvas.create_image(day_weather_x + x * 170 + 1, day_weather_y + 1, anchor = NW, image = photo_image, tags=('day_weather' + str(x)))
                # prevent garbage collection
                if not hasattr(canvas, 'dayhour_weather'):
                    canvas.dayhour_weather = {}
                canvas.dayhour_weather[x] = photo_image
            temp_image.close()  # Close PIL image
            x = x + 1
    except:
        print("Couldn't load weather data.")    

def update_day_weather():
    tc = time.time()
    tt = tc + 86400
    ty = tc - 86400
    today = datetime.fromtimestamp(tc).strftime('%Y-%m-%d')
    tomorrow = datetime.fromtimestamp(tt).strftime('%Y-%m-%d')
    yesterday = datetime.fromtimestamp(ty).strftime('%Y-%m-%d')
    hour = datetime.fromtimestamp(tc).strftime('%H')

    if (int(hour) < 3):
       # 23 from yesterday + 3, 7, 11, 15, 19 from today
       url = "https://api.brightsky.dev/weather?lat=" + latitude + "&lon=" + longitude + "&date=" + yesterday + "&tz=" +timezone
       draw_weather(-1, 23, 23, 0, url)
       url = "https://api.brightsky.dev/weather?lat=" + latitude + "&lon=" + longitude + "&date=" + today + "&tz=" +timezone
       draw_weather(int(hour), 3, 19, 1, url)
    elif (int(hour) >= 3) and (int(hour) < 7):
       # 3, 7, 11, 15, 19, 23 from today
       url = "https://api.brightsky.dev/weather?lat=" + latitude + "&lon=" + longitude + "&date=" + today + "&tz=" +timezone
       draw_weather(int(hour), 3, 23, 0, url)
    elif (int(hour) >= 7) and (int(hour) < 11):
       # 7, 11, 15, 19, 23 from today, 3 from tomorrow
       url = "https://api.brightsky.dev/weather?lat=" + latitude + "&lon=" + longitude + "&date=" + today + "&tz=" +timezone
       draw_weather(int(hour), 7, 23, 0, url)
       url = "https://api.brightsky.dev/weather?lat=" + latitude + "&lon=" + longitude + "&date=" + tomorrow + "&tz=" +timezone
       draw_weather(-1, 3, 3, 5, url)
    elif (int(hour) >= 11) and (int(hour) < 15):
       # 11, 15, 19, 23 from today, 3, 7 from tomorrow
       url = "https://api.brightsky.dev/weather?lat=" + latitude + "&lon=" + longitude + "&date=" + today + "&tz=" +timezone
       draw_weather(int(hour), 11, 23, 0, url)
       url = "https://api.brightsky.dev/weather?lat=" + latitude + "&lon=" + longitude + "&date=" + tomorrow + "&tz=" +timezone
       draw_weather(-1, 3, 7, 4, url)
    elif (int(hour) >= 15) and (int(hour) < 19):
       # 15, 19, 23 from today, 3, 7, 11 from tomorrow
       url = "https://api.brightsky.dev/weather?lat=" + latitude + "&lon=" + longitude + "&date=" + today + "&tz=" +timezone
       draw_weather(int(hour), 15, 23, 0, url)
       url = "https://api.brightsky.dev/weather?lat=" + latitude + "&lon=" + longitude + "&date=" + tomorrow + "&tz=" +timezone
       draw_weather(-1, 3, 11, 3, url)
    elif (int(hour) >= 19) and (int(hour) < 23):
       # 19, 23 from today, 3, 7, 11, 15 from tomorrow
       url = "https://api.brightsky.dev/weather?lat=" + latitude + "&lon=" + longitude + "&date=" + today + "&tz=" +timezone
       draw_weather(int(hour), 19, 23, 0, url)
       url = "https://api.brightsky.dev/weather?lat=" + latitude + "&lon=" + longitude + "&date=" + tomorrow + "&tz=" +timezone
       draw_weather(-1, 3, 15, 2, url)
    else:
       # 23 from today, 3, 7, 11, 15, 19 from tomorrow
       url = "https://api.brightsky.dev/weather?lat=" + latitude + "&lon=" + longitude + "&date=" + today + "&tz=" +timezone
       draw_weather(int(hour), 23, 23, 0, url)
       url = "https://api.brightsky.dev/weather?lat=" + latitude + "&lon=" + longitude + "&date=" + tomorrow + "&tz=" +timezone
       draw_weather(-1, 3, 19, 1, url)    
    # update every 10 min
    try:
        if not shutdown_flag and window and hasattr(window, 'winfo_exists'):
            if window.winfo_exists():
                window.after(600000, update_day_weather)
    except (RuntimeError, TclError):
        pass  # Main thread may no longer be in main loop

def display_on():
    global display_onoff
    if (display_onoff == "OFF"):
        display_onoff = "ON"
        os.system('vcgencmd display_power 1')

def display_off():
    global display_onoff
    if (display_onoff == "ON"):
        display_onoff = "OFF"
        os.system('vcgencmd display_power 0')

def update_clock():
    global script_dir
    global old_time
    global display_on_time

    #if GPIO.input(16):
    #    display_on_time = 3000  # keep display on for 5 minutes

    #if (display_on_time > 0):
    #    display_on()
    #    display_on_time = display_on_time - 1
    #else:
    #    display_off()

    # local time
    loc_time = time.strftime('%H:%M')
    # MJD + week
    date_txt = time.strftime('%d.%m.%Y')
    week_txt = "KW %s" % (time.strftime('%W'))
    if loc_time != old_time: # if time string has changed, update it
        old_time = loc_time
        
        # Create a temporary image to draw on
        temp_image = Image.new("RGBA", (351, 159), (0, 0, 0, 0))
        draw = ImageDraw.Draw(temp_image)
        draw.rectangle((0, 0, 350, 158), fill="#202020")
        
        # Draw the text onto the temporary image
        # Main clock font
        clock_font = ImageFont.truetype(os.path.join(script_dir, "arial.ttf"), 125)
        date_font = ImageFont.truetype(os.path.join(script_dir, "arial.ttf"), 27)
        
        # Draw time (main clock)
        draw.text((10, -10), loc_time, font=clock_font, fill="#ff8000")
        # Draw date and week
        draw.text((10, 119), date_txt, font=date_font, fill="#ffffff")
        draw.text((160, 119), week_txt, font=date_font, fill="#ffff00")
        
        # Convert to PhotoImage and display on canvas
        photo_image = safe_create_photoimage(temp_image)
        if photo_image:
            canvas.delete('clock')
            canvas.create_image(clock_x + 1, clock_y + 1, anchor=NW, image=photo_image, tags=('clock'))
            # prevent garbage collection
            canvas.clock = photo_image
        temp_image.close()  # Close PIL image
    
    # update every 100 msec
    try:
        if not shutdown_flag and window and hasattr(window, 'winfo_exists'):
            if window.winfo_exists():
                window.after(100, update_clock)
    except (RuntimeError, TclError):
        pass  # Main thread may no longer be in main loop

def update_mqtt_data():
    global dwd_pressure
    global dwd_outtemperature
    global dwd_outhumidity
    today = time.strftime('%Y-%m-%d')
    try:
        Response = requests.get("https://api.brightsky.dev/weather?lat=" + latitude + "&lon=" + longitude + "&date=" + today + "&tz=" +timezone)
        WeatherData = Response.json()
        dwd_pressure = str(WeatherData["weather"][int(time.strftime('%H'))]["pressure_msl"])
        dwd_outtemperature = str(WeatherData["weather"][int(time.strftime('%H'))]["temperature"])
        dwd_outhumidity = str(WeatherData["weather"][int(time.strftime('%H'))]["relative_humidity"])
    except:
        print("Couldn't load weather data.")
    update_intemperature()
    update_inhumidity()
    update_outtemperature()
    update_outhumidity()
    update_pressure()
    update_staticiaq()
    update_ppurchase()
    update_pfeed()
    update_pconsume()
    update_pgenerate()
    update_pdischarge()
    update_pcharge()
    update_eabsorb()
    update_eyield()
    update_sbatcharge()

    # update every 1 min
    try:
        if not shutdown_flag and window and hasattr(window, 'winfo_exists'):
            if window.winfo_exists():
                window.after(60000, update_mqtt_data)
    except (RuntimeError, TclError):
        pass  # Main thread may no longer be in main loop

def update_weathermap_in_gui():
    global window
    global canvas
    """Update the displayed image in the GUI (thread-safe)"""
    try:
        # Ensure we're in the main thread
        if threading.current_thread() != threading.main_thread():
            print("Warning: Weather map update attempted from background thread")
            return
            
        new_pil_image = radar.create_smooth_heatmap_grid(sigma=1.5)
        photo = safe_create_photoimage(new_pil_image)
        
        if photo:
            canvas.delete('weather_map')
            canvas.create_image(0, 0, anchor = NW, image = photo, tags=('weather_map'))

            # Store references to prevent garbage collection
            window.photo = photo
            window.current_pil_image = new_pil_image
        else:
            new_pil_image.close()  # Close if PhotoImage creation failed
    except Exception as e:
        print(f"Error updating weathermap: {e}")

def cleanup_and_exit():
    """Cleanup function to gracefully shutdown the application"""
    global shutdown_flag, client, window, canvas, radar
    
    print("Cleaning up...")
    shutdown_flag = True
    
    # Stop MQTT client properly for manual polling mode
    try:
        if 'client' in globals() and client:
            client.disconnect()  # Just disconnect, no loop_stop needed for manual polling
            time.sleep(0.1)  # Give it time to disconnect
            client = None
    except:
        pass
    
    # Stop all window timers by destroying window immediately
    try:
        if window:
            # Cancel all pending after() calls
            window.after_cancel('all')
    except:
        pass
    
    # Clear radar processor
    try:
        if radar:
            radar = None
    except:
        pass
    
    # Clear all canvas and image references
    try:
        if canvas:
            # Delete all canvas items first
            canvas.delete('all')
            
            # Clear all stored image references
            for attr in dir(canvas):
                if attr.startswith('p') and not attr.startswith('pack'):
                    try:
                        delattr(canvas, attr)
                    except:
                        pass
            
            canvas = None
    except:
        pass
    
    # Force garbage collection to clean up any remaining objects
    try:
        gc.collect()
    except:
        pass
    
    # Destroy window last with thread safety
    try:
        if window:
            # Ensure we're in the main thread for window operations
            if threading.current_thread() == threading.main_thread():
                window.quit()
                window.destroy()
            window = None
    except:
        pass
    
    # Final garbage collection
    try:
        gc.collect()
    except:
        pass

def safe_create_photoimage(pil_image):
    """Thread-safe PhotoImage creation that prevents runtime threading errors"""
    try:
        # Ensure we're in the main thread
        if threading.current_thread() != threading.main_thread():
            print("Warning: Image creation attempted from background thread")
            return None
        
        # Create PhotoImage and immediately close PIL image
        photo = ImageTk.PhotoImage(pil_image)
        return photo
    except Exception as e:
        print(f"Error creating PhotoImage: {e}")
        return None

def on_window_close():
    """Handle window close event"""
    cleanup_and_exit()

def main():
   global window
   global canvas
   global plist
   global radar
   global client
   global script_dir

   # Register cleanup function to ensure it runs on exit
   atexit.register(cleanup_and_exit)

   script_dir = os.path.dirname(os.path.realpath(__file__))

   #GPIO.setmode(GPIO.BCM)
   #GPIO.setwarnings(False)
   #GPIO.setup(16, GPIO.IN)

   # Create radar processor
   radar = RadarProcessor(
        satellite_source=radar_background,
        zoom_level=zoom,
        center_lon=float(longitude),
        center_lat=float(latitude),
        image_width_pixels=512,
        image_height_pixels=512,
        cities={
                    'Heimsheim': (8.863, 48.808, 'red'),
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

   window = Tk()
   canvas = Canvas(window, width = 1024, height = 600, bd = 0, highlightthickness = 0)
   canvas.pack()
   canvas.create_rectangle(0, 0, 1023, 599, fill='black')

   plist = circularlist(18)

   # Generate initial image
   radar.load_and_process_data(use_local=False)
   update_weathermap_in_gui()

   # Add periodic radar check in main thread instead of relying on background thread
   def check_radar_update():
       if not shutdown_flag:
           try:
               has_new_data, server_modified = radar.check_for_new_data()
               if has_new_data:
                   # Load data in background but update GUI in main thread
                   if radar.load_and_process_data(use_local=False, server_modified=server_modified):
                       update_weathermap_in_gui()
               
               if window and hasattr(window, 'winfo_exists') and window.winfo_exists():
                   window.after(60000, check_radar_update)  # Check every minute
           except Exception as e:
               print(f"Radar check error: {e}")
   
   # Start radar checking in main thread
   window.after(5000, check_radar_update)  # Start after 5 seconds

   update_clock()
   update_day_weather()
   update_mqtt_data()
   
   # Set up window close protocol
   window.protocol("WM_DELETE_WINDOW", on_window_close)

   client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
   client.username_pw_set(mqtt_user, mqtt_password)
   client.on_connect = on_connect
   client.on_disconnect = on_disconnect
   client.on_message = on_message
   
   # Set connection parameters for better stability
   client.max_inflight_messages_set(20)
   client.max_queued_messages_set(0)  # No limit on queued messages
   
   try:
      client.connect(mqtt_broker_address, mqtt_port, keepalive=60)  # Longer keepalive
      print("MQTT connection initiated...")
   except Exception as e:
      print(f"MQTT connection failed: {e}")
   
   # Use timer-based MQTT polling in main thread to avoid threading issues
   def mqtt_poll():
       global mqtt_poll_count, mqtt_last_poll_time, mqtt_connected, mqtt_reconnect_count
       global mqtt_last_successful_time, mqtt_connection_stale_threshold
       
       if shutdown_flag:
           print("MQTT polling stopped due to shutdown flag")
           return
           
       current_time = time.time()
       mqtt_poll_count += 1
       mqtt_last_poll_time = current_time
       
       # Check for stale connections (possible system resume scenario)
       connection_age = current_time - mqtt_last_successful_time
       is_connection_stale = mqtt_connected and connection_age > mqtt_connection_stale_threshold
       
       if is_connection_stale:
           print(f"MQTT connection appears stale ({connection_age:.1f}s since last success) - forcing reconnect")
           mqtt_connected = False
           mqtt_reconnect_count = 0  # Reset for fresh attempts
           try:
               client.disconnect()
               time.sleep(1.0)  # Wait for clean disconnect
               print("Initiating fresh MQTT connection after stale detection...")
               client.connect(mqtt_broker_address, mqtt_port, keepalive=60)
               mqtt_reconnect_count = 1
               print("MQTT reconnection initiated after stale connection detection")
           except Exception as e:
               print(f"MQTT reconnection after stale detection failed: {e}")
               mqtt_reconnect_count += 1
       
       # Debug output every 100 polls (about every 10 seconds)
       #if mqtt_poll_count % 100 == 1:
       #    status = "Connected" if mqtt_connected else "Disconnected"
       #    print(f"MQTT poll #{mqtt_poll_count} - Status: {status}, Reconnects: {mqtt_reconnect_count}")
       
       poll_success = True  # Assume success unless we encounter an error
       schedule_next = True  # Always schedule next poll unless explicitly disabled
       
       try:
           # Poll for MQTT messages with error detection
           result = client.loop(timeout=0.01)  # Short timeout to prevent blocking
           
           if result == mqtt.MQTT_ERR_SUCCESS:
               poll_success = True
               if mqtt_connected:
                   mqtt_last_successful_time = current_time  # Update successful activity time
           elif result == mqtt.MQTT_ERR_NO_CONN:  # Error code 7
               if not shutdown_flag and mqtt_reconnect_count < 15:  # Increased limit for resume scenarios
                   print(f"MQTT no connection (error {result}) - attempting reconnect #{mqtt_reconnect_count + 1}...")
                   try:
                       # Force a clean disconnect first
                       try:
                           client.disconnect()
                       except:
                           pass  # Ignore disconnect errors
                       
                       # Progressive delay based on attempt count
                       delay = min(3.0, 1.0 + (mqtt_reconnect_count * 0.5))
                       time.sleep(delay)
                       
                       # Fresh connection attempt
                       client.connect(mqtt_broker_address, mqtt_port, keepalive=60)
                       mqtt_reconnect_count += 1
                       print(f"MQTT reconnection attempt #{mqtt_reconnect_count} initiated (delay: {delay:.1f}s)")
                       
                       # After reconnection attempt, wait longer before next poll to allow connection to establish
                       poll_success = False
                       # Force longer interval for next poll after reconnection attempt
                       if not shutdown_flag and window and hasattr(window, 'winfo_exists'):
                           if window.winfo_exists():
                               window.after(3000, mqtt_poll)  # Wait 3 seconds before next poll
                               return  # Exit early to prevent normal scheduling
                       
                   except Exception as reconnect_error:
                       print(f"MQTT reconnection failed: {reconnect_error}")
                       mqtt_reconnect_count += 1
                   poll_success = False
               else:
                   print(f"Maximum MQTT reconnection attempts reached ({mqtt_reconnect_count}), backing off...")
                   poll_success = False
           elif result == mqtt.MQTT_ERR_CONN_LOST:  # Error code 5 - broker restart/network loss
               print(f"MQTT connection lost (error {result}) - broker restart or network issue detected")
               mqtt_connected = False
               if not shutdown_flag and mqtt_reconnect_count < 20:  # More attempts for broker restarts
                   print(f"Attempting to reconnect after connection lost #{mqtt_reconnect_count + 1}...")
                   try:
                       try:
                           client.disconnect()
                       except:
                           pass
                       
                       # Longer delay for broker restarts as they may take time to fully start
                       delay = min(5.0, 2.0 + (mqtt_reconnect_count * 0.5))
                       time.sleep(delay)
                       
                       client.connect(mqtt_broker_address, mqtt_port, keepalive=60)
                       mqtt_reconnect_count += 1
                       print(f"MQTT reconnection attempt #{mqtt_reconnect_count} after connection lost (delay: {delay:.1f}s)")
                       
                       # Wait longer for broker restart scenarios
                       if not shutdown_flag and window and hasattr(window, 'winfo_exists'):
                           if window.winfo_exists():
                               window.after(5000, mqtt_poll)  # Wait 5 seconds for broker restarts
                               return
                       
                   except Exception as reconnect_error:
                       print(f"MQTT reconnection after connection lost failed: {reconnect_error}")
                       mqtt_reconnect_count += 1
               poll_success = False
           else:
               print(f"MQTT loop error code: {result}")
               poll_success = False
                       
       except Exception as e:
           print(f"MQTT poll exception: {e}")
           poll_success = False
           # Try to reconnect on exception with backoff
           try:
               if not shutdown_flag and mqtt_reconnect_count < 8:
                   print("Attempting MQTT reconnection due to exception...")
                   try:
                       client.disconnect()
                   except:
                       pass
                   time.sleep(1.5)  # Longer wait on exception
                   client.connect(mqtt_broker_address, mqtt_port, keepalive=60)
                   mqtt_reconnect_count += 1
                   print(f"MQTT reconnection attempt #{mqtt_reconnect_count} initiated after exception")
           except Exception as reconnect_error:
               print(f"MQTT reconnection failed: {reconnect_error}")
               mqtt_reconnect_count += 1
       
       # ALWAYS schedule next poll if not shutting down - this is critical
       if not shutdown_flag and schedule_next:
           try:
               if window and hasattr(window, 'winfo_exists'):
                   if window.winfo_exists():
                       # Use appropriate intervals based on connection status and reconnection count
                       if mqtt_connected and poll_success:
                           interval = 100  # 100ms when connected and working
                       elif mqtt_connected:
                           interval = 500  # 500ms when connected but having issues
                       elif mqtt_reconnect_count < 5:
                           interval = 2000  # 2s when disconnected, trying to reconnect
                       else:
                           interval = 10000  # 10s when many reconnection failures (backoff)
                       
                       window.after(interval, mqtt_poll)
                   else:
                       print("Window no longer exists, stopping MQTT polling")
                       schedule_next = False
               else:
                   print("Window object invalid, stopping MQTT polling")
                   schedule_next = False
           except Exception as schedule_error:
               print(f"Failed to schedule next MQTT poll: {schedule_error}")
               # Even if scheduling failed, try again in a moment
               if not shutdown_flag:
                   try:
                       window.after(5000, mqtt_poll)  # Retry in 5 seconds
                   except:
                       print("Could not schedule retry poll")
       
       return poll_success
   
   # Add a watchdog function to monitor MQTT polling
   def mqtt_watchdog():
       global mqtt_last_poll_time, mqtt_connected, mqtt_reconnect_count
       if not shutdown_flag:
           current_time = time.time()
           if mqtt_last_poll_time > 0:
               time_since_poll = current_time - mqtt_last_poll_time
               if time_since_poll > 3:  # Reduced from 5 to 3 seconds for faster detection
                   print(f"MQTT polling appears stuck. Last poll: {time_since_poll:.1f}s ago")
                   print(f"Status: Connected={mqtt_connected}, Polls={mqtt_poll_count}, Reconnects={mqtt_reconnect_count}")
                   # Force restart polling immediately
                   try:
                       print("Force restarting MQTT polling...")
                       window.after(0, mqtt_poll)  # Schedule immediately
                   except Exception as e:
                       print(f"Failed to restart MQTT polling: {e}")
               elif mqtt_poll_count % 200 == 0:  # Status report every ~20 seconds (200 polls * 100ms)
                   status = "Connected" if mqtt_connected else "Disconnected"
                   print(f"MQTT Status: {status}, Polls: {mqtt_poll_count}, Reconnects: {mqtt_reconnect_count}")
           
           # Schedule next watchdog check more frequently
           if window and hasattr(window, 'winfo_exists'):
               try:
                   if window.winfo_exists():
                       window.after(5000, mqtt_watchdog)  # Check every 5 seconds (reduced from 30)
               except:
                   pass
   
   # Start MQTT polling in main thread
   print("Starting MQTT polling system...")
   window.after(500, mqtt_poll)  # Start polling after 500ms
   window.after(10000, mqtt_watchdog)  # Start watchdog after 10 seconds

   #window.geometry("1024x600+0+0")
   #window.overrideredirect(True)
   window.config(cursor="none")

   # Set up signal handlers for clean shutdown
   def signal_handler(sig, frame):
       cleanup_and_exit()
   
   signal.signal(signal.SIGINT, signal_handler)
   signal.signal(signal.SIGTERM, signal_handler)
   
   # Disable Tkinter's automatic image cleanup to prevent threading issues
   try:
       # This prevents the "main thread is not in main loop" errors
       import tkinter as tk
       
       # Store original destructor
       original_image_del = tk.Image.__del__
       original_var_del = tk.Variable.__del__
       
       # Create safe destructors that don't fail on threading issues
       def safe_image_del(self):
           try:
               if hasattr(self, 'tk') and self.tk and hasattr(self.tk, 'call'):
                   original_image_del(self)
           except (RuntimeError, tk.TclError):
               pass  # Ignore threading errors during shutdown
       
       def safe_var_del(self):
           try:
               if hasattr(self, '_tk') and self._tk and hasattr(self._tk, 'call'):
                   original_var_del(self)
           except (RuntimeError, tk.TclError):
               pass  # Ignore threading errors during shutdown
       
       # Apply the patches
       tk.Image.__del__ = safe_image_del
       tk.Variable.__del__ = safe_var_del
   except Exception as e:
       print(f"Warning: Could not patch Tkinter destructors: {e}")
   
   try:
       window.mainloop()
   except KeyboardInterrupt:
       pass
   finally:
       cleanup_and_exit()

if __name__ == '__main__':
   try:
       main()
   except Exception as e:
       print(f"Application error: {e}")
   finally:
       # Ensure cleanup runs even if main() fails
       try:
           cleanup_and_exit()
       except:
           pass
