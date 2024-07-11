from register_map import *
from regblocklist import *
from collections import deque
from cocotb.triggers import Event
import struct
from ring_buffer import *
from scheduler import *
from port import *

class Interface:
    def __init__(self, driver, index, hw_regs):
        self.driver = driver
        self.log = driver.log
        self.index = index
        self.hw_regs = hw_regs
        self.csr_hw_regs = hw_regs.create_window(driver.if_csr_offset)
        self.port_up = False

        self.reg_blocks = RegBlockList()
        self.if_ctrl_rb = None
        self.event_queue_rb = None
        self.tx_queue_rb = None
        self.tx_cpl_queue_rb = None
        self.rx_queue_rb = None
        self.rx_cpl_queue_rb = None
        self.rx_queue_map_rb = None

        self.if_features = None

        self.max_tx_mtu = 0
        self.max_rx_mtu = 0

        self.event_queue_offset = None
        self.event_queue_count = None
        self.event_queue_stride = None
        self.tx_queue_offset = None
        self.tx_queue_count = None
        self.tx_queue_stride = None
        self.tx_cpl_queue_offset = None
        self.tx_cpl_queue_count = None
        self.tx_cpl_queue_stride = None
        self.rx_queue_offset = None
        self.rx_queue_count = None
        self.rx_queue_stride = None
        self.rx_cpl_queue_offset = None
        self.rx_cpl_queue_count = None
        self.rx_cpl_queue_stride = None

        self.port_count = None
        self.sched_block_count = None

        self.rx_queue_map_indir_table_size = None
        self.rx_queue_map_indir_table = []

        self.event_queues = []

        self.tx_queues = []
        self.tx_cpl_queues = []
        self.rx_queues = []
        self.rx_cpl_queues = []
        self.ports = []
        self.sched_blocks = []

        self.interrupt_running = False
        self.interrupt_pending = 0

        self.pkt_rx_queue = deque()
        self.pkt_rx_sync = Event()

    async def init(self):
        # Read ID registers

        # Enumerate registers
        await self.reg_blocks.enumerate_reg_blocks(self.hw_regs, self.driver.if_csr_offset)

        self.if_ctrl_rb = self.reg_blocks.find(MQNIC_RB_IF_CTRL_TYPE, MQNIC_RB_IF_CTRL_VER)

        self.if_features = await self.if_ctrl_rb.read_dword(MQNIC_RB_IF_CTRL_REG_FEATURES)
        self.port_count = await self.if_ctrl_rb.read_dword(MQNIC_RB_IF_CTRL_REG_PORT_COUNT)
        self.sched_block_count = await self.if_ctrl_rb.read_dword(MQNIC_RB_IF_CTRL_REG_SCHED_COUNT)
        self.max_tx_mtu = await self.if_ctrl_rb.read_dword(MQNIC_RB_IF_CTRL_REG_MAX_TX_MTU)
        self.max_rx_mtu = await self.if_ctrl_rb.read_dword(MQNIC_RB_IF_CTRL_REG_MAX_RX_MTU)

        self.log.info("IF features: 0x%08x", self.if_features)
        self.log.info("Port count: %d", self.port_count)
        self.log.info("Scheduler block count: %d", self.sched_block_count)
        self.log.info("Max TX MTU: %d", self.max_tx_mtu)
        self.log.info("Max RX MTU: %d", self.max_rx_mtu)

        await self.set_mtu(min(self.max_tx_mtu, self.max_rx_mtu, 9214))

        self.event_queue_rb = self.reg_blocks.find(MQNIC_RB_EVENT_QM_TYPE, MQNIC_RB_EVENT_QM_VER)

        self.event_queue_offset = await self.event_queue_rb.read_dword(MQNIC_RB_EVENT_QM_REG_OFFSET)
        self.event_queue_count = await self.event_queue_rb.read_dword(MQNIC_RB_EVENT_QM_REG_COUNT)
        self.event_queue_stride = await self.event_queue_rb.read_dword(MQNIC_RB_EVENT_QM_REG_STRIDE)

        self.log.info("Event queue offset: 0x%08x", self.event_queue_offset)
        self.log.info("Event queue count: %d", self.event_queue_count)
        self.log.info("Event queue stride: 0x%08x", self.event_queue_stride)

        self.event_queue_count = min(self.event_queue_count, MQNIC_MAX_EVENT_RINGS)

        self.tx_queue_rb = self.reg_blocks.find(MQNIC_RB_TX_QM_TYPE, MQNIC_RB_TX_QM_VER)

        self.tx_queue_offset = await self.tx_queue_rb.read_dword(MQNIC_RB_TX_QM_REG_OFFSET)
        self.tx_queue_count = await self.tx_queue_rb.read_dword(MQNIC_RB_TX_QM_REG_COUNT)
        self.tx_queue_stride = await self.tx_queue_rb.read_dword(MQNIC_RB_TX_QM_REG_STRIDE)

        self.log.info("TX queue offset: 0x%08x", self.tx_queue_offset)
        self.log.info("TX queue count: %d", self.tx_queue_count)
        self.log.info("TX queue stride: 0x%08x", self.tx_queue_stride)

        self.tx_queue_count = min(self.tx_queue_count, MQNIC_MAX_TX_RINGS)

        self.tx_cpl_queue_rb = self.reg_blocks.find(MQNIC_RB_TX_CQM_TYPE, MQNIC_RB_TX_CQM_VER)

        self.tx_cpl_queue_offset = await self.tx_cpl_queue_rb.read_dword(MQNIC_RB_TX_CQM_REG_OFFSET)
        self.tx_cpl_queue_count = await self.tx_cpl_queue_rb.read_dword(MQNIC_RB_TX_CQM_REG_COUNT)
        self.tx_cpl_queue_stride = await self.tx_cpl_queue_rb.read_dword(MQNIC_RB_TX_CQM_REG_STRIDE)

        self.log.info("TX completion queue offset: 0x%08x", self.tx_cpl_queue_offset)
        self.log.info("TX completion queue count: %d", self.tx_cpl_queue_count)
        self.log.info("TX completion queue stride: 0x%08x", self.tx_cpl_queue_stride)

        self.tx_cpl_queue_count = min(self.tx_cpl_queue_count, MQNIC_MAX_TX_CPL_RINGS)

        self.rx_queue_rb = self.reg_blocks.find(MQNIC_RB_RX_QM_TYPE, MQNIC_RB_RX_QM_VER)

        self.rx_queue_offset = await self.rx_queue_rb.read_dword(MQNIC_RB_RX_QM_REG_OFFSET)
        self.rx_queue_count = await self.rx_queue_rb.read_dword(MQNIC_RB_RX_QM_REG_COUNT)
        self.rx_queue_stride = await self.rx_queue_rb.read_dword(MQNIC_RB_RX_QM_REG_STRIDE)

        self.log.info("RX queue offset: 0x%08x", self.rx_queue_offset)
        self.log.info("RX queue count: %d", self.rx_queue_count)
        self.log.info("RX queue stride: 0x%08x", self.rx_queue_stride)

        self.rx_queue_count = min(self.rx_queue_count, MQNIC_MAX_RX_RINGS)

        self.rx_cpl_queue_rb = self.reg_blocks.find(MQNIC_RB_RX_CQM_TYPE, MQNIC_RB_RX_CQM_VER)

        self.rx_cpl_queue_offset = await self.rx_cpl_queue_rb.read_dword(MQNIC_RB_RX_CQM_REG_OFFSET)
        self.rx_cpl_queue_count = await self.rx_cpl_queue_rb.read_dword(MQNIC_RB_RX_CQM_REG_COUNT)
        self.rx_cpl_queue_stride = await self.rx_cpl_queue_rb.read_dword(MQNIC_RB_RX_CQM_REG_STRIDE)

        self.log.info("RX completion queue offset: 0x%08x", self.rx_cpl_queue_offset)
        self.log.info("RX completion queue count: %d", self.rx_cpl_queue_count)
        self.log.info("RX completion queue stride: 0x%08x", self.rx_cpl_queue_stride)

        self.rx_cpl_queue_count = min(self.rx_cpl_queue_count, MQNIC_MAX_RX_CPL_RINGS)

        self.rx_queue_map_rb = self.reg_blocks.find(MQNIC_RB_RX_QUEUE_MAP_TYPE, MQNIC_RB_RX_QUEUE_MAP_VER)

        val = await self.rx_queue_map_rb.read_dword(MQNIC_RB_RX_QUEUE_MAP_REG_CFG)
        self.rx_queue_map_indir_table_size = 2**((val >> 8) & 0xff)
        self.rx_queue_map_indir_table = []
        for k in range(self.port_count):
            offset = await self.rx_queue_map_rb.read_dword(MQNIC_RB_RX_QUEUE_MAP_CH_OFFSET +
                    MQNIC_RB_RX_QUEUE_MAP_CH_STRIDE*k + MQNIC_RB_RX_QUEUE_MAP_CH_REG_OFFSET)
            self.rx_queue_map_indir_table.append(self.rx_queue_map_rb.parent.create_window(offset))

            await self.set_rx_queue_map_rss_mask(k, 0)
            await self.set_rx_queue_map_app_mask(k, 0)
            await self.set_rx_queue_map_indir_table(k, 0, 0)

        self.event_queues = []

        self.tx_queues = []
        self.tx_cpl_queues = []
        self.rx_queues = []
        self.rx_cpl_queues = []
        self.ports = []
        self.sched_blocks = []

        for k in range(self.event_queue_count):
            eq = EqRing(self, k, self.hw_regs.create_window(self.event_queue_offset + k*self.event_queue_stride, self.event_queue_stride))
            await eq.init()
            self.event_queues.append(eq)

        for k in range(self.tx_queue_count):
            txq = TxRing(self, k, self.hw_regs.create_window(self.tx_queue_offset + k*self.tx_queue_stride, self.tx_queue_stride))
            await txq.init()
            self.tx_queues.append(txq)

        for k in range(self.tx_cpl_queue_count):
            cq = CqRing(self, k, self.hw_regs.create_window(self.tx_cpl_queue_offset + k*self.tx_cpl_queue_stride, self.tx_cpl_queue_stride))
            await cq.init()
            self.tx_cpl_queues.append(cq)

        for k in range(self.rx_queue_count):
            rxq = RxRing(self, k, self.hw_regs.create_window(self.rx_queue_offset + k*self.rx_queue_stride, self.rx_queue_stride))
            await rxq.init()
            self.rx_queues.append(rxq)

        for k in range(self.rx_cpl_queue_count):
            cq = CqRing(self, k, self.hw_regs.create_window(self.rx_cpl_queue_offset + k*self.rx_cpl_queue_stride, self.rx_cpl_queue_stride))
            await cq.init()
            self.rx_cpl_queues.append(cq)

        for k in range(self.port_count):
            rb = self.reg_blocks.find(MQNIC_RB_PORT_TYPE, MQNIC_RB_PORT_VER, index=k)

            p = Port(self, k, rb)
            await p.init()
            self.ports.append(p)

        for k in range(self.sched_block_count):
            rb = self.reg_blocks.find(MQNIC_RB_SCHED_BLOCK_TYPE, MQNIC_RB_SCHED_BLOCK_VER, index=k)

            s = SchedulerBlock(self, k, rb)
            await s.init()
            self.sched_blocks.append(s)

        assert self.sched_block_count == len(self.sched_blocks)

        for eq in self.event_queues:
            await eq.alloc(1024, MQNIC_EVENT_SIZE)
            await eq.activate(self.index)  # TODO?
            await eq.arm()

        # wait for all writes to complete
        await self.hw_regs.read_dword(0)

    async def open(self):
        for rxq in self.rx_queues:
            cq = self.rx_cpl_queues[rxq.index]
            await cq.alloc(1024, MQNIC_CPL_SIZE)
            await cq.activate(self.event_queues[cq.index % self.event_queue_count])
            await cq.arm()
            await rxq.alloc(1024, MQNIC_DESC_SIZE*4)
            await rxq.activate(cq)

        for txq in self.tx_queues:
            cq = self.tx_cpl_queues[txq.index]
            await cq.alloc(1024, MQNIC_CPL_SIZE)
            await cq.activate(self.event_queues[cq.index % self.event_queue_count])
            await cq.arm()
            await txq.alloc(1024, MQNIC_DESC_SIZE*4)
            await txq.activate(cq)

        # wait for all writes to complete
        await self.hw_regs.read_dword(0)

        self.port_up = True

    async def close(self):
        self.port_up = False

        for txq in self.tx_queues:
            await txq.deactivate()
            await txq.cq.deactivate()

        for rxq in self.rx_queues:
            await rxq.deactivate()
            await rxq.cq.deactivate()

        # wait for all writes to complete
        await self.hw_regs.read_dword(0)

        for q in self.tx_queues:
            await q.free_buf()

        for q in self.rx_queues:
            await q.free_buf()

    async def start_xmit(self, skb, tx_ring=None, csum_start=None, csum_offset=None):
        if not self.port_up:
            return

        data = bytes(skb)

        assert len(data) < self.max_tx_mtu

        if tx_ring is not None:
            ring_index = tx_ring
        else:
            ring_index = 0

        ring = self.tx_queues[ring_index]

        while True:
            # check for space in ring
            if ring.head_ptr - ring.tail_ptr < ring.full_size:
                break

            # wait for space
            ring.clean_event.clear()
            await ring.clean_event.wait()

        index = ring.head_ptr & ring.size_mask

        ring.packets += 1
        ring.bytes += len(data)

        pkt = self.driver.alloc_pkt()

        assert not ring.tx_info[index]
        ring.tx_info[index] = pkt

        # put data in packet buffer
        pkt[10:len(data)+10] = data

        csum_cmd = 0

        if csum_start is not None and csum_offset is not None:
            csum_cmd = 0x8000 | (csum_offset << 8) | csum_start

        length = len(data)
        ptr = pkt.get_absolute_address(0)+10
        offset = 0

        # write descriptors
        seg = min(length-offset, 42) if ring.desc_block_size > 1 else length-offset
        struct.pack_into("<HHLQ", ring.buf, index*ring.stride, 0, csum_cmd, seg, ptr+offset if seg else 0)
        offset += seg
        for k in range(1, ring.desc_block_size):
            seg = min(length-offset, 4096) if k < ring.desc_block_size-1 else length-offset
            struct.pack_into("<4xLQ", ring.buf, index*ring.stride+k*MQNIC_DESC_SIZE, seg, ptr+offset if seg else 0)
            offset += seg

        ring.head_ptr += 1

        await ring.write_head_ptr()

    async def set_mtu(self, mtu):
        await self.if_ctrl_rb.write_dword(MQNIC_RB_IF_CTRL_REG_TX_MTU, mtu)
        await self.if_ctrl_rb.write_dword(MQNIC_RB_IF_CTRL_REG_RX_MTU, mtu)

    async def get_rx_queue_map_rss_mask(self, port):
        return await self.rx_queue_map_rb.read_dword(MQNIC_RB_RX_QUEUE_MAP_CH_OFFSET +
            MQNIC_RB_RX_QUEUE_MAP_CH_STRIDE*port + MQNIC_RB_RX_QUEUE_MAP_CH_REG_RSS_MASK)

    async def set_rx_queue_map_rss_mask(self, port, val):
        await self.rx_queue_map_rb.write_dword(MQNIC_RB_RX_QUEUE_MAP_CH_OFFSET +
            MQNIC_RB_RX_QUEUE_MAP_CH_STRIDE*port + MQNIC_RB_RX_QUEUE_MAP_CH_REG_RSS_MASK, val)

    async def get_rx_queue_map_app_mask(self, port):
        return await self.rx_queue_map_rb.read_dword(MQNIC_RB_RX_QUEUE_MAP_CH_OFFSET +
            MQNIC_RB_RX_QUEUE_MAP_CH_STRIDE*port + MQNIC_RB_RX_QUEUE_MAP_CH_REG_APP_MASK)

    async def set_rx_queue_map_app_mask(self, port, val):
        await self.rx_queue_map_rb.write_dword(MQNIC_RB_RX_QUEUE_MAP_CH_OFFSET +
            MQNIC_RB_RX_QUEUE_MAP_CH_STRIDE*port + MQNIC_RB_RX_QUEUE_MAP_CH_REG_APP_MASK, val)

    async def get_rx_queue_map_indir_table(self, port, index):
        return await self.rx_queue_map_indir_table[port].read_dword(index*4)

    async def set_rx_queue_map_indir_table(self, port, index, val):
        await self.rx_queue_map_indir_table[port].write_dword(index*4, val)

    async def recv(self):
        if not self.pkt_rx_queue:
            self.pkt_rx_sync.clear()
            await self.pkt_rx_sync.wait()
        return self.recv_nowait()

    def recv_nowait(self):
        if self.pkt_rx_queue:
            return self.pkt_rx_queue.popleft()
        return None

    async def wait(self):
        if not self.pkt_rx_queue:
            self.pkt_rx_sync.clear()
            await self.pkt_rx_sync.wait()
