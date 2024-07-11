import os
import sys
import ipaddress
import asyncio
import argparse
import logging
import virtual_machine
import communication


def parse_args() -> 'tuple[int, str, str, str]':
# parse input arguments to main
    parser = argparse.ArgumentParser(
        prog = 'SRIOVTestbench',
        description='Instantiates a number of "drivers" which interface with the SR-IOV Corundum Implementation.',
        epilog='See the README for more details'
    )
    parser.add_argument('count', type=int, help='Number of VM instances')
    parser.add_argument('mac', type=str, help='The base MAC address of the device.')
    parser.add_argument('address', type=str, help='The starting IP address for the drivers.')
    parser.add_argument('--log', dest='log', required=False, type=str,
                        help='The minimum logging level. Options are DEBUG, INFO, WARNING, or ERROR', default='DEBUG')
    args = parser.parse_args()
    return args.count, args.mac, args.address, args.log

async def main() :
    num_vms, base_mac, base_address, log_level = parse_args()
    logging.basicConfig(filename='mqnic.log', level=getattr(logging, log_level.upper()), format='%(levelname)s:%(message)s')
    logger = logging.getLogger()
    logger.info(f'Starting testbench with {num_vms} total VMs....')
    base_mac_int = int(base_mac.replace(':', ''), 16)
    base_address_int = int(ipaddress.ip_address(base_address))
    

    address_mac_dict = {}
    all_addresses = []
    all_macs = []
    for i in range(0, num_vms) :
        # Create MAC address
        mac_address_int = base_mac_int + i
        mac_address_str = hex(mac_address_int).replace('0x', '')
        mac_address = ":".join(mac_address_str[i:i+2] for i in range(0, len(mac_address_str), 2))
        # Create IP address
        ip_address = ipaddress.ip_address(base_address_int + i)
        all_addresses.append(str(ip_address))
        all_macs.append(str(mac_address))
        address_mac_dict[str(ip_address)] = mac_address
        
    # instantiate hardware-driver queues and hardware-buffer queues
    hardware_driver_queues : 'list[tuple[communication.CommunicationQueues, communication.CommunicationQueues]]'= []
    hardware_buffer_queues : 'list[tuple[communication.CommunicationQueues, communication.CommunicationQueues]]'= []
    for i in range(0, num_vms) :
        hardware_driver_queues.append(communication.create_communication_queue_pair())
        hardware_buffer_queues.append(communication.create_communication_queue_pair())
        
    virtual_machines : 'list[virtual_machine.VirtualMachine]'= []
    for i in range(0, num_vms) :
        destination_address = all_addresses.copy()
        destination_address.remove(all_addresses[i])
        new_vm = virtual_machine.VirtualMachine(all_addresses[i], destination_address,
            address_mac_dict, hardware_driver_queues[i], hardware_buffer_queues[i])
        virtual_machines.append(new_vm)
    
    vm_tasks = []
    for i in range(0, num_vms) :
        vm_tasks.append(asyncio.create_task(virtual_machines[i].run_simulation()))
    
    await asyncio.gather(*vm_tasks)
    
    

if __name__ == "__main__" :
    print("Starting testbench....")
    asyncio.run(main())
    
    
        
    
        
    
    
    