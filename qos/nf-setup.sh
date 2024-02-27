sudo ovs-vsctl -- set Bridge r1 netflow=@nf -- --id=@nf create NetFlow targets=\"127.0.0.1:9996\"
sudo ovs-vsctl -- set Bridge r2 netflow=@nf -- --id=@nf create NetFlow targets=\"127.0.0.1:9996\"
sudo ovs-vsctl -- set Bridge r3 netflow=@nf -- --id=@nf create NetFlow targets=\"127.0.0.1:9996\"
sudo ovs-vsctl -- set Bridge r4 netflow=@nf -- --id=@nf create NetFlow targets=\"127.0.0.1:9996\"