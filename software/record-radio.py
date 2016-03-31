#!/usr/bin/env python3
version = 1457968166

import os
import sys
import platform
import requests
from os import path

# import multiprocessing
from multiprocessing import Process, Lock

from rtlsdr import RtlSdr, librtlsdr

from subprocess import Popen, PIPE

import numpy as np

import time
import datetime

import hashlib
from uuid import getnode as get_mac

import json

gain_step = 1.0
gain_start = 1.0
gain_end = 48.0
signal_threshold = 0.10


def calibrating_gain_with_windows(sdr, samplerate):

    signal_level = 0.0
    gain = gain_start

    while signal_level < signal_threshold and gain <= gain_end:
        gain = gain+gain_step
        sdr.gain = gain
        # print('hello world', sdr.gain
        samples = (sdr.read_samples(2*samplerate))
        signal_level = np.mean(np.abs(samples))
        print(sdr.gain, signal_level, np.min(np.abs(samples)), np.max(np.abs(samples)))

    if sdr.gain >= 49.0:
        print("activating autogain")
        gain = 'auto'
        sdr.gain = gain
        # print('hello world', sdr.gain
        samples = (sdr.read_samples(2*samplerate))
        signal_level = np.mean(np.abs(samples))
        print(sdr.gain, signal_level, np.min(np.abs(samples)), np.max(np.abs(samples)))
    else:
        print("found gain")
        gain = gain - gain_step
        sdr.gain = gain
        samples = (sdr.read_samples(2*samplerate))
        signal_level = np.mean(np.abs(samples))
        print(sdr.gain, signal_level, np.min(np.abs(samples)), np.max(np.abs(samples)))

    return gain


def calibrating_gain_with_linux(device_number, center_frequency, samplerate):

    signal_level = 0.0
    gain = gain_start

    read_samples = (2*samplerate)
    rtl_sdr_exe = "rtl_sdr"

    while signal_level < signal_threshold*127.0 and gain <= gain_end:
        gain = gain+gain_step

        sdr = Popen([rtl_sdr_exe, "-d", str(device_number), "-f", str(center_frequency), "-s", str(samplerate),
                     "-g", str(gain), "-p", str(freq_correction), "-"],
                    stdout=PIPE, stderr=None)

        print("test")
        stream_data = sdr.stdout.read(read_samples)
        print("test1")
        samples = [int(x) - 127 for x in stream_data]
        print("test2")
        signal_level = np.mean(np.abs(samples))
        sdr.kill()
        print(gain, signal_level/127.0, np.min(np.abs(samples)), np.max(np.abs(samples)))

    if gain >= 49.0:
        print("activating autogain")
        gain = 0
        sdr = Popen([rtl_sdr_exe, "-d", str(device_number), "-f", str(center_frequency), "-s", str(samplerate),
                     "-g", "0", "-p", str(freq_correction), "-"],
                    stdout=PIPE, stderr=None)

        stream_data = sdr.stdout.read(read_samples)
        samples = [int(x) - 127 for x in stream_data]
        signal_level = np.mean(np.abs(samples))
        sdr.kill()
        print(gain, signal_level/127.00, np.min(np.abs(samples)), np.max(np.abs(samples)))
    else:
        print("found gain")
        gain = gain - gain_step
        sdr = Popen([rtl_sdr_exe, "-d", str(device_number), "-f", str(center_frequency), "-s", str(samplerate),
                     "-g", str(gain), "-p", str(freq_correction), "-"],
                    stdout=PIPE, stderr=None)

        stream_data = sdr.stdout.read(read_samples)
        samples = [int(x) - 127 for x in stream_data]
        signal_level = np.mean(np.abs(samples))
        sdr.kill()
        print(gain, signal_level/127.0, np.min(np.abs(samples)), np.max(np.abs(samples)))
    print("ready")
    return gain


def do_sha224(x):
    hashed = hashlib.sha224(x)
    hashed = hashed.hexdigest()
    return hashed


def storing_stream(l, device_number, folder, subfolders, center_frequency, samplerate, gain, nsamples, freq_correction,
                   user_hash):
    l.acquire()
    print(device_number, center_frequency, samplerate, gain, nsamples, freq_correction)
    # configure device
    sdr = RtlSdr(device_index=device_number)
    sdr.center_freq = center_frequency
    sdr.sample_rate = samplerate
    if freq_correction != 0:
        sdr.freq_correction = freq_correction   # PPM
    sdr.gain = gain
    print('hello world')
    timestamp = time.mktime(time.gmtime())
    samples = sdr.read_bytes(nsamples*2)
    sdr.close()
    l.release()

    print("save")
    filename = folder + "/" + subfolders[0] + "/tmp_" + user_hash + "_" + str(center_frequency) + "_" + str(timestamp).split(".")[0]
    # np.savez_compressed(filename, samples) # storing by numpy and copressing it
    np.save(filename, samples)
    os.rename(filename + ".npy", folder + "/" + subfolders[0] + "/" + user_hash + "_" + str(center_frequency) + "_" +
              str(timestamp).split(".")[0]+".npy")

    del samples

    return filename


def storing_stream_with_linux(stream_data, device_number, folder, subfolders, center_frequency, samplerate,
                              gain, nsamples, freq_correction, user_hash):
    timestamp = time.mktime(time.gmtime())

    test = np.fromstring(stream_data, dtype=np.uint8)
    # samples_hash = do_sha224(test)

    print("save")
    basename = "{hash}_{freq}_{time:0.0f}".format(hash=user_hash, freq=center_frequency, time=timestamp)
    filename = path.join(folder, subfolders[0], "tmp_" + basename)
    # np.savez_compressed(filename, samples) # storing by numpy and copressing it
    np.save(filename, test)
    os.rename(filename + ".npy",
              path.join(folder, subfolders[0], basename + ".npy"))

    del test

    return filename


def get_groundstationid():
    if os.path.exists("groundstationid.npy"):
        id = str(np.load("groundstationid.npy"))
    else:
        id = do_sha224(str(get_mac()).encode("utf-8"))  # added .encode("utf-8") for python 3.4.3
        np.save("groundstationid.npy", id)

    print("your groundstation id is", id)
    return id


def loading_config_file(pathname_config):
    try:
        r = requests.get('https://raw.githubusercontent.com/aerospaceresearch/dgsn-hub-ops/master/io-radio/'
                         'record-config.json')
        print("downloading record-config.json from github")
        with open(pathname_config+'/record-github-config.json', 'w') as f:
            json.dump(r.json(), f)

    except requests.exceptions.RequestException as e:
        print(e)
        if not os.path.exists(pathname_config + '/record-github-config.json'):
            print("creating empty record-github-config.json")
            with open(pathname_config + '/record-github-config.json', 'w') as f:
                json.dump({"version": 1457968166, "created": 0}, f)

    with open(pathname_config+'/record-github-config.json') as data_file:
        data_github = json.load(data_file)

    if not os.path.exists(pathname_config+'/record-config.json'):
        create_config_file_template(pathname_config+'/record-config.json')

    with open(pathname_config+'/record-config.json') as data_file:
        data_infile = json.load(data_file)

    print("created on Github:", data_github["created"], "and on local file:", data_infile["created"])
    if data_github["created"] >= data_infile["created"]:
        print("using github config file")
        data = data_github
    else:
        print("using local config file")
        data = data_infile

    return data


def create_config_file_template(file):
    # todo: always having the curent template in here!

    with open(file, "w") as f:
        json.dump({"comment": "prototpye status",
                   "version": 1457968166,
                   "created": 1457968167,
                   "device_number": 0,
                   "center_frequency": 104300000,
                   "samplerate": 2048000,
                   "secondsofrecording": 40,
                   "freq_correction": 1,
                   "recording_start": {"y": 2016, "m": 3, "d": 31, "hh": 0, "mm": 0, "ss": 0},
                   "recording_end": {"y": 2016, "m": 3, "d": 31, "hh": 1, "mm": 0, "ss": 0},
                   "gain_start": 1.0,
                   "gain_end": 48.0,
                   "gain_step": 1.0,
                   "signal_threshold": 0.12
                   }, f, indent=4)


if __name__ == '__main__':

    print("you are using", platform.system(), platform.release(), os.name)

    # creating the central shared dgsn-node-data for all programs on the nodes
    #######################################
    pathname = os.path.dirname(sys.argv[0])
    pathname_all = ""
    for i in range(len(pathname.split("/"))-1):
        pathname_all = pathname_all + pathname.split("/")[i] + "/"
    pathname_save = pathname_all + "dgsn-node-data"
    pathname_config = pathname_all + "dgsn-hub-ops"

    # creating the dump folder for files and the needed data folders
    #######################################
    if not os.path.exists(pathname_save):
        os.makedirs(pathname_save)

    folder = pathname_save+"/rec"
    subfolders = ["iq", "sdr", "gapped", "coded"]
    if not os.path.exists(folder):
        os.makedirs(folder)

    if os.path.exists(folder):
        for i in range(len(subfolders)):
            if not os.path.exists(folder+"/"+subfolders[i]):
                os.makedirs(folder+"/"+subfolders[i])

    if not os.path.exists(pathname_config):
        os.makedirs(pathname_config)

    pathname_config = pathname_config + "/io-radio"

    if not os.path.exists(pathname_config):
        os.makedirs(pathname_config)

    # setting the rtlsdr before the gain finding
    #####################################

    # getting one file to each node very simple via github, or via a local file copy
    data = loading_config_file(pathname_config)

    # getting the specific settings for the node itself. perhaps it cannot be as fast as others
    with open(pathname+'/node-config.json') as data_file:
        data_node = json.load(data_file)

    device_number = data["device_number"]
    center_frequency = data["center_frequency"]
    samplerate = data["samplerate"]

    # this will be necessary in case a full fledged pc is a node or in case a micro pc is used with less RAM
    if data["secondsofrecording"] <= data_node["secondsofrecording_maximum"]:
        secondsofrecording = data["secondsofrecording"]
    else:
        secondsofrecording = data_node["secondsofrecording_maximum"]
    print("record seconds commanded", data["secondsofrecording"], "record seconds maximum",
          data_node["secondsofrecording_maximum"], "and it is", secondsofrecording)

    nsamples = secondsofrecording*samplerate
    freq_correction = data["freq_correction"]
    user_hash = get_groundstationid()

    dt = datetime.datetime(data["recording_start"]["y"], data["recording_start"]["m"], data["recording_start"]["d"],
                           data["recording_start"]["hh"], data["recording_start"]["mm"], data["recording_start"]["ss"])
    recording_start = time.mktime(dt.timetuple())

    dt = datetime.datetime(data["recording_end"]["y"], data["recording_end"]["m"], data["recording_end"]["d"],
                           data["recording_end"]["hh"], data["recording_end"]["mm"], data["recording_end"]["ss"])
    recording_stop = time.mktime(dt.timetuple())

    # getting the data for calibration
    gain_start = data["gain_start"]
    gain_end = data["gain_end"]
    gain_step = data["gain_step"]
    signal_threshold = data["signal_threshold"]

    ##################################
    print("starting the fun...")

    if platform.system() == "Windows":
        print("detecting a windows")
        ##############
        device_count = librtlsdr.rtlsdr_get_device_count()
        print("number of rtl-sdr devices:", device_count)

        if device_count > 0:
            lock = Lock()
            jobs = []
            sdr = RtlSdr(device_index=device_number)
            sdr.center_freq = center_frequency
            sdr.sample_rate = samplerate
            # sdr.freq_correction = 1   # PPM

            # calibrating the dongle
            gain = 0
            if gain_start >= gain_end:
                gain = gain_end
            else:
                gain = calibrating_gain_with_windows(sdr, samplerate)

            print("used gain", gain)
            sdr.gain = gain
            sdr.close()

            while time.mktime(time.gmtime()) <= recording_start:
                # waiting for the time to be right :)
                time.sleep(10)
                print("still", recording_start - time.mktime(time.gmtime()), "to wait")

            print("recording starts now...")

            utctime = time.mktime(time.gmtime())
            if utctime >= recording_start and utctime <= recording_stop:
                for recs in range(2):
                    p = Process(target=storing_stream, args=(lock, device_number, folder, subfolders, center_frequency,
                                                             samplerate, gain, nsamples, freq_correction, user_hash))
                    jobs.append(p)
                    p.start()
                print("end")

                while time.mktime(time.gmtime()) <= recording_stop:
                    time.sleep(2)
                    for n, p in enumerate(jobs):
                        if not p.is_alive() and time.mktime(time.gmtime()) <= recording_stop:
                            jobs.pop(n)
                            recs += 1
                            p = Process(target=storing_stream, args=(lock, device_number, folder, subfolders,
                                                                     center_frequency, samplerate, gain, nsamples,
                                                                     freq_correction, user_hash))
                            jobs.append(p)
                            p.start()
                            print("rec number", recs, 'added')

            for job in jobs:
                job.join()

    elif platform.system() == "Linux" or platform.system() == "Linux2":
        print("detecting a linux")

        # getNumber_of_rtlsdrs_with_linux()

        gain = 0
        if gain_start >= gain_end:
            gain = gain_end
        else:
            gain = calibrating_gain_with_linux(device_number, center_frequency, samplerate)
        print("used gain", gain)

        while time.mktime(time.gmtime()) <= recording_start:
            # waiting for the time to be right :)
            time.sleep(10)
            print("still", recording_start - time.mktime(time.gmtime()), "to wait")

        print("recording starts now...")

        rtl_sdr_exe = "rtl_sdr"
        sdr = Popen([rtl_sdr_exe, "-d", str(device_number), "-f", str(center_frequency), "-s", str(samplerate),
                     "-g", str(gain), "-p", str(freq_correction), "-"],
                    stdout=PIPE, stderr=None)

        ret = None
        while time.mktime(time.gmtime()) <= recording_stop:
            stream_data = sdr.stdout.read(nsamples*2)
            storing_stream_with_linux(stream_data, device_number, folder, subfolders, center_frequency, samplerate,
                                      gain, nsamples, freq_correction, user_hash)

        sdr.kill()
