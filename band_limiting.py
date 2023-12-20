import os
from topology_builder import CLIENT_NUM, SWITCH_NUM, SERVER_NUM

MB = 1000000

def set_max_rate(intf, max_rate):
    command = f"ovs-vsctl set Port {intf} qos=@newqos -- --id=@newqos create QoS type=linux-htb other-config:max-rate={max_rate} queues:1=@q1 -- --id=@q1 create Queue other-config:max-rate={max_rate}"

    os.system(command)

if __name__ == "__main__":
    set_max_rate("r2-eth1", 10*MB)
    set_max_rate("r1-eth1", 10*MB)

def main():
    for i in range(4):
        for j in range(6):

            set_max_rate(f"r{i+1}-eth{j+1}", 0.5*MB)

# ovs-vsctl set port r2-eth1 qos=@newqos -- --id=@newqos create QoS type=linux-htb other-config:max-rate=10000000