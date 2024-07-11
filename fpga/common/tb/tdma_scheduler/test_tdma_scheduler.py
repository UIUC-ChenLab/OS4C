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

from cocotbext.eth import PtpClock


class TB(object):
    def __init__(self, dut):
        self.dut = dut

        self.log = logging.getLogger("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        cocotb.start_soon(Clock(dut.clk, 4, units="ns").start())

        self.ptp_clock = PtpClock(
            ts_tod=dut.input_ts_96,
            ts_step=dut.input_ts_step,
            clock=dut.clk,
            reset=dut.rst,
            period_ns=6.4
        )

        dut.enable.setimmediatevalue(0)
        dut.input_schedule_start.setimmediatevalue(0)
        dut.input_schedule_start_valid.setimmediatevalue(0)
        dut.input_schedule_period.setimmediatevalue(0)
        dut.input_schedule_period_valid.setimmediatevalue(0)
        dut.input_timeslot_period.setimmediatevalue(0)
        dut.input_timeslot_period_valid.setimmediatevalue(0)
        dut.input_active_period.setimmediatevalue(0)
        dut.input_active_period_valid.setimmediatevalue(0)

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

    dut.enable.value = 1

    tb.log.info("Test pulse out")

    await RisingEdge(dut.clk)

    dut.input_schedule_start.value = 1000
    dut.input_schedule_start_valid.value = 1
    dut.input_schedule_period.value = 2000
    dut.input_schedule_period_valid.value = 1
    dut.input_timeslot_period.value = 400
    dut.input_timeslot_period_valid.value = 1
    dut.input_active_period.value = 300
    dut.input_active_period_valid.value = 1

    await RisingEdge(dut.clk)

    dut.input_schedule_start_valid.value = 0
    dut.input_schedule_period_valid.value = 0
    dut.input_timeslot_period_valid.value = 0
    dut.input_active_period_valid.value = 0

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


def test_tdma_scheduler(request):
    dut = "tdma_scheduler"
    module = os.path.splitext(os.path.basename(__file__))[0]
    toplevel = dut

    verilog_sources = [
        os.path.join(rtl_dir, f"{dut}.v"),
    ]

    parameters = {}

    parameters['INDEX_WIDTH'] = 8
    parameters['SCHEDULE_START_S'] = 0
    parameters['SCHEDULE_START_NS'] = 0
    parameters['SCHEDULE_PERIOD_S'] = 0
    parameters['SCHEDULE_PERIOD_NS'] = 1000000
    parameters['TIMESLOT_PERIOD_S'] = 0
    parameters['TIMESLOT_PERIOD_NS'] = 100000

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
