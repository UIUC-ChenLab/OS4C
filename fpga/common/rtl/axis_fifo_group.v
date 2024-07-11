// SPDX-License-Identifier: BSD-2-Clause-Views
// Copyright (c) 2024 University of Illinois Urbana Champaign

module axis_fifo_group #
(
    // FIFO depth in words
    // KEEP_WIDTH words per cycle if KEEP_ENABLE set
    // Rounded up to nearest power of 2 cycles
    parameter DEPTH = 4096,
    // Width of AXI stream interfaces in bits
    parameter DATA_WIDTH = 8,
    // Propagate tkeep signal
    // If disabled, tkeep assumed to be 1'b1
    parameter KEEP_ENABLE = (DATA_WIDTH>8),
    // tkeep signal width (words per cycle)
    parameter KEEP_WIDTH = ((DATA_WIDTH+7)/8),
    // Propagate tlast signal
    parameter LAST_ENABLE = 1,
    // Propagate tid signal
    parameter ID_ENABLE = 0,
    // tid signal width
    //parameter ID_WIDTH = 8,
    // Propagate tdest signal
    parameter DEST_ENABLE = 0,
    // tdest signal width
    //parameter DEST_WIDTH = 8,
    // Propagate tuser signal
    parameter USER_ENABLE = 1,
    // tuser signal width
    //parameter USER_WIDTH = 1,
    // number of RAM pipeline registers
    //parameter RAM_PIPELINE = 1,
    // use output FIFO
    // When set, the RAM read enable and pipeline clock enables are removed
    //parameter OUTPUT_FIFO_ENABLE = 0,
    // Frame FIFO mode - operate on frames instead of cycles
    // When set, m_axis_tvalid will not be deasserted within a frame
    // Requires LAST_ENABLE set
    parameter FRAME_FIFO = 0,
    // tuser value for bad frame marker
    //parameter USER_BAD_FRAME_VALUE = 1'b1,
    // tuser mask for bad frame marker
    //parameter USER_BAD_FRAME_MASK = 1'b1,
    // Drop frames larger than FIFO
    // Requires FRAME_FIFO set
    //parameter DROP_OVERSIZE_FRAME = FRAME_FIFO,
    // Drop frames marked bad
    // Requires FRAME_FIFO and DROP_OVERSIZE_FRAME set
    //parameter DROP_BAD_FRAME = 0,
    // Drop incoming frames when full
    // When set, s_axis_tready is always asserted
    // Requires FRAME_FIFO and DROP_OVERSIZE_FRAME set
    //parameter DROP_WHEN_FULL = 0,


    // number of functions, will maintain
    // one fifo for each
    parameter NUM_FUNCS = 256

)
(
    input wire clk,
    input wire rst, 


    // AXI input for current fifo
    input  wire [DATA_WIDTH-1:0]  s_axis_tdata,

    input  wire                   s_axis_tvalid,
    output wire                   s_axis_tready,


    output wire [DATA_WIDTH-1:0]  m_axis_tdata,
  
    output wire                   m_axis_tvalid,
    input  wire                   m_axis_tready,

    input wire [($clog2(NUM_FUNCS))-1:0] curr_func_in, 
    input wire curr_func_in_valid,
    input wire [($clog2(NUM_FUNCS))-1:0] curr_func_out,
    input wire curr_func_out_valid

);

reg [DATA_WIDTH-1:0] s_axis_tdata_group [NUM_FUNCS-1:0];
reg s_axis_tvalid_group [NUM_FUNCS-1:0];
wire s_axis_tready_group [NUM_FUNCS-1:0];

wire [DATA_WIDTH-1:0] m_axis_tdata_group [NUM_FUNCS-1:0];
wire m_axis_tvalid_group [NUM_FUNCS-1:0];
reg m_axis_tready_group [NUM_FUNCS-1:0];

wire [DATA_WIDTH-1:0] s_axis_tdata_reg;
wire s_axis_tvalid_reg;
wire m_axis_tready_reg;

reg s_axis_tready_reg;
reg [DATA_WIDTH-1:0] m_axis_tdata_reg;
reg m_axis_tvalid_reg; 

assign s_axis_tdata_reg = s_axis_tdata;
assign s_axis_tvalid_reg = s_axis_tvalid;
assign m_axis_tready_reg = m_axis_tready; 

assign s_axis_tready = s_axis_tready_reg;
assign m_axis_tdata = m_axis_tdata_reg;
assign m_axis_tvalid = m_axis_tvalid_reg;

//ensure depth can only ever be minimum of 2
parameter REAL_DEPTH = (DEPTH>1) ? DEPTH : 2;


generate
    genvar i; 

    for (i=0; i<NUM_FUNCS; i=i+1) begin
    
        axis_fifo #(
            .DEPTH(REAL_DEPTH),
            .DATA_WIDTH(DATA_WIDTH),
            .KEEP_ENABLE(KEEP_ENABLE),
            .KEEP_WIDTH(KEEP_WIDTH),
            .LAST_ENABLE(LAST_ENABLE),
            .ID_ENABLE(ID_ENABLE),
            .DEST_ENABLE(DEST_ENABLE),
            .USER_ENABLE(USER_ENABLE),
            .FRAME_FIFO(FRAME_FIFO)
        ) rr_fifo (
            .clk(clk),
            .rst(rst),

            // AXI input
            .s_axis_tdata(s_axis_tdata_group[i]),
            .s_axis_tkeep(1'b0),
            .s_axis_tvalid(s_axis_tvalid_group[i]),
            .s_axis_tready(s_axis_tready_group[i]),
            .s_axis_tlast(1'b0),
            .s_axis_tid(8'b0),
            .s_axis_tdest(8'b0),
            .s_axis_tuser(1'b0),

            // AXI output
            .m_axis_tdata(m_axis_tdata_group[i]),
            .m_axis_tkeep(),
            .m_axis_tvalid(m_axis_tvalid_group[i]),
            .m_axis_tready(m_axis_tready_group[i]),
            .m_axis_tlast(),
            .m_axis_tid(),
            .m_axis_tdest(),
            .m_axis_tuser(),

            //Status
            .status_overflow(),
            .status_bad_frame(),
            .status_good_frame()
        );
    end
endgenerate

integer j; 

always @* begin

    for(j = 0; j < NUM_FUNCS; j = j + 1)begin
        s_axis_tdata_group[j] = {DATA_WIDTH{1'b0}};
        s_axis_tvalid_group[j] = 1'b0;
        m_axis_tready_group[j] = 1'b0;
    end

    if(curr_func_out_valid) begin
        m_axis_tready_group[curr_func_out]=m_axis_tready_reg; 
        m_axis_tdata_reg = m_axis_tdata_group[curr_func_out];
        m_axis_tvalid_reg = m_axis_tvalid_group[curr_func_out];
    end else begin
        m_axis_tdata_reg = {DATA_WIDTH{1'b0}};
        m_axis_tvalid_reg = 1'b0;
    end

    if (curr_func_in_valid) begin 
        s_axis_tdata_group[curr_func_in]= s_axis_tdata_reg;
        s_axis_tvalid_group[curr_func_in]=s_axis_tvalid_reg;
        s_axis_tready_reg = s_axis_tready_group[curr_func_in];  
    end else begin
        s_axis_tready_reg = 1'b0;
    end

    
end


endmodule