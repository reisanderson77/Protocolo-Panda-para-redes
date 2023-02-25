# -*- coding: utf-8 -*-
"""

@description: PyDash Project

An implementation example of a Dynamic Segment Size Selection R2A Algorithm.

The quality list is obtained with the parameter of handle_xml_response()
method and the choice is made inside of handle_segment_size_request(),
before sending the message down.

In this algorithm the quality choice is based on Dynamic Segment Size Selection,
but selecting the Quality Index instead of.
"""


import random
import time
from matplotlib import pyplot as plt
from player.parser import *
from r2a.ir2a import IR2A


class R2ADynamic(IR2A):

    def __init__(self, id):
        IR2A.__init__(self, id)
        self.parsed_mpd = ''
        self.qi = []

        self.throughputs = []        # Array containing the throughputs available across the execution
        self.request_time = None    # Last request timestamp
    
    def handle_xml_request(self, msg):
        self.request_time = time.perf_counter() # Start timer to estimate the throughput in link
        self.send_down(msg)

    def handle_xml_response(self, msg):
        # getting qi list
        self.parsed_mpd = parse_mpd(msg.get_payload())
        self.qi = self.parsed_mpd.get_qi()
        self.throughputs.append(msg.get_bit_length()/(time.perf_counter() - self.request_time))

        self.send_up(msg)

    def handle_segment_size_request(self, msg):
        # update the throughputs array to differents approachs
        
        self.updateThroughputsArrray("SMOOTHED") 

        # calculating the mean of throughput array (1)

        tavg = sum(self.throughputs) / len(self.throughputs)

        # calculating the variance of throughput array (2)
        
        variance = 0
        for i in range(len(self.throughputs)):
            variance += i * abs(self.throughputs[i] - tavg)
        variance /= len(self.throughputs)

        # calculating the p (3)

        p = tavg / (tavg + variance)

        # calculating the T (4)

        T = (1 - p) * max(self.throughputs)

        # calculating the theta (5)

        theta = p * min(self.throughputs)

        # getting the new QI (6)
        low = imin = float('inf')
        for i in range(len(self.qi)):
            if self.qi[i] - T + theta < low:
                low = T + theta - self.qi[i]
                imin = i

        # save the request timestamp
        self.request_time = time.perf_counter()

        #list = self.whiteboard.get_playback_history()
        #if len(list) > 0:
        #    print(f'>>>>>>>>>>> {list[0][1]}')

        # Hora de definir qual qualidade será escolhida
        msg.add_quality_id(self.qi[imin])

        self.send_down(msg)

    def handle_segment_size_response(self, msg):
        t = (time.perf_counter() - self.request_time)
        currentthroughput = msg.get_bit_length()/t
        self.throughputs.append(currentthroughput)

        self.send_up(msg)

    def initialize(self):
        pass

    def finalization(self):
        pass

    def updateThroughputsArrray(self, mode):
        """
        This function accepts the SMOOTHED where the algoritm uses
        all throughputs trying keep the quality more stable, LAST-SEGMENT
        will use just the last throughput to calculate the actual bitrate
        and a string with a integer number M that will be used as the last
        M throughputs in the array to calculate the actual bitrate. Using
        little throughputs helps to correct a instantaneous slow down in
        the throughput, but may causes big variation of the quality. Otherwise,
        using bigger throughput array fix the big variation of the quality
        issue, but any fluctuation on throughput is carried for a bigger time
        """
        if mode == 'LAST-SEGMENT' and len(self.throughputs) > 2:
            self.throughputs = self.throughputs[1:]
        elif mode.isdigit():
            if len(self.throughputs) > int(mode):
                self.throughputs = self.throughputs[1:]
        elif mode == "SMOOTHED":
            pass