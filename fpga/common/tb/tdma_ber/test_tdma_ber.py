#!/usr/bin/env python
# SPDX-License-Identifier: BSD-2-Clause-Views
# Copyright (c) 2020-2023 The Regents of the University of California

import logging
import os

import cocotb_test.simulator

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb.regression import TestFactory

from cocotbext.axi import AxiLiteBus, AxiLiteMaster
from cocotbext.eth import PtpClock


class TB(object):
    def __init__(self, dut):
        self.dut = dut

        self.log = logging.getLogger("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        cocotb.start_soon(Clock(dut.clk, 4, units="ns").start())
        cocotb.start_soon(Clock(dut.phy_tx_clk, 6.4, units="ns").start())
        cocotb.start_soon(Clock(dut.phy_rx_clk, 6.4, units="ns").start())

        self.axil_master = AxiLiteMaster(AxiLiteBus.from_prefix(dut, "s_axil"), dut.clk, dut.rst)

        self.ptp_clock = PtpClock(
            ts_tod=dut.ptp_ts_96,
            ts_step=dut.ptp_ts_step,
            clock=dut.clk,
            reset=dut.rst,
            period_ns=6.4
        )

        dut.phy_rx_error_count.setimmediatevalue(0)

    async def reset(self):
        self.dut.rst.setimmediatevalue(0)
        await RisingEdge(self.dut.clk)
        await RisingEdge(self.dut.clk)
        self.dut.rst.value = 1
        await RisingEdge(self.dut.clk)
        await RisingEdge(self.dut.clk)
        self.dut.rst.value = 0
        await RisingEdge(self.dut.clk)
        await RisingEdge(self.dut.clk)


async def run_test(dut):

    tb = TB(dut)

    await tb.reset()

    tb.log.info("Test scheduler")

    await tb.axil_master.write_dwords(0x0110, [0,  500, 0, 0])
    await tb.axil_master.write_dwords(0x0120, [0, 2000, 0, 0])
    await tb.axil_master.write_dwords(0x0130, [0,  400, 0, 0])
    await tb.axil_master.write_dwords(0x0140, [0,  300, 0, 0])
    await tb.axil_master.write_dword(0x0100, 0x00000001)

    await Timer(10000, 'ns')

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)


if cocotb.SIM_NAME:

    factory = TestFactory(run_test)
    factory.generate_tests()


# cocotb-test

tests_dir = os.path.dirname(__file__)
rtl_dir = os.path.abspath(os.path.join(tests_dir, '..', '..', 'rtl'))
lib_dir = os.path.abspath(os.path.join(rtl_dir, '..', 'lib'))
axi_rtl_dir = os.path.abspath(os.path.join(lib_dir, 'axi', 'rtl'))
axis_rtl_dir = os.path.abspath(os.path.join(lib_dir, 'axis', 'rtl'))
eth_rtl_dir = os.path.abspath(os.path.join(lib_dir, 'eth', 'rtl'))
pcie_rtl_dir = os.path.abspath(os.path.join(lib_dir, 'pcie', 'rtl'))


def test_tdma_ber(request):
    dut = "tdma_ber"
    module = os.path.splitext(os.path.basename(__file__))[0]
    toplevel = dut

    verilog_sources = [
        os.path.join(rtl_dir, f"{dut}.v"),
        os.path.join(rtl_dir, f"{dut}_ch.v"),
        os.path.join(rtl_dir, "tdma_scheduler.v"),
        os.path.join(axi_rtl_dir, "axil_interconnect.v"),
        os.path.join(axi_rtl_dir, "arbiter.v"),
        os.path.join(axi_rtl_dir, "priority_encoder.v"),
    ]

    parameters = {}

    parameters['COUNT'] = 2
    parameters['INDEX_WIDTH'] = 6
    parameters['SLICE_WIDTH'] = 5
    parameters['AXIL_DATA_WIDTH'] = 32
    parameters['AXIL_ADDR_WIDTH'] = parameters['INDEX_WIDTH']+4+1+(parameters['COUNT']-1).bit_length()
    parameters['AXIL_STRB_WIDTH'] = parameters['AXIL_DATA_WIDTH'] // 8
    parameters['SCHEDULE_START_S'] = 0
    parameters['SCHEDULE_START_NS'] = 0
    parameters['SCHEDULE_PERIOD_S'] = 0
    parameters['SCHEDULE_PERIOD_NS'] = 1000000
    parameters['TIMESLOT_PERIOD_S'] = 0
    parameters['TIMESLOT_PERIOD_NS'] = 100000
    parameters['ACTIVE_PERIOD_S'] = 0
    parameters['ACTIVE_PERIOD_NS'] = 100000
    parameters['PHY_PIPELINE'] = 0

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
