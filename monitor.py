from operator import attrgetter

from ryu.app import simple_switch_13
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.lib import hub

import json

class SimpleMonitor13(simple_switch_13.SimpleSwitch13):

    def __init__(self, *args, **kwargs):
        super(SimpleMonitor13, self).__init__(*args, **kwargs)
        self.datapaths = {}
        self.monitor_thread = hub.spawn(self._monitor)

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

        with open(f"monitor.{ev.msg.datapath.id}.json", "w") as jsonf:
            elem_list = []
            for stat in sorted(
                    [flow for flow in body if flow.priority == 1],
                    key=lambda flow: (flow.match["in_port"], flow.match["eth_dst"])
                    ):
                elem = {
                    "datapath_id": ev.msg.datapath.id,
                    "port_src": stat.match["in_port"],
                    "eth_src": stat.match["eth_src"],
                    "port_dst": stat.instructions[0].actions[0].port,
                    "eth_dst": stat.match["eth_dst"],
                    "packets_count": stat.packet_count,
                    "packets_bytes": stat.byte_count,
                    }
                elem_list.append(elem)
            
            jsonf.write(json.dumps(elem_list))

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        body = ev.msg.body

        with open(f"monitor_ports.{ev.msg.datapath.id}.json", "w") as jsonf:
            elem_list = []
            
            for stat in sorted(body, key=attrgetter('port_no')):
                elem = {
                        "datapath_id": ev.msg.datapath.id,
                        "port_no": stat.port_no,
                        "rx_packets": stat.rx_packets,
                        "rx_bytes": stat.rx_bytes,
                        "rx_errors": stat.rx_errors,
                        "tx_packets": stat.tx_packets,
                        "tx_bytes": stat.tx_bytes,
                        "tx_errors": stat.tx_errors,
                        }
                elem_list.append(elem)
            jsonf.write(json.dumps(elem_list))

