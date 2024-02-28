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
from ryu.controller import event
from ryu.lib.ovs.bridge import OVSBridge
import ryu.lib.hub as hub
from utils import vsctlutil
from utils import kafkaconsumer
from utils import pid
import time
import json
from utils import queue

from addict import Dict

class TrafficSlicing(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    BW = 3*1000000

    def __init__(self, *args, **kwargs):
        super(TrafficSlicing, self).__init__(*args, **kwargs)

        # outport = self.mac_to_port[dpid][mac_address]
        # self.mac_to_port = {
        #     1: {"00:00:00:00:00:01": 3, "00:00:00:00:00:02": 4, "00:00:00:00:00:03": 5, "00:00:00:00:00:04": 6},
        #     3: {"00:00:00:00:00:05": 3, "00:00:00:00:00:06": 4, "00:00:00:00:00:07": 5,"00:00:00:00:00:08": 6},
        # }

        # write ip as variables
        h1 = "10.0.0.1"
        h2 = "10.0.0.2"
        h3 = "10.0.0.3"
        h4 = "10.0.0.4"
        s1 = "10.0.0.5"
        s2 = "10.0.0.6"
        s3 = "10.0.0.7"
        s4 = "10.0.0.8"
        self.ip_to_port = {
            1: {h1: 3, h2: 4, h3: 5, h4: 6},
            3: {s1: 3, s2: 4, s3: 5, s4: 6},
        }
        self.slice_to_ip_pair = {
            0: [
                (h1, s1),
                (h1, s2),
                (h1, s3),
                (h1, s4),
                (h2, s1),
                (h2, s2),
                (h2, s3),
                (h2, s4),
            ],
            1: [
                (h3, s1),
                (h3, s2),
                (h3, s3),
                (h3, s4),
                (h4, s1),
                (h4, s2),
                (h4, s3),
                (h4, s4),
            ]
        }

        self.slice_TCport = 9999
        self.queue_mapping = Dict()
        self.nfgetter = kafkaconsumer.NetflowInformationRetriever()

        # outport = self.slice_ports[dpid][slicenumber]
        self.slice_ports = {1: {1: 1, 2: 2}, 3: {1: 1, 2: 2}}
        self.end_swtiches = [1, 3]
        poll = hub.spawn(self.pollingNetflow)


    
    def pollingNetflow(self):
        bw_usage = dict()
        time.sleep(10)
        while True:
            time.sleep(10)
            bw_usage_old = bw_usage
            bw_usage = self.nfgetter.bandwith_usage_per_link()
            queue_traffic=[0,0]
            for (src,dst) in bw_usage.keys():
                if (src,dst) in self.slice_to_ip_pair[0]:
                    queue_traffic[0]+=(bw_usage[(src,dst)]["bytes"])
                else:
                    queue_traffic[1]+=(bw_usage[(src,dst)]["bytes"])
                                

            for dpid in self.queue_mapping.keys():
                for port in self.queue_mapping[dpid].keys():
                    queues = []
                    for p in self.queue_mapping[dpid][port]["queues"].keys():
                        queues.insert(int(p), queue.Queue(0, self.queue_mapping[dpid][port]["queues"][p]["bandwidth"]))
                    print(self.queue_mapping[dpid][port]["link-capacity"])
                    q_bw, errs = pid.get_optimized_bw(link_cap=self.queue_mapping[dpid][port]["link-capacity"], 
                                        queues=queues, 
                                        objectives=[self.queue_mapping[dpid][port]["queues"][obj]["objective_cons"] for obj in self.queue_mapping[dpid][port]["queues"].keys()], 
                                        traffic_stats=queue_traffic, 
                                        errs=[self.queue_mapping[dpid][port]["queues"][obj]["error"] for obj in self.queue_mapping[dpid][port]["queues"].keys()], 
                                        dt=10)
                    uuid = self.queue_mapping[dpid][port]["queues"][0]["uuid"]
                    vsctlutil.set_queue(uuid, q_bw[0])
                    uuid = self.queue_mapping[dpid][port]["queues"][1]["uuid"]
                    vsctlutil.set_queue(uuid, q_bw[1])
                    self.queue_mapping[dpid][port]["queues"][0]["error"] = errs[0]
                    self.queue_mapping[dpid][port]["queues"][1]["error"] = errs[1]

                    print("New queue bandwidths: ", q_bw)
                    print("New errors: ", errs)



            
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser


        dpid=datapath.id
        bridge=OVSBridge(self.CONF,dpid,'tcp:127.0.0.1:6640')
        bridge.br_name=f'r{dpid}'
        ports= bridge.get_port_name_list()
        

        for port in ports:
            q_bws = [int(self.BW*0.75),int(self.BW*0.25)]
            uuids = vsctlutil.create_queue(port, self.BW, q_bws)

            nport = port.split("-")[0].strip("r")
            for i in range(1, len(uuids)):
                self.queue_mapping[dpid][nport]["queues"][i-1]["uuid"] = uuids[i]
                self.queue_mapping[dpid][nport]["queues"][i-1]["bandwidth"] = q_bws[i-1]
                self.queue_mapping[dpid][nport]["queues"][i-1]["error"] = 0
                self.queue_mapping[dpid][nport]["queues"][i-1]["objective_cons"] = 0.9 if i-1 == 0 else 0.6
            
            self.queue_mapping[dpid][nport]["link-capacity"] = self.BW
            
            # print(json.dumps(self.queue_mapping))
         
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
        if eth.ethertype != ether_types.ETH_TYPE_IP:
            return

        ip = pkt.get_protocol(ipv4.ipv4)
        dst = ip.dst
        src = ip.src

        dpid = datapath.id

        if dpid in self.ip_to_port:
            if dst in self.ip_to_port[dpid]:
                out_port = self.ip_to_port[dpid][dst]
                actions = [datapath.ofproto_parser.OFPActionSetQueue(0 if (src, dst) in self.slice_to_ip_pair[0] else 1),datapath.ofproto_parser.OFPActionOutput(out_port)]
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
                actions = [datapath.ofproto_parser.OFPActionSetQueue(0 if (src, dst) in self.slice_to_ip_pair[0] else 1),datapath.ofproto_parser.OFPActionOutput(out_port)]
                self.add_flow(datapath, 2, match, actions)
                self._send_package(msg, datapath, in_port, actions)

        elif dpid not in self.end_swtiches:
            out_port = ofproto.OFPP_FLOOD
            actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]
            match = datapath.ofproto_parser.OFPMatch(in_port=in_port)
            self.add_flow(datapath, 1, match, actions)
            self._send_package(msg, datapath, in_port, actions)

