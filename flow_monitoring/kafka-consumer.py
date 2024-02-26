from confluent_kafka import Consumer
import json
import sqlite3
import threading, multiprocessing
import datetime
import psycopg2

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
            tmp["SrcPort"] = i["SrcPort"]
            tmp["DstPort"] = i["DstPort"]

            tmp["ProtType"] = self._getProtocol(i["ProtType"])

            # Opt.
            tmp["SrcMask"] = i["SrcMask"]
            tmp["DstMask"] = i["DstMask"]

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
        return '\n'.join(f'[NEW] SrcAddr: {flow["SrcAddr"]}, DstAddr: {flow["DstAddr"]}, StartTime: {flow["StartTime"]}, PktCount: {flow["PktCount"]}, EndTime: {flow["EndTime"]}, SrcPort: {flow["SrcPort"]}, DstPort: {flow["DstPort"]}, ProtType: {flow["ProtType"]}, SrcMask: {flow["SrcMask"]}, DstMask: {flow["DstMask"]}' for flow in self.obj)

class NetflowInformationRetriever():
    OCTET = 8
    def __init__(self) -> None:
        self.conf = {
            'bootstrap.servers': '127.0.0.1:9092',
            'group.id': 'python',
            'auto.offset.reset': 'earliest'
        }

        self.hub = threading.Thread(target=self._consumer_fun_and_elaboration)
        self.consumer = Consumer(self.conf)

        self.conn = sqlite3.connect("flaws_kafka.db")
        self.cur = self.conn.cursor()
        self.suicide = True

        self.cur.execute("CREATE TABLE IF NOT EXISTS flows(src_addr, dst_addr, start_time, end_time, pkt_count, l3octets, tos);")

        self.hub.start()

    def get_flow_information(self):
        """
            Sync. Call to read database and return JSON-like data.
        """
        res = dict()
        query4 = self.cur.execute("SELECT * FROM flows;")

        for i in query4.fetchall():
            
            (src_addr, dst_addr, start_time, end_time, pkt_count, l3octets, tos) = i
            dict1 = dict()
            dict1[src_addr] = {
                "end_time": end_time,
                "start_time": start_time,
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
                query1 = self.cur.execute(f"SELECT * from flows where src_addr='{i_src}' and dst_addr='{i_dst}' and tos='{i_tos}';")
                if query1.fetchone() is None:
                    src_addr, dst_addr, start_time, end_time, pkt_count, l3octets, tos = \
                        i["SrcAddr"], i["DstAddr"], i["StartTime"], i["EndTime"], i["PktCount"], i["L3Octets"], i["Tos"]
                    query2 = self.cur.execute(f"INSERT INTO flows VALUES (?, ?, ?, ?, ?, ?, ?);", (src_addr, dst_addr, start_time, end_time, pkt_count, l3octets, tos))

                else:
                    (i1, i2, start_time, end_time, pkt_count, i6, i7) = query1[0]
                    n_start_time = start_time
                    n_end_time = end_time
                    if start_time > i["StartTime"]:
                        n_start_time = i["StartTime"]
                    if end_time < i["EndTime"]:
                        n_end_time = i["EndTime"]
                    pkt_count += i["PktCount"]
                    l3oct_new = query1[0][6] + i["L30Octets"]
                    query3 = self.cur.execute("UPDATE flows SET pkt_count=?, l30octets=?, start_time=?, end_time=? where where src_addr=? and dst_addr=? and tos=?;", 
                                              (pkt_count, l3oct_new, n_start_time, n_end_time))

                self.con.commit()

    def bandwith_usage_per_link(self):
        res = dict()
        query = self.cur.execute("SELECT * FROM flows;")

        for i in query.fetchall():
            
            (src_addr, dst_addr, start_time, end_time, pkt_count, l3octets, tos) = i
            dict1 = dict()
            dict1[src_addr] = {
                "bytes": l3octets * self.OCTET,
                "delta_t": "" ,
            }

            res[dst_addr] = dict1
            
        return res
    def close(self):
        """
            Close connection.
        """
        self.suicide = False

    def empty_trash(self):
        """
            Empty the database.
        """
        # self.cur.execute("DROP DATABASE flaws_kafka.db IF EXISTS;")
        # self.cur.execute("CREATE TABLE IF NOT EXISTS flows(src_addr, dst_addr, input, output, pkt_count, l3octets, tos);")
        
    def __del__(self):
        print("Closing..")
        self.consumer.close()


if __name__ == "__main__":
    netflow = NetflowInformationRetriever()
    netflow.empty_trash()
    for i in range(10):
        print(i, " " ,netflow.get_flow_information())
    netflow.close()