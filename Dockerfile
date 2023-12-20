FROM httpd:latest

RUN apt-get update
RUN apt-get install iputils-ping net-tools iproute2 ethtool -y

CMD python3 -m http.server
