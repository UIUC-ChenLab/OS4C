from register_map import *
import struct
import asyncio


class BufferDetails() :
    pass


async def buffer_coroutine(buffer_details : BufferDetails) :
    pass

class EqRing:
    def __init__(self, interface, size, stride, index, hw_regs):
        self.interface = interface
        self.log = interface.log
        self.driver = interface.driver
        self.log_size = size.bit_length() - 1
        self.size = 2**self.log_size
        self.size_mask = self.size-1
        self.stride = stride
        self.index = index
        self.interrupt_index = 0

        self.head_ptr = 0
        self.tail_ptr = 0

        self.hw_ptr_mask = 0xffff
        self.hw_regs = hw_regs

    async def init(self):
        self.log.info("Init EqRing %d (interface %d)", self.index, self.interface.index)

        self.buf_size = self.size*self.stride
        self.buf_region = self.driver.pool.alloc_region(self.buf_size)
        self.buf_dma = self.buf_region.get_absolute_address(0)
        self.buf = self.buf_region.mem

        await self.hw_regs.write_dword(MQNIC_EVENT_QUEUE_ACTIVE_LOG_SIZE_REG, 0)  # active, log size
        await self.hw_regs.write_dword(MQNIC_EVENT_QUEUE_BASE_ADDR_REG, self.buf_dma & 0xffffffff)  # base address
        await self.hw_regs.write_dword(MQNIC_EVENT_QUEUE_BASE_ADDR_REG+4, self.buf_dma >> 32)  # base address
        await self.hw_regs.write_dword(MQNIC_EVENT_QUEUE_INTERRUPT_INDEX_REG, 0)  # interrupt index
        await self.hw_regs.write_dword(MQNIC_EVENT_QUEUE_HEAD_PTR_REG, self.head_ptr & self.hw_ptr_mask)  # head pointer
        await self.hw_regs.write_dword(MQNIC_EVENT_QUEUE_TAIL_PTR_REG, self.tail_ptr & self.hw_ptr_mask)  # tail pointer
        await self.hw_regs.write_dword(MQNIC_EVENT_QUEUE_ACTIVE_LOG_SIZE_REG, self.log_size)  # active, log size

    async def activate(self, int_index):
        self.log.info("Activate EqRing %d (interface %d)", self.index, self.interface.index)

        self.interrupt_index = int_index

        await self.hw_regs.write_dword(MQNIC_EVENT_QUEUE_ACTIVE_LOG_SIZE_REG, 0)  # active, log size
        await self.hw_regs.write_dword(MQNIC_EVENT_QUEUE_INTERRUPT_INDEX_REG, int_index)  # interrupt index
        await self.hw_regs.write_dword(MQNIC_EVENT_QUEUE_HEAD_PTR_REG, self.head_ptr & self.hw_ptr_mask)  # head pointer
        await self.hw_regs.write_dword(MQNIC_EVENT_QUEUE_TAIL_PTR_REG, self.tail_ptr & self.hw_ptr_mask)  # tail pointer
        await self.hw_regs.write_dword(MQNIC_EVENT_QUEUE_ACTIVE_LOG_SIZE_REG, self.log_size | MQNIC_EVENT_QUEUE_ACTIVE_MASK)  # active, log size

    async def deactivate(self):
        await self.hw_regs.write_dword(MQNIC_EVENT_QUEUE_ACTIVE_LOG_SIZE_REG, self.log_size)  # active, log size
        await self.hw_regs.write_dword(MQNIC_EVENT_QUEUE_INTERRUPT_INDEX_REG, self.interrupt_index)  # interrupt index

    def empty(self):
        return self.head_ptr == self.tail_ptr

    def full(self):
        return self.head_ptr - self.tail_ptr >= self.size

    async def read_head_ptr(self):
        val = await self.hw_regs.read_dword(MQNIC_EVENT_QUEUE_HEAD_PTR_REG)
        self.head_ptr += (val - self.head_ptr) & self.hw_ptr_mask

    async def write_tail_ptr(self):
        await self.hw_regs.write_dword(MQNIC_EVENT_QUEUE_TAIL_PTR_REG, self.tail_ptr & self.hw_ptr_mask)

    async def arm(self):
        await self.hw_regs.write_dword(MQNIC_EVENT_QUEUE_INTERRUPT_INDEX_REG, self.interrupt_index | MQNIC_EVENT_QUEUE_ARM_MASK)  # interrupt index

    async def process(self):
        if not self.interface.port_up:
            return

        self.log.info("Process event queue")

        await self.read_head_ptr()

        eq_tail_ptr = self.tail_ptr
        eq_index = eq_tail_ptr & self.size_mask

        self.log.info("%d events in queue", self.head_ptr - eq_tail_ptr)

        while (self.head_ptr != eq_tail_ptr):
            event_data = struct.unpack_from("<HH", self.buf, eq_index*self.stride)

            self.log.info("Event data: %s", repr(event_data))

            if event_data[0] == 0:
                # transmit completion
                cq = self.interface.tx_cpl_queues[event_data[1]]
                await self.interface.process_tx_cq(cq)
                await cq.arm()
            elif event_data[0] == 1:
                # receive completion
                cq = self.interface.rx_cpl_queues[event_data[1]]
                await self.interface.process_rx_cq(cq)
                await cq.arm()

            eq_tail_ptr += 1
            eq_index = eq_tail_ptr & self.size_mask

        self.tail_ptr = eq_tail_ptr
        await self.write_tail_ptr()


class CqRing:
    def __init__(self, interface, size, stride, index, hw_regs):
        self.interface = interface
        self.log = interface.log
        self.driver = interface.driver
        self.log_size = size.bit_length() - 1
        self.size = 2**self.log_size
        self.size_mask = self.size-1
        self.stride = stride
        self.index = index
        self.interrupt_index = 0
        self.ring_index = 0

        self.head_ptr = 0
        self.tail_ptr = 0

        self.hw_ptr_mask = 0xffff
        self.hw_regs = hw_regs

    async def init(self):
        self.log.info("Init CqRing %d (interface %d)", self.index, self.interface.index)

        self.buf_size = self.size*self.stride
        self.buf_region = self.driver.pool.alloc_region(self.buf_size)
        self.buf_dma = self.buf_region.get_absolute_address(0)
        self.buf = self.buf_region.mem

        await self.hw_regs.write_dword(MQNIC_CPL_QUEUE_ACTIVE_LOG_SIZE_REG, 0)  # active, log size
        await self.hw_regs.write_dword(MQNIC_CPL_QUEUE_BASE_ADDR_REG, self.buf_dma & 0xffffffff)  # base address
        await self.hw_regs.write_dword(MQNIC_CPL_QUEUE_BASE_ADDR_REG+4, self.buf_dma >> 32)  # base address
        await self.hw_regs.write_dword(MQNIC_CPL_QUEUE_INTERRUPT_INDEX_REG, 0)  # event index
        await self.hw_regs.write_dword(MQNIC_CPL_QUEUE_HEAD_PTR_REG, self.head_ptr & self.hw_ptr_mask)  # head pointer
        await self.hw_regs.write_dword(MQNIC_CPL_QUEUE_TAIL_PTR_REG, self.tail_ptr & self.hw_ptr_mask)  # tail pointer
        await self.hw_regs.write_dword(MQNIC_CPL_QUEUE_ACTIVE_LOG_SIZE_REG, self.log_size)  # active, log size

    async def activate(self, int_index):
        self.log.info("Activate CqRing %d (interface %d)", self.index, self.interface.index)

        self.interrupt_index = int_index

        await self.hw_regs.write_dword(MQNIC_CPL_QUEUE_ACTIVE_LOG_SIZE_REG, 0)  # active, log size
        await self.hw_regs.write_dword(MQNIC_CPL_QUEUE_INTERRUPT_INDEX_REG, int_index)  # event index
        await self.hw_regs.write_dword(MQNIC_CPL_QUEUE_HEAD_PTR_REG, self.head_ptr & self.hw_ptr_mask)  # head pointer
        await self.hw_regs.write_dword(MQNIC_CPL_QUEUE_TAIL_PTR_REG, self.tail_ptr & self.hw_ptr_mask)  # tail pointer
        await self.hw_regs.write_dword(MQNIC_CPL_QUEUE_ACTIVE_LOG_SIZE_REG, self.log_size | MQNIC_CPL_QUEUE_ACTIVE_MASK)  # active, log size

    async def deactivate(self):
        await self.hw_regs.write_dword(MQNIC_CPL_QUEUE_ACTIVE_LOG_SIZE_REG, self.log_size)  # active, log size
        await self.hw_regs.write_dword(MQNIC_CPL_QUEUE_INTERRUPT_INDEX_REG, self.interrupt_index)  # event index

    def empty(self):
        return self.head_ptr == self.tail_ptr

    def full(self):
        return self.head_ptr - self.tail_ptr >= self.size

    async def read_head_ptr(self):
        val = await self.hw_regs.read_dword(MQNIC_CPL_QUEUE_HEAD_PTR_REG)
        self.head_ptr += (val - self.head_ptr) & self.hw_ptr_mask

    async def write_tail_ptr(self):
        await self.hw_regs.write_dword(MQNIC_CPL_QUEUE_TAIL_PTR_REG, self.tail_ptr & self.hw_ptr_mask)

    async def arm(self):
        await self.hw_regs.write_dword(MQNIC_CPL_QUEUE_INTERRUPT_INDEX_REG, self.interrupt_index | MQNIC_CPL_QUEUE_ARM_MASK)  # event index


class TxRing:
    def __init__(self, interface, size, stride, index, hw_regs):
        self.interface = interface
        self.log = interface.log
        self.driver = interface.driver
        self.log_queue_size = size.bit_length() - 1
        self.log_desc_block_size = int(stride/MQNIC_DESC_SIZE).bit_length() - 1
        self.desc_block_size = 2**self.log_desc_block_size
        self.size = 2**self.log_queue_size
        self.size_mask = self.size-1
        self.full_size = self.size >> 1
        self.stride = stride
        self.index = index
        self.cpl_index = 0

        self.head_ptr = 0
        self.tail_ptr = 0
        self.clean_tail_ptr = 0

        self.clean_event = Event()

        self.packets = 0
        self.bytes = 0

        self.hw_ptr_mask = 0xffff
        self.hw_regs = hw_regs

    async def init(self):
        self.log.info("Init TxRing %d (interface %d)", self.index, self.interface.index)

        self.tx_info = [None]*self.size

        self.buf_size = self.size*self.stride
        self.buf_region = self.driver.pool.alloc_region(self.buf_size)
        self.buf_dma = self.buf_region.get_absolute_address(0)
        self.buf = self.buf_region.mem

        await self.hw_regs.write_dword(MQNIC_QUEUE_ACTIVE_LOG_SIZE_REG, 0)  # active, log size
        await self.hw_regs.write_dword(MQNIC_QUEUE_BASE_ADDR_REG, self.buf_dma & 0xffffffff)  # base address
        await self.hw_regs.write_dword(MQNIC_QUEUE_BASE_ADDR_REG+4, self.buf_dma >> 32)  # base address
        await self.hw_regs.write_dword(MQNIC_QUEUE_CPL_QUEUE_INDEX_REG, 0)  # completion queue index
        await self.hw_regs.write_dword(MQNIC_QUEUE_HEAD_PTR_REG, self.head_ptr & self.hw_ptr_mask)  # head pointer
        await self.hw_regs.write_dword(MQNIC_QUEUE_TAIL_PTR_REG, self.tail_ptr & self.hw_ptr_mask)  # tail pointer
        await self.hw_regs.write_dword(MQNIC_QUEUE_ACTIVE_LOG_SIZE_REG, self.log_queue_size | (self.log_desc_block_size << 8))  # active, log desc block size, log queue size

    async def activate(self, cpl_index):
        self.log.info("Activate TxRing %d (interface %d)", self.index, self.interface.index)

        self.cpl_index = cpl_index

        await self.hw_regs.write_dword(MQNIC_QUEUE_ACTIVE_LOG_SIZE_REG, 0)  # active, log size
        await self.hw_regs.write_dword(MQNIC_QUEUE_CPL_QUEUE_INDEX_REG, cpl_index)  # completion queue index
        await self.hw_regs.write_dword(MQNIC_QUEUE_HEAD_PTR_REG, self.head_ptr & self.hw_ptr_mask)  # head pointer
        await self.hw_regs.write_dword(MQNIC_QUEUE_TAIL_PTR_REG, self.tail_ptr & self.hw_ptr_mask)  # tail pointer
        await self.hw_regs.write_dword(MQNIC_QUEUE_ACTIVE_LOG_SIZE_REG, self.log_queue_size | (self.log_desc_block_size << 8) | MQNIC_QUEUE_ACTIVE_MASK)  # active, log desc block size, log queue size

    async def deactivate(self):
        await self.hw_regs.write_dword(MQNIC_QUEUE_ACTIVE_LOG_SIZE_REG, self.log_queue_size | (self.log_desc_block_size << 8))  # active, log desc block size, log queue size

    def empty(self):
        return self.head_ptr == self.clean_tail_ptr

    def full(self):
        return self.head_ptr - self.clean_tail_ptr >= self.full_size

    async def read_tail_ptr(self):
        val = await self.hw_regs.read_dword(MQNIC_QUEUE_TAIL_PTR_REG)
        self.tail_ptr += (val - self.tail_ptr) & self.hw_ptr_mask

    async def write_head_ptr(self):
        await self.hw_regs.write_dword(MQNIC_QUEUE_HEAD_PTR_REG, self.head_ptr & self.hw_ptr_mask)

    def free_desc(self, index):
        pkt = self.tx_info[index]
        self.driver.free_pkt(pkt)
        self.tx_info[index] = None

    def free_buf(self):
        while not self.empty():
            index = self.clean_tail_ptr & self.size_mask
            self.free_desc(index)
            self.clean_tail_ptr += 1


class RxRing:
    def __init__(self, interface, size, stride, index, hw_regs):
        self.interface = interface
        self.log = interface.log
        self.driver = interface.driver
        self.log_queue_size = size.bit_length() - 1
        self.log_desc_block_size = int(stride/MQNIC_DESC_SIZE).bit_length() - 1
        self.desc_block_size = 2**self.log_desc_block_size
        self.size = 2**self.log_queue_size
        self.size_mask = self.size-1
        self.full_size = self.size >> 1
        self.stride = stride
        self.index = index
        self.cpl_index = 0

        self.head_ptr = 0
        self.tail_ptr = 0
        self.clean_tail_ptr = 0

        self.packets = 0
        self.bytes = 0

        self.hw_ptr_mask = 0xffff
        self.hw_regs = hw_regs

    async def init(self):
        self.log.info("Init RxRing %d (interface %d)", self.index, self.interface.index)

        self.rx_info = [None]*self.size

        self.buf_size = self.size*self.stride
        self.buf_region = self.driver.pool.alloc_region(self.buf_size)
        self.buf_dma = self.buf_region.get_absolute_address(0)
        self.buf = self.buf_region.mem

        await self.hw_regs.write_dword(MQNIC_QUEUE_ACTIVE_LOG_SIZE_REG, 0)  # active, log size
        await self.hw_regs.write_dword(MQNIC_QUEUE_BASE_ADDR_REG, self.buf_dma & 0xffffffff)  # base address
        await self.hw_regs.write_dword(MQNIC_QUEUE_BASE_ADDR_REG+4, self.buf_dma >> 32)  # base address
        await self.hw_regs.write_dword(MQNIC_QUEUE_CPL_QUEUE_INDEX_REG, 0)  # completion queue index
        await self.hw_regs.write_dword(MQNIC_QUEUE_HEAD_PTR_REG, self.head_ptr & self.hw_ptr_mask)  # head pointer
        await self.hw_regs.write_dword(MQNIC_QUEUE_TAIL_PTR_REG, self.tail_ptr & self.hw_ptr_mask)  # tail pointer
        await self.hw_regs.write_dword(MQNIC_QUEUE_ACTIVE_LOG_SIZE_REG, self.log_queue_size | (self.log_desc_block_size << 8))  # active, log desc block size, log queue size

    async def activate(self, cpl_index):
        self.log.info("Activate RxRing %d (interface %d)", self.index, self.interface.index)

        self.cpl_index = cpl_index

        await self.hw_regs.write_dword(MQNIC_QUEUE_ACTIVE_LOG_SIZE_REG, 0)  # active, log size
        await self.hw_regs.write_dword(MQNIC_QUEUE_CPL_QUEUE_INDEX_REG, cpl_index)  # completion queue index
        await self.hw_regs.write_dword(MQNIC_QUEUE_HEAD_PTR_REG, self.head_ptr & self.hw_ptr_mask)  # head pointer
        await self.hw_regs.write_dword(MQNIC_QUEUE_TAIL_PTR_REG, self.tail_ptr & self.hw_ptr_mask)  # tail pointer
        await self.hw_regs.write_dword(MQNIC_QUEUE_ACTIVE_LOG_SIZE_REG, self.log_queue_size | (self.log_desc_block_size << 8) | MQNIC_QUEUE_ACTIVE_MASK)  # active, log desc block size, log queue size

        await self.refill_buffers()

    async def deactivate(self):
        await self.hw_regs.write_dword(MQNIC_QUEUE_ACTIVE_LOG_SIZE_REG, self.log_queue_size | (self.log_desc_block_size << 8))  # active, log desc block size, log queue size

    def empty(self):
        return self.head_ptr == self.clean_tail_ptr

    def full(self):
        return self.head_ptr - self.clean_tail_ptr >= self.full_size

    async def read_tail_ptr(self):
        val = await self.hw_regs.read_dword(MQNIC_QUEUE_TAIL_PTR_REG)
        self.tail_ptr += (val - self.tail_ptr) & self.hw_ptr_mask

    async def write_head_ptr(self):
        await self.hw_regs.write_dword(MQNIC_QUEUE_HEAD_PTR_REG, self.head_ptr & self.hw_ptr_mask)

    def free_desc(self, index):
        pkt = self.rx_info[index]
        self.driver.free_pkt(pkt)
        self.rx_info[index] = None

    def free_buf(self):
        while not self.empty():
            index = self.clean_tail_ptr & self.size_mask
            self.free_desc(index)
            self.clean_tail_ptr += 1

    def prepare_desc(self, index):
        pkt = self.driver.alloc_pkt()
        self.rx_info[index] = pkt

        length = pkt.size
        ptr = pkt.get_absolute_address(0)
        offset = 0

        # write descriptors
        for k in range(0, self.desc_block_size):
            seg = min(length-offset, 4096) if k < self.desc_block_size-1 else length-offset
            struct.pack_into("<LLQ", self.buf, index*self.stride+k*MQNIC_DESC_SIZE, 0, seg, ptr+offset if seg else 0)
            offset += seg

    async def refill_buffers(self):
        missing = self.size - (self.head_ptr - self.clean_tail_ptr)

        if missing < 8:
            return

        for k in range(missing):
            self.prepare_desc(self.head_ptr & self.size_mask)
            self.head_ptr += 1

        await self.write_head_ptr()