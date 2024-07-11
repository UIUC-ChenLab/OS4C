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
 * Completion queue manager
 */
module cpl_queue_manager #
(
    // Base address width
    parameter ADDR_WIDTH = 64,
    // Request tag field width
    parameter REQ_TAG_WIDTH = 8,
    // Number of outstanding operations
    parameter OP_TABLE_SIZE = 16,
    // Operation tag field width
    parameter OP_TAG_WIDTH = 8,
    // Queue index width (log2 of number of queues)
    parameter QUEUE_INDEX_WIDTH = 8,
    // Event index width
    parameter EVENT_WIDTH = 8,
    // Queue element pointer width (log2 of number of elements)
    parameter QUEUE_PTR_WIDTH = 16,
    // Function ID index width (log2 of number of function IDs)
    parameter FUNCTION_ID_WIDTH = 8, // Scott
    // Filter the Event Queue Pointer
    parameter FILTER_EQ_PTR = 1, // Scott
    // Log queue size field width
    parameter LOG_QUEUE_SIZE_WIDTH = $clog2(QUEUE_PTR_WIDTH),
    // Queue element size
    parameter CPL_SIZE = 16,
    // Pipeline stages
    parameter PIPELINE = 2,
    // Width of AXI lite data bus in bits
    parameter AXIL_DATA_WIDTH = 32,
    // Width of AXI lite address bus in bits
    parameter AXIL_ADDR_WIDTH = QUEUE_INDEX_WIDTH+4,
    // Width of AXI lite wstrb (width of data bus in words)
    parameter AXIL_STRB_WIDTH = (AXIL_DATA_WIDTH/8)
)
(
    input  wire                         clk,
    input  wire                         rst,

    /*
     * Enqueue request input
     */
    input  wire [QUEUE_INDEX_WIDTH-1:0] s_axis_enqueue_req_queue,
    input  wire [REQ_TAG_WIDTH-1:0]     s_axis_enqueue_req_tag,
    input  wire                         s_axis_enqueue_req_valid,
    output wire                         s_axis_enqueue_req_ready,

    /*
     * Enqueue response output
     */
    output wire [QUEUE_INDEX_WIDTH-1:0] m_axis_enqueue_resp_queue,
    output wire [QUEUE_PTR_WIDTH-1:0]   m_axis_enqueue_resp_ptr,
    output wire                         m_axis_enqueue_resp_phase,
    output wire [ADDR_WIDTH-1:0]        m_axis_enqueue_resp_addr,
    output wire [EVENT_WIDTH-1:0]       m_axis_enqueue_resp_event,
    output wire [REQ_TAG_WIDTH-1:0]     m_axis_enqueue_resp_tag,
    output wire [OP_TAG_WIDTH-1:0]      m_axis_enqueue_resp_op_tag,
    output wire [FUNCTION_ID_WIDTH-1:0] m_axis_enqueue_resp_function_id, // Scott: add function ID
    output wire                         m_axis_enqueue_resp_full,
    output wire                         m_axis_enqueue_resp_error,
    output wire                         m_axis_enqueue_resp_valid,
    input  wire                         m_axis_enqueue_resp_ready,

    /*
     * Enqueue commit input
     */
    input  wire [OP_TAG_WIDTH-1:0]      s_axis_enqueue_commit_op_tag,
    input  wire                         s_axis_enqueue_commit_valid,
    output wire                         s_axis_enqueue_commit_ready,

    /*
     * Event output
     */
    output wire [EVENT_WIDTH-1:0]       m_axis_event,
    output wire [FUNCTION_ID_WIDTH-1:0] m_axis_event_function_id, // Scott
    output wire [QUEUE_INDEX_WIDTH-1:0] m_axis_event_source,
    output wire                         m_axis_event_valid,
    input  wire                         m_axis_event_ready,

    /*
     * AXI-Lite slave interface
     */
    input  wire [AXIL_ADDR_WIDTH-1:0]   s_axil_awaddr,
    input  wire [FUNCTION_ID_WIDTH-1:0] s_axil_awuser, // Scott
    input  wire [2:0]                   s_axil_awprot,
    input  wire                         s_axil_awvalid,
    output wire                         s_axil_awready,
    input  wire [AXIL_DATA_WIDTH-1:0]   s_axil_wdata,
    input  wire [AXIL_STRB_WIDTH-1:0]   s_axil_wstrb,
    input  wire                         s_axil_wvalid,
    output wire                         s_axil_wready,
    output wire [1:0]                   s_axil_bresp,
    output wire                         s_axil_bvalid,
    input  wire                         s_axil_bready,
    input  wire [AXIL_ADDR_WIDTH-1:0]   s_axil_araddr,
    input  wire [FUNCTION_ID_WIDTH-1:0] s_axil_aruser, // Scott
    input  wire [2:0]                   s_axil_arprot,
    input  wire                         s_axil_arvalid,
    output wire                         s_axil_arready,
    output wire [AXIL_DATA_WIDTH-1:0]   s_axil_rdata,
    output wire [1:0]                   s_axil_rresp,
    output wire                         s_axil_rvalid,
    input  wire                         s_axil_rready,

    /*
     * Configuration
     */
    input  wire                         enable
);

parameter QUEUE_COUNT = 2**QUEUE_INDEX_WIDTH;

parameter CL_OP_TABLE_SIZE = $clog2(OP_TABLE_SIZE);

parameter CL_CPL_SIZE = $clog2(CPL_SIZE);

parameter EVENT_QUEUES_PER_FUNC = (2**EVENT_WIDTH) / (2**FUNCTION_ID_WIDTH); // Scott
parameter LOG_QUEUES_PER_FUNC = FILTER_EQ_PTR == 1 ? $clog2(EVENT_QUEUES_PER_FUNC) : 2; // Scott

// Scott: Change total size to be 136 to hold VF ID
parameter QUEUE_RAM_BE_WIDTH = 17;
parameter QUEUE_RAM_WIDTH = QUEUE_RAM_BE_WIDTH*8;

// bus width assertions
initial begin
    if (OP_TAG_WIDTH < CL_OP_TABLE_SIZE) begin
        $error("Error: OP_TAG_WIDTH insufficient for OP_TABLE_SIZE (instance %m)");
        $finish;
    end

    if (AXIL_DATA_WIDTH != 32) begin
        $error("Error: AXI lite interface width must be 32 (instance %m)");
        $finish;
    end

    if (AXIL_STRB_WIDTH * 8 != AXIL_DATA_WIDTH) begin
        $error("Error: AXI lite interface requires byte (8-bit) granularity (instance %m)");
        $finish;
    end

    if (AXIL_ADDR_WIDTH < QUEUE_INDEX_WIDTH+4) begin
        $error("Error: AXI lite address width too narrow (instance %m)");
        $finish;
    end

    if (2**$clog2(CPL_SIZE) != CPL_SIZE) begin
        $error("Error: Completion size must be even power of two (instance %m)");
        $finish;
    end

    if (PIPELINE < 2) begin
        $error("Error: PIPELINE must be at least 2 (instance %m)");
        $finish;
    end
end

reg op_axil_write_pipe_hazard;
reg op_axil_read_pipe_hazard;
reg op_req_pipe_hazard;
reg op_commit_pipe_hazard;
reg stage_active;

reg [PIPELINE-1:0] op_axil_write_pipe_reg = {PIPELINE{1'b0}}, op_axil_write_pipe_next;
reg [PIPELINE-1:0] op_axil_read_pipe_reg = {PIPELINE{1'b0}}, op_axil_read_pipe_next;
reg [PIPELINE-1:0] op_req_pipe_reg = {PIPELINE{1'b0}}, op_req_pipe_next;
reg [PIPELINE-1:0] op_commit_pipe_reg = {PIPELINE{1'b0}}, op_commit_pipe_next;

reg [QUEUE_INDEX_WIDTH-1:0] queue_ram_addr_pipeline_reg[PIPELINE-1:0], queue_ram_addr_pipeline_next[PIPELINE-1:0];
reg [1:0] axil_reg_pipeline_reg[PIPELINE-1:0], axil_reg_pipeline_next[PIPELINE-1:0];
reg [FUNCTION_ID_WIDTH-1:0] axil_reg_pipeline_function_id_reg[PIPELINE-1:0], axil_reg_pipeline_function_id_next[PIPELINE-1:0];
reg [AXIL_DATA_WIDTH-1:0] write_data_pipeline_reg[PIPELINE-1:0], write_data_pipeline_next[PIPELINE-1:0];
reg [AXIL_STRB_WIDTH-1:0] write_strobe_pipeline_reg[PIPELINE-1:0], write_strobe_pipeline_next[PIPELINE-1:0];
reg [REQ_TAG_WIDTH-1:0] req_tag_pipeline_reg[PIPELINE-1:0], req_tag_pipeline_next[PIPELINE-1:0];

reg s_axis_enqueue_req_ready_reg = 1'b0, s_axis_enqueue_req_ready_next;

reg [QUEUE_INDEX_WIDTH-1:0] m_axis_enqueue_resp_queue_reg = 0, m_axis_enqueue_resp_queue_next;
reg [QUEUE_PTR_WIDTH-1:0] m_axis_enqueue_resp_ptr_reg = 0, m_axis_enqueue_resp_ptr_next;
reg m_axis_enqueue_resp_phase_reg = 0, m_axis_enqueue_resp_phase_next;
reg [ADDR_WIDTH-1:0] m_axis_enqueue_resp_addr_reg = 0, m_axis_enqueue_resp_addr_next;
reg [EVENT_WIDTH-1:0] m_axis_enqueue_resp_event_reg = 0, m_axis_enqueue_resp_event_next;
reg [REQ_TAG_WIDTH-1:0] m_axis_enqueue_resp_tag_reg = 0, m_axis_enqueue_resp_tag_next;
reg [OP_TAG_WIDTH-1:0] m_axis_enqueue_resp_op_tag_reg = 0, m_axis_enqueue_resp_op_tag_next;
reg [FUNCTION_ID_WIDTH-1:0] m_axis_enqueue_resp_function_id_reg = 0, m_axis_enqueue_resp_function_id_next; // Scott: add associated logic for passing function ID out of enqueue signals.
reg m_axis_enqueue_resp_full_reg = 1'b0, m_axis_enqueue_resp_full_next;
reg m_axis_enqueue_resp_error_reg = 1'b0, m_axis_enqueue_resp_error_next;
reg m_axis_enqueue_resp_valid_reg = 1'b0, m_axis_enqueue_resp_valid_next;

reg s_axis_enqueue_commit_ready_reg = 1'b0, s_axis_enqueue_commit_ready_next;

reg [EVENT_WIDTH-1:0] m_axis_event_reg = 0, m_axis_event_next;
reg [FUNCTION_ID_WIDTH-1:0] m_axis_event_function_id_reg, m_axis_event_function_id_next; // Scott
reg [QUEUE_INDEX_WIDTH-1:0] m_axis_event_source_reg = 0, m_axis_event_source_next;
reg m_axis_event_valid_reg = 1'b0, m_axis_event_valid_next;

reg s_axil_awready_reg = 0, s_axil_awready_next;
reg s_axil_wready_reg = 0, s_axil_wready_next;
reg s_axil_bvalid_reg = 0, s_axil_bvalid_next;
reg s_axil_arready_reg = 0, s_axil_arready_next;
reg [AXIL_DATA_WIDTH-1:0] s_axil_rdata_reg = 0, s_axil_rdata_next;
reg s_axil_rvalid_reg = 0, s_axil_rvalid_next;

(* ramstyle = "no_rw_check" *)
reg [QUEUE_RAM_WIDTH-1:0] queue_ram[QUEUE_COUNT-1:0];
reg [QUEUE_INDEX_WIDTH-1:0] queue_ram_read_ptr;
reg [QUEUE_INDEX_WIDTH-1:0] queue_ram_write_ptr;
reg [QUEUE_RAM_WIDTH-1:0] queue_ram_write_data;
reg queue_ram_wr_en;
reg [QUEUE_RAM_BE_WIDTH-1:0] queue_ram_be;
reg [QUEUE_RAM_WIDTH-1:0] queue_ram_read_data_reg = 0;
reg [QUEUE_RAM_WIDTH-1:0] queue_ram_read_data_pipeline_reg[PIPELINE-1:1];

wire [QUEUE_PTR_WIDTH-1:0] queue_ram_read_data_prod_ptr = queue_ram_read_data_pipeline_reg[PIPELINE-1][15:0];
wire [QUEUE_PTR_WIDTH-1:0] queue_ram_read_data_cons_ptr = queue_ram_read_data_pipeline_reg[PIPELINE-1][31:16];
wire [EVENT_WIDTH-1:0] queue_ram_read_data_event = queue_ram_read_data_pipeline_reg[PIPELINE-1][47:32];
wire [LOG_QUEUE_SIZE_WIDTH-1:0] queue_ram_read_data_log_size = queue_ram_read_data_pipeline_reg[PIPELINE-1][51:48];
wire queue_ram_read_data_continuous = queue_ram_read_data_pipeline_reg[PIPELINE-1][53];
wire queue_ram_read_data_armed = queue_ram_read_data_pipeline_reg[PIPELINE-1][54];
wire queue_ram_read_data_enable = queue_ram_read_data_pipeline_reg[PIPELINE-1][55];
wire [CL_OP_TABLE_SIZE-1:0] queue_ram_read_data_op_index = queue_ram_read_data_pipeline_reg[PIPELINE-1][63:56];
wire [FUNCTION_ID_WIDTH-1:0] queue_ram_read_data_function_id = queue_ram_read_data_pipeline_reg[PIPELINE-1][71:64]; // Scott
wire [ADDR_WIDTH-1:0] queue_ram_read_data_base_addr = {queue_ram_read_data_pipeline_reg[PIPELINE-1][127:76], 12'd0};

reg [OP_TABLE_SIZE-1:0] op_table_active = 0;
reg [OP_TABLE_SIZE-1:0] op_table_commit = 0;
(* ram_style = "distributed", ramstyle = "no_rw_check, mlab" *)
reg [QUEUE_INDEX_WIDTH-1:0] op_table_queue[OP_TABLE_SIZE-1:0];
(* ram_style = "distributed", ramstyle = "no_rw_check, mlab" *)
reg [QUEUE_PTR_WIDTH-1:0] op_table_queue_ptr[OP_TABLE_SIZE-1:0];
reg [CL_OP_TABLE_SIZE-1:0] op_table_start_ptr_reg = 0;
reg [QUEUE_INDEX_WIDTH-1:0] op_table_start_queue;
reg [QUEUE_PTR_WIDTH-1:0] op_table_start_queue_ptr;
reg op_table_start_en;
reg [CL_OP_TABLE_SIZE-1:0] op_table_commit_ptr;
reg op_table_commit_en;
reg [CL_OP_TABLE_SIZE-1:0] op_table_finish_ptr_reg = 0;
reg op_table_finish_en;

assign s_axis_enqueue_req_ready = s_axis_enqueue_req_ready_reg;

assign m_axis_enqueue_resp_queue = m_axis_enqueue_resp_queue_reg;
assign m_axis_enqueue_resp_ptr = m_axis_enqueue_resp_ptr_reg;
assign m_axis_enqueue_resp_phase = m_axis_enqueue_resp_phase_reg;
assign m_axis_enqueue_resp_addr = m_axis_enqueue_resp_addr_reg;
assign m_axis_enqueue_resp_event = m_axis_enqueue_resp_event_reg;
assign m_axis_enqueue_resp_tag = m_axis_enqueue_resp_tag_reg;
assign m_axis_enqueue_resp_op_tag = m_axis_enqueue_resp_op_tag_reg;
assign m_axis_enqueue_resp_function_id = m_axis_enqueue_resp_function_id_reg; // Scott
assign m_axis_enqueue_resp_full = m_axis_enqueue_resp_full_reg;
assign m_axis_enqueue_resp_error = m_axis_enqueue_resp_error_reg;
assign m_axis_enqueue_resp_valid = m_axis_enqueue_resp_valid_reg;

assign s_axis_enqueue_commit_ready = s_axis_enqueue_commit_ready_reg;

assign m_axis_event = m_axis_event_reg;
assign m_axis_event_function_id = m_axis_event_function_id_reg; // Scott
assign m_axis_event_source = m_axis_event_source_reg;
assign m_axis_event_valid = m_axis_event_valid_reg;

assign s_axil_awready = s_axil_awready_reg;
assign s_axil_wready = s_axil_wready_reg;
assign s_axil_bresp = 2'b00;
assign s_axil_bvalid = s_axil_bvalid_reg;
assign s_axil_arready = s_axil_arready_reg;
assign s_axil_rdata = s_axil_rdata_reg;
assign s_axil_rresp = 2'b00;
assign s_axil_rvalid = s_axil_rvalid_reg;

wire [QUEUE_INDEX_WIDTH-1:0] s_axil_awaddr_queue = s_axil_awaddr >> 4;
wire [1:0] s_axil_awaddr_reg = s_axil_awaddr >> 2;
wire [FUNCTION_ID_WIDTH-1:0] s_axil_awuser_reg = s_axil_awuser; // Scott
wire [QUEUE_INDEX_WIDTH-1:0] s_axil_araddr_queue = s_axil_araddr >> 4;
wire [1:0] s_axil_araddr_reg = s_axil_araddr >> 2;
wire [FUNCTION_ID_WIDTH-1:0] s_axil_aruser_reg = s_axil_aruser; // Scott

wire queue_active = op_table_active[queue_ram_read_data_op_index] && op_table_queue[queue_ram_read_data_op_index] == queue_ram_addr_pipeline_reg[PIPELINE-1];
wire queue_full_idle = ($unsigned(queue_ram_read_data_prod_ptr - queue_ram_read_data_cons_ptr) & ({QUEUE_PTR_WIDTH{1'b1}} << queue_ram_read_data_log_size)) != 0;
wire queue_full_active = ($unsigned(op_table_queue_ptr[queue_ram_read_data_op_index] - queue_ram_read_data_cons_ptr) & ({QUEUE_PTR_WIDTH{1'b1}} << queue_ram_read_data_log_size)) != 0;
wire queue_full = queue_active ? queue_full_active : queue_full_idle;
wire [QUEUE_PTR_WIDTH-1:0] queue_ram_read_active_prod_ptr = queue_active ? op_table_queue_ptr[queue_ram_read_data_op_index] : queue_ram_read_data_prod_ptr;

integer i, j;

initial begin
    // break up loop to work around iteration termination
    for (i = 0; i < 2**QUEUE_INDEX_WIDTH; i = i + 2**(QUEUE_INDEX_WIDTH/2)) begin
        for (j = i; j < i + 2**(QUEUE_INDEX_WIDTH/2); j = j + 1) begin
            queue_ram[j] = 0;
        end
    end

    for (i = 0; i < PIPELINE; i = i + 1) begin
        queue_ram_addr_pipeline_reg[i] = 0;
        axil_reg_pipeline_reg[i] = 0;
        axil_reg_pipeline_function_id_reg[i] = 0; //Scott
        write_data_pipeline_reg[i] = 0;
        write_strobe_pipeline_reg[i] = 0;
        req_tag_pipeline_reg[i] = 0;
    end

    for (i = 0; i < OP_TABLE_SIZE; i = i + 1) begin
        op_table_queue[i] = 0;
        op_table_queue_ptr[i] = 0;
    end
end

always @* begin
    op_axil_write_pipe_next = {op_axil_write_pipe_reg, 1'b0};
    op_axil_read_pipe_next = {op_axil_read_pipe_reg, 1'b0};
    op_req_pipe_next = {op_req_pipe_reg, 1'b0};
    op_commit_pipe_next = {op_commit_pipe_reg, 1'b0};

    queue_ram_addr_pipeline_next[0] = 0;
    axil_reg_pipeline_next[0] = 0;
    axil_reg_pipeline_function_id_next[0] = 0;
    write_data_pipeline_next[0] = 0;
    write_strobe_pipeline_next[0] = 0;
    req_tag_pipeline_next[0] = 0;
    for (j = 1; j < PIPELINE; j = j + 1) begin
        queue_ram_addr_pipeline_next[j] = queue_ram_addr_pipeline_reg[j-1];
        axil_reg_pipeline_next[j] = axil_reg_pipeline_reg[j-1];
        axil_reg_pipeline_function_id_next[j] = axil_reg_pipeline_function_id_reg[j-1];
        write_data_pipeline_next[j] = write_data_pipeline_reg[j-1];
        write_strobe_pipeline_next[j] = write_strobe_pipeline_reg[j-1];
        req_tag_pipeline_next[j] = req_tag_pipeline_reg[j-1];
    end

    s_axis_enqueue_req_ready_next = 1'b0;

    // default values, stay the same 
    m_axis_enqueue_resp_queue_next = m_axis_enqueue_resp_queue_reg;
    m_axis_enqueue_resp_ptr_next = m_axis_enqueue_resp_ptr_reg;
    m_axis_enqueue_resp_phase_next = m_axis_enqueue_resp_phase_reg;
    m_axis_enqueue_resp_addr_next = m_axis_enqueue_resp_addr_reg;
    m_axis_enqueue_resp_event_next = m_axis_enqueue_resp_event_reg;
    m_axis_enqueue_resp_tag_next = m_axis_enqueue_resp_tag_reg;
    m_axis_enqueue_resp_op_tag_next = m_axis_enqueue_resp_op_tag_reg;
    m_axis_enqueue_resp_function_id_next = m_axis_enqueue_resp_function_id_reg; // Scott
    m_axis_enqueue_resp_full_next = m_axis_enqueue_resp_full_reg;
    m_axis_enqueue_resp_error_next = m_axis_enqueue_resp_error_reg;
    m_axis_enqueue_resp_valid_next = m_axis_enqueue_resp_valid_reg && !m_axis_enqueue_resp_ready;

    s_axis_enqueue_commit_ready_next = 1'b0;

    m_axis_event_next = m_axis_event_reg;
    m_axis_event_source_next = m_axis_event_source_reg;
    m_axis_event_function_id_next = m_axis_event_function_id_reg; // Scott
    m_axis_event_valid_next = m_axis_event_valid_reg && !m_axis_event_ready;

    s_axil_awready_next = 1'b0;
    s_axil_wready_next = 1'b0;
    s_axil_bvalid_next = s_axil_bvalid_reg && !s_axil_bready;

    s_axil_arready_next = 1'b0;
    s_axil_rdata_next = s_axil_rdata_reg;
    s_axil_rvalid_next = s_axil_rvalid_reg && !s_axil_rready;

    queue_ram_read_ptr = 0;
    queue_ram_write_ptr = queue_ram_addr_pipeline_reg[PIPELINE-1];
    queue_ram_write_data = queue_ram_read_data_pipeline_reg[PIPELINE-1];
    queue_ram_wr_en = 0;
    queue_ram_be = 0;

    op_table_start_queue = queue_ram_addr_pipeline_reg[PIPELINE-1];
    op_table_start_queue_ptr = queue_ram_read_active_prod_ptr + 1;
    op_table_start_en = 1'b0;
    op_table_commit_ptr = s_axis_enqueue_commit_op_tag;
    op_table_commit_en = 1'b0;
    op_table_finish_en = 1'b0;

    op_axil_write_pipe_hazard = 1'b0;
    op_axil_read_pipe_hazard = 1'b0;
    op_req_pipe_hazard = 1'b0;
    op_commit_pipe_hazard = 1'b0;
    stage_active = 1'b0;

    for (j = 0; j < PIPELINE; j = j + 1) begin
        stage_active = op_axil_write_pipe_reg[j] || op_axil_read_pipe_reg[j] || op_req_pipe_reg[j] || op_commit_pipe_reg[j];
        op_axil_write_pipe_hazard = op_axil_write_pipe_hazard || (stage_active && queue_ram_addr_pipeline_reg[j] == s_axil_awaddr_queue);
        op_axil_read_pipe_hazard = op_axil_read_pipe_hazard || (stage_active && queue_ram_addr_pipeline_reg[j] == s_axil_araddr_queue);
        op_req_pipe_hazard = op_req_pipe_hazard || (stage_active && queue_ram_addr_pipeline_reg[j] == s_axis_enqueue_req_queue);
        op_commit_pipe_hazard = op_commit_pipe_hazard || (stage_active && queue_ram_addr_pipeline_reg[j] == op_table_queue[op_table_finish_ptr_reg]);
    end

    // pipeline stage 0 - receive request
    if (s_axil_awvalid && s_axil_wvalid && (!s_axil_bvalid || s_axil_bready) && !op_axil_write_pipe_reg && !op_axil_write_pipe_hazard) begin
        // AXIL write
        op_axil_write_pipe_next[0] = 1'b1;

        s_axil_awready_next = 1'b1;
        s_axil_wready_next = 1'b1;

        write_data_pipeline_next[0] = s_axil_wdata;
        write_strobe_pipeline_next[0] = s_axil_wstrb;

        queue_ram_read_ptr = s_axil_awaddr_queue;
        queue_ram_addr_pipeline_next[0] = s_axil_awaddr_queue;
        axil_reg_pipeline_next[0] = s_axil_awaddr_reg;
        axil_reg_pipeline_function_id_next[0] = s_axil_awuser_reg; // Scott
    end else if (s_axil_arvalid && (!s_axil_rvalid || s_axil_rready) && !op_axil_read_pipe_reg && !op_axil_read_pipe_hazard) begin
        // AXIL read
        op_axil_read_pipe_next[0] = 1'b1;

        s_axil_arready_next = 1'b1;

        queue_ram_read_ptr = s_axil_araddr_queue;
        queue_ram_addr_pipeline_next[0] = s_axil_araddr_queue;
        axil_reg_pipeline_next[0] = s_axil_araddr_reg;
        axil_reg_pipeline_function_id_next[0] = s_axil_aruser_reg; // Scott

    end else if (op_table_active[op_table_finish_ptr_reg] && op_table_commit[op_table_finish_ptr_reg] && (!m_axis_event_valid_reg || m_axis_event_ready) && !op_commit_pipe_reg && !op_commit_pipe_hazard) begin
        // enqueue commit finalize (update pointer)
        op_commit_pipe_next[0] = 1'b1;

        op_table_finish_en = 1'b1;

        write_data_pipeline_next[0] = op_table_queue_ptr[op_table_finish_ptr_reg];

        queue_ram_read_ptr = op_table_queue[op_table_finish_ptr_reg];
        queue_ram_addr_pipeline_next[0] = op_table_queue[op_table_finish_ptr_reg];
    end else if (enable && !op_table_active[op_table_start_ptr_reg] && s_axis_enqueue_req_valid && (!m_axis_enqueue_resp_valid || m_axis_enqueue_resp_ready) && !op_req_pipe_reg && !op_req_pipe_hazard) begin
        // enqueue request
        op_req_pipe_next[0] = 1'b1;

        s_axis_enqueue_req_ready_next = 1'b1;

        req_tag_pipeline_next[0] = s_axis_enqueue_req_tag;

        queue_ram_read_ptr = s_axis_enqueue_req_queue;
        queue_ram_addr_pipeline_next[0] = s_axis_enqueue_req_queue;
    end

    // read complete, perform operation
    if (op_req_pipe_reg[PIPELINE-1]) begin
        // request
        m_axis_enqueue_resp_queue_next = queue_ram_addr_pipeline_reg[PIPELINE-1];
        m_axis_enqueue_resp_ptr_next = queue_ram_read_active_prod_ptr;
        m_axis_enqueue_resp_phase_next = !queue_ram_read_active_prod_ptr[queue_ram_read_data_log_size];
        m_axis_enqueue_resp_addr_next = queue_ram_read_data_base_addr + ((queue_ram_read_active_prod_ptr & ({QUEUE_PTR_WIDTH{1'b1}} >> (QUEUE_PTR_WIDTH - queue_ram_read_data_log_size))) * CPL_SIZE);
        m_axis_enqueue_resp_event_next = queue_ram_read_data_event;
        m_axis_enqueue_resp_tag_next = req_tag_pipeline_reg[PIPELINE-1];
        m_axis_enqueue_resp_op_tag_next = op_table_start_ptr_reg;
        m_axis_enqueue_resp_function_id_next = queue_ram_read_data_function_id; // Scott
        m_axis_enqueue_resp_full_next = 1'b0;
        m_axis_enqueue_resp_error_next = 1'b0;

        queue_ram_write_ptr = queue_ram_addr_pipeline_reg[PIPELINE-1];
        queue_ram_write_data[63:56] = op_table_start_ptr_reg;
        queue_ram_wr_en = 1'b1;

        op_table_start_queue = queue_ram_addr_pipeline_reg[PIPELINE-1];
        op_table_start_queue_ptr = queue_ram_read_active_prod_ptr + 1;

        if (!queue_ram_read_data_enable) begin
            // queue inactive
            m_axis_enqueue_resp_error_next = 1'b1;
            m_axis_enqueue_resp_valid_next = 1'b1;
        end else if (queue_full) begin
            // queue full
            m_axis_enqueue_resp_full_next = 1'b1;
            m_axis_enqueue_resp_valid_next = 1'b1;
        end else begin
            // start enqueue
            m_axis_enqueue_resp_valid_next = 1'b1;

            queue_ram_be[7] = 1'b1;

            op_table_start_en = 1'b1;
        end
    end else if (op_commit_pipe_reg[PIPELINE-1]) begin
        // commit

        // update producer pointer
        queue_ram_write_ptr = queue_ram_addr_pipeline_reg[PIPELINE-1];
        queue_ram_write_data[15:0] = write_data_pipeline_reg[PIPELINE-1];
        queue_ram_be[1:0] = 2'b11;
        queue_ram_wr_en = 1'b1;

        queue_ram_write_data[55:48] = queue_ram_read_data_pipeline_reg[PIPELINE-1][55:48];
        // generate event on producer pointer update
        if (queue_ram_read_data_armed) begin
            m_axis_event_next = queue_ram_read_data_event;
            m_axis_event_function_id_next = queue_ram_read_data_function_id; // Scott
            m_axis_event_source_next = queue_ram_addr_pipeline_reg[PIPELINE-1];
            m_axis_event_valid_next = 1'b1;

            if (!queue_ram_read_data_continuous) begin
                queue_ram_write_data[54] = 1'b0;
                queue_ram_be[6] = 1'b1;
            end
        end
    end else if (op_axil_write_pipe_reg[PIPELINE-1]) begin
        // AXIL write
        s_axil_bvalid_next = 1'b1;

        queue_ram_write_data = queue_ram_read_data_pipeline_reg[PIPELINE-1];
        queue_ram_write_ptr = queue_ram_addr_pipeline_reg[PIPELINE-1];
        queue_ram_wr_en = 1'b1;

        // TODO parametrize
        case (axil_reg_pipeline_reg[PIPELINE-1])
            2'd0: begin
                // base address lower 32
                // base address is read-only when queue is active
                if (!queue_ram_read_data_enable) begin
                    queue_ram_write_data[95:76] = write_data_pipeline_reg[PIPELINE-1][31:12];
                    queue_ram_be[11:9] = write_strobe_pipeline_reg[PIPELINE-1];
                end
            end
            2'd1: begin
                // base address upper 32
                // base address is read-only when queue is active
                if (!queue_ram_read_data_enable) begin
                    queue_ram_write_data[127:96] = write_data_pipeline_reg[PIPELINE-1];
                    queue_ram_be[15:12] = write_strobe_pipeline_reg[PIPELINE-1];
                end
            end
            2'd2, 2'd3: begin
                casez (write_data_pipeline_reg[PIPELINE-1])
                    32'h8001zzzz: begin // Scott
						// VF ID
                        if (axil_reg_pipeline_function_id_reg[PIPELINE-1] == 0) begin // only func 0 can change the function id
                            queue_ram_write_data[71:64] = write_data_pipeline_reg[PIPELINE-1][7:0];
                            queue_ram_be[8] = 1'b1; 
                        end else begin
                            queue_ram_be[8] = 1'b1; 
                            queue_ram_write_data[71:64] = axil_reg_pipeline_function_id_reg[PIPELINE-1];
                        end

                    end
                    32'h8002zzzz: begin
                        // set size
                        if (!queue_ram_read_data_enable) begin
                            queue_ram_write_data[51:48] = write_data_pipeline_reg[PIPELINE-1][15:0];
                            queue_ram_be[6] = 1'b1;
                        end
                    end
                    32'hC0zzzzzz: begin
                        // set EQN
                        if (!queue_ram_read_data_enable) begin
                            if (axil_reg_pipeline_function_id_reg[PIPELINE-1] == 0 || FILTER_EQ_PTR == 0) begin
                                queue_ram_write_data[47:32] = write_data_pipeline_reg[PIPELINE-1][23:0];
                            end else begin
                                queue_ram_write_data[47:32] = (axil_reg_pipeline_function_id_reg[PIPELINE-1] << LOG_QUEUES_PER_FUNC) | write_data_pipeline_reg[PIPELINE-1][LOG_QUEUES_PER_FUNC-1:0];
                            end

                            queue_ram_be[5:4] = 2'b11;
                        end
                    end
                    32'h8080zzzz: begin
                        // set producer pointer
                        if (!queue_ram_read_data_enable) begin
                            queue_ram_write_data[15:0] = write_data_pipeline_reg[PIPELINE-1][15:0];
                            queue_ram_be[1:0] = 2'b11;
                        end
                    end
                    32'h8090zzzz: begin
                        // set consumer pointer
                        queue_ram_write_data[31:16] = write_data_pipeline_reg[PIPELINE-1][15:0];
                        queue_ram_be[3:2] = 2'b11;
                    end
                    32'h8091zzzz: begin
                        // set consumer pointer, arm
                        queue_ram_write_data[31:16] = write_data_pipeline_reg[PIPELINE-1][15:0];
                        queue_ram_be[3:2] = 2'b11;

                        queue_ram_write_data[54] = 1'b1;
                        queue_ram_be[6] = 1'b1;

                        if (queue_ram_read_data_enable && queue_ram_read_data_prod_ptr != write_data_pipeline_reg[PIPELINE-1][15:0]) begin
                            // armed and queue not empty
                            // so generate event
                            m_axis_event_next = queue_ram_read_data_event;
                            m_axis_event_source_next = queue_ram_addr_pipeline_reg[PIPELINE-1];
							m_axis_event_function_id_next = queue_ram_read_data_function_id; // Scott
                            m_axis_event_valid_next = 1'b1;

                            queue_ram_write_data[54] = 1'b0;
                            queue_ram_be[6] = 1'b1;
                        end
                    end
                    32'h400001zz: begin
                        // set enable
                        queue_ram_write_data[55] = write_data_pipeline_reg[PIPELINE-1][0];
                        queue_ram_be[6] = 1'b1;
                    end
                    32'h400002zz: begin
                        // set arm
                        queue_ram_write_data[54] = write_data_pipeline_reg[PIPELINE-1][0];
                        queue_ram_be[6] = 1'b1;

                        if (queue_ram_read_data_enable && write_data_pipeline_reg[PIPELINE-1][0] && (queue_ram_read_data_prod_ptr != queue_ram_read_data_cons_ptr)) begin
                            // armed and queue not empty
                            // so generate event
                            m_axis_event_next = queue_ram_read_data_event;
                            m_axis_event_source_next = queue_ram_addr_pipeline_reg[PIPELINE-1];
                            m_axis_event_valid_next = 1'b1;
                        	m_axis_event_function_id_next = queue_ram_read_data_function_id; // Scott

                            queue_ram_write_data[54] = 1'b0;
                            queue_ram_be[6] = 1'b1;
                        end
                    end
                    default: begin
                        // invalid command
                        $display("Error: Invalid command 0x%x for queue %d (instance %m)", write_data_pipeline_reg[PIPELINE-1], queue_ram_addr_pipeline_reg[PIPELINE-1]);
                    end
                endcase
            end
        endcase
    end else if (op_axil_read_pipe_reg[PIPELINE-1]) begin
        // AXIL read
        s_axil_rvalid_next = 1'b1;
        s_axil_rdata_next = 0;

        case (axil_reg_pipeline_reg[PIPELINE-1])
            2'd0: begin
                // VF ID
                s_axil_rdata_next[7:0] = queue_ram_read_data_function_id; // Scott
				s_axil_rdata_next[11:8] = 4'b0;
                // base address lower 32
                s_axil_rdata_next[31:12] = queue_ram_read_data_base_addr[31:12];
            end
            2'd1: begin
                // base address upper 32
                s_axil_rdata_next = queue_ram_read_data_base_addr[63:32];
            end
            2'd2: begin
                // EQN
                s_axil_rdata_next[15:0] = queue_ram_read_data_event;
                // control/status
                s_axil_rdata_next[16] = queue_ram_read_data_enable;
                s_axil_rdata_next[17] = queue_ram_read_data_armed;
                s_axil_rdata_next[18] = queue_ram_read_data_continuous;
                s_axil_rdata_next[19] = queue_active;
                // log size
                s_axil_rdata_next[31:28] = queue_ram_read_data_log_size;
            end
            2'd3: begin
                // producer pointer
                s_axil_rdata_next[15:0] = queue_ram_read_data_prod_ptr;
                // consumer pointer
                s_axil_rdata_next[31:16] = queue_ram_read_data_cons_ptr;
            end
        endcase
    end

    // enqueue commit (record in table)
    s_axis_enqueue_commit_ready_next = enable;
    if (s_axis_enqueue_commit_ready && s_axis_enqueue_commit_valid) begin
        op_table_commit_ptr = s_axis_enqueue_commit_op_tag;
        op_table_commit_en = 1'b1;
    end
end

always @(posedge clk) begin
    if (rst) begin
        op_axil_write_pipe_reg <= {PIPELINE{1'b0}};
        op_axil_read_pipe_reg <= {PIPELINE{1'b0}};
        op_req_pipe_reg <= {PIPELINE{1'b0}};
        op_commit_pipe_reg <= {PIPELINE{1'b0}};

        s_axis_enqueue_req_ready_reg <= 1'b0;
        m_axis_enqueue_resp_valid_reg <= 1'b0;
        s_axis_enqueue_commit_ready_reg <= 1'b0;
        m_axis_event_valid_reg <= 1'b0;

        s_axil_awready_reg <= 1'b0;
        s_axil_wready_reg <= 1'b0;
        s_axil_bvalid_reg <= 1'b0;
        s_axil_arready_reg <= 1'b0;
        s_axil_rvalid_reg <= 1'b0;

        op_table_active <= 0;

        op_table_start_ptr_reg <= 0;
        op_table_finish_ptr_reg <= 0;
    end else begin
        op_axil_write_pipe_reg <= op_axil_write_pipe_next;
        op_axil_read_pipe_reg <= op_axil_read_pipe_next;
        op_req_pipe_reg <= op_req_pipe_next;
        op_commit_pipe_reg <= op_commit_pipe_next;

        s_axis_enqueue_req_ready_reg <= s_axis_enqueue_req_ready_next;
        m_axis_enqueue_resp_valid_reg <= m_axis_enqueue_resp_valid_next;
        s_axis_enqueue_commit_ready_reg <= s_axis_enqueue_commit_ready_next;
        m_axis_event_valid_reg <= m_axis_event_valid_next;

        s_axil_awready_reg <= s_axil_awready_next;
        s_axil_wready_reg <= s_axil_wready_next;
        s_axil_bvalid_reg <= s_axil_bvalid_next;
        s_axil_arready_reg <= s_axil_arready_next;
        s_axil_rvalid_reg <= s_axil_rvalid_next;

        if (op_table_start_en) begin
            op_table_start_ptr_reg <= op_table_start_ptr_reg + 1;
            op_table_active[op_table_start_ptr_reg] <= 1'b1;
        end
        if (op_table_finish_en) begin
            op_table_finish_ptr_reg <= op_table_finish_ptr_reg + 1;
            op_table_active[op_table_finish_ptr_reg] <= 1'b0;
        end
    end

    for (i = 0; i < PIPELINE; i = i + 1) begin
        queue_ram_addr_pipeline_reg[i] <= queue_ram_addr_pipeline_next[i];
        axil_reg_pipeline_reg[i] <= axil_reg_pipeline_next[i];
        axil_reg_pipeline_function_id_reg[i] <= axil_reg_pipeline_function_id_next[i]; // Scott
        write_data_pipeline_reg[i] <= write_data_pipeline_next[i];
        write_strobe_pipeline_reg[i] <= write_strobe_pipeline_next[i];
        req_tag_pipeline_reg[i] <= req_tag_pipeline_next[i];
    end

    m_axis_enqueue_resp_queue_reg <= m_axis_enqueue_resp_queue_next;
    m_axis_enqueue_resp_ptr_reg <= m_axis_enqueue_resp_ptr_next;
    m_axis_enqueue_resp_phase_reg <= m_axis_enqueue_resp_phase_next;
    m_axis_enqueue_resp_addr_reg <= m_axis_enqueue_resp_addr_next;
    m_axis_enqueue_resp_event_reg <= m_axis_enqueue_resp_event_next;
    m_axis_enqueue_resp_tag_reg <= m_axis_enqueue_resp_tag_next;
    m_axis_enqueue_resp_op_tag_reg <= m_axis_enqueue_resp_op_tag_next;
    m_axis_enqueue_resp_function_id_reg <= m_axis_enqueue_resp_function_id_next; // Scott
    m_axis_enqueue_resp_full_reg <= m_axis_enqueue_resp_full_next;
    m_axis_enqueue_resp_error_reg <= m_axis_enqueue_resp_error_next;
    m_axis_event_reg <= m_axis_event_next;
    m_axis_event_source_reg <= m_axis_event_source_next;
    m_axis_event_function_id_reg <= m_axis_event_function_id_next; // Scott

    s_axil_rdata_reg <= s_axil_rdata_next;

    if (queue_ram_wr_en) begin
        for (i = 0; i < QUEUE_RAM_BE_WIDTH; i = i + 1) begin
            if (queue_ram_be[i]) begin
                queue_ram[queue_ram_write_ptr][i*8 +: 8] <= queue_ram_write_data[i*8 +: 8];
            end
        end
    end
    queue_ram_read_data_reg <= queue_ram[queue_ram_read_ptr];
    queue_ram_read_data_pipeline_reg[1] <= queue_ram_read_data_reg;
    for (i = 2; i < PIPELINE; i = i + 1) begin
        queue_ram_read_data_pipeline_reg[i] <= queue_ram_read_data_pipeline_reg[i-1];
    end

    if (op_table_start_en) begin
        op_table_commit[op_table_start_ptr_reg] <= 1'b0;
        op_table_queue[op_table_start_ptr_reg] <= op_table_start_queue;
        op_table_queue_ptr[op_table_start_ptr_reg] <= op_table_start_queue_ptr;
    end
    if (op_table_commit_en) begin
        op_table_commit[op_table_commit_ptr] <= 1'b1;
    end
end

endmodule

`resetall
