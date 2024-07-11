import logging
import os
import math
import random 
import matplotlib.pyplot as plt 
from matplotlib.patches import Patch

import numpy as np

import cocotb_test.simulator

import cocotb
import logging
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.regression import TestFactory

import cocotb_test.simulator
import pytest

from cocotbext.axi import AxiLiteBus, AxiLiteMaster
from cocotbext.axi.stream import define_stream

# axis stream slave interface, doorbell input
DoorbellBus, DoorbellTransaction, DoorbellSource, DoorbellSink, DoorbellMonitor = define_stream("Doorbell", signals=["queue","func", "valid"], optional_signals=["ready"])

# axis stream master interface, transmit request output
TxReqBus, TxReqTransaction, TxReqSource, TxReqSink, TxReqMonitor = define_stream("TxReq", signals=["queue", "func", "tag", "valid"], optional_signals=["ready"])

# axis stream slave interface, transmit response
TxRespBus, TxRespTransaction, TxRespSource, TxRespSink, TxRespMonitor = define_stream("TxResp", signals=["len", "tag", "valid"], optional_signals=["ready"])


class TB(object):
    def __init__(self, dut):
    # def to initialize things
        self.dut = dut

        self.log = logging.getLogger("cocotb.tb")

        cocotb.start_soon(Clock(dut.clk, 4, units="ns").start())

        # set an axil master
        self.axil_master = AxiLiteMaster(AxiLiteBus.from_prefix(dut, "s_axil"),dut.clk, dut.rst)


        
        # set up axis stream sources/sinks

        self.doorbell_source = DoorbellSource(DoorbellBus.from_prefix(dut, "s_axis_doorbell"), dut.clk, dut.rst)
   
        self.txrq_sink = TxReqSink(TxReqBus.from_prefix(dut, "m_axis_tx_req"), dut.clk, dut.rst)

        self.txresp_source = TxRespSource(TxRespBus.from_prefix(dut, "s_axis_tx_req_status"), dut.clk, dut.rst)

        # set input control signals
     

        cocotb.log.setLevel(logging.DEBUG)
        
    # def for async reset of scheduler
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




QUEUE_ENABLED_QUEUE_STATE = 0x01
QUEUE_DISABLED_QUEUE_STATE = 0x0
FUNC_ENABLED_FUNC_STATE = 0x01
QUEUE_SCHED_ACTIVE_STATE = 0x01010000
QUEUE_EN_SCHED_ACTIVE_STATE = 0x01010001


# plots actual # transmits per queue and func vs expected. (func will pop up first, then queue after closing the figure)
# note that there may be slight gaps between expected vs actual depending on how evenly the num_packets is divided by the various weights.
# running time: ~10 minutes
# note, the weights are displayed under each func/queue's bar in parentheses
async def basic_bar_test(dut):
     tb = TB(dut)

     # wait til reset of scheduler complete
     await tb.reset()

     # enable scheduler
     dut.enable.value = 1


     tb.log.info("Test pulse out")

     await RisingEdge(dut.clk)

     num_queues = dut.QUEUE_COUNT.value
     num_funcs = dut.NUM_FUNCS.value

     # enable all queues, read back enabled
        # parameters = {}
     for i in range(num_queues):
          await tb.axil_master.write_dword((i*4), QUEUE_ENABLED_QUEUE_STATE)
          assert await tb.axil_master.read_dword(i*4)== QUEUE_ENABLED_QUEUE_STATE
    
     func_start_addr = (num_queues)*4
     func_end_addr = func_start_addr + ((dut.MAX_NUM_FUNCS.value)*4)

     queue_weight_start_addr = func_end_addr
     queue_weight_end_addr = queue_weight_start_addr + ((num_queues)*4)

     func_ram_start_addr = queue_weight_end_addr
     func_ram_end_addr = func_ram_start_addr + ((num_funcs)*4)

     
     queue_weight_list = []
     func_weight_list = []

     for i in range(num_queues):
          queue_weight_list.append(random.randint(1,255))

     for i in range(num_funcs):
          func_weight_list.append(random.randint(1,255))

     # write and read to func weights
     for i in range(func_start_addr, func_start_addr+(num_funcs*4), 4):
          func_id  = int((i/4)-dut.QUEUE_COUNT.value)
          await tb.axil_master.write_dword(i, func_weight_list[func_id])
          assert await tb.axil_master.read_dword(i) ==  func_weight_list[func_id]

     # write and read to queue weights
     for i in range(queue_weight_start_addr, queue_weight_end_addr, 4):
          queue_id = int((i/4)-(dut.QUEUE_COUNT.value+dut.MAX_NUM_FUNCS.value))
          await tb.axil_master.write_dword(i, queue_weight_list[queue_id])
          assert await tb.axil_master.read_dword(i) == queue_weight_list[queue_id]

     # enable all funcs, read back enabled
     for i in range(func_ram_start_addr, func_ram_end_addr, 4):
          await tb.axil_master.write_dword(i, FUNC_ENABLED_FUNC_STATE)
          assert await tb.axil_master.read_dword(i) == FUNC_ENABLED_FUNC_STATE

     num_queues_per_func = num_queues/num_funcs

     # send doorbell reqeusts for all queues
     for i in range(num_queues):
          await tb.doorbell_source.send(DoorbellTransaction(queue = i, func=int(math.floor((i/num_queues_per_func)))))

     fixed_val = []
     for i in range(num_funcs):
          fixed_val.append(50)

     num_packets = 35000

     func_expected_list, queue_expected_list= get_expected_transmit_nums(num_packets, func_weight_list, queue_weight_list, num_queues_per_func)
     func_actual_list, queue_actual_list = await get_actual_transmit_nums_bar(dut, num_packets, num_funcs, num_queues)
     
     # plot packets per func
     plot_bars(num_funcs, num_queues, func_expected_list, func_actual_list, 1, func_weight_list)

     # plot packets per queue
     plot_bars(num_funcs, num_queues, queue_expected_list, queue_actual_list, 0, queue_weight_list)

# in beginning, only send doorbell for even-indexed queues
# halfway through the transmits, activate the rest of the queues by sending doorbells
# even-indexed queues should have less actual transmits vs expected, vice versa for odd-numbered queues
# funcs should have basically non-existant gap between expected and actual
# running time: ~13 minutes
# note, the weights are displayed under each func/queue's bar in parentheses
async def doorbell1_test(dut):
     tb = TB(dut)

     # wait til reset of scheduler complete
     await tb.reset()

     # enable scheduler
     dut.enable.value = 1


     tb.log.info("Test pulse out")

     await RisingEdge(dut.clk)

     num_queues = dut.QUEUE_COUNT.value
     num_funcs = dut.NUM_FUNCS.value

     # enable all queues, read back enabled
        # parameters = {}
     for i in range(num_queues):
          await tb.axil_master.write_dword((i*4), QUEUE_ENABLED_QUEUE_STATE)
          assert await tb.axil_master.read_dword(i*4)== QUEUE_ENABLED_QUEUE_STATE
    
     func_start_addr = (num_queues)*4
     func_end_addr = func_start_addr + ((dut.MAX_NUM_FUNCS.value)*4)

     queue_weight_start_addr = func_end_addr
     queue_weight_end_addr = queue_weight_start_addr + ((num_queues)*4)

     func_ram_start_addr = queue_weight_end_addr
     func_ram_end_addr = func_ram_start_addr + ((num_funcs)*4)

     
     queue_weight_list = []
     func_weight_list = []

     for i in range(num_queues):
          queue_weight_list.append(random.randint(1,255))

     for i in range(num_funcs):
          func_weight_list.append(random.randint(1,255))

     # write and read to func weights
     for i in range(func_start_addr, func_start_addr+(num_funcs*4), 4):
          func_id  = int((i/4)-dut.QUEUE_COUNT.value)
          await tb.axil_master.write_dword(i, func_weight_list[func_id])
          assert await tb.axil_master.read_dword(i) ==  func_weight_list[func_id]

     # write and read to queue weights
     for i in range(queue_weight_start_addr, queue_weight_end_addr, 4):
          queue_id = int((i/4)-(dut.QUEUE_COUNT.value+dut.MAX_NUM_FUNCS.value))
          await tb.axil_master.write_dword(i, queue_weight_list[queue_id])
          assert await tb.axil_master.read_dword(i) == queue_weight_list[queue_id]

     # enable all funcs, read back enabled
     for i in range(func_ram_start_addr, func_ram_end_addr, 4):
          await tb.axil_master.write_dword(i, FUNC_ENABLED_FUNC_STATE)
          assert await tb.axil_master.read_dword(i) == FUNC_ENABLED_FUNC_STATE

     num_queues_per_func = num_queues/num_funcs

     # send doorbell reqeusts for every even indexed queue
     for i in range(num_queues):
          if(i%2==0):
               await tb.doorbell_source.send(DoorbellTransaction(queue = i, func=int(math.floor((i/num_queues_per_func)))))

     fixed_val = []
     for i in range(num_funcs):
          fixed_val.append(50)

     num_packets = 50000

     func_expected_list, queue_expected_list= get_expected_transmit_nums(num_packets, func_weight_list, queue_weight_list, num_queues_per_func)
     func_actual_list, queue_actual_list = await get_actual_transmit_nums_doorbell1(dut, num_packets, num_funcs, num_queues)
     
     # plot packets per func
     plot_bars(num_funcs, num_queues, func_expected_list, func_actual_list, 1, func_weight_list)

     # plot packets per queue
     plot_bars(num_funcs, num_queues, queue_expected_list, queue_actual_list, 0, queue_weight_list)


# Initially, first queue of each func is activeted (doorbells only sent for these).
# Each of the remaining queues is activated with a doorbell at a random time between 0-(3/4)*num_packets.
# 1 queue per func should have more transmits than expected, the rest will have less. 
# funcs should have basically non-existant gap between # transmits expected vs. actual
# running time: ~22 minutes (w/ 75,000 packets)
# note, the weights are displayed under each func/queue's bar in parentheses
async def doorbell3_test(dut):
     tb = TB(dut)

     # wait til reset of scheduler complete
     await tb.reset()

     # enable scheduler
     dut.enable.value = 1


     tb.log.info("Test pulse out")

     await RisingEdge(dut.clk)

     num_queues = dut.QUEUE_COUNT.value
     num_funcs = dut.NUM_FUNCS.value

     # enable all queues, read back enabled
     for i in range(num_queues):
          await tb.axil_master.write_dword((i*4), QUEUE_ENABLED_QUEUE_STATE)
          assert await tb.axil_master.read_dword(i*4)== QUEUE_ENABLED_QUEUE_STATE
    
     func_start_addr = (num_queues)*4
     func_end_addr = func_start_addr + ((dut.MAX_NUM_FUNCS.value)*4)

     queue_weight_start_addr = func_end_addr
     queue_weight_end_addr = queue_weight_start_addr + ((num_queues)*4)

     func_ram_start_addr = queue_weight_end_addr
     func_ram_end_addr = func_ram_start_addr + ((num_funcs)*4)

     
     queue_weight_list = []
     func_weight_list = []

     for i in range(num_queues):
          queue_weight_list.append(random.randint(1,255))

     for i in range(num_funcs):
          func_weight_list.append(random.randint(1,255))

     # write and read to func weights
     for i in range(func_start_addr, func_start_addr+(num_funcs*4), 4):
          func_id  = int((i/4)-dut.QUEUE_COUNT.value)
          await tb.axil_master.write_dword(i, func_weight_list[func_id])
          assert await tb.axil_master.read_dword(i) ==  func_weight_list[func_id]

     # write and read to queue weights
     for i in range(queue_weight_start_addr, queue_weight_end_addr, 4):
          queue_id = int((i/4)-(dut.QUEUE_COUNT.value+dut.MAX_NUM_FUNCS.value))
          await tb.axil_master.write_dword(i, queue_weight_list[queue_id])
          assert await tb.axil_master.read_dword(i) == queue_weight_list[queue_id]

     # enable all funcs, read back enabled
     for i in range(func_ram_start_addr, func_ram_end_addr, 4):
          await tb.axil_master.write_dword(i, FUNC_ENABLED_FUNC_STATE)
          assert await tb.axil_master.read_dword(i) == FUNC_ENABLED_FUNC_STATE

     num_queues_per_func = num_queues/num_funcs

     # send doorbell reqeusts for first queue of every func
     for i in range(num_queues):
          if(i%(num_queues_per_func)==0):
               await tb.doorbell_source.send(DoorbellTransaction(queue = i, func=int(math.floor((i/num_queues_per_func)))))

     num_packets = 75000

     func_expected_list, queue_expected_list= get_expected_transmit_nums(num_packets, func_weight_list, queue_weight_list, num_queues_per_func)
     func_actual_list, queue_actual_list = await get_actual_transmit_nums_doorbell3(dut, num_packets, num_funcs, num_queues)
     
     # plot packets per func
     plot_bars(num_funcs, num_queues, func_expected_list, func_actual_list, 1, func_weight_list)

     # plot packets per queue
     plot_bars(num_funcs, num_queues, queue_expected_list, queue_actual_list, 0, queue_weight_list)

# For first half of packets transmitted, for (num_queues/2) equally spaced times, picks a random queue
# in op_table_queue to force inactive (via failed transmit status responses).
# Then some number of packets after the half way mark, force these queues to become
# active again by sending doorbells. 
# running time: ~12 minutes (with 4 items: 1/7 vfs and 8/16 queues)
# note: it's hard to tell what's going on for first half of plot with 16 queues 
async def inactive1_test(dut):
     tb = TB(dut)

     # wait til reset of scheduler complete
     await tb.reset()

     # enable scheduler
     dut.enable.value = 1


     tb.log.info("Test pulse out")

     await RisingEdge(dut.clk)

     num_queues = dut.QUEUE_COUNT.value
     num_funcs = dut.NUM_FUNCS.value

     # enable all queues, read back enabled
     for i in range(num_queues):
          await tb.axil_master.write_dword((i*4), QUEUE_ENABLED_QUEUE_STATE)
          assert await tb.axil_master.read_dword(i*4)== QUEUE_ENABLED_QUEUE_STATE
    
     func_start_addr = (num_queues)*4
     func_end_addr = func_start_addr + ((dut.MAX_NUM_FUNCS.value)*4)

     queue_weight_start_addr = func_end_addr
     queue_weight_end_addr = queue_weight_start_addr + ((num_queues)*4)

     func_ram_start_addr = queue_weight_end_addr
     func_ram_end_addr = func_ram_start_addr + ((num_funcs)*4)

     
     queue_weight_list = []
     func_weight_list = []

     for i in range(num_queues):
          queue_weight_list.append(random.randint(1,255))

     for i in range(num_funcs):
          func_weight_list.append(random.randint(1,255))

     # write and read to func weights
     for i in range(func_start_addr, func_start_addr+(num_funcs*4), 4):
          func_id  = int((i/4)-dut.QUEUE_COUNT.value)
          await tb.axil_master.write_dword(i, func_weight_list[func_id])
          assert await tb.axil_master.read_dword(i) ==  func_weight_list[func_id]

     # write and read to queue weights
     for i in range(queue_weight_start_addr, queue_weight_end_addr, 4):
          queue_id = int((i/4)-(dut.QUEUE_COUNT.value+dut.MAX_NUM_FUNCS.value))
          await tb.axil_master.write_dword(i, queue_weight_list[queue_id])
          assert await tb.axil_master.read_dword(i) == queue_weight_list[queue_id]

     # enable all funcs, read back enabled
     for i in range(func_ram_start_addr, func_ram_end_addr, 4):
          await tb.axil_master.write_dword(i, FUNC_ENABLED_FUNC_STATE)
          assert await tb.axil_master.read_dword(i) == FUNC_ENABLED_FUNC_STATE

     num_queues_per_func = num_queues/num_funcs

     # send doorbell reqeusts for all queues
     for i in range(num_queues):
          await tb.doorbell_source.send(DoorbellTransaction(queue = i, func=int(math.floor((i/num_queues_per_func)))))

     num_packets = 40000

     x = []
     l0 = []
     l1 = []
     l2 = []
     l3 = []
     l4 = []
     l5 = []
     l6 = []
     l7 = []
     l8 = []
     l9 = []
     l10 = []
     l11 = []
     l12 = []
     l13 = []
     l14 = []
     l15 = []

     func_actual_list, queue_actual_list, inactive_list = await get_actual_transmit_nums1(dut, num_packets, num_funcs, num_queues, x, l0, l1, l2, l3, l4, l5, l6, l7, l8, l9, l10, l11, l12, l13, l14, l15)

     plot_lines1(x, inactive_list, l0, l1, l2, l3, l4, l5, l6, l7, l8, l9, l10, l11, l12, l13, l14, l15)


# Only 1/4 of the queues are active at a time. They become inactive 
# with a axil write that disables the queue. Each queue should transmit
# for exactly 2 intervals of length (num_packets/8). Sequentially numbered
# queues are active/inactive together. 
# Running time:  ~24 minutes for last figure to display (4 items: queue indices 3,4 & num_vfs 1,7)
async def inactive2_test(dut):
     tb = TB(dut)

     # wait til reset of scheduler complete
     await tb.reset()

     # enable scheduler
     dut.enable.value = 1


     tb.log.info("Test pulse out")

     await RisingEdge(dut.clk)

     num_queues = dut.QUEUE_COUNT.value
     num_funcs = dut.NUM_FUNCS.value

     # enable first group of queues, read back enabled
        # parameters = {}
     for i in range(int(num_queues/4)):
          await tb.axil_master.write_dword((i*4), QUEUE_ENABLED_QUEUE_STATE)
          assert await tb.axil_master.read_dword(i*4)== QUEUE_ENABLED_QUEUE_STATE
    
     func_start_addr = (num_queues)*4
     func_end_addr = func_start_addr + ((dut.MAX_NUM_FUNCS.value)*4)

     queue_weight_start_addr = func_end_addr
     queue_weight_end_addr = queue_weight_start_addr + ((num_queues)*4)

     func_ram_start_addr = queue_weight_end_addr
     func_ram_end_addr = func_ram_start_addr + ((num_funcs)*4)

     
     queue_weight_list = []
     func_weight_list = []

     for i in range(num_queues):
          queue_weight_list.append(random.randint(1,255))

     for i in range(num_funcs):
          func_weight_list.append(random.randint(1,255))

     # write and read to func weights
     for i in range(func_start_addr, func_start_addr+(num_funcs*4), 4):
          func_id  = int((i/4)-dut.QUEUE_COUNT.value)
          await tb.axil_master.write_dword(i, func_weight_list[func_id])
          assert await tb.axil_master.read_dword(i) ==  func_weight_list[func_id]

     # write and read to queue weights
     for i in range(queue_weight_start_addr, queue_weight_end_addr, 4):
          queue_id = int((i/4)-(dut.QUEUE_COUNT.value+dut.MAX_NUM_FUNCS.value))
          await tb.axil_master.write_dword(i, queue_weight_list[queue_id])
          assert await tb.axil_master.read_dword(i) == queue_weight_list[queue_id]

     # enable all funcs, read back enabled
     for i in range(func_ram_start_addr, func_ram_end_addr, 4):
          await tb.axil_master.write_dword(i, FUNC_ENABLED_FUNC_STATE)
          assert await tb.axil_master.read_dword(i) == FUNC_ENABLED_FUNC_STATE

     num_queues_per_func = num_queues/num_funcs

     # send doorbell reqeusts for all queues
     for i in range(num_queues):
          await tb.doorbell_source.send(DoorbellTransaction(queue = i, func=int(math.floor((i/num_queues_per_func)))))


     num_packets = 40000

     x = []
     l0 = []
     l1 = []
     l2 = []
     l3 = []
     l4 = []
     l5 = []
     l6 = []
     l7 = []
     l8 = []
     l9 = []
     l10 = []
     l11 = []
     l12 = []
     l13 = []
     l14 = []
     l15 = []

     i_val = await get_actual_transmit_nums2(dut, num_packets, num_funcs, num_queues, x, l0, l1, l2, l3, l4, l5, l6, l7, l8, l9, l10, l11, l12, l13, l14, l15)

     assert i_val==39999

     plot_lines(x, l0, l1, l2, l3, l4, l5, l6, l7, l8, l9, l10, l11, l12, l13, l14, l15)

async def get_actual_transmit_nums_bar(dut, num_packets, num_funcs, num_queues):

     tb = TB(dut)

     func_transmit_count = [0]*num_funcs
     queue_transmit_count = [0]*num_queues

     op_table_active = [0]*16
     num_active_ops = 0

     for i in range(num_packets):

          if(num_active_ops==16):
               num_active_ops -= await send_tr_resps(dut, op_table_active)

          resp = await tb.txrq_sink.recv()
          func_transmit_count[int(resp.func)] += 1
          queue_transmit_count[int(resp.queue)] += 1
          op_table_active[int(resp.tag)] = 1
          num_active_ops +=1

     return func_transmit_count, queue_transmit_count

async def get_actual_transmit_nums_doorbell1(dut, num_packets, num_funcs, num_queues):

     tb = TB(dut)

     func_transmit_count = [0]*num_funcs
     queue_transmit_count = [0]*num_queues

     op_table_active = [0]*16
     num_active_ops = 0

     num_queues_per_func = num_queues/num_funcs
     for i in range(num_packets):

          if(i==int(num_packets/2)):
               # send doorbells for all queues (should effectively activate all odd numbered index queues)
               for i in range(num_queues):
                    await tb.doorbell_source.send(DoorbellTransaction(queue = i, func=int(math.floor((i/num_queues_per_func)))))

          if(num_active_ops==16):
               num_active_ops -= await send_tr_resps(dut, op_table_active)

          resp = await tb.txrq_sink.recv()
          func_transmit_count[int(resp.func)] += 1
          queue_transmit_count[int(resp.queue)] += 1
          op_table_active[int(resp.tag)] = 1
          num_active_ops +=1

     return func_transmit_count, queue_transmit_count

async def get_actual_transmit_nums_doorbell3(dut, num_packets, num_funcs, num_queues):

     tb = TB(dut)

     func_transmit_count = [0]*num_funcs
     queue_transmit_count = [0]*num_queues

     op_table_active = [0]*16
     num_active_ops = 0

     num_queues_per_func = num_queues/num_funcs

     # create list of inactive queues (only first queue of every func is active)
     inactive_queue_list = []
     #create list of random packet # to make this queue active
     rand_time_list = []
     for i in range(num_queues):
          if(i%num_queues_per_func!=0):
               inactive_queue_list.append(i)
               rand_time_list.append(random.randint(0,math.floor(num_packets*(3/4))))

     # sort rand int list to be low to high
     rand_time_list.sort()

     for i in range(num_packets):

          # as long as there's still an inactive queue, check if doorbell should be sent
          if(len(inactive_queue_list)>0):
               # if i equals random time at front of list
               if(rand_time_list[0]==i):
                    # pick random inactive queue to send doorbell for
                    rand_queue_spot = random.randint(0,(len(inactive_queue_list)-1))
                    queue_idx = inactive_queue_list[rand_queue_spot]

                    await tb.doorbell_source.send(DoorbellTransaction(queue = queue_idx, func=int(math.floor((queue_idx/num_queues_per_func)))))

                    #take queue and rand time from respective lists
                    rand_time_list.pop(0)
                    inactive_queue_list.pop(rand_queue_spot)
                    

          if(num_active_ops==16):
               num_active_ops -= await send_tr_resps(dut, op_table_active)

          resp = await tb.txrq_sink.recv()
          func_transmit_count[int(resp.func)] += 1
          queue_transmit_count[int(resp.queue)] += 1
          op_table_active[int(resp.tag)] = 1
          num_active_ops +=1

     return func_transmit_count, queue_transmit_count

async def get_actual_transmit_nums1(dut, num_packets, num_funcs, num_queues, x, y0, y1, y2, y3, y4, y5, y6, y7, y8, y9, y10, y11, y12, y13, y14, y15):

     tb = TB(dut)

     func_transmit_count = [0]*num_funcs
     queue_transmit_count = [0]*num_queues

     op_table_active = [0]*16
     op_table_func = [0]*16
     op_table_queue = [0]*16


     num_active_ops = 0
     queue_counter = 0
     func_counter = 0 

     num_queues_per_func = num_queues/num_funcs

     # create list of inactive queues (only first queue of every func is active)
     inactive_queue_list = []
     saved_inactive_list = []
   

     for i in range(num_packets):

          if(num_active_ops==16):
               num_active_ops -= await send_tr_resps(dut, op_table_active)

          resp = await tb.txrq_sink.recv()
          func_transmit_count[int(resp.func)] += 1
          queue_transmit_count[int(resp.queue)] += 1
          op_table_active[int(resp.tag)] = 1
          op_table_func[int(resp.tag)]=int(resp.func)
          op_table_queue[int(resp.tag)]=[int(resp.queue)]
          num_active_ops +=1

          # well after desired queues have been marked as inactive  (numpackets/2 + 300), wake them up
          if(i==((num_packets)/2)+300):
               saved_inactive_list = [int(element) for element in inactive_queue_list]
               await wake_up_queues(dut, inactive_queue_list, num_queues_per_func)

          if(i%40==0):
          # to cut down on time, only update lines every 40 transmits
               update_queue_line_data(num_queues, queue_transmit_count, i, x, y0, y1, y2, y3, y4, y5, y6, y7, y8, y9, y10, y11, y12, y13, y14, y15)

          # if queue counter >0, trying to mark queue as inactive by failing all it's transmits until failed status sets in, fail this one
          if(min(queue_counter, func_counter)>0 and last_failed_queue==int(resp.queue) and i<((num_packets)/2)+3):
               await send_tr_resp_fail(dut, op_table_active, resp.tag)
               queue_counter = int(dut.queue_counter_next.value)
               func_counter = int(dut.func_counter_next.value)
               if(queue_counter==0 or func_counter ==0):
                    last_failed_queue = num_queues + 5
               # skip past next section of code
               continue

          # for (num_queues/2) evenly spaced times in first half of num packets sent, pick a queue to become inactive
          if(i%((num_packets/2)/(num_queues/2))==0 and i<(num_packets/2)):
               await send_tr_resp_fail(dut, op_table_active, resp.tag)

               # search for any current ops for this queue and also fail those
               for k in range(16):
                    if(op_table_active[k]==1 and op_table_queue[k]==resp.queue):
                         await send_tr_resp_fail(dut, op_table_active, k)

               # add queue to inactive list
               inactive_queue_list.append(resp.queue)

               # save current queue counter so we can fail any remaining transmits from this queue
               queue_counter = int(dut.queue_counter_next.value)
               func_counter = int(dut.func_counter_next.value)
               last_failed_queue = int(resp.queue)

          

     return func_transmit_count, queue_transmit_count, saved_inactive_list

def get_expected_transmit_nums(num_packets, func_weight_list, queue_weight_list, num_queues_per_func):

     func_return_list = []
     queue_return_list = []

     func_weight_sum = sum(func_weight_list)
     queue_weight_sum_per_func = []

     for i in range(len(func_weight_list)):
          func_return_list.append(math.floor((func_weight_list[i]/func_weight_sum)*num_packets))
          start = int(i*num_queues_per_func)
          end = int(start+num_queues_per_func)
          queue_weight_sum_per_func.append(sum(queue_weight_list[start:end]))

     for i in range(len(queue_weight_list)):
          func = math.floor(i/num_queues_per_func)
          queue_return_list.append(math.floor((queue_weight_list[i]/queue_weight_sum_per_func[func])*func_return_list[func]))

     return func_return_list, queue_return_list

def plot_bars(num_funcs, num_queues, expected_val, actual_val, plot_funcs, weight_list):
     # plot expected func bandwidths

     if (plot_funcs == 1):
          x_axis_labels = [f'{j}\n({weight_list[j]})' for j in range(0,num_funcs)]
          plt.xlabel("Function")
          plt.ylabel("# Packets Transmitted")
          plt.title(f'Packets Transmitted Per Function ({num_queues} Queues)')
     else:
          x_axis_labels = [f'{j}\n({weight_list[j]})' for j in range(0,num_queues)]
          plt.xlabel("Queue")
          plt.ylabel("# Packets Transmitted")
          plt.title(f'Packets Transmitted Per Queue ({num_funcs} Funcs)')
     
     bars_expected = plt.bar(x_axis_labels, expected_val, color='gray')


     # Display bar values at the top of each bar
     for bar_e in bars_expected:
          yval = bar_e.get_height()
          plt.text(bar_e.get_x() + bar_e.get_width() / 2, yval, round(yval, 2), ha='center', va='bottom', color="dimgray")


     bars_actual = plt.bar(x_axis_labels, actual_val, color='powderblue', alpha = 0.7)
     # Display bar values at the top of each bar
     for bar_a in bars_actual:
          plt.text(bar_a.get_x() + bar_a.get_width() / 2, bar_a.get_height()/2, bar_a.get_height(), ha='center', va='bottom', color="black")

     categories = ['Expected', 'Actual']
     colors = ['gray', 'powderblue']

     # Create legend handles
     legend_handles = [Patch(color=color, label=category) for color, category in zip(colors, categories)]

     # Create a legend
     plt.legend(handles=legend_handles, loc='upper center')

     plt.show()

def plot_lines1(x, inactive_list, *args):

     for i,y in enumerate(args):
          if (len(y)>0):
               plt.plot(x, y, label=f'Queue {i}')

               # display the ending val of each line
               plt.text(x[-1] + 0.1, y[-1], f'{y[-1]:.0f}', fontsize=8, verticalalignment='center')

     plt.xlim(min(x), max(x) + 35)  # Adjust the value as needed

     plt.xlabel('Time (in # total packets)')
     plt.ylabel('# packets transmitted')
     plt.title('Queue Packet Transmissions Across Time')

     text_to_display = f"in. queues: \n" + '\n'.join(map(str, inactive_list))

     max_x_val = x[len(x)-1]
     plt.text(max_x_val + 30, 5, text_to_display, fontsize=8, verticalalignment='center')
     plt.legend()

     
     plt.grid(which='both')

     plt.show()
def plot_lines(x, *args):

     for i,y in enumerate(args):
          if (len(y)>0):
               plt.plot(x, y, label=f'Queue {i}')

               # display the ending val of each line
               plt.text(x[-1] + 0.1, y[-1], f'{y[-1]:.0f}', fontsize=8, verticalalignment='center')

     plt.xlabel('Time (in # total packets)')
     plt.ylabel('# packets transmitted')
     plt.title('Queue Packet Transmissions Across Time')

     plt.legend()

     plt.grid(which='both')

     plt.show()

async def disable_queue(dut, queue_idx):
    tb = TB(dut)

    await tb.axil_master.write_dword((queue_idx*4), QUEUE_DISABLED_QUEUE_STATE)

async def enable_queue(dut, queue_idx):
    tb = TB(dut)

    await tb.axil_master.write_dword((queue_idx*4), QUEUE_ENABLED_QUEUE_STATE)

async def wake_up_queues(dut, queue_list, num_queues_per_func):
     tb = TB(dut)

     # for all queues in queue_list, send a doorbell to wake them up
     while(len(queue_list)!=0):
          queue_idx = int(queue_list[0])
          await tb.doorbell_source.send(DoorbellTransaction(queue = queue_idx, func=int(math.floor((queue_idx/num_queues_per_func)))))
          queue_list.pop(0)

async def get_actual_transmit_nums2(dut, num_packets, num_funcs, num_queues, x, y0, y1, y2, y3, y4, y5, y6, y7, y8, y9, y10, y11, y12, y13, y14, y15):

     tb = TB(dut)


     op_table_active = [0]*16
     op_table_func = [0]*16
     op_table_queue = [0]*16

     num_active_ops = 0

     queue_transmit_counts = [0]*num_queues

     # create list of active queues. 
     active_queue_list = []
     
     # initiate active queue list to first group of queues
     for k in range(int(num_queues/4)):
        active_queue_list.append(k)

     for i in range(num_packets):

          if(num_active_ops==16):
               num_active_ops -= await send_tr_resps(dut, op_table_active)

          resp = await tb.txrq_sink.recv()
          op_table_active[int(resp.tag)] = 1
          op_table_func[int(resp.tag)]=int(resp.func)
          op_table_queue[int(resp.tag)]=[int(resp.queue)]
          queue_transmit_counts[int(resp.queue)] += 1
          num_active_ops +=1

          # update line data every 40th transmit
          if(i%40==0):
            update_queue_line_data(num_queues, queue_transmit_counts, i, x, y0, y1, y2, y3, y4, y5, y6, y7, y8, y9, y10, y11, y12, y13, y14, y15)

          # for (num_packets/8) evenly spaced times (i>0 since first interval set up initially) 
          # disable current group of queues, enable next
          if(i%(num_packets/8)==0 and i>0):
               for j in range(int(num_queues/4)):
                    num_queues_per_group = int(num_queues/4)
                    next_queue_idx = (active_queue_list[j]+num_queues_per_group)%num_queues
                    print("i=%d",i)
                    print("disabling queue %d, enabling queue %d \n", active_queue_list[j], next_queue_idx)
                    await disable_queue(dut, active_queue_list[j])
                    await enable_queue(dut, next_queue_idx)
                    active_queue_list[j]= next_queue_idx

          

     return i




def update_queue_line_data(num_queues, transmit_counts, time_tick, x, y0, y1, y2, y3, y4, y5, y6, y7, y8, y9, y10, y11, y12, y13, y14, y15):

     # for all other queues, add a point that's equal to the last point for y-data
     for i in range(num_queues):
        # copy current transmit counts to line data
        line_name = locals()[f'y{i}']
        line_name.append(transmit_counts[i])
          
     # append time_tick (equivalent to current total packet count) to x data of line
     x.append(time_tick)

async def send_tr_resp_fail(dut, active_list, tag):

     # send failed response for given tag
     dut.s_axis_tx_req_status_len.setimmediatevalue(0)
     dut.s_axis_tx_req_status_tag.setimmediatevalue(tag)
     dut.s_axis_tx_req_status_valid.setimmediatevalue(1)
     await RisingEdge(dut.clk)
     dut.s_axis_tx_req_status_valid.setimmediatevalue(0)

     # mark tag as inactive/not in use
     active_list[tag]=0

     # return number of transmit responses sent
     return 1
        
async def send_tr_resps(dut, active_list):

     # starting at rand index 0-15
     start = random.randint(0,15)

     # send successful status for 1-16 queues as long as index valid
     num_responses = random.randint(1,16)

     k=0
     while((start+k)<16 and k<num_responses):
          dut.s_axis_tx_req_status_len.setimmediatevalue(4)
          dut.s_axis_tx_req_status_tag.setimmediatevalue((start+k))
          dut.s_axis_tx_req_status_valid.setimmediatevalue(1)
          await RisingEdge(dut.clk)
          dut.s_axis_tx_req_status_valid.setimmediatevalue(0)
          # mark tag as inactive/not in use
          active_list[k]=0

          k+=1
     # return number of transmit responses sent
     return k


if cocotb.SIM_NAME:
     #factory = TestFactory(basic_bar_test)
     #factory = TestFactory(doorbell1_test)
     factory = TestFactory(doorbell3_test)
     #factory = TestFactory(inactive1_test)
     #factory = TestFactory(inactive2_test)
     factory.generate_tests()


# cocotb-test

tests_dir = os.path.dirname(__file__)
rtl_dir = os.path.abspath(os.path.join(tests_dir, '..', '..', 'rtl'))
lib_dir = os.path.abspath(os.path.join(tests_dir, '..',  '..', 'lib'))
axi_rtl_dir = os.path.abspath(os.path.join(lib_dir, 'axi', 'rtl'))
axis_rtl_dir = os.path.abspath(os.path.join(lib_dir, 'axis', 'rtl'))
eth_rtl_dir = os.path.abspath(os.path.join(lib_dir, 'eth', 'rtl'))
pcie_rtl_dir = os.path.abspath(os.path.join(lib_dir, 'pcie', 'rtl'))

# only use up to 32 queues for bar graphs (else too many lines)
@pytest.mark.parametrize("queue_index_width", [4,5])
@pytest.mark.parametrize("num_vfs", [1,7])

# @pytest.mark.parametrize("queue_index_width", [3,4])
# @pytest.mark.parametrize("num_vfs", [1,7])
def test_tx_scheduler_w(request, queue_index_width, num_vfs):
    dut = "tx_scheduler_w"
    module = os.path.splitext(os.path.basename(__file__))[0]
    toplevel = dut

    verilog_sources = [
        os.path.join(rtl_dir, f"{dut}.v"),
        os.path.join(rtl_dir, f"axis_fifo_group.v"),
        os.path.join(axis_rtl_dir, f"axis_fifo.v"),
        os.path.join(axis_rtl_dir, f"priority_encoder.v"),
    ]

    parameters = {}

    parameters['AXIL_DATA_WIDTH'] = 32
    parameters['AXIL_ADDR_WIDTH'] = 16
    parameters['AXIL_STRB_WIDTH'] = 4
    parameters['LEN_WIDTH'] = 16
    parameters['REQ_TAG_WIDTH'] = 8
    parameters['OP_TABLE_SIZE'] = 16
    parameters['QUEUE_INDEX_WIDTH'] = queue_index_width
    parameters['PIPELINE'] = 2
    parameters['SCHED_CTRL_ENABLE'] = 0
    parameters['NUM_VFs'] = num_vfs

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
