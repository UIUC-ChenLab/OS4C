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
 * Descriptor operation mux
 */
module desc_op_mux #
(
    // Number of ports
    parameter PORTS = 2,
    // Select field width
    parameter SELECT_WIDTH = 1,
    // Queue index width
    parameter QUEUE_INDEX_WIDTH = 4,
    // Queue element pointer width
    parameter QUEUE_PTR_WIDTH = 16,
    // Completion queue index width
    parameter CPL_QUEUE_INDEX_WIDTH = 4,
    // Input request tag field width
    parameter S_REQ_TAG_WIDTH = 8,
    // Output request tag field width (towards descriptor module)
    // Additional bits required for response routing
    parameter M_REQ_TAG_WIDTH = S_REQ_TAG_WIDTH+$clog2(PORTS),
    // Width of AXI stream interface in bits
    parameter AXIS_DATA_WIDTH = 256,
    // AXI stream tkeep signal width (words per cycle)
    parameter AXIS_KEEP_WIDTH = AXIS_DATA_WIDTH/8,
    // select round robin arbitration
    parameter ARB_TYPE_ROUND_ROBIN = 0,
    // LSB priority selection
    parameter ARB_LSB_HIGH_PRIORITY = 1,
    // Function ID width Scott
    parameter FUNCTION_ID_WIDTH = 8
)
(
    input  wire                                   clk,
    input  wire                                   rst,

    /*
     * Descriptor request output (to descriptor module)
     */
    output wire [SELECT_WIDTH-1:0]                m_axis_req_sel,
    output wire [QUEUE_INDEX_WIDTH-1:0]           m_axis_req_queue,
    output wire [M_REQ_TAG_WIDTH-1:0]             m_axis_req_tag,
    output wire                                   m_axis_req_valid,
    input  wire                                   m_axis_req_ready,

    /* 
     * Descriptor request status input (from descriptor module)
     */
    input  wire [QUEUE_INDEX_WIDTH-1:0]           s_axis_req_status_queue,
    input  wire [QUEUE_PTR_WIDTH-1:0]             s_axis_req_status_ptr,
    input  wire [CPL_QUEUE_INDEX_WIDTH-1:0]       s_axis_req_status_cpl,
    input  wire [M_REQ_TAG_WIDTH-1:0]             s_axis_req_status_tag,
    input  wire [FUNCTION_ID_WIDTH-1:0]           s_axis_req_status_function_id,
    input  wire                                   s_axis_req_status_empty,
    input  wire                                   s_axis_req_status_error,
    input  wire                                   s_axis_req_status_valid,

    /*
     * Descriptor data input (from descriptor module)
     */
    input  wire [AXIS_DATA_WIDTH-1:0]             s_axis_desc_tdata,
    input  wire [AXIS_KEEP_WIDTH-1:0]             s_axis_desc_tkeep,
    input  wire                                   s_axis_desc_tvalid,
    output wire                                   s_axis_desc_tready,
    input  wire                                   s_axis_desc_tlast,
    input  wire [M_REQ_TAG_WIDTH-1:0]             s_axis_desc_tid,
    input  wire                                   s_axis_desc_tuser,

    /*
     * Descriptor request input
     */
    input  wire [PORTS*SELECT_WIDTH-1:0]          s_axis_req_sel,
    input  wire [PORTS*QUEUE_INDEX_WIDTH-1:0]     s_axis_req_queue,
    input  wire [PORTS*S_REQ_TAG_WIDTH-1:0]       s_axis_req_tag,
    input  wire [PORTS-1:0]                       s_axis_req_valid,
    output wire [PORTS-1:0]                       s_axis_req_ready,

    /*
     * Descriptor request status output
     */
    output wire [PORTS*QUEUE_INDEX_WIDTH-1:0]     m_axis_req_status_queue,
    output wire [PORTS*QUEUE_PTR_WIDTH-1:0]       m_axis_req_status_ptr,
    output wire [PORTS*CPL_QUEUE_INDEX_WIDTH-1:0] m_axis_req_status_cpl,
    output wire [PORTS*S_REQ_TAG_WIDTH-1:0]       m_axis_req_status_tag,
    output wire [PORTS*FUNCTION_ID_WIDTH-1:0]     m_axis_req_status_function_id, // Scott
    output wire [PORTS-1:0]                       m_axis_req_status_empty,
    output wire [PORTS-1:0]                       m_axis_req_status_error,
    output wire [PORTS-1:0]                       m_axis_req_status_valid,

    /*
     * Descriptor data output
     */
    output wire [PORTS*AXIS_DATA_WIDTH-1:0]       m_axis_desc_tdata,
    output wire [PORTS*AXIS_KEEP_WIDTH-1:0]       m_axis_desc_tkeep,
    output wire [PORTS-1:0]                       m_axis_desc_tvalid,
    input  wire [PORTS-1:0]                       m_axis_desc_tready,
    output wire [PORTS-1:0]                       m_axis_desc_tlast,
    output wire [PORTS*S_REQ_TAG_WIDTH-1:0]       m_axis_desc_tid,
    output wire [PORTS-1:0]                       m_axis_desc_tuser
);

parameter CL_PORTS = $clog2(PORTS);

// check configuration
initial begin
    if (M_REQ_TAG_WIDTH < S_REQ_TAG_WIDTH+$clog2(PORTS)) begin
        $error("Error: M_REQ_TAG_WIDTH must be at least $clog2(PORTS) larger than S_REQ_TAG_WIDTH (instance %m)");
        $finish;
    end
end

// request mux
wire [PORTS-1:0] request;
wire [PORTS-1:0] acknowledge;
wire [PORTS-1:0] grant;
wire grant_valid;
wire [CL_PORTS-1:0] grant_encoded;

// input registers to pipeline arbitration delay
reg [PORTS*SELECT_WIDTH-1:0]      s_axis_req_sel_reg = 0;
reg [PORTS*QUEUE_INDEX_WIDTH-1:0] s_axis_req_queue_reg = 0;
reg [PORTS*S_REQ_TAG_WIDTH-1:0]   s_axis_req_tag_reg = 0;
reg [PORTS-1:0]                   s_axis_req_valid_reg = 0;

// internal datapath
reg  [SELECT_WIDTH-1:0]      m_axis_req_sel_int;
reg  [QUEUE_INDEX_WIDTH-1:0] m_axis_req_queue_int;
reg  [M_REQ_TAG_WIDTH-1:0]   m_axis_req_tag_int;
reg                          m_axis_req_valid_int;
reg                          m_axis_req_ready_int_reg = 1'b0;
wire                         m_axis_req_ready_int_early;

assign s_axis_req_ready = ~s_axis_req_valid_reg | ({PORTS{m_axis_req_ready_int_reg}} & grant);

// mux for incoming packet
wire [SELECT_WIDTH-1:0]      current_s_desc_sel   = s_axis_req_sel_reg[grant_encoded*SELECT_WIDTH +: SELECT_WIDTH];
wire [QUEUE_INDEX_WIDTH-1:0] current_s_desc_queue = s_axis_req_queue_reg[grant_encoded*QUEUE_INDEX_WIDTH +: QUEUE_INDEX_WIDTH];
wire [S_REQ_TAG_WIDTH-1:0]   current_s_desc_tag   = s_axis_req_tag_reg[grant_encoded*S_REQ_TAG_WIDTH +: S_REQ_TAG_WIDTH];
wire                         current_s_desc_valid = s_axis_req_valid_reg[grant_encoded];
wire                         current_s_desc_ready = s_axis_req_ready[grant_encoded];

// arbiter instance
arbiter #(
    .PORTS(PORTS),
    .ARB_TYPE_ROUND_ROBIN(ARB_TYPE_ROUND_ROBIN),
    .ARB_BLOCK(1),
    .ARB_BLOCK_ACK(1),
    .ARB_LSB_HIGH_PRIORITY(ARB_LSB_HIGH_PRIORITY)
)
arb_inst (
    .clk(clk),
    .rst(rst),
    .request(request),
    .acknowledge(acknowledge),
    .grant(grant),
    .grant_valid(grant_valid),
    .grant_encoded(grant_encoded)
);

assign request = (s_axis_req_valid_reg & ~grant) | (s_axis_req_valid & grant);
assign acknowledge = grant & s_axis_req_valid_reg & {PORTS{m_axis_req_ready_int_reg}};

always @* begin
    // pass through selected packet data
    m_axis_req_sel_int   = current_s_desc_sel;
    m_axis_req_queue_int = current_s_desc_queue;
    m_axis_req_tag_int   = {grant_encoded, current_s_desc_tag};
    m_axis_req_valid_int = current_s_desc_valid && m_axis_req_ready_int_reg && grant_valid;
end

integer i;

always @(posedge clk) begin
    // register inputs
    for (i = 0; i < PORTS; i = i + 1) begin
        if (s_axis_req_ready[i]) begin
            s_axis_req_sel_reg[i*SELECT_WIDTH +: SELECT_WIDTH] <= s_axis_req_sel[i*SELECT_WIDTH +: SELECT_WIDTH];
            s_axis_req_queue_reg[i*QUEUE_INDEX_WIDTH +: QUEUE_INDEX_WIDTH] <= s_axis_req_queue[i*QUEUE_INDEX_WIDTH +: QUEUE_INDEX_WIDTH];
            s_axis_req_tag_reg[i*S_REQ_TAG_WIDTH +: S_REQ_TAG_WIDTH] <= s_axis_req_tag[i*S_REQ_TAG_WIDTH +: S_REQ_TAG_WIDTH];
            s_axis_req_valid_reg[i] <= s_axis_req_valid[i];
       end
    end

    if (rst) begin
        s_axis_req_valid_reg <= 0;
    end
end

// output datapath logic
reg [SELECT_WIDTH-1:0]      m_axis_req_sel_reg   = {SELECT_WIDTH{1'b0}};
reg [QUEUE_INDEX_WIDTH-1:0] m_axis_req_queue_reg = {QUEUE_INDEX_WIDTH{1'b0}};
reg [M_REQ_TAG_WIDTH-1:0]   m_axis_req_tag_reg   = {M_REQ_TAG_WIDTH{1'b0}};
reg                         m_axis_req_valid_reg = 1'b0, m_axis_req_valid_next;

reg [SELECT_WIDTH-1:0]      temp_m_axis_req_sel_reg   = {SELECT_WIDTH{1'b0}};
reg [QUEUE_INDEX_WIDTH-1:0] temp_m_axis_req_queue_reg = {QUEUE_INDEX_WIDTH{1'b0}};
reg [M_REQ_TAG_WIDTH-1:0]   temp_m_axis_req_tag_reg   = {M_REQ_TAG_WIDTH{1'b0}};
reg                         temp_m_axis_req_valid_reg = 1'b0, temp_m_axis_req_valid_next;

// datapath control
reg store_axis_int_to_output;
reg store_axis_int_to_temp;
reg store_axis_temp_to_output;

assign m_axis_req_sel   = m_axis_req_sel_reg;
assign m_axis_req_queue = m_axis_req_queue_reg;
assign m_axis_req_tag   = m_axis_req_tag_reg;
assign m_axis_req_valid = m_axis_req_valid_reg;

// enable ready input next cycle if output is ready or if both output registers are empty
assign m_axis_req_ready_int_early = m_axis_req_ready || (!temp_m_axis_req_valid_reg && !m_axis_req_valid_reg);

always @* begin
    // transfer sink ready state to source
    m_axis_req_valid_next = m_axis_req_valid_reg;
    temp_m_axis_req_valid_next = temp_m_axis_req_valid_reg;

    store_axis_int_to_output = 1'b0;
    store_axis_int_to_temp = 1'b0;
    store_axis_temp_to_output = 1'b0;

    if (m_axis_req_ready_int_reg) begin
        // input is ready
        if (m_axis_req_ready || !m_axis_req_valid_reg) begin
            // output is ready or currently not valid, transfer data to output
            m_axis_req_valid_next = m_axis_req_valid_int;
            store_axis_int_to_output = 1'b1;
        end else begin
            // output is not ready, store input in temp
            temp_m_axis_req_valid_next = m_axis_req_valid_int;
            store_axis_int_to_temp = 1'b1;
        end
    end else if (m_axis_req_ready) begin
        // input is not ready, but output is ready
        m_axis_req_valid_next = temp_m_axis_req_valid_reg;
        temp_m_axis_req_valid_next = 1'b0;
        store_axis_temp_to_output = 1'b1;
    end
end

always @(posedge clk) begin
    m_axis_req_valid_reg <= m_axis_req_valid_next;
    m_axis_req_ready_int_reg <= m_axis_req_ready_int_early;
    temp_m_axis_req_valid_reg <= temp_m_axis_req_valid_next;

    // datapath
    if (store_axis_int_to_output) begin
        m_axis_req_sel_reg <= m_axis_req_sel_int;
        m_axis_req_queue_reg <= m_axis_req_queue_int;
        m_axis_req_tag_reg <= m_axis_req_tag_int;
    end else if (store_axis_temp_to_output) begin
        m_axis_req_sel_reg <= temp_m_axis_req_sel_reg;
        m_axis_req_queue_reg <= temp_m_axis_req_queue_reg;
        m_axis_req_tag_reg <= temp_m_axis_req_tag_reg;
    end

    if (store_axis_int_to_temp) begin
        temp_m_axis_req_sel_reg <= m_axis_req_sel_int;
        temp_m_axis_req_queue_reg <= m_axis_req_queue_int;
        temp_m_axis_req_tag_reg <= m_axis_req_tag_int;
    end

    if (rst) begin
        m_axis_req_valid_reg <= 1'b0;
        m_axis_req_ready_int_reg <= 1'b0;
        temp_m_axis_req_valid_reg <= 1'b0;
    end
end

// request status demux
reg [QUEUE_INDEX_WIDTH-1:0] m_axis_req_status_queue_reg = {QUEUE_INDEX_WIDTH{1'b0}}, m_axis_req_status_queue_next;
reg [QUEUE_PTR_WIDTH-1:0] m_axis_req_status_ptr_reg = {QUEUE_PTR_WIDTH{1'b0}}, m_axis_req_status_ptr_next;
reg [CPL_QUEUE_INDEX_WIDTH-1:0] m_axis_req_status_cpl_reg = {CPL_QUEUE_INDEX_WIDTH{1'b0}}, m_axis_req_status_cpl_next;
reg [S_REQ_TAG_WIDTH-1:0] m_axis_req_status_tag_reg = {S_REQ_TAG_WIDTH{1'b0}}, m_axis_req_status_tag_next;
reg [FUNCTION_ID_WIDTH-1:0] m_axis_req_status_function_id_reg = {FUNCTION_ID_WIDTH{1'b0}}, m_axis_req_status_function_id_next; // Scott
reg m_axis_req_status_empty_reg = 1'b0, m_axis_req_status_empty_next;
reg m_axis_req_status_error_reg = 1'b0, m_axis_req_status_error_next;
reg [PORTS-1:0] m_axis_req_status_valid_reg = {PORTS{1'b0}}, m_axis_req_status_valid_next;

assign m_axis_req_status_queue = {PORTS{m_axis_req_status_queue_reg}};
assign m_axis_req_status_ptr = {PORTS{m_axis_req_status_ptr_reg}};
assign m_axis_req_status_cpl = {PORTS{m_axis_req_status_cpl_reg}};
assign m_axis_req_status_tag = {PORTS{m_axis_req_status_tag_reg}};
assign m_axis_req_status_function_id = {PORTS{m_axis_req_status_function_id_reg}}; // Scott
assign m_axis_req_status_empty = {PORTS{m_axis_req_status_empty_reg}};
assign m_axis_req_status_error = {PORTS{m_axis_req_status_error_reg}};
assign m_axis_req_status_valid = m_axis_req_status_valid_reg;

always @* begin
    m_axis_req_status_queue_next = s_axis_req_status_queue;
    m_axis_req_status_ptr_next = s_axis_req_status_ptr;
    m_axis_req_status_cpl_next = s_axis_req_status_cpl;
    m_axis_req_status_tag_next = s_axis_req_status_tag;
    m_axis_req_status_function_id_next = s_axis_req_status_function_id; // Scott
    m_axis_req_status_empty_next = s_axis_req_status_empty;
    m_axis_req_status_error_next = s_axis_req_status_error;
    m_axis_req_status_valid_next = s_axis_req_status_valid << (PORTS > 1 ? (s_axis_req_status_tag >> S_REQ_TAG_WIDTH) : 0);
end

always @(posedge clk) begin
    m_axis_req_status_queue_reg <= m_axis_req_status_queue_next;
    m_axis_req_status_ptr_reg <= m_axis_req_status_ptr_next;
    m_axis_req_status_cpl_reg <= m_axis_req_status_cpl_next;
    m_axis_req_status_tag_reg <= m_axis_req_status_tag_next;
    m_axis_req_status_function_id_reg <= m_axis_req_status_function_id_next; // Scott
    m_axis_req_status_empty_reg <= m_axis_req_status_empty_next;
    m_axis_req_status_error_reg <= m_axis_req_status_error_next;
    m_axis_req_status_valid_reg <= m_axis_req_status_valid_next;

    if (rst) begin
        m_axis_req_status_valid_reg <= {PORTS{1'b0}};
    end
end

// descriptor data demux

// internal datapath
reg  [AXIS_DATA_WIDTH-1:0] m_axis_desc_tdata_int;
reg  [AXIS_KEEP_WIDTH-1:0] m_axis_desc_tkeep_int;
reg  [PORTS-1:0]           m_axis_desc_tvalid_int;
reg                        m_axis_desc_tready_int_reg = 1'b0;
wire                       m_axis_desc_tready_int_early;
reg                        m_axis_desc_tlast_int;
reg  [S_REQ_TAG_WIDTH-1:0] m_axis_desc_tid_int;
reg                        m_axis_desc_tuser_int;

assign s_axis_desc_tready = m_axis_desc_tready_int_reg;

always @* begin
    m_axis_desc_tdata_int  = s_axis_desc_tdata;
    m_axis_desc_tkeep_int  = s_axis_desc_tkeep;
    m_axis_desc_tvalid_int = (s_axis_desc_tvalid && s_axis_desc_tready) << (PORTS > 1 ? (s_axis_desc_tid >> S_REQ_TAG_WIDTH) : 0);
    m_axis_desc_tlast_int  = s_axis_desc_tlast;
    m_axis_desc_tid_int    = s_axis_desc_tid;
    m_axis_desc_tuser_int  = s_axis_desc_tuser;
end

// output datapath logic
reg [AXIS_DATA_WIDTH-1:0] m_axis_desc_tdata_reg  = {AXIS_DATA_WIDTH{1'b0}};
reg [AXIS_KEEP_WIDTH-1:0] m_axis_desc_tkeep_reg  = {AXIS_KEEP_WIDTH{1'b0}};
reg [PORTS-1:0]           m_axis_desc_tvalid_reg = {PORTS{1'b0}}, m_axis_desc_tvalid_next;
reg                       m_axis_desc_tlast_reg  = 1'b0;
reg [S_REQ_TAG_WIDTH-1:0] m_axis_desc_tid_reg    = {S_REQ_TAG_WIDTH{1'b0}};
reg                       m_axis_desc_tuser_reg  = 1'b0;

reg [AXIS_DATA_WIDTH-1:0] temp_m_axis_desc_tdata_reg  = {AXIS_DATA_WIDTH{1'b0}};
reg [AXIS_KEEP_WIDTH-1:0] temp_m_axis_desc_tkeep_reg  = {AXIS_KEEP_WIDTH{1'b0}};
reg [PORTS-1:0]           temp_m_axis_desc_tvalid_reg = {PORTS{1'b0}}, temp_m_axis_desc_tvalid_next;
reg                       temp_m_axis_desc_tlast_reg  = 1'b0;
reg [S_REQ_TAG_WIDTH-1:0] temp_m_axis_desc_tid_reg    = {S_REQ_TAG_WIDTH{1'b0}};
reg                       temp_m_axis_desc_tuser_reg  = 1'b0;

// datapath control
reg store_axis_req_int_to_output;
reg store_axis_req_int_to_temp;
reg store_axis_req_temp_to_output;

assign m_axis_desc_tdata  = {PORTS{m_axis_desc_tdata_reg}};
assign m_axis_desc_tkeep  = {PORTS{m_axis_desc_tkeep_reg}};
assign m_axis_desc_tlast  = {PORTS{m_axis_desc_tlast_reg}};
assign m_axis_desc_tid    = {PORTS{m_axis_desc_tid_reg}};
assign m_axis_desc_tuser  = {PORTS{m_axis_desc_tuser_reg}};
assign m_axis_desc_tvalid = m_axis_desc_tvalid_reg;

// enable ready input next cycle if output is ready or if both output registers are empty
assign m_axis_desc_tready_int_early = (m_axis_desc_tready & m_axis_desc_tvalid) || (!temp_m_axis_desc_tvalid_reg && !m_axis_desc_tvalid_reg);

always @* begin
    // transfer sink ready state to source
    m_axis_desc_tvalid_next = m_axis_desc_tvalid_reg;
    temp_m_axis_desc_tvalid_next = temp_m_axis_desc_tvalid_reg;

    store_axis_req_int_to_output = 1'b0;
    store_axis_req_int_to_temp = 1'b0;
    store_axis_req_temp_to_output = 1'b0;

    if (m_axis_desc_tready_int_reg) begin
        // input is ready
        if ((m_axis_desc_tready & m_axis_desc_tvalid) || !m_axis_desc_tvalid) begin
            // output is ready or currently not valid, transfer data to output
            m_axis_desc_tvalid_next = m_axis_desc_tvalid_int;
            store_axis_req_int_to_output = 1'b1;
        end else begin
            // output is not ready, store input in temp
            temp_m_axis_desc_tvalid_next = m_axis_desc_tvalid_int;
            store_axis_req_int_to_temp = 1'b1;
        end
    end else if (m_axis_desc_tready & m_axis_desc_tvalid) begin
        // input is not ready, but output is ready
        m_axis_desc_tvalid_next = temp_m_axis_desc_tvalid_reg;
        temp_m_axis_desc_tvalid_next = {PORTS{1'b0}};
        store_axis_req_temp_to_output = 1'b1;
    end
end

always @(posedge clk) begin
    m_axis_desc_tvalid_reg <= m_axis_desc_tvalid_next;
    m_axis_desc_tready_int_reg <= m_axis_desc_tready_int_early;
    temp_m_axis_desc_tvalid_reg <= temp_m_axis_desc_tvalid_next;

    // datapath
    if (store_axis_req_int_to_output) begin
        m_axis_desc_tdata_reg <= m_axis_desc_tdata_int;
        m_axis_desc_tkeep_reg <= m_axis_desc_tkeep_int;
        m_axis_desc_tlast_reg <= m_axis_desc_tlast_int;
        m_axis_desc_tid_reg <= m_axis_desc_tid_int;
        m_axis_desc_tuser_reg <= m_axis_desc_tuser_int;
    end else if (store_axis_req_temp_to_output) begin
        m_axis_desc_tdata_reg <= temp_m_axis_desc_tdata_reg;
        m_axis_desc_tkeep_reg <= temp_m_axis_desc_tkeep_reg;
        m_axis_desc_tlast_reg <= temp_m_axis_desc_tlast_reg;
        m_axis_desc_tid_reg <= temp_m_axis_desc_tid_reg;
        m_axis_desc_tuser_reg <= temp_m_axis_desc_tuser_reg;
    end

    if (store_axis_req_int_to_temp) begin
        temp_m_axis_desc_tdata_reg <= m_axis_desc_tdata_int;
        temp_m_axis_desc_tkeep_reg <= m_axis_desc_tkeep_int;
        temp_m_axis_desc_tlast_reg <= m_axis_desc_tlast_int;
        temp_m_axis_desc_tid_reg <= m_axis_desc_tid_int;
        temp_m_axis_desc_tuser_reg <= m_axis_desc_tuser_int;
    end

    if (rst) begin
        m_axis_desc_tvalid_reg <= {PORTS{1'b0}};
        m_axis_desc_tready_int_reg <= 1'b0;
        temp_m_axis_desc_tvalid_reg <= {PORTS{1'b0}};
    end
end

endmodule

`resetall
