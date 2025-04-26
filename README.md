# Timelapse by raspsberry Pi Zero 2W
This is a timelapse photography project for Raspberry Pi, designed to capture seasonal changes.

## Project Overview
This project uses a Raspberry Pi and camera module to capture images at set intervals and upload them to cloud storage. Users can set shooting intervals, exposure settings, and other parameters, while the system analyzes brightness during the process to select the best exposure value.

## Components
Raspberry Pi Zero 2W (130 CNY) + IMX219 Camera (50 CNY) + USB Cable (7 CNY) + TF card 128GB (20 CNY) + Camera mount by 3D print (20 CNY) = ~230 CNY

## Features
- Supports timed photography and automatic image uploads, will save into raspberry and move to cloud/NAS (Synology)
- Intelligent exposure settings, automatically adjusting shutter speed based on ambient light
- Supports different image formats, such as RAW and DNG
- Generates timelapse images and stores them in the cloud

## Core Strategy
Python control: Query local sun raise and sun set time (everyday), as sun raise/sun set as T0, shot from T0-40 mins to T0+40 mins every 2 mins. 2 more shots at noon, total 44 shots one day

Raspberry Pi control (by systemd): 1 timer using for trigger python every minute from 4am - 8am, and 4pm - 830pm. Once trigger .py, it will determine if it is in the time frame, if yes, shot; if not, exit.

Since the light contrast is very strong in sun raise/set, the camera's auto exposure cannot work well. Pre-set camera as "ISO-100, white-balance = indoor, brightness = 0", take 1 shot as preview, use "pillow" to calculate whole picture average brightness (avg); also use "numpy" to calculate highlight_ratio. Set up several avg gradients, for each gradient, take 7 pictures at different exposures, choose 1 picture's shot parameters with avg closest 110 and lowest highlight_ratio, then use this parameter as the final shot.

Due to RAM limit in raspberry, such frequency libcamera calls will lead insufficient RAM. Another reboot timer is introduced into Raspberry systemd at 2am, 10am and 2pm.

## Known Bug
- Sun raise and sun set time looks like based on UTC 0, if use Beijing Time, i.e. UTC+8, sun raise time and sun set time will not in the same day, to make sure the time in the same day. Time calculation is +48 hours.
- Log.txt will record so much useless information, don't know how to remove yet.
- RAM used up too rapid, don't know how to solve yet, rapid reboot as temp solution.

## Installation
- Upload .py into Raspberry via SSH or Command (pscp `C:\your folder name\timelapse.py RaspberryUserName@192.168.x.xxx:/home/timelapse/timelapse.py`)
- Create following file into `/etc/systemd/system` (Raspberry): `timelapse.service` (trigger .py), `timelapse.timer` (trigger timelapse.service), `reboot-schedule.service` (trigger reboot), `reboot-schedule.timer` (setup reboot time and trigger reboot-schedule.service), due to permission restriction, these 4 files cannot be direct copied into folder. Have to use sudo nano /etc/systemd/system/`reboot-schedule.service` to create and edit. Just copy and paste those 4 files code into correspondence files.
- Remember to reload systemd and restart timer and service by following commands:
sudo systemctl daemon-reload #reload systemd

sudo systemctl enable timelapse.service

sudo systemctl start timelapse.service

sudo systemctl enable timelapse.timer

sudo systemctl start timelapse.timer

sudo systemctl enable reboot-schedule.service

sudo systemctl start reboot-schedule.service

sudo systemctl enable reboot-schedule.timer

sudo systemctl start reboot-schedule.timer
