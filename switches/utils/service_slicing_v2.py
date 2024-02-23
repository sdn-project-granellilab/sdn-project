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
from ryu.lib.xflow import netflow

from ryu.lib.ovs.bridge import OVSBridge
import os, socket

VFLOW_COLLECTOR_IP   = "127.0.0.1"
VFLOW_COLLECTOR_PORT = "9996"

class TrafficSlicing(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(TrafficSlicing, self).__init__(*args, **kwargs)

        self.switches_macs = []
        # outport = self.mac_to_port[dpid][mac_address]
        self.mac_to_port = {
            # 1: {"00:00:00:00:00:01": 3, "00:00:00:00:00:02": 4},
            # 4: {"00:00:00:00:00:03": 3, "00:00:00:00:00:04": 4},
        }
        self.slice_TCport = 9999

        # outport = self.slice_ports[dpid][slicenumber]
        self.slice_ports = {1: {1: 1, 2: 2}, 3: {1: 1, 2: 2}}
        self.end_swtiches = [1, 3]
        #runnato una volta sola per sempre, a meno che non si pulisca la tabella manager di ovsdb
        #os.system("ovs-vsctl set-manager 'ptcp:6640'")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # install the table-miss flow entry.
        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)
        ]
        self.add_flow(datapath, 0, match, actions)

        dpid=datapath.id
        bridge=OVSBridge(self.CONF,dpid,'tcp:127.0.0.1:6640')
        bridge.br_name=f'r{dpid}'
        ports= bridge.get_port_name_list()
        bw=1000 if dpid==3 else 10000
        for port in ports:
            result=bridge.set_qos(port,max_rate=str(bw),
                           queues=[
                               {'max-rate':str(int(bw*0.75))},
                               {'max-rate':str(int(bw*0.25))}
                           ])
            #result è una lista di righe del db: oggetti ovs.db.idl.Row
            for r in result:
                print(f'{port} : {r.uuid}')#si ottengono gli uuid di QoS, queue 0, queue 1 per ogni porta
            
        

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

        # msd.data => elementi del pacchetto in formato binario
        
        # print(f"Packet: {msg.data}")
        #vflow = netflow.NetFlowV5Flow.parser(msg.data)
        #print(vflow)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(msg.data, (VFLOW_COLLECTOR_IP, VFLOW_COLLECTOR_PORT))

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            # ignore lldp packet
            return
        dst = eth.dst
        src = eth.src

        dpid = datapath.id
        # learn a mac address to avoid FLOOD next time.
        if not src in self.switches_macs and dpid in self.end_swtiches:
            check = True
            for key in self.mac_to_port:
                if src in self.mac_to_port[key]:
                    print("SRC IS: ", src)
                    check = False
                    break
            if check:
                self.mac_to_port.setdefault(dpid, {})
                self.mac_to_port[dpid][src] = in_port
        # print("MACTOPORT: ", self.mac_to_port)
        # print ("PACKET\n", "DPID:", dpid, "SRC:", src, "DST:", dst, "PROTO:")

        if dpid in self.mac_to_port:
            if dst in self.mac_to_port[dpid]:
                out_port = self.mac_to_port[dpid][dst]
                actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]
                match = datapath.ofproto_parser.OFPMatch(eth_dst=dst)
                self.add_flow(datapath, 1, match, actions)
                self._send_package(msg, datapath, in_port, actions)

            elif (pkt.get_protocol(udp.udp) and pkt.get_protocol(udp.udp).dst_port == self.slice_TCport):
                slice_number = 1
                out_port = self.slice_ports[dpid][slice_number]
                match = datapath.ofproto_parser.OFPMatch(
                    in_port=in_port,
                    eth_dst=dst,
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=0x11,  # udp
                    udp_dst=self.slice_TCport,
                )
                ##########################################
                #   setta la queue e gli dice di buttarlo dalla porta giusta, presunto slice 1 = poca banda
                ##########################################
                actions = [datapath.ofproto_parser.OFPActionSetQueue(1),datapath.ofproto_parser.OFPActionOutput(out_port)]
                self.add_flow(datapath, 2, match, actions)
                self._send_package(msg, datapath, in_port, actions)

            elif (pkt.get_protocol(udp.udp) and pkt.get_protocol(udp.udp).dst_port != self.slice_TCport):
                slice_number = 2
                out_port = self.slice_ports[dpid][slice_number]
                match = datapath.ofproto_parser.OFPMatch(
                    in_port=in_port,
                    eth_dst=dst,
                    eth_src=src,
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=0x11,  # udp
                    udp_dst=pkt.get_protocol(udp.udp).dst_port,
                )
                actions = [datapath.ofproto_parser.OFPActionSetQueue(0),datapath.ofproto_parser.OFPActionOutput(out_port)]
                self.add_flow(datapath, 1, match, actions)
                self._send_package(msg, datapath, in_port, actions)

            elif pkt.get_protocol(tcp.tcp):
                slice_number = 2
                out_port = self.slice_ports[dpid][slice_number]
                match = datapath.ofproto_parser.OFPMatch(
                    in_port=in_port,
                    eth_dst=dst,
                    eth_src=src,
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=0x06,  # tcp
                )
                actions = [datapath.ofproto_parser.OFPActionSetQueue(0),datapath.ofproto_parser.OFPActionOutput(out_port)]
                self.add_flow(datapath, 1, match, actions)
                self._send_package(msg, datapath, in_port, actions)

            elif pkt.get_protocol(icmp.icmp):
                slice_number = 2
                out_port = self.slice_ports[dpid][slice_number]
                match = datapath.ofproto_parser.OFPMatch(
                    in_port=in_port,
                    eth_dst=dst,
                    eth_src=src,
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=0x01,  # icmp
                )
                actions = [datapath.ofproto_parser.OFPActionSetQueue(1),datapath.ofproto_parser.OFPActionOutput(out_port)]
                self.add_flow(datapath, 1, match, actions)
                self._send_package(msg, datapath, in_port, actions)

        #################
        #       bisogna ridirigere il traffico anche nei router intermedi
        #################

        elif dpid not in self.end_swtiches:
            out_port = ofproto.OFPP_FLOOD
            actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]
            match = datapath.ofproto_parser.OFPMatch(in_port=in_port)
            self.add_flow(datapath, 1, match, actions)
            self._send_package(msg, datapath, in_port, actions)

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, CONFIG_DISPATCHER)
    def port_desc_stats_reply_handler(self, ev):
        ports = []
        for p in ev.msg.body:
            self.switches_macs.append(p.hw_addr)
            ports.append('port_no=%d hw_addr=%s name=%s' %
                         (p.port_no, p.hw_addr, p.name))
        self.logger.info('OFPPortDescStatsReply received: %s', self.switches_macs)
        #print("len is:", len(self.switches_macs))