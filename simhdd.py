#!/usr/bin/env python3

from atapt import atapt
import ctypes
import sys
import time
import os
import termios
import fcntl
from multiprocessing import Process, Manager

SECTORS_AT_ONCE = 256
SLOW_SECTOR_LATENCY = 50
NEED_QUIT = True
ERASE_WITH_PATTERN = False


def printDisks(sel):
    print("{:^5}{:^30}{:^20}{:^6}    {}{:^24}{}".format("#", "Model",
                                                        "Serial", "Size", "Mode  Loop", "Progress", "  Speed   Slow   Error"))
    print(123 * "-")
    for key in select:
        if key == 0:
            continue
        print()
        if select.index(key) == sel:
            print('\033[30m' + '\033[47m', end="")
        else:
            print('\033[37m' + '\033[40m', end="")
        print("{:^5}{:<30}{:<20}{:>5} Gb {:^7}{:^5}{:<22}{:>2}{:^7}{:^7}{:^7}".format(select.index(key), disks[key].model,
                                                                            disks[key].serial, int(disks[key].size),
                                                                            mode[disks[key].serial], loop[disks[key].serial],
                                                                            "[" + progress[disks[key].serial] * "#" + (20 - progress[disks[key].serial]) * " " + "]",
                                                                            busy[disks[key].serial], speed[disks[key].serial], slow[disks[key].serial], error[disks[key].serial], end=""))
        print('\033[37m' + '\033[40m', end="")
    print()


def showSmart(serial):
    disk = disks[serial]
    os.system('clear')
    # Disk identifycation
    print()
    print("Device:             " + disk.dev)
    print("Model:              " + disk.model)
    print("Firmware:           " + disk.firmware)
    print("Serial:             " + disk.serial)
    print("Sectors:            %d" % disk.sectors)
    print("Size:               %d Gb" % disk.size)
    if disk.ssd:
        print("Type:               SSD")
    else:
        print("Type:               HDD")
        if disk.rpm > 1:
            print("RPM:                %d" % disk.rpm)
    print("log. sector size:   %d bytes" % disk.logicalSectorSize)
    print("phys. sector size:  %d bytes" % disk.physicalSectorSize)

    # Read SMART
    print()
    print("Read SMART")
    disk.readSmart()
    print()
    print("SMART VALUES:")
    print("ID# ATTRIBUTE NAME             TYPE     UPDATED   VALUE  WORST  THRESH  RAW")
    for id in sorted(disk.smart):
        if disk.smart[id][3] < disk.smart[id][5]:
            print("\033[91m", end="")
        # [pre_fail, online, current, worst, raw, treshold]
        print("{:>3} {:<24} {:10} {:7}  {}  {}  {}    {}".format(id, disk.getSmartStr(id),
                                                                 "Pre-fail" if disk.smart[id][0] else "Old_age",
                                                                 "Always" if disk.smart[id][1] else "Offline",
                                                                 "  %03d" % disk.smart[id][2],
                                                                 "  %03d" % disk.smart[id][3],
                                                                 "  %03d" % disk.smart[id][5], disk.getSmartRawStr(id)))
        print("\033[0m", end="")
    if disk.readSmartStatus() == atapt.SMART_BAD_STATUS:
        print("\033[91mSMART STATUS BAD!\033[0m")
    while not sys.stdin.read(1):
        time.sleep(0.1)
    os.system('clear')


def nextBusy(busy):
    if busy == "|":
        return("/")
    elif busy == "/":
        return("-")
    elif busy == "-":
        return("\\")
    elif busy == "\\":
        return("|")


def diskLongTest(serial):
    disk = disks[serial]
    slow[serial] = 0
    error[serial] = 0
    progress[serial] = 0
    loop[serial] = 0
    speed[serial] = 0
    awgSpeed = 0
    mode[serial] = "Long"
    time.sleep(1)
    busy[serial] = "|"
    try:
        disk.runSmartSelftest(2)  # Execute SMART Extended self-test routine immediately in off-line mode
    except atapt.senseError:
        error[serial] = 1
    disk.readSmart()
    while disk.selftestStatus >> 4 == 0x0F:
        time.sleep(0.5)
        disk.readSmart()
        progress[serial] = 20 - (disk.selftestStatus & 0x0F) * 2
        busy[serial] = nextBusy(busy[serial])
        if mode[serial] != "Long":
            error[serial] = 0
            try:
                disk.runSmartSelftest(0x7F)  # Abort off-line mode self-test routine
            except atapt.senseError:
                error[serial] = 1
            slow[serial] = 0
            progress[serial] = 0 
            busy[serial] = " "
            return
    if disk.selftestStatus != 0:
        error[serial] = disk.selftestStatus
    else:
        progress[serial] = 20
    mode[serial] = "Idle"
    busy[serial] = " "
    speed[serial] = 0


def diskShortTest(serial):
    disk = disks[serial]
    slow[serial] = 0
    error[serial] = 0
    progress[serial] = 0
    loop[serial] = 0
    speed[serial] = 0
    awgSpeed = 0
    mode[serial] = "Short"
    time.sleep(1)
    busy[serial] = "|"
    try:
        disk.runSmartSelftest(1)  # Execute SMART Short self-test routine immediately in off-line mode
    except atapt.senseError:
        error[serial] = 1
    disk.readSmart()
    while disk.selftestStatus >> 4 == 0x0F:
        time.sleep(0.5)
        disk.readSmart()
        progress[serial] = 20 - (disk.selftestStatus & 0x0F) * 2
        busy[serial] = nextBusy(busy[serial])
        if mode[serial] != "Short":
            error[serial] = 0
            try:
                disk.runSmartSelftest(0x7F)  # Abort off-line mode self-test routine
            except atapt.senseError:
                error[serial] = 1
            slow[serial] = 0
            progress[serial] = 0 
            busy[serial] = " "
            return
    if disk.selftestStatus != 0:
        error[serial] = disk.selftestStatus
    else:
        progress[serial] = 20
    mode[serial] = "Idle"
    busy[serial] = " "
    speed[serial] = 0


def diskVerify(serial):
    disk = disks[serial]
    slow[serial] = 0
    error[serial] = 0
    progress[serial] = 0
    loop[serial] = 0
    speed[serial] = 0
    awgSpeed = 0
    mode[serial] = "Read"
    time.sleep(1)
    busy[serial] = "|"
    blockSize = disk.logicalSectorSize * SECTORS_AT_ONCE / 1024 / 1024
    tail = disk.sectors % SECTORS_AT_ONCE
    for i in range(0, disk.sectors - tail - 1, SECTORS_AT_ONCE):
        try:
            disk.verifySectors(SECTORS_AT_ONCE, i)
        except atapt.senseError:
            error[serial] = error[serial] + 1
        awgSpeed = awgSpeed + int(1 / (0.001 * disk.duration) * blockSize)
        if disk.ata_error != 0:
            error[serial] = error[serial] + 1
        elif disk.duration > SLOW_SECTOR_LATENCY:
            slow[serial] = slow[serial] + 1
        if (i % (SECTORS_AT_ONCE * 512)) == 0:
            speed[serial] = int(awgSpeed / 512)
            awgSpeed = 0
            progress[serial] = int(20 / disk.sectors * i)
            busy[serial] = nextBusy(busy[serial])
        if mode[serial] != "Read":
            slow[serial] = 0
            error[serial] = 0
            progress[serial] = 0
            busy[serial] = " "
            return
    try:
        disk.verifySectors(tail, disk.sectors - tail)
    except atapt.senseError:
        pass
    if disk.ata_error != 0:
        error[serial] = error[serial] + 1
    elif disk.duration > 100:
        slow[serial] = slow[serial] + 1
    mode[serial] = "Idle"
    progress[serial] = 20
    busy[serial] = " "
    speed[serial] = 0


def diskErase(serial):
    disk = disks[serial]
    loop[serial] = 0
    mode[serial] = "Write"
    time.sleep(1)
    busy[serial] = "|"
    blockSize = disk.logicalSectorSize * SECTORS_AT_ONCE / 1024 / 1024
    while 1:
        speed[serial] = 0
        awgSpeed = 0
        slow[serial] = 0
        error[serial] = 0
        progress[serial] = 0
        tail = disk.sectors % SECTORS_AT_ONCE
        buf = ctypes.c_buffer(disk.logicalSectorSize * SECTORS_AT_ONCE)
        for i in range(disk.logicalSectorSize * SECTORS_AT_ONCE):
            if ERASE_WITH_PATTERN:
                buf[i] = int(i % 128)
            else:
                buf[i] = 0
        for i in range(0, disk.sectors - tail - 1, SECTORS_AT_ONCE):
            try:
                disk.writeSectors(SECTORS_AT_ONCE, i, buf)
            except atapt.senseError:
                error[serial] = error[serial] + 1
            awgSpeed = awgSpeed + int(1 / (0.001 * disk.duration) * blockSize)
            if disk.ata_error != 0:
                error[serial] = error[serial] + 1
            elif disk.duration > SLOW_SECTOR_LATENCY:
                slow[serial] = slow[serial] + 1
            if (i % (SECTORS_AT_ONCE * 512)) == 0:
                speed[serial] = int(awgSpeed / 512)
                awgSpeed = 0
                progress[serial] = int(20 / disk.sectors * i)
                busy[serial] = nextBusy(busy[serial])
            if mode[serial] != "Write":
                slow[serial] = 0
                error[serial] = 0
                progress[serial] = 0
                loop[serial] = 0
                busy[serial] = " "
                return
        buf = ctypes.c_buffer(disk.logicalSectorSize * tail)
        for i in range(disk.logicalSectorSize * tail):
            if ERASE_WITH_PATTERN:
                buf[i] = int(i % 128)
            else:
                buf[i] = 0
        try:
            disk.writeSectors(tail, disk.sectors - tail, buf)
        except atapt.senseError:
            pass
        if disk.ata_error != 0:
            error[serial] = error[serial] + 1
        elif disk.duration > 100:
            slow[serial] = slow[serial] + 1
        loop[serial] = loop[serial] + 1


m = Manager()
disks = {}
select = [0]
progress = m.dict()
mode = m.dict()
loop = m.dict()
slow = m.dict()
error = m.dict()
busy = m.dict()
speed = m.dict()
dev = filter(lambda x: x.find('sd') != -1 and len(x) == 3, os.listdir("/dev"))
for d in dev:
    disk = atapt.atapt("/dev/" + d)
    disks[disk.serial] = disk
    select.append(disks[disk.serial].serial)
    progress[disk.serial] = 0
    loop[disk.serial] = 0
    slow[disk.serial] = 0
    error[disk.serial] = 0
    speed[disk.serial] = 0
    busy[disk.serial] = " "
    mode[disk.serial] = "Idle"

sel = 0
try:
    fd = sys.stdin.fileno()

    oldterm = termios.tcgetattr(fd)
    newattr = termios.tcgetattr(fd)
    newattr[3] = newattr[3] & ~termios.ICANON & ~termios.ECHO
    termios.tcsetattr(fd, termios.TCSANOW, newattr)

    oldflags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, oldflags | os.O_NONBLOCK)
    print('\033[9;0]' + '\033[14;0]', end="")
    os.system('clear')
    # os.system('dmesg -D')

    while 1:
        ch = sys.stdin.read(1)
        print('\033[0;0H', end="")
        printDisks(sel)
        if (ch >= "1") and (ch <= str(len(select) - 1)):
            sel = int(ch)
            ch = 0
        if sel > 0:
            print("Select action :   I-Info   V-Verify   E-Erase   R-Short   L-Long   S-Stop", end="")
            if NEED_QUIT:
                print("    Q-Quit")
            else:
                print("            ")
            if ch == "i" or ch == "I":
                showSmart(select[sel])
                sel = 0
            elif ch == "v" or ch == "V":
                d = Process(target=diskVerify, args=(select[sel],))
                d.start()
                sel = 0
            elif ch == "e" or ch == "E":
                d = Process(target=diskErase, args=(select[sel],))
                d.start()
                sel = 0
            elif ch == "r" or ch == "R":
                d = Process(target=diskShortTest, args=(select[sel],))
                d.start()
                sel = 0
            elif ch == "l" or ch == "L":
                d = Process(target=diskLongTest, args=(select[sel],))
                d.start()
                sel = 0
            elif ch == "s" or ch == "S":
                mode[select[sel]] = "Idle"
                sel = 0
            elif NEED_QUIT and (ch == "q" or ch == "Q"):
                exit()
        else:
            print("Select disk : _" + 100 * " ")

        time.sleep(0.1)
finally:
    termios.tcsetattr(fd, termios.TCSAFLUSH, oldterm)
    fcntl.fcntl(fd, fcntl.F_SETFL, oldflags)

