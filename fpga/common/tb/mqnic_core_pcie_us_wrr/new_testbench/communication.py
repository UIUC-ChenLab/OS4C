import asyncio

class CommunicationQueues :
    def __init__(self, send_queue : asyncio.Queue, receive_queue : asyncio.Queue) :
        self.send_queue = send_queue
        self.receive_queue = receive_queue
        
def create_communication_queue_pair() -> 'tuple[CommunicationQueues, CommunicationQueues]':
    first_to_second = asyncio.Queue()
    second_to_first = asyncio.Queue()
    first_queue = CommunicationQueues(first_to_second, second_to_first)
    second_queue = CommunicationQueues(second_to_first, first_to_second)
    return (first_queue, second_queue)
