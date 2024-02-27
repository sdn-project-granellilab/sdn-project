from confluent_kafka import Consumer
import json
import threading
import datetime
import psycopg2
import time

# This code is create to handle the packet flow translation in a way that could be
# accessed by the ryu-manager script running.

# type FlowRecord struct {
# 	SrcAddr   uint32 // Source IP Address
# 	DstAddr   uint32 // Destination IP Address
# 	NextHop   uint32 // IP Address of the next hop router
# 	Input     uint16 // SNMP index of input interface
# 	Output    uint16 // SNMP index of output interface
# 	PktCount  uint32 // Number of packets in the flow
# 	L3Octets  uint32 // Total number of Layer 3 bytes in the packets of the flow
# 	StartTime uint32 // SysUptime at start of flow in ms since last boot
# 	EndTime   uint32 // SysUptime at end of the flow in ms since last boot
# 	SrcPort   uint16 // TCP/UDP source port number or equivalent
# 	DstPort   uint16 // TCP/UDP destination port number or equivalent
# 	Padding1  uint8  // Unused (zero) bytes
# 	TCPFlags  uint8  // Cumulative OR of TCP flags
# 	ProtType  uint8  // IP protocol type (for example, TCP = 6; UDP = 17)
# 	Tos       uint8  // IP type of service (ToS)
# 	SrcAsNum  uint16 // Autonomous system number of the source, either origin or peer
# 	DstAsNum  uint16 // Autonomous system number of the destination, either origin or peer
# 	SrcMask   uint8  // Source address prefix mask bits
# 	DstMask   uint8  // Destination address prefix mask bits
# 	Padding2  uint16 // Unused (zero) bytes
# }

class NetflowInfo:
    def __init__(self, inlog):
        self.obj = []

        for i in inlog["Flows"]:
            tmp = {}

            tmp["SrcAddr"] = i["SrcAddr"]
            tmp["DstAddr"] = i["DstAddr"]
            tmp["StartTime"] = i["StartTime"]
            tmp["PktCount"] = i["PktCount"]
            tmp["EndTime"] = i["EndTime"]

            tmp["ProtType"] = self._getProtocol(i["ProtType"])

            self.obj.append(tmp)

    def _getProtocol(self, protocol):
        if protocol == 6:
            return "TCP"
        elif protocol == 17:
            return "UDP"
        else:
            return "None"
    def __str__(self):
        # Assuming you want to print the details of each flow
        return '\n'.join(f'[NEW] SrcAddr: {flow["SrcAddr"]}, DeltaT: {flow["StartTime"]-flow["EndTime"]}, PktCount: {flow["PktCount"]}, DstAddr: {flow["DstAddr"]},  ProtType: {flow["ProtType"]},' for flow in self.obj)

class NetflowInformationRetriever():
    OCTET = 8
    def __init__(self) -> None:
        self.conf = {
            'bootstrap.servers': '127.0.0.1:9092',
            'group.id': 'python',
            'auto.offset.reset': 'earliest'
        }

        self.consumer = Consumer(self.conf)

        self.conn = psycopg2.connect(
            database = "Netflow",
            host = "127.0.0.1",
            user = "postgres",
            password = "example",
            port = "5432"
        )
        self.cur = self.conn.cursor()
        self.suicide = True

        self.last_element = dict()

        # TODO: create database.
        # self.cur.execute("CREATE DATABASE IF NOT EXISTS Netflow;")

        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS flows(src_addr VARCHAR(20), dst_addr VARCHAR(20), time_delta INT, pkt_count INT, octets INT, tos INT);
                """)
        self.conn.commit()


    def get_flow_information(self):
        """
            Sync. Call to read database and return JSON-like data.
        """
        res = dict()
        self.cur.execute("SELECT * FROM flows;")

        if self.cur.fetchone() is None:
            return {"message": "no data exists on database."}
        for i in self.cur.fetchall():
            
            (src_addr, dst_addr, interval, pkt_count, l3octets, tos) = i
            dict1 = dict()
            dict1[src_addr] = {
                "interval": interval,
                "pkt_count": pkt_count,
                "l3octet": l3octets,
                "tos": tos
            }

            res[dst_addr] = dict1
            
        return res

    def _consumer_fun_and_elaboration(self):
        self.consumer.subscribe(['vflow.netflow5'])
        while self.suicide:
            msg = self.consumer.poll(1.0)
            #print("This this is gettingexecuted")

            if msg is None:
                continue
            if msg.error():
                print("Consumer error: {}".format(msg.error()))
                continue
            pkt_conv = NetflowInfo(json.loads(msg.value().decode("utf-8")))
            print('Received message: ', pkt_conv)
            msg_dec = json.loads(msg.value().decode("utf-8"))

            for i in msg_dec["Flows"]:

                # check if there is already a component present
                i_src = i["SrcAddr"]
                i_dst = i["DstAddr"]
                i_tos = i["Tos"]
                self.cur.execute(f"SELECT * from flows where src_addr=%s and dst_addr=%s and tos=%s;", 
                                          (i_src, i_dst, i_tos))
                query1 = self.cur.fetchone()
                if query1 is None:
                    src_addr, dst_addr, start_time, end_time, pkt_count, l3octets, tos = \
                        i["SrcAddr"], i["DstAddr"], i["StartTime"], i["EndTime"], i["PktCount"], i["L3Octets"], i["Tos"]
                    insert_query = "INSERT INTO flows (src_addr, dst_addr, time_delta, pkt_count, octets, tos) VALUES (%s, %s, %s, %s, %s, %s);"
                    print(end_time-start_time)
                    values = (src_addr, dst_addr, end_time-start_time, pkt_count, l3octets, tos)
                    print(values)
                    self.cur.execute(insert_query, values)

                else:
                    #print(i)
                    (i1, i2, interval, pkt_count, octet, i6) = query1
                    n_interval = 0
                    n_interval += interval
                    pkt_count += i["PktCount"]
                    l3oct_new = octet + i["L3Octets"]
                    self.cur.execute("UPDATE flows SET pkt_count=%s, octets=%s, time_delta=%s WHERE src_addr=%s and dst_addr=%s and tos=%s;", 
                                              (pkt_count, l3oct_new, n_interval, i_src, i_dst, i_tos))

                self.conn.commit()

    def bandwith_usage_per_link(self):
        res = dict()
        self.cur.execute("SELECT * FROM flows;")
        query = self.cur.fetchall()

        # 1. find flows (10.1)/10.5 -> 10.5/10.1
        # 2. while finding the flows, elaborate on flow bandwith

        #print("This is the query:\n",  query)
        # 10.1 -> 10.3 tos=0
        # 10.1 -> 10.3 tos=16
        
        for i in query:
            
            (src_addr, dst_addr, delta_t, pkt_count, l3octets, tos) = i

            if (dst_addr, src_addr) in res:
                # [IF] l'inverso esiste, allora inserisco quello nuovo
                # come somma di quelli prima, e poi aggiorno quello inizialmente inserito
                # Recupero le informazioni che gia' ho
                curr_obj = res[(dst_addr, src_addr)]

                # Le sommo a quelle che non ho ancora
                res[(src_addr, dst_addr)] = {   
                    "bytes": curr_obj["bytes"]+(l3octets*self.OCTET*pkt_count),
                    "delta_t": curr_obj["delta_t"] + delta_t,
                    "tos": [curr_obj["tos"][0], tos]
                }

                # Aggiorno l'oggetto originale in modo che siano uguali
                res[(dst_addr, src_addr)] = res[(src_addr, dst_addr)].copy()
            else:
                # se non esiste inserisco semplicemente il primo valore.
                res[(src_addr, dst_addr)] = {
                    "bytes": l3octets * self.OCTET * pkt_count,
                    "delta_t":  delta_t,
                    "tos": [tos],
                }
        
        # this for loop ensure that every flow is a couple.
        for i in query:
            (src_addr, dst_addr, delta_t, pkt_count, l3octets, tos) = i
            if res[(dst_addr, src_addr)] is None:
                if res[(src_addr, dst_addr)] is None:
                    continue
                else:
                    res[(src_addr, dst_addr)] = res[(dst_addr, src_addr)].copy()
            else:
                if res[(src_addr, dst_addr)] is None:
                    res[(src_addr, dst_addr)] = res[(dst_addr, dst_addr)].copy()

        checked = []
        for (i, k) in res.keys():
            #print("STAMPA FOR: ", (i, k))
            if (i, k) in checked or (k, i) in checked:
                continue

            try:
                if self.last_element[(i, k)] is not None:
                    new_bytes = res[(i, k)]["bytes"] - self.last_element[(i, k)]["bytes"] if res[(i, k)]["bytes"] - self.last_element[(i, k)]["bytes"] > 0 else -1
                    new_delta = res[(i, k)]["delta_t"] - self.last_element[(i, k)]["delta_t"] if res[(i, k)]["delta_t"] - self.last_element[(i, k)]["delta_t"] > 0 else -1

                    res[(i, k)] = {
                        "bytes":  new_bytes,
                        "delta_t": new_delta,
                        "tos": res[(i, k)]["tos"]
                    }

                    res[(k, i)] = {
                        "bytes":  new_bytes,
                        "delta_t": new_delta,
                        "tos": res[(i, k)]["tos"]
                    }
                    checked.append((i, k))
            except KeyError:
                continue

        self.last_element = res.copy()

        return res
    
    def close(self):
        """
            Close connection.
        """
        self.suicide = False
        
    def __del__(self):
        print("Closing..")
        self.consumer.close()

class NetflowUpdater(NetflowInformationRetriever):
    def __init__(self) -> None:
        super().__init__()
        self.hub = threading.Thread(target=self._consumer_fun_and_elaboration)
        self.hub.start()

if __name__ == "__main__":
    netflow = NetflowUpdater()
    for i in range(10000000):
        netflow.bandwith_usage_per_link()
        #print(i, " " ,netflow.bandwith_usage_per_link())
        time.sleep(5)
    netflow.close()