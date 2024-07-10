# OS4C: An Open-Source SR-IOV System for SmartNIC-based Cloud Platforms 

## Introduction

This is the repository associated with our 2024 IEEE Cloud paper. OS4C is the first open-source 100 Gbps NIC with support for virtualization (SR-IOV). We took Corundum (https://github.com/corundum/corundum/) and modified it to support virtualization. This entailed adding a new scheduler, SR-IOV support, and updating the testing/simulation tools. If you leverage this work, please cite both our paper and the original Corundum paper.


## Documentation

For detailed documentation on our modifications to Corundum, please see our IEEE Cloud 2024 paper.

For documentation on Corundum's original design, see https://docs.corundum.io/

### OS4C Key Features

* OS4C Supports SR-IOV with up to 252 VFs. We are limited by the PCIe IP.
* OS4C Supports a two-stage weighted round-robin transmit scheduler that integrates with the virtualization logic
* We currently offically support the Alveo U280 - but other Alveo boards should work with minimal modifications (they are as of yet untried)

### Usage

Navigate to fpga/mqnic/Alveo/fpga_100g/fpga_AU280 and type *make* to build.

You can change the synthesis parameters in the Makefile located in fpga/mqnic/Alveo/fpga_100g/fpga_AU28O/config.tcl

### Testbench

We need the same tools as Corundum to run the testbench. See below.

"Running the included testbenches requires [cocotb](https://github.com/cocotb/cocotb), [cocotbext-axi](https://github.com/alexforencich/cocotbext-axi), [cocotbext-eth](https://github.com/alexforencich/cocotbext-eth), [cocotbext-pcie](https://github.com/alexforencich/cocotbext-pcie), [scapy](https://scapy.net/), and [Icarus Verilog](http://iverilog.icarus.com/).  The testbenches can be run with pytest directly (requires [cocotb-test](https://github.com/themperek/cocotb-test)), pytest via tox, or via cocotb makefiles." - from the original Corundum repository.

Run the testbenches by navigating to the fpga/common/tb/ folder. Many of the testbenches for modules are from the original Corundum repo. 

Once you install the dependencies (see above) you can run them using pytest. Currently, we have only released a simplified single-tenant testbench. The multi-tenant testbench requires modifications to some of the above libraries. We are working on seeing if those modifications can be added to those repositories as a new release. If not, we will release patches here. Expect that in the next week or two (by mid August 2024)

Example: *pytest -n auto --log-file=log.txt*

The above will use pytest to launch a series of tests. The *-n auto* parameter tells pytest to automatically determine how many cores to use (more cores should enable faster completion of the set of tests). The *--log-file=log.txt* parameter lets you print lots of useful information to a log file. 



### Notes and Future Work
* We plan to discuss with the existing Corundum developers possible integration of our work into their projcect.
* We are working to improve documentation over the next few weeks


## OS4C Publication
- S. Smith, Y. Ma, M. Lanz, B. Dai, M. Ohmacht, B. Sukhwani, H. Franke, V. Kindratenko, D. Chen, *OS4C: An Open-Source SR-IOV System for SmartNIC-based Cloud Platforms,* in IEEE Cloud'2024 

## Corundum Publications

- A. Forencich, A. C. Snoeren, G. Porter, G. Papen, *Corundum: An Open-Source 100-Gbps NIC,* in FCCM'20. ([FCCM Paper](https://www.cse.ucsd.edu/~snoeren/papers/corundum-fccm20.pdf), [FCCM Presentation](https://www.fccm.org/past/2020/forums/topic/corundum-an-open-source-100-gbps-nic/))

- J. A. Forencich, *System-Level Considerations for Optical Switching in Data Center Networks*. ([Thesis](https://escholarship.org/uc/item/3mc9070t))

## Dependencies

We build upon the following repositories (Corundum + the libraries Corundum relies on)

*  https://github.com/corundum/corundum/
*  https://github.com/alexforencich/verilog-axi
*  https://github.com/alexforencich/verilog-axis
*  https://github.com/alexforencich/verilog-ethernet
*  https://github.com/alexforencich/verilog-pcie
*  https://github.com/solemnwarning/timespec

