# SPDX-License-Identifier: BSD-2-Clause-Views
# Copyright (c) 2021-2023 The Regents of the University of California

import logging
import os
import struct
import sys

import scapy.utils
from scapy.layers.l2 import Ether
from scapy.layers.inet import IP, UDP

import cocotb_test.simulator
import pytest

import cocotb
from cocotb.log import SimLog
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer

from cocotbext.axi import AxiStreamBus
from cocotbext.axi import AxiSlave, AxiBus, SparseMemoryRegion
from cocotbext.eth import EthMac
from cocotbext.pcie.core import RootComplex
from cocotbext.pcie.xilinx.us import UltraScalePlusPcieDevice

try:
    import mqnic
except ImportError:
    # attempt import from current directory
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    try:
        import mqnic
    finally:
        del sys.path[0]


class TB(object):

    async def monitor_rx_engine_desc_table_dequeue(self, rx_engine_inst) :
        while True :
            await RisingEdge(rx_engine_inst.desc_table_dequeue_en)
            self.log.info(f"RX Engine Information... Dequeue Update of Descriptor Table[{rx_engine_inst.desc_table_store_queue_ptr}] - Function ID: {rx_engine_inst.desc_table_dequeue_function_id}; RX Completion Queue: {rx_engine_inst.desc_table_dequeue_cpl_queue}")

    async def monitor_rx_engine_desc_table_store(self, rx_engine_inst) :
        while True :
            await RisingEdge(rx_engine_inst.desc_table_store_queue_en)
            self.log.info(f"RX Engine Information... Store Queue Update of Descriptor Table[{rx_engine_inst.desc_table_store_queue_ptr}] - RX Queue: {rx_engine_inst.desc_table_store_queue}; Function ID: {rx_engine_inst.queue_map_resp_function_id};")


    async def monitor_rx_engine_desc_request(self, rx_engine_inst) :
        while True :
            await RisingEdge(rx_engine_inst.m_axis_desc_req_valid)
            self.log.info(f"RX Engine Information...  Descriptor Request to Desc Fetch - m_axis_desc_req_queue: {rx_engine_inst.m_axis_desc_req_queue.value.integer} m_axis_desc_req_tag: {rx_engine_inst.m_axis_desc_req_tag.value.integer}")
            await RisingEdge(rx_engine_inst.s_axis_desc_req_status_valid)
            self.log.info(f"RX Engine Information... Descriptor Request Status from Desc Fetch - s_axis_desc_req_status_queue: {rx_engine_inst.s_axis_desc_req_status_queue.value.integer} s_axis_desc_req_status_ptr: {rx_engine_inst.s_axis_desc_req_status_ptr} s_axis_desc_req_status_cpl: {rx_engine_inst.s_axis_desc_req_status_cpl.value.integer} s_axis_desc_req_status_tag: {rx_engine_inst.s_axis_desc_req_status_tag.value.integer} s_axis_desc_req_status_function_id: {rx_engine_inst.s_axis_desc_req_status_function_id.value.integer} s_axis_desc_req_status_error: {rx_engine_inst.s_axis_desc_req_status_error} s_axis_desc_req_status_empty: {rx_engine_inst.s_axis_desc_req_status_empty}")

    async def monitor_desc_fetch_dma_status(self, desc_fetch_inst) :
        while True :
            await RisingEdge(desc_fetch_inst.m_axis_req_status_valid)
            self.log.info(f"Desc Fetch Information... DMA Status to TX/RX Engine- Queue: {desc_fetch_inst.m_axis_req_status_queue.value.integer} Func ID: {desc_fetch_inst.m_axis_req_status_function_id.value.integer}; Error: {desc_fetch_inst.m_axis_req_status_error}; Empty: {desc_fetch_inst.m_axis_req_status_empty}; CPL Queue: {desc_fetch_inst.m_axis_req_status_cpl.value.integer}")

    async def monitor_desc_fetch_rx_dma_request_to_queue_manager(self, mqnic_interface_inst) :
        while True :
            await RisingEdge(mqnic_interface_inst.rx_desc_dequeue_req_valid)
            self.log.info(f"Desc Fetch Information... RX DMA Request to Queue Manager - Queue: {mqnic_interface_inst.rx_desc_dequeue_req_queue.value.integer}; Tag: {mqnic_interface_inst.rx_desc_dequeue_req_tag.value.integer}")

    async def monitor_desc_fetch_tx_dma_request_to_queue_manager(self, mqnic_interface_inst) :
        while True :
            await RisingEdge(mqnic_interface_inst.tx_desc_dequeue_req_valid)
            self.log.info(f"Desc Fetch Information... TX DMA Request to Queue Manager - Queue: {mqnic_interface_inst.tx_desc_dequeue_req_queue.value.integer}; Tag: {mqnic_interface_inst.tx_desc_dequeue_req_tag.value.integer}")


    async def monitor_desc_fetch_dma_request_to_queue_manager_response(self, desc_fetch_inst) :
        while True :
            await RisingEdge(desc_fetch_inst.s_axis_desc_dequeue_resp_valid)
            self.log.info(f"Desc Fetch Information... DMA Request Response from Queue Manager - Queue: {desc_fetch_inst.s_axis_desc_dequeue_resp_queue.value.integer}; Tag: {desc_fetch_inst.s_axis_desc_dequeue_resp_tag.value.integer}; Function ID {desc_fetch_inst.s_axis_desc_dequeue_resp_function_id.value.integer}; Empty: {desc_fetch_inst.s_axis_desc_dequeue_resp_empty}; Error: {desc_fetch_inst.s_axis_desc_dequeue_resp_error}")

    async def monitor_desc_fetch_dma_read(self, desc_fetch_inst) :
        while True :
            await RisingEdge(desc_fetch_inst.m_axis_dma_read_desc_valid)
            self.log.info(f"Desc Fetch Information... Control to DMA Engine - Addr: {desc_fetch_inst.m_axis_dma_read_desc_dma_addr} Func ID: {desc_fetch_inst.m_axis_dma_read_desc_function_id.value.integer}")


    # async def monitor_pcie_axil_master_tlp_in(self, pcie_axil_master) :
    #     while True :
    #         await RisingEdge(pcie_axil_master.rx_req_tlp_valid)
    #         self.log.info(f"AXIL Master Information... TLP Request in - Data: {pcie_axil_master.rx_req_tlp_data.value.binstr}; HDR: {pcie_axil_master.rx_req_tlp_hdr.value.binstr}; Target Func: {pcie_axil_master.rx_req_tlp_func_num.value.binstr}")

    # async def monitor_pcie_axil_master_tlp_out(self, pcie_axil_master) :
    #     while True :
    #         await RisingEdge(pcie_axil_master.tx_cpl_tlp_valid)
    #         self.log.info(f"AXIL Master Information... TLP Request out - Data: {pcie_axil_master.tx_cpl_tlp_data.value.binstr}; HDR: {pcie_axil_master.tx_cpl_tlp_hdr.value.binstr};")

    # async def monitor_pcie_axil_master_write_out(self, pcie_axil_master) :
    #     while True:
    #         await RisingEdge(pcie_axil_master.m_axil_awvalid)
    #         self.log.info(f"AXIL Master Information... AXIL write out - Addr: {pcie_axil_master.m_axil_awaddr.value.binstr}; User: {pcie_axil_master.m_axil_awuser.value.binstr}; Bvalid: {pcie_axil_master.m_axil_bvalid.value.integer}")
    #         if (pcie_axil_master.m_axil_bvalid.value.integer == 0) :
    #             await RisingEdge(pcie_axil_master.m_axil_bvalid)
    #             self.log.info(f"AXIL Master Information... AXIL Write Input - Bvalid is now raised: {pcie_axil_master.m_axil_bvalid.value.integer}")

    # async def monitor_pcie_axil_master_read_out(self, pcie_axil_master) :
    #     while True:
    #         await RisingEdge(pcie_axil_master.m_axil_arvalid)
    #         self.log.info(f"AXIL Master Information... AXIL read out - Addr: {pcie_axil_master.m_axil_araddr.value.binstr}; User: {pcie_axil_master.m_axil_rvalid.value.binstr}")
    #         if (pcie_axil_master.m_axil_rvalid.value.integer == 0) :
    #             await RisingEdge(pcie_axil_master.m_axil_rvalid)
    #             self.log.info(f"AXIL Master Information... AXIL Write Input - Bvalid is now raised: {pcie_axil_master.m_axil_rvalid.value.integer}")   
    
    # async def monitor_queue_dequeue_request_input(self, queue_manager, type) :
    #     while True :
    #         await RisingEdge(queue_manager.s_axis_dequeue_req_valid)
    #         self.log.info(f"{type} Queue Manager Information... Dequeue Request Input - Queue: {queue_manager.s_axis_dequeue_req_queue.value.integer}; Tag: {queue_manager.s_axis_dequeue_req_tag}")

    # async def monitor_queue_dequeue_request_output(self, queue_manager, type) :
    #     while True :
    #         await RisingEdge(queue_manager.m_axis_dequeue_resp_valid)
    #         self.log.info(f"{type} Queue Manager Information... Dequeue Request Output - Queue: {queue_manager.m_axis_dequeue_resp_queue.value.integer}; Tag: {queue_manager.m_axis_dequeue_resp_op_tag}; Function ID: {queue_manager.m_axis_dequeue_resp_function_id}; Empty: {queue_manager.m_axis_dequeue_resp_empty}; Error: {queue_manager.m_axis_dequeue_resp_error}")

    # async def monitor_queue_axil_write(self, queue_manager, type) :
    #     while True :
    #         await RisingEdge(queue_manager.s_axil_awvalid)
    #         self.log.info(f"{type} Queue Manager Information... AXIL Write Input - Addr: {queue_manager.s_axil_awaddr.value.binstr}; Data: {queue_manager.s_axil_wdata.value} Queue: {queue_manager.s_axil_awaddr_queue}; bvalid: {queue_manager.s_axil_bvalid.value.integer}; Doorbell Queue Reg: {queue_manager.m_axis_doorbell_queue_reg.value.integer}; Doorbell Queue Reg Next: {queue_manager.m_axis_doorbell_queue_next.value.integer}; Pipeline Reg: {queue_manager.queue_ram_addr_pipeline_reg[0]} {queue_manager.queue_ram_addr_pipeline_reg[1]}; Write Pointer: {queue_manager.queue_ram_write_ptr}")
    #         await RisingEdge(queue_manager.clk)
    #         self.log.info(f"{type} Queue Manager Information... AXIL Write Input - Doorbell Queue Reg: {queue_manager.m_axis_doorbell_queue_reg.value.integer}; Doorbell Queue Reg Next: {queue_manager.m_axis_doorbell_queue_next.value.integer}; Pipeline Reg: {queue_manager.queue_ram_addr_pipeline_reg[0]} {queue_manager.queue_ram_addr_pipeline_reg[1]}; Write Pointer: {queue_manager.queue_ram_write_ptr}")
    #         # await RisingEdge(queue_manager.clk)
    #         # self.log.info(f"{type} Queue Manager Information... AXIL Write Input - Doorbell Queue Reg: {queue_manager.m_axis_doorbell_queue_reg.value.integer}; Pipeline Reg: {queue_manager.queue_ram_addr_pipeline_reg};")

    #         if (queue_manager.s_axil_bvalid.value.integer == 0) :
    #             await RisingEdge(queue_manager.s_axil_bvalid)
    #             self.log.info(f"{type} Queue Manager Information... AXIL Write Input - Doorbell Queue Reg: {queue_manager.m_axis_doorbell_queue_reg.value.integer}; Doorbell Queue Reg Next: {queue_manager.m_axis_doorbell_queue_next.value.integer}; Pipeline Reg: {queue_manager.queue_ram_addr_pipeline_reg[0]} {queue_manager.queue_ram_addr_pipeline_reg[1]}; Write Pointer: {queue_manager.queue_ram_write_ptr}")

    #             self.log.info(f"Queue Manager Information... AXIL Write Input - Bvalid is now raised: {queue_manager.s_axil_bvalid.value.integer}")

    # async def monitor_queue_axil_read(self, queue_manager, type) :
    #     while True :
    #         await RisingEdge(queue_manager.s_axil_arvalid)
    #         self.log.info(f"{type} Queue Manager Information... AXIL Read Input - Addr: {queue_manager.s_axil_araddr.value.binstr}; Queue: {queue_manager.s_axil_rvalid.value.integer};")
    #         if (queue_manager.s_axil_rvalid.value.integer == 0) :
    #             await RisingEdge(queue_manager.s_axil_rvalid)
    #             self.log.info(f"Queue Manager Information... AXIL Read Input - Bvalid is now raised: {queue_manager.s_axil_rvalid.value.integer}")

    # async def monitor_queue_doorbell(self, queue_manager, type) :
    #     while True :
    #         await RisingEdge(queue_manager.m_axis_doorbell_valid)
    #         # self.log.info(f"{type} Queue Manager Information... Queue Doorbell Out - Queue: {queue_manager.m_axis_doorbell_queue.value.integer}; Func: {queue_manager.m_axis_doorbell_function_id.value.integer}")
    #         self.log.info(f"{type} Queue Manager Information... Queue Doorbell Out - Queue: {queue_manager.m_axis_doorbell_queue.value.integer}; Reg: {queue_manager.m_axis_doorbell_queue_reg.value.integer}; Next: {queue_manager.m_axis_doorbell_queue_next.value.integer}")


    async def monitor_pcie_msix_irq_request_in(self, msix) :
        while True :
            await RisingEdge(msix.irq_valid)
            self.log.info(f"PCIe MSIx IRQ Information... IRQ Request Input - IRQ {msix.irq_index};")

    async def monitor_pcie_msix_irq_axil_write_in(self, msix) :
        while True: 
            await RisingEdge(msix.s_axil_awvalid)
            self.log.info(f"PCIe MSIx IRQ information... AXIL Write Input - Addr {msix.s_axil_awaddr.value.binstr}; User: {msix.s_axil_awuser.value.binstr}; New Addr: {msix.s_axil_awaddr_index.value.binstr}; Old Addr: {msix.s_axil_awaddr_index_temp}")

    async def monitor_pcie_msix_irq_axil_read_in(self, msix) :
        while True: 
            await RisingEdge(msix.s_axil_arvalid)
            self.log.info(f"PCIe MSIx IRQ information... AXIL Read Input - Addr {msix.s_axil_araddr.value.binstr}; User: {msix.s_axil_aruser.value.binstr}; New Addr: {msix.s_axil_araddr_index.value.binstr} Old Addr: {msix.s_axil_araddr_index_temp}")

    async def monitor_pcie_msix_irq_request_out(self, msix) :
        while True :
            await RisingEdge(msix.tx_wr_req_tlp_valid)
            self.log.info(f"PCIe MSIx IRQ Information... IRQ Request Output - TLP HDR: {msix.tx_wr_req_tlp_hdr.value.binstr}; Data: {msix.tx_wr_req_tlp_data}")

    async def monitor_pcie_msix_irq_request_out_ready(self, msix) :
        while True: 
            await RisingEdge(msix.tx_wr_req_tlp_ready)
            # self.log.info(f"Scott temp: CLOG_NUM_ENTRIES_PER_FUNC: {msix.CLOG_NUM_ENTRIES_PER_FUNC}; NUM_TABLE_ENTRIES: {msix.NUM_TABLE_ENTRIES}; NUM_ENTRIES_PER_FUNC: {msix.NUM_ENTRIES_PER_FUNC}")
            self.log.info(f"PCIe MSIx IRQ Information... IRQ Request Output marked as ready: {msix.tx_wr_req_tlp_ready.value.integer}")

    # async def monitor_pcie_msix_irq_translate

    async def monitor_pcie_if_inst_irq_in(self, pcie_us_if) :
        while True :
            await RisingEdge(pcie_us_if.tx_msix_wr_req_tlp_valid)
            self.log.info(f"PCIe US_IF Information... IRQ request in - HDR: {pcie_us_if.tx_msix_wr_req_tlp_hdr.value.binstr}; TLP Data: {pcie_us_if.tx_msix_wr_req_tlp_data.value.binstr}; Ready: {pcie_us_if.tx_msix_wr_req_tlp_ready}")
            # if pcie_us_if.tx_msix_wr_req_tlp_ready.value.integer == 0 :
            #     await RisingEdge(pcie_us_if.tx_msix_wr_req_tlp_ready)
            #     self.log.info("PCI: it went ready later...")

    async def monitor_pcie_if_inst_irq_out(self, pcie_us_if) :
        while True :
            await RisingEdge(pcie_us_if.cfg_interrupt_msix_int)
            self.log.info(f"PCIe US_IF Information... IRQ request out - Address: {pcie_us_if.cfg_interrupt_msix_address.value.binstr}; Data: {pcie_us_if.cfg_interrupt_msix_data.value.binstr}; Function Number: {pcie_us_if.cfg_interrupt_msi_function_number_msix.value.integer}")


    # async def monitor_scheduler_doorbell_in(self, scheduler) :
    #     while True :
    #         await RisingEdge(scheduler.s_axis_doorbell_valid)
    #         self.log.info(f"Scheduler Information.... Doorbell in - Queue: {scheduler.s_axis_doorbell_queue}")
   
    # async def monitor_scheduler_transmit_request(self, scheduler) :
    #     while True:
    #         await RisingEdge(scheduler.m_axis_tx_req_valid)
    #         self.log.info(f"Scheduler Information... Transmit Request - Queue: {scheduler.m_axis_tx_req_queue}")

    # async def monitor_scheduler_internal_fifo_out(self, scheduler) :
    #     while True :
    #         await RisingEdge(scheduler.axis_doorbell_fifo_valid)
    #         self.log.info(f"Scheduler Information... Internal FIFO Out - Queue: {scheduler.axis_doorbell_fifo_queue}")

    # async def monitor_scheduler_internal_fifo_in(self, scheduler) :
    #     while True :
    #         await RisingEdge(scheduler.s_axis_doorbell_valid)
    #         self.log.info(f"Scheduler Information... Internal FIFO In - Queue: {scheduler.s_axis_doorbell_queue}")


    def __init__(self, dut, msix_count=32):
        self.dut = dut

        self.log = SimLog("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        for iface in self.dut.core_pcie_inst.core_inst.iface:
            cocotb.start_soon(self.monitor_rx_engine_desc_table_dequeue(iface.interface_inst.interface_rx_inst.rx_engine_inst))
            cocotb.start_soon(self.monitor_rx_engine_desc_table_store(iface.interface_inst.interface_rx_inst.rx_engine_inst))

            cocotb.start_soon(self.monitor_rx_engine_desc_request(iface.interface_inst.interface_rx_inst.rx_engine_inst))

        # for iface in self.dut.core_pcie_inst.core_inst.iface :
        #     cocotb.start_soon(self.monitor_desc_fetch_dma_read(iface.interface_inst.desc_fetch_inst))
        #     cocotb.start_soon(self.monitor_desc_fetch_dma_status(iface.interface_inst.desc_fetch_inst))
        #     cocotb.start_soon(self.monitor_desc_fetch_rx_dma_request_to_queue_manager(iface.interface_inst))
        #     cocotb.start_soon(self.monitor_desc_fetch_tx_dma_request_to_queue_manager(iface.interface_inst))

        #     cocotb.start_soon(self.monitor_desc_fetch_dma_request_to_queue_manager_response(iface.interface_inst.desc_fetch_inst))

            # for sched in iface.interface_inst.sched :
            #     cocotb.start_soon(self.monitor_scheduler_doorbell_in(sched.scheduler_block))
            #     cocotb.start_soon(self.monitor_scheduler_transmit_request(sched.scheduler_block))
            #     cocotb.start_soon(self.monitor_scheduler_internal_fifo_in(sched.scheduler_block.tx_scheduler_inst))
            #     cocotb.start_soon(self.monitor_scheduler_internal_fifo_out(sched.scheduler_block.tx_scheduler_inst))

        # for iface in self.dut.core_pcie_inst.core_inst.iface :
            # cocotb.start_soon(self.monitor_queue_dequeue_request_output(iface.interface_inst.rx_qm_inst, "RX"))
#            cocotb.start_soon(self.monitor_queue_dequeue_request_input(iface.interface_inst.rx_qm_inst, "RX"))
            # cocotb.start_soon(self.monitor_queue_dequeue_request_output(iface.interface_inst.tx_qm_inst, "TX"))
            # cocotb.start_soon(self.monitor_queue_dequeue_request_input(iface.interface_inst.tx_qm_inst, "TX"))

            # cocotb.start_soon(self.monitor_queue_axil_write(iface.interface_inst.rx_qm_inst, "RX"))
            # cocotb.start_soon(self.monitor_queue_axil_read(iface.interface_inst.rx_qm_inst, "RX"))
            # cocotb.start_soon(self.monitor_queue_doorbell(iface.interface_inst.rx_qm_inst, "RX"))

            # cocotb.start_soon(self.monitor_queue_axil_write(iface.interface_inst.tx_qm_inst, "TX"))
            # cocotb.start_soon(self.monitor_queue_axil_read(iface.interface_inst.tx_qm_inst, "TX"))
            # cocotb.start_soon(self.monitor_queue_doorbell(iface.interface_inst.tx_qm_inst, "TX"))



        # cocotb.start_soon(self.monitor_pcie_msix_irq_request_in(self.dut.core_pcie_inst.pcie_msix_inst))
        # cocotb.start_soon(self.monitor_pcie_msix_irq_request_out(self.dut.core_pcie_inst.pcie_msix_inst))
        # cocotb.start_soon(self.monitor_pcie_msix_irq_request_out_ready(self.dut.core_pcie_inst.pcie_msix_inst))
        # cocotb.start_soon(self.monitor_pcie_msix_irq_axil_write_in(self.dut.core_pcie_inst.pcie_msix_inst))
        # cocotb.start_soon(self.monitor_pcie_msix_irq_axil_read_in(self.dut.core_pcie_inst.pcie_msix_inst))

        # cocotb.start_soon(self.monitor_pcie_if_inst_irq_in(self.dut.pcie_if_inst))
        # cocotb.start_soon(self.monitor_pcie_if_inst_irq_out(self.dut.pcie_if_inst))

        # cocotb.start_soon(self.monitor_pcie_axil_master_tlp_in(self.dut.core_pcie_inst.pcie_axil_master_inst))
        # cocotb.start_soon(self.monitor_pcie_axil_master_tlp_out(self.dut.core_pcie_inst.pcie_axil_master_inst))
        # cocotb.start_soon(self.monitor_pcie_axil_master_write_out(self.dut.core_pcie_inst.pcie_axil_master_inst))
        # cocotb.start_soon(self.monitor_pcie_axil_master_read_out(self.dut.core_pcie_inst.pcie_axil_master_inst))


        # PCIe
        self.rc = RootComplex()

        self.rc.max_payload_size = 0x1  # 256 bytes
        self.rc.max_read_request_size = 0x2  # 512 bytes

        self.dev = UltraScalePlusPcieDevice(
            # configuration options
            pcie_generation=3,
            # pcie_link_width=16,
            user_clk_frequency=250e6,
            alignment="dword",
            cq_straddle=len(dut.pcie_if_inst.pcie_us_if_cq_inst.rx_req_tlp_valid_reg) > 1,
            cc_straddle=len(dut.pcie_if_inst.pcie_us_if_cc_inst.out_tlp_valid) > 1,
            rq_straddle=len(dut.pcie_if_inst.pcie_us_if_rq_inst.out_tlp_valid) > 1,
            rc_straddle=len(dut.pcie_if_inst.pcie_us_if_rc_inst.rx_cpl_tlp_valid_reg) > 1,
            rc_4tlp_straddle=len(dut.pcie_if_inst.pcie_us_if_rc_inst.rx_cpl_tlp_valid_reg) > 2,
            pf_count=1,
            max_payload_size=1024,
            enable_client_tag=True,
            enable_extended_tag=True,
            enable_parity=False,
            enable_rx_msg_interface=False,
            enable_sriov=False,
            enable_extended_configuration=False,

            pf0_msi_enable=False,
            pf0_msi_count=32,
            pf1_msi_enable=False,
            pf1_msi_count=1,
            pf2_msi_enable=False,
            pf2_msi_count=1,
            pf3_msi_enable=False,
            pf3_msi_count=1,
            pf0_msix_enable=True,
            pf0_msix_table_size=msix_count-1,
            pf0_msix_table_bir=0,
            pf0_msix_table_offset=0x00010000,
            pf0_msix_pba_bir=0,
            pf0_msix_pba_offset=0x00018000,
            pf1_msix_enable=False,
            pf1_msix_table_size=0,
            pf1_msix_table_bir=0,
            pf1_msix_table_offset=0x00000000,
            pf1_msix_pba_bir=0,
            pf1_msix_pba_offset=0x00000000,
            pf2_msix_enable=False,
            pf2_msix_table_size=0,
            pf2_msix_table_bir=0,
            pf2_msix_table_offset=0x00000000,
            pf2_msix_pba_bir=0,
            pf2_msix_pba_offset=0x00000000,
            pf3_msix_enable=False,
            pf3_msix_table_size=0,
            pf3_msix_table_bir=0,
            pf3_msix_table_offset=0x00000000,
            pf3_msix_pba_bir=0,
            pf3_msix_pba_offset=0x00000000,

            # signals
            # Clock and Reset Interface
            user_clk=dut.clk,
            user_reset=dut.rst,
            # user_lnk_up
            # sys_clk
            # sys_clk_gt
            # sys_reset
            # phy_rdy_out

            # Requester reQuest Interface
            rq_bus=AxiStreamBus.from_prefix(dut, "m_axis_rq"),
            pcie_rq_seq_num0=dut.s_axis_rq_seq_num_0,
            pcie_rq_seq_num_vld0=dut.s_axis_rq_seq_num_valid_0,
            pcie_rq_seq_num1=dut.s_axis_rq_seq_num_1,
            pcie_rq_seq_num_vld1=dut.s_axis_rq_seq_num_valid_1,
            # pcie_rq_tag0
            # pcie_rq_tag1
            # pcie_rq_tag_av
            # pcie_rq_tag_vld0
            # pcie_rq_tag_vld1

            # Requester Completion Interface
            rc_bus=AxiStreamBus.from_prefix(dut, "s_axis_rc"),

            # Completer reQuest Interface
            cq_bus=AxiStreamBus.from_prefix(dut, "s_axis_cq"),
            # pcie_cq_np_req
            # pcie_cq_np_req_count

            # Completer Completion Interface
            cc_bus=AxiStreamBus.from_prefix(dut, "m_axis_cc"),

            # Transmit Flow Control Interface
            # pcie_tfc_nph_av=dut.pcie_tfc_nph_av,
            # pcie_tfc_npd_av=dut.pcie_tfc_npd_av,

            # Configuration Management Interface
            cfg_mgmt_addr=dut.cfg_mgmt_addr,
            cfg_mgmt_function_number=dut.cfg_mgmt_function_number,
            cfg_mgmt_write=dut.cfg_mgmt_write,
            cfg_mgmt_write_data=dut.cfg_mgmt_write_data,
            cfg_mgmt_byte_enable=dut.cfg_mgmt_byte_enable,
            cfg_mgmt_read=dut.cfg_mgmt_read,
            cfg_mgmt_read_data=dut.cfg_mgmt_read_data,
            cfg_mgmt_read_write_done=dut.cfg_mgmt_read_write_done,
            # cfg_mgmt_debug_access

            # Configuration Status Interface
            # cfg_phy_link_down
            # cfg_phy_link_status
            # cfg_negotiated_width
            # cfg_current_speed
            cfg_max_payload=dut.cfg_max_payload,
            cfg_max_read_req=dut.cfg_max_read_req,
            # cfg_function_status
            # cfg_vf_status
            # cfg_function_power_state
            # cfg_vf_power_state
            # cfg_link_power_state
            # cfg_err_cor_out
            # cfg_err_nonfatal_out
            # cfg_err_fatal_out
            # cfg_local_error_out
            # cfg_local_error_valid
            # cfg_rx_pm_state
            # cfg_tx_pm_state
            # cfg_ltssm_state
            cfg_rcb_status=dut.cfg_rcb_status,
            # cfg_obff_enable
            # cfg_pl_status_change
            # cfg_tph_requester_enable
            # cfg_tph_st_mode
            # cfg_vf_tph_requester_enable
            # cfg_vf_tph_st_mode

            # Configuration Received Message Interface
            # cfg_msg_received
            # cfg_msg_received_data
            # cfg_msg_received_type

            # Configuration Transmit Message Interface
            # cfg_msg_transmit
            # cfg_msg_transmit_type
            # cfg_msg_transmit_data
            # cfg_msg_transmit_done

            # Configuration Flow Control Interface
            cfg_fc_ph=dut.cfg_fc_ph,
            cfg_fc_pd=dut.cfg_fc_pd,
            cfg_fc_nph=dut.cfg_fc_nph,
            cfg_fc_npd=dut.cfg_fc_npd,
            cfg_fc_cplh=dut.cfg_fc_cplh,
            cfg_fc_cpld=dut.cfg_fc_cpld,
            cfg_fc_sel=dut.cfg_fc_sel,

            # Configuration Control Interface
            # cfg_hot_reset_in
            # cfg_hot_reset_out
            # cfg_config_space_enable
            # cfg_dsn
            # cfg_bus_number
            # cfg_ds_port_number
            # cfg_ds_bus_number
            # cfg_ds_device_number
            # cfg_ds_function_number
            # cfg_power_state_change_ack
            # cfg_power_state_change_interrupt
            cfg_err_cor_in=dut.status_error_cor,
            cfg_err_uncor_in=dut.status_error_uncor,
            # cfg_flr_in_process
            # cfg_flr_done
            # cfg_vf_flr_in_process
            # cfg_vf_flr_func_num
            # cfg_vf_flr_done
            # cfg_pm_aspm_l1_entry_reject
            # cfg_pm_aspm_tx_l0s_entry_disable
            # cfg_req_pm_transition_l23_ready
            # cfg_link_training_enable

            # Configuration Interrupt Controller Interface
            # cfg_interrupt_int
            # cfg_interrupt_sent
            # cfg_interrupt_pending
            # cfg_interrupt_msi_enable
            # cfg_interrupt_msi_mmenable
            # cfg_interrupt_msi_mask_update
            # cfg_interrupt_msi_data
            # cfg_interrupt_msi_select
            # cfg_interrupt_msi_int
            # cfg_interrupt_msi_pending_status
            # cfg_interrupt_msi_pending_status_data_enable
            # cfg_interrupt_msi_pending_status_function_num
            # cfg_interrupt_msi_sent
            # cfg_interrupt_msi_fail
            cfg_interrupt_msix_enable=dut.cfg_interrupt_msix_enable,
            cfg_interrupt_msix_mask=dut.cfg_interrupt_msix_mask,
            cfg_interrupt_msix_vf_enable=dut.cfg_interrupt_msix_vf_enable,
            cfg_interrupt_msix_vf_mask=dut.cfg_interrupt_msix_vf_mask,
            cfg_interrupt_msix_address=dut.cfg_interrupt_msix_address,
            cfg_interrupt_msix_data=dut.cfg_interrupt_msix_data,
            cfg_interrupt_msix_int=dut.cfg_interrupt_msix_int,
            cfg_interrupt_msix_vec_pending=dut.cfg_interrupt_msix_vec_pending,
            cfg_interrupt_msix_vec_pending_status=dut.cfg_interrupt_msix_vec_pending_status,
            cfg_interrupt_msix_sent=dut.cfg_interrupt_msix_sent,
            cfg_interrupt_msix_fail=dut.cfg_interrupt_msix_fail,
            # cfg_interrupt_msi_attr
            # cfg_interrupt_msi_tph_present
            # cfg_interrupt_msi_tph_type
            # cfg_interrupt_msi_tph_st_tag
            cfg_interrupt_msi_function_number=dut.cfg_interrupt_msi_function_number,

            # Configuration Extend Interface
            # cfg_ext_read_received
            # cfg_ext_write_received
            # cfg_ext_register_number
            # cfg_ext_function_number
            # cfg_ext_write_data
            # cfg_ext_write_byte_enable
            # cfg_ext_read_data
            # cfg_ext_read_data_valid
        )

        # self.dev.log.setLevel(logging.DEBUG)

        self.rc.make_port().connect(self.dev)

        self.driver = mqnic.Driver()

        self.dev.functions[0].configure_bar(0, 2**len(dut.core_pcie_inst.axil_ctrl_araddr), ext=True, prefetch=True)
        if hasattr(dut.core_pcie_inst, 'pcie_app_ctrl'):
            self.dev.functions[0].configure_bar(2, 2**len(dut.core_pcie_inst.axil_app_ctrl_araddr), ext=True, prefetch=True)

        core_inst = dut.core_pcie_inst.core_inst

        # Ethernet
        self.port_mac = []

        eth_int_if_width = len(core_inst.m_axis_tx_tdata) / len(core_inst.m_axis_tx_tvalid)
        eth_clock_period = 6.4
        eth_speed = 10e9

        if eth_int_if_width == 64:
            # 10G
            eth_clock_period = 6.4
            eth_speed = 10e9
        elif eth_int_if_width == 128:
            # 25G
            eth_clock_period = 2.56
            eth_speed = 25e9
        elif eth_int_if_width == 512:
            # 100G
            eth_clock_period = 3.102
            eth_speed = 100e9

        for iface in core_inst.iface:
            for k in range(len(iface.port)):
                cocotb.start_soon(Clock(iface.port[k].port_rx_clk, eth_clock_period, units="ns").start())
                cocotb.start_soon(Clock(iface.port[k].port_tx_clk, eth_clock_period, units="ns").start())

                iface.port[k].port_rx_rst.setimmediatevalue(0)
                iface.port[k].port_tx_rst.setimmediatevalue(0)

                mac = EthMac(
                    tx_clk=iface.port[k].port_tx_clk,
                    tx_rst=iface.port[k].port_tx_rst,
                    tx_bus=AxiStreamBus.from_prefix(iface.interface_inst.port[k].port_inst.port_tx_inst, "m_axis_tx"),
                    tx_ptp_time=iface.port[k].port_tx_ptp_ts_tod,
                    tx_ptp_ts=iface.interface_inst.port[k].port_inst.port_tx_inst.s_axis_tx_cpl_ts,
                    tx_ptp_ts_tag=iface.interface_inst.port[k].port_inst.port_tx_inst.s_axis_tx_cpl_tag,
                    tx_ptp_ts_valid=iface.interface_inst.port[k].port_inst.port_tx_inst.s_axis_tx_cpl_valid,
                    rx_clk=iface.port[k].port_rx_clk,
                    rx_rst=iface.port[k].port_rx_rst,
                    rx_bus=AxiStreamBus.from_prefix(iface.interface_inst.port[k].port_inst.port_rx_inst, "s_axis_rx"),
                    rx_ptp_time=iface.port[k].port_rx_ptp_ts_tod,
                    ifg=12, speed=eth_speed
                )

                self.port_mac.append(mac)

        dut.eth_tx_status.setimmediatevalue(2**len(core_inst.m_axis_tx_tvalid)-1)
        dut.eth_tx_fc_quanta_clk_en.setimmediatevalue(2**len(core_inst.m_axis_tx_tvalid)-1)
        dut.eth_rx_status.setimmediatevalue(2**len(core_inst.m_axis_tx_tvalid)-1)
        dut.eth_rx_lfc_req.setimmediatevalue(0)
        dut.eth_rx_pfc_req.setimmediatevalue(0)
        dut.eth_rx_fc_quanta_clk_en.setimmediatevalue(2**len(core_inst.m_axis_tx_tvalid)-1)

        # DDR
        self.ddr_group_size = core_inst.DDR_GROUP_SIZE.value
        self.ddr_ram = []
        self.ddr_axi_if = []
        if hasattr(core_inst, 'ddr'):
            ram = None
            for i, ch in enumerate(core_inst.ddr.dram_if_inst.ch):
                cocotb.start_soon(Clock(ch.ch_clk, 3.332, units="ns").start())
                ch.ch_rst.setimmediatevalue(0)
                ch.ch_status.setimmediatevalue(1)

                if i % self.ddr_group_size == 0:
                    ram = SparseMemoryRegion()
                    self.ddr_ram.append(ram)
                self.ddr_axi_if.append(AxiSlave(AxiBus.from_prefix(ch, "axi_ch"), ch.ch_clk, ch.ch_rst, target=ram))

        # HBM
        self.hbm_group_size = core_inst.HBM_GROUP_SIZE.value
        self.hbm_ram = []
        self.hbm_axi_if = []
        if hasattr(core_inst, 'hbm'):
            ram = None
            for i, ch in enumerate(core_inst.hbm.dram_if_inst.ch):
                cocotb.start_soon(Clock(ch.ch_clk, 2.222, units="ns").start())
                ch.ch_rst.setimmediatevalue(0)
                ch.ch_status.setimmediatevalue(1)

                if i % self.hbm_group_size == 0:
                    ram = SparseMemoryRegion()
                    self.hbm_ram.append(ram)
                self.hbm_axi_if.append(AxiSlave(AxiBus.from_prefix(ch, "axi_ch"), ch.ch_clk, ch.ch_rst, target=ram))

        dut.ctrl_reg_wr_wait.setimmediatevalue(0)
        dut.ctrl_reg_wr_ack.setimmediatevalue(0)
        dut.ctrl_reg_rd_data.setimmediatevalue(0)
        dut.ctrl_reg_rd_wait.setimmediatevalue(0)
        dut.ctrl_reg_rd_ack.setimmediatevalue(0)

        cocotb.start_soon(Clock(dut.ptp_clk, 6.4, units="ns").start())
        dut.ptp_rst.setimmediatevalue(0)
        cocotb.start_soon(Clock(dut.ptp_sample_clk, 8, units="ns").start())

        dut.s_axis_stat_tdata.setimmediatevalue(0)
        dut.s_axis_stat_tid.setimmediatevalue(0)
        dut.s_axis_stat_tvalid.setimmediatevalue(0)

        self.loopback_enable = False
        cocotb.start_soon(self._run_loopback())

    async def init(self):

        for mac in self.port_mac:
            mac.rx.reset.setimmediatevalue(0)
            mac.tx.reset.setimmediatevalue(0)

        self.dut.ptp_rst.setimmediatevalue(0)

        for ram in self.ddr_axi_if + self.ddr_axi_if:
            ram.write_if.reset.setimmediatevalue(0)

        await RisingEdge(self.dut.clk)
        await RisingEdge(self.dut.clk)

        for mac in self.port_mac:
            mac.rx.reset.setimmediatevalue(1)
            mac.tx.reset.setimmediatevalue(1)

        self.dut.ptp_rst.setimmediatevalue(1)

        for ram in self.ddr_axi_if + self.ddr_axi_if:
            ram.write_if.reset.setimmediatevalue(1)
        await FallingEdge(self.dut.rst)
        await Timer(100, 'ns')

        await RisingEdge(self.dut.clk)
        await RisingEdge(self.dut.clk)

        for mac in self.port_mac:
            mac.rx.reset.setimmediatevalue(0)
            mac.tx.reset.setimmediatevalue(0)

        self.dut.ptp_rst.setimmediatevalue(0)

        for ram in self.ddr_axi_if + self.ddr_axi_if:
            ram.write_if.reset.setimmediatevalue(0)

        await self.rc.enumerate()

    async def _run_loopback(self):
        while True:
            await RisingEdge(self.dut.clk)

            if self.loopback_enable:
                for mac in self.port_mac:
                    if not mac.tx.empty():
                        await mac.rx.send(await mac.tx.recv())


@cocotb.test()
async def run_test_nic(dut):


    tb = TB(dut, msix_count=2**len(dut.core_pcie_inst.irq_index))

    # tb.log.info(f"Scott: {len(dut.core_pcie_inst.irq_index)}")
    # exit(0)
    await tb.init()

    tb.log.info("Init driver")
    await tb.driver.init_pcie_dev(tb.rc.find_device(tb.dev.functions[0].pcie_id))
    for interface in tb.driver.interfaces:
        await interface.open()

    # enable queues
    tb.log.info("Enable queues")
    for interface in tb.driver.interfaces:
        await interface.sched_blocks[0].schedulers[0].rb.write_dword(mqnic.MQNIC_RB_SCHED_RR_REG_CTRL, 0x00000001)
        for k in range(len(interface.txq)):
            await interface.sched_blocks[0].schedulers[0].hw_regs.write_dword(4*k, 0x00000003)

    # wait for all writes to complete
    await tb.driver.hw_regs.read_dword(0)
    tb.log.info("Init complete")

    tb.log.info("Send and receive single packet")

    for interface in tb.driver.interfaces:
        payload = bytes([x % 256 for x in range(256)])
        eth = Ether(src='5A:51:52:53:54:55', dst='DA:D1:D2:D3:D4:00')
        ip = IP(src='192.168.1.100', dst='192.168.1.101')
        udp = UDP(sport=1, dport=0)
        test_pkt = eth / ip / udp / payload
        
        await interface.start_xmit(test_pkt, 0)
        tb.log.info("Successfully triggered xmit")

        pkt = await tb.port_mac[interface.index*interface.port_count].tx.recv()
        tb.log.info("Out of QSFP Packet: %s", pkt)

        await tb.port_mac[interface.index*interface.port_count].rx.send(pkt)

        pkt = await interface.recv()

        tb.log.info(f"Received Packet on Queue {pkt.queue}")
        if interface.if_feature_rx_csum:
            assert pkt.rx_checksum == ~scapy.utils.checksum(bytes(pkt.data[14:])) & 0xffff

        # return

    tb.log.info("RX and TX checksum tests")

    payload = bytes([x % 256 for x in range(256)])
    eth = Ether(src='5A:51:52:53:54:55', dst='DA:D1:D2:D3:D4:00')
    ip = IP(src='192.168.1.100', dst='192.168.1.101')
    udp = UDP(sport=1, dport=2)
    test_pkt = eth / ip / udp / payload

    if tb.driver.interfaces[0].if_feature_tx_csum:
        test_pkt2 = test_pkt.copy()
        test_pkt2[UDP].chksum = scapy.utils.checksum(bytes(test_pkt2[UDP]))

        await tb.driver.interfaces[0].start_xmit(test_pkt2.build(), 0, 34, 6)
    else:
        await tb.driver.interfaces[0].start_xmit(test_pkt.build(), 0)

    pkt = await tb.port_mac[0].tx.recv()
    tb.log.info(f"Packet Received and resent through design")

    await tb.port_mac[0].rx.send(pkt)

    pkt = await tb.driver.interfaces[0].recv()

    tb.log.info(f"Packet Received")
    if tb.driver.interfaces[0].if_feature_rx_csum:
        assert pkt.rx_checksum == ~scapy.utils.checksum(bytes(pkt.data[14:])) & 0xffff
    assert Ether(pkt.data).build() == test_pkt.build()

    # tb.log.info("Queue mapping offset test")


    # tb.loopback_enable = True

    # for k in range(4):
    #     payload = bytes([x % 256 for x in range(256)])
    #     eth = Ether(src='5A:51:52:53:54:55', dst='DA:D1:D2:D3:D4:00')
    #     ip = IP(src='192.168.1.100', dst='192.168.1.101')
    #     udp = UDP(sport=1, dport=k+0)
    #     test_pkt = eth / ip / udp / payload
            
    #     await tb.driver.interfaces[0].set_rx_queue_map_indir_table(0, 0, k)

    #     await tb.driver.interfaces[0].start_xmit(test_pkt, 0)

    #     pkt = await tb.driver.interfaces[0].recv()

    #     tb.log.info("Packet: %s", pkt)
    #     if tb.driver.interfaces[0].if_feature_rx_csum:
    #         assert pkt.rx_checksum == ~scapy.utils.checksum(bytes(pkt.data[14:])) & 0xffff
    #     assert pkt.queue == k

    # tb.loopback_enable = False

    # await tb.driver.interfaces[0].set_rx_queue_map_indir_table(0, 0, 0)

    # if tb.driver.interfaces[0].if_feature_rss:
    #     tb.log.info("Queue mapping RSS mask test")

    #     await tb.driver.interfaces[0].set_rx_queue_map_rss_mask(0, 0x00000003)

    #     for k in range(4):
    #         await tb.driver.interfaces[0].set_rx_queue_map_indir_table(0, k, k)

    #     tb.loopback_enable = True

    #     queues = set()

    #     for k in range(64):
    #         payload = bytes([x % 256 for x in range(256)])
    #         eth = Ether(src='5A:51:52:53:54:55', dst='DA:D1:D2:D3:D4:00')
    #         ip = IP(src='192.168.1.100', dst='192.168.1.101')
    #         udp = UDP(sport=1, dport=k+0)
    #         test_pkt = eth / ip / udp / payload

    #         if tb.driver.interfaces[0].if_feature_tx_csum:
    #             test_pkt2 = test_pkt.copy()
    #             test_pkt2[UDP].chksum = scapy.utils.checksum(bytes(test_pkt2[UDP]))

    #             await tb.driver.interfaces[0].start_xmit(test_pkt2.build(), 0, 34, 6)
    #         else:
    #             await tb.driver.interfaces[0].start_xmit(test_pkt.build(), 0)

    #     for k in range(64):
    #         pkt = await tb.driver.interfaces[0].recv()

    #         tb.log.info("Packet: %s", pkt)
    #         if tb.driver.interfaces[0].if_feature_rx_csum:
    #             assert pkt.rx_checksum == ~scapy.utils.checksum(bytes(pkt.data[14:])) & 0xffff

    #         queues.add(pkt.queue)

    #     assert len(queues) == 4

    #     tb.loopback_enable = False

    #     await tb.driver.interfaces[0].set_rx_queue_map_rss_mask(0, 0)

    tb.log.info("Multiple small packets")

    count = 64

    pkts = []
    for i in range(0, count) :
        payload = bytes([x % 256 for x in range(256)])
        eth = Ether(src='5A:51:52:53:54:55', dst='DA:D1:D2:D3:D4:00')
        ip = IP(src=f'192.168.1.{i}', dst='192.168.1.101')
        udp = UDP(sport=1, dport=0)
        test_pkt = eth / ip / udp / payload

        pkts.append(test_pkt)
        
    tb.loopback_enable = True

    my_counter = 0
    for p in pkts:
        my_counter += 1
        await tb.driver.interfaces[0].start_xmit(p, 0)
        tb.log.info(f"Packet {my_counter} Sent")


    for k in range(count):
        pkt = await tb.driver.interfaces[0].recv()

        tb.log.info(f"Packet {k} received on queue {pkt.queue}")
        # assert pkt.data == pkts[k]
        if tb.driver.interfaces[0].if_feature_rx_csum:
            assert pkt.rx_checksum == ~scapy.utils.checksum(bytes(pkt.data[14:])) & 0xffff

    tb.loopback_enable = False

    tb.log.info("Multiple TX queues")

    count = 64

    pkts = []

    for k in range(count) :
        payload = bytes([x % 256 for x in range(256)])
        eth = Ether(src='5A:51:52:53:54:55', dst='DA:D1:D2:D3:D4:00')
        ip = IP(src='192.168.1.100', dst='192.168.1.101')
        udp = UDP(sport=1, dport=k+0)
        test_pkt = eth / ip / udp / payload
        pkts.append(test_pkt)

    tb.loopback_enable = True

    for k in range(len(pkts)):
        tb.log.info(f"Sent Packet ({k}): to Queue {k % len(tb.driver.interfaces[0].txq)}")
        await tb.driver.interfaces[0].start_xmit(pkts[k], k % len(tb.driver.interfaces[0].txq))

    for k in range(count):
        pkt = await tb.driver.interfaces[0].recv()

        tb.log.info(f"Packet ({k}) in Queue ({pkt.queue})")
        if tb.driver.interfaces[0].if_feature_rx_csum:
            assert pkt.rx_checksum == ~scapy.utils.checksum(bytes(pkt.data[14:])) & 0xffff

    tb.loopback_enable = False

    tb.log.info("Multiple large packets")

    count = 24

    tb.loopback_enable = True

    for k in range(count):
        payload = bytes([x % 256 for x in range(8700)])
        eth = Ether(src='5A:51:52:53:54:55', dst='DA:D1:D2:D3:D4:00')
        ip = IP(src='192.168.1.100', dst='192.168.1.101')
        udp = UDP(sport=1, dport=k+0)
        test_pkt = eth / ip / udp / payload
        
        await tb.driver.interfaces[0].start_xmit(test_pkt, 0)

        pkt = await tb.driver.interfaces[0].recv()

        tb.log.info("Packet in: %s; Packet out: %s", test_pkt, pkt)

    # if len(tb.driver.interfaces[0].sched_blocks) > 1:
    #     tb.log.info("All interface 0 scheduler blocks")

    #     for block in tb.driver.interfaces[0].sched_blocks:
    #         await block.schedulers[0].rb.write_dword(mqnic.MQNIC_RB_SCHED_RR_REG_CTRL, 0x00000001)
    #         await block.interface.set_rx_queue_map_indir_table(block.index, 0, block.index)
    #         for k in range(len(block.interface.txq)):
    #             if k % len(block.interface.sched_blocks) == block.index:
    #                 await block.schedulers[0].hw_regs.write_dword(4*k, 0x00000003)
    #             else:
    #                 await block.schedulers[0].hw_regs.write_dword(4*k, 0x00000000)

    #         await block.interface.ports[block.index].set_tx_ctrl(mqnic.MQNIC_PORT_TX_CTRL_EN)
    #         await block.interface.ports[block.index].set_rx_ctrl(mqnic.MQNIC_PORT_RX_CTRL_EN)

    #     count = 64

    #     pkts = [bytearray([(x+k) % 256 for x in range(1514)]) for k in range(count)]

    #     tb.loopback_enable = True

    #     queues = set()

    #     for k, p in enumerate(pkts):
    #         await tb.driver.interfaces[0].start_xmit(p, k % len(tb.driver.interfaces[0].sched_blocks))

    #     for k in range(count):
    #         pkt = await tb.driver.interfaces[0].recv()

    #         tb.log.info("Packet: %s", pkt)
    #         # assert pkt.data == pkts[k]
    #         if tb.driver.interfaces[0].if_feature_rx_csum:
    #             assert pkt.rx_checksum == ~scapy.utils.checksum(bytes(pkt.data[14:])) & 0xffff

    #         queues.add(pkt.queue)

    #     assert len(queues) == len(tb.driver.interfaces[0].sched_blocks)

    #     tb.loopback_enable = False

    #     for block in tb.driver.interfaces[0].sched_blocks[1:]:
    #         await block.schedulers[0].rb.write_dword(mqnic.MQNIC_RB_SCHED_RR_REG_CTRL, 0x00000000)
    #         await tb.driver.interfaces[0].set_rx_queue_map_indir_table(block.index, 0, 0)

    # if tb.driver.interfaces[0].if_feature_lfc:
    #     tb.log.info("Test LFC pause frame RX")

    #     await tb.driver.interfaces[0].ports[0].set_lfc_ctrl(mqnic.MQNIC_PORT_LFC_CTRL_TX_LFC_EN | mqnic.MQNIC_PORT_LFC_CTRL_RX_LFC_EN)
    #     await tb.driver.hw_regs.read_dword(0)

    #     lfc_xoff = Ether(src='DA:D1:D2:D3:D4:D5', dst='01:80:C2:00:00:01', type=0x8808) / struct.pack('!HH', 0x0001, 2000)

    #     await tb.port_mac[0].rx.send(bytes(lfc_xoff))

    #     count = 16

    #     pkts = [bytearray([(x+k) % 256 for x in range(1514)]) for k in range(count)]

    #     tb.loopback_enable = True

    #     for p in pkts:
    #         await tb.driver.interfaces[0].start_xmit(p, 0)

    #     for k in range(count):
    #         pkt = await tb.driver.interfaces[0].recv()

    #         tb.log.info("Packet: %s", pkt)
    #         assert pkt.data == pkts[k]
    #         if tb.driver.interfaces[0].if_feature_rx_csum:
    #             assert pkt.rx_checksum == ~scapy.utils.checksum(bytes(pkt.data[14:])) & 0xffff

    #     tb.loopback_enable = False

    # tb.log.info("Read statistics counters")

    # await Timer(2000, 'ns')

    # lst = []

    # for k in range(64):
    #     lst.append(await tb.driver.hw_regs.read_dword(0x020000+k*8))

    # print(lst)

    # await RisingEdge(dut.clk)
    # await RisingEdge(dut.clk)


# cocotb-test

tests_dir = os.path.dirname(__file__)
rtl_dir = os.path.abspath(os.path.join(tests_dir, '..', '..', 'rtl'))
lib_dir = os.path.abspath(os.path.join(rtl_dir, '..', 'lib'))
axi_rtl_dir = os.path.abspath(os.path.join(lib_dir, 'axi', 'rtl'))
axis_rtl_dir = os.path.abspath(os.path.join(lib_dir, 'axis', 'rtl'))
eth_rtl_dir = os.path.abspath(os.path.join(lib_dir, 'eth', 'rtl'))
pcie_rtl_dir = os.path.abspath(os.path.join(lib_dir, 'pcie', 'rtl'))


@pytest.mark.parametrize(("if_count", "ports_per_if", "axis_pcie_data_width",
        "axis_eth_data_width", "axis_eth_sync_data_width", "ptp_ts_enable"), [
            (1, 1, 256, 64, 64, 1),
            (1, 1, 256, 64, 64, 0),
            (2, 1, 256, 64, 64, 1),
            (1, 2, 256, 64, 64, 1),
            (1, 1, 256, 64, 128, 1),
            (1, 1, 512, 64, 64, 1),
            (1, 1, 512, 64, 128, 1),
            (1, 1, 512, 512, 512, 1),
        ])
def test_mqnic_core_pcie_us(request, if_count, ports_per_if, axis_pcie_data_width,
        axis_eth_data_width, axis_eth_sync_data_width, ptp_ts_enable):
    dut = "mqnic_core_pcie_us"
    module = os.path.splitext(os.path.basename(__file__))[0]
    toplevel = dut

    verilog_sources = [
        os.path.join(rtl_dir, f"{dut}.v"),
        os.path.join(rtl_dir, "mqnic_core_pcie.v"),
        os.path.join(rtl_dir, "mqnic_core.v"),
        os.path.join(rtl_dir, "mqnic_dram_if.v"),
        os.path.join(rtl_dir, "mqnic_interface.v"),
        os.path.join(rtl_dir, "resource_translator.v"),
        os.path.join(rtl_dir, "mqnic_interface_tx.v"),
        os.path.join(rtl_dir, "mqnic_interface_rx.v"),
        os.path.join(rtl_dir, "mqnic_port.v"),
        os.path.join(rtl_dir, "mqnic_port_tx.v"),
        os.path.join(rtl_dir, "mqnic_port_rx.v"),
        os.path.join(rtl_dir, "mqnic_egress.v"),
        os.path.join(rtl_dir, "mqnic_ingress.v"),
        os.path.join(rtl_dir, "mqnic_l2_egress.v"),
        os.path.join(rtl_dir, "mqnic_l2_ingress.v"),
        os.path.join(rtl_dir, "mqnic_rx_queue_map.v"),
        os.path.join(rtl_dir, "mqnic_ptp.v"),
        os.path.join(rtl_dir, "mqnic_ptp_clock.v"),
        os.path.join(rtl_dir, "mqnic_ptp_perout.v"),
        os.path.join(rtl_dir, "mqnic_rb_clk_info.v"),
        os.path.join(rtl_dir, "cpl_write.v"),
        os.path.join(rtl_dir, "cpl_op_mux.v"),
        os.path.join(rtl_dir, "desc_fetch.v"),
        os.path.join(rtl_dir, "desc_op_mux.v"),
        os.path.join(rtl_dir, "queue_manager.v"),
        os.path.join(rtl_dir, "cpl_queue_manager.v"),
        os.path.join(rtl_dir, "tx_fifo.v"),
        os.path.join(rtl_dir, "rx_fifo.v"),
        os.path.join(rtl_dir, "tx_req_mux.v"),
        os.path.join(rtl_dir, "tx_engine.v"),
        os.path.join(rtl_dir, "rx_engine.v"),
        os.path.join(rtl_dir, "tx_checksum.v"),
        os.path.join(rtl_dir, "rx_hash.v"),
        os.path.join(rtl_dir, "rx_checksum.v"),
        os.path.join(rtl_dir, "stats_counter.v"),
        os.path.join(rtl_dir, "stats_collect.v"),
        os.path.join(rtl_dir, "stats_pcie_if.v"),
        os.path.join(rtl_dir, "stats_pcie_tlp.v"),
        os.path.join(rtl_dir, "stats_dma_if_pcie.v"),
        os.path.join(rtl_dir, "stats_dma_latency.v"),
        os.path.join(rtl_dir, "mqnic_tx_scheduler_block_rr.v"),
        os.path.join(rtl_dir, "tx_scheduler_rr.v"),
        # os.path.join(rtl_dir, "axis_fifo_group.v"),
        os.path.join(eth_rtl_dir, "mac_ctrl_rx.v"),
        os.path.join(eth_rtl_dir, "mac_ctrl_tx.v"),
        os.path.join(eth_rtl_dir, "mac_pause_ctrl_rx.v"),
        os.path.join(eth_rtl_dir, "mac_pause_ctrl_tx.v"),
        os.path.join(eth_rtl_dir, "ptp_td_phc.v"),
        os.path.join(eth_rtl_dir, "ptp_td_leaf.v"),
        os.path.join(eth_rtl_dir, "ptp_perout.v"),
        os.path.join(axi_rtl_dir, "axil_crossbar.v"),
        os.path.join(axi_rtl_dir, "axil_crossbar_addr.v"),
        os.path.join(axi_rtl_dir, "axil_crossbar_rd.v"),
        os.path.join(axi_rtl_dir, "axil_crossbar_wr.v"),
        os.path.join(axi_rtl_dir, "axil_reg_if.v"),
        os.path.join(axi_rtl_dir, "axil_reg_if_rd.v"),
        os.path.join(axi_rtl_dir, "axil_reg_if_wr.v"),
        os.path.join(axi_rtl_dir, "axil_register_rd.v"),
        os.path.join(axi_rtl_dir, "axil_register_wr.v"),
        os.path.join(axi_rtl_dir, "arbiter.v"),
        os.path.join(axi_rtl_dir, "priority_encoder.v"),
        os.path.join(axis_rtl_dir, "axis_adapter.v"),
        os.path.join(axis_rtl_dir, "axis_arb_mux.v"),
        os.path.join(axis_rtl_dir, "axis_async_fifo.v"),
        os.path.join(axis_rtl_dir, "axis_async_fifo_adapter.v"),
        os.path.join(axis_rtl_dir, "axis_demux.v"),
        os.path.join(axis_rtl_dir, "axis_fifo.v"),
        os.path.join(axis_rtl_dir, "axis_fifo_adapter.v"),
        os.path.join(axis_rtl_dir, "axis_pipeline_fifo.v"),
        os.path.join(axis_rtl_dir, "axis_register.v"),
        os.path.join(pcie_rtl_dir, "pcie_axil_master.v"),
        os.path.join(pcie_rtl_dir, "pcie_tlp_demux.v"),
        os.path.join(pcie_rtl_dir, "pcie_tlp_demux_bar.v"),
        os.path.join(pcie_rtl_dir, "pcie_tlp_mux.v"),
        os.path.join(pcie_rtl_dir, "pcie_tlp_fifo.v"),
        os.path.join(pcie_rtl_dir, "pcie_tlp_fifo_raw.v"),
        os.path.join(pcie_rtl_dir, "pcie_msix.v"),
        os.path.join(pcie_rtl_dir, "irq_rate_limit.v"),
        os.path.join(pcie_rtl_dir, "dma_if_pcie.v"),
        os.path.join(pcie_rtl_dir, "dma_if_pcie_rd.v"),
        os.path.join(pcie_rtl_dir, "dma_if_pcie_wr.v"),
        os.path.join(pcie_rtl_dir, "dma_if_mux.v"),
        os.path.join(pcie_rtl_dir, "dma_if_mux_rd.v"),
        os.path.join(pcie_rtl_dir, "dma_if_mux_wr.v"),
        os.path.join(pcie_rtl_dir, "dma_if_desc_mux.v"),
        os.path.join(pcie_rtl_dir, "dma_ram_demux_rd.v"),
        os.path.join(pcie_rtl_dir, "dma_ram_demux_wr.v"),
        os.path.join(pcie_rtl_dir, "dma_psdpram.v"),
        os.path.join(pcie_rtl_dir, "dma_client_axis_sink.v"),
        os.path.join(pcie_rtl_dir, "dma_client_axis_source.v"),
        os.path.join(pcie_rtl_dir, "pcie_us_if.v"),
        os.path.join(pcie_rtl_dir, "pcie_us_if_rc.v"),
        os.path.join(pcie_rtl_dir, "pcie_us_if_rq.v"),
        os.path.join(pcie_rtl_dir, "pcie_us_if_cc.v"),
        os.path.join(pcie_rtl_dir, "pcie_us_if_cq.v"),
        os.path.join(pcie_rtl_dir, "pcie_us_cfg.v"),
        os.path.join(pcie_rtl_dir, "pulse_merge.v"),
    ]

    parameters = {}

    # Structural configuration
    parameters['IF_COUNT'] = if_count
    parameters['PORTS_PER_IF'] = ports_per_if
    parameters['SCHED_PER_IF'] = ports_per_if
    parameters['FUNCTION_ID_WIDTH'] = 8

    # Clock configuration
    parameters['CLK_PERIOD_NS_NUM'] = 4
    parameters['CLK_PERIOD_NS_DENOM'] = 1

    # PTP configuration
    parameters['PTP_CLK_PERIOD_NS_NUM'] = 32
    parameters['PTP_CLK_PERIOD_NS_DENOM'] = 5
    parameters['PTP_CLOCK_PIPELINE'] = 0
    parameters['PTP_CLOCK_CDC_PIPELINE'] = 0
    parameters['PTP_SEPARATE_TX_CLOCK'] = 0
    parameters['PTP_SEPARATE_RX_CLOCK'] = 0
    parameters['PTP_PORT_CDC_PIPELINE'] = 0
    parameters['PTP_PEROUT_ENABLE'] = 0
    parameters['PTP_PEROUT_COUNT'] = 1

    # Queue manager configuration
    parameters['EVENT_QUEUE_OP_TABLE_SIZE'] = 32
    parameters['TX_QUEUE_OP_TABLE_SIZE'] = 32
    parameters['RX_QUEUE_OP_TABLE_SIZE'] = 32
    parameters['CQ_OP_TABLE_SIZE'] = 32
    parameters['EQN_WIDTH'] = 9
    parameters['TX_QUEUE_INDEX_WIDTH'] = 13
    parameters['RX_QUEUE_INDEX_WIDTH'] = 9
    parameters['CQN_WIDTH'] = max(parameters['TX_QUEUE_INDEX_WIDTH'], parameters['RX_QUEUE_INDEX_WIDTH']) + 1
    parameters['EQ_PIPELINE'] = 3
    parameters['TX_QUEUE_PIPELINE'] = 3 + max(parameters['TX_QUEUE_INDEX_WIDTH']-12, 0)
    parameters['RX_QUEUE_PIPELINE'] = 3 + max(parameters['RX_QUEUE_INDEX_WIDTH']-12, 0)
    parameters['CQ_PIPELINE'] = 3 + max(parameters['CQN_WIDTH']-12, 0)

    # TX and RX engine configuration
    parameters['TX_DESC_TABLE_SIZE'] = 32
    parameters['RX_DESC_TABLE_SIZE'] = 32
    parameters['RX_INDIR_TBL_ADDR_WIDTH'] = min(parameters['RX_QUEUE_INDEX_WIDTH'], 8)

    # Scheduler configuration
    parameters['TX_SCHEDULER_OP_TABLE_SIZE'] = parameters['TX_DESC_TABLE_SIZE']
    parameters['TX_SCHEDULER_PIPELINE'] = parameters['TX_QUEUE_PIPELINE']
    parameters['TDMA_INDEX_WIDTH'] = 6

    # Interface configuration
    parameters['PTP_TS_ENABLE'] = ptp_ts_enable
    parameters['TX_CPL_ENABLE'] = parameters['PTP_TS_ENABLE']
    parameters['TX_CPL_FIFO_DEPTH'] = 32
    parameters['TX_TAG_WIDTH'] = 16
    parameters['TX_CHECKSUM_ENABLE'] = 1
    parameters['RX_HASH_ENABLE'] = 1
    parameters['RX_CHECKSUM_ENABLE'] = 1
    parameters['LFC_ENABLE'] = 1
    parameters['PFC_ENABLE'] = parameters['LFC_ENABLE']
    parameters['MAC_CTRL_ENABLE'] = 1
    parameters['TX_FIFO_DEPTH'] = 32768
    parameters['RX_FIFO_DEPTH'] = 131072
    parameters['MAX_TX_SIZE'] = 9214
    parameters['MAX_RX_SIZE'] = 9214
    parameters['TX_RAM_SIZE'] = 131072
    parameters['RX_RAM_SIZE'] = 131072

    # RAM configuration
    parameters['DDR_CH'] = 1
    parameters['DDR_ENABLE'] = 0
    parameters['DDR_GROUP_SIZE'] = 1
    parameters['AXI_DDR_DATA_WIDTH'] = 256
    parameters['AXI_DDR_ADDR_WIDTH'] = 32
    parameters['AXI_DDR_ID_WIDTH'] = 8
    parameters['AXI_DDR_MAX_BURST_LEN'] = 256
    parameters['HBM_CH'] = 1
    parameters['HBM_ENABLE'] = 0
    parameters['HBM_GROUP_SIZE'] = parameters['HBM_CH']
    parameters['AXI_HBM_DATA_WIDTH'] = 256
    parameters['AXI_HBM_ADDR_WIDTH'] = 32
    parameters['AXI_HBM_ID_WIDTH'] = 6
    parameters['AXI_HBM_MAX_BURST_LEN'] = 16

    # Application block configuration
    parameters['APP_ID'] = 0x00000000
    parameters['APP_ENABLE'] = 0
    parameters['APP_CTRL_ENABLE'] = 1
    parameters['APP_DMA_ENABLE'] = 1
    parameters['APP_AXIS_DIRECT_ENABLE'] = 1
    parameters['APP_AXIS_SYNC_ENABLE'] = 1
    parameters['APP_AXIS_IF_ENABLE'] = 1
    parameters['APP_STAT_ENABLE'] = 1

    # DMA interface configuration
    parameters['DMA_IMM_ENABLE'] = 0
    parameters['DMA_IMM_WIDTH'] = 32
    parameters['DMA_LEN_WIDTH'] = 16
    parameters['DMA_TAG_WIDTH'] = 16
    parameters['RAM_ADDR_WIDTH'] = (max(parameters['TX_RAM_SIZE'], parameters['RX_RAM_SIZE'])-1).bit_length()
    parameters['RAM_PIPELINE'] = 2

    # PCIe interface configuration
    parameters['AXIS_PCIE_DATA_WIDTH'] = axis_pcie_data_width
    parameters['PF_COUNT'] = 1
    parameters['VF_COUNT'] = 0

    # Interrupt configuration
    parameters['IRQ_INDEX_WIDTH'] = parameters['EQN_WIDTH'] - parameters["FUNCTION_ID_WIDTH"]

    # AXI lite interface configuration (control)
    parameters['AXIL_CTRL_DATA_WIDTH'] = 32
    parameters['AXIL_CTRL_ADDR_WIDTH'] = 24
    parameters['AXIL_CSR_PASSTHROUGH_ENABLE'] = 0

    # AXI lite interface configuration (application control)
    parameters['AXIL_APP_CTRL_DATA_WIDTH'] = parameters['AXIL_CTRL_DATA_WIDTH']
    parameters['AXIL_APP_CTRL_ADDR_WIDTH'] = 24

    # Ethernet interface configuration
    parameters['AXIS_ETH_DATA_WIDTH'] = axis_eth_data_width
    parameters['AXIS_ETH_SYNC_DATA_WIDTH'] = axis_eth_sync_data_width
    parameters['AXIS_ETH_RX_USE_READY'] = 0
    parameters['AXIS_ETH_TX_PIPELINE'] = 0
    parameters['AXIS_ETH_TX_FIFO_PIPELINE'] = 2
    parameters['AXIS_ETH_TX_TS_PIPELINE'] = 0
    parameters['AXIS_ETH_RX_PIPELINE'] = 0
    parameters['AXIS_ETH_RX_FIFO_PIPELINE'] = 2

    # Statistics counter subsystem
    parameters['STAT_ENABLE'] = 1
    parameters['STAT_DMA_ENABLE'] = 1
    parameters['STAT_PCIE_ENABLE'] = 1
    parameters['STAT_INC_WIDTH'] = 24
    parameters['STAT_ID_WIDTH'] = 12

    extra_env = {f'PARAM_{k}': str(v) for k, v in parameters.items()}

    sim_build = os.path.join(tests_dir, "sim_build",
        request.node.name.replace('[', '-').replace(']', ''))

    cocotb_test.simulator.run(
        python_search=[tests_dir],
        verilog_sources=verilog_sources,
        toplevel=toplevel,
        module=module,
        parameters=parameters,
        sim_build=sim_build,
        extra_env=extra_env,
    )
