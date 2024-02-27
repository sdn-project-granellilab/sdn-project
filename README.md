# Getting Started

To start, run, in this order:

1. Config /etc/hosts

```sh
sudo echo "127.0.0.1 kafka" >> /etc/hosts
```

2. Start docker services !TODO

```sh
docker-compose up -f /docker-compose/docker-compose.yml
```

3. Start Ryu-Controller TODO

```sh
ryu-manager switches/simple-switch.py
```

4. Start mininet

```sh
sudo mn -c && sudo python3 topo/topolino.py
```

5. Set Netflow Data exporters on OpenFlow's routers

Using this service, we move out the complexity from the network appliance, in order
to optimize the systems, and make it faster, since the entire complexity of the flow
monitoring is moved to the dedicated service.

```sh
bash ./qos/nf-setup.sh
```

6. Create Traffic on the mininet network.

TODO

7. Visualize the flow on Grafana `localhost:3000`