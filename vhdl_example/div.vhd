---------------------------------------------------------------------------------------------------                 
-- Non restoring divider
---------------------------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
USE ieee.numeric_std.all;

entity div is                         
   port( clk          : in   std_logic;                             -- System Clock   
         reset        : in   std_logic;                             -- Active high
		 dividend     : in   unsigned(31 downto 0);
         divisor      : in   unsigned(31 downto 0);		 
		 divsigned	  : in   boolean;								-- false=unsigned, true=signed
         quotient     : out  unsigned(31 downto 0);
         remainder    : out  unsigned(31 downto 0);                           
         start        : in   boolean;
		 busy         : out  boolean);								-- Stall the pipe when asserted
end div;                                                        

architecture rtl of div is
		
	type   states is (sIdle,sAddLoad,sRestore,sDone);               -- Controlling FSM ,sTwos
	signal state: states;
	
	signal count_s    : unsigned(4 downto 0);         				-- Number of iterations
		
	signal dividend_s : unsigned(31 downto 0);
    signal divisor_s  : unsigned(32 downto 0);		
	
	signal twos_s     : std_logic;									-- Correct Quotient
	
	signal Q          : unsigned(31 downto 0);
	signal M          : unsigned(32 downto 0);
	signal minM       : unsigned(32 downto 0);
	
begin

	process(all)
	begin
		if divsigned then
			if dividend(31)='1' then
				dividend_s <= NOT(dividend) + 1;					-- Two's complement	
			else
				dividend_s <= dividend;	
			end if;
			if divisor(31)='1' then
				divisor_s <= NOT(divisor(31)&divisor) + 1;			-- Two's complement	
			else
				divisor_s <= '0'&divisor;	
			end if;
			
			if (dividend(31)='1' AND divisor(31)='0') OR (dividend(31)='0' AND divisor(31)='1') then
				twos_s <= '1';										-- Two's complement quotient
			else
				twos_s <= '0';										-- No correction
			end if;
			
		else
			dividend_s <= dividend;	
			divisor_s  <= '0'&divisor;			
			twos_s     <= '0';										-- No correction
		end if;
	end process;

	minM <= NOT(M) + 1;												-- Two's complement			   		


	-----------------------------------------------------------------------------------------------
	-- Control FSM
	-----------------------------------------------------------------------------------------------
	process (clk,reset)      
		variable A_v  : unsigned(32 downto 0); 
	begin
		if (reset = '1') then     
			state       <= sIdle; 
			count_s     <= (others => '0');
			busy        <= FALSE;	
		elsif (rising_edge(clk)) then  
			case state is
				when sIdle =>   
					A_v := (others => '0');					
					Q <= dividend_s;
					M <= divisor_s;						
				    count_s  <= "11111"; 							-- 32	
				
					if start then 							
						busy <= TRUE;						
						state <= sAddLoad; 
					else 
						busy  <= FALSE;	
					end if; 

				
				when sAddLoad =>						
					if A_v(32)='1' then 
						A_v := A_v(31 downto 0) & Q(31); 			-- shift left
						A_v := A_v + M;
					else
						A_v := A_v(31 downto 0) & Q(31); 			-- shift left
						A_v := A_v + minM;
					end if;
				
					if A_v(32)='1' then 
						Q <= Q(30 downto 0) & '0';
					else
						Q <= Q(30 downto 0) & '1';
					end if;
				
					count_s <= count_s-1;
					if count_s="00000" then			    
						if A_v(32)='1' then
							state <= sRestore;									
						else 
							state <= sDone;
						end if;
					end if;													
							
				when sRestore =>													
					A_v := A_v + M;
					state <= sDone;	
								
				when sDone =>	
					if twos_s='1' then
						quotient <= (NOT(Q(31 downto 0))) + 1;		-- Correct Quotient as it is negative
					else					
						quotient <= Q(31 downto 0);
					end if;

					remainder <= A_v(31 downto 0);  
				
					state <= sIdle;
					busy  <= FALSE;
					
				when others =>                                        
					state <= sIdle; 
					busy  <= FALSE;							
			end case;
		end if;   
	end process;  
	
end rtl;
