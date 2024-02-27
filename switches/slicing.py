from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
from ryu.lib.packet import udp
from ryu.lib.packet import tcp
from ryu.lib.packet import icmp
from ryu.lib.packet import ipv4

from ryu.lib.ovs.bridge import OVSBridge
from utils import vsctlutil
import json 

class TrafficSlicing(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(TrafficSlicing, self).__init__(*args, **kwargs)

        # outport = self.mac_to_port[dpid][mac_address]
        # self.mac_to_port = {
        #     1: {"00:00:00:00:00:01": 3, "00:00:00:00:00:02": 4, "00:00:00:00:00:03": 5, "00:00:00:00:00:04": 6},
        #     3: {"00:00:00:00:00:05": 3, "00:00:00:00:00:06": 4, "00:00:00:00:00:07": 5,"00:00:00:00:00:08": 6},
        # }
        self.mac_to_port = {
            1: {"10.0.0.1": 3, "10.0.0.2": 4, "10.0.0.3": 5, "10.0.0.4": 6},
            3: {"10.0.0.5": 3, "10.0.0.6": 4, "10.0.0.7": 5, "10.0.0.8": 6},
        }
        self.slice_TCport = 9999
        self.queue_mapping = dict()

        # outport = self.slice_ports[dpid][slicenumber]
        self.slice_ports = {1: {1: 1, 2: 2}, 3: {1: 1, 2: 2}}
        self.end_swtiches = [1, 3]

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser


        dpid=datapath.id
        bridge=OVSBridge(self.CONF,dpid,'tcp:127.0.0.1:6640')
        bridge.br_name=f'r{dpid}'
        ports= bridge.get_port_name_list()
        
        mega = 1000000

        bw=3*mega if dpid==4 else 30*mega
        for port in ports:
            result = vsctlutil.create_queue(port, bw, [int(bw*0.75),int(bw*0.25)])

            nport = port.split("-")[0].strip("r")
            #print(nport)
            for i in range(1, len(result)):
                dict1 = dict()
                dict1[str(i)] = result[i]
                dict2 = dict()
                dict2[str(nport)] = dict1

                self.queue_mapping[str(dpid)] = dict2
         
        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)
        ]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # construct flow_mod message and send it.
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath, priority=priority, match=match, instructions=inst
        )
        datapath.send_msg(mod)

    def _send_package(self, msg, datapath, in_port, actions):
        data = None
        ofproto = datapath.ofproto
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        datapath.send_msg(out)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            # ignore lldp packet
            return
        # dst = eth.dst
        # src = eth.src

        ip = pkt.get_protocol(ipv4.ipv4)
        dst = ip.dst
        src = ip.src

        dpid = datapath.id

        if dpid in self.mac_to_port:
            if dst in self.mac_to_port[dpid]:
                out_port = self.mac_to_port[dpid][dst]
                actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]
                match = datapath.ofproto_parser.OFPMatch(ipv4_dst=dst)
                self.add_flow(datapath, 1, match, actions)
                self._send_package(msg, datapath, in_port, actions)

            else:
                slice_number = 1
                out_port = self.slice_ports[dpid][slice_number]
                match = datapath.ofproto_parser.OFPMatch(
                    in_port=in_port,
                    ipv4_dst=dst,
                    eth_type=ether_types.ETH_TYPE_IP,
                )
                actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]
                self.add_flow(datapath, 2, match, actions)
                self._send_package(msg, datapath, in_port, actions)

        elif dpid not in self.end_swtiches:
            out_port = ofproto.OFPP_FLOOD
            actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]
            match = datapath.ofproto_parser.OFPMatch(in_port=in_port)
            self.add_flow(datapath, 1, match, actions)
            self._send_package(msg, datapath, in_port, actions)

