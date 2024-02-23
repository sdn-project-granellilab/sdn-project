from ryu.lib.ovs import vsctl
from ryu.lib.ovs.bridge import OVSBridge
from typing import List

class Queue:
    def __init__(self, min_bw:int,max_bw:int) -> None:
        self.min_rate=str(min_bw)
        self.max_rate=str(max_bw)
    def rate_dict(self):
        return{
            'max-rate':self.max_rate,
            'min-rate':self.min_rate
        }

def init_queues_in_port(bridge:OVSBridge,name:str,port:str,qos_bw:int,queues:List[Queue]):
    '''
    Creates the specified queues on the specified port of the bridge
    '''
    bridge.br_name=name
    result=bridge.set_qos(port,max_rate=str(qos_bw),queues=[
        queue.rate_dict()
    for queue in queues])
    return result

def modify_queue(ovsdb_addr,uuid,max_bw,min_bw):
    ovs_vsctl=vsctl.VSCtl(ovsdb_addr)
    cmd = vsctl.VSCtlCommand('set', ('Queue', uuid), ('other-config:max-rate',str(max_bw)),('other-config:min-rate',str(min_bw)))
    ovs_vsctl.run_command(cmd)
    return cmd.result

# ryu_switch -> metodo init
    #os.system("ovs-vsctl set-manager 'ptcp:6640'") (solo una volta a meno che non venga pulito completamente il db)
#ryu_switch -> metodo packet_in_handler
    # dpid=datapath.id
    #     bridge=OVSBridge(self.CONF,dpid,'tcp:127.0.0.1:6640')
    #     bridge.br_name=f'r{dpid}'
    #     ports= bridge.get_port_name_list()
        
    #     bw=1000 if dpid==4 else 10000
    #     queue0=qos.Queue(0,bw*0.75)
    #     queue1=qos.Queue(0,bw*0.25)
    #     for port in ports:
    #         result = qos.init_queues_in_port(bridge,bridge.br_name,port,bw,[queue0,queue1])
    #         #result è una lista di righe del db: oggetti ovs.db.idl.Row
    #         print(f"----{port}----")
    #         print(f"QoS:{result[0].uuid}\n Queue0:{result[1].uuid}\nQueue1:{result[2].uuid}")

    ########################################################################################
    #
    #   Si può creare un dizionario in cui mappare gli uuid da usare poi con modify_queue
    #
    ########################################################################################

############################################################################################
#                             COMANDI UTILI
############################################################################################
# Visualizzare le tabelle queue e qos
    #sudo ovs-vsctl -f table list queue
    #sudo ovs-vsctl -f table list qos
# Eliminare tutte le politiche QoS e Queue (pulisce le tabelle)[se non funziona invertire i comandi]{Prima bisogna fermare mininet e resettarlo mn -c}
    #sudo ovs-vsctl --all destroy QoS
    #sudo ovs-vsctl --all destroy Queue
############################################################################################