# Grupo 3:
# Divino Junio Batista Lopes
# Luthiery Costa Cavalcante
# Vinicius Toshiyuki Menezes Sugimoto

import statistics
import time
from player.parser import parse_mpd
from r2a.ir2a import IR2A



class R2APANDA(IR2A):  # {{{1
    """Implementation of PANDA (Probe AND Adapt) algorithm. {{{

        This implementation is based on the work Probe and Adapt: Rate
        Adaptation for HTTP Video Streaming At Scale (Zhi Li et. al, 2014)
        This implementation does not control segment requests scheduling
        as proposed by PANDA.

        This class is suposed to work as follows:
        1. Receives a xml request to be sent to DASH server from upper layer
        2. Handles the request and sends it to lower layer
        3. Receives a xml response from DASH server from lower layer
        4. Handles the response (parse) and sends it to upper layer
        5. Receives a video segment request to be sent to DASH server from
            upper layer
        6. Handles the request (decide quality) and sends it to lower layer
        7. Receives a video segment response from DASH server from lower layer
        8. Handles the response (measure request time) and sends it to upper
            layer
        9. Go to step (5.)
    }}}"""
    # Video segment duration (τ)
    seg_duration = 1

    def __init__(self, id, probe_inc=50000, probe_conv=1.9):  # {{{2
        """Init for R2APANDA class. {{{

        @param probe_inc Probing additive increase bitrate (ω)
        @param probe_conv Probing convergence rate (κ)
        }}}"""
        IR2A.__init__(self, id)

        self.probe_inc = probe_inc  # (ω)
        self.probe_conv = probe_conv  # (κ)

        self.request_time = None  # Last request timestamp
        self.interreq_time = []  # Actual time between requests (Τ)
        self.target_interreq_time = [0]
        self.target_bandshare = []  # Target average data rate (x̂)
        self.smooth_bandshare = []  # Smoothed version of x̂ (ŷ)
        self.throughputs = []  # TCP throughput measured (x̃)

        self.buffer_duration = [0]
        self.buffer_convergence = 0.5
        self.buffer_min = self.whiteboard.get_max_buffer_size() * 0.25
        self.buffer_min *= R2APANDA.seg_duration

        self.parsed_mpd = None
        self.qi = []  # List of available bitrates (quality) from manifest
        self.q = []  # List of chosen bitrates (r)
    # 2}}}

    def handle_xml_request(self, msg):  # {{{2
        """Handle a xml manifest request to DASH server. {{{

            @param msg Message to be sent
        }}}"""

        # Start high perfomance timer
        self.request_time = time.perf_counter()
        self.send_down(msg)
    # 2}}}

    def handle_xml_response(self, msg):  # {{{2
        """Handle a xml manifest request response from DASH server. {{{

            @param msg Message received
        }}}"""
        # Get qi list (R)
        self.parsed_mpd = parse_mpd(msg.get_payload())
        R2APANDA.seg_duration = int(
                self.parsed_mpd.get_segment_template()["duration"]
                )
        R2APANDA.seg_duration /= int(
                self.parsed_mpd.get_segment_template()["timescale"]
                )
        self.whiteboard.add_max_buffer_size(
            self.whiteboard.get_max_buffer_size() * R2APANDA.seg_duration
        )
        self.qi = self.parsed_mpd.get_qi()

        # Get time delta (request response time)
        t = time.perf_counter() - self.request_time
        self.interreq_time.append(t)

        # Compute throughput by x̃ := (r * τ) / t
        self.throughputs.append(
                msg.get_bit_length() / t
                )

        self.target_bandshare.insert(0, self.throughputs[-1])
        # Compute target bandshare
        self.target_bandshare.append(self._get_target_bandshare())
        # Remove stub initial bandshare
        self.target_bandshare.pop(0)

        self.send_up(msg)
    # 2}}}

    def handle_segment_size_request(self, msg):  # {{{2
        """Handle a video segment request to DASH server. {{{

            @param msg Message to be sent
        }}}"""
        # Start high perfomance timer
        self.request_time = time.perf_counter()

        # 2) Smooth out `self.target_bandshare[-1]` to produce filtered
        # version `self.smooth_bandshare[-1]` by
        # ŷ[n] = S({x̂[m] : m ≤ n})
        self.smooth_bandshare.append(
                self.smoothen(self.target_bandshare)
                )

        # 3) Quantize `self.smooth_bandshare[-1]` to the discrete video
        # bitrate `self.q[-1]` by
        # r[n] = Q(ŷ[n]; ...) (the elipsis mean optional arguments may be used,
        # as explained in "... Q(·) can also incorporate side information,
        # including the past fetched bitrates {r[m] : m < n} and the buffer
        # history {B[m] : m < n}.")
        self.q.append(self.quantize(self.smooth_bandshare))

        # 4) Schedule the next download request depending on the buffer
        # fullnes:
        # t̂[n] = (r[n] * τ) / ŷ[n] + β·(B[n-1]-Bmin)
        target_time = self.q[-1] * R2APANDA.seg_duration
        target_time /= self.smooth_bandshare[-1]  # 0 <= target_time < 1
        # < 0 se menos que buffer_min
        buffer_delta = self.buffer_duration[-1] - self.buffer_min
        target_time += self.buffer_convergence * buffer_delta

        self.target_interreq_time.append(target_time)

        # Set quality
        msg.add_quality_id(self.q[-1])
        self.send_down(msg)
    # 2}}}

    def handle_segment_size_response(self, msg):  # {{{2
        """Handle a segment request response from DASH server. {{{

            @param msg Message received
        }}}"""
        # Get time delta (request response time)
        t = time.perf_counter() - self.request_time

        # 1) Estimate the bandwidth share `self.target_bandshare[-1]` by
        self.buffer_duration.append(max(
            0,
            self.buffer_duration[-1] +
            R2APANDA.seg_duration - self.target_interreq_time[-1]
        ))  # Quantos segundos de vídeo tem armazenado no buffer
        self.throughputs.append(
                msg.get_bit_length() / t
                )
        self.interreq_time.append(t)
        self.target_bandshare.append(self._get_target_bandshare())

        self.send_up(msg)
    # 2}}}

    def initialize(self):  # {{{2
        pass
    # 2}}}

    def finalization(self):  # {{{2
        pass
    # 2}}}

    def _get_target_bandshare(self):  # {{{2
        """PANDA algorithm step 1). {{{

            Estimate the bandwidth share `self.target_bandshare[-1]` (x̂[n]) by

            x̂[n] - x̂[n-1]   κ·(ω - max(0, x̂[n-1]-x̃[n-1]+ω))
            ───────────── = ───────────────────────────────
                T[n-1]                     1

                ↓↓↓

            x̂[n] = (κ·(ω - max(0, x̂[n-1]-x̃[n-1]+ω)))·T[n-1]+x̂[n-1]
        }}}"""
        w = self.probe_inc
        k = self.probe_conv

        ret = w - max(0, self.target_bandshare[-1] - self.throughputs[-1] + w)
        ret *= k
        ret *= max(self.interreq_time[-1], self.target_interreq_time[-1])
        ret += self.target_bandshare[-1]

        return max(ret, self.qi[0])  # self.throughputs[-1]
    # 2}}}

    def smoothen(self, target_bandshare):  # {{{2
        """PANDA algorithm step 2). {{{

            As explained in the paper, for the smoothing function, "various
            filtering methods are possible, such as sliding-window moving
            average, exponential weighted moving average (EWMA) or harmonic
            mean."
            This implements a harmonic mean method.
        }}}"""
        # TODO: implement other methods?
        return statistics.harmonic_mean(target_bandshare[-5:])
    # 2}}}

    def quantize(self, smooth_bandshare):  # {{{2
        """PANDA algorithm step 3). {{{

            Discretize smooth bandshare.
            Uses the average from the current and previous smooth bandshare.
            Finds the greatest quality that is less than the computed average.
        }}}"""
        rate = self.qi[0]
        for q in self.qi:
            if q > statistics.mean(smooth_bandshare[-5:]):
                break
            rate = q
        ratio = self.buffer_duration[-1] / self.buffer_min
        rate = self.qi[min(self.qi.index(rate) + int(ratio), len(self.qi) - 1)]
        return rate
    # 2}}}
# 1}}}
