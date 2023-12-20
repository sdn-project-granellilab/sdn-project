#!/usr/bin/python3

from topology_builder import NetworkSlicingTopo
import os
from multiprocessing import Process
from threading import Thread

# entry point
if __name__ == '__main__':
    os.system('mn -c')
    os.system('docker stop d1; docker stop d2; docker stop d3; docker stop d4;')
    os.system('docker build -t alpine_test - < Dockerfile')
    t_cli = Thread(target=os.system, args=['python3 topology_builder.py'])
    t_switch = Thread(target=os.system, args=['ryu-manager switch.py > ryu_manager.log'], daemon=True)

    t_switch.start()
    t_cli.start()


