#!/usr/bin/python3
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, RemoteController
from mininet.cli import CLI
from mininet.link import TCLink
from comnetsemu.net import Containernet
from comnetsemu.node import DockerHost
from mininet.log import setLogLevel
from functools import partial

SWITCH_NUM = 4
CLIENT_NUM = 4
SERVER_NUM = 4

SERVER_IMG = [
        "server_circa:latest",
        "server_circa:latest",
        "server_circa:latest",
        "server_circa:latest"
        ]

class NetworkSlicingTopo(Topo):
    def __init__(self):
        Topo.__init__(self)
        
        host_config      = dict(
            inNamespace=True
            )
        link_config_high = dict(
                    bw=10,
                    #delay="10ms"
                )
        link_config_low  = dict(
                    bw=1,
                    #delay="10ms"
                )
        host_link_config = dict(
                    bw=0.5,
                    #delay="15ms"
                )
        server_link_config = dict(
                    bw=10,
                    #delay="10ms"
                )
        switch_config    = dict(
                #inNamespace=True,
                failMode="standalone",
                stp=True
            )

        # SWITCH
        for i in range(SWITCH_NUM):
            sconfig = {**switch_config, "dpid": "%016x"%(i+1)}
            self.addSwitch(f"r{i+1}", **sconfig)
        
        # Client
        for i in range(CLIENT_NUM):
            self.addHost(f"h{i+1}", **host_config)

        for i in range(SERVER_NUM):
            self.addHost(
                    f"s{i+1}",
                    ip=f"10.0.0.{i+CLIENT_NUM+1}",
                    dimage=SERVER_IMG[i],
                    port_bindings={80:80, 443:443},
                    ports=[80,443],
                    publish_all_ports=True,
                    docker_args={
                        },
                    cls=DockerHost
                )
            #print(type(self.g.node[f"s{i+CLIENT_NUM+1}"]))
                
            #.setIP(f"10.0.0.{i+CLIENT_NUM+1}", prefixLen=24, intf=f"s{i+CLIENT_NUM+1}-eth0")
            #get(f"s{i+1}").setIP(f"10.0.0.{ii+CLIENT_NUM+1}", prefixLen=24, intf=f"s{i+1}-eth0")
            
            #print(h1)

        self.addLink("r1", "r2", port1=5, port2=1, **link_config_high)
        self.addLink("r1", "r4", port1=6, port2=1, **link_config_low)
        self.addLink("r4", "r3", port1=2, port2=5, **link_config_low)
        self.addLink("r2", "r3", port1=2, port2=6, **link_config_high)

        for i in range(CLIENT_NUM):
            self.addLink(f"h{i+1}", "r1", port1=0, port2=i+1, **host_link_config)

        for i in range(SERVER_NUM):
            self.addLink(f"s{i+1}", "r3", port1=0, port2=i+1, **server_link_config)
    
    @staticmethod
    def setContainerIP(net):
        print(net.get(f"s1").IP())
        for i in range(SERVER_NUM):
            net.get(f's{i+1}').cmd(f"ifconfig s{i+1}-eth0 10.0.0.{i+1+CLIENT_NUM}")

#topos = {"networkSlicingTopo": (lambda: NetworkSlicingTopo())}

if __name__ == '__main__':
    #setLogLevel("debug")
    topo = NetworkSlicingTopo()
    net = Containernet(
        topo=topo,
        switch=OVSKernelSwitch,
        build=False,
        #controller=partial(RemoteController, name='c0',ip='127.0.0.1', port=6633),
        autoSetMacs=True,
        #autoStaticArp=True,
        link=TCLink
        )
    net.addController('c0',controller=RemoteController,ip='127.0.0.1')
    net.build()
    # this line add network ip configuration to the docker host, since the Containernet interface fails to do it
    #topo.setContainerIP(net)
    #import band_limiting
    #band_limiting.main()
    net.start()
    #band_limiting.main()

    CLI(net)
    net.stop()