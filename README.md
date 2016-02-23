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

#Configuration

For better understanding what is it let's go to investigate some config file example.

```
{
    "general": {
        "movies_path": "/opt/video-loops",	// path to video files
        "baudrate": 9600,			// UART params
        "bytesize": 8,					
        "parity": 'N',
        "stopbits": 1
    },
    "map": {			// mappings file names to ID's (in step definion we just use id instead of file names)
        "A0": "./v_1.mp4",	// A0 - id, ./v_1.mp4 - video file in general.movies_path
        "A1": "./v_2.mp4",
        "B0": "./v_3.mp4",
        "B1": "./v_4.mp4",
    },
    "subtitles": {
    	"A0": "./v_1.srt"	// subtitles file in general.movies_path for A0 video file (v_1.mp4 in this example)
    },
    "gpio": [
    	{
    	  "gpio": "4",		// connect GPIO04 to the step B0 (file v_3.mp4 will be played on active level of GPIO04)
    	  "step": "B0"
        }
    ],
    "steps": {			// steps definitions
        "A": [			// step ID
            {
                "movie": "A0",	// first video file in step (v_1.mp4 in this example)
                "loop": false,	// not loop this video file, just play and go to the next file in step 
                		// or first file in next step
                "length": 45.5	// the length of the video file (it must be smaller than actual file length), 
                		// we need to define it :( for seamless looping
            },
            {
                "movie": "A1",
                "loop": true,	// this video file will be looped, for switch to the next file (first in next step),
                		// external event needed (NEXT command on UART or some GPIO)
                "length": 43.02
            }
        ],
        "B": [
            {
                "movie": "B0",
                "loop": false,
                "length": 16.02,
		"flash": true	// it is for what pyopengles used, some nice flash at start of playing this file,
				// shaders of it i wrote by myself and it is in pyopengles.py
            },
      	    {
                "movie": "B1",
                "loop": false,
                "length": 46.36
            }
        ]
    },
    "steps_order": ["A","B"]	// order of steps (used by NEXT command on UART)
}
```
