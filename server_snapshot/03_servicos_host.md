# Serviços do Host (fora do Docker)

## Services rodando
```
containerd.service
cron.service
dbus.service
docker.service
getty@tty1.service
grafana-agent.service
nginx.service
rsyslog.service
ssh.service
systemd-journald.service
systemd-logind.service
systemd-timesyncd.service
systemd-udevd.service
user@0.service
```

## Timers ativos
```
roleta-deploy.service Wed 2026-06-10 18:51:15
systemd-tmpfiles-clean.service Wed 2026-06-10 18:54:26
fstrim.service Wed 2026-06-10 19:14:14
apt-daily-upgrade.service Wed 2026-06-10 19:35:07
man-db.service Wed 2026-06-10 19:48:11
apt-daily.service Wed 2026-06-10 23:46:17
dpkg-db-backup.service Thu 2026-06-11 00:00:00
logrotate.service Thu 2026-06-11 00:00:00
certbot.service Thu 2026-06-11 06:17:32
e2scrub_all.service Sun 2026-06-14 03:10:24
```

## Crontab root
```
* * * * * /usr/local/bin/roleta-gap-check.sh
```

## Portas escutando
```
0.0.0.0:22 "sshd"
0.0.0.0:443 "nginx"
0.0.0.0:80 "nginx"
127.0.0.1:12345 "grafana-agent"
127.0.0.1:12346 "grafana-agent"
127.0.0.1:3000 "docker-proxy"
127.0.0.1:5432 "docker-proxy"
127.0.0.1:8765 "docker-proxy"
127.0.0.1:8766 "docker-proxy"
127.0.0.1:9090 "docker-proxy"
127.0.0.1:9093 "docker-proxy"
127.0.0.1:9187 "docker-proxy"
[::]:22 "sshd"
*:9100 "node_exporter"
```
