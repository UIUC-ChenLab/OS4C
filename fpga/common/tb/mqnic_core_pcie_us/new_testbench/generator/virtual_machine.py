import driver.driver as driver
import application
import driver.ring_buffer as ring_buffer
import communication
import asyncio

class VirtualMachine() :
    application_details : application.applicationDetails
    driver_details : driver.DriverDetails
    buffer_details : ring_buffer.BufferDetails
    
    def __init__(self,
                my_address : str,
                destination_addresses : 'list[str]',
                function_id : int,
                address_mac_dict : 'dict[str, str]',
                driver_to_hardware : communication.CommunicationQueue,
                driver_to_memory : communication.CommunicationQueue,
                hardware_to_driver : communication.CommunicationQueue
                ) :
        
        # initialize application-Driver Queues
        application_to_driver = communication.create_communication_queue(False)
            
        # initialize application Data Structure
        self.application_details = application.ApplicationDetails(
            my_address,
            destination_addresses,
            address_mac_dict,
            application_to_driver
            )

        self.driver_details = driver.DriverDetails(
            function_id,
            driver_to_memory,
            application_to_driver,
            driver_to_hardware,
            hardware_to_driver
            )

        self.buffer_details = None
        
    async def run_simulation(self) :
        application_routine = asyncio.create_task(application.application_coroutine(self.application_details))
        driver_routine = asyncio.create_task(driver.driver_coroutine(self.driver_details))
        # buffer_routine = asyncio.create_task(ring_buffer.buffer_coroutine(self.buffer_details))
        await asyncio.gather(application_routine, driver_routine)
        