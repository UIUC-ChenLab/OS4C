from regblocklist import *

class Port:
    def __init__(self, interface, index, rb):
        self.interface = interface
        self.log = interface.log
        self.driver = interface.driver
        self.index = index

        self.port_rb = rb
        self.reg_blocks = RegBlockList()
        self.port_ctrl_rb = None

        self.port_features = None

    async def init(self):
        # Read ID registers

        offset = await self.port_rb.read_dword(MQNIC_RB_PORT_REG_OFFSET)
        await self.reg_blocks.enumerate_reg_blocks(self.port_rb.parent, offset)

        self.port_ctrl_rb = self.reg_blocks.find(MQNIC_RB_PORT_CTRL_TYPE, MQNIC_RB_PORT_CTRL_VER)

        self.port_features = await self.port_ctrl_rb.read_dword(MQNIC_RB_PORT_CTRL_REG_FEATURES)

        self.log.info("Port features: 0x%08x", self.port_features)

    async def get_tx_status(self, port):
        return await self.port_ctrl_rb.read_dword(MQNIC_RB_PORT_CTRL_REG_TX_STATUS)

    async def get_rx_status(self, port):
        return await self.port_ctrl_rb.read_dword(MQNIC_RB_PORT_CTRL_REG_RX_STATUS)

