# SPDX-License-Identifier: BSD-2-Clause-Views
# Copyright (c) 2020-2023 The Regents of the University of California

import logging
import os
import sys

import scapy.utils
from scapy.layers.l2 import Ether
from scapy.layers.inet import IP, UDP

import cocotb_test.simulator

import cocotb
from cocotb.log import SimLog
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer

from cocotbext.axi import AxiStreamBus, AxiLiteBus, AxiLiteRam
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
    def __init__(self, dut, msix_count=32):
        self.dut = dut

        self.log = SimLog("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        # PCIe
        self.rc = RootComplex()

        self.rc.max_payload_size = 0x1  # 256 bytes
        self.rc.max_read_request_size = 0x2  # 512 bytes

        self.dev = UltraScalePlusPcieDevice(
            # configuration options
            pcie_generation=3,
            pcie_link_width=16,
            user_clk_frequency=250e6,
            alignment="dword",
            cq_straddle=len(dut.uut.core_inst.pcie_if_inst.pcie_us_if_cq_inst.rx_req_tlp_valid_reg) > 1,
            cc_straddle=len(dut.uut.core_inst.pcie_if_inst.pcie_us_if_cc_inst.out_tlp_valid) > 1,
            rq_straddle=len(dut.uut.core_inst.pcie_if_inst.pcie_us_if_rq_inst.out_tlp_valid) > 1,
            rc_straddle=len(dut.uut.core_inst.pcie_if_inst.pcie_us_if_rc_inst.rx_cpl_tlp_valid_reg) > 1,
            rc_4tlp_straddle=len(dut.uut.core_inst.pcie_if_inst.pcie_us_if_rc_inst.rx_cpl_tlp_valid_reg) > 2,
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
            user_clk=dut.clk_250mhz,
            user_reset=dut.rst_250mhz,
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

        self.dev.functions[0].configure_bar(0, 2**len(dut.uut.core_inst.core_pcie_inst.axil_ctrl_araddr), ext=True, prefetch=True)
        if hasattr(dut.uut.core_inst.core_pcie_inst, 'pcie_app_ctrl'):
            self.dev.functions[0].configure_bar(2, 2**len(dut.uut.core_inst.core_pcie_inst.axil_app_ctrl_araddr), ext=True, prefetch=True)

        cocotb.start_soon(Clock(dut.ptp_clk, 6.206, units="ns").start())
        dut.ptp_rst.setimmediatevalue(0)
        cocotb.start_soon(Clock(dut.ptp_sample_clk, 8, units="ns").start())

        # Ethernet
        self.qsfp_mac = []

        for ch in self.dut.ch:
            cocotb.start_soon(Clock(ch.ch_rx_clk, 3.102, units="ns").start())
            cocotb.start_soon(Clock(ch.ch_tx_clk, 3.102, units="ns").start())

            mac = EthMac(
                tx_clk=ch.ch_tx_clk,
                tx_rst=ch.ch_tx_rst,
                tx_bus=AxiStreamBus.from_prefix(ch, "ch_tx_axis"),
                tx_ptp_time=ch.ch_tx_ptp_time,
                tx_ptp_ts=ch.ch_tx_ptp_ts,
                tx_ptp_ts_tag=ch.ch_tx_ptp_ts_tag,
                tx_ptp_ts_valid=ch.ch_tx_ptp_ts_valid,
                rx_clk=ch.ch_rx_clk,
                rx_rst=ch.ch_rx_rst,
                rx_bus=AxiStreamBus.from_prefix(ch, "ch_rx_axis"),
                rx_ptp_time=ch.ch_rx_ptp_time,
                ifg=12, speed=100e9
            )

            self.qsfp_mac.append(mac)

            ch.ch_rx_status.setimmediatevalue(1)
            ch.ch_rx_lfc_req.setimmediatevalue(0)
            ch.ch_rx_pfc_req.setimmediatevalue(0)

        cocotb.start_soon(Clock(dut.qsfp_drp_clk, 8, units="ns").start())
        dut.qsfp_drp_rst.setimmediatevalue(0)
        dut.qsfp_drp_do.setimmediatevalue(0)
        dut.qsfp_drp_rdy.setimmediatevalue(0)

        dut.qsfp_modprsl.setimmediatevalue(0)
        dut.qsfp_intl.setimmediatevalue(1)

        dut.sw.setimmediatevalue(0)

        dut.i2c_scl_i.setimmediatevalue(1)
        dut.i2c_sda_i.setimmediatevalue(1)

        dut.qspi_dq_i.setimmediatevalue(0)

        self.cms_ram = AxiLiteRam(AxiLiteBus.from_prefix(dut, "m_axil_cms"), dut.m_axil_cms_clk, dut.m_axil_cms_rst, size=256*1024)

        self.loopback_enable = False
        cocotb.start_soon(self._run_loopback())

    async def init(self):

        self.dut.ptp_rst.setimmediatevalue(0)
        for ch in self.dut.ch:
            ch.ch_rx_rst.setimmediatevalue(0)
            ch.ch_tx_rst.setimmediatevalue(0)

        await RisingEdge(self.dut.clk_250mhz)
        await RisingEdge(self.dut.clk_250mhz)

        self.dut.ptp_rst.setimmediatevalue(1)
        for ch in self.dut.ch:
            ch.ch_rx_rst.setimmediatevalue(1)
            ch.ch_tx_rst.setimmediatevalue(1)

        await FallingEdge(self.dut.rst_250mhz)
        await Timer(100, 'ns')

        await RisingEdge(self.dut.clk_250mhz)
        await RisingEdge(self.dut.clk_250mhz)

        self.dut.ptp_rst.setimmediatevalue(0)
        for ch in self.dut.ch:
            ch.ch_rx_rst.setimmediatevalue(0)
            ch.ch_tx_rst.setimmediatevalue(0)

        await self.rc.enumerate()

    async def _run_loopback(self):
        while True:
            await RisingEdge(self.dut.clk_250mhz)

            if self.loopback_enable:
                for mac in self.qsfp_mac:
                    if not mac.tx.empty():
                        await mac.rx.send(await mac.tx.recv())


@cocotb.test()
async def run_test_nic(dut):

    tb = TB(dut, msix_count=2**len(dut.uut.core_inst.core_pcie_inst.irq_index))

    await tb.init()

    tb.log.info("Init driver")
    await tb.driver.init_pcie_dev(tb.rc.find_device(tb.dev.functions[0].pcie_id))
    await tb.driver.interfaces[0].open()
    # await tb.driver.interfaces[1].open()

    # enable queues
    tb.log.info("Enable queues")
    await tb.driver.interfaces[0].sched_blocks[0].schedulers[0].rb.write_dword(mqnic.MQNIC_RB_SCHED_RR_REG_CTRL, 0x00000001)
    for k in range(len(tb.driver.interfaces[0].txq)):
        await tb.driver.interfaces[0].sched_blocks[0].schedulers[0].hw_regs.write_dword(4*k, 0x00000003)

    # wait for all writes to complete
    await tb.driver.hw_regs.read_dword(0)
    tb.log.info("Init complete")

    tb.log.info("Send and receive single packet")

    data = bytearray([x % 256 for x in range(1024)])

    await tb.driver.interfaces[0].start_xmit(data, 0)

    pkt = await tb.qsfp_mac[0].tx.recv()
    tb.log.info("Packet: %s", pkt)

    await tb.qsfp_mac[0].rx.send(pkt)

    pkt = await tb.driver.interfaces[0].recv()

    tb.log.info("Packet: %s", pkt)
    assert pkt.rx_checksum == ~scapy.utils.checksum(bytes(pkt.data[14:])) & 0xffff

    # await tb.driver.interfaces[1].start_xmit(data, 0)

    # pkt = await tb.qsfp_mac[1].tx.recv()
    # tb.log.info("Packet: %s", pkt)

    # await tb.qsfp_mac[1].rx.send(pkt)

    # pkt = await tb.driver.interfaces[1].recv()

    # tb.log.info("Packet: %s", pkt)
    # assert pkt.rx_checksum == ~scapy.utils.checksum(bytes(pkt.data[14:])) & 0xffff

    tb.log.info("RX and TX checksum tests")

    payload = bytes([x % 256 for x in range(256)])
    eth = Ether(src='5A:51:52:53:54:55', dst='DA:D1:D2:D3:D4:D5')
    ip = IP(src='192.168.1.100', dst='192.168.1.101')
    udp = UDP(sport=1, dport=2)
    test_pkt = eth / ip / udp / payload

    test_pkt2 = test_pkt.copy()
    test_pkt2[UDP].chksum = scapy.utils.checksum(bytes(test_pkt2[UDP]))

    await tb.driver.interfaces[0].start_xmit(test_pkt2.build(), 0, 34, 6)

    pkt = await tb.qsfp_mac[0].tx.recv()
    tb.log.info("Packet: %s", pkt)

    await tb.qsfp_mac[0].rx.send(pkt)

    pkt = await tb.driver.interfaces[0].recv()

    tb.log.info("Packet: %s", pkt)
    assert pkt.rx_checksum == ~scapy.utils.checksum(bytes(pkt.data[14:])) & 0xffff
    assert Ether(pkt.data).build() == test_pkt.build()

    tb.log.info("Queue mapping offset test")

    data = bytearray([x % 256 for x in range(1024)])

    tb.loopback_enable = True

    for k in range(4):
        await tb.driver.interfaces[0].set_rx_queue_map_indir_table(0, 0, k)

        await tb.driver.interfaces[0].start_xmit(data, 0)

        pkt = await tb.driver.interfaces[0].recv()

        tb.log.info("Packet: %s", pkt)
        assert pkt.rx_checksum == ~scapy.utils.checksum(bytes(pkt.data[14:])) & 0xffff
        assert pkt.queue == k

    tb.loopback_enable = False

    await tb.driver.interfaces[0].set_rx_queue_map_indir_table(0, 0, 0)

    tb.log.info("Queue mapping RSS mask test")

    await tb.driver.interfaces[0].set_rx_queue_map_rss_mask(0, 0x00000003)

    for k in range(4):
        await tb.driver.interfaces[0].set_rx_queue_map_indir_table(0, k, k)

    tb.loopback_enable = True

    queues = set()

    for k in range(64):
        payload = bytes([x % 256 for x in range(256)])
        eth = Ether(src='5A:51:52:53:54:55', dst='DA:D1:D2:D3:D4:D5')
        ip = IP(src='192.168.1.100', dst='192.168.1.101')
        udp = UDP(sport=1, dport=k+0)
        test_pkt = eth / ip / udp / payload

        test_pkt2 = test_pkt.copy()
        test_pkt2[UDP].chksum = scapy.utils.checksum(bytes(test_pkt2[UDP]))

        await tb.driver.interfaces[0].start_xmit(test_pkt2.build(), 0, 34, 6)

    for k in range(64):
        pkt = await tb.driver.interfaces[0].recv()

        tb.log.info("Packet: %s", pkt)
        assert pkt.rx_checksum == ~scapy.utils.checksum(bytes(pkt.data[14:])) & 0xffff

        queues.add(pkt.queue)

    assert len(queues) == 4

    tb.loopback_enable = False

    await tb.driver.interfaces[0].set_rx_queue_map_rss_mask(0, 0)

    tb.log.info("Multiple small packets")

    count = 64

    pkts = [bytearray([(x+k) % 256 for x in range(60)]) for k in range(count)]

    tb.loopback_enable = True

    for p in pkts:
        await tb.driver.interfaces[0].start_xmit(p, 0)

    for k in range(count):
        pkt = await tb.driver.interfaces[0].recv()

        tb.log.info("Packet: %s", pkt)
        assert pkt.data == pkts[k]
        assert pkt.rx_checksum == ~scapy.utils.checksum(bytes(pkt.data[14:])) & 0xffff

    tb.loopback_enable = False

    tb.log.info("Multiple large packets")

    count = 64

    pkts = [bytearray([(x+k) % 256 for x in range(1514)]) for k in range(count)]

    tb.loopback_enable = True

    for p in pkts:
        await tb.driver.interfaces[0].start_xmit(p, 0)

    for k in range(count):
        pkt = await tb.driver.interfaces[0].recv()

        tb.log.info("Packet: %s", pkt)
        assert pkt.data == pkts[k]
        assert pkt.rx_checksum == ~scapy.utils.checksum(bytes(pkt.data[14:])) & 0xffff

    tb.loopback_enable = False

    tb.log.info("Jumbo frames")

    count = 64

    pkts = [bytearray([(x+k) % 256 for x in range(9014)]) for k in range(count)]

    tb.loopback_enable = True

    for p in pkts:
        await tb.driver.interfaces[0].start_xmit(p, 0)

    for k in range(count):
        pkt = await tb.driver.interfaces[0].recv()

        tb.log.info("Packet: %s", pkt)
        assert pkt.data == pkts[k]
        assert pkt.rx_checksum == ~scapy.utils.checksum(bytes(pkt.data[14:])) & 0xffff

    tb.loopback_enable = False

    await RisingEdge(dut.clk_250mhz)
    await RisingEdge(dut.clk_250mhz)


# cocotb-test

tests_dir = os.path.dirname(__file__)
rtl_dir = os.path.abspath(os.path.join(tests_dir, '..', '..', 'rtl'))
lib_dir = os.path.abspath(os.path.join(rtl_dir, '..', 'lib'))
app_dir = os.path.abspath(os.path.join(rtl_dir, '..', 'app'))
axi_rtl_dir = os.path.abspath(os.path.join(lib_dir, 'axi', 'rtl'))
axis_rtl_dir = os.path.abspath(os.path.join(lib_dir, 'axis', 'rtl'))
eth_rtl_dir = os.path.abspath(os.path.join(lib_dir, 'eth', 'rtl'))
pcie_rtl_dir = os.path.abspath(os.path.join(lib_dir, 'pcie', 'rtl'))


def test_fpga_core(request):
    dut = "fpga_core"
    module = os.path.splitext(os.path.basename(__file__))[0]
    toplevel = f"test_{dut}"

    verilog_sources = [
        os.path.join(tests_dir, f"{toplevel}.v"),
        os.path.join(rtl_dir, f"{dut}.v"),
        os.path.join(rtl_dir, "common", "mqnic_core_pcie_us.v"),
        os.path.join(rtl_dir, "common", "mqnic_core_pcie.v"),
        os.path.join(rtl_dir, "common", "mqnic_core.v"),
        os.path.join(rtl_dir, "common", "mqnic_dram_if.v"),
        os.path.join(rtl_dir, "common", "mqnic_interface.v"),
        os.path.join(rtl_dir, "common", "mqnic_interface_tx.v"),
        os.path.join(rtl_dir, "common", "mqnic_interface_rx.v"),
        os.path.join(rtl_dir, "common", "mqnic_port.v"),
        os.path.join(rtl_dir, "common", "mqnic_port_tx.v"),
        os.path.join(rtl_dir, "common", "mqnic_port_rx.v"),
        os.path.join(rtl_dir, "common", "mqnic_egress.v"),
        os.path.join(rtl_dir, "common", "mqnic_ingress.v"),
        os.path.join(rtl_dir, "common", "mqnic_l2_egress.v"),
        os.path.join(rtl_dir, "common", "mqnic_l2_ingress.v"),
        os.path.join(rtl_dir, "common", "mqnic_rx_queue_map.v"),
        os.path.join(rtl_dir, "common", "mqnic_ptp.v"),
        os.path.join(rtl_dir, "common", "mqnic_ptp_clock.v"),
        os.path.join(rtl_dir, "common", "mqnic_ptp_perout.v"),
        os.path.join(rtl_dir, "common", "mqnic_rb_clk_info.v"),
        os.path.join(rtl_dir, "common", "mqnic_port_map_mac_axis.v"),
        os.path.join(rtl_dir, "common", "cpl_write.v"),
        os.path.join(rtl_dir, "common", "cpl_op_mux.v"),
        os.path.join(rtl_dir, "common", "desc_fetch.v"),
        os.path.join(rtl_dir, "common", "desc_op_mux.v"),
        os.path.join(rtl_dir, "common", "queue_manager.v"),
        os.path.join(rtl_dir, "common", "cpl_queue_manager.v"),
        os.path.join(rtl_dir, "common", "tx_fifo.v"),
        os.path.join(rtl_dir, "common", "rx_fifo.v"),
        os.path.join(rtl_dir, "common", "tx_req_mux.v"),
        os.path.join(rtl_dir, "common", "tx_engine.v"),
        os.path.join(rtl_dir, "common", "rx_engine.v"),
        os.path.join(rtl_dir, "common", "tx_checksum.v"),
        os.path.join(rtl_dir, "common", "rx_hash.v"),
        os.path.join(rtl_dir, "common", "rx_checksum.v"),
        os.path.join(rtl_dir, "common", "rb_drp.v"),
        os.path.join(rtl_dir, "common", "stats_counter.v"),
        os.path.join(rtl_dir, "common", "stats_collect.v"),
        os.path.join(rtl_dir, "common", "stats_pcie_if.v"),
        os.path.join(rtl_dir, "common", "stats_pcie_tlp.v"),
        os.path.join(rtl_dir, "common", "stats_dma_if_pcie.v"),
        os.path.join(rtl_dir, "common", "stats_dma_latency.v"),
        os.path.join(rtl_dir, "common", "mqnic_tx_scheduler_block_rr.v"),
        os.path.join(rtl_dir, "common", "tx_scheduler_rr.v"),
        os.path.join(eth_rtl_dir, "ptp_td_phc.v"),
        os.path.join(eth_rtl_dir, "ptp_td_leaf.v"),
        os.path.join(eth_rtl_dir, "ptp_perout.v"),
        os.path.join(axi_rtl_dir, "axil_interconnect.v"),
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
    parameters['IF_COUNT'] = 2
    parameters['PORTS_PER_IF'] = 1
    parameters['SCHED_PER_IF'] = parameters['PORTS_PER_IF']
    parameters['PORT_MASK'] = 0

    # Clock configuration
    parameters['CLK_PERIOD_NS_NUM'] = 4
    parameters['CLK_PERIOD_NS_DENOM'] = 1

    # PTP configuration
    parameters['PTP_CLK_PERIOD_NS_NUM'] = 1024
    parameters['PTP_CLK_PERIOD_NS_DENOM'] = 165
    parameters['PTP_CLOCK_PIPELINE'] = 0
    parameters['PTP_CLOCK_CDC_PIPELINE'] = 0
    parameters['PTP_PORT_CDC_PIPELINE'] = 0
    parameters['PTP_PEROUT_ENABLE'] = 0
    parameters['PTP_PEROUT_COUNT'] = 1

    # Queue manager configuration
    parameters['EVENT_QUEUE_OP_TABLE_SIZE'] = 32
    parameters['TX_QUEUE_OP_TABLE_SIZE'] = 32
    parameters['RX_QUEUE_OP_TABLE_SIZE'] = 32
    parameters['CQ_OP_TABLE_SIZE'] = 32
    parameters['EQN_WIDTH'] = 6
    parameters['TX_QUEUE_INDEX_WIDTH'] = 13
    parameters['RX_QUEUE_INDEX_WIDTH'] = 8
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
    parameters['PTP_TS_ENABLE'] = 1
    parameters['TX_CPL_FIFO_DEPTH'] = 32
    parameters['TX_CHECKSUM_ENABLE'] = 1
    parameters['RX_HASH_ENABLE'] = 1
    parameters['RX_CHECKSUM_ENABLE'] = 1
    parameters['LFC_ENABLE'] = 1
    parameters['PFC_ENABLE'] = parameters['LFC_ENABLE']
    parameters['TX_FIFO_DEPTH'] = 32768
    parameters['RX_FIFO_DEPTH'] = 131072
    parameters['MAX_TX_SIZE'] = 9214
    parameters['MAX_RX_SIZE'] = 9214
    parameters['TX_RAM_SIZE'] = 131072
    parameters['RX_RAM_SIZE'] = 131072

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
    parameters['AXIS_PCIE_DATA_WIDTH'] = 512
    parameters['PF_COUNT'] = 1
    parameters['VF_COUNT'] = 0

    # Interrupt configuration
    parameters['IRQ_INDEX_WIDTH'] = parameters['EQN_WIDTH']

    # AXI lite interface configuration (control)
    parameters['AXIL_CTRL_DATA_WIDTH'] = 32
    parameters['AXIL_CTRL_ADDR_WIDTH'] = 24

    # AXI lite interface configuration (application control)
    parameters['AXIL_APP_CTRL_DATA_WIDTH'] = parameters['AXIL_CTRL_DATA_WIDTH']
    parameters['AXIL_APP_CTRL_ADDR_WIDTH'] = 24

    # Ethernet interface configuration
    parameters['AXIS_ETH_TX_PIPELINE'] = 4
    parameters['AXIS_ETH_TX_FIFO_PIPELINE'] = 4
    parameters['AXIS_ETH_TX_TS_PIPELINE'] = 4
    parameters['AXIS_ETH_RX_PIPELINE'] = 4
    parameters['AXIS_ETH_RX_FIFO_PIPELINE'] = 4

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
