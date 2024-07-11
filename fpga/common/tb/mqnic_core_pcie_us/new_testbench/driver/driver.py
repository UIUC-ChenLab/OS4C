import asyncio
from collections import deque
from driver.register_map import *
import cocotb
from interface import *
from interrupt import *
from regblocklist import *        
import datetime

        
class Driver:
    def __init__(self):
        self.dev = None
        self.pool = None

        self.hw_regs = None
        self.app_hw_regs = None
        self.ram_hw_regs = None

        self.irq_sig = None
        self.irq_list = []

        self.reg_blocks = RegBlockList()
        self.fw_id_rb = None
        self.if_rb = None
        self.phc_rb = None

        self.fpga_id = None
        self.fw_id = None
        self.fw_ver = None
        self.board_id = None
        self.board_ver = None
        self.build_date = None
        self.build_time = None
        self.git_hash = None
        self.rel_info = None

        self.app_id = None

        self.if_offset = None
        self.if_count = None
        self.if_stride = None
        self.if_csr_offset = None

        self.initialized = False
        self.interrupt_running = False

        self.if_count = 1
        self.interfaces = []

        self.pkt_buf_size = 16384
        self.allocated_packets = []
        self.free_packets = deque()

    async def init_pcie_dev(self, dev):
        assert not self.initialized
        self.initialized = True

        self.dev = dev

        self.pool = self.dev.rc.mem_pool

        await self.dev.enable_device()
        await self.dev.set_master()
        await self.dev.alloc_irq_vectors(1, MQNIC_MAX_EVENT_RINGS)

        self.hw_regs = self.dev.bar_window[0]
        self.app_hw_regs = self.dev.bar_window[2]
        self.ram_hw_regs = self.dev.bar_window[4]

        # set up MSI
        for index in range(32):
            irq = Interrupt(index, self.interrupt_handler)
            self.dev.request_irq(index, irq.interrupt)
            self.irq_list.append(irq)

        await self.init_common()

    async def init_axi_dev(self, pool, hw_regs, app_hw_regs=None, irq=None):
        assert not self.initialized
        self.initialized = True

        self.pool = pool

        self.hw_regs = hw_regs
        self.app_hw_regs = app_hw_regs

        # set up edge-triggered interrupts
        if irq:
            for index in range(len(irq)):
                self.irq_list.append(Interrupt(index, self.interrupt_handler))
            cocotb.start_soon(self._run_edge_interrupts(irq))

        await self.init_common()

    async def init_common(self):
        self.log.info("Control BAR size: %d", self.hw_regs.size)
        if self.app_hw_regs:
            self.log.info("Application BAR size: %d", self.app_hw_regs.size)
        if self.ram_hw_regs:
            self.log.info("RAM BAR size: %d", self.ram_hw_regs.size)

        # Enumerate registers
        await self.reg_blocks.enumerate_reg_blocks(self.hw_regs)

        # Read ID registers
        self.fw_id_rb = self.reg_blocks.find(MQNIC_RB_FW_ID_TYPE, MQNIC_RB_FW_ID_VER)

        self.fpga_id = await self.fw_id_rb.read_dword(MQNIC_RB_FW_ID_REG_FPGA_ID)
        self.log.info("FPGA JTAG ID: 0x%08x", self.fpga_id)
        self.fw_id = await self.fw_id_rb.read_dword(MQNIC_RB_FW_ID_REG_FW_ID)
        self.log.info("FW ID: 0x%08x", self.fw_id)
        self.fw_ver = await self.fw_id_rb.read_dword(MQNIC_RB_FW_ID_REG_FW_VER)
        self.log.info("FW version: %d.%d.%d.%d", *self.fw_ver.to_bytes(4, 'big'))
        self.board_id = await self.fw_id_rb.read_dword(MQNIC_RB_FW_ID_REG_BOARD_ID)
        self.log.info("Board ID: 0x%08x", self.board_id)
        self.board_ver = await self.fw_id_rb.read_dword(MQNIC_RB_FW_ID_REG_BOARD_VER)
        self.log.info("Board version: %d.%d.%d.%d", *self.board_ver.to_bytes(4, 'big'))
        self.build_date = await self.fw_id_rb.read_dword(MQNIC_RB_FW_ID_REG_BUILD_DATE)
        self.log.info("Build date: %s UTC (raw: 0x%08x)", datetime.datetime.utcfromtimestamp(self.build_date).isoformat(' '), self.build_date)
        self.git_hash = await self.fw_id_rb.read_dword(MQNIC_RB_FW_ID_REG_GIT_HASH)
        self.log.info("Git hash: %08x", self.git_hash)
        self.rel_info = await self.fw_id_rb.read_dword(MQNIC_RB_FW_ID_REG_REL_INFO)
        self.log.info("Release info: %d", self.rel_info)

        rb = self.reg_blocks.find(MQNIC_RB_APP_INFO_TYPE, MQNIC_RB_APP_INFO_VER)

        if rb:
            self.app_id = await rb.read_dword(MQNIC_RB_APP_INFO_REG_ID)
            self.log.info("Application ID: 0x%08x", self.app_id)

        self.phc_rb = self.reg_blocks.find(MQNIC_RB_PHC_TYPE, MQNIC_RB_PHC_VER)

        # Enumerate interfaces
        self.if_rb = self.reg_blocks.find(MQNIC_RB_IF_TYPE, MQNIC_RB_IF_VER)
        self.interfaces = []

        if self.if_rb:
            self.if_offset = await self.if_rb.read_dword(MQNIC_RB_IF_REG_OFFSET)
            self.log.info("IF offset: %d", self.if_offset)
            self.if_count = await self.if_rb.read_dword(MQNIC_RB_IF_REG_COUNT)
            self.log.info("IF count: %d", self.if_count)
            self.if_stride = await self.if_rb.read_dword(MQNIC_RB_IF_REG_STRIDE)
            self.log.info("IF stride: 0x%08x", self.if_stride)
            self.if_csr_offset = await self.if_rb.read_dword(MQNIC_RB_IF_REG_CSR_OFFSET)
            self.log.info("IF CSR offset: 0x%08x", self.if_csr_offset)

            for k in range(self.if_count):
                i = Interface(self, k, self.hw_regs.create_window(self.if_offset + k*self.if_stride, self.if_stride))
                await i.init()
                self.interfaces.append(i)

        else:
            self.log.warning("No interface block found")

    async def _run_edge_interrupts(self, signal):
        last_val = 0
        count = len(signal)
        while True:
            await Edge(signal)
            val = signal.value.integer
            edge = val & ~last_val
            for index in (x for x in range(count) if edge & (1 << x)):
                await self.irq_list[index].interrupt()

    async def interrupt_handler(self, index):
        self.log.info("Interrupt handler start (IRQ %d)", index)
        for i in self.interfaces:
            for eq in i.event_queues:
                if eq.interrupt_index == index:
                    await eq.process()
                    await eq.arm()
        self.log.info("Interrupt handler end (IRQ %d)", index)

    def alloc_pkt(self):
        if self.free_packets:
            return self.free_packets.popleft()

        pkt = self.pool.alloc_region(self.pkt_buf_size)
        self.allocated_packets.append(pkt)
        return pkt

    def free_pkt(self, pkt):
        assert pkt is not None
        assert pkt in self.allocated_packets
        self.free_packets.append(pkt)