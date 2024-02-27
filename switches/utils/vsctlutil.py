import subprocess

def create_queue(port, max_rate, queues):
    queue_configs = []
    for i in range(len(queues)):
        queue_configs.insert(i, f"@queue{i}")
    queue_config = ""
    for i in range(len(queue_configs)):
        queue_config += f"queues:{i}={queue_configs[i]} "
    
    command = f"ovs-vsctl set port {port} qos=@qos1 -- --id=@qos1 create qos type=linux-htb {queue_config} other-config:max-rate={max_rate} "

    for i in range(len(queue_configs)):
        command += f"-- --id={queue_configs[i]} create queue other-config:max-rate={queues[i]} "
    print(command)
    output = subprocess.check_output(command, shell=True)
    out = str.split(output.decode("utf-8"), "\n")
    return out[:-1]

def set_queue(uuid, queue_max_rate):
    command = f'ovs-vsctl set queue {uuid} other-config:max-rate={queue_max_rate}'
    subprocess.check_output(command, shell=True)
