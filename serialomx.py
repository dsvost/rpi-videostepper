#!/bin/python

# Copyright 2015-2016 Dmitriy Vostrikov <dsvost@gmail.com>
#
# This file is part of rpi-videostepper.
#
# rpi-videostepper is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# rpi-videostepper is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with RPiVideoStepper.  If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import daemon
import lockfile
import serial
import io
import json
# import pdb

sys.path.append('./pyopengles')

import pyopengles
#import dbus

from pyomxplayer import OMXPlayer
from threading import Thread, Lock
from time import sleep

import RPi.GPIO as GPIO

ttydev = '/dev/ttyAMA0'
#ttydev = '/dev/tty10'

config_path = '/opt/video-loops/VIDEO/config'
audio_output = 'local'
#subtitles_font_arg = ' --font /opt/SerialOmxControl/expressway.ttf --italic-font /opt/SerialOmxControl/expressway.ttf --font-size 48 --align center --no-ghost-box --no-osd --no-boost-on-downmix'
subtitles_font_arg = ' --font /opt/SerialOmxControl/expressway.ttf --italic-font /opt/SerialOmxControl/expressway.ttf --font-size 48 --align center --no-ghost-box --no-osd'

dctx = daemon.DaemonContext(
    working_directory='/opt/video-loops/VIDEO',
    pidfile=lockfile.FileLock('/var/run/serialomx.pid')
)

class Singleton:
    """
    A non-thread-safe helper class to ease implementing singletons.
    This should be used as a decorator -- not a metaclass -- to the
    class that should be a singleton.

    The decorated class can define one `__init__` function that
    takes only the `self` argument. Other than that, there are
    no restrictions that apply to the decorated class.

    To get the singleton instance, use the `Instance` method. Trying
    to use `__call__` will result in a `TypeError` being raised.

    Limitations: The decorated class cannot be inherited from.

    """

    def __init__(self, decorated):
        self._decorated = decorated

    def Instance(self):
        """
        Returns the singleton instance. Upon its first call, it creates a
        new instance of the decorated class and calls its `__init__` method.
        On all subsequent calls, the already created instance is returned.

        """
        try:
            return self._instance
        except AttributeError:
            self._instance = self._decorated()
            return self._instance

    def __call__(self):
        raise TypeError('Singletons must be accessed through `Instance()`.')

    def __instancecheck__(self, inst):
        return isinstance(inst, self._decorated)


@Singleton
class VideoStepper:
    def __init__(self):
        print 'Init VideoStepper'

        try:
            cfgFd = open(config_path, 'r')
            self.cfg = json.load(cfgFd)
            self.stepsNumber = len(self.cfg['steps'])
        except IOError:
            quit()

        # need pause if true
        self.isFirstVideoMovie = False
        self.isFirstVideoMovie2 = False

        if 'general' in self.cfg:
            if 'movies_path' in self.cfg['general']:
                self.movies_path = self.cfg['general']['movies_path']
            else:
                print 'Error: cfg not contain general/movies_path'
                quit()

            if 'baudrate' in self.cfg['general']:
                self.s_baudrate = self.cfg['general']['baudrate']
            else:
                self.s_baudrate = 19200

            if 'bytesize' in self.cfg['general']:
                self.s_bytesize = self.cfg['general']['bytesize']
            else:
                self.s_bytesize = 8

            if 'parity' in self.cfg['general']:
                self.s_parity = self.cfg['general']['parity']
            else:
                self.s_parity = 'N'

            if 'stopbits' in self.cfg['general']:
                self.s_stopbits = self.cfg['general']['stopbits']
            else:
                self.s_stopbits = 1

        else:
            print 'Error: cfg not contain general'
            quit()

        if 'map' not in self.cfg:
            print 'Error: cfg not contain map'
            quit()

        if 'steps' not in self.cfg:
            print 'Error: cfg not contain steps'
            quit()

        if 'steps_order' not in self.cfg:
            print 'Error: cfg not contain steps_order'
            quit()

        self.gpio = {}
        if 'gpio' in self.cfg:
            GPIO.setmode(GPIO.BCM)

            GPIO.setup(25, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(25, GPIO.RISING, callback=gpio_event, bouncetime=200)

            for idx, curGpio in enumerate(self.cfg['gpio']):
                gpioNum = curGpio['gpio']
                gpioStep = curGpio['step']

                self.gpio[gpioNum] = gpioStep

                GPIO.setup(gpioNum, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                GPIO.add_event_detect(gpioNum, GPIO.FALLING, callback=gpio_event, bouncetime=200)

        self.currentStep = ""
        self.players = []
        self.currentPlayer = None
        self.nextStepPlayer = None
        self.stepIdForNextStepPlayer = ""
        self.goingToStep = False
        self.needFlash = False

        self.lock = Lock()

        self.playersThread = Thread(target=self.playFiles)
        self.playersThread.start()

        self.stepperThread = Thread(target=self.playStep)
        self.stepperThread.start()

    def playFiles(self):
        # try:
        #     pdb.set_trace()
        # except:
        #     pass

        curPlayer = None
        oldPlayer = None
        while True:
            self.lock.acquire()
            needStop = False
            if self.currentStep == "<STOP>":
                needStop = True
            elif not self.currentPlayer:
                self.lock.release()
                sleep(0.01)
                continue
            elif self.currentPlayer == curPlayer:
                # print 'not changed'
                self.lock.release()
                sleep(0.01)
                continue

            oldPlayer = curPlayer
            curPlayer = self.currentPlayer
            self.currentPlayer.set_volume(1)
            # oldPlayer = curPlayer
            self.lock.release()

            print 'currentPlayer changed, start it'

            # pdb.set_trace()
            # if self.needFlash:
            #     pyopengles.play()
            if not needStop:
                if not self.isFirstVideoMovie:
                    curPlayer.play()
                else:
                    self.isFirstVideoMovie = False

            # stop previous player (finished on last iteration) after start new player for smaller gap between them
            if oldPlayer:
                oldPlayer.stop()
                if needStop:
                    self.lock.acquire()
                    if self.currentStep == "<STOP>":
                        self.currentStep = ""
                    self.lock.release()


            # waiting whane self.currentPlayer changed
            # while not curPlayer.finished:
            #     self.lock.acquire()
            #     if curPlayer != self.currentPlayer:
            #         self.lock.release()
            #         break
            #
            #     self.lock.release()
            #     sleep(0.05)
        print 'playFiles thread terminated...'

    def getMoviePathByMovieId(self, movieId):
        if movieId not in self.cfg['map']:
            return ""

        return os.path.abspath(
            os.path.join(self.movies_path, self.cfg['map'][movieId])
        )

    def getSRTPathByMovieId(self, movieId):
        if movieId not in self.cfg['subtitles']:
            return ""

        return os.path.abspath(
            os.path.join(self.movies_path, self.cfg['subtitles'][movieId])
        )

    def doStep(self, step):
        print "doStep invoked"
        # search step cfg
        if step not in self.cfg['steps'] and step != "<STOP>":
            print 'Step %s definition not found' % step
            return

        # for doing step we alwayes need to create new instance of omxplayer,
        # cause we can't change currently plaing movie in the same instance
        # of omxplayer
        self.lock.acquire()
        self.currentStep = step
        print "GOING TO STEP %s" % self.currentStep
        self.lock.release()

    def playStep(self):
        # single step can contain multiple movies
        try:
            pdb.set_trace()
        except:
            pass
        curStepFirstPlayer = None
        curStepSecondPlayer = None
        step = ""
        layNum = 0
        while True:
            self.lock.acquire()
            # print "CURRENT STEP: %s" % self.currentStep
            if self.currentStep == "<STOP>":
                step = ""
                self.lock.release()
                sleep(0.01)
                continue

            if (not self.currentStep):
                self.lock.release()
                sleep(0.01)
                continue
            elif step == self.currentStep:
                self.lock.release()
                sleep(0.01)
                continue

            step = self.currentStep

            self.lock.release()

            # playing step
            currentStepNeedStop = False
            curStepFirstPlayer = None
            curStepSecondPlayer = None

            filesInStep = len(self.cfg['steps'][step])
            for idx, curFile in enumerate(self.cfg['steps'][step]):
                if currentStepNeedStop:
                    break

                movieId = curFile['movie']
                curFileLen = -1
                if 'length' in curFile:
                    curFileLen = curFile['length']

                isLoop = False
                if 'loop' in curFile:
                    isLoop = curFile['loop']

                needFlash = False
                if 'flash' in curFile:
                    needFlash = curFile['flash']

                movieFile = self.getMoviePathByMovieId(movieId)
                srtFile = self.getSRTPathByMovieId(movieId)

                if idx == 0 and self.nextStepPlayer:
                    if step == self.stepIdForNextStepPlayer:
                        curStepFirstPlayer = self.nextStepPlayer
                    else:
                        # next steps is different from what we planning (not next - something another, may be previous)
                        self.nextStepPlayer.stop()

                    self.nextStepPlayer = None
                    self.stepIdForNextStepPlayer = ""
                elif curStepSecondPlayer:
                    curStepFirstPlayer = curStepSecondPlayer
                    curStepSecondPlayer = None

                if not curStepFirstPlayer:
                    # layNum += 1
                    curStepFirstPlayer = OMXPlayer(
                        movieFile,
                        #args='-o hdmi -p' + ("" if not isLoop else ' --loop'),
                        args='-o ' + audio_output + ' -p --layer '+str(layNum) + ((' --subtitles ' + srtFile + subtitles_font_arg) if srtFile else ''),
                        start_playback=not self.isFirstVideoMovie
                    )
                    curStepFirstPlayer.set_volume(1)

                self.needFlash = needFlash

                self.lock.acquire()
                self.currentPlayer = curStepFirstPlayer
                self.lock.release()

                # if self.isFirstVideoMovie:
                #     self.isFirstVideoMovie = False

                # nextFilePrepared = False
                # prepare the next video file with own omxplayer for smallest
                # gap between them
                # sleep(0.4)
                nextFileInStep = None
                # needPauseForInitNextPlayer = False
                if idx < filesInStep-1:
                    nextFileInStep = self.cfg['steps'][step][idx+1]
                    nextMovieFile = self.getMoviePathByMovieId(nextFileInStep['movie'])
                    nextSrtFile = self.getSRTPathByMovieId(nextFileInStep['movie'])
                    if nextFileInStep:
                        sleep(1)
                        layNum += 1
                        curStepSecondPlayer = OMXPlayer(
                            nextMovieFile,
                            #args='-o hdmi' + ("" if not nextFileInStep['loop'] else ' --loop'),
                            args='-o ' + audio_output + ' -p --layer ' + str(layNum) + ((' --subtitles ' + nextSrtFile + subtitles_font_arg) if nextSrtFile else ''),
                            start_playback=False,
                            hidemode=False
                        )

                        # pause for audio up
                        # self.togglePause()
                        # sleep(0.06)
                        # self.togglePause()

                        #self.currentPlayer.increase_volume()
                        #sleep(0.07)
                        #self.currentPlayer.decrease_volume()

                        #curStepSecondPlayer.set_volume(0)
                        #layNum += 1
                        # needPauseForInitNextPlayer = True

                    print 'Next file in step PREPARED'
                elif idx == (filesInStep-1):
                    # prepare first movie in next step
                    nextStep = self.getNextStepId(step)
                    if nextStep:
                        nextFileInStep = self.cfg['steps'][nextStep][0]
                        nextMovieFile = self.getMoviePathByMovieId(nextFileInStep['movie'])
                        nextSrtFile = self.getSRTPathByMovieId(nextFileInStep['movie'])

                        if nextFileInStep:
                            sleep(1)
                            # self.nextStepPlayer = OMXPlayer(
                            layNum += 1
                            self.nextStepPlayer = OMXPlayer(
                                nextMovieFile,
                                #args='-o hdmi' + ("" if not nextFileInStep['loop'] else ' --loop'),
                                args='-o ' + audio_output + ' -p --layer '+str(layNum) + ((' --subtitles ' + nextSrtFile + subtitles_font_arg) if nextSrtFile else ''),
                                start_playback=False,
                                hidemode=False
                            )

                            # self.togglePause()
                            # sleep(0.06)
                            # self.togglePause()

                            #self.currentPlayer.increase_volume()
                            #sleep(0.07)
                            #self.currentPlayer.decrease_volume()

                            #self.nextStepPlayer.set_volume(0)
                            #layNum += 1
                            self.stepIdForNextStepPlayer = nextStep
                            # needPauseForInitNextPlayer = True

                        print 'First file in next step PREPARED'

                    # while self.currentPlayer and not self.currentPlayer.finished:
                # if needPauseForInitNextPlayer:
                #     sleep(0.1)

                isRewinding = False
                while True:
                    # check current step may was changed
                    self.lock.acquire()
                    # print "self.currentStep != step: %s" % (self.currentStep != step)
                    if self.currentStep != step:
                        currentStepNeedStop = True
                        if curStepSecondPlayer:
                            curStepSecondPlayer.stop()
                            curStepSecondPlayer = None
                            # layNum -= 1

                        self.lock.release()
                        break
                    else:
                        if curFileLen > 0 and self.currentPlayer.position >= curFileLen and not isRewinding:
                            if (isLoop):
                                self.currentPlayer.rewind()
                                isRewinding = True
                                print 'SEEK playing by manual'
                                # sleep(0.2)
                            else:
                                self.lock.release()
                                print 'STOP playing by manual'
                                # layNum -= 1
                                break
                        elif self.currentPlayer and self.currentPlayer.finished:
                            self.lock.release()
                            # layNum -= 1
                            break

                        if self.currentPlayer.position < curFileLen:
                            # just rewinded
                            isRewinding = False

                    self.lock.release()

                    # if self.currentPlayer._paused:
                    #     print "PAUSED"

                    # sleep(0.01)

            # self.lock.acquire()
            # if self.currentStep == step:
            #     print "CLEAR STEP ON STEP: %s" % step
            #     self.currentStep = ""
            # self.lock.release()

            # self.currentStep = None

    def pause(self, isPause):
        if not self.currentPlayer:
            return

        if isPause:
            self.currentPlayer.pause()
        else:
            self.currentPlayer.play()

        pass

    def togglePause(self):
        if not self.currentPlayer:
            return

        self.currentPlayer.toggle_pause()

    def getNextStepId(self, currentStep=""):
        if not currentStep:
            currentStep = self.currentStep

        nextStepFound = False
        nextStep = ""
        if not currentStep:
            nextStep = self.cfg['steps_order'][0]
        else:
            for step in self.cfg['steps_order']:
                if nextStepFound:
                    nextStep = step
                    break

                if step == currentStep:
                    nextStepFound = True

        return nextStep

    def next(self):
        nextStep = self.getNextStepId()

        if not nextStep:
            return

        # self.doStep(nextStep, False if self.getNextStepId(nextStep) else True)
        self.doStep(nextStep)

    def prev(self):
        prevStep = ""

        if not self.currentStep:
            prevStep = self.cfg['steps_order'][0]
        else:
            tmpStep = ""
            for step in self.cfg['steps_order']:
                if step == self.currentStep:
                    prevStep = tmpStep
                    break

                tmpStep = step

        if not prevStep:
            prevStep = self.cfg['steps_order'][0]
            #return

        # if self.currentStepNextPlayer:
        #     self.currentStepNextPlayer.stop()
        #     self.currentStepNextPlayer = None
        if self.nextStepPlayer:
            self.nextStepPlayer.stop()
            self.nextStepPlayer = None

        self.doStep(prevStep)

    def gotoStep(self, step):
        if self.goingToStep:
          return

        self.goingToStep = True

        if self.isFirstVideoMovie2:
            self.isFirstVideoMovie2 = False

        self.doStep("<STOP>")

        while True:
            self.lock.acquire()
            curStep = self.currentStep
            self.lock.release()

            if not curStep:
                break

            sleep(0.01)

        self.doStep(step)

        self.goingToStep = False


    def stop(self):
        self.doStep("<STOP>")


def doCmd(cmd):
    vs = VideoStepper.Instance()

    if len(cmd) == 0:
        return

    if cmd[0] == '>':
        vs.doStep(cmd[1:])
    elif cmd == 'TOGGLE_PAUSE':
        vs.togglePause()
    elif cmd == 'PAUSE':
        vs.pause(True)
    elif cmd == 'RESUME':
        vs.pause(False)
    elif cmd == 'STOP':
        vs.stop()
    elif cmd == 'NEXT':
        if vs.isFirstVideoMovie2:
            vs.isFirstVideoMovie2 = False
            vs.togglePause()
            return

        vs.next()
    elif cmd == 'PREV':
        vs.prev()
    elif cmd == 'FIRE':
        vs.needFlash = True
    elif cmd == 'START':
        # we need it for VideoStepper first instantation
        pass


def gpio_event(channel):
    vs = VideoStepper.Instance()

    if channel == 25:
        vs.stop()
        return

    vs.gotoStep(vs.gpio[channel])


def main():
    vs = VideoStepper.Instance()

    # opening serial port
    # PARITY_NONE, PARITY_EVEN, PARITY_ODD, PARITY_MARK, PARITY_SPACE = 'N', 'E', 'O', 'M', 'S'
    # STOPBITS_ONE, STOPBITS_ONE_POINT_FIVE, STOPBITS_TWO = (1, 1.5, 2)
    # FIVEBITS, SIXBITS, SEVENBITS, EIGHTBITS = (5, 6, 7, 8)
    serialLine = serial.Serial(ttydev, vs.s_baudrate, vs.s_bytesize, vs.s_parity, vs.s_stopbits, timeout=0.1)
    sio = io.TextIOWrapper(io.BufferedRWPair(serialLine, serialLine))


    vs.isFirstVideoMovie = True
    doCmd('NEXT')

    vs.isFirstVideoMovie2 = True

    while True:
        try:
            if vs.needFlash:
                pyopengles.play()
                vs.needFlash = False
            cmd = sio.readline()
        except:
            pass
        else:
            if (cmd):
                doCmd(cmd.strip())

    VideoStepper.Instance().stopStep()

#with dctx:
main()
