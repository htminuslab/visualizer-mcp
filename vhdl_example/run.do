# Compile Design
vcom -quiet -2008 div.vhd
vcom -quiet -2008 div_tb.vhd

# Optimise Design
vopt -debug,livesim +designfile  div_tb -o div_tb_vopt 

# Simulate Design
vsim -visualizer -qwavedb=+signal+memory+vhdlvariable  div_tb_vopt 

set StdArithNoWarnings 1
