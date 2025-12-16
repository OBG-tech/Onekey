sudo iw dev wlp3s0 interface add wlp3s0_ap type __ap
sudo ip link set dev wlp3s0_ap address 22:33:44:55:66:00
cd create_ap/
sudo nohup create_ap -c 11 wlp3s0_ap wlp3s0 MagicLLM 12345678