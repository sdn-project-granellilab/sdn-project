from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet

class SimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)

        self.mac_to_port = {}

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # install table-miss flow entry
        #
        # We specify NO BUFFER to max_len of the output action due to
        # OVS bug. At this moment, if we specify a lesser number, e.g.,
        # 128, OVS will send Packet-In with invalid buffer_id and
        # truncated packet data. In that case, we cannot output packets
        # correctly.  The bug has been fixed in OVS v2.1.0.
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=0,
                                match=match, instructions=inst)
        datapath.send_msg(mod)

    def add_flow(self, datapath, dst, in_port, out_port):
        print("ADDING A FLOW")
        ofproto = datapath.ofproto
        ofp_parser = datapath.ofproto_parser

        # to add a flow we have to define some match criteria
        match = ofp_parser.OFPMatch(
            in_port=in_port, # we match the input port
            eth_dst=dst) # and the destination MAC address

        # we also need to define the desired action
        actions = [ofp_parser.OFPActionOutput(out_port)]
        inst = [ofp_parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        # now we build a flow table entry
        flow = ofp_parser.OFPFlowMod(
            datapath=datapath, # assign datapath
            command=ofproto.OFPFC_ADD, # we want to add a new flow
            match=match, # define match criteria for the flow table entry
            cookie=0, # can be used to identify the flow
            idle_timeout=0, hard_timeout=0, # the flow entry never times out
            priority=ofproto.OFP_DEFAULT_PRIORITY,
            flags=0, # here we could decide to handle flow removal messages
            instructions=inst)

        # send it to the switch
        datapath.send_msg(flow)

        self.logger.debug('Flow added for {} ports {}->{}'.format(dst, in_port, out_port))


    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        print(f"MESSAGE: {msg}")
        dpid = datapath.id

        # if we have not seen this switch yet then we add it to our memory
        # with an empty port mapping
        self.mac_to_port.setdefault(dpid, {})

        # we need to disect the message payload
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        # from the ethernet frame we can extract the MAC addresses
        dst = eth.dst
        src = eth.src

        print(f"DPID: {dpid}, DsT: {dst}, ETH: {src}")

        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = in_port


        if dst in self.mac_to_port[dpid]:
            # if we already know the mac we can select the output port
            out_port = self.mac_to_port[dpid][dst]
            self.logger.info('Message for known {} at port {}'.format(src, out_port))

            # if we know the destination we can establish a flow
            self.add_flow(datapath, dst, in_port, out_port)
        else:
            # but if it can't be found we just flood the packet
            self.logger.info('Message for unknown {}'.format(src))
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)
