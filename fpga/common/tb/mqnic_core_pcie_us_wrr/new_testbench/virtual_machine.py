import driver
import generator
import ring_buffer
import communication
import asyncio

class VirtualMachine() :
    generator_details : generator.GeneratorDetails
    driver_details : driver.DriverDetails
    buffer_details : ring_buffer.BufferDetails
    
    def __init__(self, my_address : str, destination_addresses : 'list[str]',
                address_mac_dict : 'dict[str, str]', hardware_driver_queue : communication.CommunicationQueues,
                hardware_buffer_queue : communication.CommunicationQueues) :
        
        # initialize Generator-Driver Queues
        generator_driver_queue_pair = communication.create_communication_queue_pair()
            
        # initialize RingBuffer-Driver Queues
        buffer_driver_queue_pair = communication.create_communication_queue_pair()
            
        # initialize Generator Data Structure
        self.generator_details = generator.GeneratorDetails(my_address, destination_addresses,
            address_mac_dict, generator_driver_queue_pair[0])
        
        self.driver_details = None
        self.buffer_details = None
        
    async def run_simulation(self) :
        generator_routine = asyncio.create_task(generator.generator_coroutine(self.generator_details))
        driver_routine = asyncio.create_task(driver.driver_coroutine(self.driver_details))
        buffer_routine = asyncio.create_task(ring_buffer.buffer_coroutine(self.buffer_details))
        await asyncio.gather(generator_routine, driver_routine, buffer_routine)
        