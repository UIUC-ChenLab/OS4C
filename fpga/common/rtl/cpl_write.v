// SPDX-License-Identifier: BSD-2-Clause-Views
/*
 * Copyright (c) 2024 University of Illinois Urbana Champaign
 * Copyright (c) 2019-2023 The Regents of the University of California
 */

// Language: Verilog 2001

`resetall
`timescale 1ns / 1ps
`default_nettype none

/*
 * Completion write module
 */
module cpl_write #
(
    // Number of ports
    parameter PORTS = 2,
    // Select field width
    parameter SELECT_WIDTH = $clog2(PORTS),
    // RAM segment count
    parameter SEG_COUNT = 2,
    // RAM segment data width
    parameter SEG_DATA_WIDTH = 64,
    // RAM segment address width
    parameter SEG_ADDR_WIDTH = 8,
    // RAM segment byte enable width
    parameter SEG_BE_WIDTH = SEG_DATA_WIDTH/8,
    // RAM address width
    parameter RAM_ADDR_WIDTH = SEG_ADDR_WIDTH+$clog2(SEG_COUNT)+$clog2(SEG_BE_WIDTH),
    // DMA RAM pipeline stages
    parameter RAM_PIPELINE = 2,
    // DMA address width
    parameter DMA_ADDR_WIDTH = 64,
    // DMA length field width
    parameter DMA_LEN_WIDTH = 20,
    // DMA tag field width
    parameter DMA_TAG_WIDTH = 8,
    // Transmit request tag field width
    parameter REQ_TAG_WIDTH = 8,
    // Queue request tag field width
    parameter QUEUE_REQ_TAG_WIDTH = 8,
    // Queue operation tag field width
    parameter QUEUE_OP_TAG_WIDTH = 8,
    // Queue index width
    parameter QUEUE_INDEX_WIDTH = 4,
    // Completion size (in bytes)
    parameter CPL_SIZE = 32,
    // Descriptor table size (number of in-flight operations)
    parameter DESC_TABLE_SIZE = 8,
    // Function ID index width (log2 of number of function IDs)
    parameter FUNCTION_ID_WIDTH = 8 // Scott
)
(
    input  wire                                 clk,
    input  wire                                 rst,

    /*
     * Completion write request input (From TX/RX Engine or Event Queue)
     */
    input  wire [SELECT_WIDTH-1:0]              s_axis_req_sel,
    input  wire [QUEUE_INDEX_WIDTH-1:0]         s_axis_req_queue,
    input  wire [FUNCTION_ID_WIDTH-1:0]         s_axis_req_function_id, // Scott (not used)
    input  wire [REQ_TAG_WIDTH-1:0]             s_axis_req_tag,
    input  wire [CPL_SIZE*8-1:0]                s_axis_req_data,
    input  wire                                 s_axis_req_valid,
    output wire                                 s_axis_req_ready,

    /*
     * Completion write request status output
     */
    output wire [REQ_TAG_WIDTH-1:0]             m_axis_req_status_tag,
    output wire                                 m_axis_req_status_full,
    output wire                                 m_axis_req_status_error,
    output wire                                 m_axis_req_status_valid,

    /*
     * Completion enqueue request output (to completion queue managers)
     */
    output wire [PORTS*QUEUE_INDEX_WIDTH-1:0]   m_axis_cpl_enqueue_req_queue,
    output wire [PORTS*REQ_TAG_WIDTH-1:0]       m_axis_cpl_enqueue_req_tag,
    output wire [PORTS-1:0]                     m_axis_cpl_enqueue_req_valid,
    input  wire [PORTS-1:0]                     m_axis_cpl_enqueue_req_ready,

    /*
     * Completion enqueue response input (from completion queue managers)
     */
    input  wire [PORTS-1:0]                     s_axis_cpl_enqueue_resp_phase,
    input  wire [PORTS*DMA_ADDR_WIDTH-1:0]      s_axis_cpl_enqueue_resp_addr,
    input  wire [PORTS*QUEUE_REQ_TAG_WIDTH-1:0] s_axis_cpl_enqueue_resp_tag,
    input  wire [PORTS*QUEUE_OP_TAG_WIDTH-1:0]  s_axis_cpl_enqueue_resp_op_tag,
    input  wire [PORTS*FUNCTION_ID_WIDTH-1:0]   s_axis_cpl_enqueue_resp_function_id, // Scott
    input  wire [PORTS-1:0]                     s_axis_cpl_enqueue_resp_full,
    input  wire [PORTS-1:0]                     s_axis_cpl_enqueue_resp_error,
    input  wire [PORTS-1:0]                     s_axis_cpl_enqueue_resp_valid,
    output wire [PORTS-1:0]                     s_axis_cpl_enqueue_resp_ready,

    /*
     * Completion enqueue commit output
     */
    output wire [PORTS*QUEUE_OP_TAG_WIDTH-1:0]  m_axis_cpl_enqueue_commit_op_tag,
    output wire [PORTS-1:0]                     m_axis_cpl_enqueue_commit_valid,
    input  wire [PORTS-1:0]                     m_axis_cpl_enqueue_commit_ready,

    /*
     * DMA write descriptor output
     */
    output wire [DMA_ADDR_WIDTH-1:0]            m_axis_dma_write_desc_dma_addr,
    output wire [FUNCTION_ID_WIDTH-1:0]         m_axis_dma_write_desc_function_id, // Scott
    output wire [RAM_ADDR_WIDTH-1:0]            m_axis_dma_write_desc_ram_addr,
    output wire [DMA_LEN_WIDTH-1:0]             m_axis_dma_write_desc_len,
    output wire [DMA_TAG_WIDTH-1:0]             m_axis_dma_write_desc_tag,
    output wire                                 m_axis_dma_write_desc_valid,
    input  wire                                 m_axis_dma_write_desc_ready,

    /*
     * DMA write descriptor status input
     */
    input  wire [DMA_TAG_WIDTH-1:0]             s_axis_dma_write_desc_status_tag,
    input  wire [3:0]                           s_axis_dma_write_desc_status_error,
    input  wire                                 s_axis_dma_write_desc_status_valid,

    /*
     * RAM interface
     */
    input  wire [SEG_COUNT*SEG_ADDR_WIDTH-1:0]  dma_ram_rd_cmd_addr,
    input  wire [SEG_COUNT-1:0]                 dma_ram_rd_cmd_valid,
    output wire [SEG_COUNT-1:0]                 dma_ram_rd_cmd_ready,
    output wire [SEG_COUNT*SEG_DATA_WIDTH-1:0]  dma_ram_rd_resp_data,
    output wire [SEG_COUNT-1:0]                 dma_ram_rd_resp_valid,
    input  wire [SEG_COUNT-1:0]                 dma_ram_rd_resp_ready,

    /*
     * Configuration
     */
    input  wire                                 enable
);

parameter CL_DESC_TABLE_SIZE = $clog2(DESC_TABLE_SIZE);
parameter DESC_PTR_MASK = {CL_DESC_TABLE_SIZE{1'b1}};

parameter CL_PORTS = $clog2(PORTS);

// bus width assertions
initial begin
    if (DMA_TAG_WIDTH < CL_DESC_TABLE_SIZE+1) begin
        $error("Error: DMA tag width insufficient for descriptor table size (instance %m)");
        $finish;
    end

    if (QUEUE_REQ_TAG_WIDTH < CL_DESC_TABLE_SIZE) begin
        $error("Error: Queue request tag width insufficient for descriptor table size (instance %m)");
        $finish;
    end

    if (SEG_ADDR_WIDTH < CL_DESC_TABLE_SIZE) begin
        $error("Error: SEG_ADDR_WIDTH not sufficient for requested size (min %d for table size %d) (instance %m)", CL_DESC_TABLE_SIZE, DESC_TABLE_SIZE);
        $finish;
    end

    if (SEG_COUNT*SEG_DATA_WIDTH < CPL_SIZE*8) begin
        $error("Error: DMA RAM width insufficient for completion size (instance %m)");
        $finish;
    end
end

reg s_axis_req_ready_reg = 1'b0, s_axis_req_ready_next;

reg [REQ_TAG_WIDTH-1:0] m_axis_req_status_tag_reg = {REQ_TAG_WIDTH{1'b0}}, m_axis_req_status_tag_next;
reg m_axis_req_status_full_reg = 1'b0, m_axis_req_status_full_next;
reg m_axis_req_status_error_reg = 1'b0, m_axis_req_status_error_next;
reg m_axis_req_status_valid_reg = 1'b0, m_axis_req_status_valid_next;

reg [QUEUE_INDEX_WIDTH-1:0] m_axis_cpl_enqueue_req_queue_reg = {QUEUE_INDEX_WIDTH{1'b0}}, m_axis_cpl_enqueue_req_queue_next;
reg [QUEUE_REQ_TAG_WIDTH-1:0] m_axis_cpl_enqueue_req_tag_reg = {QUEUE_REQ_TAG_WIDTH{1'b0}}, m_axis_cpl_enqueue_req_tag_next;
reg [PORTS-1:0] m_axis_cpl_enqueue_req_valid_reg = {PORTS{1'b0}}, m_axis_cpl_enqueue_req_valid_next;

reg [PORTS-1:0] s_axis_cpl_enqueue_resp_ready_reg = {PORTS{1'b0}}, s_axis_cpl_enqueue_resp_ready_next;

reg [QUEUE_OP_TAG_WIDTH-1:0] m_axis_cpl_enqueue_commit_op_tag_reg = {QUEUE_OP_TAG_WIDTH{1'b0}}, m_axis_cpl_enqueue_commit_op_tag_next;
reg [PORTS-1:0] m_axis_cpl_enqueue_commit_valid_reg = {PORTS{1'b0}}, m_axis_cpl_enqueue_commit_valid_next;

reg [DMA_ADDR_WIDTH-1:0] m_axis_dma_write_desc_dma_addr_reg = {DMA_ADDR_WIDTH{1'b0}}, m_axis_dma_write_desc_dma_addr_next;
reg [FUNCTION_ID_WIDTH-1:0] m_axis_dma_write_desc_function_id_reg = {FUNCTION_ID_WIDTH{1'b0}}, m_axis_dma_write_desc_function_id_next; // Scott
reg [RAM_ADDR_WIDTH-1:0] m_axis_dma_write_desc_ram_addr_reg = {RAM_ADDR_WIDTH{1'b0}}, m_axis_dma_write_desc_ram_addr_next;
reg [DMA_LEN_WIDTH-1:0] m_axis_dma_write_desc_len_reg = {DMA_LEN_WIDTH{1'b0}}, m_axis_dma_write_desc_len_next;
reg [DMA_TAG_WIDTH-1:0] m_axis_dma_write_desc_tag_reg = {DMA_TAG_WIDTH{1'b0}}, m_axis_dma_write_desc_tag_next;
reg m_axis_dma_write_desc_valid_reg = 1'b0, m_axis_dma_write_desc_valid_next;

reg [DESC_TABLE_SIZE-1:0] desc_table_active = 0;
reg [DESC_TABLE_SIZE-1:0] desc_table_invalid = 0;
reg [DESC_TABLE_SIZE-1:0] desc_table_cpl_write_done = 0;
(* ram_style = "distributed", ramstyle = "no_rw_check, mlab" *)
reg [CL_PORTS-1:0] desc_table_sel[DESC_TABLE_SIZE-1:0];
(* ram_style = "distributed", ramstyle = "no_rw_check, mlab" *)
reg [REQ_TAG_WIDTH-1:0] desc_table_tag[DESC_TABLE_SIZE-1:0];
(* ram_style = "distributed", ramstyle = "no_rw_check, mlab" *)
reg [CPL_SIZE*8-1:0] desc_table_data[DESC_TABLE_SIZE-1:0];
(* ram_style = "distributed", ramstyle = "no_rw_check, mlab" *)
reg desc_table_phase[DESC_TABLE_SIZE-1:0];
(* ram_style = "distributed", ramstyle = "no_rw_check, mlab" *)
reg [QUEUE_OP_TAG_WIDTH-1:0] desc_table_queue_op_tag[DESC_TABLE_SIZE-1:0];

reg [CL_DESC_TABLE_SIZE+1-1:0] desc_table_start_ptr_reg = 0;
reg [CL_PORTS-1:0] desc_table_start_sel;
reg [REQ_TAG_WIDTH-1:0] desc_table_start_tag;
reg [CPL_SIZE*8-1:0] desc_table_start_data;
reg [QUEUE_INDEX_WIDTH-1:0] desc_table_start_cpl_queue;
reg [QUEUE_OP_TAG_WIDTH-1:0] desc_table_start_queue_op_tag;
reg desc_table_start_en;
reg [CL_DESC_TABLE_SIZE-1:0] desc_table_enqueue_ptr;
reg desc_table_enqueue_phase;
reg [QUEUE_OP_TAG_WIDTH-1:0] desc_table_enqueue_queue_op_tag;
reg desc_table_enqueue_invalid;
reg desc_table_enqueue_en;
reg [CL_DESC_TABLE_SIZE-1:0] desc_table_cpl_write_done_ptr;
reg desc_table_cpl_write_done_en;
reg [CL_DESC_TABLE_SIZE+1-1:0] desc_table_finish_ptr_reg = 0;
reg desc_table_finish_en;

assign s_axis_req_ready = s_axis_req_ready_reg;

assign m_axis_req_status_tag = m_axis_req_status_tag_reg;
assign m_axis_req_status_full = m_axis_req_status_full_reg;
assign m_axis_req_status_error = m_axis_req_status_error_reg;
assign m_axis_req_status_valid = m_axis_req_status_valid_reg;

assign m_axis_cpl_enqueue_req_queue = {PORTS{m_axis_cpl_enqueue_req_queue_reg}};
assign m_axis_cpl_enqueue_req_tag = {PORTS{m_axis_cpl_enqueue_req_tag_reg}};
assign m_axis_cpl_enqueue_req_valid = m_axis_cpl_enqueue_req_valid_reg;

assign s_axis_cpl_enqueue_resp_ready = s_axis_cpl_enqueue_resp_ready_reg;

assign m_axis_cpl_enqueue_commit_op_tag = {PORTS{m_axis_cpl_enqueue_commit_op_tag_reg}};
assign m_axis_cpl_enqueue_commit_valid = m_axis_cpl_enqueue_commit_valid_reg;

assign m_axis_dma_write_desc_dma_addr = m_axis_dma_write_desc_dma_addr_reg;
assign m_axis_dma_write_desc_function_id = m_axis_dma_write_desc_function_id_reg; // Scott
assign m_axis_dma_write_desc_ram_addr = m_axis_dma_write_desc_ram_addr_reg;
assign m_axis_dma_write_desc_len = m_axis_dma_write_desc_len_reg;
assign m_axis_dma_write_desc_tag = m_axis_dma_write_desc_tag_reg;
assign m_axis_dma_write_desc_valid = m_axis_dma_write_desc_valid_reg;

wire [CL_PORTS-1:0] enqueue_resp_enc;
wire enqueue_resp_enc_valid;

priority_encoder #(
    .WIDTH(PORTS),
    .LSB_HIGH_PRIORITY(1)
)
op_table_start_enc_inst (
    .input_unencoded(s_axis_cpl_enqueue_resp_valid & ~s_axis_cpl_enqueue_resp_ready),
    .output_valid(enqueue_resp_enc_valid),
    .output_encoded(enqueue_resp_enc),
    .output_unencoded()
);

generate

    genvar n;

    for (n = 0; n < SEG_COUNT; n = n + 1) begin

        reg [RAM_PIPELINE-1:0] dma_ram_rd_resp_valid_pipe_reg = 0;
        reg [SEG_DATA_WIDTH-1:0] dma_ram_rd_resp_data_pipe_reg[RAM_PIPELINE-1:0];

        integer i, j;

        initial begin
            for (i = 0; i < RAM_PIPELINE; i = i + 1) begin
                dma_ram_rd_resp_data_pipe_reg[i] = 0;
            end
        end

        always @(posedge clk) begin
            if (dma_ram_rd_resp_ready[n]) begin
                dma_ram_rd_resp_valid_pipe_reg[RAM_PIPELINE-1] <= 1'b0;
            end

            for (j = RAM_PIPELINE-1; j > 0; j = j - 1) begin
                if (dma_ram_rd_resp_ready[n] || ((~dma_ram_rd_resp_valid_pipe_reg) >> j)) begin
                    dma_ram_rd_resp_valid_pipe_reg[j] <= dma_ram_rd_resp_valid_pipe_reg[j-1];
                    dma_ram_rd_resp_data_pipe_reg[j] <= dma_ram_rd_resp_data_pipe_reg[j-1];
                    dma_ram_rd_resp_valid_pipe_reg[j-1] <= 1'b0;
                end
            end

            if (dma_ram_rd_cmd_valid[n] && dma_ram_rd_cmd_ready[n]) begin
                dma_ram_rd_resp_valid_pipe_reg[0] <= 1'b1;
                dma_ram_rd_resp_data_pipe_reg[0] <= {desc_table_phase[dma_ram_rd_cmd_addr[SEG_ADDR_WIDTH*n +: CL_DESC_TABLE_SIZE]], desc_table_data[dma_ram_rd_cmd_addr[SEG_ADDR_WIDTH*n +: CL_DESC_TABLE_SIZE]][CPL_SIZE*8-1-1:0]} >> SEG_DATA_WIDTH*n;
            end

            if (rst) begin
                dma_ram_rd_resp_valid_pipe_reg <= 0;
            end
        end

        assign dma_ram_rd_cmd_ready[n] = dma_ram_rd_resp_ready[n] || ~dma_ram_rd_resp_valid_pipe_reg;

        assign dma_ram_rd_resp_valid[n] = dma_ram_rd_resp_valid_pipe_reg[RAM_PIPELINE-1];
        assign dma_ram_rd_resp_data[SEG_DATA_WIDTH*n +: SEG_DATA_WIDTH] = dma_ram_rd_resp_data_pipe_reg[RAM_PIPELINE-1];
    end

endgenerate

always @* begin
    s_axis_req_ready_next = 1'b0;

    m_axis_req_status_tag_next = m_axis_req_status_tag_reg;
    m_axis_req_status_full_next = m_axis_req_status_full_reg;
    m_axis_req_status_error_next = m_axis_req_status_error_reg;
    m_axis_req_status_valid_next = 1'b0;

    m_axis_cpl_enqueue_req_queue_next = m_axis_cpl_enqueue_req_queue_reg;
    m_axis_cpl_enqueue_req_tag_next = m_axis_cpl_enqueue_req_tag_reg;
    m_axis_cpl_enqueue_req_valid_next = m_axis_cpl_enqueue_req_valid_reg & ~m_axis_cpl_enqueue_req_ready;

    s_axis_cpl_enqueue_resp_ready_next = 1'b0;

    m_axis_cpl_enqueue_commit_op_tag_next = m_axis_cpl_enqueue_commit_op_tag_reg;
    m_axis_cpl_enqueue_commit_valid_next = m_axis_cpl_enqueue_commit_valid_reg & ~m_axis_cpl_enqueue_commit_ready;

    m_axis_dma_write_desc_dma_addr_next = m_axis_dma_write_desc_dma_addr_reg;
    m_axis_dma_write_desc_function_id_next = m_axis_dma_write_desc_function_id_reg; // Scott
    m_axis_dma_write_desc_ram_addr_next = m_axis_dma_write_desc_ram_addr_reg;
    m_axis_dma_write_desc_len_next = m_axis_dma_write_desc_len_reg;
    m_axis_dma_write_desc_tag_next = m_axis_dma_write_desc_tag_reg;
    m_axis_dma_write_desc_valid_next = m_axis_dma_write_desc_valid_reg && !m_axis_dma_write_desc_ready;

    desc_table_start_sel = s_axis_req_sel;
    desc_table_start_tag = s_axis_req_tag;
    desc_table_start_data = s_axis_req_data;
    desc_table_start_en = 1'b0;
    desc_table_enqueue_ptr = s_axis_cpl_enqueue_resp_tag[enqueue_resp_enc*QUEUE_REQ_TAG_WIDTH +: QUEUE_REQ_TAG_WIDTH] & DESC_PTR_MASK;
    desc_table_enqueue_phase = s_axis_cpl_enqueue_resp_phase[enqueue_resp_enc];
    desc_table_enqueue_queue_op_tag = s_axis_cpl_enqueue_resp_op_tag[enqueue_resp_enc*QUEUE_OP_TAG_WIDTH +: QUEUE_OP_TAG_WIDTH];
    desc_table_enqueue_invalid = 1'b0;
    desc_table_enqueue_en = 1'b0;
    desc_table_cpl_write_done_ptr = s_axis_dma_write_desc_status_tag & DESC_PTR_MASK;
    desc_table_cpl_write_done_en = 1'b0;
    desc_table_finish_en = 1'b0;

    // queue query
    // wait for descriptor request
    s_axis_req_ready_next = enable && !desc_table_active[desc_table_start_ptr_reg & DESC_PTR_MASK] && ($unsigned(desc_table_start_ptr_reg - desc_table_finish_ptr_reg) < DESC_TABLE_SIZE) && (!m_axis_cpl_enqueue_req_valid || (m_axis_cpl_enqueue_req_valid & m_axis_cpl_enqueue_req_ready));
    if (s_axis_req_ready && s_axis_req_valid) begin
        s_axis_req_ready_next = 1'b0;

        // store in descriptor table
        desc_table_start_sel = s_axis_req_sel;
        desc_table_start_tag = s_axis_req_tag;
        desc_table_start_data = s_axis_req_data;
        desc_table_start_en = 1'b1;

        // initiate queue query
        m_axis_cpl_enqueue_req_queue_next = s_axis_req_queue;
        m_axis_cpl_enqueue_req_tag_next = desc_table_start_ptr_reg & DESC_PTR_MASK;
        m_axis_cpl_enqueue_req_valid_next = 1 << s_axis_req_sel;
    end

    // start completion write
    // wait for queue query response
    if (enqueue_resp_enc_valid && !m_axis_dma_write_desc_valid_reg) begin
        s_axis_cpl_enqueue_resp_ready_next = 1 << enqueue_resp_enc;

        // update entry in descriptor table
        desc_table_enqueue_ptr = s_axis_cpl_enqueue_resp_tag[enqueue_resp_enc*QUEUE_REQ_TAG_WIDTH +: QUEUE_REQ_TAG_WIDTH] & DESC_PTR_MASK;
        desc_table_enqueue_phase = s_axis_cpl_enqueue_resp_phase[enqueue_resp_enc];
        desc_table_enqueue_queue_op_tag = s_axis_cpl_enqueue_resp_op_tag[enqueue_resp_enc*QUEUE_OP_TAG_WIDTH +: QUEUE_OP_TAG_WIDTH];
        desc_table_enqueue_invalid = 1'b0;
        desc_table_enqueue_en = 1'b1;

        // return descriptor request completion
        m_axis_req_status_tag_next = desc_table_tag[s_axis_cpl_enqueue_resp_tag[enqueue_resp_enc*QUEUE_REQ_TAG_WIDTH +: QUEUE_REQ_TAG_WIDTH] & DESC_PTR_MASK];
        m_axis_req_status_full_next = s_axis_cpl_enqueue_resp_full[enqueue_resp_enc*1 +: 1];
        m_axis_req_status_error_next = s_axis_cpl_enqueue_resp_error[enqueue_resp_enc*1 +: 1];
        m_axis_req_status_valid_next = 1'b1;

        // initiate completion write
        m_axis_dma_write_desc_dma_addr_next = s_axis_cpl_enqueue_resp_addr[enqueue_resp_enc*DMA_ADDR_WIDTH +: DMA_ADDR_WIDTH];
        m_axis_dma_write_desc_function_id_next = s_axis_cpl_enqueue_resp_function_id[enqueue_resp_enc*FUNCTION_ID_WIDTH +: FUNCTION_ID_WIDTH]; // Scott
        m_axis_dma_write_desc_ram_addr_next = (s_axis_cpl_enqueue_resp_tag[enqueue_resp_enc*QUEUE_REQ_TAG_WIDTH +: QUEUE_REQ_TAG_WIDTH] & DESC_PTR_MASK) << $clog2(SEG_COUNT*SEG_BE_WIDTH);
        m_axis_dma_write_desc_len_next = CPL_SIZE;
        m_axis_dma_write_desc_tag_next = (s_axis_cpl_enqueue_resp_tag[enqueue_resp_enc*QUEUE_REQ_TAG_WIDTH +: QUEUE_REQ_TAG_WIDTH] & DESC_PTR_MASK);

        if (s_axis_cpl_enqueue_resp_error[enqueue_resp_enc*1 +: 1] || s_axis_cpl_enqueue_resp_full[enqueue_resp_enc*1 +: 1]) begin
            // queue empty or not active

            // invalidate entry
            desc_table_enqueue_invalid = 1'b1;
        end else begin
            // descriptor available to enqueue

            // initiate completion write
            m_axis_dma_write_desc_valid_next = 1'b1;
        end
    end

    // finish completion write
    if (s_axis_dma_write_desc_status_valid) begin
        // update entry in descriptor table
        desc_table_cpl_write_done_ptr = s_axis_dma_write_desc_status_tag & DESC_PTR_MASK;
        desc_table_cpl_write_done_en = 1'b1;
    end

    // operation complete
    if (desc_table_active[desc_table_finish_ptr_reg & DESC_PTR_MASK] && desc_table_finish_ptr_reg != desc_table_start_ptr_reg) begin
        if (desc_table_invalid[desc_table_finish_ptr_reg & DESC_PTR_MASK]) begin
            // invalidate entry in descriptor table
            desc_table_finish_en = 1'b1;

        end else if (desc_table_cpl_write_done[desc_table_finish_ptr_reg & DESC_PTR_MASK] && !m_axis_cpl_enqueue_commit_valid) begin
            // invalidate entry in descriptor table
            desc_table_finish_en = 1'b1;

            // commit enqueue operation
            m_axis_cpl_enqueue_commit_op_tag_next = desc_table_queue_op_tag[desc_table_finish_ptr_reg & DESC_PTR_MASK];
            m_axis_cpl_enqueue_commit_valid_next = 1 << desc_table_sel[desc_table_finish_ptr_reg & DESC_PTR_MASK];
        end
    end
end

always @(posedge clk) begin
    s_axis_req_ready_reg <= s_axis_req_ready_next;

    m_axis_req_status_tag_reg <= m_axis_req_status_tag_next;
    m_axis_req_status_full_reg <= m_axis_req_status_full_next;
    m_axis_req_status_error_reg <= m_axis_req_status_error_next;
    m_axis_req_status_valid_reg <= m_axis_req_status_valid_next;

    m_axis_cpl_enqueue_req_queue_reg <= m_axis_cpl_enqueue_req_queue_next;
    m_axis_cpl_enqueue_req_tag_reg <= m_axis_cpl_enqueue_req_tag_next;
    m_axis_cpl_enqueue_req_valid_reg <= m_axis_cpl_enqueue_req_valid_next;

    s_axis_cpl_enqueue_resp_ready_reg <= s_axis_cpl_enqueue_resp_ready_next;

    m_axis_cpl_enqueue_commit_op_tag_reg <= m_axis_cpl_enqueue_commit_op_tag_next;
    m_axis_cpl_enqueue_commit_valid_reg <= m_axis_cpl_enqueue_commit_valid_next;

    m_axis_dma_write_desc_dma_addr_reg <= m_axis_dma_write_desc_dma_addr_next;
    m_axis_dma_write_desc_function_id_reg <= m_axis_dma_write_desc_function_id_next; // Scott
    m_axis_dma_write_desc_ram_addr_reg <= m_axis_dma_write_desc_ram_addr_next;
    m_axis_dma_write_desc_len_reg <= m_axis_dma_write_desc_len_next;
    m_axis_dma_write_desc_tag_reg <= m_axis_dma_write_desc_tag_next;
    m_axis_dma_write_desc_valid_reg <= m_axis_dma_write_desc_valid_next;

    if (desc_table_start_en) begin
        desc_table_active[desc_table_start_ptr_reg & DESC_PTR_MASK] <= 1'b1;
        desc_table_invalid[desc_table_start_ptr_reg & DESC_PTR_MASK] <= 1'b0;
        desc_table_cpl_write_done[desc_table_start_ptr_reg & DESC_PTR_MASK] <= 1'b0;
        desc_table_sel[desc_table_start_ptr_reg & DESC_PTR_MASK] <= desc_table_start_sel;
        desc_table_tag[desc_table_start_ptr_reg & DESC_PTR_MASK] <= desc_table_start_tag;
        desc_table_data[desc_table_start_ptr_reg & DESC_PTR_MASK] <= desc_table_start_data;
        desc_table_start_ptr_reg <= desc_table_start_ptr_reg + 1;
    end

    if (desc_table_enqueue_en) begin
        desc_table_phase[desc_table_enqueue_ptr & DESC_PTR_MASK] <= desc_table_enqueue_phase;
        desc_table_queue_op_tag[desc_table_enqueue_ptr & DESC_PTR_MASK] <= desc_table_enqueue_queue_op_tag;
        desc_table_invalid[desc_table_enqueue_ptr & DESC_PTR_MASK] <= desc_table_enqueue_invalid;
    end

    if (desc_table_cpl_write_done_en) begin
        desc_table_cpl_write_done[desc_table_cpl_write_done_ptr & DESC_PTR_MASK] <= 1'b1;
    end

    if (desc_table_finish_en) begin
        desc_table_active[desc_table_finish_ptr_reg & DESC_PTR_MASK] <= 1'b0;
        desc_table_finish_ptr_reg <= desc_table_finish_ptr_reg + 1;
    end

    if (rst) begin
        s_axis_req_ready_reg <= 1'b0;
        m_axis_req_status_valid_reg <= 1'b0;
        m_axis_cpl_enqueue_req_valid_reg <= 1'b0;
        s_axis_cpl_enqueue_resp_ready_reg <= 1'b0;
        m_axis_cpl_enqueue_commit_valid_reg <= 1'b0;
        m_axis_dma_write_desc_valid_reg <= 1'b0;

        desc_table_active <= 0;
        desc_table_invalid <= 0;

        desc_table_start_ptr_reg <= 0;
        desc_table_finish_ptr_reg <= 0;
    end
end

endmodule

`resetall
