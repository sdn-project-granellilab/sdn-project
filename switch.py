from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet, arp


class ExampleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ExampleSwitch13, self).__init__(*args, **kwargs)
        # initialize mac address table.
        self.mac_to_port = {}

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # print(f"DATAPATH: {dir(datapath)}")
        '''
        DATAPATH: ['__class__', '__delattr__', '__dict__', '__dir__', '__doc__', '__eq__', '__format__', 
        '__ge__', '__getattribute__', '__gt__', '__hash__', '__init__', '__init_subclass__', '__le__', 
        '__lt__', '__module__', '__ne__', '__new__', '__reduce__', '__reduce_ex__', '__repr__', '__setattr__', 
        '__sizeof__', '__str__', '__subclasshook__', '__weakref__', '_close_write', '_echo_request_loop', '_ports', 
        '_recv_loop', '_send_loop', '_send_q_sem', 'acknowledge_echo_reply', 'address', 'close', 'echo_request_interval',
        'flow_format', 'id', 'is_active', 'is_reserved_port', 'max_unreplied_echo_requests', 'ofp_brick', 'ofproto', 'ofproto_parser', 
        'ports', 'send', 'send_barrier', 'send_delete_all_flows', 'send_flow_del', 'send_flow_mod', 'send_msg', 
        'send_nxt_set_flow_format', 'send_packet_out', 'send_q', 'serve', 'set_state', 'set_version', 'set_xid', 'socket', 
        'state', 'supported_ofp_version', 'unreplied_echo_requests', 'xid']
        '''
        print(f"Client Hello: r{datapath.id}")
        # install the table-miss flow entry.
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # construct flow_mod message and send it.
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        
        # this datapath object contains:
        #DEFAULT METHODS => ['__class__', '__delattr__', '__dict__', '__dir__', '__doc__', '__eq__', 
        # '__format__', '__ge__', '__getattribute__', '__gt__', '__hash__', '__init__', 
        # '__init_subclass__', '__le__', '__lt__', '__module__', '__ne__', '__new__', 
        # '__reduce__', '__reduce_ex__', '__repr__', '__setattr__', '__sizeof__', '__str__',
        
        # NON DEFAULT
        # '__subclasshook__', '__weakref__', '_close_write', '_echo_request_loop', '_ports', 
        # '_recv_loop', '_send_loop', '_send_q_sem', 'acknowledge_echo_reply', 
        # 'address', 'close', 'echo_request_interval', 'flow_format', 'id', 
        # 'is_active', 'is_reserved_port', 'max_unreplied_echo_requests', 'ofp_brick', 'ofproto', 
        # 'ofproto_parser', 'ports', 'send', 'send_barrier', 'send_delete_all_flows', 'send_flow_del', 
        # 'send_flow_mod', 'send_msg', 'send_nxt_set_flow_format', 'send_packet_out', 'send_q', 'serve', 
        # 'set_state', 'set_version', 'set_xid', 'socket', 'state', 'supported_ofp_version', 'unreplied_echo_requests', 'xid']
        
        msg = ev.msg
        datapath = msg.datapath
        timestamp = ev.timestamp
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # get Datapath ID to identify OpenFlow switches.
        dpid = datapath.id
        import time
        print(f"{time.strftime('%d-%m-%Y %H:%M:%S', time.gmtime(timestamp))} Packets in: {datapath.id}")
        
        self.mac_to_port.setdefault(dpid, {})

        # analyse the received packets using the packet library.
        pkt = packet.Packet(msg.data)
        eth_pkt = pkt.get_protocol(ethernet.ethernet)
        dst = eth_pkt.dst
        src = eth_pkt.src
        #arp_pkt = pkt.get_protocol(arp.arp)
        
        for p in pkt:
            #print("#### Packets ####")
            print(p.protocol_name)
            if p.protocol_name == 'arp':
                print(f"ARP Packets: {p.src_mac} {p.src_ip} -> {p.dst_mac} {p.dst_ip}")
            if p.protocol_name == 'tcp':
                print(dir(p))

        # get the received port number from packet_in message.
        in_port = msg.match['in_port']

        self.logger.info(f"Packet in: r{dpid}, {src}:{in_port} -> {dst}")
        #self.logger.info(f"{dir(arp_pkt)}")
        #if arp_pkt is not None:
        #    self.logger.info(f"ARP in: r{dpid}, {arp_pkt.src_} -> {}")
        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = in_port

        import json
        with open("settings.json", "w") as jsonf:
            jsonf.write(json.dumps(self.mac_to_port))

        #if dpid == 1

        # if the destination mac address is already learned,
        # decide which port to output the packet, otherwise FLOOD.
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        # construct action list.
        actions = [parser.OFPActionOutput(out_port)]

        # install a flow to avoid packet_in next time.
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst)
            self.add_flow(datapath, 1, match, actions)

        # construct packet_out message and send it.
        out = parser.OFPPacketOut(datapath=datapath,
                                  buffer_id=ofproto.OFP_NO_BUFFER,
                                  in_port=in_port, actions=actions,
                                  data=msg.data)
        datapath.send_msg(out)