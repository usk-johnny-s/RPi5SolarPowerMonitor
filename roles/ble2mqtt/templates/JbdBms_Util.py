from typing import Optional

def jbd_checksum8(data: bytes) -> bytes:
    # 8bit checksum
    sum = 0
    for byte in data:
        sum = ((sum + int(byte)) & 0xff)
    return sum.to_bytes(1)

def jbd_checksum16(data: bytes) -> bytes:
    # inverted 16bit checksum
    sum = 0
    for byte in data:
        sum = ((sum + int(byte)) & 0xffff)
    return ((-sum) & 0xffff).to_bytes(2,"big")

def jbd_packet_pack(start: int,cmd: int,data: bytes, stop: Optional[int] = None) -> bytes:
    if ((start == 0xFFAA) and (stop is None)):
        packet = bytes()
        packet += start.to_bytes(2,"big")
        packet += cmd.to_bytes()
        packet += (len(data)).to_bytes(1)
        packet += data
        csum8 = jbd_checksum8(packet[2:])
        packet += csum8
        return packet
    if (((start == 0xDDA5) or (start == 0xDD5A)) and (stop == 0x77)):
        packet = bytes()
        packet += start.to_bytes(2,"big")
        packet += cmd.to_bytes(1)
        packet += (len(data)).to_bytes(1)
        packet += data
        csum16 = jbd_checksum16(packet[2:])
        packet += csum16
        packet += stop.to_bytes(1)
        return packet
    return None # Unknown start,stop

def jdb_packet_unpack(packet: bytes) -> tuple[Optional[int], Optional[int], Optional[bytes], Optional[int]]:
    if (len(packet) < 5):
        return (None,None,None,None) # Packet too short.
    pkt_start = int.from_bytes(packet[:2],"big")
    if (pkt_start == 0xFFAA):
        csum8 = jbd_checksum8(packet[2:-1])
        pkt_csum8 = packet[-1:]
        if (pkt_csum8 != csum8):
            return (None,None,None,None) # Packet csum8 not match.
        pkt_cmd = packet[2]
        pkt_len = packet[3]
        pkt_data = packet[4:-1]
        if (pkt_len != len(pkt_data)):
            return (None,None,None,None) # Not match packet length
        return (pkt_start,pkt_cmd,pkt_data,None)
    pkt_start = packet[0]
    pkt_stop = packet[-1]
    if ((pkt_start == 0xDD) and (pkt_stop == 0x77)):
        csum16 = jbd_checksum16(packet[2:-3])
        pkt_csum16 = packet[-3:-1]
        if (pkt_csum16 != csum16):
            return (None,None,None,None) # Packet csum16 not match.
        pkt_cmd = packet[1]
        pkt_data = packet[2:-3]
        return (pkt_start,pkt_cmd,pkt_data,pkt_stop)
    return (None,None,None,None) # Unknown start,stop
