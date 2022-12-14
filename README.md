# Weather Clock for Raspberry PI
This project is a dashboard for Raspberry Pi to display environmental weather data, rain radar, weather forecast, etc. on a connected LCD written in Python. The data is collected from local MQTT broker and also from Internet services.

<img src="/dashboard.jpg" alt="drawing" width="1000"/>

## Display
I used a 7inch IPS display with 1024x600 hardware resolution and HDMI input, which has a low power consumption of only 1-2 Watt which is predestinated for 24/7 operation. An RCWL-0516 doppler radar microwave motion sensor module is used to switch off the backlight when no motion has been detected for the last 10 minutes. This is for saving energy when nobody is in the room to watch the dashboard. The backlight is switched on automatically when motion is detected. 

https://www.waveshare.com/wiki/7inch_HDMI_LCD

## Raspberry PI
I use the Raspberry Pi Zero WH which has enough performance, a low power consumption and an HDMI connector. Also it is possible to connect it directly to the backside of the Waveshare display. Only a mini-HDMI (type C) to normal-HDMI (type A) cable is required. The whole system (RPI + display) can be powered over the USB connector and consumes in total a maximum of 4 Watt.

## Software on the Raspberry PI
* Use a 16Gbyte SD card and install Raspberry Pi OS on it
* Configure graphics driver and resolution as described on https://www.waveshare.com/wiki/7inch_HDMI_LCD
* Configure a static IP within your WiFi network
* Activate SSH for remote configuration, SW update and maintainance

### Install following packages used by the Python program:
* pip install python3-utils
* sudo apt-get install python3-pil python3-pil.imagetk
* sudo apt-get install python3-pip -y
* sudo pip3 install paho-mqtt

## Weather Clock configuration
### Please change following variables according to your location. The value for xmin and ymin can be determined with https://oms.wff.ch/calc.htm for a specific zoom level.
* longitude = "8.900"
* latiude  = "48.800"
* timezone = "Europe/Berlin"
* zoom = 12
* xmin = 2148
* ymin = 1409

### Please change following variables according to your MQTT settings:
* mqtt_user = "*********"
* mqtt_password = "***************"
* mqtt_broker_address = "192.168.xxx.xxx"
* mqtt_port = 1883
* mqtt_topic_pressure = "/483fdabaceba/pressure"
* mqtt_topic_outtemperature = "/483fdabaceba/temperature"
* mqtt_topic_outhumidity = "/483fdabaceba/humidity"
* mqtt_topic_intemperature = "/483fdabaceba/temperature"
* mqtt_topic_inhumidity = "/483fdabaceba/humidity"
* mqtt_topic_staticiaq = "/483fdaaaceba/staticiaq"
* mqtt_topic_ppurchase = "/00d0935D9eb9/ppurchase"
* mqtt_topic_pfeed = "/00d0935D9eb9/pfeed"
* mqtt_topic_pconsume = "/00d0935D9eb9/pconsume"
* mqtt_topic_pgenerate = "/00d0935D9eb9/pgenerate"

## Internet services used
* Tiles for the map background from Openstreetmap: e.g. https://tile.openstreetmap.org/12/2148/1409.png
* Rainviewer API: https://api.rainviewer.com/public/weather-maps.json
* Tiles for the rain radar as overlay from Rainviewer: e.g. https://tilecache.rainviewer.com/v2/radar/1636462800/256/12/2148/1409/2/1_1.png
* Actual weather and weather forecast from BrightSky (DWD open weaher data): e.g. https://api.brightsky.dev/weather?lat=48.80&lon=8.90&date=2021-10-18&tz=Europe/Berlin

## The program
Execute the program with: python3 ./weatherclock_rpi.py
