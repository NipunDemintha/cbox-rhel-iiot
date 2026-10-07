# CBOX-E ↔ RHEL IIoT Bridge

Two-way communication between a **Haiwell CBOX-E** edge gateway and an **RHEL** server
over MQTT, with every value logged to **PostgreSQL**.

```
CBOX (192.168.1.112) ⇄ Mosquitto (RHEL 192.168.1.200:1883) ⇄ Python bridge → PostgreSQL
```

## Components
| Folder | Content |
|---|---|
| `bridge/` | Python MQTT ↔ PostgreSQL bridge + Dockerfile |
| `mosquitto/` | Broker configuration |
| `database/` | Table schema (`cbox_tag_log`) |
| `haiwell/` | Haiwell Cloud SCADA project (`RHEL_IoT_Task.hwdev`) |
| `docs/` | Setup / configuration reference (PDF) |

## MQTT message format
| Direction | Topic | Payload |
|---|---|---|
| RHEL → CBOX | `data/1234/factory/task1//1` | `{"V0":"123","_groupName":"data1"}` (value as string) |
| CBOX → RHEL | `cmd/1234/factory/task1//1` | `{"type":"set_var","payload":{"V0":"55"}}` |

## Network prerequisite (RHEL)
The CBOX project expects the broker at `192.168.1.200`:
```bash
sudo nmcli con mod cbox +ipv4.addresses 192.168.1.200/24
sudo nmcli con up cbox
sudo firewall-cmd --add-port=1883/tcp --permanent && sudo firewall-cmd --reload
```

## Run with Docker (recommended)
```bash
cp .env.example .env        # set DB_PASSWORD
docker compose up -d --build
docker compose logs -f bridge
```

## Run without Docker
```bash
pip3 install --user -r bridge/requirements.txt
python3 bridge/cbox_bridge_db.py   # reads ./.env or ~/cbox/cbox.env
```

## Check data
```bash
docker exec -it cbox-postgres psql -U cbox -d cbox_db \
  -c "SELECT id, ts AT TIME ZONE 'Asia/Colombo', value, direction FROM cbox_tag_log ORDER BY id DESC LIMIT 10;"
```

## Roadmap
- [ ] MQTT username/password (requires updating CBOX `MQTT_1` + project download)
- [ ] Production DB credentials
- [ ] Decide on legacy `mqtt-bridge` container
