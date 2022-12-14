from tkinter import *
import math
import time
import os
import threading
from PIL import Image, ImageTk
import urllib.request
import io
from io import BytesIO
from datetime import datetime
import json
import requests
import paho.mqtt.client as mqtt
import RPi.GPIO as GPIO

# local settings
old_time = time.strftime('%H:%M:%S')
longitude = "8.900"
latiude  = "48.800"
timezone = "Europe/Berlin"
# https://oms.wff.ch/calc.htm zoom: 12 lon: 8.900 lat: 48.800
zoom = 12
xmin = 2148
ymin = 1409

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

# coordinates
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
ppurchase_x      = 512
ppurchase_y      = 416
pfeed_x          = 672
pfeed_y          = 416
pconsume_x       = 672
pconsume_y       = 448
pgenerate_x      = 512
pgenerate_y      = 448

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
mqtt_generate = "-----"

# display settings
display_on_time = 6000  # 10min
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

def draw_pressure_tendency(t1, t2, t3):
    global icon_pre

    # zone limit 0.1 hPa
    th =  0.1
    tl = -0.1

    if (t1 <= tl) and (t2 <= tl) and (t3 <= tl):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_7.png"))
    if (t1 <= tl) and (t2 <= tl) and (t3 > tl) and (t3 <= th):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_6.png"))
    if (t1 <= tl) and (t2 <= tl) and (t3 > th):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_5.png"))
    if (t1 <= tl) and (t2 > tl) and (t2 <= th) and (t3 <= tl):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_7.png"))
    if (t1 <= tl) and (t2 > tl) and (t2 <= th) and (t3 > tl) and (t3 <= th):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_4.png"))
    if (t1 <= tl) and (t2 > tl) and (t2 <= th) and (t3 > th):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_4.png"))
    if (t1 <= tl) and (t2 > th) and (t3 <= tl):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_7.png"))
    if (t1 <= tl) and (t2 > th) and (t3 > tl) and (t3 <= th):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_4.png"))
    if (t1 <= tl) and (t2 > th) and (t3 > th):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_3.png"))
    if (t1 > tl) and (t1 <= th) and (t2 <= tl) and (t3 <= tl):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_8.png"))
    if (t1 > tl) and (t1 <= th) and (t2 <= tl) and (t3 > tl) and (t3 <= th):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_4.png"))
    if (t1 > tl) and (t1 <= th) and (t2 <= tl) and (t3 > th):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_4.png"))
    if (t1 > tl) and (t1 <= th) and (t2 > tl) and (t2 <= th) and (t3 <= tl):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_4.png"))
    if (t1 > tl) and (t1 <= th) and (t2 > tl) and (t2 <= th) and (t3 > tl) and (t3 <= th):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_4.png"))
    if (t1 > tl) and (t1 <= th) and (t2 > tl) and (t2 <= th) and (t3 > th):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_4.png"))
    if (t1 > tl) and (t1 <= th) and (t2 > th) and (t3 <= tl):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_4.png"))
    if (t1 > tl) and (t1 <= th) and (t2 > th) and (t3 > tl) and (t3 <= th):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_4.png"))
    if (t1 > tl) and (t1 <= th) and (t2 > th) and (t3 > th):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_3.png"))
    if (t1 > th) and (t2 <= tl) and (t3 <= tl):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_8.png"))
    if (t1 > th) and (t2 <= tl) and (t3 > tl) and (t3 <= th):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_4.png"))
    if (t1 > th) and (t2 <= tl) and (t3 > th):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_2.png"))
    if (t1 > th) and (t2 > tl) and (t2 <= th) and (t3 <= tl):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_4.png"))
    if (t1 > th) and (t2 > tl) and (t2 <= th) and (t3 > tl) and (t3 <= th):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_4.png"))
    if (t1 > th) and (t2 > tl) and (t2 <= th) and (t3 > th):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_2.png"))
    if (t1 > th) and (t2 > th) and (t3 <= tl):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_0.png"))
    if (t1 > th) and (t2 > th) and (t3 > tl) and (t3 <= th):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_1.png"))
    if (t1 > th) and (t2 > th) and (t3 > th):
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_2.png"))
    canvas.create_image(pressure_x + 290, pressure_y + 1, anchor = NW, image = icon_pre, tags=('pressure'))

def update_intemperature():
    canvas.delete('intemperature')
    canvas.create_rectangle(intemperature_x, intemperature_y, intemperature_x + 354, intemperature_y + 32, fill="#202020", tags=('intemperature'))
    canvas.create_text(intemperature_x + 4, intemperature_y, text = "Raumtemperatur: ", font=("Arial", 20), anchor = NW, fill = "#ffffff", tags=('intemperature')) 
    canvas.create_text(intemperature_x + 220, intemperature_y, text = mqtt_intemperature + " °C", font=("Arial", 20), anchor = NW, fill = "#ffff00", tags=('intemperature'))

def update_inhumidity():
    canvas.delete('inhumidity')
    canvas.create_rectangle(inhumidity_x, inhumidity_y, inhumidity_x + 354, inhumidity_y + 32, fill="#202020", tags=('inhumidity'))
    canvas.create_rectangle(inhumidity_x, inhumidity_y + 32, 1023, inhumidity_y + 64, fill="#202020", tags=('inhumidity'))
    canvas.create_text(inhumidity_x + 4, inhumidity_y, text = "Raumluftfeuchte: ", font=("Arial", 20), anchor = NW, fill = "#ffffff", tags=('inhumidity')) 
    canvas.create_text(inhumidity_x + 214, inhumidity_y, text = mqtt_inhumidity + " %rF", font=("Arial", 20), anchor = NW, fill = "#ffff00", tags=('inhumidity'))

def update_outtemperature():
    global icon_temp
    canvas.delete('outtemperature')
    canvas.create_rectangle(outtemperature_x, outtemperature_y, outtemperature_x + 354, outtemperature_y + 128, fill="#303030", tags=('outtemperature'))
    icon_temp = ImageTk.PhotoImage(Image.open("./Icons/temp.png"))
    canvas.create_image(outtemperature_x + 4, outtemperature_y + 4, anchor = NW, image = icon_temp, tags=('outtemperature'))
    canvas.create_text(outtemperature_x + 34, outtemperature_y, text = "°C", font=("Arial", 20), anchor = NW, fill = "#ffffff", tags=('outtemperature'))

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
    canvas.create_text(outtemperature_x + 53, outtemperature_y, text = mqtt_outtemperature, font=("Arial", 94), anchor = NW, fill = color, tags=('outtemperature'))

def update_outhumidity():
    global icon_hum_blue
    global icon_hum_grey

    canvas.delete('outhumidity')
    canvas.create_rectangle(outhumidity_x, outhumidity_y, outhumidity_x + 160, outhumidity_y + 128, fill="#202020", tags=('outhumidity'))
    if (mqtt_outhumidity != "---.-"):
        level = int(float(mqtt_outhumidity) * 1.07)      
        icon_hum_blue = ImageTk.PhotoImage(Image.open("./Icons/humidity_blue.png").crop([0, 125 - 9 - level, 125, 125]))
        icon_hum_grey = ImageTk.PhotoImage(Image.open("./Icons/humidity_grey.png").crop([0, 0, 125, 125 - 9 - level]))
        canvas.create_image(outhumidity_x + 16, outhumidity_y + 128 - 9 - level, anchor = NW, image = icon_hum_blue, tags=('outhumidity'))
        canvas.create_image(outhumidity_x + 16, outhumidity_y + 3, anchor = NW, image = icon_hum_grey, tags=('outhumidity'))
    else:
        icon_hum_grey = ImageTk.PhotoImage(Image.open("./Icons/humidity_grey.png"))
        canvas.create_image(outhumidity_x + 16, outhumidity_y + 3, anchor = NW, image = icon_hum_grey, tags=('outhumidity'))

def update_staticiaq():
    global icon_iaq
    
    canvas.delete('staticiaq')
    canvas.create_rectangle(staticiaq_x, staticiaq_y, staticiaq_x + 160, staticiaq_y + 160, fill="#202020", tags=('staticiaq'))
    if (mqtt_staticiaq != "---.-"):
        if (float(mqtt_staticiaq) < 100.0):     
            icon_iaq = ImageTk.PhotoImage(Image.open("./Icons/IAQ_good.png"))
        elif (float(mqtt_staticiaq) >= 100.0) and (float(mqtt_staticiaq) <= 200.0):
            icon_iaq = ImageTk.PhotoImage(Image.open("./Icons/IAQ_medium.png")) 
        else:
            icon_iaq = ImageTk.PhotoImage(Image.open("./Icons/IAQ_bad.png"))

        canvas.create_image(staticiaq_x + 16, staticiaq_y + 16, anchor = NW, image = icon_iaq, tags=('staticiaq'))

def update_pressure():
    global icon_pre

    canvas.delete('pressure')
    canvas.create_rectangle(pressure_x, pressure_y, pressure_x + 354, pressure_y + 32, fill="#202020", tags=('pressure'))
    canvas.create_text(pressure_x + 4, pressure_y, text = "Luftdruck: ", font=("Arial", 20), anchor = NW, fill = "#ffffff", tags=('pressure')) 
    canvas.create_text(pressure_x + 130, pressure_y, text = mqtt_pressure + " hPa", font=("Arial", 20), anchor = NW, fill = "#ffff00", tags=('pressure'))
    if (plist.length() == 18):
        tend1 = calc_pressure_tendency(plist, 0, 6)
        tend2 = calc_pressure_tendency(plist, 6, 12)
        tend3 = calc_pressure_tendency(plist, 12, 18)
        draw_pressure_tendency(tend1, tend2, tend3)
    else:
        icon_pre = ImageTk.PhotoImage(Image.open("./Icons/pressure_tendency_4.png"))
        canvas.create_image(pressure_x + 290, pressure_y + 1, anchor = NW, image = icon_pre, tags=('pressure'))

def update_ppurchase():
    canvas.delete('ppurchase')
    canvas.create_rectangle(ppurchase_x, ppurchase_y, ppurchase_x + 160, ppurchase_y + 32, fill="#303030", tags=('ppurchase'))
    canvas.create_text(ppurchase_x + 4, ppurchase_y, text = mqtt_ppurchase.split(".")[0] + " W", font=("Arial", 20), anchor = NW, fill = "#ff0000", tags=('ppurchase'))

def update_pfeed():
    canvas.delete('pfeed')
    canvas.create_rectangle(pfeed_x, pfeed_y, pfeed_x + 160, pfeed_y + 32, fill="#303030", tags=('pfeed'))
    canvas.create_text(pfeed_x + 4, pfeed_y, text = mqtt_pfeed.split(".")[0] + " W", font=("Arial", 20), anchor = NW, fill = "#ffff00", tags=('pfeed'))

def update_pconsume():
    canvas.delete('pconsume')
    canvas.create_rectangle(pconsume_x, pconsume_y, pconsume_x + 160, pconsume_y + 32, fill="#303030", tags=('pconsume'))
    canvas.create_text(pconsume_x + 4, pconsume_y, text = mqtt_pconsume.split(".")[0] + " W", font=("Arial", 20), anchor = NW, fill = "#ffffff", tags=('pconsume'))

def update_pgenerate():
    canvas.delete('pgenerate')
    canvas.create_rectangle(pgenerate_x, pgenerate_y, pgenerate_x + 160, pgenerate_y + 32, fill="#303030", tags=('pgenerate'))
    canvas.create_text(pgenerate_x + 4, pgenerate_y, text = mqtt_pgenerate.split(".")[0] + " W", font=("Arial", 20), anchor = NW, fill = "#00ff00", tags=('pgenerate'))

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

    msg = str(message.payload.decode("utf-8"))
    #print("message received: ", msg)
    #print("message topic: ", message.topic)
    if (message.topic == mqtt_topic_intemperature):
        mqtt_intemperature = msg
        update_intemperature()
    if (message.topic == mqtt_topic_inhumidity):
        mqtt_inhumidity = msg
        update_inhumidity()
    if (message.topic == mqtt_topic_outtemperature):
        mqtt_outtemperature = msg
        update_outtemperature()
    if (message.topic == mqtt_topic_outhumidity):
        mqtt_outhumidity = msg
        update_outhumidity()
    if (message.topic == mqtt_topic_pressure):
        mqtt_pressure = msg
        try:
           plist.append(float(mqtt_pressure))
        except:
           print("Pressure value has wrong format.")
        update_pressure()
    if (message.topic == mqtt_topic_staticiaq):
        mqtt_staticiaq = msg
        update_staticiaq()
    if (message.topic == mqtt_topic_ppurchase):
        mqtt_ppurchase = msg
        update_ppurchase()
    if (message.topic == mqtt_topic_pfeed):
        mqtt_pfeed = msg
        update_pfeed()
    if (message.topic == mqtt_topic_pconsume):
        mqtt_pconsume = msg
        update_pconsume()
    if (message.topic == mqtt_topic_pgenerate):
        mqtt_pgenerate = msg
        update_pgenerate()

def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT Broker: " + mqtt_broker_address)
    mqtt_intemperature = "--.-"
    mqtt_inhumidity = "---.-"
    mqtt_outtemperature = "--.-"
    mqtt_outhumidity = "---.-"
    mqtt_pressure = "----.-"
    mqtt_staticiaq = "---"
    mqtt_ppurchase = "-----"
    mqtt_pfeed = "-----"
    mqtt_pconsume = "-----"
    mqtt_pgenerate = "-----"
    client.subscribe(mqtt_topic_intemperature)
    client.subscribe(mqtt_topic_inhumidity)    
    client.subscribe(mqtt_topic_outtemperature)
    client.subscribe(mqtt_topic_outhumidity)
    client.subscribe(mqtt_topic_pressure)
    client.subscribe(mqtt_topic_staticiaq)
    client.subscribe(mqtt_topic_ppurchase)
    client.subscribe(mqtt_topic_pfeed)
    client.subscribe(mqtt_topic_pconsume)
    client.subscribe(mqtt_topic_pgenerate)

def draw_pointer(x, y):
    global icon_pointer
    icon_pointer = ImageTk.PhotoImage(Image.open("./Icons/pointer.png"))
    canvas.create_image(x - 12, y - 40, anchor = NW, image = icon_pointer, tags=('weather_map'))

def init_weather_icons():
    global icon_clear_day
    global icon_clear_night
    global icon_cloudy
    global icon_fog
    global icon_hail
    global icon_partly_cloudy_day
    global icon_partly_cloudy_day_rain
    global icon_partly_cloudy_day_snow
    global icon_partly_cloudy_night
    global icon_partly_cloudy_night_rain
    global icon_partly_cloudy_night_snow
    global icon_rain
    global icon_sleet
    global icon_snow
    global icon_thunderstorm
    global icon_wind
    global icon_clear_day_big
    global icon_clear_night_big
    global icon_cloudy_big
    global icon_fog_big
    global icon_hail_big
    global icon_partly_cloudy_day_big
    global icon_partly_cloudy_day_rain_big
    global icon_partly_cloudy_day_snow_big
    global icon_partly_cloudy_night_big
    global icon_partly_cloudy_night_rain_big
    global icon_partly_cloudy_night_snow_big
    global icon_rain_big
    global icon_sleet_big
    global icon_snow_big
    global icon_thunderstorm_big
    global icon_wind_big
    icon_clear_day = ImageTk.PhotoImage(Image.open("./Icons/clear-day.png"))
    icon_clear_night = ImageTk.PhotoImage(Image.open("./Icons/clear-night.png"))
    icon_cloudy = ImageTk.PhotoImage(Image.open("./Icons/cloudy.png"))
    icon_fog = ImageTk.PhotoImage(Image.open("./Icons/fog.png"))
    icon_hail = ImageTk.PhotoImage(Image.open("./Icons/hail.png"))
    icon_partly_cloudy_day = ImageTk.PhotoImage(Image.open("./Icons/partly-cloudy-day.png"))
    icon_partly_cloudy_day_rain = ImageTk.PhotoImage(Image.open("./Icons/partly-cloudy-day-rain.png"))
    icon_partly_cloudy_day_snow = ImageTk.PhotoImage(Image.open("./Icons/partly-cloudy-day-snow.png"))
    icon_partly_cloudy_night = ImageTk.PhotoImage(Image.open("./Icons/partly-cloudy-night.png"))
    icon_partly_cloudy_night_rain = ImageTk.PhotoImage(Image.open("./Icons/partly-cloudy-night-rain.png"))
    icon_partly_cloudy_night_snow = ImageTk.PhotoImage(Image.open("./Icons/partly-cloudy-night-snow.png"))
    icon_rain = ImageTk.PhotoImage(Image.open("./Icons/rain.png"))
    icon_sleet = ImageTk.PhotoImage(Image.open("./Icons/sleet.png"))
    icon_snow = ImageTk.PhotoImage(Image.open("./Icons/snow.png"))
    icon_thunderstorm = ImageTk.PhotoImage(Image.open("./Icons/thunderstorm.png"))
    icon_wind = ImageTk.PhotoImage(Image.open("./Icons/wind.png"))
    icon_clear_day_big = ImageTk.PhotoImage(Image.open("./Icons/clear-day-big.png"))
    icon_clear_night_big = ImageTk.PhotoImage(Image.open("./Icons/clear-night-big.png"))
    icon_cloudy_big = ImageTk.PhotoImage(Image.open("./Icons/cloudy-big.png"))
    icon_fog_big = ImageTk.PhotoImage(Image.open("./Icons/fog-big.png"))
    icon_hail_big = ImageTk.PhotoImage(Image.open("./Icons/hail-big.png"))
    icon_partly_cloudy_day_big = ImageTk.PhotoImage(Image.open("./Icons/partly-cloudy-day-big.png"))
    icon_partly_cloudy_day_rain_big = ImageTk.PhotoImage(Image.open("./Icons/partly-cloudy-day-rain-big.png"))
    icon_partly_cloudy_day_snow_big = ImageTk.PhotoImage(Image.open("./Icons/partly-cloudy-day-snow-big.png"))
    icon_partly_cloudy_night_big = ImageTk.PhotoImage(Image.open("./Icons/partly-cloudy-night-big.png"))
    icon_partly_cloudy_night_rain_big = ImageTk.PhotoImage(Image.open("./Icons/partly-cloudy-night-rain-big.png"))
    icon_partly_cloudy_night_snow_big = ImageTk.PhotoImage(Image.open("./Icons/partly-cloudy-night-snow-big.png"))
    icon_rain_big = ImageTk.PhotoImage(Image.open("./Icons/rain-big.png"))
    icon_sleet_big = ImageTk.PhotoImage(Image.open("./Icons/sleet-big.png"))
    icon_snow_big = ImageTk.PhotoImage(Image.open("./Icons/snow-big.png"))
    icon_thunderstorm_big = ImageTk.PhotoImage(Image.open("./Icons/thunderstorm-big.png"))
    icon_wind_big = ImageTk.PhotoImage(Image.open("./Icons/wind-big.png"))

def draw_weather_icon(x, y, icon):
    if (icon == "clear-day"):
        canvas.create_image(x, y, anchor = NW, image = icon_clear_day, tags=('day_weather'))
    elif (icon == "clear-night"):
        canvas.create_image(x, y, anchor = NW, image = icon_clear_night, tags=('day_weather'))
    elif (icon == "cloudy"):
        canvas.create_image(x, y, anchor = NW, image = icon_cloudy, tags=('day_weather'))
    elif (icon == "fog"):
        canvas.create_image(x, y, anchor = NW, image = icon_fog, tags=('day_weather'))
    elif (icon == "hail"):
        canvas.create_image(x, y, anchor = NW, image = icon_hail, tags=('day_weather'))
    elif (icon == "partly-cloudy-day"):
        canvas.create_image(x, y, anchor = NW, image = icon_partly_cloudy_day, tags=('day_weather'))
    elif (icon == "partly-cloudy-day-rain"):
        canvas.create_image(x, y, anchor = NW, image = icon_partly_cloudy_day_rain, tags=('day_weather'))
    elif (icon == "partly-cloudy-day-snow"):
        canvas.create_image(x, y, anchor = NW, image = icon_partly_cloudy_day_snow, tags=('day_weather'))
    elif (icon == "partly-cloudy-night"):
        canvas.create_image(x, y, anchor = NW, image = icon_partly_cloudy_night, tags=('day_weather'))
    elif (icon == "partly-cloudy-night-rain"):
        canvas.create_image(x, y, anchor = NW, image = icon_partly_cloudy_night_rain, tags=('day_weather'))
    elif (icon == "partly-cloudy-night-snow"):
        canvas.create_image(x, y, anchor = NW, image = icon_partly_cloudy_night_snow, tags=('day_weather'))
    elif (icon == "rain"):
        canvas.create_image(x, y, anchor = NW, image = icon_rain, tags=('day_weather'))
    elif (icon == "sleet"):
        canvas.create_image(x, y, anchor = NW, image = icon_sleet, tags=('day_weather'))
    elif (icon == "snow"):
        canvas.create_image(x, y, anchor = NW, image = icon_snow, tags=('day_weather'))
    elif (icon == "thunderstorm"):
        canvas.create_image(x, y, anchor = NW, image = icon_thunderstorm, tags=('day_weather'))
    elif (icon == "wind"):
        canvas.create_image(x, y, anchor = NW, image = icon_wind, tags=('day_weather'))
    else:
        print("Failed to create icon.")

def draw_weather_icon_big(x, y, icon):
    if (icon == "clear-day"):
        canvas.create_image(x, y, anchor = NW, image = icon_clear_day_big, tags=('day_weather'))
    elif (icon == "clear-night"):
        canvas.create_image(x, y, anchor = NW, image = icon_clear_night_big, tags=('day_weather'))
    elif (icon == "cloudy"):
        canvas.create_image(x, y, anchor = NW, image = icon_cloudy_big, tags=('day_weather'))
    elif (icon == "fog"):
        canvas.create_image(x, y, anchor = NW, image = icon_fog_big, tags=('day_weather'))
    elif (icon == "hail"):
        canvas.create_image(x, y, anchor = NW, image = icon_hail_big, tags=('day_weather'))
    elif (icon == "partly-cloudy-day"):
        canvas.create_image(x, y, anchor = NW, image = icon_partly_cloudy_day_big, tags=('day_weather'))
    elif (icon == "partly-cloudy-day-rain"):
        canvas.create_image(x, y, anchor = NW, image = icon_partly_cloudy_day_rain_big, tags=('day_weather'))
    elif (icon == "partly-cloudy-day-snow"):
        canvas.create_image(x, y, anchor = NW, image = icon_partly_cloudy_day_snow_big, tags=('day_weather'))
    elif (icon == "partly-cloudy-night"):
        canvas.create_image(x, y, anchor = NW, image = icon_partly_cloudy_night_big, tags=('day_weather'))
    elif (icon == "partly-cloudy-night-rain"):
        canvas.create_image(x, y, anchor = NW, image = icon_partly_cloudy_night_rain_big, tags=('day_weather'))
    elif (icon == "partly-cloudy-night-snow"):
        canvas.create_image(x, y, anchor = NW, image = icon_partly_cloudy_night_snow_big, tags=('day_weather'))
    elif (icon == "rain"):
        canvas.create_image(x, y, anchor = NW, image = icon_rain_big, tags=('day_weather'))
    elif (icon == "sleet"):
        canvas.create_image(x, y, anchor = NW, image = icon_sleet_big, tags=('day_weather'))
    elif (icon == "snow"):
        canvas.create_image(x, y, anchor = NW, image = icon_snow_big, tags=('day_weather'))
    elif (icon == "thunderstorm"):
        canvas.create_image(x, y, anchor = NW, image = icon_thunderstorm_big, tags=('day_weather'))
    elif (icon == "wind"):
        canvas.create_image(x, y, anchor = NW, image = icon_wind_big, tags=('day_weather'))
    else:
        print("Failed to create big icon.")

def draw_weather(now_hour, first_hour, last_hour, start_pos, url):
    x = start_pos
    try:
        Response = requests.get(url)
        WeatherData = Response.json()
        if (now_hour != -1):
            icon_now = str(WeatherData["weather"][now_hour]["icon"])
            canvas.create_rectangle(512, 160, 672, 288, fill="#303030", tags=('day_weather'))
            draw_weather_icon_big(512 + 16, 160, icon_now)
        for h in range(first_hour, last_hour+1, 4):
            icon = str(WeatherData["weather"][h]["icon"])
            cond = str(WeatherData["weather"][h]["condition"])
            temperature = str(WeatherData["weather"][h]["temperature"])
            pressure = str(WeatherData["weather"][h]["pressure_msl"])
            humidity = str(WeatherData["weather"][h]["relative_humidity"])
            precipitation = WeatherData["weather"][h]["precipitation"]
            if ((icon == "partly-cloudy-day" or icon == "partly-cloudy-night") and (cond == "rain" or cond == "snow")):
                icon = icon + '-' + cond;
            if (icon == "cloudy" and (cond == "rain" or cond == "snow") and precipitation > 0.2):
                icon = cond;
            canvas.create_rectangle(day_weather_x + x * 170, day_weather_y, x * 170 + 171, 599, fill="black", tags=('day_weather'))
            draw_weather_icon(day_weather_x + x * 170, day_weather_y + 12, icon)
            canvas.create_text(day_weather_x + x * 170 + 66, day_weather_y + 2, text = str(h) + ":00", font=("Arial", 20), anchor = NW, fill = "#ffffff", tags=('day_weather'))
            canvas.create_text(day_weather_x + x * 170 + 66, day_weather_y + 30, text = temperature + " °C", font=("Arial", 13), anchor = NW, fill = "#ffff00", tags=('day_weather'))
            canvas.create_text(day_weather_x + x * 170 + 66, day_weather_y + 48, text = pressure + " hPa", font=("Arial", 13), anchor = NW, fill = "#ffff00", tags=('day_weather'))
            canvas.create_text(day_weather_x + x * 170 + 66, day_weather_y + 66, text = humidity + " %rF", font=("Arial", 13), anchor = NW, fill = "#ffff00", tags=('day_weather'))
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

    canvas.delete('day_weather')

    if (int(hour) < 3):
       # 23 from yesterday + 3, 7, 11, 15, 19 from today
       url = "https://api.brightsky.dev/weather?lat=" + latiude + "&lon=" + longitude + "&date=" + yesterday + "&tz=" +timezone
       draw_weather(-1, 23, 23, 0, url)
       url = "https://api.brightsky.dev/weather?lat=" + latiude + "&lon=" + longitude + "&date=" + today + "&tz=" +timezone
       draw_weather(int(hour), 3, 19, 1, url)
    elif (int(hour) >= 3) and (int(hour) < 7):
       # 3, 7, 11, 15, 19, 23 from today
       url = "https://api.brightsky.dev/weather?lat=" + latiude + "&lon=" + longitude + "&date=" + today + "&tz=" +timezone
       draw_weather(int(hour), 3, 23, 0, url)
    elif (int(hour) >= 7) and (int(hour) < 11):
       # 7, 11, 15, 19, 23 from today, 3 from tomorrow
       url = "https://api.brightsky.dev/weather?lat=" + latiude + "&lon=" + longitude + "&date=" + today + "&tz=" +timezone
       draw_weather(int(hour), 7, 23, 0, url)
       url = "https://api.brightsky.dev/weather?lat=" + latiude + "&lon=" + longitude + "&date=" + tomorrow + "&tz=" +timezone
       draw_weather(-1, 3, 3, 5, url)
    elif (int(hour) >= 11) and (int(hour) < 15):
       # 11, 15, 19, 23 from today, 3, 7 from tomorrow
       url = "https://api.brightsky.dev/weather?lat=" + latiude + "&lon=" + longitude + "&date=" + today + "&tz=" +timezone
       draw_weather(int(hour), 11, 23, 0, url)
       url = "https://api.brightsky.dev/weather?lat=" + latiude + "&lon=" + longitude + "&date=" + tomorrow + "&tz=" +timezone
       draw_weather(-1, 3, 7, 4, url)
    elif (int(hour) >= 15) and (int(hour) < 19):
       # 15, 19, 23 from today, 3, 7, 11 from tomorrow
       url = "https://api.brightsky.dev/weather?lat=" + latiude + "&lon=" + longitude + "&date=" + today + "&tz=" +timezone
       draw_weather(int(hour), 15, 23, 0, url)
       url = "https://api.brightsky.dev/weather?lat=" + latiude + "&lon=" + longitude + "&date=" + tomorrow + "&tz=" +timezone
       draw_weather(-1, 3, 11, 3, url)
    elif (int(hour) >= 19) and (int(hour) < 23):
       # 19, 23 from today, 3, 7, 11, 15 from tomorrow
       url = "https://api.brightsky.dev/weather?lat=" + latiude + "&lon=" + longitude + "&date=" + today + "&tz=" +timezone
       draw_weather(int(hour), 19, 23, 0, url)
       url = "https://api.brightsky.dev/weather?lat=" + latiude + "&lon=" + longitude + "&date=" + tomorrow + "&tz=" +timezone
       draw_weather(-1, 3, 15, 2, url)
    else:
       # 23 from today, 3, 7, 11, 15, 19 from tomorrow
       url = "https://api.brightsky.dev/weather?lat=" + latiude + "&lon=" + longitude + "&date=" + today + "&tz=" +timezone
       draw_weather(int(hour), 23, 23, 0, url)
       url = "https://api.brightsky.dev/weather?lat=" + latiude + "&lon=" + longitude + "&date=" + tomorrow + "&tz=" +timezone
       draw_weather(-1, 3, 19, 1, url)    
    # update every 10 min
    window.after(600000, update_day_weather)

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
    global old_time
    global display_on_time

    if GPIO.input(16):
        display_on_time = 6000

    if (display_on_time > 0):
        display_on()
        display_on_time = display_on_time - 1
    else:
        display_off()

    # local time
    loc_time = time.strftime('%H:%M')
    # MJD + week
    date_txt = time.strftime('%d.%m.%Y')
    week_txt = "KW %s" % (time.strftime('%W'))
    if loc_time != old_time: # if time string has changed, update it
        old_time = loc_time
        canvas.delete('clock')
        canvas.create_rectangle(clock_x, clock_y, clock_x + 352, clock_y + 160, fill="#202020", tags=('clock'))
        canvas.create_text(clock_x + 10, clock_y - 10, text = loc_time, font=("Arial", 94), anchor = NW, fill = "#ff8000", tags=('clock'))
        canvas.create_text(clock_x + 14, clock_y + 119, text = date_txt, font=("Arial", 20), anchor = NW, fill = "#ffffff", tags=('clock'))
        canvas.create_text(clock_x + 160, clock_y + 119, text = week_txt, font=("Arial", 20), anchor = NW, fill = "#ffff00", tags=('clock'))
    # update every 100 msec
    window.after(100, update_clock)

def update_mqtt_data():
    global dwd_pressure
    global dwd_outtemperature
    global dwd_outhumidity
    today = time.strftime('%Y-%m-%d')
    try:
        Response = requests.get("https://api.brightsky.dev/weather?lat=" + latiude + "&lon=" + longitude + "&date=" + today + "&tz=" +timezone)
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
    # update every 1 min
    window.after(60000, update_mqtt_data)

def getImageClusterMap(xmin, ymin, xmax,  ymax, zoom):
    smurl = r"https://tile.openstreetmap.org/{0}/{1}/{2}.png" 

    Cluster = Image.new('RGBA',((xmax-xmin+1)*256,(ymax-ymin+1)*256) ) 
    for xtile in range(xmin, xmax+1):
        for ytile in range(ymin,  ymax+1):
            try:
                imgurl=smurl.format(zoom, xtile, ytile)
                #print("Opening: " + imgurl)
                imgstr = requests.get(imgurl)
                tile = Image.open(BytesIO(imgstr.content))
                Cluster.paste(tile, box=((xtile-xmin)*256, (ytile-ymin)*256))
            except: 
                print("Couldn't download map image")
                tile = Image.open("./Map/" + str(xtile) + "_" + str(ytile) + ".png")
                Cluster.paste(tile, box=((xtile-xmin)*256, (ytile-ymin)*256))
    return Cluster

def getImageClusterRadar(xmin, ymin, xmax,  ymax, zoom):
    global im_black_single

    try:
        apiurl = r"https://api.rainviewer.com/public/weather-maps.json"  
        apistr = requests.get(apiurl)
        api = apistr.json()
    except:
        print("Couldn't download weather api")
        api = None

    if (api != None):
        rvurl = api['host'] + api['radar']['past'][-1]['path'] + "/256/{0}/{1}/{2}/2/1_1.png"  

        for xtile in range(xmin, xmax+1):
            for ytile in range(ymin,  ymax+1):
                try:
                    imgurl=rvurl.format(zoom, xtile, ytile)
                    #print("Opening: " + imgurl)
                    imgstr = requests.get(imgurl)
                    tile = Image.open(BytesIO(imgstr.content))
                    if (tile.mode == "RGBA"):
                        im_rad.paste(tile, box=((xtile-xmin)*256, (ytile-ymin)*256))
                    else:
                        im_rad.paste(im_black_single, box=((xtile-xmin)*256, (ytile-ymin)*256))
                except: 
                    print("Couldn't download radar image")
                    tile = None

def update_weathermap(xmin, ymin, xmax, ymax, zoom): 
    global map_photo
    global im_rad
    global im_tot
    while True:
        print("Update Map - Unix time: ", int(time.time()))
        getImageClusterRadar(xmin, ymin, xmax, ymax, zoom)
        im_rad = Image.blend(im_black, im_rad, alpha=0.8)

        im_tot = im_map.copy()
        im_tot.paste(im_rad, (0, 0), im_rad)

        map_photo = ImageTk.PhotoImage(im_tot)
        canvas.delete('weather_map')
        canvas.create_image(0, 0, anchor = NW, image = map_photo, tags=('weather_map'))
        draw_pointer(248, 248)
        #update every 5min
        time.sleep(300)

def main():
   global window
   global canvas
   global im_black_single
   global im_black
   global im_rad
   global im_tot
   global im_map
   global plist

   GPIO.setmode(GPIO.BCM)
   GPIO.setwarnings(False)
   GPIO.setup(16, GPIO.IN)

   window = Tk()
   canvas = Canvas(window, width = 1024, height = 600, bd = 0, highlightthickness = 0)
   canvas.pack()
   canvas.create_rectangle(0, 0, 1023, 599, fill='black')

   init_weather_icons()
   plist = circularlist(18)

   xmax = xmin + 1
   ymax = ymin + 1

   #empty black + opaque image
   im_black_single = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
   im_black = Image.new("RGBA", ((xmax-xmin+1)*256,(ymax-ymin+1)*256), (0, 0, 0, 0))

   #map image
   im_map = getImageClusterMap(xmin, ymin, xmax, ymax, zoom)
   im_map = im_map.convert("RGBA")

   im_rad = Image.new('RGBA',((xmax-xmin+1)*256,(ymax-ymin+1)*256))
   im_tot = Image.new('RGBA',((xmax-xmin+1)*256,(ymax-ymin+1)*256))

   thd = threading.Thread(target=update_weathermap, args=(xmin, ymin, xmax, ymax, zoom))
   thd.daemon = True
   thd.start()

   update_clock()
   update_day_weather()
   update_mqtt_data()

   client = mqtt.Client()
   client.username_pw_set(mqtt_user, mqtt_password)
   client.on_connect = on_connect
   client.on_message = on_message
   try:
      client.connect(mqtt_broker_address, mqtt_port, keepalive = 10)
      print("MQTT connection succeeded.")
   except:
      print("MQTT connection failed.")
   client.loop_start()

   window.config(cursor="none")
   window.wm_attributes('-fullscreen', 'True')
   window.mainloop()

if __name__ == '__main__':
   main()
