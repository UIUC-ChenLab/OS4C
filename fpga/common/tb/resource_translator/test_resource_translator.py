#!/usr/bin/env python
# SPDX-License-Identifier: BSD-2-Clause-Views
# Copyright (c) 2024 Scott Smith
# Copyright (c) 2020 The Regents of the University of California

import logging
import os
import random

import cocotb_test.simulator
import pytest
import math

import cocotb
from cocotb.triggers import RisingEdge, Timer
from cocotb.regression import TestFactory



class TB(object):
	def __init__(self, dut):
		self.dut = dut

		self.log = logging.getLogger("cocotb.tb")
		self.log.setLevel(logging.DEBUG)



# @cocotb.test()
async def run_test(dut):

	tb = TB(dut)

	total_resources = dut.TOTAL_RESOURCES.value
	function_id_width = dut.FUNCTION_ID_WIDTH.value
	resource_bit_width = dut.RESOURCE_BIT_WIDTH.value
	axil_addr_width = dut.AXIL_ADDR_WIDTH.value

	def calc_correct_value(function_id, address) :
		resources_per_func = math.ceil(math.log2(total_resources / 2 ** function_id_width))
		resource_bits = resources_per_func + resource_bit_width

		resource_bitmask = 0b0

		for i in range(resource_bits) :
			resource_bitmask = (resource_bitmask << 1) | 1
  
		if function_id == 0 :
			return address
		else :
			return int((function_id << resource_bits) | address & resource_bitmask)


	async def testcase(read_function_id, read_address, write_function_id, write_address) :

		tb.log.info(f"Running test for Read Function ID {read_function_id} & Write Function ID {write_function_id} & input read address: {bin(read_address)} & input write address: {bin(write_address)}")

		dut.input_read_address.value = read_address
		dut.input_write_address.value = write_address
		dut.input_read_function_id.value = read_function_id
		dut.input_write_function_id.value = write_function_id
		await Timer(2, units="ns")

		tb.log.info(f"Outputs Read Function: {dut.output_read_function_id.value} & Write Function {dut.output_write_function_id.value} Read Address: {dut.output_read_address.value} & Output Write Address: {dut.output_write_address.value}" )
		assert dut.input_read_function_id.value == dut.output_read_function_id.value
		assert dut.input_write_function_id.value == dut.output_write_function_id.value
		assert dut.output_read_address.value.integer == calc_correct_value(read_function_id, read_address)
		assert dut.output_write_address.value.integer == calc_correct_value(write_function_id, write_address)



	# await tb.reset()
	tb.log.info("Starting testbench for the Resource Translator...")

	tb.log.info(f"The parameters are:\n Total Resources: {total_resources}\n Function ID Width: {function_id_width}\n Resource Bit Width: {resource_bit_width}\n AXIL Address Width: {axil_addr_width}")
	tb.log.info(msg=f"Calculated Resources Per Function: { dut.RESOURCES_PER_FUNC.value}")
	tb.log.info(f"Calculated Bits Per Resource: {dut.RESOURCE_BITS.value}")


	await testcase(read_function_id=0, read_address=0b0000, write_function_id=1, write_address=0b0001)	
	await testcase(read_function_id=0, read_address=0b0001, write_function_id=2, write_address=0b0000)
	await testcase(read_function_id=1, read_address=0b0000, write_function_id=0, write_address=0b0001)
	await testcase(read_function_id=1, read_address=0b0001, write_function_id=0, write_address=0b0000)
	await testcase(read_function_id=2, read_address=0b0000, write_function_id=3, write_address=0b0001)
	await testcase(read_function_id=2, read_address=0b0001, write_function_id=2, write_address=0b0000)

	await testcase(read_function_id=1, read_address=0b0010, write_function_id=0, write_address=0b0011)
	await testcase(read_function_id=1, read_address=0b0011, write_function_id=0, write_address=0b0111)

if cocotb.SIM_NAME:

	factory = TestFactory(run_test)
	factory.generate_tests()


# cocotb-test

tests_dir = os.path.dirname(__file__)
rtl_dir = os.path.abspath(os.path.join(tests_dir, '..', '..', 'rtl'))

@pytest.mark.parametrize(
		(
			"total_resources", 
		 	"resource_bit_width",
			"axil_addr_width"
		), 
		[
			(4096, 1, 32),
			(4096, 2, 32),
			(4096, 4, 32),
			(2048, 1, 32),
			(2048, 2, 32),
			(2048, 4, 32),
			(512, 1, 32),
			(512, 4, 32),
   			(512, 8, 32),
			(4096, 4, 64),
			(4096, 8, 128)
		])
def test_resource_manager(request, total_resources, resource_bit_width, axil_addr_width):
	dut = "resource_translator"
	module = os.path.splitext(os.path.basename(__file__))[0]
	toplevel = dut

	verilog_sources = [
		os.path.join(rtl_dir, f"{dut}.v"),
	]

	parameters = {}

	parameters['TOTAL_RESOURCES'] = total_resources
	parameters['FUNCTION_ID_WIDTH'] = 8
	parameters['RESOURCE_BIT_WIDTH'] = resource_bit_width
	parameters['AXIL_ADDR_WIDTH'] = axil_addr_width

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
