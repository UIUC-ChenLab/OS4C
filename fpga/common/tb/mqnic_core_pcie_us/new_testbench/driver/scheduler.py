from driver.register_map import *
from regblocklist import *

class BaseScheduler:
    def __init__(self, port, index, rb):
        self.port = port
        self.log = port.log
        self.interface = port.interface
        self.driver = port.interface.driver
        self.index = index
        self.rb = rb
        self.hw_regs = None

    async def init(self):
        pass


class SchedulerRoundRobin(BaseScheduler):
    def __init__(self, port, index, rb):
        super().__init__(port, index, rb)

    async def init(self):
        offset = await self.rb.read_dword(MQNIC_RB_SCHED_RR_REG_OFFSET)
        self.hw_regs = self.rb.parent.create_window(offset)


class SchedulerControlTdma(BaseScheduler):
    def __init__(self, port, index, rb):
        super().__init__(port, index, rb)

    async def init(self):
        offset = await self.rb.read_dword(MQNIC_RB_SCHED_CTRL_TDMA_REG_OFFSET)
        self.hw_regs = self.rb.parent.create_window(offset)


class SchedulerBlock:
    def __init__(self, interface, index, rb):
        self.interface = interface
        self.log = interface.log
        self.driver = interface.driver
        self.index = index

        self.block_rb = rb
        self.reg_blocks = RegBlockList()

        self.sched_count = None

        self.schedulers = []

    async def init(self):
        # Read ID registers

        offset = await self.block_rb.read_dword(MQNIC_RB_SCHED_BLOCK_REG_OFFSET)
        await self.reg_blocks.enumerate_reg_blocks(self.block_rb.parent, offset)

        self.schedulers = []

        self.sched_count = 0
        for rb in self.reg_blocks:
            if rb.type == MQNIC_RB_SCHED_RR_TYPE and rb.version == MQNIC_RB_SCHED_RR_VER:
                s = SchedulerRoundRobin(self, self.sched_count, rb)
                await s.init()
                self.schedulers.append(s)

                self.sched_count += 1
            elif rb.type == MQNIC_RB_SCHED_CTRL_TDMA_TYPE and rb.version == MQNIC_RB_SCHED_CTRL_TDMA_VER:
                s = SchedulerControlTdma(self, self.sched_count, rb)
                await s.init()
                self.schedulers.append(s)

                self.sched_count += 1

        self.log.info("Scheduler count: %d", self.sched_count)
