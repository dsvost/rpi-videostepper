#rpi-videostepper

This is a video stepper for RaspberryPi.

The main purpose of rpi-videostepper is show sequence of video files in a seamless manner by specific scenario that you can define in config file.

It can be controlled by RaspberryPi UART using simple ASCII protocol and GPIO.

The main concept of it is a step. Step can include one or more video files that will be played in sequence. Steps will be also played in defined sequence step by step. The last video file in every step can be "looped". Transition from such looped video to the next step is performed by external event - NEXT command by UART or defined GPIO.
So, all this provides exellent functionality for entertainment industry.
With rpi-videostepper you can create something like video game.

#Dependencies

* [pyomxplayer](https://github.com/jbaiter/pyomxplayer)
* pexpect
* [pyopengles](https://github.com/peterderivaz/pyopengles)

#Limitations

Only work with analog audio output of raspberry pi, because there is some problem with HDMI in a context of that project. 

#Configuration

The "config" file should be in general.movies path.
For better understanding what is it let's go to investigate some config file example.

```
{
    "general": {
    	// path to video files
        "movies_path": "/opt/video-loops",
        // UART params
        "baudrate": 9600,
        "bytesize": 8,					
        "parity": 'N',
        "stopbits": 1
    },
    // mappings file names to ID's (in step definion we just use id instead of file names)
    "map": {
    	// A0 - id, ./v_1.mp4 - video file in general.movies_path
        "A0": "./v_1.mp4",	
        "A1": "./v_2.mp4",
        "B0": "./v_3.mp4",
        "B1": "./v_4.mp4",
    },
    "subtitles": {
    	// subtitles file in general.movies_path for A0 video file (v_1.mp4 in this example)
    	"A0": "./v_1.srt"
    },
    "gpio": [
    	{
    	  // connect GPIO04 to the step B0 (file v_3.mp4 will be played on active level of GPIO04)
    	  "gpio": "4",
    	  "step": "B0"
        }
    ],
    // steps definitions
    "steps": {
    	// step ID
        "A": [
            {
            	// first video file in step (v_1.mp4 in this example)
                "movie": "A0",
                // not loop this video file, just play and go to the next file in step 
                // or first file in next step
                "loop": false,
                // the length of the video file (it must be smaller than actual file length),
                // we need to define it :( for seamless looping
                "length": 45.5
            },
            {
                "movie": "A1",
                // this video file will be looped, for switch to the next file (first in next step),
                // external event needed (NEXT command on UART or some GPIO)
                "loop": true,
                "length": 43.02
            }
        ],
        "B": [
            {
                "movie": "B0",
                "loop": false,
                "length": 16.02,
                // it is for what pyopengles used, some nice flash at start of playing this file,
                // shaders of it in pyopengles.py
		"flash": true
            },
      	    {
                "movie": "B1",
                "loop": false,
                "length": 46.36
            }
        ]
    },
    // steps order (used by NEXT command on UART)
    "steps_order": ["A","B"]
}
```
#UART commands

* TOGGLE_PAUSE 	- toggle pause :)
* PAUSE		- pause playback
* RESUME	- resume playback
* STOP		- stop playback completly (going to the initial state to the first step)
* NEXT		- going to the next step playback (first file in next step)
* PREV		- going to the previous step (first file in previous step)
* FIRE		- show nice flash as opengl es overlay

#GPIO

* GPIO25	- equivalent to the STOP uart command
