import socket
import struct
from ipfix import IpfixMessage, IpfixTemplate, IpfixDataRecord

def convert_to_ipfix(packet_data):
    # Parse the raw packet data
    eth_header = packet_data[:14]
    ip_header = packet_data[14:34]
    tcp_header = packet_data[34:54]
    
    # Extract relevant fields from the headers
    src_ip = socket.inet_ntoa(eth_header[6:10])
    dst_ip = socket.inet_ntoa(eth_header[0:4])
    src_port = struct.unpack('!H', tcp_header[0:2])[0]
    dst_port = struct.unpack('!H', tcp_header[2:4])[0]
    protocol = struct.unpack('!B', tcp_header[9])[0]
    
    # Create an IPFIX message
    ipfix_msg = IpfixMessage()
    
    # Define the template for the IPFIX record
    template = IpfixTemplate(
        template_id=1,
        field_count=4,
        fields=[
            (1, 'sourceIPv4Address', 'ipv4Address'),
            (2, 'destinationIPv4Address', 'ipv4Address'),
            (3, 'sourceTransportPort', 'unsigned16'),
            (4, 'destinationTransportPort', 'unsigned16')
        ]
    )
    ipfix_msg.add_template(template)
    
    # Create a data record using the template
    data_record = IpfixDataRecord(template_id=1, data=[src_ip, dst_ip, src_port, dst_port])
    ipfix_msg.add_data_record(data_record)
    
    # Convert the IPFIX message to a byte string
    ipfix_data = ipfix_msg.to_bytes()
    
    return ipfix_data

# Example usage
packet_data = b'33\x00\x00\x00\x16\x00\x00\x00\x00\x00\x07\x86\xdd`\x00\x00\x00\x00$\x00\x01\xfe\x80\x00\x00\x00\x00\x00\x00\x02\x00\x00\xff\xfe\x00\x00\x07\xff\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x16:\x00\x05\x02\x00\x00\x01\x00\x8f\x00o\xfb\x00\x00\x00\x01\x04\x00\x00\x00\xff\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\xff\x00\x00\x07'
ipfix_data = convert_to_ipfix(packet_data)
print(ipfix_data)