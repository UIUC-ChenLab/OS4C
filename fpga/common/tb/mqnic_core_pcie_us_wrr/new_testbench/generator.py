import asyncio
import time
import numpy as np

from scapy.layers.l2 import Ether
from scapy.layers.inet import IP, UDP, TCP
import scapy.utils
import communication
import ipaddress
import random
import logging

class GeneratorDetails :
    
    def __init__(self, my_address : ipaddress.IPv4Address, destination_addresses : 'list[ipaddress.IPv4Address]',
                address_mac_dict : dict, generator_driver_queues : communication.CommunicationQueues) :
        self.my_address = my_address
        self.destination_addresses = destination_addresses
        self.address_mac_dict = address_mac_dict
        self.generator_driver_queues = generator_driver_queues
        
def random_payload_generator(packet_size : int = 256) :
    payload = bytes([random.randint(0, 255) for i in range(packet_size)])
    return payload

def udp_protocol(src_port : int, dst_port : int) :
    return UDP(sport=src_port, dport=dst_port)

#TODO: probably doesnt work as is.
def tcp_protocol(src_port : int, dst_port : int) :
    return TCP(sport=src_port, dport=dst_port)

def ethernet_protocol(src_mac : str, dst_mac : str) :
    return Ether(src=src_mac, dst=dst_mac)

def choose_random_destination(destination_addresses : list) :
    return destination_addresses[random.randint(0, len(destination_addresses)-1)]

def ip_protocol(src_address : str, dst_address : str) :
    return IP(src=src_address, dst=dst_address)

async def gaussian_delay(center : float = 1, deviation : float = 1, max_range : float = 3) -> float :
# waits for a random amount of time. The random number is based on a gaussian distribution
    sleep_time = np.random.normal(center, deviation)
    sleep_time = max(sleep_time, 0, center - max_range)
    sleep_time = min(sleep_time, center + max_range)
    await asyncio.sleep(sleep_time)

async def generator_coroutine(generator_details : GeneratorDetails) -> bytes:
    
    logger = logging.getLogger()
    
    while True :
        await gaussian_delay(1, 1, 3)
        payload = random_payload_generator(1470)
        dst_address = choose_random_destination(generator_details.destination_addresses)
        layer_4 = udp_protocol(1, 1)
        layer_3 = ip_protocol(generator_details.my_address, dst_address)
        src_mac = generator_details.address_mac_dict[generator_details.my_address]
        dst_mac = generator_details.address_mac_dict[dst_address]
        layer_2 = ethernet_protocol(src_mac, dst_mac)
        
        test_pkt = layer_2 / layer_3 / layer_4 / payload
        test_pkt[UDP].chksum = scapy.utils.checksum(bytes(test_pkt))
        
        final_packet = test_pkt.build()
        
        await generator_details.generator_driver_queues.send_queue.put(final_packet)
        logger.info(f'{generator_details.my_address} generated a packet of size {len(final_packet)} with destination {dst_address}')
        
