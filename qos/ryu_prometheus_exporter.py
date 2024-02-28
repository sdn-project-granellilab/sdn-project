import array
from operator import attrgetter
from ryu.lib.packet import packet

from ryu.app import simple_switch_13
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.lib import hub

class SimpleMonitor13(simple_switch_13.SimpleSwitch13):

    def __init__(self, *args, **kwargs):
        super(SimpleMonitor13, self).__init__(*args, **kwargs)
        self.datapaths = {}
        self.packet_count = Gauge('packet_count', 'Number of packets', ['port'])
        self.byte_count = Gauge('byte_count', 'Number of bytes', ['port'])
        self.monitor_thread = hub.spawn(self._monitor)
        start_http_server(9091)  # Start Prometheus metrics server

    @set_ev_cls(ofp_event.EventOFPStateChange,
                [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.datapaths:
                self.logger.debug('register datapath: %016x', datapath.id)
                self.datapaths[datapath.id] = datapath
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                self.logger.debug('unregister datapath: %016x', datapath.id)
                del self.datapaths[datapath.id]

    def _monitor(self):
        while True:
            for dp in self.datapaths.values():
                self._request_stats(dp)
            hub.sleep(10)

    def _request_stats(self, datapath):
        self.logger.debug('send stats request: %016x', datapath.id)
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)

        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_reply_handler(self, ev):
        body = ev.msg.body

        for stat in sorted([flow for flow in body if flow.priority == 1],
                           key=lambda flow: (flow.match['in_port'],
                                             flow.match['eth_dst'])):
            self.packet_count.labels(port=str(stat.port_no)).inc(stat.packet_count)
            self.byte_count.labels(port=str(stat.port_no)).inc(stat.byte_count)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        body = ev.msg.body
        for stat in sorted(body):
            self.packet_count.labels(port=str(stat.port_no)).inc(stat.rx_packets + stat.tx_packets)
            self.byte_count.labels(port=str(stat.port_no)).inc(stat.rx_bytes + stat.tx_bytes)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        port = msg.match['in_port']
        pkt = packet.Packet(array.array('B', ev.msg.data))
        #self.logger.info("packet-in %s" % (pkt,))
        print ("\n\nPACKET:")
        for p in pkt.protocols:
            print(p)
            #if p.protocol_name == 'tcp':
            #     print("TCP: ", p, "Port: ", p.dst_port)
            # if p.protocol_name == 'udp':
            #     print("UDP: ", p, "Port: ", p.dst_port)