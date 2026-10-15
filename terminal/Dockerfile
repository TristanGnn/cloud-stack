FROM ubuntu:24.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ttyd bash-completion nano vim less git curl ca-certificates gcc make libc6-dev default-jdk-headless \
      python3 iputils-ping iproute2 dnsutils net-tools traceroute tree zip unzip man-db \
    && rm -rf /var/lib/apt/lists/*
COPY demarrer.sh /usr/local/bin/demarrer.sh
RUN chmod 755 /usr/local/bin/demarrer.sh
USER 1000:1000
ENV HOME=/workspace TERM=xterm-256color
WORKDIR /workspace/hers
# -a : l'URL ?arg=c est passée en argument à demarrer.sh
CMD ["ttyd", "-W", "-a", "-p", "7681", "-t", "fontSize=15", "-t", "titleFixed=Terminal", "/usr/local/bin/demarrer.sh"]
