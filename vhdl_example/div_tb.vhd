-- Very simple non self-checking testbench, needs updating HABT2015

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity div_tb is
end entity div_tb;

architecture rtl of div_tb is

component div is
   port( clk          : in   std_logic;                             
         reset        : in   std_logic;                             
		 dividend     : in   unsigned(31 downto 0);
         divisor      : in   unsigned(31 downto 0);	
		 divsigned	  : in   boolean;								-- 0=unsigned, 1=signed		 
         quotient     : out  unsigned(31 downto 0);
         remainder    : out  unsigned(31 downto 0);                 
         start        : in   boolean;						
         busy         : out  boolean);								
end component div;



signal reset_s	    : std_logic;
signal clk_s	    : std_logic:='0';
signal dividend_s	: unsigned(31 downto 0);
signal divisor_s	: unsigned(31 downto 0);
signal divsigned_s  : boolean;								-- 0=unsigned, 1=signed		 
signal quotient_s	: unsigned(31 downto 0);
signal remainder_s	: unsigned(31 downto 0);                 
signal start_s	    : boolean;						
signal busy_s	    : boolean;		

begin
	
	clk_s <= not clk_s after 10 ns;
	
	DUT : div
	port map (clk 	     => clk_s,
			  reset      => reset_s,
			  dividend   => dividend_s,  
			  divisor    => divisor_s,   
			  divsigned  => divsigned_s,
			  quotient   => quotient_s,  
			  remainder  => remainder_s, 
			  start      => start_s,        
			  busy       => busy_s);

	process
		begin
			reset_s <= '1';
			start_s <= false;
			dividend_s <= (others =>'0');
			divisor_s  <= (others =>'0');
			divsigned_s <= false; --unsigned
			
			wait for 40 ns;
			reset_s	<= '0';
			wait for 270 ns;
						
			dividend_s <= X"ED160000";--"1011"; 		-- 11  HABT 12/20
			divisor_s  <= X"60920000"; --"0011"; 		-- 3		
			
			
			wait until rising_edge(clk_s);
			start_s <= true;
			wait until rising_edge(clk_s);
			start_s <= false;
			wait until rising_edge(clk_s);
			
			wait until falling_edge(busy_s);
			
			dividend_s <= X"00000003";
			divisor_s  <= X"0000000B";
			wait until rising_edge(clk_s);
			start_s <= true;
			wait until rising_edge(clk_s);
			start_s <= false;
			wait until rising_edge(clk_s);

			wait until falling_edge(busy_s);
			
			dividend_s <= X"0000000B";
			divisor_s  <= X"00000001";
			wait until rising_edge(clk_s);
			start_s <= true;
			wait until rising_edge(clk_s);
			start_s <= false;
			wait until rising_edge(clk_s);
			
			wait until falling_edge(busy_s);
			
			dividend_s <= X"0000002E";
			divisor_s  <= X"00000017";
			wait until rising_edge(clk_s);
			start_s <= true;
			wait until rising_edge(clk_s);
			start_s <= false;
			wait until rising_edge(clk_s);
			

			wait until falling_edge(busy_s);
			
			dividend_s <= X"00000017";
			divisor_s  <= X"0000002E";
			wait until rising_edge(clk_s);
			start_s <= true;
			wait until rising_edge(clk_s);
			start_s <= false;
			wait until rising_edge(clk_s);
			

			wait until falling_edge(busy_s);
			divsigned_s <= true;
			wait for 1 us;
			
			dividend_s <= X"FFFFFFF5";			 		-- -11
			divisor_s  <= X"00000003";  		-- 3
			wait until rising_edge(clk_s);
			start_s <= true;
			wait until rising_edge(clk_s);
			start_s <= false;
			wait until rising_edge(clk_s);
			
			wait until falling_edge(busy_s);		

			wait for 500 ns;
			dividend_s <= X"0000000B";			 		-- 11
			divisor_s  <= X"FFFFFFFD";  		-- -3
			wait until rising_edge(clk_s);
			start_s <= true;
			wait until rising_edge(clk_s);
			start_s <= false;
			wait until rising_edge(clk_s);
			
			wait until falling_edge(busy_s);		
			
			divsigned_s <= true;
			wait for 500 ns;
			dividend_s <= X"00000001";			-- 1
			divisor_s  <= X"80000000";  		-- -1
			wait until rising_edge(clk_s);
			start_s <= true;
			wait until rising_edge(clk_s);
			start_s <= false;
			wait until rising_edge(clk_s);
			
			wait until falling_edge(busy_s);				
					
			--assert FALSE report "End of Simulation" severity failure;
			wait;	
	end process;


end architecture rtl;
