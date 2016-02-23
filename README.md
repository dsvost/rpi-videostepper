#rpi-videostepper

This is a video stepper for RaspberryPi.

The main purpose of rpi-videostepper is show sequence of video files in a seamless manner by specific scenario that you can define in config file.

It can be controlled by RaspberryPi UART using simple ASCII protocol and GPIO.

The main concept of it is a step. Step can include one or more video files that will be played in sequence. Steps will be also played in defined sequence step by step. The last video file in every step can be "looped". Transition from such looped video to the next step is performed by external event - NEXT command by UART or defined GPIO.
So, all this provides exellent functionality for entertainment industry.
With rpi-videostepper you can create something like video game.

#Dependencies


For better understanding what is it let's go to investigate some config file example.

```
{
    "general": {
        "movies_path": "/opt/video-loops",
        "baudrate": 9600,
        "bytesize": 8,
        "parity": 'N',
        "stopbits": 1
    },
    "map": {
        "A0": "./v_1.mp4",
        "A1": "./v_2.mp4",
        "B0": "./v_3.mp4",
	"B1": "./v_4.mp4",
    },
    "subtitles": {
	"A0": "./v_1.srt"
    },
    "gpio": {
        "0": "A"
    },
    "steps": {
        "A": [
            {
                "movie": "A0",
                "loop": false,
                "length": 45.5
            },
            {
                "movie": "A1",
                "loop": false,
                "length": 43.02
            }
        ],
        "B": [
            {
                "movie": "B0",
                "loop": false,
                "length": 16.02,
		"flash": true
            },
      	    {
                "movie": "B1",
                "loop": true,
                "length": 46.36
            }
        ]
    },
    "steps_order": ["A","B"]
}
```
