#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Copyright (c) 2016, Kieran J. Broadfoot. All rights reserved.

import sys
import os
import re
import time
import subprocess
import socket
import simplejson as json
import requests

class Plugin(indigo.PluginBase):

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        self.access_token = False

    def __del__(self):
        indigo.PluginBase.__del__(self)

    def startup(self):
        self.logger.info("starting flowerpower plugin")
        if self.getBearerToken(self.pluginPrefs.get("username", ""), self.pluginPrefs.get("password", ""), self.pluginPrefs.get("accessID", ""), self.pluginPrefs.get("accessSecret", "")):
            self.initDevices()

    def getBearerToken(self, username, password, accessid, accesssecret):
        try:
            req = requests.get('https://api-flower-power-pot.parrot.com/user/v1/authenticate',
                               data={'grant_type': 'password',
                                     'username': username,
                                     'password': password,
                                     'client_id': accessid,
                                     'client_secret': accesssecret,
                                     })
            response = req.json()
            try:
                self.access_token = response['access_token']
                self.logger.info("credentials are valid")
                return True
            except KeyError:
                self.logger.error("credentials are *invalid*")
                return False
        except Exception:
            self.logger.error("unable to communicate with cloud service")
            return False

    def shutdown(self):
        self.logger.info("stopping flowerpower plugin")

    def validatePrefsConfigUi(self, valuesDict):
        if self.getBearerToken(valuesDict["username"],valuesDict["password"],valuesDict["accessID"],valuesDict["accessSecret"]):
            return True
        else:
            errorDict = indigo.Dict()
            errorDict["username"] = "Invalid credentials"
            errorDict["password"] = "Invalid credentials"
            errorDict["accessID"] = "Invalid credentials"
            errorDict["accessSecret"] = "Invalid credentials"
            return (False, valuesDict, errorDict)

    def initDevices(self):
        try:
            req = requests.get('https://api-flower-power-pot.parrot.com/garden/v2/configuration',
                               headers={'Authorization': 'Bearer {token}'.format(token=self.access_token)})
            response = req.json()
            for location in response['locations']:
                device = None
                for dev in indigo.devices.iter("self"):
                    if dev.address == location['sensor']['sensor_serial']:
                        device = indigo.devices[dev.name]
                if device == None:
                    self.createDevice(location['sensor']['sensor_serial'],
                                      location['sensor']['sensor_type'],
                                      location['plant_nickname'],
                                      location['location_identifier'])
        except Exception:
            self.logger.error("unable to communicate with cloud service")

    def createDevice(self, serial, type, name, location):
        self.logger.info("creating FlowerPower sensor \""+name+"\" in Indigo")
        device = None
        while device == None:
            try:
                device = indigo.device.create(protocol=indigo.kProtocol.Plugin,
                                              address=serial,
                                              name=name,
                                              description="Parrot Flower Power Sensor",
                                              pluginId="com.kieranbroadfoot.indigoplugin.FlowerPower",
                                              deviceTypeId="FlowerPowerSensor",
                                              props={})
                updates = [
                    {'key':'locationIdentifier', 'value':location},
                    {'key':'state', 'value':'active'},
                    {'key':'sensorType', 'value':type}
                ]
                device.updateStatesOnServer(updates)
            except ValueError:
                self.logger.info("name of FlowerPower sensor is not unique - renaming to "+name+"_"+serial)
                name = name+"_"+serial
        return device

    def generateListValue(self, input):
        if input == None:
            return ""
        if "too_low" in input:
            return "too_low"
        if "good" in input:
                return "good"
        if "too_high" in input:
            return "too_high"
        self.logger.warn("received unknown response from cloud: "+input)
        return ""

    def runConcurrentThread(self):
        while True:
            if self.access_token:
                sensors = []
                for sensor in indigo.devices.iter("self"):
                    sensors.append(sensor.id)
                try:
                    req = requests.get('https://api-flower-power-pot.parrot.com/garden/v1/status',
                                       headers={'Authorization': 'Bearer {token}'.format(token=self.access_token)})
                    response = req.json()
                    for location in response['locations']:
                        device = None
                        while device == None:
                            for dev in indigo.devices.iter("self"):
                                if dev.states["locationIdentifier"] == location['location_identifier']:
                                    device = indigo.devices[dev.name]
                            if device == None:
                                self.logger.warn("seen a sensor which is unknown to me. re-generating devices")
                                self.initDevices()
                        updates = [
                            {'key':'temperatureValue', 'value':location['air_temperature']['gauge_values']['current_value']},
                            {'key':'lightValue', 'value':location['light']['gauge_values']['current_value']},
                            {'key':'fertilizerValue', 'value':location['fertilizer']['gauge_values']['current_value']},
                            {'key':'soilMoistureValue', 'value':location['watering']['soil_moisture']['gauge_values']['current_value']},
                            {'key':'temperatureInstruction', 'value':self.generateListValue(location['air_temperature']['instruction_key'])},
                            {'key':'lightInstruction', 'value':self.generateListValue(location['light']['instruction_key'])},
                            {'key':'fertilizerInstruction', 'value':self.generateListValue(location['fertilizer']['instruction_key'])},
                            {'key':'soilMoistureInstruction', 'value':self.generateListValue(location['watering']['soil_moisture']['instruction_key'])},
                            {'key':'batteryLevel', 'value':location['battery']['gauge_values']['current_value']},
                            {'key':'state', 'value':'active'}
                        ]
                        device.updateStatesOnServer(updates)
                        try:
                            sensors.remove(device.id)
                        except ValueError:
                            # if the sensor does not appear in the list it means we newly created it. no issue.
                            pass
                    for s in sensors:
                        self.logger.warn("setting sensor "+s+" to inactive")
                        sensor = indigo.devices[s]
                        sensor.updateStateOnServer("state", "inactive")
                except Exception:
                    self.logger.warn("unable to communicate with cloud service")
                self.sleep(900)

    def createKeys(self):
        self.browserOpen("https://api-flower-power-pot.parrot.com/api_access/signup")

    def visitAPI(self):
        self.browserOpen("http://developer.parrot.com/docs/FlowerPower/")